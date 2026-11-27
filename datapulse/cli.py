import argparse
import json
import sys
import time

from . import analytics, fixture, pipeline, report
from .crawler import Crawler
from .warehouse import connect


def main(argv=None):
    ap = argparse.ArgumentParser(prog='datapulse', description='Crawl, store, analyse and report on product prices.')
    sub = ap.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('fixture', help='serve the local demo shop')
    s.add_argument('--port', type=int, default=8099)
    s.add_argument('--day', type=int, default=0)
    s.add_argument('--flaky', type=int, default=0)

    s = sub.add_parser('crawl', help='crawl a shop into the warehouse')
    s.add_argument('--url', default='http://127.0.0.1:8099')
    s.add_argument('--db', default='datapulse.db')
    s.add_argument('--label', default=time.strftime('%Y-%m-%d'))
    s.add_argument('--delay', type=float, default=0.0)
    s.add_argument('--no-enrich', action='store_true')

    s = sub.add_parser('demo', help='simulate several daily crawls on the local shop')
    s.add_argument('--db', default='datapulse.db')
    s.add_argument('--days', type=int, default=6)

    s = sub.add_parser('report', help='write the Excel report')
    s.add_argument('--db', default='datapulse.db')
    s.add_argument('--out', default='datapulse-report.xlsx')

    s = sub.add_parser('changes', help='print price changes vs the previous run')
    s.add_argument('--db', default='datapulse.db')
    s.add_argument('--min-pct', type=float, default=5.0)
    s.add_argument('--json', action='store_true')

    s = sub.add_parser('serve', help='start the dashboard')
    s.add_argument('--db', default='datapulse.db')
    s.add_argument('--port', type=int, default=8080)

    a = ap.parse_args(argv)
    if a.cmd == 'fixture':
        srv = fixture.serve(fixture.Shop(day=a.day, flaky=a.flaky), port=a.port)
        print(f'Demo shop on http://127.0.0.1:{srv.server_address[1]} (Ctrl+C to stop)')
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0
    if a.cmd == 'crawl':
        conn = connect(a.db)
        print(json.dumps(pipeline.crawl_into(conn, a.url, a.label, a.delay, not a.no_enrich)))
    elif a.cmd == 'demo':
        _, res = pipeline.demo(a.db, a.days)
        for r in res:
            print(r)
    elif a.cmd == 'report':
        print('wrote', report.write_report(connect(a.db), a.out))
    elif a.cmd == 'changes':
        ch = [c for c in analytics.price_changes(connect(a.db), a.min_pct)]
        if a.json:
            print(json.dumps(ch, indent=2))
        else:
            for c in ch:
                print(f"{c['sku']:8} {c['name']:24} {c['old']:>10,.0f} -> {c['new']:>10,.0f}  {c['pct']:+.1f}%")
    elif a.cmd == 'serve':
        srv = __import__('datapulse.dashboard', fromlist=['serve']).serve(a.db, port=a.port)
        print(f'Dashboard on http://127.0.0.1:{a.port}')
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
