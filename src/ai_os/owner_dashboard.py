"""Small responsive owner dashboard for supervised technology discovery."""
from fastapi.responses import HTMLResponse

OWNER_HTML = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIOS · Company Control Center</title>
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
<body><div id="loginPanel" style="position:fixed;inset:0;z-index:20;background:#080d19ee;display:flex;align-items:center;justify-content:center;padding:20px"><form id="loginForm" class="panel" style="width:min(420px,100%)"><h2>Owner sign in</h2><p class="small">Enter your Owner API Key once. AIOS will create a secure 14-day browser session. The key is not saved in browser storage.</p><input id="loginKey" type="password" autocomplete="current-password" placeholder="AIOS Owner API Key" required style="width:100%;margin:8px 0"><button id="loginButton" type="submit" style="width:100%">Sign in securely</button><div id="loginStatus" class="status" role="status"></div></form></div><main>
<div class="top"><div><div class="muted">AI OPERATING SYSTEM / OWNER CONSOLE</div><h1>AI Company Control Center</h1><div class="hint">Inspect real GitHub projects before approving any integration.</div></div><div class="toolbar"><span class="tag">Owner-supervised · bounded AI execution</span><button id="logoutButton" class="secondary">Log out</button></div></div>
<nav class="toolbar section"><a href="#overview">Company</a><a href="#workforce">Workforce</a><a href="#sources">Repositories</a><a href="#tasks">Tasks & approvals</a><a href="#discovery">Technology</a><a href="#models">AI models</a></nav>
<section id="overview" class="panel section"><h2>Company operations</h2><div class="grid" style="margin:10px 0"><div class="metric"><strong id="workforceCount">283</strong><span>Catalogued specialists</span></div><div class="metric"><strong id="departmentCount">18</strong><span>Departments</span></div><div class="metric"><strong id="taskCount">—</strong><span>Tasks</span></div><div class="metric"><strong id="approvalCount">—</strong><span>Pending approvals</span></div></div><div id="companyStatus" class="small">Workforce catalog loaded. Bounded specialist execution and CEO review are available for text-only tasks; external actions remain disabled.</div></section>
<section id="workforce" class="panel section"><h2>Agency workforce · 283 specialists</h2><p class="small">18 departments · 284 roles including CEO. Source: <a href="https://github.com/hamza00alik-source/agency-agents" target="_blank" rel="noopener">Agency Agents repository</a> · MIT. Roles are invoked on demand by a shared worker; they are not 283 always-on processes.</p><div class="toolbar"><input id="agentSearch" placeholder="Search 283 specialists…" style="flex:1;min-width:180px"><select id="departmentFilter"><option value="">All departments</option></select><button id="loadAgents" class="secondary">Refresh roster</button></div><div id="departmentChips" class="toolbar section"></div><div class="scroll section"><table><thead><tr><th>Specialist</th><th>Department</th><th>Runtime state</th><th>Source</th></tr></thead><tbody id="agentRows"><tr><td colspan="4">Loading workforce catalog…</td></tr></tbody></table></div></section>
<section id="sources" class="panel section"><h2>Repository intelligence · 12 sources</h2><p class="small">The Agency Agents workforce and Automaton runtime reference are separated from the ten company/platform comparison repositories. Reference status does not mean code is installed or trusted.</p><div class="scroll"><table><thead><tr><th>Repository</th><th>Role</th><th>Current state</th><th>Purpose</th><th>License</th></tr></thead><tbody id="sourceRows"><tr><td colspan="5">Loading repository inventory…</td></tr></tbody></table></div></section>
<section id="tasks" class="panel section"><h2>Tasks & owner approvals</h2><form id="taskForm" class="toolbar"><input id="taskTitle" required maxlength="200" placeholder="New company task" style="flex:1;min-width:180px"><select id="taskDepartment"><option value="general">General</option><option value="research">Research</option><option value="engineering">Engineering</option><option value="product">Product</option><option value="marketing">Marketing</option><option value="sales">Sales</option><option value="finance">Finance</option><option value="operations">Operations</option><option value="support">Support</option></select><button type="submit">Create task</button></form><div class="toolbar section"><button id="loadOperations" class="secondary">Refresh operations</button><span class="small">Owner approval remains mandatory for consequential actions.</span></div><div id="taskApprovalPanel" class="small">No operational data loaded.</div><div id="agentRunOutput" class="section" aria-live="polite"></div></section>
<div class="grid">
<div class="metric"><strong id="scans">—</strong><span>Discovery scans</span></div>
<div class="metric"><strong id="candidates">—</strong><span>Candidate projects</span></div>
<div class="metric"><strong id="review">—</strong><span>Needs review</span></div>
<div class="metric"><strong id="integrated">0</strong><span>Integrated from this pipeline</span></div>
</div>
<section id="discovery" class="panel">
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

