import pytest
from conftest import rec

from datapulse import analytics
from datapulse.warehouse import load_run, runs


def test_load_run_inserts_products_and_prices(conn):
    rid = load_run(conn, 'd1', [rec('A', 1000), rec('B', 2000)], [{'sku': 'X', 'reason': 'bad'}], {'requests': 5})
    assert conn.execute('SELECT COUNT(*) FROM prices WHERE run_id=?', (rid,)).fetchone()[0] == 2
    assert runs(conn)[0]['products'] == 2 and runs(conn)[0]['rejects'] == 1 and runs(conn)[0]['requests'] == 5


def test_reloading_same_label_replaces_run(conn):
    load_run(conn, 'd1', [rec('A', 1000), rec('B', 2000)])
    load_run(conn, 'd1', [rec('A', 1500)])
    assert len(runs(conn)) == 1
    assert [r[0] for r in conn.execute('SELECT price FROM prices')] == [1500]


def test_price_must_be_positive(conn):
    with pytest.raises(Exception):
        load_run(conn, 'd1', [rec('A', 0)])
    assert runs(conn) == []  # failed load rolled back, no half-written run


def test_product_first_and_last_run(conn):
    load_run(conn, 'd1', [rec('A', 100)])
    load_run(conn, 'd2', [rec('A', 110), rec('B', 50)])
    a = conn.execute("SELECT first_run, last_run FROM products WHERE sku='A'").fetchone()
    b = conn.execute("SELECT first_run, last_run FROM products WHERE sku='B'").fetchone()
    assert (a[0], a[1]) == (1, 2) and (b[0], b[1]) == (2, 2)


def seeded(conn):
    load_run(conn, 'd1', [rec('A', 10000), rec('B', 20000), rec('C', 30000, 'home'), rec('D', 5000, 'home', stock=False)])
    load_run(conn, 'd2', [rec('A', 9000), rec('B', 20000), rec('C', 33000, 'home'), rec('E', 1000)])
    load_run(conn, 'd3', [rec('A', 8000), rec('B', 21000), rec('C', 30000, 'home'), rec('E', 1200)])
    return conn


def test_summary_and_category_stats(conn):
    seeded(conn)
    s = analytics.summary(conn)
    assert s['runs'] == 3 and s['products'] == 4 and s['categories'] == 2 and s['avg_price'] == 150.5
    cats = {c['category']: c for c in analytics.category_stats(conn)}
    assert cats['audio']['count'] == 3 and cats['audio']['min'] == 12.0 and cats['audio']['max'] == 210.0


def test_empty_warehouse(conn):
    assert analytics.summary(conn)['products'] == 0 and analytics.price_changes(conn) == []
    assert analytics.latest_run(conn) is None


def test_price_changes_sorted_by_size(conn):
    seeded(conn)
    ch = analytics.price_changes(conn)
    assert [c['sku'] for c in ch] == ['E', 'A', 'C', 'B']
    by = {c['sku']: c for c in ch}
    assert by['A']['pct'] == -11.11 and by['C']['pct'] == -9.09 and by['B']['pct'] == 5.0
    assert [c['sku'] for c in analytics.price_changes(conn, min_pct=10)] == ['E', 'A']


def test_new_and_removed(conn):
    seeded(conn)
    load_run(conn, 'd4', [rec('A', 8000), rec('Z', 100)])
    nr = analytics.new_and_removed(conn)
    assert nr['new'] == ['Z'] and nr['removed'] == ['B', 'C', 'E']


def test_history_and_volatility(conn):
    seeded(conn)
    assert [h['price'] for h in analytics.history(conn, 'A')] == [100.0, 90.0, 80.0]
    vol = analytics.volatility(conn)
    assert vol[0]['sku'] == 'A'
    assert {v['sku'] for v in vol} == {'A', 'B', 'C'}  # E and D have fewer than 3 observations


def test_lowest_vs_average(conn):
    seeded(conn)
    deals = analytics.lowest_vs_average(conn)
    assert deals[0]['sku'] == 'A' and deals[0]['below_pct'] > 0


def test_outliers_flag_extreme_prices(conn):
    load_run(conn, 'd1', [rec(f'S{i}', 1000 + i * 10) for i in range(8)] + [rec('BIG', 100000)])
    out = analytics.outliers(conn, z=2.0)
    assert [o['sku'] for o in out] == ['BIG'] and out[0]['z'] > 2


def test_category_trend(conn):
    seeded(conn)
    t = analytics.category_trend(conn)
    assert [p['run'] for p in t['audio']] == ['d1', 'd2', 'd3']
