"""Small local web panel for the n8n workflow (demo / manual testing).

Usage:  python panel.py   ->  open http://127.0.0.1:8765
Needs the workflow running in n8n (N8N_URL, default http://127.0.0.1:5678). Standard library only.
It only forwards requests to the n8n webhooks; nothing is stored here.
"""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

N8N = os.environ.get("N8N_URL", "http://127.0.0.1:5678")

PAGE = """<!doctype html><meta charset=utf-8><title>Ramp Ops Assistant</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
body{font:16px system-ui;margin:0;background:#f4f5f7;color:#1c2330}
main{max-width:860px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px}.sub{color:#5b6573;margin-bottom:20px}
section{background:#fff;border-radius:10px;padding:16px;margin-bottom:16px;box-shadow:0 1px 3px #0001}
h2{font-size:15px;margin:0 0 10px;text-transform:uppercase;letter-spacing:.04em;color:#5b6573}
textarea{width:100%;box-sizing:border-box;height:80px;font:inherit;padding:8px;border:1px solid #c9ced6;border-radius:6px}
button{font:inherit;padding:8px 14px;border:0;border-radius:6px;background:#1f6feb;color:#fff;cursor:pointer}
button.ok{background:#1a7f37}button.no{background:#cf222e}button:disabled{opacity:.5}
.card{border:1px solid #e1e4e8;border-radius:8px;padding:10px;margin-top:10px}
.tag{display:inline-block;padding:2px 8px;border-radius:10px;font-size:13px;margin-right:6px;background:#eaeef2}
.critica{background:#ffd8d3}.alta{background:#ffe8c2}.media{background:#fff3b0}.baja{background:#d6f5dc}
table{border-collapse:collapse}td,th{padding:4px 14px 4px 0;text-align:left}.muted{color:#5b6573;font-size:14px}
</style><main>
<h1>Ramp Operations Assistant</h1><div class=sub>n8n + local LLM &middot; synthetic data only</div>
<section><h2>1. Report an incident</h2>
<textarea id=t placeholder="Free text, e.g. Sale humo de una bodega durante la carga."></textarea>
<p><button id=send>Classify</button> <span class=muted id=st></span></p><div id=res></div></section>
<section><h2>2. Waiting for human approval</h2><div id=pend class=muted>-</div></section>
<section><h2>3. Simulated alerts (routing by severity)</h2><div id=av class=muted>-</div></section>
<section><h2>4. Report</h2><div id=rep class=muted>-</div></section></main>
<script>
const $=i=>document.getElementById(i);
const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const tags=r=>`<span class="tag ${r.gravedad}">${esc(r.gravedad)}</span><span class=tag>${esc(r.tipo)}</span>`;
async function j(u,o){const r=await fetch(u,o);return r.json()}
async function refresh(){
 const p=await j('/api/pendientes');
 $('pend').innerHTML=p.total_pendientes?p.pendientes.map(x=>`<div class=card>${tags(x)}<b>${esc(x.id)}</b>
  <div>${esc(x.texto)}</div><div class=muted>${esc((x.motivos_seguridad||[]).join(', '))}</div>
  <p><button class=ok onclick="dec('${esc(x.id)}','aprobar')">Approve</button>
  <button class=no onclick="dec('${esc(x.id)}','rechazar')">Reject</button></p></div>`).join(''):'Nothing pending.';
 const a=await j('/api/avisos');
 $('av').innerHTML=a.total?a.avisos.slice(0,6).map(x=>`<div class=card><span class="tag ${x.gravedad}">${esc(x.gravedad)}</span><b>&rarr; ${esc(x.destino)}</b>
  <span class=muted> via ${esc(x.canal)} &middot; ${esc(x.plazo)}</span><div class=muted>${esc(x.id)}: ${esc(x.texto)}</div></div>`).join('')+'<p class=muted>Nothing is actually sent: this node is simulated. In production it is replaced by Telegram / email / Slack.</p>':'No alerts yet.';
 const r=await j('/api/informe');
 const tb=(o)=>'<table>'+Object.entries(o).map(([k,v])=>`<tr><td>${esc(k)}</td><td><b>${v}</b></td></tr>`).join('')+'</table>';
 $('rep').innerHTML=`<p>Total incidents: <b>${r.total}</b> &middot; pending: <b>${r.pendientes_de_aprobacion}</b></p>
  <div style="display:flex;gap:40px;flex-wrap:wrap"><div><b>By severity</b>${tb(r.por_gravedad)}</div>
  <div><b>By type</b>${tb(r.por_tipo)}</div><div><b>By status</b>${tb(r.por_estado)}</div></div>`;
}
async function dec(id,a){await j('/api/decision?id='+encodeURIComponent(id)+'&accion='+a);refresh()}
$('send').onclick=async()=>{
 const t=$('t').value.trim();if(!t)return;$('send').disabled=true;$('st').textContent='Classifying with the local model (can take ~20 s)...';
 try{const r=await j('/api/incidencia',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({id:'W'+Date.now().toString(36).toUpperCase(),texto:t})});
  $('res').innerHTML=`<div class=card>${tags(r)}<b>${esc(r.estado)}</b><div class=muted>${esc((r.motivos_seguridad||[]).join(', '))}</div></div>`;
 }catch(e){$('res').textContent='Error: '+e}
 $('send').disabled=false;$('st').textContent='';refresh()};
refresh();
</script>"""

RUTAS = {"/api/incidencia": "/webhook/incidencia", "/api/pendientes": "/webhook/pendientes",
         "/api/informe": "/webhook/informe", "/api/avisos": "/webhook/avisos", "/api/decision": "/webhook/decision"}


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, tipo="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", tipo + "; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self, metodo):
        ruta, _, query = self.path.partition("?")
        if ruta == "/" and metodo == "GET":
            return self._send(200, PAGE.encode(), "text/html")
        if ruta not in RUTAS:
            return self._send(404, b"{}")
        datos = self.rfile.read(int(self.headers.get("Content-Length", 0))) if metodo == "POST" else None
        req = urllib.request.Request(N8N + RUTAS[ruta] + ("?" + query if query else ""), data=datos, method=metodo,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                self._send(200, r.read())
        except Exception as e:
            self._send(502, json.dumps({"error": str(e)}).encode())

    def do_GET(self):
        self._proxy("GET")

    def do_POST(self):
        self._proxy("POST")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Panel on http://127.0.0.1:8765  (n8n at %s)" % N8N)
    HTTPServer(("127.0.0.1", 8765), H).serve_forever()