<section id="models" class="panel section"><h2>Live AI model gateway</h2>
<div class="small">OpenRouter keys are encrypted on the server before storage. The first connection uses only the free-model router and has no paid fallback. Use HTTPS.</div>
<div class="section" style="border:1px solid var(--line);border-radius:10px;padding:12px"><strong>Provider credentials · OpenRouter</strong><div class="small">Enter your OpenRouter key here. It is sent only to the authenticated server, encrypted at rest, and never returned to this page. Do not paste it into chat or GitHub.</div><div class="toolbar" style="margin-top:10px"><input id="providerApiKey" type="password" autocomplete="off" placeholder="OpenRouter API key" style="flex:1;min-width:220px"><button id="saveProviderKey">Save encrypted key</button></div><label style="margin-top:10px"><input id="confirmFreeOnly" type="checkbox"> I confirm this connection must use the free-only router, with no paid model or paid fallback.</label><div id="credentialStatus" class="status">Credential status not loaded.</div></div></div>
<div class="toolbar" style="margin-top:12px"><select id="providerSelect"><option value="">Loading providers…</option></select><button class="secondary" id="loadProviders">Refresh providers</button><button id="testProvider">Test live connection</button></div>
<div id="providerStatus" class="status">Provider status not loaded.</div>
<textarea id="modelPrompt" rows="3" style="width:100%;margin:8px 0" placeholder="Enter a small test prompt. This sends a real request to the selected provider."></textarea>
<button id="runModel">Run real model request</button>
<pre id="modelOutput" style="white-space:pre-wrap;overflow-wrap:anywhere;background:#0c1425;border:1px solid var(--line);border-radius:9px;padding:12px;min-height:60px">No live inference run yet.</pre>
</section>
</main>
<script>
const $=id=>document.getElementById(id);let authenticated=false;
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function say(s){$("message").textContent=s}
async function api(path,options={}){const response=await fetch(path,{...options,credentials:"same-origin",headers:{"Content-Type":"application/json",...(options.headers||{})}});if(response.status===401){showLogin("Your owner session expired. Sign in again.");throw Error("Owner session expired. Please sign in again.");}if(!response.ok)throw Error("API "+response.status+": "+(await response.text()).slice(0,300));return response.json()}
function date(s){return s?new Date(s).toLocaleString():"—"}
async function refresh(){try{const [scans,candidates]=await Promise.all([api("/discovery/scans"),api("/discovery/candidates")]);$("scans").textContent=scans.length;$("candidates").textContent=candidates.length;$("review").textContent=candidates.filter(c=>c.status==="needs-review").length;
$("scanRows").innerHTML=scans.length?scans.map(s=>'<tr><td>'+esc(date(s.created_at))+'</td><td>'+esc((s.categories||[]).join(", "))+'</td><td><span class="pill">'+esc(s.status)+'</span></td><td>'+esc(s.result_count)+'</td><td class="bad">'+esc(s.error||"—")+'</td></tr>').join():'<tr><td colspan="5">No scans yet</td></tr>';
$("candidateRows").innerHTML=candidates.length?candidates.map(c=>'<tr><td><a target="_blank" rel="noopener" href="'+esc(c.canonical_url)+'">'+esc(c.full_name)+'</a><div class="small">'+esc(c.description)+'</div></td><td>'+esc(c.category)+'</td><td>'+esc(c.license)+'</td><td>'+esc(c.maintenance)+'</td><td>'+esc(c.stars)+'</td><td><span class="pill '+(c.review_state==="rejected"?"bad":c.review_state==="approved-for-sandbox"?"good":"warn")+'">'+esc(c.review_state||"pending")+'</span><div class="small">Metadata: '+esc(c.status)+'</div><button class="secondary" data-url="'+esc(c.canonical_url)+'" data-decision="approved-for-sandbox" onclick="reviewCandidate(this.dataset.url,this.dataset.decision)">Approve sandbox</button> <button class="secondary" data-url="'+esc(c.canonical_url)+'" data-decision="rejected" onclick="reviewCandidate(this.dataset.url,this.dataset.decision)">Reject</button></td><td><a target="_blank" rel="noopener" href="'+esc(c.evidence?.url||c.canonical_url)+'">Source</a><div class="small">Cost: '+esc(c.evidence?.cost||"unknown")+' · Security: '+esc(c.evidence?.security||"not-tested")+'</div></td></tr>').join():'<tr><td colspan="7">No candidates yet. Queue a scan to discover projects.</td></tr>';
say("Live data loaded at "+new Date().toLocaleTimeString()+".");}catch(e){say(e.message)}}
$("run").onclick=async()=>{const categories=[...document.querySelectorAll('input[name="cat"]:checked')].map(x=>x.value);if(!categories.length){say("Select at least one category.");return}try{$("run").disabled=true;const result=await api("/discovery/scans",{method:"POST",body:JSON.stringify({categories})});say("Scan queued: "+result.id+". The background worker must be running to process it.");await refresh()}catch(e){say(e.message)}finally{$("run").disabled=false}};
$("refresh").onclick=refresh;
window.reviewCandidate=async(url,decision)=>{const label=decision==="approved-for-sandbox"?"Approve for isolated sandbox review":"Reject candidate";if(!confirm(label+"? This records your decision only; it will not install or execute anything."))return;const notes=prompt("Optional review notes:")||"";try{await api("/discovery/candidates/review",{method:"POST",body:JSON.stringify({repository_url:url,decision,notes})});say("Owner decision saved. No software was installed or executed.");await refresh()}catch(e){say(e.message)}};


