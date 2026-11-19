"""Owner-controlled FastAPI surface for the OpenCompany runtime."""
from __future__ import annotations
import base64, hashlib, html, json, os, secrets, time
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID, uuid4
from fastapi import FastAPI, Depends, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from opencompany_core.domain import AuditRecord, TaskState
from opencompany_app.runtime import Runtime, create_runtime, WorkItem, _audit
from opencompany_app.catalogue import ROLE_CATALOGUE, DEPARTMENT_CATALOGUE, DEPARTMENTS
from opencompany_core.asset_storage import AssetStorageError
from opencompany_core.asset_scanning import AssetScanError

app=FastAPI(title="OpenCompany")
_default_runtime_instance=None
_sessions={}
_login_failures=defaultdict(list)
_invalid_key_failures=defaultdict(list)

def _default_runtime():
    global _default_runtime_instance
    if _default_runtime_instance is None:
        _default_runtime_instance=Runtime(os.getenv("OPENCOMPANY_DATABASE_PATH",":memory:"))
    return _default_runtime_instance

def get_runtime(): return _default_runtime()
def get_store(runtime=Depends(get_runtime)): return runtime.store
def get_delegation_store(runtime=Depends(get_runtime)): return runtime.delegations

class ManagerProposalInput(BaseModel):
    max_specialists:int=Field(default=15,ge=1,le=50)

class SessionInput(BaseModel):
    api_key:str

def _clear_login_failures(key):
    _login_failures.pop(key,None);_invalid_key_failures.pop(key,None)

def _prune(values):
    now=time.time()
    while values and now-values[0]>300:values.pop(0)
    return values

def _business_fernet():
    secret=os.getenv("OPENCOMPANY_SECRET_ENCRYPTION_KEY","")
    if len(secret)<32:
        raise HTTPException(503,"Business credential encryption is not configured.")
    from cryptography.fernet import Fernet
    key=base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def _business_id(value):
    if value not in ("physical-agency","physical-brand","digital-products"):
        raise HTTPException(404,"Business unit not found.")
    return value


def _owner(request:Request, x_opencompany_api_key:str|None=Header(default=None)):
    key=os.getenv("OPENCOMPANY_OWNER_API_KEY")
    if not key: raise HTTPException(503,"Owner authentication is not configured.")
    client=request.client.host if request.client else "unknown"
    supplied=x_opencompany_api_key
    if supplied:
        failures=_prune(_invalid_key_failures[client])
        if len(failures)>=4: raise HTTPException(429,"Too many invalid owner credentials.",headers={"Retry-After":"60"})
        if not secrets.compare_digest(supplied,key):
            failures.append(time.time());raise HTTPException(401,"Invalid owner credentials.")
        return "owner"
    token=request.cookies.get("opencompany_session")
    session=_sessions.get(token or "")
    if session and session["expires"]>time.time():
        if request.method not in ("GET","HEAD","OPTIONS"):
            csrf=request.headers.get("x-csrf-token")
            if not csrf:
                raise HTTPException(401,"Owner authentication required for cookie-authenticated writes.")
            origin=request.headers.get("origin")
            if origin != str(request.base_url).rstrip("/"):
                raise HTTPException(403,"Cookie-authenticated writes must come from the same origin.")
            if not secrets.compare_digest(csrf,session["csrf"]) or request.cookies.get("opencompany_csrf")!=csrf:
                raise HTTPException(403,"A valid CSRF token is required.")
        return "owner"
    if supplied is None: raise HTTPException(401,"Owner authentication required.")
    raise HTTPException(401,"Invalid owner credentials.")

def _security_headers(response:Response):
    nonce=secrets.token_urlsafe(18)
    response.headers["Cache-Control"]="no-store"
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Referrer-Policy"]="no-referrer"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Content-Security-Policy"]=f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; style-src 'self' 'nonce-{nonce}'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    response.headers["X-OpenCompany-Nonce"]=nonce
    return nonce

@app.middleware("http")
async def security_middleware(request,call_next):
    response=await call_next(request)
    nonce=_security_headers(response)
    if request.url.path=="/owner" and response.media_type=="text/html":
        response.headers["X-OpenCompany-Nonce"]=nonce
    return response

@app.get("/health")
def health():return {"status":"ok","mode":"owner-authenticated","service":"opencompany-core"}

@app.get("/ready")
def ready():
    if not os.getenv("OPENCOMPANY_OWNER_API_KEY"):raise HTTPException(503,"Owner runtime configuration is required.")
    runtime=get_runtime()
    try:
        runtime.sqlite._connection.execute("SELECT 1").fetchone()
    except Exception:raise HTTPException(503,"Persistent storage is unavailable.")
    return {"status":"ready","service":"opencompany-core","storage":"ok","worker_fleet_running":runtime.fleet.status().running,"provider_required_for_readiness":False}

