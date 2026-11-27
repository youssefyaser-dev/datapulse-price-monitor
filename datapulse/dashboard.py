import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import analytics
from .warehouse import connect, runs


def api(conn, path, query):
    if path == '/api/summary':
        return {**analytics.summary(conn), 'runs_list': runs(conn)}
    if path == '/api/categories':
        return analytics.category_stats(conn)
    if path == '/api/changes':
        return analytics.price_changes(conn, float((query.get('min') or ['0'])[0]))
    if path == '/api/trend':
        return analytics.category_trend(conn)
    if path == '/api/deals':
        return analytics.lowest_vs_average(conn, 10)
    if path == '/api/volatility':
        return analytics.volatility(conn, 10)
    if path == '/api/outliers':
        return analytics.outliers(conn)
    if path == '/api/history':
        sku = (query.get('sku') or [''])[0]
        return analytics.history(conn, sku)
    if path == '/api/products':
        q = (query.get('q') or [''])[0]
        cat = (query.get('category') or [''])[0]
        rid = analytics.latest_run(conn)
        sql = ('SELECT pr.sku, pr.name, pr.category, p.price / 100.0 AS price, p.in_stock FROM prices p '
               'JOIN products pr ON pr.sku = p.sku WHERE p.run_id = ? AND (pr.name LIKE ? OR pr.sku LIKE ?)')
        args = [rid, f'%{q}%', f'%{q}%']
        if cat:
            sql += ' AND pr.category = ?'
            args.append(cat)
        return [dict(r) for r in conn.execute(sql + ' ORDER BY pr.category, pr.name LIMIT 200', args)]
    return None


def make_handler(db_path):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ('/', '/index.html'):
                body, ctype, code = PAGE.encode(), 'text/html; charset=utf-8', 200
            elif u.path.startswith('/api/'):
                conn = connect(db_path)  # one connection per request keeps threads independent
                try:
                    data = api(conn, u.path, parse_qs(u.query))
                finally:
                    conn.close()
                if data is None:
                    body, ctype, code = b'{"error":"not found"}', 'application/json', 404
                else:
                    body, ctype, code = json.dumps(data).encode(), 'application/json', 200
            else:
                body, ctype, code = b'not found', 'text/plain', 404
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)
    return H


def serve(db_path, host='127.0.0.1', port=8080, background=False):
    srv = ThreadingHTTPServer((host, port), make_handler(db_path))
    if background:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DataPulse</title><style>
