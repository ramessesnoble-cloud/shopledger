"""SQLite connection and schema."""

import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    unit TEXT NOT NULL DEFAULT 'unit',
    cost INTEGER NOT NULL DEFAULT 0 CHECK (cost >= 0),
    price INTEGER NOT NULL DEFAULT 0 CHECK (price >= 0),
    stock REAL NOT NULL DEFAULT 0 CHECK (stock >= 0),
    reorder_level REAL NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
    expiry TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    qty REAL NOT NULL CHECK (qty > 0),
    unit_price INTEGER NOT NULL,
    unit_cost INTEGER NOT NULL,
    total INTEGER NOT NULL,
    sold_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sold_at);
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK (amount >= 0),
    note TEXT NOT NULL DEFAULT '',
    spent_at TEXT NOT NULL
);
"""


def default_path() -> str:
    env = os.environ.get("SHOPLEDGER_DB")
    if env:
        return env
    return str(Path.home() / ".shopledger" / "shop.db")


def connect(path=None) -> sqlite3.Connection:
    path = path or default_path()
    if path != ":memory:":
        Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
