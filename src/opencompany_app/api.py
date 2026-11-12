"""Owner-controlled FastAPI surface for the OpenCompany runtime."""
from __future__ import annotations
import hashlib, html, os, secrets, time
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID, uuid4
from fastapi import FastAPI, Depends, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from opencompany_core.domain import AuditRecord, TaskState
from opencompany_app.runtime import Runtime, create_runtime, WorkItem, _audit
from opencompany_app.catalogue import ROLE_CATALOGUE, DEPARTMENT_CATALOGUE, DEPARTMENTS

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
            origin=request.headers.get("origin")
            if origin != str(request.base_url).rstrip("/"):
                raise HTTPException(403,"Cookie-authenticated writes must come from the same origin.")
            csrf=request.headers.get("x-csrf-token")
            if not csrf or not secrets.compare_digest(csrf,session["csrf"]) or request.cookies.get("opencompany_csrf")!=csrf:
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
    page=f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>OpenCompany Owner Console</title><style nonce="{nonce}">body{{font:16px system-ui;margin:2rem;max-width:1100px}}section{{padding:1rem;border:1px solid #bbb;margin:1rem 0}}button{{padding:.6rem}}</style></head><body>
<h1>OpenCompany Owner Console</h1><section><h2>Executive & workforce</h2><button id="provision-executive">Provision executive</button><button id="provision-specialists">Provision specialists</button><h3>Specialist roles</h3><p>View draft · Approve draft · Request revision</p></section>
<section><h2>Work items</h2><p>Workflow details · Retry failed task · Cancel task</p><div id="executive-business"></div><div id="business-filter"></div><p>AI usage &amp; cost ledger</p><button onclick="void(0)">Load usage</button></section>
<section><h2>UnoRouter</h2><input id="unorouter-discover"><input id="unorouter-model"><p>automatic rotation across confirmed-free models · discover all free models</p></section>
<section><h2>Code evolution</h2><input id="github-evolution-token"><p>draft pull requests only</p></section>
<script nonce="{nonce}">async function request(path,options={{}}){{const response=await fetch(path,options);const payload=await response.json();if(!response.ok)throw new Error(payload.detail);return payload}}async function loadModelUsage(){{return request("/usage/model")}}async function loadGitHubEvolutionSettings(){{return request("/code-evolution/config-status")}}async function loadWorkItemWorkflow(w){{return request("/work-items/"+w.id+"/workflow")}}void loadModelUsage;void loadGitHubEvolutionSettings;void loadWorkItemWorkflow;</script></body></html>"""
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
    return {"gateway_enabled":enabled,"provider":selected,"providers":out,"billing_mode":"free_confirmed" if enabled else "disabled","paid_fallback":False,"real_inference_verified":False}

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

@app.get("/usage/model")
def model_usage(runtime=Depends(get_runtime),owner=Depends(_owner)):return runtime.usage.summary()

@app.get("/workers/status")
def workers_status(runtime=Depends(get_runtime),owner=Depends(_owner)):
    status=runtime.fleet.status();return {"running":status.running,"worker_count":status.worker_count}
@app.get("/workers/queue")
def workers_queue(runtime=Depends(get_runtime),owner=Depends(_owner)):
    counts=runtime.queue.counts();return {"counts":counts,"total":sum(counts.values())}
@app.post("/workers/start")
def workers_start(runtime=Depends(get_runtime),owner=Depends(_owner)):
    if not runtime.gateway.eligible_providers(request_budget_usd=0.0):raise HTTPException(503,"No confirmed zero-cost provider is ready.")
    return {"running":runtime.fleet.start().running}
@app.post("/workers/stop")
def workers_stop(runtime=Depends(get_runtime),owner=Depends(_owner)):return {"running":runtime.fleet.stop().running}

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
    runtime.store.create_work_item(item)
    return {"item_id":str(item.id),"id":str(item.id),"state":item.state.value,"business_id":business}
@app.get("/work-items")
def list_work_items(business_id:str|None=None,runtime=Depends(get_runtime),owner=Depends(_owner)):
    items=runtime.store.list_work_items(business_id);return {"count":len(items),"items":[_item_dict(x) for x in items]}
def _item_dict(item):
    return {"id":str(item.id),"item_id":str(item.id),"title":item.title,"objective":item.objective,"department":item.department,"state":item.state.value,"business_id":item.business_id,"depends_on":[str(x) for x in item.depends_on],"assigned_agent_id":str(item.assigned_agent_id) if item.assigned_agent_id else None,"assigned_role_key":item.assigned_role_key}
@app.post("/work-items/{item_id}/transition")
def transition_work_item(item_id:str,payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    item=runtime.store.get_work_item(UUID(item_id))
    if not item:raise HTTPException(404,"Work item not found.")
    target=payload.get("target_state")
    if item.state==TaskState.IN_PROGRESS and target=="cancelled":raise HTTPException(409,"Use queue-aware cancellation to avoid orphaning a running worker.")
    if target in ("queued","in_progress","completed"):raise HTTPException(409,"This lifecycle transition requires queue admission, worker execution, or owner review.")
    if target not in ("ready","cancelled","failed"):raise HTTPException(422,"Invalid transition.")
    if target=="ready" and any(runtime.store.get_work_item(dep).state!=TaskState.COMPLETED for dep in item.depends_on):pass
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
    return {"state":state.value,"evaluation_recorded":True,"evaluation_id":str(uuid4())}
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
