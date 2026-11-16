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


@app.post("/executive/plan")
def executive_plan(payload:dict,runtime=Depends(get_runtime),owner=Depends(_owner)):
    """Draft an atomic multi-department plan; never queue or execute its work items."""
    ceo=runtime.agents.get("chief_executive_orchestrator")
    if not ceo or ceo.get("state")!="active":
        raise HTTPException(409,"The CEO orchestrator must be explicitly active before planning.")
    title=str(payload.get("title","")).strip()
    objective=str(payload.get("objective","")).strip()
    if not title or not objective:raise HTTPException(422,"Plan title and objective are required.")
    max_tasks=max(1,min(int(payload.get("max_tasks",8)),20))
    request={
        "task":"draft_executive_plan","title":title,"objective":objective,
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
            "physical-agency",tuple(ids[dependency] for dependency in entry["depends_on"]),
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


@app.get("/work-items/{item_id}/delegation-proposals")
def list_delegation_proposals(item_id:str,runtime=Depends(get_runtime),owner=Depends(_owner)):
    item=runtime.store.get_work_item(UUID(item_id))
    if not item:raise HTTPException(404,"Work item not found.")
    proposals=runtime.delegations.list_proposals(item.id)
    return {"count":len(proposals),"proposals":proposals}


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
        work_item=WorkItem(
            uuid4(),child["title"],child["objective"],child["department"],TaskState.READY,
            item.business_id,(),UUID(agent["id"]),child["role_key"],
        )
        runtime.store.create_work_item(work_item,_audit("delegation.child_approved",work_item.id,"owner"))
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
    return {"id":str(item.id),"item_id":str(item.id),"title":item.title,"objective":item.objective,"department":item.department,"state":item.state.value,"business_id":item.business_id,"depends_on":[str(x) for x in item.depends_on],"assigned_agent_id":str(item.assigned_agent_id) if item.assigned_agent_id else None,"assigned_role_key":item.assigned_role_key}
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
