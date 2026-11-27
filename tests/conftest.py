import pytest

from datapulse import fixture
from datapulse.warehouse import connect


@pytest.fixture()
def shop():
    shop = fixture.Shop(day=0)
    srv = fixture.serve(shop)
    shop.url = f'http://127.0.0.1:{srv.server_address[1]}'
    yield shop
    srv.shutdown()


@pytest.fixture()
def conn():
    c = connect(':memory:')
    yield c
    c.close()


def rec(sku, price, cat='audio', name=None, stock=True):
    return {'sku': sku, 'name': name or f'Item {sku}', 'category': cat, 'price': price, 'in_stock': stock}
