import csv
import os
import tempfile
import unittest
from datetime import date, timedelta

from shopledger.cli import main
from shopledger.db import connect
from shopledger.money import format_money, parse_money, plain_money
from shopledger.service import Shop, ShopError


def make_shop() -> Shop:
    return Shop(connect(":memory:"))


class MoneyTests(unittest.TestCase):
    def test_parse_whole_currency(self):
        self.assertEqual(parse_money("1,500"), 1500)

    def test_parse_with_decimals(self):
        self.assertEqual(parse_money("12.50", 2), 1250)
        self.assertEqual(parse_money("0.005", 2), 1)  # rounds half up

    def test_rejects_bad_input(self):
        for bad in ("abc", "-5", "nan", "inf", ""):
            with self.assertRaises(ValueError):
                parse_money(bad)

    def test_format(self):
        self.assertEqual(format_money(1500000, 0, "UGX"), "UGX 1,500,000")
        self.assertEqual(format_money(1250, 2, "USD"), "USD 12.50")
        self.assertEqual(plain_money(1250, 2), "12.50")


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.shop = make_shop()
        self.shop.add_product("Tomatoes", cost=800, price=1200, stock=50, unit="kg", reorder_level=10)

    def test_duplicate_name_is_case_insensitive(self):
        with self.assertRaises(ShopError):
            self.shop.add_product("tomatoes", 1, 2)

    def test_unknown_product(self):
        with self.assertRaises(ShopError):
            self.shop.get_product("Nope")

    def test_bad_expiry_date(self):
        with self.assertRaises(ShopError):
            self.shop.add_product("Milk", 1, 2, expiry="31/12/2026")

    def test_restock_keeps_earliest_expiry(self):
        self.shop.set_price("Tomatoes", 1300)
        self.shop.restock("Tomatoes", 5, expiry="2030-06-01")
        p = self.shop.restock("Tomatoes", 5, expiry="2030-09-01")
        self.assertEqual(p["expiry"], "2030-06-01")
        self.assertEqual(p["stock"], 60)

    def test_restock_updates_cost(self):
        p = self.shop.restock("Tomatoes", 10, cost=900)
        self.assertEqual(p["cost"], 900)

    def test_restock_rejects_non_positive(self):
        with self.assertRaises(ShopError):
            self.shop.restock("Tomatoes", 0)