@app.get("/owner",response_class=HTMLResponse)
def owner_dashboard():
    nonce=secrets.token_urlsafe(18)
    page="""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>OpenCompany · Owner Control Center</title>
<style nonce="__NONCE__">
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color-scheme:light dark}
*{box-sizing:border-box}body{margin:0;background:Canvas;color:CanvasText}
header{padding:22px max(18px,calc((100vw - 1180px)/2));border-bottom:1px solid #8885;display:flex;justify-content:space-between;gap:16px;align-items:center}
main{max-width:1180px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:1.55rem;margin:0}h2{font-size:1.08rem;margin:0 0 14px}h3{font-size:.95rem;margin:0 0 8px}
.muted{opacity:.7;font-size:.88rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:16px 0}
.card,section{border:1px solid #8885;border-radius:14px;padding:16px;background:Canvas}
.metric{font-size:1.8rem;font-weight:700;display:block;margin-top:8px}
.columns{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:14px}
button,input,select,textarea{font:inherit;border:1px solid #8888;border-radius:8px;padding:9px;background:Canvas;color:CanvasText}
button{cursor:pointer}button.primary{background:#2563eb;color:white;border-color:#2563eb}button:disabled{opacity:.5;cursor:not-allowed}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
form.inline{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}form.inline input,form.inline select{flex:1;min-width:130px}
table{width:100%;border-collapse:collapse;font-size:.9rem}th,td{text-align:left;padding:9px 6px;border-bottom:1px solid #8884;vertical-align:top}
.scroll{overflow-x:auto}.pill{display:inline-block;border:1px solid #8888;border-radius:20px;padding:2px 8px;font-size:.78rem}
.stack{display:grid;gap:8px}.rowitem{padding:9px 0;border-bottom:1px solid #8884;display:flex;justify-content:space-between;gap:10px;align-items:center}
#login{max-width:420px;margin:12vh auto;padding:22px;border:1px solid #8885;border-radius:14px}
#login form{display:grid;gap:12px}#login input{width:100%}
#notice{padding:10px 12px;border-radius:9px;background:#8882;margin:12px 0;display:none}
#dashboard[hidden],#login[hidden]{display:none!important}
@media(max-width:560px){header{align-items:flex-start;flex-direction:column}main{padding:14px 10px 40px}.card,section{padding:13px}h1{font-size:1.3rem}}
</style></head>
<body>
<header><div><h1>OpenCompany</h1><div class="muted">Owner control center · supervised company operations</div></div><button id="logout" hidden>Sign out</button></header>
<main>
<div id="notice" role="status" aria-live="polite"></div>
<section id="login" hidden><h2>Owner sign in</h2><p class="muted">Use your private OpenCompany owner key. It is sent only to this server and is not saved in browser storage.</p>
<form id="login-form"><input id="owner-key" type="password" autocomplete="current-password" placeholder="Owner API key" required><button class="primary" type="submit">Sign in</button></form></section>
<div id="dashboard" hidden>
<div class="actions"><button id="refresh" class="primary">Refresh company status</button><span class="muted" id="updated"></span></div>
<div class="grid">
<div class="card"><span class="muted">Provisioned agents</span><strong class="metric" id="metric-agents">—</strong><span class="muted" id="metric-active"></span></div>
<div class="card"><span class="muted">Work items</span><strong class="metric" id="metric-work">—</strong><span class="muted" id="metric-work-detail"></span></div>
<div class="card"><span class="muted">Queue</span><strong class="metric" id="metric-queue">—</strong><span class="muted" id="metric-queue-detail"></span></div>
<div class="card"><span class="muted">Finance records</span><strong class="metric" id="metric-finance">—</strong><span class="muted">Ledger entries, not verified cash balance</span></div>
</div>
<div class="columns">
<section><h2>Organization & workforce</h2><p class="muted">Role catalogue entries are templates; only provisioned profiles appear below. Activating a profile does not start a worker.</p>
<div class="actions"><button id="bootstrap-ceo">Provision CEO</button><button id="bootstrap-managers">Provision department managers</button><button id="bootstrap-specialists">Provision 500 specialists</button></div>
<div id="agents" class="stack"></div></section>
<section><h2>Company objectives & work</h2><p class="muted">Create draft work. Planning, delegation, queue admission and execution remain separate owner-controlled steps.</p>
<form id="task-form" class="stack"><input id="task-title" placeholder="Work item title" required maxlength="180">
<textarea id="task-objective" placeholder="Objective and expected deliverable" required rows="3"></textarea>
<select id="task-business"><option value="physical-agency">Physical-products agency</option><option value="physical-brand">Own physical-products brand</option><option value="digital-products">Digital products</option></select>
<select id="task-department" required></select><button class="primary" type="submit">Create draft work item</button></form>
<div id="tasks" class="stack"></div><div id="task-detail" class="stack"></div></section>
<section><h2>Execution & resources</h2><div class="actions"><button id="ceo-cycle">Run CEO coordination cycle</button><button id="advance-work">Advance CEO-ready work</button><button id="worker-start">Start worker (zero-cost only)</button><button id="worker-stop">Stop worker</button></div><div id="worker-status" class="stack"></div><div id="usage" class="stack"></div><p class="muted">Worker start requires an eligible owner-confirmed zero-cost provider. No paid fallback. No automatic customer contact, publishing or payments.</p></section>
<section><h2>Finance, budgets & reconciliation</h2>
<p class="muted">Amounts use integer minor units (for example, cents). Budgets are monitoring limits, not spending authorization. Reconciliation compares owner-entered statements with recorded ledger activity; it does not connect to a bank.</p>
<form id="budget-form" class="stack">
<select id="budget-business"><option value="physical-agency">Physical-products agency</option><option value="physical-brand">Own physical-products brand</option><option value="digital-products">Digital products</option></select>
<input id="budget-currency" value="USD" maxlength="3" placeholder="Currency code" required>
<input id="budget-limit" type="number" min="0" step="1" placeholder="Monthly expense limit (minor units)" required>
<input id="budget-rationale" placeholder="Reason for setting/changing this limit" required maxlength="1200">
<label><input id="budget-confirm" type="checkbox" required> I confirm this budget is for the selected business unit.</label>
<button class="primary" type="submit">Save budget limit</button></form>
<form id="reconciliation-form" class="stack">
<select id="recon-business"><option value="physical-agency">Physical-products agency</option><option value="physical-brand">Own physical-products brand</option><option value="digital-products">Digital products</option></select>
<input id="recon-currency" value="USD" maxlength="3" placeholder="Currency code" required>
<label>Period start <input id="recon-start" type="datetime-local" required></label>
<label>Period end <input id="recon-end" type="datetime-local" required></label>
<input id="recon-opening" type="number" step="1" placeholder="Opening balance (minor units)" required>
<input id="recon-closing" type="number" step="1" placeholder="Statement closing balance (minor units)" required>
<label><input id="recon-confirm" type="checkbox" required> I confirm these values were transcribed from the statement.</label>
<button class="primary" type="submit">Reconcile statement</button></form>
<h3>Budget status & ledger</h3><div id="finance" class="stack"></div>
<h3>Reconciliation history</h3><div id="reconciliation-list" class="stack"></div></section>
<section><h2>Departments</h2><div id="departments" class="stack"></div></section><section><h2>Business memory & integrations</h2>
<p class="muted">Memory is isolated by business unit and can only be written by the owner. Integration records remain pending review; listing them does not connect external services.</p>
<select id="memory-business"><option value="physical-agency">Physical-products agency</option><option value="physical-brand">Own physical-products brand</option><option value="digital-products">Digital products</option></select>
<form id="memory-form" class="stack">
<input id="memory-key" placeholder="Memory key" required maxlength="100">
<input id="memory-category" placeholder="Category" required maxlength="80">
<input id="memory-source" placeholder="Source / evidence reference" required maxlength="500">
<textarea id="memory-content" placeholder="Business memory content" required rows="3"></textarea>
<label><input id="memory-confirm" type="checkbox" required> I confirm this owner-written memory is accurate and belongs to this business unit.</label>
<button class="primary" type="submit">Save business memory</button></form>
<h3>Saved memories</h3><div id="memory-list" class="stack"></div>
<h3>Integration registry</h3>
<form id="integration-form" class="stack">
<input id="integration-provider" placeholder="Provider key (e.g. shop-api)" required maxlength="80">
<input id="integration-name" placeholder="Display name" required maxlength="120">
<input id="integration-credential" placeholder="Existing credential key" required maxlength="100">
<input id="integration-permissions" placeholder="Permissions, comma separated (read-only first)" required>
<textarea id="integration-rationale" placeholder="Why is this integration needed?" rows="2" required></textarea>
<label><input id="integration-confirm" type="checkbox" required> I confirm this registration is only a permission-review request.</label>
<button class="primary" type="submit">Register for review</button></form>
<div id="integration-list" class="stack"></div>
<h3>Stored credential references</h3><div id="credential-list" class="stack"></div></section>
</div></div></main>
<script nonce="__NONCE__">
(()=> {
"use strict";
let csrfToken="";
const el=id=>document.getElementById(id);
function notice(message,isError=false){const n=el("notice");n.textContent=message;n.style.display="block";n.style.border=isError?"1px solid #dc2626":"1px solid #8885";}
function clearNotice(){el("notice").style.display="none";}
async function api(path,options={}){
 const method=(options.method||"GET").toUpperCase();
 const headers={"Accept":"application/json",...(options.headers||{})};
 if(options.body!==undefined){headers["Content-Type"]="application/json";options.body=JSON.stringify(options.body);}
 if(method!=="GET"&&csrfToken)headers["X-CSRF-Token"]=csrfToken;
 const response=await fetch(path,{...options,method,headers,credentials:"same-origin"});
 const raw=await response.text();let data={};try{data=raw?JSON.parse(raw):{};}catch(_){data={detail:raw||"Unexpected server response"};}
 if(!response.ok)throw new Error(data.detail||("Request failed ("+response.status+")"));
 return data;
}
function node(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(className)n.className=className;return n;}
function setText(id,value){el(id).textContent=value===undefined||value===null?"—":String(value);}
function showDashboard(authenticated){el("login").hidden=authenticated;el("dashboard").hidden=!authenticated;el("logout").hidden=!authenticated;}
async function checkSession(){try{const s=await api("/auth/session");csrfToken=s.csrf_token||"";showDashboard(true);await refreshAll();}catch(_){showDashboard(false);}}
async function signIn(event){event.preventDefault();clearNotice();try{const result=await api("/auth/session",{method:"POST",body:{api_key:el("owner-key").value}});csrfToken=result.csrf_token||"";el("owner-key").value="";showDashboard(true);notice("Signed in. Loading company status.");await refreshAll();}catch(e){notice(e.message,true);}}
async function signOut(){try{await api("/auth/logout",{method:"POST",body:{}});}catch(_){}csrfToken="";showDashboard(false);notice("Signed out.");}
async function refreshAll(){
 clearNotice();
 try{
  const [agents,tasks,queue,workers,service,usage,finance,depts,orchestration]=await Promise.all([
   api("/agents"),api("/work-items"),api("/workers/queue"),api("/workers/status"),api("/workers/service-status"),api("/usage/model"),api("/finance/entries"),api("/finance/budgets"),api("/finance/reconciliations"),api("/organization/departments"),api("/executive/orchestration/status")
  ]);
  renderAgents(agents.agents||[]);renderTasks(tasks.items||[]);renderDepartments(depts.departments||[]);
  renderWorker(workers,service,queue,orchestration);renderUsage(usage);renderFinance(finance.entries||[],budgets.budgets||[],reconciliations.reconciliations||[]);
  await refreshBusinessContext();
  const aa=agents.agents||[],tt=tasks.items||[],fc=finance.entries||[],qc=queue.counts||{};
  setText("metric-agents",aa.length);setText("metric-active",aa.filter(a=>a.state==="active").length+" active · "+aa.filter(a=>a.state==="paused").length+" paused");
  setText("metric-work",tt.length);setText("metric-work-detail",tt.filter(x=>x.state!=="completed").length+" not completed");
  setText("metric-queue",queue.total||0);setText("metric-queue-detail",Object.entries(qc).map(([k,v])=>k+": "+v).join(" · ")||"No queue records");
  setText("metric-finance",fc.length);setText("updated","Updated "+new Date().toLocaleTimeString());
 }catch(e){notice("Could not load all company data: "+e.message,true);}
}
function renderAgents(agents){
 const root=el("agents");root.replaceChildren();
 if(!agents.length){root.append(node("p","No profiles provisioned yet.","muted"));return;}
 agents.slice(0,80).forEach(a=>{
  const row=node("div",undefined,"rowitem"),left=node("div"),name=node("strong",a.title||a.name||a.role_key),meta=node("div",(a.department||"")+" · "+a.role_key,"muted");
  left.append(name,meta);const right=node("div"),state=node("span",a.state,"pill"),btn=node("button",a.state==="active"?"Pause":a.state==="paused"?"Activate":"Activate");
  btn.addEventListener("click",async()=>{btn.disabled=true;try{await api("/agents/"+encodeURIComponent(a.id)+"/state",{method:"POST",body:{expected_revision:a.revision,target_state:a.state==="active"?"paused":"active"}});await refreshAll();}catch(e){notice(e.message,true);btn.disabled=false;}});
  right.append(state,btn);row.append(left,right);root.append(row);
 });
 if(agents.length>80)root.append(node("p","Showing first 80 of "+agents.length+" profiles. Use workforce APIs for the full catalogue.","muted"));
}
function actionButton(parent,label,handler){
 const button=node("button",label);button.addEventListener("click",async()=>{button.disabled=true;try{await handler();}catch(e){notice(e.message,true);}finally{button.disabled=false;}});parent.append(button);return button;
}
async function showTaskWorkflow(item,container){
 const data=await api("/work-items/"+encodeURIComponent(item.id)+"/workflow");
 container.replaceChildren();
 const heading=node("h3","Workflow · "+item.title);container.append(heading);
 container.append(node("p","State: "+data.work_item.state+" · Next action: "+data.next_action,"muted"));
 container.append(node("p","Prerequisites: "+(data.prerequisites||[]).map(x=>x.title+" ("+x.state+")").join(" · ")||"None"));
 container.append(node("p","Dependent work: "+(data.dependents||[]).map(x=>x.title+" ("+x.state+")").join(" · ")||"None"));
 (data.deliverables||[]).forEach((d,index)=>{
  container.append(node("h3","Deliverable "+(index+1)+" · "+(d.role_key||"specialist")));
  container.append(node("pre",String(d.content||"").slice(0,10000),"muted"));
 });
 if(item.state==="review"){
  const actions=node("div",undefined,"actions");
  actionButton(actions,"Approve deliverable",async()=>{
   const rationale=window.prompt("Owner review rationale","Reviewed and accepted");
   if(rationale===null||!rationale.trim())return;
   await api("/work-items/"+encodeURIComponent(item.id)+"/review",{method:"POST",body:{approved:true,rationale}});
   notice("Deliverable accepted and evaluation recorded.");await refreshAll();
  });
  actionButton(actions,"Reject deliverable",async()=>{
   const rationale=window.prompt("Explain what must be corrected","Revision required");
   if(rationale===null||!rationale.trim())return;
   await api("/work-items/"+encodeURIComponent(item.id)+"/review",{method:"POST",body:{approved:false,rationale}});
   notice("Deliverable rejected; task moved to failed for explicit retry.");await refreshAll();
  });
  container.append(actions);
 }
}
async function showDelegationProposals(item,container){
 const data=await api("/work-items/"+encodeURIComponent(item.id)+"/delegation-proposals");
 container.replaceChildren(node("h3","Delegation proposals · "+item.title));
 if(!data.proposals.length){container.append(node("p","No proposals saved.","muted"));return;}
 data.proposals.slice().reverse().forEach(proposal=>{
  const card=node("section"),heading=node("strong","Proposal · "+proposal.status),manager=node("p","Manager: "+proposal.manager_role_key+" · "+(proposal.children||[]).length+" specialists","muted");
  card.append(heading,manager);
  (proposal.children||[]).forEach(child=>card.append(node("p",child.title+" · "+child.role_key+" · "+child.state,"muted")));
  if(proposal.status==="draft"){
   const actions=node("div",undefined,"actions");
   actionButton(actions,"Approve & create child tasks",async()=>{
    const result=await api("/work-items/"+encodeURIComponent(item.id)+"/delegation-proposals/"+encodeURIComponent(proposal.id)+"/approve",{method:"POST",body:{}});
    notice("Delegation approved. "+(result.materialized_work_items||[]).length+" child tasks created; queue admission "+(result.queue_entries_created?"occurred":"did not occur")+".");await refreshAll();
   });
   actionButton(actions,"Reject proposal",async()=>{
    const rationale=window.prompt("Why are you rejecting this proposal?");
    if(rationale===null||!rationale.trim())return;
    await api("/work-items/"+encodeURIComponent(item.id)+"/delegation-proposals/"+encodeURIComponent(proposal.id)+"/reject",{method:"POST",body:{rationale}});
    notice("Delegation proposal rejected.");await refreshAll();
   });
   card.append(actions);
  }
  container.append(card);
 });
}
function renderTasks(items){
 const root=el("tasks");root.replaceChildren();
 if(!items.length){root.append(node("p","No work items yet.","muted"));return;}
 items.slice().reverse().slice(0,50).forEach(item=>{
  const card=node("section"),heading=node("strong",item.title),meta=node("p",(item.department||"")+" · "+(item.business_id||"")+" · "+(item.state||"draft")+" · "+(item.assigned_role_key||"Unassigned"),"muted");
  const actions=node("div",undefined,"actions");
  actionButton(actions,"Workflow details",()=>showTaskWorkflow(item,el("task-detail")));
  if(item.state==="draft"){
   actionButton(actions,"Create team proposal",async()=>{
    await api("/work-items/"+encodeURIComponent(item.id)+"/delegation-proposals",{method:"POST",body:{max_specialists:5,required_capabilities:[]}});
    notice("Draft delegation proposal created. Activate its manager and all proposed specialists before owner approval.");await showDelegationProposals(item,el("task-detail"));
   });
   actionButton(actions,"Show proposals",()=>showDelegationProposals(item,el("task-detail")));
  }
  if(item.state==="ready"&&item.assigned_agent_id){
   actionButton(actions,"Admit to queue",async()=>{
    await api("/work-items/"+encodeURIComponent(item.id)+"/enqueue",{method:"POST",body:{}});
    notice("Task admitted to the queue. Worker execution has not been started.");await refreshAll();
   });
  }
  if(item.state==="queued"&&item.assigned_agent_id&&item.assigned_role_key){
   actionButton(actions,"Run one task",async()=>{
    const result=await api("/workers/run-once",{method:"POST",body:{agent_id:item.assigned_agent_id,role_key:item.assigned_role_key}});
    notice("Worker result: "+result.status);await refreshAll();
   });
  }
  if(item.state==="review")actionButton(actions,"Review deliverable",()=>showTaskWorkflow(item,el("task-detail")));
  card.append(heading,meta,actions);root.append(card);
 });
}
function renderDepartments(items){
 const root=el("departments");root.replaceChildren();el("task-department").replaceChildren();
 items.forEach(d=>{const label=d.name||d.department;root.append(node("div",label+" · "+(d.department||""),"rowitem"));const o=document.createElement("option");o.value=d.department;o.textContent=label;el("task-department").append(o);});
}
function renderWorker(workers,service,queue,orchestration){
 const root=el("worker-status");root.replaceChildren();
 root.append(node("div","In-process fleet: "+(workers.running?"running":"stopped")+" · "+workers.execution_mode));
 root.append(node("div","Dedicated service instances: "+((service.worker_instances||[]).length)+" · single-instance mode"));
 root.append(node("div","Queue admission: owner-controlled · background loop: "+(workers.background_loop_enabled?"enabled":"disabled")));
 root.append(node("div","Draft tasks ready for advancement: "+((orchestration.eligible_to_advance||[]).length)));
 root.append(node("div","Blocked drafts: "+((orchestration.blocked_draft_items||[]).length)));
}
function renderUsage(usage){const root=el("usage");root.replaceChildren();root.append(node("h3","Model usage"));root.append(node("pre",JSON.stringify(usage,null,2),"muted"));}
function renderFinance(entries,budgets,reconciliations){
 const root=el("finance");root.replaceChildren();
 if(!entries.length)root.append(node("p","No finance entries recorded.","muted"));
 entries.slice().reverse().slice(0,20).forEach(x=>root.append(node("div",(x.entry_type||"")+" · "+x.amount_minor+" "+x.currency+" · "+x.business_id+" · "+(x.latest_review_action||"unreviewed"),"rowitem")));
 (budgets||[]).forEach(b=>{
  const row=node("div",undefined,"rowitem");
  const label=node("span",b.business_id+" · "+b.currency+" · monthly limit "+b.monthly_expense_limit_minor);
  const button=node("button","View month status");
  button.addEventListener("click",async()=>{try{const status=await api("/finance/budgets/status?business_id="+encodeURIComponent(b.business_id)+"&currency="+encodeURIComponent(b.currency));notice("Budget "+status.budget_status+": expenses "+status.expenses_minor+" / "+status.monthly_expense_limit_minor+" "+status.currency+" minor units. This does not authorize spending.");}catch(e){notice(e.message,true);}});
  row.append(label,button);root.append(row);
 });
 const history=el("reconciliation-list");history.replaceChildren();
 if(!(reconciliations||[]).length)history.append(node("p","No reconciliation records yet.","muted"));
 (reconciliations||[]).slice(0,20).forEach(r=>history.append(node("div",r.business_id+" · "+r.currency+" · "+r.status+" · difference "+r.difference_minor+" · "+r.period_start+" → "+r.period_end,"rowitem")));
}
async function refreshBusinessContext(){
 const business=el("memory-business").value;
 const [memory,integrations,credentials]=await Promise.all([
  api("/business-units/"+encodeURIComponent(business)+"/memory"),
  api("/business-units/"+encodeURIComponent(business)+"/integrations"),
  api("/business-units/"+encodeURIComponent(business)+"/credentials")
 ]);
 const memories=el("memory-list");memories.replaceChildren();
 if(!memory.memories.length)memories.append(node("p","No saved memories for this business unit.","muted"));
 memory.memories.forEach(item=>{
  const card=node("div",undefined,"rowitem");
  const left=node("div"),title=node("strong",item.memory_key+" · "+item.category),body=node("p",item.content,"muted"),source=node("p","Source: "+item.source+" · revision "+item.revision,"muted");
  left.append(title,body,source);
  const actions=node("div");const historyButton=node("button","History"),forgetButton=node("button","Forget");
  historyButton.addEventListener("click",async()=>{try{const history=await api("/business-units/"+encodeURIComponent(business)+"/memory/"+encodeURIComponent(item.memory_key)+"/history");const details=node("pre",JSON.stringify(history.history,null,2),"muted");card.append(details);}catch(e){notice(e.message,true);}});
  forgetButton.addEventListener("click",async()=>{if(!window.confirm("Deactivate this memory for "+business+"? Historical versions remain in the audit history."))return;try{await api("/business-units/"+encodeURIComponent(business)+"/memory/"+encodeURIComponent(item.memory_key),{method:"DELETE",body:{confirm_owner_forget:true}});notice("Memory deactivated. Historical versions are retained.");await refreshBusinessContext();}catch(e){notice(e.message,true);}});
  actions.append(historyButton,forgetButton);card.append(left,actions);memories.append(card);
 });
 const registry=el("integration-list");registry.replaceChildren();
 if(!integrations.integrations.length)registry.append(node("p","No integration registrations.","muted"));
 integrations.integrations.forEach(item=>{
  const card=node("div",undefined,"rowitem");
  const left=node("div"),title=node("strong",item.display_name+" · "+item.provider_key),meta=node("p",item.status+" · permissions: "+(item.permissions||[]).join(", ")+" · credential "+(item.credential_available?"available":"missing"),"muted");
  left.append(title,meta);const actions=node("div");
  const eventsButton=node("button","History");eventsButton.addEventListener("click",async()=>{try{const result=await api("/business-units/"+encodeURIComponent(business)+"/integrations/"+encodeURIComponent(item.integration_id)+"/events");card.append(node("pre",JSON.stringify(result.events,null,2),"muted"));}catch(e){notice(e.message,true);}});
  actions.append(eventsButton);
  if(item.status==="pending_review"){
   for(const decision of ["approve","reject"]){const button=node("button",decision==="approve"?"Approve":"Reject");button.addEventListener("click",async()=>{const rationale=window.prompt("Reason for "+decision+"ing this integration permission request:");if(!rationale||!rationale.trim())return;try{const result=await api("/business-units/"+encodeURIComponent(business)+"/integrations/"+encodeURIComponent(item.integration_id)+"/review",{method:"POST",body:{decision,rationale,confirm_owner_decision:true}});notice("Integration "+result.status+". External connection remains disabled.");await refreshBusinessContext();}catch(e){notice(e.message,true);}});actions.append(button);}
  }
  card.append(left,actions);registry.append(card);
 });
 const refs=el("credential-list");refs.replaceChildren();
 if(!credentials.credentials.length)refs.append(node("p","No stored credential references.","muted"));
 credentials.credentials.forEach(item=>refs.append(node("div",item.credential_key+" · stored "+(item.created_at||"date unavailable"),"rowitem")));
}
async function bootstrap(path){try{const r=await api(path,{method:"POST",body:{}});notice("Provisioning complete: "+(r.count??"done")+" profiles. They remain draft until activated.");await refreshAll();}catch(e){notice(e.message,true);}}
async function createTask(event){event.preventDefault();try{const r=await api("/work-items",{method:"POST",body:{title:el("task-title").value,objective:el("task-objective").value,business_id:el("task-business").value,department:el("task-department").value}});el("task-form").reset();notice("Draft work item created: "+r.id+". No execution was started.");await refreshAll();}catch(e){notice(e.message,true);}}
el("login-form").addEventListener("submit",signIn);el("logout").addEventListener("click",signOut);el("refresh").addEventListener("click",refreshAll);el("task-form").addEventListener("submit",createTask);
el("bootstrap-ceo").addEventListener("click",()=>bootstrap("/agents/bootstrap-executive"));
el("bootstrap-managers").addEventListener("click",()=>bootstrap("/agents/bootstrap"));
el("bootstrap-specialists").addEventListener("click",()=>bootstrap("/agents/bootstrap-specialists"));
el("ceo-cycle").addEventListener("click",async()=>{try{const result=await api("/executive/orchestration/cycle",{method:"POST",body:{}});notice("CEO cycle: "+(result.delegations.drafted_count||0)+" delegation proposals drafted; "+result.readiness.advanced_count+" work items advanced. Owner approval remains required; nothing was queued or executed.");await refreshAll();}catch(e){notice(e.message,true);}});
el("advance-work").addEventListener("click",async()=>{try{const result=await api("/executive/orchestration/advance",{method:"POST",body:{}});notice("CEO readiness pass: "+result.advanced_count+" work items advanced. Queue admission and execution were not started.");await refreshAll();}catch(e){notice(e.message,true);}});
el("worker-start").addEventListener("click",async()=>{try{const result=await api("/workers/start",{method:"POST",body:{}});notice(result.running?"Worker started. It can process only owner-admitted tasks through a confirmed zero-cost provider.":"Worker did not start.");await refreshAll();}catch(e){notice(e.message,true);}});
el("worker-stop").addEventListener("click",async()=>{try{const result=await api("/workers/stop",{method:"POST",body:{}});notice(result.running?"Worker remains running.":"Worker stopped.");await refreshAll();}catch(e){notice(e.message,true);}});
el("memory-business").addEventListener("change",()=>refreshBusinessContext().catch(e=>notice(e.message,true)));
el("budget-form").addEventListener("submit",async event=>{event.preventDefault();try{const result=await api("/finance/budgets",{method:"POST",body:{business_id:el("budget-business").value,currency:el("budget-currency").value,monthly_expense_limit_minor:Number(el("budget-limit").value),rationale:el("budget-rationale").value,confirm_owner_budget:el("budget-confirm").checked}});notice("Budget limit saved for "+result.business_id+". It does not authorize spending.");el("budget-form").reset();await refreshAll();}catch(e){notice(e.message,true);}});
el("reconciliation-form").addEventListener("submit",async event=>{event.preventDefault();try{const iso=v=>new Date(v).toISOString();const result=await api("/finance/reconciliations",{method:"POST",body:{business_id:el("recon-business").value,currency:el("recon-currency").value,period_start:iso(el("recon-start").value),period_end:iso(el("recon-end").value),opening_balance_minor:Number(el("recon-opening").value),statement_closing_minor:Number(el("recon-closing").value),confirm_owner_reconciliation:el("recon-confirm").checked}});notice("Reconciliation result: "+result.status+" · difference "+result.difference_minor+" "+result.currency+" minor units. No bank connection or funds movement occurred.");el("reconciliation-form").reset();await refreshAll();}catch(e){notice(e.message,true);}});
el("integration-form").addEventListener("submit",async event=>{event.preventDefault();try{const permissions=el("integration-permissions").value.split(",").map(x=>x.trim()).filter(Boolean);const business=el("memory-business").value;const result=await api("/business-units/"+encodeURIComponent(business)+"/integrations",{method:"POST",body:{provider_key:el("integration-provider").value,display_name:el("integration-name").value,credential_key:el("integration-credential").value,permissions,rationale:el("integration-rationale").value,confirm_owner_registration:el("integration-confirm").checked}});notice("Integration registration saved as "+result.integration.status+". No external connection was attempted.");el("integration-form").reset();await refreshBusinessContext();}catch(e){notice(e.message,true);}});

el("memory-form").addEventListener("submit",async event=>{event.preventDefault();try{const business=el("memory-business").value;await api("/business-units/"+encodeURIComponent(business)+"/memory",{method:"POST",body:{memory_key:el("memory-key").value,category:el("memory-category").value,source:el("memory-source").value,content:el("memory-content").value,confirm_owner_write:el("memory-confirm").checked}});el("memory-form").reset();notice("Owner-written memory saved within "+business+". Agent writes remain disabled.");await refreshBusinessContext();}catch(e){notice(e.message,true);}});
checkSession();
})();
</script></body></html>""".replace("__NONCE__",nonce)
    return HTMLResponse(page)

