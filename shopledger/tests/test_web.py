import http.client
import json
import os
import tempfile
import threading
import unittest

from shopledger.web import create_server


class WebApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.server = create_server(os.path.join(cls.tmp.name, "w.db"), port=0)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def call(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        h = dict(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body)
            h.setdefault("Content-Type", "application/json")
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        raw = r.read()
        c.close()
        return r.status, raw

    def test_flow(self):
        s, raw = self.call("GET", "/")
        self.assertEqual(s, 200)
        self.assertIn(b"ShopLedger", raw)
        s, _ = self.call("POST", "/api/product", {"name": "Rice", "cost": "3,000", "price": "4000",
                                                  "stock": "10", "unit": "kg", "reorder": "2"})
        self.assertEqual(s, 200)
        s, raw = self.call("POST", "/api/sell", {"name": "Rice", "qty": "3"})
        self.assertEqual(s, 200)
        self.assertEqual(json.loads(raw)["total"], 12000)
        s, raw = self.call("POST", "/api/sell", {"name": "Rice", "qty": "99"})
        self.assertEqual(s, 400)
        self.assertIn("in stock", json.loads(raw)["error"])
        s, _ = self.call("POST", "/api/expense", {"category": "Transport", "amount": "1000"})
        self.assertEqual(s, 200)
        s, raw = self.call("GET", "/api/state")
        st = json.loads(raw)
        self.assertEqual(st["report_today"]["revenue"], 12000)
        self.assertEqual(st["report_today"]["net_profit"], 2000)
        self.assertEqual(st["products"][0]["stock"], 7)
        s, raw = self.call("GET", "/api/export.csv")
        self.assertEqual(s, 200)
        self.assertIn(b"Rice", raw)

    def test_validation_errors_are_400_not_500(self):
        for body in ({"name": "X"}, {"name": "X", "cost": "abc", "price": "1"},
                     {"name": "", "cost": "1", "price": "1"}):
            s, _ = self.call("POST", "/api/product", body)
            self.assertEqual(s, 400)

    def test_rejects_non_json_post(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        c.request("POST", "/api/sell", body="name=Rice&qty=1",
                  headers={"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(c.getresponse().status, 415)

    def test_rejects_foreign_host_header(self):
        s, _ = self.call("GET", "/api/state", headers={"Host": "evil.example.com"})
        self.assertEqual(s, 403)

    def test_unknown_route(self):
        self.assertEqual(self.call("GET", "/api/nope")[0], 404)
        self.assertEqual(self.call("POST", "/api/nope", {})[0], 404)


if __name__ == "__main__":
    unittest.main()