async function loadAgents(){
 try{
  const q=$("agentSearch").value.trim(),dep=$("departmentFilter").value;
  const params=new URLSearchParams();if(q)params.set("q",q);if(dep)params.set("department",dep);
  const data=await api("/workforce/agents?"+params.toString());
  $("workforceCount").textContent=data.agent_count;$("departmentCount").textContent=data.department_count;
  const select=$("departmentFilter"),current=select.value;
  if(select.options.length===1){for(const d of data.departments){const o=document.createElement("option");o.value=d.id;o.textContent=d.name+" ("+d.agent_count+")";select.appendChild(o)}}
  if(current)select.value=current;
  $("departmentChips").innerHTML=data.departments.map(d=>'<span class="pill">'+esc(d.name)+': '+esc(d.agent_count)+'</span>').join("");
  $("agentRows").innerHTML=data.agents.map(a=>'<tr><td><strong>'+esc(a.name)+'</strong><div class="small">'+esc(a.id)+'</div></td><td>'+esc(a.department)+'</td><td><span class="pill warn">Available on demand</span></td><td><a href="'+esc(a.source_url)+'" target="_blank" rel="noopener">Agent instructions</a></td></tr>').join("")||'<tr><td colspan="4">No matching specialists.</td></tr>';
  $("companyStatus").textContent="Source: "+data.source_repository+" · License: "+data.license+" · 283 specialist definitions indexed. Shared agent worker: invokes the best-matched specialist instructions for each task, then performs CEO review. Check worker health in Company operations.";
 }catch(e){$("agentRows").innerHTML='<tr><td colspan="4">'+esc(e.message)+'</td></tr>'}
}