@app.post("/auth/session")
def login(payload:SessionInput,request:Request,response:Response):
    expected=os.getenv("OPENCOMPANY_OWNER_API_KEY")
    if not expected:raise HTTPException(503,"Owner authentication is not configured.")
    client=request.client.host if request.client else "unknown"
    failures=_prune(_login_failures[client])
    if len(failures)>=4:raise HTTPException(429,"Too many failed login attempts.",headers={"Retry-After":"60"})
    if not secrets.compare_digest(payload.api_key,expected):
        failures.append(time.time());raise HTTPException(401,"Invalid owner credentials.")
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
    _sessions[token]={"csrf":csrf,"expires":time.time()+604800}
    response.set_cookie("opencompany_session",token,max_age=604800,httponly=True,secure=True,samesite="strict",path="/")
    response.set_cookie("opencompany_csrf",csrf,max_age=604800,httponly=True,secure=True,samesite="strict",path="/")
    return {"authenticated":True,"csrf_token":csrf}

@app.get("/auth/session")
def session_status(request:Request):
    token=request.cookies.get("opencompany_session");session=_sessions.get(token or "")
    if not session or session["expires"]<=time.time():raise HTTPException(401,"Session expired.")
    return {"authenticated":True,"csrf_token":session["csrf"]}

@app.post("/auth/logout")
def logout(request:Request,owner=Depends(_owner),response:Response=None):
    token=request.cookies.get("opencompany_session");_sessions.pop(token or "",None)
    response.delete_cookie("opencompany_session",path="/");response.delete_cookie("opencompany_csrf",path="/")
    return {"authenticated":False}

@app.get("/workforce/roles")
def workforce_roles():
    return {"catalogue":"opencompany-original","count":len(ROLE_CATALOGUE),"specialist_count":500,"leadership_role_count":11,"team_count":100,"roles":ROLE_CATALOGUE}

@app.get("/organization/departments")
def organization_departments():
    return {"catalogue":"opencompany-original","count":len(DEPARTMENT_CATALOGUE),"departments":DEPARTMENT_CATALOGUE}

@app.post("/workforce/route-preview")
def route_preview(payload:dict):
    dept=payload.get("department")
    if dept not in {d[0] for d in DEPARTMENTS}:raise HTTPException(422,"Unknown department.")
    required=[str(x).lower() for x in payload.get("required_capabilities",[])]
    limit=max(1,min(int(payload.get("limit",5)),50))
    candidates=[r for r in ROLE_CATALOGUE if r["department"]==dept and r["kind"]=="specialist" and all(any(term in c.lower() for c in r["capabilities"]+[r["title"].lower()]) for term in required)]
    return {"candidate_count":len(candidates),"candidates":candidates[:limit],"assignment_performed":False,"execution_started":False}

@app.post("/plans/preview")
def plan_preview(payload:dict):
    items=payload.get("items",[])
    ids=[str(x.get("id")) for x in items]
    if len(ids)!=len(set(ids)):raise HTTPException(422,"Duplicate plan item IDs.")
    known={d[0] for d in DEPARTMENTS}
    graph={}
    for item in items:
        if item.get("department") not in known:raise HTTPException(422,"Unknown department.")
        deps=[str(x) for x in item.get("depends_on",[])]
        if any(x not in ids for x in deps):raise HTTPException(422,"Unknown dependency.")
        graph[str(item["id"])]=deps
    visiting=set();visited=set()
    def visit(node):
        if node in visiting:raise HTTPException(422,"Dependency cycle detected.")
        if node in visited:return
        visiting.add(node)
        for dep in graph[node]:visit(dep)
        visiting.remove(node);visited.add(node)
    for node in graph:visit(node)
    blocked=[];ready=[]
    state={str(x["id"]):x.get("state","ready") for x in items}
    for item in items:
        deps=graph[str(item["id"])]
        if any(state.get(dep)!="completed" for dep in deps):blocked.append({"id":str(item["id"]),"depends_on":deps})
        elif item.get("state","ready")=="ready":ready.append(str(item["id"]))
    return {"ready_item_ids":ready,"blocked_items":blocked,"execution_performed":False}

@app.get("/providers/status")
def provider_status():
    out={}
    for name,prefix in (("unorouter","UNOROUTER"),("openrouter","OPENROUTER")):
        key=os.getenv(f"OPENCOMPANY_{prefix}_API_KEY")
        model=os.getenv(f"OPENCOMPANY_{prefix}_FREE_MODEL")
        confirmed=os.getenv(f"OPENCOMPANY_CONFIRM_{prefix}_FREE","").lower()=="true"
        out[name]={"configured":bool(key and model and confirmed),"partial_configuration_detected":bool(key or model),"model":model if key and model and confirmed else None,"billing_mode":"free_confirmed" if key and model and confirmed else "disabled"}
    enabled=any(x["configured"] for x in out.values())
    selected="unorouter" if out["unorouter"]["configured"] else "openrouter" if out["openrouter"]["configured"] else None
    return {"gateway_enabled":enabled,"partial_configuration_detected":any(x["partial_configuration_detected"] for x in out.values()),"provider":selected,"providers":out,"billing_mode":"free_confirmed" if enabled else "disabled","paid_fallback":False,"real_inference_verified":False}

@app.get("/providers/candidates")
def provider_candidates():return {"gateway_enabled":False,"candidates":[{"provider":"unorouter","configured":False},{"provider":"openrouter","configured":False}]}

@app.get("/media/capabilities")
def media_capabilities():return {"capabilities":[{"key":"longcat-video","state":"researched_not_connected"}]}

def discover_free_models(api_key,force_refresh=False):return []

