"""Local web interface. Standard library only.

Security model: the server binds to 127.0.0.1 (this computer only), rejects requests
whose Host header is not localhost (DNS-rebinding protection) and only accepts
JSON POSTs (browsers cannot send those cross-site without a CORS preflight, which
this server never approves). There is no login, so do not expose it to a network."""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .db import connect
from .money import parse_money
from .service import Shop, ShopError
from .ui import INDEX_HTML

ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
MAX_BODY = 1_000_000


def _num(value, label: str) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ShopError(f"{label} must be a number") from None
    if not math.isfinite(n):
        raise ShopError(f"{label} must be a number")
    return n


def _opt(data: dict, key: str):
    v = data.get(key)
    if v is None or str(v).strip() == "":
        return None
    return str(v).strip()


def _req(data: dict, key: str, label: str) -> str:
    v = _opt(data, key)
    if v is None:
        raise ShopError(f"{label} is required")
    return v


def _rows(rows) -> list:
    return [dict(r) for r in rows]


def _report(r: dict) -> dict:
    r = dict(r)
    r["expenses_by_category"] = _rows(r["expenses_by_category"])
    r["top_products"] = _rows(r["top_products"])
    return r


def build_state(shop: Shop) -> dict:
    today = date.today()
    alerts = shop.alerts()
    return {
        "currency": shop.currency,
        "decimals": shop.decimals,
        "today": today.isoformat(),
        "products": _rows(shop.list_products()),
        "alerts": {k: _rows(v) for k, v in alerts.items()},
        "report_today": _report(shop.report(today.isoformat(), today.isoformat())),
        "report_month": _report(shop.report(today.replace(day=1).isoformat(), today.isoformat())),
        "sales": _rows(shop.list_sales(15)),
        "expenses": _rows(shop.list_expenses(15)),
    }


def make_handler(db_path: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ShopLedger"

        def log_message(self, *args):  # keep the terminal quiet
            pass

        # ---- helpers
        def _send(self, status: int, body: bytes, ctype: str, extra=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj):
            self._send(status, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

        def _host_ok(self) -> bool:
            host = self.headers.get("Host", "")
            return host.rsplit(":", 1)[0].strip("[]") in ALLOWED_HOSTS if ":" in host else host in ALLOWED_HOSTS

        # ---- routes
        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {"error": "forbidden host"})
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/":
                    return self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
                conn = connect(db_path)
                try:
                    shop = Shop(conn)
                    if url.path == "/api/state":
                        return self._json(200, build_state(shop))
                    if url.path == "/api/report":
                        return self._json(200, _report(shop.report(q.get("start") or None, q.get("end") or None)))
                    if url.path == "/api/export.csv":
                        fd, tmp = tempfile.mkstemp(suffix=".csv")
                        os.close(fd)
                        try:
                            shop.export_sales_csv(tmp, q.get("start") or None, q.get("end") or None)
                            with open(tmp, "rb") as f:
                                data = f.read()
                        finally:
                            os.remove(tmp)
                        return self._send(200, data, "text/csv; charset=utf-8",
                                          {"Content-Disposition": 'attachment; filename="sales.csv"'})
                finally:
                    conn.close()
                self._json(404, {"error": "not found"})
            except (ShopError, ValueError) as err:
                self._json(400, {"error": str(err)})
            except Exception:
                self._json(500, {"error": "unexpected server error"})

        def do_POST(self):
            if not self._host_ok():
                return self._json(403, {"error": "forbidden host"})
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._json(415, {"error": "JSON only"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > MAX_BODY:
                    return self._json(413, {"error": "request too large"})
                data = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(data, dict):
                    raise ShopError("invalid request")
                conn = connect(db_path)
                try:
                    shop = Shop(conn)
                    result = self._dispatch(urlparse(self.path).path, shop, data)
                finally:
                    conn.close()
                if result is None:
                    return self._json(404, {"error": "not found"})
                self._json(200, result)
            except json.JSONDecodeError:
                self._json(400, {"error": "invalid JSON"})
            except (ShopError, ValueError) as err:
                self._json(400, {"error": str(err)})
            except Exception:
                self._json(500, {"error": "unexpected server error"})

        @staticmethod
        def _dispatch(path: str, shop: Shop, d: dict):
            money = lambda key, label: parse_money(_req(d, key, label), shop.decimals)
            if path == "/api/product":
                shop.add_product(_req(d, "name", "name"), money("cost", "cost"), money("price", "price"),
                                 _num(d.get("stock") or 0, "stock"), _opt(d, "unit") or "unit",
                                 _num(d.get("reorder") or 0, "reorder level"), _opt(d, "expiry"))
                return {"ok": True}
            if path == "/api/restock":
                cost = parse_money(_opt(d, "cost"), shop.decimals) if _opt(d, "cost") else None
                p = shop.restock(_req(d, "name", "name"), _num(d.get("qty"), "quantity"), cost, _opt(d, "expiry"))
                return {"ok": True, "stock": p["stock"]}
            if path == "/api/price":
                shop.set_price(_req(d, "name", "name"), money("price", "price"))
                return {"ok": True}
            if path == "/api/sell":
                price = parse_money(_opt(d, "price"), shop.decimals) if _opt(d, "price") else None
                return {"ok": True, **shop.sell(_req(d, "name", "product"), _num(d.get("qty"), "quantity"), price)}
            if path == "/api/expense":
                shop.add_expense(_req(d, "category", "category"), money("amount", "amount"), _opt(d, "note") or "")
                return {"ok": True}
            return None

    return Handler


def create_server(db_path: str, port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(db_path))


def serve(db_path: str, port: int = 8000, open_browser: bool = True) -> None:
    try:
        server = create_server(db_path, port)
    except OSError:
        raise ShopError(f"port {port} is busy; try: python -m shopledger web --port {port + 1}") from None
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"ShopLedger is running at {url}\nPress Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