async function loadSources(){
 try{
  const data=await api("/company/sources");
  $("sourceRows").innerHTML=data.sources.map(s=>'<tr><td><a href="https://github.com/'+esc(s.repository)+'" target="_blank" rel="noopener">'+esc(s.repository)+'</a></td><td>'+esc(s.role)+'</td><td><span class="pill '+(s.status==="catalogued"?"good":"warn")+'">'+esc(s.status)+'</span></td><td>'+esc(s.purpose)+'</td><td>'+esc(s.license)+'</td></tr>').join("");
 }catch(e){$("sourceRows").innerHTML='<tr><td colspan="5">'+esc(e.message)+'</td></tr>'}
}
async function loadOperations(){
 try{
  const [overview,tasks,approvals,runs]=await Promise.all([api("/company/overview"),api("/tasks"),api("/approvals"),api("/agent-runs")]);
  $("taskCount").textContent=Object.values(overview.tasks).reduce((a,b)=>a+b,0);
  $("approvalCount").textContent=overview.approvals.pending||0;
  const latest={};runs.forEach(r=>{if(!latest[r.task_id])latest[r.task_id]=r});
  $("taskApprovalPanel").innerHTML='<p><strong>Tasks</strong>: '+tasks.length+' · <strong>Approvals pending</strong>: '+(overview.approvals.pending||0)+' · <strong>Agent worker</strong>: '+esc(overview.execution_runtime)+'</p><div class="scroll"><table><thead><tr><th>Task</th><th>Department</th><th>Status</th><th>AI team</th></tr></thead><tbody>'+tasks.slice(0,30).map(t=>{const r=latest[t.id];return '<tr><td>'+esc(t.title)+'</td><td>'+esc(t.department)+'</td><td>'+esc(t.status)+'</td><td>'+(r?'<span class="pill">'+esc(r.status)+'</span> ':'')+'<button class="secondary" data-id="'+esc(t.id)+'" onclick="runTask(this.dataset.id)">Run AI team</button></td></tr>'}).join("")+'</tbody></table></div><h3>Approval inbox</h3><div class="scroll"><table><thead><tr><th>Requested action</th><th>Details</th><th>Status</th><th>Owner decision</th></tr></thead><tbody>'+approvals.slice(0,20).map(a=>'<tr><td>'+esc(a.action)+'</td><td>'+esc(a.details)+'</td><td>'+esc(a.status)+'</td><td>'+(a.status==="pending"?'<button class="secondary" data-id="'+esc(a.id)+'" onclick="decideApproval(this.dataset.id,\'approved\')">Approve</button> <button class="secondary" data-id="'+esc(a.id)+'" onclick="decideApproval(this.dataset.id,\'rejected\')">Reject</button>':'—')+'</td></tr>').join("")+'</tbody></table></div>';
 }catch(e){$("taskApprovalPanel").textContent=e.message}
}
window.runTask=async(taskId)=>{try{$("agentRunOutput").textContent="Queuing specialist and CEO review…";const run=await api("/tasks/"+encodeURIComponent(taskId)+"/execute",{method:"POST"});$("agentRunOutput").textContent="AI team run "+run.id+" · "+run.status+". Waiting for specialist and CEO review…";await loadOperations();pollAgentRun(run.id)}catch(e){$("agentRunOutput").textContent=e.message}};
async function pollAgentRun(runId){try{const r=await api("/agent-runs/"+encodeURIComponent(runId));if(r.status==="completed"){$("agentRunOutput").innerHTML='<h3>Completed · '+esc(r.assigned_agent_id||"specialist")+' + CEO review</h3><h4>Specialist report</h4><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(r.specialist_output)+'</pre><h4>CEO-reviewed deliverable</h4><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(r.ceo_review)+'</pre><p class="small">Usage: '+esc(JSON.stringify(r.usage||{}))+'</p>';await loadOperations();return}if(r.status==="failed"){$("agentRunOutput").textContent="Agent run failed: "+r.error;await loadOperations();return}$("agentRunOutput").textContent="AI team run "+r.status+"…";setTimeout(()=>pollAgentRun(runId),3000)}catch(e){$("agentRunOutput").textContent=e.message}}