@app.post("/settings/providers/unorouter/discover")
def unorouter_discover(payload:dict,owner=Depends(_owner)):
    models=discover_free_models(payload.get("api_key",""))
    models=[m for m in models if str(m.get("id","")).endswith(":free")]
    return {"count":len(models),"models":models,"paid_models_included":False}

@app.put("/settings/providers/unorouter")
def save_unorouter(payload:dict,owner=Depends(_owner)):
    if not payload.get("confirm_free"):raise HTTPException(422,"Owner free-tier confirmation is required.")
    models=discover_free_models(payload.get("api_key",""))
    if not any(m.get("id")==payload.get("model") for m in models):raise HTTPException(409,"Model must be revalidated against the current free catalogue.")
    return {"configured":False,"saved":False,"paid_fallback":False}
@app.get("/settings/providers/unorouter")
def get_unorouter(owner=Depends(_owner)):return {"configured":False}

@app.post("/settings/providers/unorouter/test")
def start_unorouter_test(runtime=Depends(get_runtime),owner=Depends(_owner)):
    job_id=str(uuid4())
    runtime.unorouter_tested_at=None
    try:
        if hasattr(runtime.gateway,"set_usage_recorder"):
            runtime.gateway.set_usage_recorder(runtime.usage.record)
        result=runtime.gateway.generate(
            {"task":"verify_zero_cost_provider","prompt":"Reply exactly OPENCOMPANY_UNOROUTER_OK."},
            request_budget_usd=0.0,
        )
        if result.cost_usd!=0.0:
            raise RuntimeError("Provider returned a non-zero cost.")
        runtime.unorouter_tested_at=datetime.now(timezone.utc).isoformat()
        job={
            "status":"succeeded","success":True,"provider":result.provider,"model":result.model,
            "cost_usd":result.cost_usd,"output_preview":result.text[:160],
            "worker_autostart_enabled":os.getenv("OPENCOMPANY_WORKER_AUTOSTART","false").lower()=="true",
            "worker_started":runtime.fleet.status().running,"paid_fallback":False,
        }
    except Exception as exc:
        job={
            "status":"failed","success":False,
            "error":"UnoRouter test failed safely: "+str(exc),
            "paid_fallback":False,"worker_autostart_enabled":os.getenv("OPENCOMPANY_WORKER_AUTOSTART","false").lower()=="true",
            "worker_started":runtime.fleet.status().running,
        }
    runtime.provider_test_jobs[job_id]=job
    return Response(
        content=json.dumps({"job_id":job_id}),status_code=202,
        media_type="application/json",
    )


