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


PAGE = r"""<!doctype html><html lang="en" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DataPulse</title><link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet"><style>
:root{--ink:#1a1710;--mut:#7a7360;--bg:#f7f4ec;--card:#fffdf7;--line:#ebe5d3;--acc:#e0a100;--acc2:#ff7a1a;--up:#d92d3a;--down:#0e9f6e;--row:#f6efd8;--sh:0 14px 30px -20px rgba(90,70,0,.45)}
:root[data-theme=dark]{--ink:#f5f0e1;--mut:#a39b82;--bg:#12110d;--card:#1b1913;--line:#2b2820;--acc:#ffc233;--acc2:#ff8a3d;--up:#ff6b6b;--down:#3ddc97;--row:#26231a;--sh:0 14px 30px -20px #000}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 'IBM Plex Sans',system-ui,sans-serif;background:var(--bg);color:var(--ink);background-image:radial-gradient(45% 30% at 100% 0,color-mix(in srgb,var(--acc) 18%,transparent),transparent);background-attachment:fixed}
header{padding:18px 32px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);backdrop-filter:blur(8px);position:sticky;top:0;z-index:3;background:color-mix(in srgb,var(--bg) 85%,transparent)}
.brand{display:flex;align-items:center;gap:12px;font-weight:700;font-size:20px;letter-spacing:-.02em}.brand i{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;background:linear-gradient(135deg,var(--acc),var(--acc2));color:#201400;box-shadow:0 8px 18px -6px var(--acc)}
.hr{display:flex;align-items:center;gap:14px;font:12px 'IBM Plex Mono',monospace;color:var(--mut)}.hr button{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:6px 12px;font:inherit;cursor:pointer}.live:before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--down);margin-right:8px;box-shadow:0 0 8px var(--down)}
main{max-width:1200px;margin:24px auto;padding:0 22px 50px;display:grid;gap:18px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px 20px;box-shadow:var(--sh)}
.kpi small{color:var(--mut);text-transform:uppercase;letter-spacing:.1em;font-size:11px;font-weight:600}.kpi div{font:600 30px 'IBM Plex Mono',monospace;letter-spacing:-.03em;margin-top:4px}.kpi:first-child div{background:linear-gradient(90deg,var(--acc),var(--acc2));-webkit-background-clip:text;background-clip:text;color:transparent}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}h2{margin:0 0 14px;font-size:13px;text-transform:uppercase;letter-spacing:.1em;color:var(--mut);font-weight:600}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line)}tr:last-child td{border:0}
th{color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.08em}td.n,th.n{text-align:right;font-family:'IBM Plex Mono',monospace;font-size:13px}.up{color:var(--up)}.down{color:var(--down)}
input,select{padding:9px 12px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--ink);font:inherit}input:focus,select:focus{outline:2px solid var(--acc);border-color:transparent}svg text{font:11px 'IBM Plex Mono',monospace;fill:var(--mut)}
tr.click{cursor:pointer}tr.click:hover td{background:var(--row)}.legend{margin-top:8px}.legend span{margin-right:14px;font-size:12px;color:var(--mut)}.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px}
.brow{display:flex;align-items:center;gap:12px;margin:10px 0}.brow span{width:120px;color:var(--mut)}.brow .t{flex:1;background:var(--line);border-radius:8px;height:16px;overflow:hidden}.brow .t div{height:100%;border-radius:8px}.brow b{width:70px;text-align:right;font-family:'IBM Plex Mono',monospace;font-weight:500}
@media(max-width:800px){.kpis,.two{grid-template-columns:1fr 1fr}.brow span{width:80px}}@media(max-width:520px){.kpis,.two{grid-template-columns:1fr}}
</style></head><body><header><div class="brand"><i>&#9650;</i>DataPulse</div><div class="hr"><span class="live" id="runinfo"></span><button id="th" type="button">Light / dark</button></div></header><main>
<div class="kpis" id="kpis"></div>
<div class="two"><div class="card"><h2>Average price by category (EGP)</h2><div id="bars"></div></div>
<div class="card"><h2>Average price per run</h2><div id="trend"></div><div class="legend" id="legend"></div></div></div>
<div class="two"><div class="card"><h2>Biggest price changes vs previous run</h2><table id="changes"></table></div>
<div class="card"><h2>Best deals vs own average</h2><table id="deals"></table></div></div>
<div class="card"><h2>Price history <span id="histname" style="color:#667085;font-weight:400"></span></h2><div id="hist">Select a product below.</div></div>
<div class="card"><h2>Products</h2><p><input id="q" placeholder="Search name or SKU"> <select id="cat"><option value="">All categories</option></select></p><table id="prods"></table></div>
</main><script>
const $=id=>document.getElementById(id),J=u=>fetch(u).then(r=>r.json()),E=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const COL=['#ffb000','#ff6b3d','#22c1a4','#6c8cff','#c264ff','#ff5c8a'],fmt=n=>n==null?'-':Number(n).toLocaleString('en',{maximumFractionDigits:0});
function line(el,series,w=520,h=220){const names=Object.keys(series);if(!names.length)return;const all=names.flatMap(n=>series[n].map(p=>p.avg));
 const mx=Math.max(...all),mn=Math.min(...all),L=Math.max(...names.map(n=>series[n].length));let s=`<svg viewBox="0 0 ${w} ${h}" width="100%">`;
 names.forEach((n,i)=>{const pts=series[n].map((p,j)=>[40+j*(w-60)/Math.max(1,L-1),h-25-(p.avg-mn)/((mx-mn)||1)*(h-50)]);
 s+=`<polyline fill="none" stroke="${COL[i%6]}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" points="${pts.map(p=>p.join(',')).join(' ')}"/>`;pts.forEach(p=>s+=`<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="${COL[i%6]}"/>`)});
 s+=`<text x="2" y="14">${fmt(mx)}</text><text x="2" y="${h-22}">${fmt(mn)}</text></svg>`;$(el).innerHTML=s}
function bars(rows){const mx=Math.max(...rows.map(r=>r.avg));$('bars').innerHTML=rows.map((r,i)=>`<div class="brow"><span>${E(r.category)}</span><div class="t"><div style="width:${r.avg/mx*100}%;background:linear-gradient(90deg,${COL[i%6]},${COL[(i+1)%6]})"></div></div><b>${fmt(r.avg)}</b></div>`).join('')}
async function hist(sku,name){const h=await J('/api/history?sku='+encodeURIComponent(sku));$('histname').textContent=name+' ('+sku+')';line('hist',{[sku]:h.map(p=>({run:p.run,avg:p.price}))},900,200)}
async function prods(){const d=await J('/api/products?q='+encodeURIComponent($('q').value)+'&category='+$('cat').value);
 $('prods').innerHTML='<tr><th>SKU</th><th>Name</th><th>Category</th><th class=n>Price</th><th>Stock</th></tr>'+d.map(p=>`<tr class=click data-s="${E(p.sku)}" data-n="${E(p.name)}"><td>${E(p.sku)}</td><td>${E(p.name)}</td><td>${E(p.category)}</td><td class=n>${fmt(p.price)}</td><td>${p.in_stock==null?'?':p.in_stock?'Yes':'No'}</td></tr>`).join('');
 document.querySelectorAll('#prods tr.click').forEach(r=>r.onclick=()=>hist(r.dataset.s,r.dataset.n))}
$('th').onclick=()=>{const r=document.documentElement;r.dataset.theme=(r.dataset.theme||'dark')==='dark'?'light':'dark'};
(async()=>{const s=await J('/api/summary');
 $('kpis').innerHTML=[['Runs',s.runs],['Products',s.products],['Average price (EGP)',fmt(s.avg_price)],['Out of stock',s.out_of_stock]].map(k=>`<div class="card kpi"><small>${k[0]}</small><div>${k[1]}</div></div>`).join('');
 const last=s.runs_list.at(-1);$('runinfo').textContent=last?'Latest run: '+last.label:'';
 const c=await J('/api/categories');bars(c);c.forEach(x=>$('cat').add(new Option(x.category,x.category)));
 const t=await J('/api/trend');line('trend',t);$('legend').innerHTML=Object.keys(t).map((n,i)=>`<span><i style="background:${COL[i%6]}"></i>${E(n)}</span>`).join('');
 const ch=await J('/api/changes');$('changes').innerHTML='<tr><th>Product</th><th class=n>Old</th><th class=n>New</th><th class=n>%</th></tr>'+ch.slice(0,8).map(x=>`<tr><td>${E(x.name)}</td><td class=n>${fmt(x.old)}</td><td class=n>${fmt(x.new)}</td><td class="n ${x.pct>0?'up':'down'}">${x.pct>0?'+':''}${x.pct}</td></tr>`).join('');
 const d=await J('/api/deals');$('deals').innerHTML='<tr><th>Product</th><th class=n>Now</th><th class=n>Average</th><th class=n>Below</th></tr>'+d.slice(0,8).map(x=>`<tr><td>${E(x.name)}</td><td class=n>${fmt(x.now)}</td><td class=n>${fmt(x.avg)}</td><td class="n down">${x.below_pct}%</td></tr>`).join('');
 $('q').oninput=prods;$('cat').onchange=prods;prods()})();
</script></body></html>"""
