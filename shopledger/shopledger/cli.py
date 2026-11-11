"""Command-line interface:  python -m shopledger <command> --help"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from . import __version__
from .db import connect, default_path
from .money import format_money, parse_money
from .service import Shop, ShopError


def table(headers, rows) -> str:
    rows = [[str(c) for c in r] for r in rows]
    widths = [max([len(h)] + [len(r[i]) for r in rows]) for i, h in enumerate(headers)]
    line = lambda cells: "  ".join(c.ljust(w) for c, w in zip(cells, widths)).rstrip()
    out = [line(headers), line(["-" * w for w in widths])]
    out += [line(r) for r in rows]
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="shopledger",
                                description="Inventory, sales and profit tracker for small shops.")
    p.add_argument("--db", help=f"database file (default: {default_path()}, or $SHOPLEDGER_DB)")
    p.add_argument("--version", action="version", version=f"shopledger {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("config", help="set currency / decimal places")
    c.add_argument("--currency")
    c.add_argument("--decimals", type=int, choices=range(0, 5))

    a = sub.add_parser("add", help="add a new product")
    a.add_argument("name")
    a.add_argument("--cost", required=True, help="what one unit costs you")
    a.add_argument("--price", required=True, help="what you sell one unit for")
    a.add_argument("--stock", type=float, default=0)
    a.add_argument("--unit", default="unit", help="kg, bag, box, piece...")
    a.add_argument("--reorder", type=float, default=0, help="warn when stock falls to this level")
    a.add_argument("--expiry", help="YYYY-MM-DD")

    r = sub.add_parser("restock", help="add stock to a product")
    r.add_argument("name")
    r.add_argument("qty", type=float)
    r.add_argument("--cost", help="new unit cost, if it changed")
    r.add_argument("--expiry", help="expiry of the new batch, YYYY-MM-DD")

    sp = sub.add_parser("set-price", help="change selling price")
    sp.add_argument("name")
    sp.add_argument("price")

    s = sub.add_parser("sell", help="record a sale")
    s.add_argument("name")
    s.add_argument("qty", type=float)
    s.add_argument("--price", help="override the unit price for this sale")
    s.add_argument("--allow-expired", action="store_true")

    sub.add_parser("products", help="list products and stock")

    sl = sub.add_parser("sales", help="list recent sales")
    sl.add_argument("--limit", type=int, default=20)

    e = sub.add_parser("expense", help="record an expense (rent, transport, wages...)")
    e.add_argument("category")
    e.add_argument("amount")
    e.add_argument("--note", default="")

    al = sub.add_parser("alerts", help="low stock, expiring and expired products")
    al.add_argument("--days", type=int, default=7, help="expiry warning window (default 7)")

    rp = sub.add_parser("report", help="profit report")
    rp.add_argument("--from", dest="start", help="YYYY-MM-DD")
    rp.add_argument("--to", dest="end", help="YYYY-MM-DD")
    rp.add_argument("--today", action="store_true")
    rp.add_argument("--month", action="store_true", help="this calendar month")

    w = sub.add_parser("web", help="open the app in your browser")
    w.add_argument("--port", type=int, default=8000)
    w.add_argument("--no-browser", action="store_true")

    ex = sub.add_parser("export", help="export sales to CSV (opens in Excel)")
    ex.add_argument("path")
    ex.add_argument("--from", dest="start")
    ex.add_argument("--to", dest="end")
    return p


def run(args, shop: Shop) -> int:
    money = lambda v: format_money(v, shop.decimals, shop.currency)
    parse = lambda t: parse_money(t, shop.decimals)
    cmd = args.command

    if cmd == "config":
        if args.currency:
            shop.set_setting("currency", args.currency.upper())
        if args.decimals is not None:
            shop.set_setting("decimals", str(args.decimals))
        print(f"currency={shop.currency} decimals={shop.decimals}")

    elif cmd == "add":
        shop.add_product(args.name, parse(args.cost), parse(args.price), args.stock,
                         args.unit, args.reorder, args.expiry)
        print(f"Added {args.name}: cost {money(parse(args.cost))}, price {money(parse(args.price))}, "
              f"stock {args.stock:g} {args.unit}")

    elif cmd == "restock":
        p = shop.restock(args.name, args.qty, parse(args.cost) if args.cost else None, args.expiry)
        print(f"{p['name']}: stock now {p['stock']:g} {p['unit']}")

    elif cmd == "set-price":
        shop.set_price(args.name, parse(args.price))
        print(f"Price of {args.name} set to {money(parse(args.price))}")

    elif cmd == "sell":
        res = shop.sell(args.name, args.qty, parse(args.price) if args.price else None,
                        allow_expired=args.allow_expired)
        print(f"Sold {args.qty:g} {res['unit']} of {res['name']} for {money(res['total'])} "
              f"(profit {money(res['profit'])}). Remaining: {res['remaining']:g}")
        if res["low_stock"]:
            print(f"  ! Low stock: only {res['remaining']:g} {res['unit']} left, time to restock.")

    elif cmd == "products":
        rows = []
        for p in shop.list_products():
            margin = (p["price"] - p["cost"]) / p["price"] * 100 if p["price"] else 0
            flag = "LOW" if p["stock"] <= p["reorder_level"] else ""
            rows.append([p["name"], f"{p['stock']:g} {p['unit']}", money(p["cost"]), money(p["price"]),
                         f"{margin:.0f}%", p["expiry"] or "-", flag])
        print(table(["PRODUCT", "STOCK", "COST", "PRICE", "MARGIN", "EXPIRY", ""], rows)
              if rows else "No products yet. Add one with: shopledger add NAME --cost X --price Y")

    elif cmd == "sales":
        rows = [[s["id"], s["sold_at"].replace("T", " "), s["name"], f"{s['qty']:g} {s['unit']}",
                 money(s["total"]), money(s["profit"])] for s in shop.list_sales(args.limit)]
        print(table(["ID", "WHEN", "PRODUCT", "QTY", "TOTAL", "PROFIT"], rows) if rows else "No sales yet.")

    elif cmd == "expense":
        shop.add_expense(args.category, parse(args.amount), args.note)
        print(f"Recorded expense: {args.category} {money(parse(args.amount))}")

    elif cmd == "alerts":
        a = shop.alerts(expiry_days=args.days)
        if not any(a.values()):
            print("All clear: no low stock or expiry problems.")
        if a["low_stock"]:
            print("LOW / OUT OF STOCK")
            print(table(["PRODUCT", "STOCK", "REORDER AT"],
                        [[p["name"], f"{p['stock']:g} {p['unit']}", f"{p['reorder_level']:g}"]
                         for p in a["low_stock"]]) + "\n")
        if a["expiring"]:
            print(f"EXPIRING WITHIN {args.days} DAYS")
            print(table(["PRODUCT", "STOCK", "EXPIRES"],
                        [[p["name"], f"{p['stock']:g} {p['unit']}", p["expiry"]]
                         for p in a["expiring"]]) + "\n")
        if a["expired"]:
            print("EXPIRED (remove from shelf)")
            print(table(["PRODUCT", "STOCK", "EXPIRED ON"],
                        [[p["name"], f"{p['stock']:g} {p['unit']}", p["expiry"]]
                         for p in a["expired"]]))

    elif cmd == "report":
        start, end = args.start, args.end
        today = date.today()
        if args.today:
            start = end = today.isoformat()
        elif args.month:
            start, end = today.replace(day=1).isoformat(), today.isoformat()
        r = shop.report(start, end)
        print(f"PROFIT REPORT  {start or 'beginning'} -> {end or 'now'}")
        print(f"  Sales made      {r['sales_count']}")
        print(f"  Revenue         {money(r['revenue'])}")
        print(f"  Cost of goods   {money(r['cogs'])}")
        print(f"  Gross profit    {money(r['gross_profit'])}  ({r['margin_pct']:.1f}% margin)")
        print(f"  Expenses        {money(r['expenses'])}")
        print(f"  NET PROFIT      {money(r['net_profit'])}")
        print(f"  Stock on hand   {money(r['stock_value'])} (at cost)")
        if r["expenses_by_category"]:
            print("\nExpenses by category")
            print(table(["CATEGORY", "TOTAL"], [[c["category"], money(c["total"])]
                                                  for c in r["expenses_by_category"]]))
        if r["top_products"]:
            print("\nTop products by profit")
            print(table(["PRODUCT", "QTY SOLD", "REVENUE", "PROFIT"],
                        [[t["name"], f"{t['qty']:g} {t['unit']}", money(t["revenue"]), money(t["profit"])]
                         for t in r["top_products"]]))

    elif cmd == "export":
        n = shop.export_sales_csv(args.path, args.start, args.end)
        print(f"Exported {n} sales to {args.path}")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "web":
            from .web import serve
            serve(args.db or default_path(), args.port, not args.no_browser)
            return 0
        conn = connect(args.db)
        try:
            return run(args, Shop(conn))
        finally:
            conn.close()
    except (ShopError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