@app.get("/settings/providers/unorouter/test/{job_id}")
def get_unorouter_test(job_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    job=runtime.provider_test_jobs.get(job_id)
    if not job:raise HTTPException(404,"Provider test job not found.")
    return job


@app.get("/settings/providers/unorouter/models")
def get_unorouter_models(runtime=Depends(get_runtime),owner=Depends(_owner)):
    saved=runtime.secret_vault.get("unorouter")
    api_key=saved.get("api_key") if isinstance(saved,dict) else None
    models=discover_free_models(api_key,force_refresh=True) if api_key else ()
    free_models=sorted({
        str(value.get("id")) if isinstance(value,dict) else str(value)
        for value in models
        if (str(value.get("id","")) if isinstance(value,dict) else str(value)).endswith(":free")
    })
    return {
        "routing_mode":"automatic_all_free_models","models":free_models,
        "paid_fallback":False,"configured":bool(api_key),
    }


@app.post("/business-units/{business_id}/credentials")
def store_business_credential(business_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    key=str(payload.get("credential_key","")).strip()
    secret=payload.get("secret")
    if payload.get("confirm_owner_storage") is not True:
        raise HTTPException(422,"Owner confirmation is required to store a business credential.")
    if not key or len(key)>100 or not all(ch.isalnum() or ch in "._-" for ch in key):
        raise HTTPException(422,"Credential key is invalid.")
    if not isinstance(secret,dict) or not secret:
        raise HTTPException(422,"Credential secret must be a non-empty object.")
    try:
        encrypted=_business_fernet().encrypt(json.dumps(secret,sort_keys=True).encode("utf-8")).decode("ascii")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422,"Credential could not be encrypted.") from exc
    record=runtime.business.put_credential(business_id,key,encrypted)
    return {"credential":{"business_id":business_id,"credential_key":key,"created_at":record["created_at"]},
            "stored":True,"external_connection_attempted":False}


@app.get("/business-units/{business_id}/credentials")
def list_business_credentials(business_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    credentials=runtime.business.list_credentials(business_id)
    return {"count":len(credentials),"credentials":credentials}


@app.delete("/business-units/{business_id}/credentials/{credential_key}")
def delete_business_credential(business_id:str,credential_key:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    if payload.get("confirm_owner_deletion") is not True:
        raise HTTPException(422,"Owner confirmation is required to delete a credential.")
    deleted=runtime.business.delete_credential(business_id,credential_key)
    if not deleted:raise HTTPException(404,"Business credential not found.")
    return {"deleted":True,"business_id":business_id,"credential_key":credential_key,"external_connection_attempted":False}


@app.post("/business-units/{business_id}/integrations")
def register_business_integration(business_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    if payload.get("confirm_owner_registration") is not True:
        raise HTTPException(422,"Owner confirmation is required to register an integration.")
    provider_key=str(payload.get("provider_key","")).strip()
    display_name=str(payload.get("display_name","")).strip()
    credential_key=str(payload.get("credential_key","")).strip()
    permissions=payload.get("permissions",[])
    rationale=str(payload.get("rationale","")).strip()
    if not provider_key or not display_name or not credential_key or not rationale:
        raise HTTPException(422,"Integration metadata and rationale are required.")
    if not isinstance(permissions,list) or not permissions or not all(isinstance(x,str) and x.strip() for x in permissions):
        raise HTTPException(422,"At least one explicit integration permission is required.")
    if not runtime.business.has_credential(business_id,credential_key):
        raise HTTPException(409,"The integration credential must exist in this business unit.")
    integration={
        "integration_id":str(uuid4()),"business_id":business_id,"provider_key":provider_key,
        "display_name":display_name,"credential_key":credential_key,"permissions":permissions,
        "rationale":rationale[:1200],"status":"pending_review",
        "created_at":datetime.now(timezone.utc).isoformat(),
    }
    runtime.business.add_integration(integration)
    return {"integration":integration,"external_connection_attempted":False}


@app.get("/business-units/{business_id}/integrations")
def list_business_integrations(business_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    integrations=runtime.business.list_integrations(business_id)
    return {"count":len(integrations),"integrations":integrations,"external_connections_enabled":False}


@app.get("/business-units/{business_id}/integrations/{integration_id}/events")
def business_integration_events(business_id:str,integration_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    events=runtime.business.integration_events(business_id,integration_id)
    if events is None:raise HTTPException(404,"Business integration not found.")
    return {"count":len(events),"events":events}


@app.post("/business-units/{business_id}/integrations/{integration_id}/review")
def review_business_integration(business_id:str,integration_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    if payload.get("confirm_owner_decision") is not True:
        raise HTTPException(422,"Owner confirmation is required to review an integration.")
    decision=str(payload.get("decision",""))
    rationale=str(payload.get("rationale","")).strip()
    if decision not in ("approve","reject"):
        raise HTTPException(422,"Integration decision must be approve or reject.")
    if not rationale:
        raise HTTPException(422,"A review rationale is required.")
    try:
        result=runtime.business.review_integration(business_id,integration_id,decision,rationale)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc
    if result is None:
        raise HTTPException(404,"Business integration not found.")
    return result


@app.post("/business-units/{business_id}/memory")
def save_business_memory(business_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    if payload.get("confirm_owner_write") is not True:
        raise HTTPException(422,"Owner confirmation is required to write business memory.")
    memory_key=str(payload.get("memory_key","")).strip()
    category=str(payload.get("category","")).strip()
    content=str(payload.get("content","")).strip()
    source=str(payload.get("source","")).strip()
    if not memory_key or not category or not content or not source:
        raise HTTPException(422,"Memory key, category, content, and source are required.")
    memory=runtime.business.save_memory(business_id,{
        "memory_key":memory_key,"category":category,"content":content,"source":source,
    })
    return {"memory":memory,"agent_writes_enabled":False}


@app.get("/business-units/{business_id}/memory")
def list_business_memory(business_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    memories=runtime.business.list_memory(business_id)
    return {"count":len(memories),"memories":memories,"agent_writes_enabled":False}


@app.get("/business-units/{business_id}/memory/{memory_key}/history")
def business_memory_history(business_id:str,memory_key:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    history=runtime.business.memory_history(business_id,memory_key)
    return {"count":len(history),"history":history}


@app.delete("/business-units/{business_id}/memory/{memory_key}")
def forget_business_memory(business_id:str,memory_key:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    if payload.get("confirm_owner_forget") is not True:
        raise HTTPException(422,"Owner confirmation is required to forget business memory.")
    forgotten=runtime.business.forget_memory(business_id,memory_key)
    if not forgotten:raise HTTPException(404,"Active business memory not found.")
    return {"forgotten":True,"historical_versions_retained":True,"agent_writes_enabled":False}


def _public_asset(asset):
    allowed=("asset_id","business_id","asset_key","title","asset_type","filename","media_type",
             "checksum_sha256","byte_size","source","storage_state","status","file_bytes_received","created_at")
    return {key:asset[key] for key in allowed if key in asset}


@app.post("/business-units/{business_id}/assets")
def declare_business_asset(business_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    if payload.get("confirm_owner_declaration") is not True:
        raise HTTPException(422,"Owner confirmation is required to declare a business asset.")
    try:
        asset=runtime.asset_registry.declare(
            business_id,asset_key=payload.get("asset_key"),title=payload.get("title"),
            asset_type=payload.get("asset_type"),filename=payload.get("filename"),
            media_type=payload.get("media_type"),checksum_sha256=payload.get("checksum_sha256"),
            byte_size=payload.get("byte_size"),source=payload.get("source"),
            audit=_audit("asset.declared",uuid4(),"owner"),
        )
    except (ValueError,PermissionError) as exc:
        raise HTTPException(422,str(exc)) from exc
    return {"asset":_public_asset(asset),"file_bytes_received":False,"message":"Asset declared. No file was uploaded."}


@app.get("/business-units/{business_id}/assets")
def list_business_assets(business_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    assets=[_public_asset(asset) for asset in runtime.asset_registry.list(business_id)]
    return {"count":len(assets),"assets":assets,"download_enabled":False}


@app.get("/business-units/{business_id}/assets/{asset_id}/events")
def business_asset_events(business_id:str,asset_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    try:
        events=runtime.asset_registry.events(business_id,asset_id)
    except ValueError as exc:
        raise HTTPException(404,"Business asset not found.") from exc
    if not events:raise HTTPException(404,"Business asset not found.")
    return {"count":len(events),"events":events}


@app.get("/business-units/{business_id}/assets/{asset_id}/scan-events")
def business_asset_scan_events(business_id:str,asset_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    try:
        events=runtime.asset_registry.scan_events(business_id,asset_id)
    except ValueError as exc:
        raise HTTPException(404,"Business asset not found.") from exc
    return {"count":len(events),"events":events}


@app.put("/business-units/{business_id}/assets/{asset_id}/content")
async def upload_business_asset_content(business_id:str,asset_id:str,request:Request,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    if request.headers.get("x-confirm-owner-upload","").lower()!="true":
        raise HTTPException(422,"Explicit owner confirmation is required before uploading asset bytes.")
    if runtime.asset_storage is None:
        raise HTTPException(503,"Private asset storage is not configured.")
    try:
        declaration=runtime.asset_registry.storage_declaration(business_id,asset_id)
        stored=await runtime.asset_storage.store_stream(
            business_id=declaration["business_id"],asset_scope_id=declaration["asset_scope_id"],
            asset_id=declaration["asset_id"],expected_sha256=declaration["checksum_sha256"],
            expected_size=declaration["byte_size"],chunks=request.stream(),
            expected_media_type=declaration["media_type"],
        )
        try:
            asset=runtime.asset_registry.record_storage(
                business_id,asset_id,storage_key=stored["storage_key"],
                checksum_sha256=stored["checksum_sha256"],byte_size=stored["byte_size"],
                audit=_audit("asset.stored",UUID(asset_id),"owner"),
            )
        except Exception:
            runtime.asset_storage.discard_uncommitted(
                business_id=business_id,asset_scope_id=declaration["asset_scope_id"],
                asset_id=asset_id,storage_key=stored["storage_key"],
            )
            raise
    except AssetStorageError as exc:
        detail=str(exc)
        if "declared size" in detail or "checksum" in detail:
            detail="Uploaded asset size or checksum does not match its owner declaration."
        raise HTTPException(422,detail) from exc
    except ValueError as exc:
        status=409 if "already" in str(exc) else 422
        raise HTTPException(status,str(exc)) from exc
    return {
        "asset":_public_asset(asset),"checksum_verified":True,
        "malware_scan_completed":False,"download_enabled":False,
    }


@app.post("/business-units/{business_id}/assets/{asset_id}/scan")
def scan_business_asset(business_id:str,asset_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=_business_id(business_id)
    if payload.get("confirm_owner_scan") is not True:
        raise HTTPException(422,"Owner confirmation is required before scanning this asset.")
    if runtime.asset_storage is None or runtime.asset_scanner is None:
        raise HTTPException(503,"Private storage and a local ClamAV scanner must both be configured.")
    try:
        declaration=runtime.asset_registry.scan_declaration(business_id,asset_id)
        result=runtime.asset_scanner.scan(runtime.asset_storage.read_chunks(declaration["storage_key"]))
        if result["checksum_sha256"]!=declaration["checksum_sha256"] or result["byte_size"]!=declaration["byte_size"]:
            raise HTTPException(409,"Scanned bytes do not match the stored asset declaration.")
        asset=runtime.asset_registry.record_scan_result(
            business_id,asset_id,scanner_key=result["scanner_key"],status=result["status"],
            checksum_sha256=result["checksum_sha256"],byte_size=result["byte_size"],
            verdict=result["verdict"],audit=_audit("asset.scan",UUID(asset_id),"system"),
        )
    except AssetScanError as exc:
        raise HTTPException(503,"Malware scanner could not provide a definitive verdict; asset remains unavailable.") from exc
    except AssetStorageError as exc:
        raise HTTPException(503,"Private asset could not be read safely for scanning.") from exc
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc
    return {
        "asset":_public_asset(asset),"scan_status":result["status"],
        "malware_scan_completed":True,"download_enabled":False,
        "delivery_approval_required":result["status"]=="clean",
    }


@app.post("/finance/entries")
def create_finance_entry(payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=str(payload.get("business_id",""))
    entry_type=str(payload.get("entry_type",""))
    amount=payload.get("amount_minor")
    currency=str(payload.get("currency","")).upper()
    description=str(payload.get("description","")).strip()
    if business_id not in ("physical-agency","physical-brand","digital-products"):
        raise HTTPException(422,"Unknown business unit.")
    if entry_type not in ("expense","revenue"):
        raise HTTPException(422,"Finance entry type must be expense or revenue.")
    if not isinstance(amount,int) or isinstance(amount,bool) or amount<=0:
        raise HTTPException(422,"Amount must be a positive integer in minor currency units.")
    if len(currency)!=3 or not currency.isalpha() or not description:
        raise HTTPException(422,"A three-letter currency and description are required.")
    if payload.get("confirm_owner_record") is not True:
        raise HTTPException(422,"Owner confirmation is required to record a finance entry.")
    entry={
        "id":str(uuid4()),"business_id":business_id,"entry_type":entry_type,
        "amount_minor":amount,"currency":currency,"description":description[:1000],
        "recorded_at":datetime.now(timezone.utc).isoformat(),
    }
    runtime.finance.create_entry(entry)
    return {**entry,"entry_id":entry["id"],"recorded":True,"external_payment_initiated":False,"spending_authorized":False}


@app.post("/finance/entries/{entry_id}/review")
def review_finance_entry(entry_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    entry=runtime.finance.get_entry(entry_id)
    if not entry:raise HTTPException(404,"Finance entry not found.")
    if payload.get("confirm_owner_decision") is not True:
        raise HTTPException(422,"Owner confirmation is required for a finance review decision.")
    action=str(payload.get("action",""))
    if action not in ("owner_approved","owner_rejected","owner_verified"):
        raise HTTPException(422,"Unsupported finance review action.")
    rationale=str(payload.get("rationale","")).strip()
    if not rationale:raise HTTPException(422,"A review rationale is required.")
    review={
        "id":str(uuid4()),"entry_id":entry_id,"action":action,
        "rationale":rationale[:1200],"created_at":datetime.now(timezone.utc).isoformat(),
    }
    if not runtime.finance.save_review(review):
        raise HTTPException(422,"A finance entry can receive only one owner review decision.")
    return {**review,"external_payment_initiated":False,"spending_authorized":False}


@app.get("/finance/entries")
def list_finance_entries(business_id:str|None=None,runtime=Depends(get_runtime),owner=Depends(_owner)):
    if business_id and business_id not in ("physical-agency","physical-brand","digital-products"):
        raise HTTPException(422,"Unknown business unit.")
    entries=runtime.finance.list_entries(business_id)
    return {"count":len(entries),"entries":entries,"external_payment_initiated":False}


@app.post("/finance/budgets")
def set_finance_budget(payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=str(payload.get("business_id",""))
    currency=str(payload.get("currency","")).upper()
    limit=payload.get("monthly_expense_limit_minor")
    if business_id not in ("physical-agency","physical-brand","digital-products"):
        raise HTTPException(422,"Unknown business unit.")
    if len(currency)!=3 or not currency.isalpha():
        raise HTTPException(422,"A three-letter currency is required.")
    if not isinstance(limit,int) or isinstance(limit,bool) or limit<0:
        raise HTTPException(422,"Monthly budget must be a non-negative integer in minor currency units.")
    if payload.get("confirm_owner_budget") is not True:
        raise HTTPException(422,"Owner confirmation is required to set a budget.")
    rationale=str(payload.get("rationale","")).strip()
    if not rationale:
        raise HTTPException(422,"A rationale is required for the budget decision.")
    record=runtime.finance.set_budget(business_id,currency,limit,rationale)
    return {**record,"spending_authorized":False,"automatic_spend_blocking":False}


@app.get("/finance/budgets")
def list_finance_budgets(business_id:str|None=None,runtime=Depends(get_runtime),owner=Depends(_owner)):
    if business_id and business_id not in ("physical-agency","physical-brand","digital-products"):
        raise HTTPException(422,"Unknown business unit.")
    budgets=runtime.finance.list_budgets(business_id)
    return {"count":len(budgets),"budgets":budgets,"spending_authorized":False}


@app.get("/finance/budgets/history")
def finance_budget_history(business_id:str|None=None,runtime=Depends(get_runtime),owner=Depends(_owner)):
    if business_id and business_id not in ("physical-agency","physical-brand","digital-products"):
        raise HTTPException(422,"Unknown business unit.")
    events=runtime.finance.list_budget_events(business_id)
    return {"count":len(events),"events":events,"spending_authorized":False}


@app.get("/finance/budgets/status")
def finance_budget_status(business_id:str,currency:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    if business_id not in ("physical-agency","physical-brand","digital-products"):
        raise HTTPException(422,"Unknown business unit.")
    currency=currency.upper()
    if len(currency)!=3 or not currency.isalpha():
        raise HTTPException(422,"A three-letter currency is required.")
    now=datetime.now(timezone.utc)
    start=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0).isoformat()
    status=runtime.finance.budget_status(business_id,currency,start,now.isoformat())
    return status


@app.post("/finance/reconciliations")
def create_finance_reconciliation(payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    business_id=str(payload.get("business_id",""))
    currency=str(payload.get("currency","")).upper()
    period_start=str(payload.get("period_start",""))
    period_end=str(payload.get("period_end",""))
    opening=payload.get("opening_balance_minor")
    closing=payload.get("statement_closing_minor")
    if business_id not in ("physical-agency","physical-brand","digital-products"):
        raise HTTPException(422,"Unknown business unit.")
    if len(currency)!=3 or not currency.isalpha():
        raise HTTPException(422,"A three-letter currency is required.")
    try:
        start_dt=datetime.fromisoformat(period_start)
        end_dt=datetime.fromisoformat(period_end)
    except (TypeError,ValueError):
        raise HTTPException(422,"Period start and end must be ISO-8601 timestamps.")
    if start_dt.tzinfo is None or end_dt.tzinfo is None or end_dt<start_dt:
        raise HTTPException(422,"Reconciliation period must be timezone-aware and end after it starts.")
    period_start=start_dt.astimezone(timezone.utc).isoformat()
    period_end=end_dt.astimezone(timezone.utc).isoformat()
    if not isinstance(opening,int) or isinstance(opening,bool) or not isinstance(closing,int) or isinstance(closing,bool):
        raise HTTPException(422,"Opening and statement closing balances must be integer minor currency units.")
    if payload.get("confirm_owner_reconciliation") is not True:
        raise HTTPException(422,"Owner confirmation is required to record a reconciliation.")
    movement=runtime.finance.calculate_ledger_movement(business_id,currency,period_start,period_end)
    expected=opening+movement
    difference=closing-expected
    record={
        "id":str(uuid4()),"business_id":business_id,"currency":currency,
        "period_start":period_start,"period_end":period_end,
        "opening_balance_minor":opening,"statement_closing_minor":closing,
        "ledger_movement_minor":movement,"expected_closing_minor":expected,
        "difference_minor":difference,"status":"balanced" if difference==0 else "discrepancy",
        "created_at":datetime.now(timezone.utc).isoformat(),
    }
    runtime.finance.create_reconciliation(record)
    return {**record,"bank_connection_attempted":False,"funds_moved":False}


@app.get("/finance/reconciliations")
def list_finance_reconciliations(business_id:str|None=None,runtime=Depends(get_runtime),owner=Depends(_owner)):
    if business_id and business_id not in ("physical-agency","physical-brand","digital-products"):
        raise HTTPException(422,"Unknown business unit.")
    records=runtime.finance.list_reconciliations(business_id)
    return {"count":len(records),"reconciliations":records,"bank_connection_attempted":False}


@app.get("/usage/model")
def model_usage(runtime=Depends(get_runtime),owner=Depends(_owner)):return runtime.usage.summary()

@app.get("/workers/status")
def workers_status(runtime=Depends(get_runtime),owner=Depends(_owner)):
    status=runtime.fleet.status();return {"running":status.running,"worker_count":status.worker_count,"execution_mode":"owner_triggered_single_task","background_loop_enabled":False}
@app.get("/workers/service-status")
def workers_service_status(runtime=Depends(get_runtime),owner=Depends(_owner)):
    now=datetime.now(timezone.utc)
    instances=[]
    for record in runtime.worker_presence.list_instances():
        last=datetime.fromisoformat(record["last_seen_at"])
        if last.tzinfo is None:
            last=last.replace(tzinfo=timezone.utc)
        age=max(0,int((now-last).total_seconds()))
        instances.append({**record,"heartbeat_age_seconds":age,
                          "stale":record["state"]=="running" and age>30})
    return {"worker_instances":instances,"single_instance_mode":True,
            "multi_replica_supported":False}


@app.get("/workers/queue")
def workers_queue(runtime=Depends(get_runtime),owner=Depends(_owner)):
    counts=runtime.queue.counts();return {"counts":counts,"total":sum(counts.values())}
@app.post("/workers/start")
def workers_start(runtime=Depends(get_runtime),owner=Depends(_owner)):
    if not runtime.gateway.eligible_providers(request_budget_usd=0.0):raise HTTPException(503,"No confirmed zero-cost provider is ready.")
    return {"running":runtime.fleet.start().running,"execution_mode":"owner_triggered_single_task","background_loop_enabled":False}
@app.post("/workers/stop")
def workers_stop(runtime=Depends(get_runtime),owner=Depends(_owner)):return {"running":runtime.fleet.stop().running,"execution_mode":"owner_triggered_single_task","background_loop_enabled":False}

@app.post("/workers/run-once")
def workers_run_once(payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    if not runtime.fleet.status().running:
        raise HTTPException(409,"Workers must be explicitly started before executing queued work.")
    if not runtime.gateway.eligible_providers(request_budget_usd=0.0):
        raise HTTPException(503,"No confirmed zero-cost provider is ready.")
    agent_id=payload.get("agent_id")
    role_key=payload.get("role_key")
    if not isinstance(agent_id,str) or not isinstance(role_key,str) or not role_key.strip():
        raise HTTPException(422,"An active specialist agent ID and role key are required.")
    agent=next((value for value in runtime.agents.values() if value.get("id")==agent_id),None)
    if not agent or agent.get("state")!="active" or agent.get("role_key")!=role_key:
        raise HTTPException(409,"The selected specialist must be active and match the requested role.")
    try:
        result=runtime.worker.run_once(UUID(agent_id),role_key)
    except (ProviderUnavailable,ValueError) as exc:
        raise HTTPException(503,"Specialist execution failed safely: "+str(exc)) from exc
    return {"status":result,"execution_mode":"single_task_owner_triggered","background_loop_enabled":False}



@app.post("/agents/bootstrap")
def bootstrap_agents(runtime=Depends(get_runtime),owner=Depends(_owner)):
    for role in ROLE_CATALOGUE:
        if role["kind"]=="leadership" and role["role_key"]!="chief_executive_orchestrator":
            runtime.agents.setdefault(role["role_key"],_agent(role))
    agents=[a for a in runtime.agents.values() if a["kind"]=="leadership" and a["role_key"]!="chief_executive_orchestrator"]
    return {"count":len(agents),"all_draft":True,"execution_started":False}
@app.post("/agents/bootstrap-specialists")
def bootstrap_specialists(runtime=Depends(get_runtime),owner=Depends(_owner)):
    for role in ROLE_CATALOGUE:
        if role["kind"]=="specialist":runtime.agents.setdefault(role["role_key"],_agent(role))
    return {"count":500,"all_draft":True,"execution_started":False}
@app.post("/agents/bootstrap-executive")
def bootstrap_executive(runtime=Depends(get_runtime),owner=Depends(_owner)):
    role=next(r for r in ROLE_CATALOGUE if r["role_key"]=="chief_executive_orchestrator")
    agent=runtime.agents.setdefault(role["role_key"],_agent(role))
    return {"count":1,"agent":agent,"execution_started":False}
def _agent(role):
    return {"id":str(uuid4()),"role_key":role["role_key"],"name":role["title"],"title":role["title"],"department":role["department"],"team_key":role["team_key"],"capabilities":role["capabilities"],"state":"draft","revision":1,"kind":role["kind"]}
@app.get("/agents")
def list_agents(runtime=Depends(get_runtime),owner=Depends(_owner)):
    agents=list(runtime.agents.values());return {"count":len(agents),"agents":agents}
@app.post("/agents/{agent_id}/state")
def agent_state(agent_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    agent=next((a for a in runtime.agents.values() if a["id"]==agent_id),None)
    if not agent:raise HTTPException(404,"Agent not found.")
    if payload.get("expected_revision")!=agent["revision"]:raise HTTPException(409,"Stale agent revision.")
    target=payload.get("target_state")
    if target not in ("active","paused","draft"):raise HTTPException(422,"Invalid agent state.")
    agent["state"]=target;agent["revision"]+=1
    runtime.agents.save(agent)
    return {**agent,"worker_started":False}

@app.post("/work-items")
def create_work_item(payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    dept=payload.get("department")
    if dept not in {d[0] for d in DEPARTMENTS}:raise HTTPException(422,"Unknown department.")
    business=payload.get("business_id","physical-agency")
    if business not in ("physical-agency","physical-brand","digital-products"):raise HTTPException(422,"Unknown business unit.")
    deps=tuple(UUID(str(x)) for x in payload.get("depends_on",[]))
    for dep in deps:
        parent=runtime.store.get_work_item(dep)
        if not parent or parent.business_id!=business:raise HTTPException(422,"Dependency must exist in the same business unit.")
    item=WorkItem(uuid4(),payload.get("title","").strip(),payload.get("objective","").strip(),dept,TaskState.DRAFT,business,deps)
    if not item.title or not item.objective:raise HTTPException(422,"Title and objective are required.")
    runtime.store.create_work_item(item,_audit("owner.created",item.id,"owner"))
    return {"item_id":str(item.id),"id":str(item.id),"state":item.state.value,"business_id":business}
@app.post("/work-items/{item_id}/delegation-preview")
def delegation_preview(item_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    """Preview a same-team manager/specialist group without assigning or starting work."""
    item=runtime.store.get_work_item(UUID(item_id))
    if not item:raise HTTPException(404,"Work item not found.")
    department=next((d for d in DEPARTMENT_CATALOGUE if d["department"]==item.department),None)
    if not department:raise HTTPException(422,"Work item department is not in the OpenCompany catalogue.")
    manager=next((r for r in ROLE_CATALOGUE if r["role_key"]==department["manager_role_key"]),None)
    if not manager:raise HTTPException(503,"Department manager role is unavailable.")
    team_key=item.department+"__team_01"
    candidates=[
        r for r in ROLE_CATALOGUE
        if r["department"]==item.department and r["kind"]=="specialist" and r["team_key"]==team_key
    ]
    required=[str(value).casefold() for value in payload.get("required_capabilities",[])]
    def relevance(role):
        values=[role["title"].casefold(),*(str(x).casefold() for x in role["capabilities"])]
        return sum(any(term in value for value in values) for term in required)
    candidates.sort(key=relevance,reverse=True)
    limit=max(1,min(int(payload.get("max_specialists",5)),5))
    specialists=[
        {
            "role_key":role["role_key"],"title":role["title"],"department":role["department"],
            "team_key":role["team_key"],"capabilities":role["capabilities"],
            "supporting_member":index>=max(0,limit-2),
        }
        for index,role in enumerate(candidates[:limit])
    ]
    return {
        "work_item_id":str(item.id),
        "manager":{"role_key":manager["role_key"],"title":manager["title"],"department":manager["department"]},
        "mode":"specialist_team","specialists":specialists,
        "assignment_performed":False,"execution_started":False,
    }


@app.post("/work-items/{item_id}/delegation-proposals")
def create_delegation_proposal(item_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    """Create a persisted draft team proposal; do not assign work or enqueue tasks."""
    item=runtime.store.get_work_item(UUID(item_id))
    if not item:raise HTTPException(404,"Work item not found.")
    department=next((d for d in DEPARTMENT_CATALOGUE if d["department"]==item.department),None)
    if not department:raise HTTPException(422,"Unknown OpenCompany department.")
    manager=next((r for r in ROLE_CATALOGUE if r["role_key"]==department["manager_role_key"]),None)
    if not manager:raise HTTPException(503,"Department manager role is unavailable.")
    manager_agent=runtime.agents.get(manager["role_key"])
    team_key=item.department+"__team_01"
    candidates=[
        role for role in ROLE_CATALOGUE
        if role["department"]==item.department and role["kind"]=="specialist" and role["team_key"]==team_key
    ]
    required=[str(value).casefold() for value in payload.get("required_capabilities",[])]
    def relevance(role):
        values=[role["title"].casefold(),*(str(value).casefold() for value in role["capabilities"])]
        return sum(any(term in value for value in values) for term in required)
    candidates.sort(key=relevance,reverse=True)
    limit=max(1,min(int(payload.get("max_specialists",5)),5))
    children=[]
    for role in candidates[:limit]:
        agent=runtime.agents.get(role["role_key"])
        if not agent:raise HTTPException(409,"Bootstrap the specialist profiles before preparing a delegation proposal.")
        children.append({
            "id":str(uuid4()),"title":item.title+" — "+role["title"],
            "objective":item.objective,"department":item.department,"role_key":role["role_key"],
            "assigned_agent_id":agent["id"],"team_key":role["team_key"],
            "state":"draft","materialized_work_item_id":None,
        })
    if len(children)!=limit:raise HTTPException(409,"The department does not have enough specialist roles for this proposal.")
    now=datetime.now(timezone.utc).isoformat()
    proposal={
        "id":str(uuid4()),"work_item_id":str(item.id),"department":item.department,
        "manager_role_key":manager["role_key"],
        "manager_agent_id":manager_agent["id"] if manager_agent else None,
        "status":"draft","children":children,"queue_entries_created":False,
        "execution_started":False,"created_at":now,"updated_at":now,
    }
    runtime.delegations.save_proposal(proposal)
    return proposal


def _executive_orchestration_snapshot(runtime, business_id=None):
    """Evaluate dependency and assignment readiness without changing work."""
    items=runtime.store.list_work_items(business_id)
    by_id={item.id:item for item in items}
    agents={agent.get("id"):agent for agent in runtime.agents.values()}
    eligible=[]
    blocked=[]
    counts={}
    for item in items:
        state=item.state.value
        counts[state]=counts.get(state,0)+1
        if item.state!=TaskState.DRAFT:
            continue
        reasons=[]
        for dependency_id in item.depends_on:
            dependency=by_id.get(dependency_id) or runtime.store.get_work_item(dependency_id)
            if dependency is None:
                reasons.append("dependency_missing:"+str(dependency_id))
            elif dependency.state!=TaskState.COMPLETED:
                reasons.append("dependency_not_completed:"+str(dependency_id))
        agent=agents.get(str(item.assigned_agent_id)) if item.assigned_agent_id else None
        if not item.assigned_agent_id or not item.assigned_role_key:
            reasons.append("specialist_assignment_required")
        elif not agent:
            reasons.append("assigned_specialist_missing")
        elif agent.get("role_key")!=item.assigned_role_key:
            reasons.append("assigned_role_mismatch")
        elif agent.get("state")!="active":
            reasons.append("assigned_specialist_not_active")
        if reasons:
            blocked.append({"work_item_id":str(item.id),"title":item.title,"reasons":reasons})
        else:
            eligible.append({"work_item_id":str(item.id),"title":item.title,
                             "department":item.department,"assigned_role_key":item.assigned_role_key,"revision":item.revision})
    return {
        "business_id":business_id,
        "work_item_count":len(items),
        "state_counts":counts,
        "eligible_to_advance":eligible,
        "blocked_draft_items":blocked,
        "queue_counts":runtime.queue.counts(),
        "execution_started":False,
        "queue_admission_performed":False,
    }


@app.get("/executive/orchestration/status")
def executive_orchestration_status(business_id:str|None=None,runtime=Depends(get_runtime),owner=Depends(_owner)):
    if business_id is not None:
        _business_id(business_id)
    return _executive_orchestration_snapshot(runtime,business_id)


@app.post("/executive/orchestration/cycle")
def executive_orchestration_cycle(payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    """Run one bounded CEO coordination cycle; never queues or executes work."""
    ceo=runtime.agents.get("chief_executive_orchestrator")
    if not ceo or ceo.get("state")!="active":
        raise HTTPException(409,"The CEO orchestrator must be explicitly active before coordinating a cycle.")
    business_id=payload.get("business_id")
    if business_id is not None:
        _business_id(business_id)
    has_title=bool(str(payload.get("title","")).strip())
    has_objective=bool(str(payload.get("objective","")).strip())
    if has_title!=has_objective:
        raise HTTPException(422,"Provide both title and objective to request a new CEO plan.")
    plan_result=None
    if has_title:
        plan_result=executive_plan({
            "title":payload["title"],"objective":payload["objective"],
            "business_id":business_id or "physical-agency",
            "max_tasks":payload.get("max_tasks",8),
        },runtime,"owner")
    delegation_result={
        "drafted_count":0,"drafted":[],"skipped":[],
        "owner_approval_required":True,"assignment_performed":False,
        "queue_entries_created":False,"execution_started":False,
    }
    if runtime.gateway.eligible_providers(request_budget_usd=0.0):
        delegation_result=executive_draft_delegations({
            "business_id":business_id,"max_items":payload.get("max_items",5),
            "max_specialists":payload.get("max_specialists",5),
        },runtime,"owner")
    else:
        delegation_result["skipped"].append({
            "reason":"no_confirmed_zero_cost_provider",
            "detail":"Manager proposal generation was skipped; no paid fallback was attempted.",
        })
    advance_result=executive_orchestration_advance({
        "business_id":business_id,"max_items":payload.get("max_advance",10),
    },runtime,"owner")
    return {
        "plan":plan_result,
        "delegations":delegation_result,
        "readiness":advance_result,
        "owner_approval_required_for_delegations":True,
        "queue_admission_performed":False,
        "execution_started":False,
        "parallel_execution_enabled":False,
    }


@app.post("/executive/orchestration/advance")
def executive_orchestration_advance(payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    """Advance only fully assigned, active, dependency-satisfied drafts to READY.

    This owner-triggered coordinator never admits queue work or starts execution.
    """
    ceo=runtime.agents.get("chief_executive_orchestrator")
    if not ceo or ceo.get("state")!="active":
        raise HTTPException(409,"The CEO orchestrator must be explicitly active before advancing work.")
    business_id=payload.get("business_id")
    if business_id is not None:
        _business_id(business_id)
    limit=max(1,min(int(payload.get("max_items",10)),20))
    snapshot=_executive_orchestration_snapshot(runtime,business_id)
    eligible_ids=[entry["work_item_id"] for entry in snapshot["eligible_to_advance"][:limit]]
    from dataclasses import replace
    advanced=[]
    for item_id in eligible_ids:
        item=runtime.store.get_work_item(UUID(item_id))
        if not item or item.state!=TaskState.DRAFT:
            continue
        changed=replace(item,state=TaskState.READY,revision=item.revision+1)
        runtime.store.save_work_item_with_audit(
            changed,_audit("ceo.orchestration_ready",changed.id,"ceo"),
        )
        advanced.append(_item_dict(changed))
    return {
        "advanced_count":len(advanced),
        "items":advanced,
        "remaining_eligible_count":max(0,len(snapshot["eligible_to_advance"])-len(advanced)),
        "queue_admission_performed":False,
        "execution_started":False,
        "owner_approval_required_for_queue_admission":True,
    }


@app.post("/executive/plan")
def executive_plan(payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    """Draft an atomic multi-department plan; never queue or execute its work items."""
    ceo=runtime.agents.get("chief_executive_orchestrator")
    if not ceo or ceo.get("state")!="active":
        raise HTTPException(409,"The CEO orchestrator must be explicitly active before planning.")
    title=str(payload.get("title","")).strip()
    objective=str(payload.get("objective","")).strip()
    if not title or not objective:raise HTTPException(422,"Plan title and objective are required.")
    business_id=_business_id(str(payload.get("business_id","physical-agency")))
    max_tasks=max(1,min(int(payload.get("max_tasks",8)),20))
    request={
        "task":"draft_executive_plan","title":title,"objective":objective,
        "business_id":business_id,
        "departments":[{"id":d["department"],"name":d["name"]} for d in DEPARTMENT_CATALOGUE],
        "constraints":{"max_tasks":max_tasks,"draft_only":True,"no_queue":True,"no_execution":True,"zero_cost_only":True},
    }
    try:
        result=runtime.gateway.generate(request,request_budget_usd=0.0)
    except Exception as exc:
        raise HTTPException(503,"The confirmed zero-cost provider could not produce an executive plan.") from exc
    try:
        decision=json.loads(result.text)
        raw_items=decision.get("work_items",[])
        if not isinstance(raw_items,list) or not raw_items or len(raw_items)>max_tasks:
            raise ValueError("work_items must be a non-empty list within max_tasks")
        normalized=[]
        for index,raw in enumerate(raw_items):
            department=str(raw.get("department",""))
            task_title=str(raw.get("title","")).strip()
            task_objective=str(raw.get("objective","")).strip()
            dependencies=raw.get("depends_on",[])
            if department not in {d[0] for d in DEPARTMENTS} or not task_title or not task_objective:
                raise ValueError("Each plan item needs a known department, title, and objective")
            if not isinstance(dependencies,list):
                raise ValueError("depends_on must be a list of earlier item indexes")
            deps=[]
            for dependency in dependencies:
                if not isinstance(dependency,int) or dependency<0 or dependency>=index:
                    raise ValueError("Plan dependencies must reference earlier items only")
                deps.append(dependency)
            normalized.append({"department":department,"title":task_title,"objective":task_objective,"depends_on":deps})
    except (TypeError,ValueError,AttributeError) as exc:
        raise HTTPException(422,"Executive plan was invalid: "+str(exc)) from exc
    ids=[uuid4() for _ in normalized]
    created=[]
    for index,entry in enumerate(normalized):
        item=WorkItem(
            ids[index],entry["title"],entry["objective"],entry["department"],TaskState.DRAFT,
            business_id,tuple(ids[dependency] for dependency in entry["depends_on"]),
        )
        runtime.store.create_work_item(item,_audit("ceo.plan_item_drafted",item.id,"ceo"))
        created.append(_item_dict(item))
    return {
        "title":title,"rationale":str(decision.get("rationale",""))[:1600],
        "manager_ai":{"provider":result.provider,"model":result.model,"cost_usd":result.cost_usd},
        "created_count":len(created),"items":created,
        "owner_review_required":True,"queue_entries_created":False,"execution_started":False,
    }


@app.post("/work-items/{item_id}/manager-proposal")
def manager_proposal(item_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    """Let an active department manager draft a team proposal; owner approval remains required."""
    item=runtime.store.get_work_item(UUID(item_id))
    if not item:raise HTTPException(404,"Work item not found.")
    department=next((d for d in DEPARTMENT_CATALOGUE if d["department"]==item.department),None)
    if not department:raise HTTPException(422,"Unknown OpenCompany department.")
    manager_role=next((r for r in ROLE_CATALOGUE if r["role_key"]==department["manager_role_key"]),None)
    manager=runtime.agents.get(department["manager_role_key"])
    if not manager or manager.get("state")!="active":
        raise HTTPException(409,"The department manager must be explicitly ACTIVE before creating an AI proposal.")
    request={
        "task":"propose_specialist_team",
        "manager_role":manager_role,
        "work_item":{"title":item.title,"objective":item.objective,"department":item.department},
        "constraints":{"max_specialists":max(1,min(int(payload.get("max_specialists",5)),5)),
                       "no_assignment":True,"no_queue_admission":True,"no_execution":True,
                       "zero_cost_only":True},
    }
    try:
        result=runtime.gateway.generate(request,request_budget_usd=0.0)
    except Exception as exc:
        raise HTTPException(503,"The confirmed zero-cost model provider could not produce a manager proposal.") from exc
    try:
        decision=json.loads(result.text)
        required=[str(value) for value in decision.get("required_capabilities",[])]
        if not required or not all(value.strip() for value in required):
            raise ValueError("required_capabilities must be a non-empty list")
    except (TypeError,ValueError,AttributeError) as exc:
        raise HTTPException(422,"Manager proposal output was not valid structured JSON.") from exc
    proposal=create_delegation_proposal(
        item_id,{"required_capabilities":required,"max_specialists":request["constraints"]["max_specialists"]},
        runtime,owner,
    )
    proposal["rationale"]=str(decision.get("rationale",""))[:1200]
    proposal["manager_role_key"]=manager_role["role_key"]
    runtime.delegations.save_proposal(proposal)
    return {
        "manager_ai":{"provider":result.provider,"model":result.model,"cost_usd":result.cost_usd},
        "required_capabilities":required,"rationale":proposal["rationale"],
        "mode":"specialist_team","proposal":proposal,
        "owner_approval_required":True,"assignment_performed":False,
        "queue_entries_created":False,"execution_started":False,
    }


@app.post("/executive/orchestration/draft-delegations")
def executive_draft_delegations(payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    """Ask active department managers for draft team proposals; owner approval remains separate."""
    ceo=runtime.agents.get("chief_executive_orchestrator")
    if not ceo or ceo.get("state")!="active":
        raise HTTPException(409,"The CEO orchestrator must be explicitly active before coordinating managers.")
    if not runtime.gateway.eligible_providers(request_budget_usd=0.0):
        raise HTTPException(503,"No confirmed zero-cost provider is ready for manager proposals.")
    business_id=payload.get("business_id")
    if business_id is not None:
        _business_id(business_id)
    try:
        max_items=int(payload.get("max_items",5))
        max_specialists=int(payload.get("max_specialists",5))
    except (TypeError,ValueError) as exc:
        raise HTTPException(422,"max_items and max_specialists must be integers.") from exc
    max_items=max(1,min(max_items,10))
    max_specialists=max(1,min(max_specialists,5))
    drafted=[]
    skipped=[]
    for item in runtime.store.list_work_items(business_id):
        if len(drafted)>=max_items:
            break
        if item.state!=TaskState.DRAFT or item.assigned_agent_id:
            continue
        existing=runtime.delegations.list_proposals(item.id)
        if existing:
            skipped.append({"work_item_id":str(item.id),"reason":"delegation_proposal_already_exists"})
            continue
        department=next((d for d in DEPARTMENT_CATALOGUE if d["department"]==item.department),None)
        manager=runtime.agents.get(department["manager_role_key"]) if department else None
        if not manager or manager.get("state")!="active":
            skipped.append({"work_item_id":str(item.id),"reason":"department_manager_not_active"})
            continue
        try:
            result=manager_proposal(
                str(item.id),{"max_specialists":max_specialists},runtime,"owner",
            )
            drafted.append({
                "work_item_id":str(item.id),
                "proposal":result["proposal"],
                "manager_ai":result["manager_ai"],
            })
        except HTTPException as exc:
            skipped.append({"work_item_id":str(item.id),"reason":str(exc.detail)[:300]})
    return {
        "drafted_count":len(drafted),
        "drafted":drafted,
        "skipped":skipped,
        "owner_approval_required":True,
        "assignment_performed":False,
        "queue_entries_created":False,
        "execution_started":False,
    }


@app.get("/work-items/{item_id}/delegation-proposals")
def list_delegation_proposals(item_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    item=runtime.store.get_work_item(UUID(item_id))
    if not item:raise HTTPException(404,"Work item not found.")
    proposals=runtime.delegations.list_proposals(item.id)
    return {"count":len(proposals),"proposals":proposals}


@app.post("/work-items/{item_id}/delegation-proposals/{proposal_id}/reject")
def reject_delegation_proposal(item_id:str,proposal_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    """Record an explicit owner rejection without materializing or queueing child work."""
    item=runtime.store.get_work_item(UUID(item_id))
    if not item:raise HTTPException(404,"Work item not found.")
    proposal=runtime.delegations.get_proposal(item.id,proposal_id)
    if not proposal:raise HTTPException(404,"Delegation proposal not found.")
    if proposal["status"]!="draft":raise HTTPException(409,"Only draft delegation proposals can be rejected.")
    rationale=str(payload.get("rationale","")).strip()
    if not rationale:raise HTTPException(422,"Owner rejection rationale is required.")
    proposal["status"]="rejected"
    proposal["owner_approval_required"]=False
    proposal["decision_rationale"]=rationale[:1200]
    proposal["decided_at"]=datetime.now(timezone.utc).isoformat()
    proposal["updated_at"]=proposal["decided_at"]
    proposal["queue_entries_created"]=False
    proposal["execution_started"]=False
    runtime.delegations.save_proposal(proposal)
    runtime.store.save_work_item_with_audit(
        item,_audit("delegation.proposal_rejected",item.id,"owner"),
    )
    return {
        **proposal,
        "materialized_work_items":[],
        "queue_entries_created":False,
        "execution_started":False,
    }


@app.post("/work-items/{item_id}/delegation-proposals/{proposal_id}/approve")
def approve_delegation_proposal(item_id:str,proposal_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    item=runtime.store.get_work_item(UUID(item_id))
    if not item:raise HTTPException(404,"Work item not found.")
    proposal=runtime.delegations.get_proposal(item.id,proposal_id)
    if not proposal:raise HTTPException(404,"Delegation proposal not found.")
    if proposal["status"]!="draft":raise HTTPException(409,"Only draft delegation proposals can be approved.")
    manager=next((agent for agent in runtime.agents.values() if agent["id"]==proposal.get("manager_agent_id")),None)
    if not manager or manager.get("state")!="active":
        raise HTTPException(409,"The department manager must be explicitly active before approval.")
    specialists=[]
    for child in proposal["children"]:
        agent=next((value for value in runtime.agents.values() if value["id"]==child["assigned_agent_id"]),None)
        if not agent or agent.get("state")!="active":
            raise HTTPException(409,"Every assigned specialist must be explicitly active before approval.")
        specialists.append(agent)
    materialized=[]
    from dataclasses import replace
    for child,agent in zip(proposal["children"],specialists):
        # Derive a stable child ID from the proposal and child definition. If a
        # request is interrupted after inserting a child but before saving the
        # proposal, a retry finds and reuses that same work item.
        stable_child_id=UUID(child["materialized_work_item_id"]) if child.get("materialized_work_item_id") else __import__("uuid").uuid5(UUID(proposal["id"]),str(child["id"]))
        work_item=runtime.store.get_work_item(stable_child_id)
        if work_item is None:
            work_item=WorkItem(
                stable_child_id,child["title"],child["objective"],child["department"],TaskState.READY,
                item.business_id,(),UUID(agent["id"]),child["role_key"],
            )
            runtime.store.create_work_item(work_item,_audit("delegation.child_approved",work_item.id,"owner"))
        else:
            # Never adopt an unrelated item if persisted proposal metadata is corrupt.
            if (work_item.title!=child["title"] or work_item.objective!=child["objective"]
                    or work_item.assigned_agent_id!=UUID(agent["id"])
                    or work_item.assigned_role_key!=child["role_key"]):
                raise HTTPException(409,"A previously materialized child does not match this proposal.")
        child["state"]="approved"
        child["materialized_work_item_id"]=str(work_item.id)
        materialized.append(_item_dict(work_item))
    child_ids=tuple(UUID(task["id"]) for task in materialized)
    assigned_parent=replace(
        item,assigned_agent_id=UUID(manager["id"]),
        assigned_role_key=manager["role_key"],
        depends_on=tuple(dict.fromkeys((*item.depends_on,*child_ids))),
    )
    runtime.store.save_work_item_with_audit(
        assigned_parent,_audit("delegation.parent_assigned",item.id,"owner"),
    )
    auto_queue_enabled=os.getenv("OPENCOMPANY_AUTO_QUEUE_APPROVED_WORK","false").lower()=="true"
    provider_ready=bool(runtime.gateway.eligible_providers(request_budget_usd=0.0)) if auto_queue_enabled else False
    queued_ids=[]
    if auto_queue_enabled and provider_ready:
        for index,task in enumerate(materialized):
            child_item=runtime.store.get_work_item(UUID(task["id"]))
            agent=specialists[index]
            if child_item and agent.get("state")=="active":
                runtime.queue.admit(child_item.id,child_item.assigned_agent_id,child_item.assigned_role_key)
                queued_item=replace(child_item,state=TaskState.QUEUED)
                runtime.store.save_work_item_with_audit(queued_item,_audit("queue.auto_admitted",queued_item.id,"owner"))
                task.update(_item_dict(queued_item))
                queued_ids.append(str(queued_item.id))
    proposal["status"]="approved"
    proposal["queue_entries_created"]=bool(queued_ids)
    proposal["execution_started"]=False
    proposal["materialized_work_items"]=materialized
    proposal["updated_at"]=datetime.now(timezone.utc).isoformat()
    runtime.delegations.save_proposal(proposal)
    return {
        **proposal,
        "queue_entries_created":bool(queued_ids),
        "auto_queue":{"enabled":auto_queue_enabled,"provider_ready":provider_ready,"queued_work_item_ids":queued_ids},
    }


@app.post("/work-items/{item_id}/enqueue")
def enqueue_work_item(item_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    """Admit an explicitly assigned, ready task to the queue without starting a worker."""
    item=runtime.store.get_work_item(UUID(item_id))
    if not item:raise HTTPException(404,"Work item not found.")
    if item.state!=TaskState.READY:raise HTTPException(409,"Only owner-ready work items can be queued.")
    for dependency_id in item.depends_on:
        dependency=runtime.store.get_work_item(dependency_id)
        if (dependency is None or dependency.business_id!=item.business_id
                or dependency.state!=TaskState.COMPLETED):
            raise HTTPException(409,"Every prerequisite must be completed in the same business unit before queue admission.")
    if not item.assigned_agent_id or not item.assigned_role_key:
        raise HTTPException(409,"Work must be assigned to an active specialist before queue admission.")
    agent=next((value for value in runtime.agents.values() if value["id"]==str(item.assigned_agent_id)),None)
    if not agent or agent.get("state")!="active":
        raise HTTPException(409,"The assigned specialist must be explicitly active before queue admission.")
    if not runtime.gateway.eligible_providers(request_budget_usd=0.0):
        raise HTTPException(503,"No confirmed zero-cost provider is ready for this task.")
    try:
        runtime.queue.admit(item.id,item.assigned_agent_id,item.assigned_role_key)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from exc
    from dataclasses import replace
    changed=replace(item,state=TaskState.QUEUED)
    runtime.store.save_work_item_with_audit(changed,_audit("queue.admitted",item.id,"owner"))
    return {**_item_dict(changed),"worker_started":False}


@app.get("/work-items")
def list_work_items(business_id:str|None=None,runtime=Depends(get_runtime),owner=Depends(_owner)):
    items=runtime.store.list_work_items(business_id);return {"count":len(items),"items":[_item_dict(x) for x in items]}
def _item_dict(item):
    return {"id":str(item.id),"item_id":str(item.id),"title":item.title,"objective":item.objective,"department":item.department,"state":item.state.value,"business_id":item.business_id,"depends_on":[str(x) for x in item.depends_on],"assigned_agent_id":str(item.assigned_agent_id) if item.assigned_agent_id else None,"assigned_role_key":item.assigned_role_key,"revision":item.revision}
@app.post("/work-items/{item_id}/transition")
def transition_work_item(item_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    item=runtime.store.get_work_item(UUID(item_id))
    if not item:raise HTTPException(404,"Work item not found.")
    target=payload.get("target_state")
    if item.state==TaskState.IN_PROGRESS and target=="cancelled":raise HTTPException(409,"Use queue-aware cancellation to avoid orphaning a running worker.")
    if target=="completed":
        runtime.store.save_work_item_with_audit(item,_audit("owner.direct_completion_blocked",item.id,"owner"))
        raise HTTPException(409,"Completion requires an owner review of a saved deliverable.")
    if target in ("queued","in_progress"):raise HTTPException(409,"This lifecycle transition requires queue admission or worker execution.")
    if target not in ("ready","cancelled","failed"):raise HTTPException(422,"Invalid transition.")
    if target=="ready":
        for dependency_id in item.depends_on:
            dependency=runtime.store.get_work_item(dependency_id)
            if (dependency is None or dependency.business_id!=item.business_id
                    or dependency.state!=TaskState.COMPLETED):
                raise HTTPException(409,"Every prerequisite must be completed in the same business unit before work can be marked ready.")
    from dataclasses import replace
    changed=replace(item,state=TaskState(target))
    runtime.store.save_work_item_with_audit(changed,_audit("owner.transition",item.id,"owner"))
    return _item_dict(changed)
@app.post("/work-items/{item_id}/review")
def review_work_item(item_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    item=runtime.store.get_work_item(UUID(item_id))
    if not item:raise HTTPException(404,"Work item not found.")
    if item.state not in (TaskState.REVIEW,TaskState.IN_PROGRESS):raise HTTPException(409,"Work item is not awaiting review.")
    if not payload.get("rationale","").strip():raise HTTPException(422,"Review rationale is required.")
    from dataclasses import replace
    state=TaskState.COMPLETED if payload.get("approved") else TaskState.FAILED
    changed=replace(item,state=state)
    runtime.store.save_work_item_with_audit(changed,_audit("owner.review",item.id,"owner"))
    evaluation_id=str(uuid4())
    deliverables=runtime.store.list_deliverables(item.id)
    role_key=(deliverables[-1]["role_key"] if deliverables else item.assigned_role_key) or "unassigned"
    runtime.learning.save_evaluation({
        "id":evaluation_id,"work_item_id":str(item.id),"role_key":role_key,
        "approved":bool(payload.get("approved")),"rationale":payload["rationale"].strip(),
        "deliverable_content":deliverables[-1]["content"] if deliverables else "",
        "created_at":datetime.now(timezone.utc).isoformat(),
    })
    auto_queue_enabled=os.getenv("OPENCOMPANY_AUTO_QUEUE_APPROVED_WORK","false").lower()=="true"
    provider_ready=bool(runtime.gateway.eligible_providers(request_budget_usd=0.0)) if auto_queue_enabled else False
    queued_ids=[]
    if state==TaskState.COMPLETED:
        for dependent in runtime.store.list_work_items():
            if item.id in dependent.depends_on and dependent.state==TaskState.DRAFT and dependent.assigned_agent_id:
                prerequisites=[runtime.store.get_work_item(dep) for dep in dependent.depends_on]
                if prerequisites and all(value and value.state==TaskState.COMPLETED for value in prerequisites):
                    ready_parent=replace(dependent,state=TaskState.READY)
                    runtime.store.save_work_item_with_audit(
                        ready_parent,_audit("workflow.dependencies_completed",dependent.id,"system"),
                    )
                    if auto_queue_enabled and provider_ready:
                        manager=next((value for value in runtime.agents.values()
                                      if value["id"]==str(ready_parent.assigned_agent_id)),None)
                        if manager and manager.get("state")=="active":
                            runtime.queue.admit(ready_parent.id,ready_parent.assigned_agent_id,ready_parent.assigned_role_key)
                            queued_parent=replace(ready_parent,state=TaskState.QUEUED)
                            runtime.store.save_work_item_with_audit(
                                queued_parent,_audit("queue.auto_admitted",queued_parent.id,"owner"),
                            )
                            queued_ids.append(str(queued_parent.id))
    return {
        "state":state.value,"evaluation_recorded":True,"evaluation_id":evaluation_id,
        "auto_queue":{"enabled":auto_queue_enabled,"provider_ready":provider_ready,"queued_work_item_ids":queued_ids},
    }
@app.post("/learning/ai-proposals")
def learning_ai_proposal(payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    """Draft a learning note from persisted review evaluations; never apply it automatically."""
    evaluation_ids=payload.get("evaluation_ids",[])
    if not isinstance(evaluation_ids,list) or not evaluation_ids:
        raise HTTPException(422,"At least one evaluation ID is required.")
    evaluations=runtime.learning.get_evaluations(evaluation_ids)
    if len(evaluations)!=len(set(str(value) for value in evaluation_ids)):
        raise HTTPException(404,"One or more review evaluations were not found.")
    request={
        "task":"propose_role_learning_note",
        "evaluations":evaluations,
        "constraints":{"draft_only":True,"owner_approval_required":True,"do_not_apply":True,"zero_cost_only":True},
    }
    try:
        result=runtime.gateway.generate(request,request_budget_usd=0.0)
    except Exception as exc:
        raise HTTPException(503,"The confirmed zero-cost provider could not draft a learning note.") from exc
    try:
        decision=json.loads(result.text)
        role_key=str(decision["role_key"])
        note=str(decision["note"]).strip()
        rationale=str(decision["rationale"]).strip()
        expected=str(decision["expected_measurement"]).strip()
        risk=str(decision["risk_level"]).strip().lower()
        if role_key not in {role["role_key"] for role in ROLE_CATALOGUE} or not note or not rationale or not expected:
            raise ValueError("Learning proposal fields are incomplete or refer to an unknown role.")
    except (KeyError,TypeError,ValueError) as exc:
        raise HTTPException(422,"Learning proposal output was not valid structured content.") from exc
    proposal={
        "id":str(uuid4()),"role_key":role_key,"note":note[:3000],
        "rationale":rationale[:1600],"expected_measurement":expected[:1200],
        "risk_level":risk,"evaluation_ids":[str(value) for value in evaluation_ids],
        "status":"draft","owner_approval_required":True,"note_applied":False,
        "provider":result.provider,"model":result.model,"cost_usd":result.cost_usd,
        "created_at":datetime.now(timezone.utc).isoformat(),
    }
    runtime.learning.save_proposal(proposal)
    source_item=runtime.store.get_work_item(UUID(evaluations[0]["work_item_id"]))
    if source_item:
        runtime.store.save_work_item_with_audit(source_item,_audit("learning.proposal_created",source_item.id,"owner"))
    return proposal


@app.post("/learning/proposals/{proposal_id}/decision")
def decide_learning_proposal(proposal_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    proposal=runtime.learning.get_proposal(proposal_id)
    if not proposal:raise HTTPException(404,"Learning proposal not found.")
    if proposal["status"]!="draft":raise HTTPException(409,"Only draft learning proposals can receive an owner decision.")
    rationale=str(payload.get("rationale","")).strip()
    if not rationale:raise HTTPException(422,"Owner decision rationale is required.")
    approved=bool(payload.get("approved"))
    proposal["status"]="approved" if approved else "rejected"
    proposal["owner_approval_required"]=False
    proposal["decision_rationale"]=rationale[:1200]
    proposal["decided_at"]=datetime.now(timezone.utc).isoformat()
    runtime.learning.save_proposal(proposal)
    evaluations=runtime.learning.get_evaluations(proposal["evaluation_ids"])
    if evaluations:
        source_item=runtime.store.get_work_item(UUID(evaluations[0]["work_item_id"]))
        if source_item:
            runtime.store.save_work_item_with_audit(source_item,_audit("learning.proposal_decided",source_item.id,"owner"))
    return proposal


@app.post("/learning/proposals/{proposal_id}/apply-note")
def apply_learning_note(proposal_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    proposal=runtime.learning.get_proposal(proposal_id)
    if not proposal:raise HTTPException(404,"Learning proposal not found.")
    if proposal["status"]!="approved":raise HTTPException(409,"An owner-approved learning proposal is required before applying a note.")
    note={
        "id":str(uuid4()),"role_key":proposal["role_key"],"note":proposal["note"],
        "proposal_id":proposal["id"],"expected_measurement":proposal["expected_measurement"],
        "risk_level":proposal["risk_level"],"created_at":datetime.now(timezone.utc).isoformat(),
    }
    runtime.learning.add_note(note)
    proposal["status"]="implemented"
    proposal["note_applied"]=True
    proposal["implemented_at"]=note["created_at"]
    runtime.learning.save_proposal(proposal)
    evaluations=runtime.learning.get_evaluations(proposal["evaluation_ids"])
    if evaluations:
        source_item=runtime.store.get_work_item(UUID(evaluations[0]["work_item_id"]))
        if source_item:
            runtime.store.save_work_item_with_audit(source_item,_audit("learning.note_applied",source_item.id,"owner"))
    return {"state":"implemented","note_id":note["id"],"role_key":note["role_key"],"note_applied":True}


@app.get("/learning/notes/{role_key}")
def list_learning_notes(role_key:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    notes=runtime.learning.list_notes(role_key)
    return {"role_key":role_key,"count":len(notes),"notes":notes}


@app.get("/code-evolution/config-status")
def code_evolution_config_status(runtime=Depends(get_runtime),owner=Depends(_owner)):
    client=runtime.github_evolution
    enabled=bool(client and runtime.github_evolution_tested_at)
    return {
        "enabled":enabled,
        "repository":getattr(client,"repository",None) if enabled else None,
        "base_branch":getattr(client,"base_branch",None) if enabled else None,
        "tested_at":runtime.github_evolution_tested_at if enabled else None,
        "draft_pull_requests_only":True,"merge_requires_owner":True,"deployment_enabled":False,
    }


@app.post("/code-evolution/proposals")
def create_code_evolution_proposal(payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    client=runtime.github_evolution
    if not client or not runtime.github_evolution_tested_at:
        raise HTTPException(503,"GitHub code-evolution access must be verified before drafting changes.")
    problem=str(payload.get("problem","")).strip()
    paths=payload.get("file_paths",[])
    if not problem or not isinstance(paths,list) or not paths or len(paths)>10:
        raise HTTPException(422,"A problem statement and one to ten file paths are required.")
    normalized=[]
    for value in paths:
        path=str(value)
        if path.startswith("/") or ".." in path.split("/") or not path.startswith(("src/","tests/","docs/")):
            raise HTTPException(422,"Code evolution may only draft changes inside src/, tests/, or docs/.")
        if any(secret in path.casefold() for secret in (".env","secret","credential","private_key")):
            raise HTTPException(422,"Sensitive paths are not eligible for code evolution.")
        normalized.append(path)
    try:
        existing=client.read_files(normalized)
        request={
            "task":"draft_isolated_code_improvement",
            "problem":problem,"requested_paths":normalized,"existing_files":existing,
            "constraints":{"draft_pull_request_only":True,"no_merge":True,"no_deploy":True,
                           "no_secrets":True,"preserve_unrelated_changes":True,"tests_required":True},
        }
        if hasattr(runtime.gateway,"set_usage_recorder"):
            runtime.gateway.set_usage_recorder(runtime.usage.record)
        result=runtime.gateway.generate(request,request_budget_usd=0.0)
        decision=json.loads(result.text)
        title=str(decision["title"]).strip()
        summary=str(decision["summary"]).strip()
        files=decision["files"]
        if not title or not summary or not isinstance(files,list) or not files or len(files)>10:
            raise ValueError("The proposed change set is incomplete.")
        safe_files={}
        for entry in files:
            file_path=str(entry["path"])
            content=str(entry["content"])
            if file_path not in normalized or not content or len(content)>100000:
                raise ValueError("The model proposed an unrequested or invalid file.")
            safe_files[file_path]=content
        if len(safe_files)!=len(files):
            raise ValueError("Duplicate file paths are not allowed.")
        pull_request=client.create_pull_request(title=title,summary=summary,files=safe_files)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503,"A safe draft pull request could not be created.") from exc
    return {
        "pull_request_number":pull_request.number,"pull_request_url":pull_request.url,
        "branch":pull_request.branch,"commit":pull_request.commit_sha,"title":pull_request.title,
        "draft":True,"merged":False,"deployed":False,"owner_merge_review_required":True,
    }


@app.get("/work-items/{item_id}/deliverables")
def deliverables(item_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    items=runtime.store.list_deliverables(UUID(item_id));return {"count":len(items),"deliverables":list(items)}
@app.get("/work-items/{item_id}/workflow")
def work_item_workflow(item_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    item=runtime.store.get_work_item(UUID(item_id))
    if not item:raise HTTPException(404,"Work item not found.")
    deps=[runtime.store.get_work_item(x) for x in item.depends_on]
    all_items=runtime.store.list_work_items()
    dependents=[x for x in all_items if item.id in x.depends_on]
    deliver=runtime.store.list_deliverables(item.id)
    return {"work_item":_item_dict(item),"next_action":"owner_review_and_mark_ready" if item.state==TaskState.DRAFT else "review_deliverable" if item.state==TaskState.REVIEW else "none","prerequisites":[_item_dict(x) for x in deps if x],"dependents":[_item_dict(x) for x in dependents],"queue":None,"deliverables":list(deliver),"counts":{"deliverables":len(deliver)}}

@app.get("/audit/verify")
def audit_verify(runtime=Depends(get_runtime),owner=Depends(_owner)):
    return {"event_count":runtime.store.audit_count(),"chain_valid":runtime.store.verify_audit_chain()}

def initialize_autonomous_runtime():
    runtime=_default_runtime()
    if os.getenv("OPENCOMPANY_WORKER_AUTOSTART","false").lower()=="true" and runtime.gateway.eligible_providers(request_budget_usd=0.0):
        runtime.fleet.start()
