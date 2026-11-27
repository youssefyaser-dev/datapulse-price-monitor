import sqlite3
from contextlib import closing

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY, label TEXT NOT NULL UNIQUE, started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  products INTEGER NOT NULL DEFAULT 0, rejects INTEGER NOT NULL DEFAULT 0, requests INTEGER NOT NULL DEFAULT 0, retries INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS products (
  sku TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, rating REAL, first_run INTEGER REFERENCES runs(id), last_run INTEGER REFERENCES runs(id)
);
CREATE TABLE IF NOT EXISTS prices (
  run_id INTEGER NOT NULL REFERENCES runs(id), sku TEXT NOT NULL REFERENCES products(sku),
  price INTEGER NOT NULL CHECK (price > 0), in_stock INTEGER, PRIMARY KEY (run_id, sku)
);
CREATE TABLE IF NOT EXISTS rejects (run_id INTEGER NOT NULL REFERENCES runs(id), sku TEXT, reason TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_prices_sku ON prices(sku);
"""


def connect(path=':memory:'):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.executescript(SCHEMA)
    return conn


def load_run(conn, label, records, rejects=(), stats=None):
    """Load one crawl atomically. Re-loading the same label replaces that run."""
    stats = stats or {}
    with conn:
        old = conn.execute('SELECT id FROM runs WHERE label = ?', (label,)).fetchone()
        if old:
            conn.execute('DELETE FROM prices WHERE run_id = ?', (old['id'],))
            conn.execute('DELETE FROM rejects WHERE run_id = ?', (old['id'],))
            conn.execute('UPDATE runs SET products=?, rejects=?, requests=?, retries=?, started_at=CURRENT_TIMESTAMP WHERE id=?',
                         (len(records), len(rejects), stats.get('requests', 0), stats.get('retries', 0), old['id']))
            run_id = old['id']
        else:
            run_id = conn.execute('INSERT INTO runs (label, products, rejects, requests, retries) VALUES (?,?,?,?,?)',
                                  (label, len(records), len(rejects), stats.get('requests', 0), stats.get('retries', 0))).lastrowid
        for r in records:
            conn.execute(
                """INSERT INTO products (sku, name, category, rating, first_run, last_run) VALUES (?,?,?,?,?,?)
                   ON CONFLICT(sku) DO UPDATE SET name=excluded.name, category=excluded.category,
                     rating=COALESCE(excluded.rating, products.rating), last_run=MAX(products.last_run, excluded.last_run)""",
                (r['sku'], r['name'], r['category'], r.get('rating'), run_id, run_id))
            conn.execute('INSERT INTO prices (run_id, sku, price, in_stock) VALUES (?,?,?,?)',
                         (run_id, r['sku'], r['price'], None if r.get('in_stock') is None else int(r['in_stock'])))
        for b in rejects:
            conn.execute('INSERT INTO rejects (run_id, sku, reason) VALUES (?,?,?)', (run_id, b.get('sku'), b['reason']))
    return run_id


def runs(conn):
    return [dict(r) for r in conn.execute('SELECT * FROM runs ORDER BY id')]
