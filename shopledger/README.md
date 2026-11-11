# ShopLedger

Inventory, sales and profit tracking for small shops, market traders and kiosks.
Runs offline on any computer, stores everything in one local file, needs **no
dependencies** beyond Python 3.9+.

## The problem

Small businesses often lose money without noticing: goods spoil on the shelf,
stock runs out at the wrong time, and nobody knows the real profit once rent and
transport are counted. ShopLedger answers three questions every day:

1. **What do I have, and what is running out or about to expire?**
2. **What did I sell, and how much did I actually make on it?**
3. **After expenses, did the business earn money this week/month?**

## Quick start (app with screens)

```bash
python -m shopledger web
```

This opens ShopLedger in your browser at `http://127.0.0.1:8000` with a dashboard, Sell,
Products, Expenses and Reports screens. It runs only on your own computer (no internet,
no login needed). Press `Ctrl+C` in the terminal to stop it.

## Command line


```bash
git clone https://github.com/<your-username>/shopledger.git
cd shopledger
python -m shopledger --help
```

Optional: `pip install -e .` gives you a `shopledger` command instead of `python -m shopledger`.

```bash
# one-time: choose currency (default UGX, 0 decimals)
python -m shopledger config --currency UGX --decimals 0

# add products
python -m shopledger add Tomatoes --cost 800 --price 1200 --stock 50 --unit kg --reorder 10 --expiry 2026-12-01
python -m shopledger add Rice --cost 3000 --price 4000 --stock 100 --unit kg --reorder 20

# daily work
python -m shopledger sell Tomatoes 4
python -m shopledger restock Rice 50 --cost 3200
python -m shopledger expense Transport 15000 --note "market trip"

# insight
python -m shopledger products
python -m shopledger alerts
python -m shopledger report --month
python -m shopledger export sales.csv --from 2026-01-01
```

## Rules the app enforces

- You cannot sell more than you have in stock.
- Expired goods cannot be sold (unless you pass `--allow-expired`).
- Profit uses the cost **at the time of sale**, so later price changes never rewrite history.
- Sales and stock changes happen in one database transaction: no half-recorded sales.
- Money is stored as integers, never floats, so the books always add up.
- Restocking tracks the **earliest** expiry on the shelf, so an old batch is not hidden by a new one.

## Where is my data?

`~/.shopledger/shop.db` (a SQLite file). Use `--db PATH` or the `SHOPLEDGER_DB`
environment variable to keep it elsewhere. **Back this file up.**

## Project layout

```
shopledger/
  money.py     integer money parsing/formatting
  db.py        SQLite schema and connection
  service.py   all business rules (no printing, easy to test and reuse)
  cli.py       command-line interface
  web.py       local web server (JSON API, localhost only)
  ui.py        the browser interface
tests/         31 tests (business rules, CLI and web API)
.github/workflows/ci.yml   runs tests on Python 3.9-3.12 for every push
```

## Development

```bash
python -m unittest discover -s tests -v
```

## Roadmap

- [ ] Per-batch expiry tracking
- [ ] Sale voids / returns
- [ ] Customer credit (who owes me money)
- [x] Local web interface
- [ ] Login + hosted version so shopkeepers can use it from their phones
- [ ] Multi-shop support and sync
- [ ] Mobile money (MTN MoMo / Airtel Money) payment records

## License

MIT
