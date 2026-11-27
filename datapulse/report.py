from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import analytics

HEAD = PatternFill('solid', fgColor='1F3A5F')


def _sheet(wb, title, headers, rows, widths=None):
    ws = wb.create_sheet(title)
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = HEAD
        c.alignment = Alignment(horizontal='center')
    for r in rows:
        ws.append(r)
    for i, h in enumerate(headers, 1):
        longest = max([len(str(h))] + [len(str(r[i - 1])) for r in rows]) if rows else len(h)
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(i, min(40, longest + 3))
    ws.freeze_panes = 'A2'
    return ws


def build_workbook(conn):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Summary'
    s = analytics.summary(conn)
    for k, v in [('Runs', s['runs']), ('Products (latest run)', s['products']), ('Categories', s['categories']),
                 ('Average price (EGP)', s['avg_price']), ('Out of stock', s['out_of_stock'])]:
        ws.append([k, v])
    ws.column_dimensions['A'].width = 26
    for c in ws['A']:
        c.font = Font(bold=True)

    cats = analytics.category_stats(conn)
    cs = _sheet(wb, 'Categories', ['Category', 'Products', 'Min', 'Median', 'Average', 'Max'],
                [[c['category'], c['count'], c['min'], c['median'], c['avg'], c['max']] for c in cats])
    if cats:
        ch = BarChart()
        ch.title = 'Average price by category (EGP)'
        ch.add_data(Reference(cs, min_col=5, min_row=1, max_row=len(cats) + 1), titles_from_data=True)
        ch.set_categories(Reference(cs, min_col=1, min_row=2, max_row=len(cats) + 1))
        ch.height, ch.width = 8, 16
        cs.add_chart(ch, 'H2')

    changes = analytics.price_changes(conn)
    _sheet(wb, 'Price changes', ['SKU', 'Name', 'Category', 'Old', 'New', 'Change %'],
           [[c['sku'], c['name'], c['category'], c['old'], c['new'], c['pct']] for c in changes])

    trend = analytics.category_trend(conn)
    if trend:
        labels = [p['run'] for p in next(iter(trend.values()))]
        tw = _sheet(wb, 'Trend', ['Run'] + list(trend), [[lab] + [trend[c][i]['avg'] if i < len(trend[c]) else None for c in trend] for i, lab in enumerate(labels)])
        if len(labels) > 1:
            lc = LineChart()
            lc.title = 'Average price per run (EGP)'
            lc.add_data(Reference(tw, min_col=2, max_col=1 + len(trend), min_row=1, max_row=len(labels) + 1), titles_from_data=True)
            lc.set_categories(Reference(tw, min_col=1, min_row=2, max_row=len(labels) + 1))
            lc.height, lc.width = 8, 18
            tw.add_chart(lc, 'H2')

    _sheet(wb, 'Best deals', ['SKU', 'Name', 'Now', 'Average', 'Below avg %'],
           [[d['sku'], d['name'], d['now'], d['avg'], d['below_pct']] for d in analytics.lowest_vs_average(conn, 20)])
    _sheet(wb, 'Volatility', ['SKU', 'Name', 'CV %', 'Average'],
           [[v['sku'], v['name'], v['cv'], v['avg']] for v in analytics.volatility(conn, 20)])
    _sheet(wb, 'Outliers', ['SKU', 'Name', 'Category', 'Price', 'Z-score'],
           [[o['sku'], o['name'], o['category'], o['price'], o['z']] for o in analytics.outliers(conn)])
    rej = conn.execute('SELECT r.label, x.sku, x.reason FROM rejects x JOIN runs r ON r.id = x.run_id ORDER BY r.id').fetchall()
    _sheet(wb, 'Rejected rows', ['Run', 'SKU', 'Reason'], [[r['label'], r['sku'], r['reason']] for r in rej])
    return wb


def write_report(conn, path):
    build_workbook(conn).save(path)
    return path
