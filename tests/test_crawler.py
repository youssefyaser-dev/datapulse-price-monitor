import pytest

from datapulse import fixture
from datapulse.crawler import Crawler, FetchError, enrich


def test_discovers_categories(shop):
    assert Crawler(shop.url).categories() == list(fixture.CATEGORIES)


def test_crawl_category_follows_pagination(shop):
    rows = Crawler(shop.url).crawl_category('audio')
    assert len(rows) == 12 and {r['category'] for r in rows} == {'audio'}


def test_crawl_all_cleans_and_collects_rejects(shop):
    good, bad = Crawler(shop.url).crawl_all()
    assert len(good) + len(bad) == 60
    assert bad and all('Call for price' not in g['name'] for g in good)
    assert all(g['price'] > 0 for g in good) and all(b['sku'] for b in bad)


def test_retries_on_503_then_succeeds():
    shop = fixture.Shop(flaky=3)
    srv = fixture.serve(shop)
    try:
        c = Crawler(f'http://127.0.0.1:{srv.server_address[1]}', backoff=0.001)
        good, bad = c.crawl_all()
        assert c.stats['retries'] > 0 and c.stats['errors'] == 0 and len(good) + len(bad) == 60
    finally:
        srv.shutdown()


def test_404_is_not_retried(shop):
    c = Crawler(shop.url, backoff=0.001)
    with pytest.raises(FetchError):
        c._get('/nope')
    assert c.stats['retries'] == 0


def test_gives_up_after_retries():
    shop = fixture.Shop(flaky=1)  # every request fails
    srv = fixture.serve(shop)
    try:
        c = Crawler(f'http://127.0.0.1:{srv.server_address[1]}', retries=2, backoff=0.001)
        with pytest.raises(FetchError):
            c._get('/', check=False)
        assert c.stats['retries'] == 2 and c.stats['errors'] == 1
    finally:
        srv.shutdown()


def test_robots_disallow_is_respected(shop):
    c = Crawler(shop.url)
    assert c.allowed('/category/phones') and not c.allowed('/admin/users')
    with pytest.raises(FetchError):
        c._get('/admin/users')


def test_enrich_adds_rating_and_stock(shop):
    c = Crawler(shop.url)
    good, _ = c.crawl_all()
    enrich(c, good, limit=3)
    assert all(g['rating'] and g['stock_count'] is not None for g in good[:3]) and 'rating' not in good[5]
