import json
import urllib.request

import pytest
from openpyxl import load_workbook

from datapulse import cli, dashboard, pipeline, report
from datapulse.warehouse import connect


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / 'dp.db')
    conn, results = pipeline.demo(path, days=4, flaky=0)
    conn.close()
    return path


def test_demo_pipeline_loads_runs(db):
    conn = connect(db)
    assert conn.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 4
    assert conn.execute('SELECT COUNT(DISTINCT sku) FROM products').fetchone()[0] >= 55
    assert conn.execute('SELECT COUNT(*) FROM rejects').fetchone()[0] > 0


def test_excel_report_has_expected_sheets_and_charts(db, tmp_path):
    out = report.write_report(connect(db), str(tmp_path / 'r.xlsx'))
    wb = load_workbook(out)
    assert wb.sheetnames == ['Summary', 'Categories', 'Price changes', 'Trend', 'Best deals', 'Volatility', 'Outliers', 'Rejected rows']
    assert wb['Categories'].max_row == 6 and len(wb['Categories']._charts) == 1 and len(wb['Trend']._charts) == 1
    assert wb['Price changes'].max_row > 5 and wb['Summary']['A1'].value == 'Runs' and wb['Summary']['B1'].value == 4


def test_report_on_empty_warehouse(tmp_path):
    out = report.write_report(connect(':memory:'), str(tmp_path / 'e.xlsx'))
    assert load_workbook(out)['Summary']['B2'].value == 0


@pytest.fixture()
def server(db):
    srv = dashboard.serve(db, port=0, background=True)
    yield f'http://127.0.0.1:{srv.server_address[1]}'
    srv.shutdown()


def get(url):
    with urllib.request.urlopen(url) as r:
        return r.status, r.headers['Content-Type'], r.read()


def test_dashboard_page_and_api(server):
    st, ct, body = get(server + '/')
    assert st == 200 and 'text/html' in ct and b'DataPulse' in body
    for ep in ['summary', 'categories', 'changes', 'trend', 'deals', 'volatility', 'outliers']:
        st, ct, body = get(f'{server}/api/{ep}')
        assert st == 200 and 'json' in ct, ep
        json.loads(body)
    assert json.loads(get(server + '/api/summary')[2])['runs'] == 4


def test_products_api_search_filter_and_injection_safe(server):
    rows = json.loads(get(server + '/api/products?category=phones')[2])
    assert rows and {r['category'] for r in rows} == {'phones'}
    assert json.loads(get(server + "/api/products?q=%27%20OR%201%3D1%20--")[2]) == []
    assert all('Laptop' in r['name'] for r in json.loads(get(server + '/api/products?q=Laptop')[2]))


def test_history_api_and_404(server, db):
    sku = connect(db).execute('SELECT sku FROM products LIMIT 1').fetchone()[0]
    assert len(json.loads(get(f'{server}/api/history?sku={sku}')[2])) == 4
    with pytest.raises(urllib.error.HTTPError) as e:
        get(server + '/api/nope')
    assert e.value.code == 404


def test_cli_changes_and_report(db, tmp_path, capsys):
    assert cli.main(['changes', '--db', db, '--min-pct', '0', '--json']) == 0
    assert isinstance(json.loads(capsys.readouterr().out), list)
    out = str(tmp_path / 'x.xlsx')
    cli.main(['report', '--db', db, '--out', out])
    assert 'wrote' in capsys.readouterr().out
