"""Normalisation of scraped values."""
import re

_AR = str.maketrans('٠١٢٣٤٥٦٧٨٩٫٬', '0123456789.,')


class CleanError(ValueError):
    pass


def parse_price(raw):
    """Return the price in piasters (int). Accepts '1,299.00 EGP', 'EGP 1,299', '١٢٬٣٠٠ ج.م', '1299'."""
    if raw is None:
        raise CleanError('missing price')
    s = str(raw).translate(_AR)
    m = re.search(r'\d[\d,]*(?:\.\d+)?', s)
    if not m:
        raise CleanError(f'no number in {raw!r}')
    num = m.group(0).replace(',', '')
    value = round(float(num) * 100)
    if value <= 0:
        raise CleanError('non-positive price')
    return value


def parse_stock(raw):
    """True / False / None (unknown)."""
    if not raw:
        return None
    low = raw.strip().lower()
    if 'out' in low or 'نفد' in low:
        return False
    if 'in stock' in low or 'متوفر' in low:
        return True
    return None


def clean_name(name):
    return re.sub(r'\s+', ' ', (name or '')).strip()


def dedupe(records, key='sku'):
    """Keep the last record seen for each key, preserving first-seen order."""
    out = {}
    for r in records:
        out[r[key]] = r
    return list(out.values())
