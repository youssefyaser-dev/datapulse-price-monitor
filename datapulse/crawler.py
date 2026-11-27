import time
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse

from . import clean, parse


class FetchError(RuntimeError):
    pass


class Crawler:
    def __init__(self, base_url, delay=0.0, retries=3, backoff=0.05, timeout=5, user_agent='datapulse/1.0'):
        self.base = base_url.rstrip('/')
        self.delay, self.retries, self.backoff, self.timeout = delay, retries, backoff, timeout
        self.ua = user_agent
        self.stats = {'requests': 0, 'retries': 0, 'errors': 0}
        self._disallow = None

    def _robots(self):
        if self._disallow is None:
            self._disallow = []
            try:
                txt = self._get('/robots.txt', check=False)
                for line in txt.splitlines():
                    if line.lower().startswith('disallow:'):
                        p = line.split(':', 1)[1].strip()
                        if p:
                            self._disallow.append(p)
            except FetchError:
                pass
        return self._disallow

    def allowed(self, path):
        return not any(urlparse(path).path.startswith(p) for p in self._robots())

    def _get(self, path, check=True):
        if check and not self.allowed(path):
            raise FetchError(f'blocked by robots.txt: {path}')
        url = urljoin(self.base + '/', path.lstrip('/'))
        last = None
        for attempt in range(self.retries + 1):
            self.stats['requests'] += 1
            try:
                req = urllib.request.Request(url, headers={'User-Agent': self.ua})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    body = r.read().decode('utf-8', 'replace')
                if self.delay:
                    time.sleep(self.delay)
                return body
            except urllib.error.HTTPError as e:
                last = e
                if e.code < 500:  # 4xx will not get better
                    break
            except (urllib.error.URLError, TimeoutError) as e:
                last = e
            if attempt < self.retries:
                self.stats['retries'] += 1
                time.sleep(self.backoff * (2 ** attempt))
        self.stats['errors'] += 1
        raise FetchError(f'{url}: {last}')

    def categories(self):
        html = self._get('/')
        links = parse._Collector()
        links.feed(html)
        return [h.rsplit('/', 1)[1] for k, h in links.links if k == 'link' and h.startswith('/category/')]

    def crawl_category(self, cat, max_pages=50):
        path, out, seen = f'/category/{cat}', [], set()
        while path and len(seen) < max_pages and path not in seen:
            seen.add(path)
            cards, nxt = parse.parse_listing(self._get(path))
            for c in cards:
                c['category'] = cat
            out.extend(cards)
            path = nxt
        return out

    def crawl_all(self):
        """Return (clean_records, rejects). Bad rows are kept as rejects with the reason."""
        good, bad = [], []
        for cat in self.categories():
            try:
                raw = self.crawl_category(cat)
            except FetchError as e:
                bad.append({'sku': None, 'reason': f'category {cat}: {e}'})
                continue
            for r in raw:
                try:
                    good.append({
                        'sku': r['sku'], 'name': clean.clean_name(r['name']), 'category': cat,
                        'price': clean.parse_price(r['price_raw']), 'in_stock': clean.parse_stock(r['stock_raw']),
                    })
                except (clean.CleanError, KeyError) as e:
                    bad.append({'sku': r.get('sku'), 'reason': str(e)})
        return clean.dedupe(good), bad


def enrich(crawler, records, limit=None):
    """Fetch product pages for rating and stock count. Failures leave the fields empty."""
    for r in records[:limit]:
        try:
            p = parse.parse_product(crawler._get(f"/product/{r['sku']}"))
            r['rating'] = float(p['rating']) if p.get('rating') else None
            r['stock_count'] = int(p['stock-count']) if p.get('stock-count', '').isdigit() else None
        except (FetchError, ValueError):
            r['rating'] = r['stock_count'] = None
    return records
