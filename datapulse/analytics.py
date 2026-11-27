"""Queries over the warehouse. Prices are piasters; outputs are in EGP floats where noted."""
import statistics


def _egp(v):
    return None if v is None else round(v / 100, 2)


def latest_run(conn):
    r = conn.execute('SELECT id FROM runs ORDER BY id DESC LIMIT 1').fetchone()
    return r['id'] if r else None


def previous_run(conn, run_id):
    r = conn.execute('SELECT id FROM runs WHERE id < ? ORDER BY id DESC LIMIT 1', (run_id,)).fetchone()
    return r['id'] if r else None


def summary(conn):
    rid = latest_run(conn)
    if rid is None:
        return {'runs': 0, 'products': 0, 'categories': 0, 'avg_price': None, 'out_of_stock': 0}
    row = conn.execute(
        """SELECT COUNT(*) n, AVG(p.price) a, SUM(CASE WHEN p.in_stock = 0 THEN 1 ELSE 0 END) oos,
                  COUNT(DISTINCT pr.category) c FROM prices p JOIN products pr ON pr.sku = p.sku WHERE p.run_id = ?""", (rid,)).fetchone()
    return {'runs': conn.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 'products': row['n'], 'categories': row['c'],
            'avg_price': _egp(row['a']), 'out_of_stock': row['oos'] or 0}


def category_stats(conn, run_id=None):
    rid = run_id or latest_run(conn)
    out = []
    for c in conn.execute('SELECT DISTINCT pr.category FROM prices p JOIN products pr ON pr.sku=p.sku WHERE p.run_id=? ORDER BY 1', (rid,)):
        prices = [r[0] for r in conn.execute(
            'SELECT p.price FROM prices p JOIN products pr ON pr.sku=p.sku WHERE p.run_id=? AND pr.category=? ORDER BY p.price', (rid, c[0]))]
        out.append({'category': c[0], 'count': len(prices), 'min': _egp(prices[0]), 'max': _egp(prices[-1]),
                    'avg': _egp(statistics.fmean(prices)), 'median': _egp(statistics.median(prices))})
    return out


def price_changes(conn, min_pct=0.0):
    """Compare the latest run with the one before it. Sorted by absolute change."""
    cur = latest_run(conn)
    prev = previous_run(conn, cur) if cur else None
    if prev is None:
        return []
    rows = conn.execute(
        """SELECT pr.sku, pr.name, pr.category, a.price old, b.price new FROM prices a
           JOIN prices b ON b.sku = a.sku AND b.run_id = ? JOIN products pr ON pr.sku = a.sku WHERE a.run_id = ?""", (cur, prev)).fetchall()
    out = []
    for r in rows:
        pct = (r['new'] - r['old']) / r['old'] * 100
        if abs(pct) >= min_pct and r['new'] != r['old']:
            out.append({'sku': r['sku'], 'name': r['name'], 'category': r['category'], 'old': _egp(r['old']), 'new': _egp(r['new']), 'pct': round(pct, 2)})
    return sorted(out, key=lambda x: -abs(x['pct']))


def new_and_removed(conn):
    cur = latest_run(conn)
    prev = previous_run(conn, cur) if cur else None
    if prev is None:
        return {'new': [], 'removed': []}
    q = 'SELECT sku FROM prices WHERE run_id = ?'
    a = {r[0] for r in conn.execute(q, (prev,))}
    b = {r[0] for r in conn.execute(q, (cur,))}
    return {'new': sorted(b - a), 'removed': sorted(a - b)}


def history(conn, sku):
    return [{'run': r['label'], 'price': _egp(r['price'])} for r in conn.execute(
        'SELECT r.label, p.price FROM prices p JOIN runs r ON r.id = p.run_id WHERE p.sku = ? ORDER BY r.id', (sku,))]


def volatility(conn, top=10):
    """Coefficient of variation of price across runs (needs 3+ observations)."""
    out = []
    for p in conn.execute('SELECT sku, name FROM products'):
        vals = [r[0] for r in conn.execute('SELECT price FROM prices WHERE sku = ?', (p['sku'],))]
        if len(vals) >= 3:
            m = statistics.fmean(vals)
            out.append({'sku': p['sku'], 'name': p['name'], 'cv': round(statistics.pstdev(vals) / m * 100, 2), 'avg': _egp(m)})
    return sorted(out, key=lambda x: -x['cv'])[:top]


def lowest_vs_average(conn, top=10):
    """Products whose latest price is furthest below their own historical average."""
    cur = latest_run(conn)
    out = []
    for p in conn.execute('SELECT pr.sku, pr.name, p.price FROM prices p JOIN products pr ON pr.sku=p.sku WHERE p.run_id = ?', (cur,)):
        vals = [r[0] for r in conn.execute('SELECT price FROM prices WHERE sku = ?', (p['sku'],))]
        if len(vals) >= 2:
            avg = statistics.fmean(vals)
            out.append({'sku': p['sku'], 'name': p['name'], 'now': _egp(p['price']), 'avg': _egp(avg), 'below_pct': round((avg - p['price']) / avg * 100, 2)})
    return sorted(out, key=lambda x: -x['below_pct'])[:top]


def outliers(conn, z=2.0):
    """Latest-run prices more than z standard deviations from their category mean."""
    cur = latest_run(conn)
    out = []
    for c in conn.execute('SELECT DISTINCT pr.category FROM prices p JOIN products pr ON pr.sku=p.sku WHERE p.run_id=?', (cur,)):
        rows = conn.execute('SELECT pr.sku, pr.name, p.price FROM prices p JOIN products pr ON pr.sku=p.sku WHERE p.run_id=? AND pr.category=?', (cur, c[0])).fetchall()
        vals = [r['price'] for r in rows]
        if len(vals) < 4:
            continue
        m, sd = statistics.fmean(vals), statistics.pstdev(vals)
        if sd == 0:
            continue
        for r in rows:
            zs = (r['price'] - m) / sd
            if abs(zs) >= z:
                out.append({'sku': r['sku'], 'name': r['name'], 'category': c[0], 'price': _egp(r['price']), 'z': round(zs, 2)})
    return sorted(out, key=lambda x: -abs(x['z']))


def category_trend(conn):
    """Average price per category per run, for the trend chart."""
    rows = conn.execute(
        """SELECT r.label, pr.category, AVG(p.price) a FROM prices p JOIN runs r ON r.id=p.run_id JOIN products pr ON pr.sku=p.sku
           GROUP BY r.id, pr.category ORDER BY r.id""").fetchall()
    series = {}
    for r in rows:
        series.setdefault(r['category'], []).append({'run': r['label'], 'avg': _egp(r['a'])})
    return series