class SalesTests(unittest.TestCase):
    def setUp(self):
        self.shop = make_shop()
        self.shop.add_product("Rice", cost=3000, price=4000, stock=20, unit="kg", reorder_level=5)

    def test_sale_reduces_stock_and_computes_profit(self):
        res = self.shop.sell("Rice", 4)
        self.assertEqual(res["total"], 16000)
        self.assertEqual(res["profit"], 4000)
        self.assertEqual(res["remaining"], 16)
        self.assertEqual(self.shop.get_product("Rice")["stock"], 16)

    def test_cannot_oversell(self):
        with self.assertRaises(ShopError):
            self.shop.sell("Rice", 21)
        self.assertEqual(self.shop.get_product("Rice")["stock"], 20)  # unchanged
        self.assertEqual(self.shop.list_sales(), [])                   # nothing recorded

    def test_fractional_quantity(self):
        res = self.shop.sell("Rice", 2.5)
        self.assertEqual(res["total"], 10000)
        self.assertEqual(self.shop.get_product("Rice")["stock"], 17.5)

    def test_low_stock_flag(self):
        res = self.shop.sell("Rice", 16)
        self.assertTrue(res["low_stock"])

    def test_price_override(self):
        res = self.shop.sell("Rice", 1, unit_price=3500)
        self.assertEqual(res["total"], 3500)
        self.assertEqual(res["profit"], 500)

    def test_profit_uses_cost_at_time_of_sale(self):
        self.shop.sell("Rice", 1)                  # cost 3000
        self.shop.restock("Rice", 10, cost=3600)   # cost goes up later
        sale = self.shop.list_sales()[0]
        self.assertEqual(sale["profit"], 1000)     # history is not rewritten

    def test_cannot_sell_expired_goods(self):
        self.shop.add_product("Yoghurt", 500, 800, stock=5, expiry="2000-01-01")
        with self.assertRaises(ShopError):
            self.shop.sell("Yoghurt", 1)
        self.shop.sell("Yoghurt", 1, allow_expired=True)

    def test_rejects_zero_or_negative_qty(self):
        for q in (0, -1):
            with self.assertRaises(ShopError):
                self.shop.sell("Rice", q)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.shop = make_shop()
        self.shop.add_product("Rice", 3000, 4000, stock=100, unit="kg")
        self.shop.add_product("Beans", 2000, 3000, stock=100, unit="kg")
        self.shop.sell("Rice", 10, sold_at="2026-03-01T10:00:00")   # rev 40000, profit 10000
        self.shop.sell("Beans", 5, sold_at="2026-03-02T10:00:00")   # rev 15000, profit 5000
        self.shop.sell("Rice", 1, sold_at="2026-04-01T10:00:00")    # outside March
        self.shop.add_expense("Transport", 4000, spent_at="2026-03-02T08:00:00")
        self.shop.add_expense("Rent", 6000, spent_at="2026-03-03T08:00:00")
        self.shop.add_expense("Rent", 6000, spent_at="2026-04-03T08:00:00")

    def test_period_report(self):
        r = self.shop.report("2026-03-01", "2026-03-31")
        self.assertEqual(r["revenue"], 55000)
        self.assertEqual(r["cogs"], 40000)
        self.assertEqual(r["gross_profit"], 15000)
        self.assertEqual(r["expenses"], 10000)
        self.assertEqual(r["net_profit"], 5000)
        self.assertEqual(r["sales_count"], 2)
        self.assertEqual(r["top_products"][0]["name"], "Rice")

    def test_all_time_report(self):
        r = self.shop.report()
        self.assertEqual(r["revenue"], 59000)
        self.assertEqual(r["expenses"], 16000)

    def test_stock_value(self):
        r = self.shop.report()
        self.assertEqual(r["stock_value"], 89 * 3000 + 95 * 2000)

    def test_empty_report_does_not_crash(self):
        r = make_shop().report()
        self.assertEqual(r["net_profit"], 0)
        self.assertEqual(r["margin_pct"], 0.0)

    def test_bad_date(self):
        with self.assertRaises(ShopError):
            self.shop.report("yesterday")

    def test_csv_export(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sales.csv")
            n = self.shop.export_sales_csv(path, "2026-03-01", "2026-03-31")
            self.assertEqual(n, 2)
            with open(path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["product"], "Rice")
            self.assertEqual(rows[0]["total"], "40000")


class AlertTests(unittest.TestCase):
    def test_alert_groups(self):
        shop = make_shop()
        today = date(2026, 6, 15)
        shop.add_product("Low", 1, 2, stock=2, reorder_level=5)
        shop.add_product("Fine", 1, 2, stock=50, reorder_level=5)
        shop.add_product("Soon", 1, 2, stock=5, expiry=(today + timedelta(days=3)).isoformat())
        shop.add_product("Old", 1, 2, stock=5, expiry=(today - timedelta(days=1)).isoformat())
        shop.add_product("OldEmpty", 1, 2, stock=0, expiry=(today - timedelta(days=9)).isoformat())
        a = shop.alerts(today=today, expiry_days=7)
        self.assertIn("Low", [p["name"] for p in a["low_stock"]])
        self.assertNotIn("Fine", [p["name"] for p in a["low_stock"]])
        self.assertEqual([p["name"] for p in a["expiring"]], ["Soon"])
        self.assertEqual([p["name"] for p in a["expired"]], ["Old"])  # empty shelf is not a problem


class CliTests(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "t.db")
            run = lambda *a: main(["--db", db, *a])
            self.assertEqual(run("add", "Sugar", "--cost", "3,000", "--price", "3,800",
                                 "--stock", "10", "--unit", "kg"), 0)
            self.assertEqual(run("sell", "Sugar", "2"), 0)
            self.assertEqual(run("sell", "Sugar", "99"), 1)        # error exit code
            self.assertEqual(run("expense", "Transport", "1000"), 0)
            self.assertEqual(run("report"), 0)
            self.assertEqual(run("alerts"), 0)
            self.assertEqual(run("products"), 0)
            self.assertEqual(run("add", "Bad", "--cost", "abc", "--price", "1"), 1)


if __name__ == "__main__":
    unittest.main()