:root{--ink:#14213d;--mut:#667085;--bg:#f4f6fb;--card:#fff;--acc:#2563eb;--up:#dc2626;--down:#16a34a}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--ink)}
header{background:var(--ink);color:#fff;padding:14px 28px;display:flex;justify-content:space-between;align-items:center}
header b{font-size:18px}main{max-width:1180px;margin:20px auto;padding:0 20px;display:grid;gap:16px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.card{background:var(--card);border-radius:10px;padding:16px;box-shadow:0 1px 3px #0001}
.kpi small{color:var(--mut)}.kpi div{font-size:26px;font-weight:700}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
h2{margin:0 0 10px;font-size:15px}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #eef0f4}
th{color:var(--mut);font-weight:600;font-size:12px}td.n,th.n{text-align:right}.up{color:var(--up)}.down{color:var(--down)}
input,select{padding:6px 8px;border:1px solid #d0d5dd;border-radius:6px}svg text{font-size:11px;fill:#475467}
tr.click{cursor:pointer}tr.click:hover{background:#f0f5ff}.legend span{margin-right:12px;font-size:12px}.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px}
@media(max-width:800px){.kpis,.two{grid-template-columns:1fr 1fr}}
</style></head><body><header><b>DataPulse</b><span id="runinfo"></span></header><main>
<div class="kpis" id="kpis"></div>
<div class="two"><div class="card"><h2>Average price by category (EGP)</h2><div id="bars"></div></div>
<div class="card"><h2>Average price per run</h2><div id="trend"></div><div class="legend" id="legend"></div></div></div>
<div class="two"><div class="card"><h2>Biggest price changes vs previous run</h2><table id="changes"></table></div>
<div class="card"><h2>Best deals vs own average</h2><table id="deals"></table></div></div>
<div class="card"><h2>Price history <span id="histname" style="color:#667085;font-weight:400"></span></h2><div id="hist">Select a product below.</div></div>
<div class="card"><h2>Products</h2><p><input id="q" placeholder="Search name or SKU"> <select id="cat"><option value="">All categories</option></select></p><table id="prods"></table></div>
</main><script>
const $=id=>document.getElementById(id),J=u=>fetch(u).then(r=>r.json()),E=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const COL=['#2563eb','#16a34a','#f59e0b','#dc2626','#7c3aed','#0891b2'],fmt=n=>n==null?'-':Number(n).toLocaleString('en',{maximumFractionDigits:0});
function line(el,series,w=520,h=220){const names=Object.keys(series);if(!names.length)return;const all=names.flatMap(n=>series[n].map(p=>p.avg));
 const mx=Math.max(...all),mn=Math.min(...all),L=Math.max(...names.map(n=>series[n].length));let s=`<svg viewBox="0 0 ${w} ${h}" width="100%">`;
 names.forEach((n,i)=>{const pts=series[n].map((p,j)=>[40+j*(w-60)/Math.max(1,L-1),h-25-(p.avg-mn)/((mx-mn)||1)*(h-50)]);
 s+=`<polyline fill="none" stroke="${COL[i%6]}" stroke-width="2" points="${pts.map(p=>p.join(',')).join(' ')}"/>`;pts.forEach(p=>s+=`<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="${COL[i%6]}"/>`)});
 s+=`<text x="2" y="14">${fmt(mx)}</text><text x="2" y="${h-22}">${fmt(mn)}</text></svg>`;$(el).innerHTML=s}
function bars(rows){const mx=Math.max(...rows.map(r=>r.avg));$('bars').innerHTML=rows.map((r,i)=>`<div style="display:flex;align-items:center;margin:6px 0"><span style="width:110px">${E(r.category)}</span><div style="flex:1;background:#eef2ff;border-radius:4px"><div style="width:${r.avg/mx*100}%;background:${COL[i%6]};height:18px;border-radius:4px"></div></div><b style="width:80px;text-align:right">${fmt(r.avg)}</b></div>`).join('')}
async function hist(sku,name){const h=await J('/api/history?sku='+encodeURIComponent(sku));$('histname').textContent=name+' ('+sku+')';line('hist',{[sku]:h.map(p=>({run:p.run,avg:p.price}))},900,200)}
async function prods(){const d=await J('/api/products?q='+encodeURIComponent($('q').value)+'&category='+$('cat').value);
 $('prods').innerHTML='<tr><th>SKU</th><th>Name</th><th>Category</th><th class=n>Price</th><th>Stock</th></tr>'+d.map(p=>`<tr class=click data-s="${E(p.sku)}" data-n="${E(p.name)}"><td>${E(p.sku)}</td><td>${E(p.name)}</td><td>${E(p.category)}</td><td class=n>${fmt(p.price)}</td><td>${p.in_stock==null?'?':p.in_stock?'Yes':'No'}</td></tr>`).join('');
 document.querySelectorAll('#prods tr.click').forEach(r=>r.onclick=()=>hist(r.dataset.s,r.dataset.n))}
(async()=>{const s=await J('/api/summary');
 $('kpis').innerHTML=[['Runs',s.runs],['Products',s.products],['Average price (EGP)',fmt(s.avg_price)],['Out of stock',s.out_of_stock]].map(k=>`<div class="card kpi"><small>${k[0]}</small><div>${k[1]}</div></div>`).join('');
 const last=s.runs_list.at(-1);$('runinfo').textContent=last?'Latest run: '+last.label:'';
 const c=await J('/api/categories');bars(c);c.forEach(x=>$('cat').add(new Option(x.category,x.category)));
 const t=await J('/api/trend');line('trend',t);$('legend').innerHTML=Object.keys(t).map((n,i)=>`<span><i style="background:${COL[i%6]}"></i>${E(n)}</span>`).join('');
 const ch=await J('/api/changes');$('changes').innerHTML='<tr><th>Product</th><th class=n>Old</th><th class=n>New</th><th class=n>%</th></tr>'+ch.slice(0,8).map(x=>`<tr><td>${E(x.name)}</td><td class=n>${fmt(x.old)}</td><td class=n>${fmt(x.new)}</td><td class="n ${x.pct>0?'up':'down'}">${x.pct>0?'+':''}${x.pct}</td></tr>`).join('');
 const d=await J('/api/deals');$('deals').innerHTML='<tr><th>Product</th><th class=n>Now</th><th class=n>Average</th><th class=n>Below</th></tr>'+d.slice(0,8).map(x=>`<tr><td>${E(x.name)}</td><td class=n>${fmt(x.now)}</td><td class=n>${fmt(x.avg)}</td><td class="n down">${x.below_pct}%</td></tr>`).join('');
 $('q').oninput=prods;$('cat').onchange=prods;prods()})();
</script></body></html>"""
