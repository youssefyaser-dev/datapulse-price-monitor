import pytest

from datapulse import clean, fixture, parse


@pytest.mark.parametrize('raw,expected', [
    ('1,299.00 EGP', 129900), ('EGP 1,299', 129900), ('1299', 129900), ('١٢٬٣٠٠ ج.م', 1230000),
    ('٩٩٫٥٠', 9950), ('  250 ', 25000)])
def test_parse_price_formats(raw, expected):
    assert clean.parse_price(raw) == expected


@pytest.mark.parametrize('raw', ['Call for price', '', None, '0', 'EGP 0.00'])
def test_parse_price_rejects(raw):
    with pytest.raises(clean.CleanError):
        clean.parse_price(raw)


def test_parse_stock():
    assert clean.parse_stock('In stock') is True
    assert clean.parse_stock('Out of stock') is False
    assert clean.parse_stock('متوفر') is True
    assert clean.parse_stock(None) is None and clean.parse_stock('maybe') is None


def test_clean_name_and_dedupe():
    assert clean.clean_name('  Nova \n  Phone  X1 ') == 'Nova Phone X1'
    out = clean.dedupe([{'sku': 'a', 'v': 1}, {'sku': 'b', 'v': 2}, {'sku': 'a', 'v': 3}])
    assert out == [{'sku': 'a', 'v': 3}, {'sku': 'b', 'v': 2}]


def test_parse_listing_cards_and_pagination():
    shop = fixture.Shop()
    cards, nxt = parse.parse_listing(shop.category_page('phones', 1))
    assert len(cards) == fixture.PAGE_SIZE and nxt == '/category/phones?page=2'
    assert all(c['sku'] and c['name'] and c['price_raw'] for c in cards[:3] if 'Call' not in c['price_raw'])
    cards2, nxt2 = parse.parse_listing(shop.category_page('phones', 2))
    assert len(cards2) == 12 - fixture.PAGE_SIZE and nxt2 is None


def test_parse_handles_escaped_names_and_missing_stock():
    html = '<div class="card" data-sku="X1"><a class="title" href="/product/X1">A &amp; B</a><span class="price">10</span></div>'
    cards, _ = parse.parse_listing(html)
    assert cards[0]['name'] == 'A & B' and cards[0]['stock_raw'] is None


def test_parse_product_page():
    shop = fixture.Shop()
    p = parse.parse_product(shop.product_page(shop.items[0]['sku']))
    assert p['sku'] == shop.items[0]['sku'] and float(p['rating']) > 0 and p['stock-count'].isdigit()


def test_fixture_is_deterministic_and_drifts():
    a, b = fixture.build_catalog(), fixture.build_catalog()
    assert a == b and len(a) == 60
    it = a[0]
    assert fixture.price_on_day(it, 3) == fixture.price_on_day(it, 3)
    assert len({fixture.price_on_day(it, d) for d in range(10)}) > 1
