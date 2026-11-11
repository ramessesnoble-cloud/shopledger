"""Business logic. No printing and no argument parsing in here, so it is easy to test
and easy to reuse later from a web API or a GUI."""

from __future__ import annotations

import csv
import sqlite3
from datetime import date, datetime, timedelta
from typing import Optional

from .money import plain_money


class ShopError(Exception):
    """A problem the user can fix (bad input, not enough stock, unknown product...)."""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _check_date(text: Optional[str], label: str) -> Optional[str]:
    if text is None:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise ShopError(f"{label} must be a date like 2026-12-31, got {text!r}") from None


def _positive(value: float, label: str) -> float:
    if not value > 0:
        raise ShopError(f"{label} must be greater than 0")
    return value


class Shop:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ------------------------------------------------------------------ settings
    def get_setting(self, key: str, default: str) -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    @property
    def currency(self) -> str:
        return self.get_setting("currency", "UGX")

    @property
    def decimals(self) -> int:
        return int(self.get_setting("decimals", "0"))

    # ------------------------------------------------------------------ products
    def add_product(self, name: str, cost: int, price: int, stock: float = 0,
                    unit: str = "unit", reorder_level: float = 0,
                    expiry: Optional[str] = None) -> None:
        name = name.strip()
        if not name:
            raise ShopError("product name cannot be empty")
        if stock < 0 or reorder_level < 0:
            raise ShopError("stock and reorder level cannot be negative")
        expiry = _check_date(expiry, "expiry")
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO products(name, unit, cost, price, stock, reorder_level, expiry, created_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, unit, cost, price, stock, reorder_level, expiry, _now()),
                )
        except sqlite3.IntegrityError:
            raise ShopError(f"product {name!r} already exists") from None

    def get_product(self, name: str) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM products WHERE name = ?", (name.strip(),)).fetchone()
        if row is None:
            raise ShopError(f"no product named {name!r} (see: shopledger products)")
        return row

    def list_products(self) -> list:
        return self.conn.execute("SELECT * FROM products ORDER BY name").fetchall()

    def restock(self, name: str, qty: float, cost: Optional[int] = None,
                expiry: Optional[str] = None) -> sqlite3.Row:
        """Add stock. Tracks the EARLIEST expiry still on the shelf, so an old batch
        is never hidden by a newer one."""
        _positive(qty, "quantity")
        p = self.get_product(name)
        expiry = _check_date(expiry, "expiry")
        new_expiry = p["expiry"]
        if expiry:
            if p["stock"] > 0 and p["expiry"]:
                new_expiry = min(p["expiry"], expiry)
            else:
                new_expiry = expiry
        with self.conn:
            self.conn.execute(
                "UPDATE products SET stock = ROUND(stock + ?, 6), cost = ?, expiry = ? WHERE id = ?",
                (qty, p["cost"] if cost is None else cost, new_expiry, p["id"]),
            )
        return self.get_product(name)

    def set_price(self, name: str, price: int) -> None:
        p = self.get_product(name)
        with self.conn:
            self.conn.execute("UPDATE products SET price = ? WHERE id = ?", (price, p["id"]))

    # --------------------------------------------------------------------- sales
    def sell(self, name: str, qty: float, unit_price: Optional[int] = None,
             sold_at: Optional[str] = None, today: Optional[date] = None,
             allow_expired: bool = False) -> dict:
        _positive(qty, "quantity")
        today = today or date.today()
        with self.conn:  # one transaction: stock and sale record change together or not at all
            p = self.get_product(name)
            if p["stock"] + 1e-9 < qty:
                raise ShopError(
                    f"only {p['stock']:g} {p['unit']} of {p['name']} in stock, cannot sell {qty:g}")
            if p["expiry"] and p["expiry"] < today.isoformat() and not allow_expired:
                raise ShopError(
                    f"{p['name']} expired on {p['expiry']}; remove it from stock "
                    f"(or pass --allow-expired to override)")
            price = p["price"] if unit_price is None else unit_price
            total = int(round(qty * price))
            self.conn.execute("UPDATE products SET stock = ROUND(stock - ?, 6) WHERE id = ?",
                              (qty, p["id"]))
            self.conn.execute(
                "INSERT INTO sales(product_id, qty, unit_price, unit_cost, total, sold_at) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (p["id"], qty, price, p["cost"], total, sold_at or _now()),
            )
        profit = total - int(round(qty * p["cost"]))
        remaining = round(p["stock"] - qty, 6)
        return {"total": total, "profit": profit, "remaining": remaining, "unit": p["unit"],
                "low_stock": remaining <= p["reorder_level"], "name": p["name"]}

    def list_sales(self, limit: int = 20) -> list:
        return self.conn.execute(
            "SELECT s.id, s.sold_at, p.name, p.unit, s.qty, s.unit_price, s.total, "
            "CAST(ROUND(s.total - s.qty * s.unit_cost) AS INTEGER) AS profit "
            "FROM sales s JOIN products p ON p.id = s.product_id "
            "ORDER BY s.sold_at DESC, s.id DESC LIMIT ?", (limit,)).fetchall()

    # ------------------------------------------------------------------ expenses
    def add_expense(self, category: str, amount: int, note: str = "",
                    spent_at: Optional[str] = None) -> None:
        category = category.strip()
        if not category:
            raise ShopError("expense category cannot be empty")
        with self.conn:
            self.conn.execute(
                "INSERT INTO expenses(category, amount, note, spent_at) VALUES(?, ?, ?, ?)",
                (category, amount, note, spent_at or _now()))

    def list_expenses(self, limit: int = 20) -> list:
        return self.conn.execute(
            "SELECT id, category, amount, note, spent_at FROM expenses "
            "ORDER BY spent_at DESC, id DESC LIMIT ?", (limit,)).fetchall()

    # -------------------------------------------------------------------- alerts
    def alerts(self, today: Optional[date] = None, expiry_days: int = 7) -> dict:
        today = today or date.today()
        soon = (today + timedelta(days=expiry_days)).isoformat()
        t = today.isoformat()
        q = self.conn.execute
        return {
            "low_stock": q("SELECT * FROM products WHERE stock <= reorder_level ORDER BY name").fetchall(),
            "expiring": q("SELECT * FROM products WHERE stock > 0 AND expiry IS NOT NULL "
                          "AND expiry >= ? AND expiry <= ? ORDER BY expiry", (t, soon)).fetchall(),
            "expired": q("SELECT * FROM products WHERE stock > 0 AND expiry IS NOT NULL "
                         "AND expiry < ? ORDER BY expiry", (t,)).fetchall(),
        }

    # ------------------------------------------------------------------- reports
    @staticmethod
    def _range(column: str, start: Optional[str], end: Optional[str]):
        clauses, params = [], []
        if start:
            clauses.append(f"date({column}) >= ?")
            params.append(_check_date(start, "start date"))
        if end:
            clauses.append(f"date({column}) <= ?")
            params.append(_check_date(end, "end date"))
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def report(self, start: Optional[str] = None, end: Optional[str] = None) -> dict:
        s_where, s_params = self._range("s.sold_at", start, end)
        e_where, e_params = self._range("spent_at", start, end)
        q = self.conn.execute
        row = q("SELECT COALESCE(SUM(s.total), 0) AS revenue, "
                "COALESCE(SUM(CAST(ROUND(s.qty * s.unit_cost) AS INTEGER)), 0) AS cogs, "
                "COUNT(*) AS sales_count FROM sales s" + s_where, s_params).fetchone()
        expenses = q("SELECT COALESCE(SUM(amount), 0) AS total FROM expenses" + e_where,
                     e_params).fetchone()["total"]
        by_category = q("SELECT category, SUM(amount) AS total FROM expenses" + e_where +
                        " GROUP BY category ORDER BY total DESC", e_params).fetchall()
        top = q("SELECT p.name, p.unit, SUM(s.qty) AS qty, SUM(s.total) AS revenue, "
                "CAST(ROUND(SUM(s.total - s.qty * s.unit_cost)) AS INTEGER) AS profit "
                "FROM sales s JOIN products p ON p.id = s.product_id" + s_where +
                " GROUP BY p.id ORDER BY profit DESC LIMIT 5", s_params).fetchall()
        stock_value = q("SELECT COALESCE(CAST(ROUND(SUM(stock * cost)) AS INTEGER), 0) AS v "
                        "FROM products").fetchone()["v"]
        gross = row["revenue"] - row["cogs"]
        return {"revenue": row["revenue"], "cogs": row["cogs"], "gross_profit": gross,
                "expenses": expenses, "net_profit": gross - expenses,
                "sales_count": row["sales_count"], "expenses_by_category": by_category,
                "top_products": top, "stock_value": stock_value,
                "margin_pct": (gross / row["revenue"] * 100) if row["revenue"] else 0.0}

    # -------------------------------------------------------------------- export
    def export_sales_csv(self, path: str, start: Optional[str] = None,
                         end: Optional[str] = None) -> int:
        where, params = self._range("s.sold_at", start, end)
        rows = self.conn.execute(
            "SELECT s.id, s.sold_at, p.name, p.unit, s.qty, s.unit_price, s.total, "
            "CAST(ROUND(s.total - s.qty * s.unit_cost) AS INTEGER) AS profit "
            "FROM sales s JOIN products p ON p.id = s.product_id" + where +
            " ORDER BY s.sold_at, s.id", params).fetchall()
        d = self.decimals
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "sold_at", "product", "unit", "qty", "unit_price", "total", "profit"])
            for r in rows:
                w.writerow([r["id"], r["sold_at"], r["name"], r["unit"], f"{r['qty']:g}",
                            plain_money(r["unit_price"], d), plain_money(r["total"], d),
                            plain_money(r["profit"], d)])
        return len(rows)
