from . import fixture
from .crawler import Crawler, enrich
from .warehouse import connect, load_run


def crawl_into(conn, base_url, label, delay=0.0, do_enrich=True):
    c = Crawler(base_url, delay=delay)
    records, rejects = c.crawl_all()
    if do_enrich:
        enrich(c, records)
    run_id = load_run(conn, label, records, rejects, c.stats)
    return {'run_id': run_id, 'products': len(records), 'rejects': len(rejects), **c.stats}


def demo(db_path, days=6, flaky=17):
    """Simulate `days` daily crawls against the local fixture shop."""
    conn = connect(db_path)
    shop = fixture.Shop(day=0, flaky=flaky)
    srv = fixture.serve(shop)
    base = f'http://127.0.0.1:{srv.server_address[1]}'
    results = []
    try:
        for d in range(days):
            shop.day = d
            results.append(crawl_into(conn, base, f'day-{d + 1:02d}'))
    finally:
        srv.shutdown()
    return conn, results