window.decideApproval=async(id,decision)=>{if(!confirm("Confirm "+decision+" this requested action? The CEO/agent must still execute it through the approved runtime."))return;try{await api("/approvals/"+encodeURIComponent(id)+"/decision",{method:"POST",body:JSON.stringify({decision})});await loadOperations()}catch(e){say(e.message)}};
$("taskForm").addEventListener("submit",async e=>{e.preventDefault();const title=$("taskTitle").value.trim();if(!title)return;try{await api("/tasks",{method:"POST",body:JSON.stringify({title,department:$("taskDepartment").value})});$("taskTitle").value="";await loadOperations()}catch(e){say(e.message)}});
$("loadAgents").onclick=loadAgents;$("agentSearch").addEventListener("input",()=>{clearTimeout(window.agentSearchTimer);window.agentSearchTimer=setTimeout(loadAgents,250)});$("departmentFilter").onchange=loadAgents;$("loadOperations").onclick=loadOperations;
async function loadProviders(){try{const providers=await api("/llm/providers");const select=$("providerSelect");select.innerHTML=providers.map(p=>'<option value="'+esc(p.id)+'">'+esc(p.name)+' · '+(p.eligible?'eligible':'blocked')+'</option>').join("");$("providerStatus").textContent=providers.map(p=>p.name+": "+(p.eligible?"eligible (free status owner-confirmed)":p.reason)).join("\\n");}catch(e){$("providerStatus").textContent=e.message}}
async function runModel(test){const provider=$("providerSelect").value;if(!provider){$("modelOutput").textContent="Select a provider first.";return}const prompt=test?"Reply with exactly: AIOS live connection successful":$("modelPrompt").value.trim();if(!prompt){$("modelOutput").textContent="Enter a prompt first.";return}const button=test?$("testProvider"):$("runModel");button.disabled=true;$("modelOutput").textContent="Sending live request…";try{const result=await api(test?"/llm/test":"/llm/run",{method:"POST",body:JSON.stringify({provider,prompt})});$("modelOutput").textContent=JSON.stringify(result,null,2)}catch(e){$("modelOutput").textContent="Live request failed: "+e.message}finally{button.disabled=false}}
$("loadProviders").onclick=loadProviders;$("testProvider").onclick=()=>runModel(true);$("runModel").onclick=()=>runModel(false);
async function saveProviderKey(){const api_key=$("providerApiKey").value.trim();if(!api_key){$("credentialStatus").textContent="Enter your OpenRouter key.";return}if(!$("confirmFreeOnly").checked){$("credentialStatus").textContent="Confirm free-only routing before saving.";return}const b=$("saveProviderKey");b.disabled=true;$("credentialStatus").textContent="Encrypting and saving on the server…";try{const result=await api("/llm/credentials/openrouter",{method:"POST",body:JSON.stringify({api_key,confirm_free_only:true})});$("providerApiKey").value="";$("credentialStatus").textContent="Saved securely in encrypted storage. Secret was not returned.";await loadProviders()}catch(e){$("credentialStatus").textContent=e.message}finally{b.disabled=false}}
$("saveProviderKey").onclick=saveProviderKey;

function showLogin(message=""){ $("loginPanel").style.display="flex"; $("loginStatus").textContent=message; $("loginKey").focus(); }
async function startDashboard(){authenticated=true;$("loginPanel").style.display="none";refresh();loadProviders();loadAgents();loadSources();loadOperations();api("/llm/credentials").then(x=>$("credentialStatus").textContent=x.openrouter.configured?"OpenRouter credential is saved (encrypted).":"No OpenRouter credential saved yet.").catch(e=>$("credentialStatus").textContent=e.message);if(!window.aiosRefreshTimer)window.aiosRefreshTimer=setInterval(refresh,10000)}
$("loginForm").addEventListener("submit",async e=>{e.preventDefault();const b=$("loginButton");b.disabled=true;$("loginStatus").textContent="Validating owner key…";try{const r=await fetch("/auth/session",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({api_key:$("loginKey").value})});if(!r.ok)throw Error("Owner key was rejected. Check the key in Railway Variables.");$("loginKey").value="";await startDashboard()}catch(err){$("loginStatus").textContent=err.message}finally{b.disabled=false}});
$("logoutButton").onclick=async()=>{try{await fetch("/auth/session",{method:"DELETE",credentials:"same-origin"});}finally{authenticated=false;showLogin("You have been signed out.")}};
fetch("/auth/session",{credentials:"same-origin"}).then(r=>r.json()).then(s=>{if(s.authenticated)startDashboard();else showLogin()}).catch(()=>showLogin("Sign in to continue."));
</script></body></html>
"""

def owner_dashboard() -> HTMLResponse:
    return HTMLResponse(OWNER_HTML)
