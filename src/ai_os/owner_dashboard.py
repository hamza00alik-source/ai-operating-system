"""Small responsive owner dashboard for supervised technology discovery."""
from fastapi.responses import HTMLResponse

OWNER_HTML = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIOS · Owner Console</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#121a2d;--line:#26334d;--muted:#9aa9c3;--text:#edf3ff;--accent:#7c9cff;--green:#51d6a1;--amber:#f4c66a;--red:#ff8585}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 15% 0%,#17264b 0,transparent 42%),var(--bg);color:var(--text);font:15px/1.5 system-ui, sans-serif}
main{max-width:1180px;margin:auto;padding:24px 18px 60px}.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
h1{font-size:clamp(25px,4vw,36px);margin:0}.muted,.hint{color:var(--muted)}.tag{border:1px solid var(--line);border-radius:99px;padding:5px 10px;color:var(--green);font-size:12px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:22px 0}
.panel,.metric{background:linear-gradient(145deg,#151f35,#10182a);border:1px solid var(--line);border-radius:15px;padding:16px}
.metric strong{display:block;font-size:28px}.metric span{color:var(--muted);font-size:13px}
h2{font-size:18px;margin:0 0 14px}.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
button,input,select{font:inherit;border-radius:9px;border:1px solid var(--line);padding:10px 12px;background:#0c1425;color:var(--text)}
button{cursor:pointer;background:#263d75;border-color:#4564ac}button.secondary{background:#172238}button:disabled{opacity:.55;cursor:wait}
label{display:flex;gap:7px;align-items:center;color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;min-width:760px}th,td{text-align:left;padding:11px 10px;border-bottom:1px solid var(--line);vertical-align:top;font-size:13px}th{color:var(--muted);font-weight:600}
.scroll{overflow:auto}.pill{display:inline-block;border:1px solid var(--line);border-radius:99px;padding:2px 8px;font-size:11px}.good{color:var(--green)}.warn{color:var(--amber)}.bad{color:var(--red)}
.status{margin:12px 0;color:var(--muted);min-height:24px}.small{font-size:12px;color:var(--muted)}a{color:#a9c0ff}.section{margin-top:16px}
@media(max-width:760px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}main{padding:18px 12px}.panel{padding:12px}}
</style></head>
<body><main>
<div class="top"><div><div class="muted">AI OPERATING SYSTEM / OWNER CONSOLE</div><h1>Technology Discovery</h1><div class="hint">Inspect real GitHub projects before approving any integration.</div></div><span class="tag">Owner-supervised · Read-only discovery</span></div>
<div class="grid">
<div class="metric"><strong id="scans">—</strong><span>Discovery scans</span></div>
<div class="metric"><strong id="candidates">—</strong><span>Candidate projects</span></div>
<div class="metric"><strong id="review">—</strong><span>Needs review</span></div>
<div class="metric"><strong id="integrated">0</strong><span>Integrated from this pipeline</span></div>
</div>
<section class="panel">
<h2>Run a discovery scan</h2>
<div class="toolbar">
<label><input type="checkbox" name="cat" value="agent-frameworks" checked> Agent frameworks</label>
<label><input type="checkbox" name="cat" value="mcp-servers" checked> MCP servers</label>
<label><input type="checkbox" name="cat" value="rag-storage"> RAG & storage</label>
<label><input type="checkbox" name="cat" value="self-hosted"> Self-hosted</label>
<label><input type="checkbox" name="cat" value="llm-tools"> LLM tools</label>
<button id="run">Queue scan</button><button class="secondary" id="refresh">Refresh</button>
</div>
<div class="small">Scans read public GitHub repository metadata only. They do not install software, connect accounts, or change production.</div>
<div id="message" class="status" role="status">Connect with your owner API key to load live data.</div>
</section>
<section class="panel section"><h2>Recent scans</h2><div class="scroll"><table><thead><tr><th>Created</th><th>Categories</th><th>Status</th><th>Results</th><th>Error</th></tr></thead><tbody id="scanRows"><tr><td colspan="5" class="muted">No data loaded</td></tr></tbody></table></div></section>
<section class="panel section"><h2>Discovered projects</h2><div class="scroll"><table><thead><tr><th>Project</th><th>Category</th><th>License</th><th>Maintenance</th><th>Stars</th><th>Review state</th><th>Evidence</th></tr></thead><tbody id="candidateRows"><tr><td colspan="7" class="muted">No data loaded</td></tr></tbody></table></div></section>
<p class="small section">Cost, security, commercial-use rights, and provider terms remain unverified unless the evidence record explicitly says otherwise. A discovered project is not an approved integration.</p>
</main>
<script>
const $=id=>document.getElementById(id);let key=sessionStorage.getItem("aios_owner_key")||"";
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function say(s){$("message").textContent=s}
async function api(path,options={}){const response=await fetch(path,{...options,headers:{"Content-Type":"application/json","X-API-Key":key,...(options.headers||{})}});if(response.status===401)throw Error("Owner API key rejected. Enter a valid key and refresh.");if(!response.ok)throw Error("API "+response.status+": "+(await response.text()).slice(0,300));return response.json()}
function date(s){return s?new Date(s).toLocaleString():"—"}
async function refresh(){try{const [scans,candidates]=await Promise.all([api("/discovery/scans"),api("/discovery/candidates")]);$("scans").textContent=scans.length;$("candidates").textContent=candidates.length;$("review").textContent=candidates.filter(c=>c.status==="needs-review").length;
$("scanRows").innerHTML=scans.length?scans.map(s=>'<tr><td>'+esc(date(s.created_at))+'</td><td>'+esc((s.categories||[]).join(", "))+'</td><td><span class="pill">'+esc(s.status)+'</span></td><td>'+esc(s.result_count)+'</td><td class="bad">'+esc(s.error||"—")+'</td></tr>').join():'<tr><td colspan="5">No scans yet</td></tr>';
$("candidateRows").innerHTML=candidates.length?candidates.map(c=>'<tr><td><a target="_blank" rel="noopener" href="'+esc(c.canonical_url)+'">'+esc(c.full_name)+'</a><div class="small">'+esc(c.description)+'</div></td><td>'+esc(c.category)+'</td><td>'+esc(c.license)+'</td><td>'+esc(c.maintenance)+'</td><td>'+esc(c.stars)+'</td><td><span class="pill '+(c.status==="needs-review"?"warn":"good")+'">'+esc(c.status)+'</span></td><td><a target="_blank" rel="noopener" href="'+esc(c.evidence?.url||c.canonical_url)+'">Source</a><div class="small">Cost: '+esc(c.evidence?.cost||"unknown")+' · Security: '+esc(c.evidence?.security||"unknown")+'</div></td></tr>').join():'<tr><td colspan="7">No candidates yet. Queue a scan to discover projects.</td></tr>';
say("Live data loaded at "+new Date().toLocaleTimeString()+".");}catch(e){say(e.message)}}
$("run").onclick=async()=>{const categories=[...document.querySelectorAll('input[name="cat"]:checked')].map(x=>x.value);if(!categories.length){say("Select at least one category.");return}try{$("run").disabled=true;const result=await api("/discovery/scans",{method:"POST",body:JSON.stringify({categories})});say("Scan queued: "+result.id+". The background worker must be running to process it.");await refresh()}catch(e){say(e.message)}finally{$("run").disabled=false}};
$("refresh").onclick=refresh;
if(!key){key=prompt("Enter your AIOS owner API key (kept only for this browser tab):")||"";if(key)sessionStorage.setItem("aios_owner_key",key)}
if(key)refresh();
</script></body></html>
"""

def owner_dashboard() -> HTMLResponse:
    return HTMLResponse(OWNER_HTML)
