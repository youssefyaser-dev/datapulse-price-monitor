"""A small local shop used as the crawl target.

It serves paginated category pages and product pages with deliberately uneven markup
(price formats, Arabic digits, missing fields, a flaky mode) so the pipeline has real
cleaning and retry work to do. Prices drift deterministically with the simulated day.
"""
import hashlib
import html
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

CATEGORIES = {
    'phones': ('Phones', 'هواتف'),
    'laptops': ('Laptops', 'لابتوبات'),
    'audio': ('Audio', 'صوتيات'),
    'home': ('Home Appliances', 'أجهزة منزلية'),
    'gaming': ('Gaming', 'ألعاب'),
}
BRANDS = ['Nova', 'Orbit', 'Zenith', 'Atlas', 'Pulse', 'Vertex', 'Lumen', 'Kairo']
KINDS = {
    'phones': ['Phone X1', 'Phone S2', 'Phone Lite', 'Phone Max'],
    'laptops': ['Laptop 14', 'Laptop Pro 15', 'Laptop Air', 'Laptop Studio'],
    'audio': ['Earbuds', 'Headphones', 'Speaker Mini', 'Soundbar'],
    'home': ['Air Fryer', 'Blender', 'Vacuum', 'Kettle'],
    'gaming': ['Controller', 'Headset', 'Keyboard', 'Mouse'],
}
BASE = {'phones': 14000, 'laptops': 26000, 'audio': 2200, 'home': 3200, 'gaming': 1600}
PAGE_SIZE = 8
ARABIC_DIGITS = str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')


def _h(*parts):
    return int(hashlib.sha256('|'.join(map(str, parts)).encode()).hexdigest()[:8], 16)


def build_catalog(n_per_category=12):
    items = []
    for cat in CATEGORIES:
        for i in range(n_per_category):
            brand = BRANDS[_h(cat, i, 'b') % len(BRANDS)]
            kind = KINDS[cat][i % len(KINDS[cat])]
            base = round(BASE[cat] * (0.55 + (_h(cat, i, 'p') % 100) / 100), -1)
            items.append({
                'sku': f'{cat[:2].upper()}-{1000 + i}', 'name': f'{brand} {kind}', 'category': cat,
                'base': base, 'rating': round(3 + (_h(cat, i, 'r') % 20) / 10, 1),
                'stock': (_h(cat, i, 's') % 40),
            })
    return items


def price_on_day(item, day):
    """Deterministic drift: -12%..+10% around base, with occasional sale days."""
    swing = ((_h(item['sku'], day, 'd') % 23) - 12) / 100
    if _h(item['sku'], day, 'sale') % 9 == 0:
        swing -= 0.08
    return round(item['base'] * (1 + swing), 0)


def fmt_price(item, price):
    """Mixed formats on purpose."""
    if _h(item['sku'], 'bad') % 23 == 0:
        return 'Call for price'
    k = _h(item['sku'], 'fmt') % 4
    if k == 0:
        return f'{price:,.2f} EGP'
    if k == 1:
        return f'EGP {price:,.0f}'
    if k == 2:
        return (f'{price:,.0f}').translate(ARABIC_DIGITS).replace(',', '٬') + ' ج.م'
    return f'{price:.0f}'


class Shop:
    def __init__(self, day=0, flaky=0, n_per_category=12):
        self.day = day
        self.flaky = flaky  # every Nth request returns 503
        self.items = build_catalog(n_per_category)
        self.requests = 0
        self.lock = threading.Lock()

    def by_category(self, cat):
        return [i for i in self.items if i['category'] == cat]

    def card(self, it):
        price = price_on_day(it, self.day)
        stock = '<span class="stock out">Out of stock</span>' if it['stock'] == 0 else '<span class="stock">In stock</span>'
        if _h(it['sku'], 'nostock') % 11 == 0:
            stock = ''  # missing availability on some cards
        return (f'<div class="card" data-sku="{it["sku"]}"><a class="title" href="/product/{it["sku"]}">{html.escape(it["name"])}</a>'
                f'<span class="price">{fmt_price(it, price)}</span>{stock}</div>')

    def category_page(self, cat, page):
        items = self.by_category(cat)
        pages = max(1, -(-len(items) // PAGE_SIZE))
        chunk = items[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
        name = CATEGORIES[cat][0]
        nxt = f'<a rel="next" href="/category/{cat}?page={page + 1}">Next</a>' if page < pages else ''
        return (f'<html><head><title>{name}</title></head><body><h1>{name}</h1><div class="grid">'
                + ''.join(self.card(i) for i in chunk) + f'</div><nav>{nxt}</nav></body></html>')

    def product_page(self, sku):
        it = next((i for i in self.items if i['sku'] == sku), None)
        if not it:
            return None
        price = price_on_day(it, self.day)
        return (f'<html><body><h1 class="name">{html.escape(it["name"])}</h1>'
                f'<span class="sku">{it["sku"]}</span><span class="cat">{CATEGORIES[it["category"]][0]}</span>'
                f'<span class="price">{fmt_price(it, price)}</span><span class="rating">{it["rating"]}</span>'
                f'<span class="stock-count">{it["stock"]}</span></body></html>')

    def index_page(self):
        links = ''.join(f'<li><a href="/category/{c}">{n[0]}</a></li>' for c, n in CATEGORIES.items())
        return f'<html><body><h1>Demo Shop</h1><ul class="cats">{links}</ul></body></html>'


def make_handler(shop):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype='text/html; charset=utf-8'):
            data = body.encode()
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            with shop.lock:
                shop.requests += 1
                n = shop.requests
            if shop.flaky and n % shop.flaky == 0:
                return self._send(503, 'busy')
            u = urlparse(self.path)
            if u.path == '/':
                return self._send(200, shop.index_page())
            if u.path.startswith('/category/'):
                cat = u.path.split('/')[2]
                if cat not in CATEGORIES:
                    return self._send(404, 'not found')
                page = int((parse_qs(u.query).get('page') or ['1'])[0])
                return self._send(200, shop.category_page(cat, page))
            if u.path.startswith('/product/'):
                body = shop.product_page(u.path.split('/')[2])
                return self._send(200, body) if body else self._send(404, 'not found')
            if u.path == '/robots.txt':
                return self._send(200, 'User-agent: *\nDisallow: /admin\n', 'text/plain')
            self._send(404, 'not found')
    return Handler


def serve(shop, host='127.0.0.1', port=0):
    srv = ThreadingHTTPServer((host, port), make_handler(shop))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv
