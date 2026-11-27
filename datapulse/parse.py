"""HTML parsing with the standard library only."""
from html.parser import HTMLParser


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cards, self.links, self.fields = [], [], {}
        self._card = None
        self._cls = None
        self._depth = 0
        self._cur = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get('class') or '').split()
        if tag == 'div' and 'card' in cls:
            self._card = {'sku': a.get('data-sku'), 'name': '', 'url': None, 'price_raw': '', 'stock_raw': None}
            self._depth = 1
            return
        if self._card is not None and tag == 'div':
            self._depth += 1
        if tag == 'a' and a.get('rel') == 'next':
            self.links.append(('next', a.get('href')))
        if tag == 'a' and self._card is not None and 'title' in cls:
            self._card['url'] = a.get('href')
            self._cur = ('card', 'name')
        elif tag == 'a' and not self._card and 'href' in a:
            self.links.append(('link', a['href']))
        if tag == 'span' and 'price' in cls:
            self._cur = ('card', 'price_raw') if self._card is not None else ('page', 'price_raw')
        elif tag == 'span' and 'stock' in cls and self._card is not None:
            self._card['stock_raw'] = ''
            self._cur = ('card', 'stock_raw')
        elif tag == 'span' and cls and cls[0] in ('sku', 'cat', 'rating', 'stock-count') and self._card is None:
            self._cur = ('page', cls[0])
        elif tag == 'h1' and 'name' in cls:
            self._cur = ('page', 'name')

    def handle_endtag(self, tag):
        if tag in ('a', 'span', 'h1'):
            self._cur = None
        if tag == 'div' and self._card is not None:
            self._depth -= 1
            if self._depth == 0:
                self.cards.append(self._card)
                self._card = None

    def handle_data(self, data):
        if not self._cur:
            return
        scope, key = self._cur
        if scope == 'card' and self._card is not None:
            self._card[key] = (self._card.get(key) or '') + data
        elif scope == 'page':
            self.fields[key] = self.fields.get(key, '') + data


def parse_listing(html_text):
    c = _Collector()
    c.feed(html_text)
    nxt = next((h for k, h in c.links if k == 'next'), None)
    cards = [{**x, 'name': x['name'].strip(), 'price_raw': x['price_raw'].strip(),
              'stock_raw': (x['stock_raw'] or '').strip() or None} for x in c.cards]
    return cards, nxt


def parse_product(html_text):
    c = _Collector()
    c.feed(html_text)
    return {k: v.strip() for k, v in c.fields.items()}
