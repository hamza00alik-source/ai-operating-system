"""Self-contained, dependency-free, mobile-friendly owner console."""

OWNER_DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>OpenCompany Owner Console</title>
<style>
:root{color-scheme:dark;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;background:#0b1020;color:#eef2ff}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(145deg,#101a32,#0b1020 55%);min-height:100vh}
main{max-width:1100px;margin:auto;padding:22px 16px 48px}.top{display:flex;gap:14px;align-items:center;justify-content:space-between;flex-wrap:wrap}
h1{font-size:clamp(1.5rem,4vw,2.1rem);margin:0}.muted{color:#9aa8c7}.panel{background:#141e35;border:1px solid #283653;border-radius:16px;padding:16px;margin-top:16px}
.auth{display:flex;gap:10px;flex-wrap:wrap}.auth input{flex:1;min-width:180px;background:#0b1428;border:1px solid #405071;color:#fff;border-radius:10px;padding:12px;font-size:16px}
button{border:0;border-radius:10px;background:#8ab4ff;color:#081326;font-weight:700;padding:12px 16px;cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-top:14px}.metric{background:#0e172b;border:1px solid #293a5a;border-radius:12px;padding:14px}.metric strong{display:block;font-size:1.8rem;margin-top:5px}
.list{display:grid;gap:10px;margin-top:12px}.item{background:#0e172b;border:1px solid #293a5a;border-radius:12px;padding:13px}.item h3{font-size:1rem;margin:0 0 7px}.item p{margin:5px 0;color:#b7c3dc;line-height:1.45;font-size:.92rem}
.row{display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:wrap}.pill{font-size:.75rem;border-radius:999px;background:#263653;color:#cfe0ff;padding:5px 9px}
.warn{color:#ffd58a}.error{color:#ff9c9c}.success{color:#91e0bd}.section-title{margin:22px 0 8px;font-size:1.15rem}
@media(max-width:520px){main{padding:16px 12px 32px}.panel{padding:13px}.auth{flex-direction:column}.auth button{width:100%}}
</style>
</head>
<body>
<main>
  <div class="top">
    <div><h1>OpenCompany</h1><div class="muted">Owner control centre · independent core</div></div>
    <span class="pill">Owner approval controls enabled</span>
  </div>
  <section class="panel">
    <h2 style="font-size:1.05rem;margin:0 0 10px">Secure owner connection</h2>
    <div class="auth">
      <input id="owner-key" type="password" autocomplete="current-password" placeholder="Enter owner API key">
      <button id="connect">Connect</button>
      <button id="disconnect" type="button">Disconnect</button>
    </div>
    <p id="message" class="muted" aria-live="polite">Enter the owner API key to establish a revocable HttpOnly session. The key is exchanged once and is not retained by this page.</p>
  </section>
  <section class="grid" aria-label="Company overview">
    <div class="metric"><span class="muted">Departments</span><strong id="department-count">—</strong></div>
    <div class="metric"><span class="muted">Agent profiles</span><strong id="agent-count">—</strong></div>
    <div class="metric"><span class="muted">Specialist roles</span><strong id="specialist-count">—</strong></div>
    <div class="metric"><span class="muted">Work items</span><strong id="work-count">—</strong></div>
    <div class="metric"><span class="muted">Model gateway</span><strong id="provider-state" style="font-size:1.05rem">—</strong></div>
  </section>
  <section class="panel">
    <div class="row"><h2 class="section-title" style="margin:0">Departments</h2><span class="pill">Original OpenCompany design</span></div>
    <div id="departments" class="list"><p class="muted">Connect to load departments.</p></div>
  </section>
  <section class="panel">
    <div class="row">
      <div><h2 class="section-title" style="margin:0">Company agent profiles</h2><p class="muted">CEO, managers and specialists are created as drafts; provisioning does not start workers.</p></div>
      <div class="auth"><button id="provision-executive" disabled>Provision CEO</button><button id="provision" disabled>Provision managers</button><button id="provision-specialists" disabled>Provision 500 specialists</button></div>
    </div>
    <div id="agents" class="list"><p class="muted">Connect to view manager profiles.</p></div>
  </section>
  <section class="panel">
    <h2 class="section-title" style="margin:0">AI capabilities</h2>
    <div id="capabilities" class="list"><p class="muted">Connect to inspect provider and media readiness.</p></div>
  </section>
  <section class="panel">
    <h2 class="section-title" style="margin:0">Work queue</h2>
    <div id="work-items" class="list"><p class="muted">Connect to view work items.</p></div>
  </section>
  <p class="muted" style="font-size:.8rem;margin:18px 4px">This console does not publish content, contact customers, spend money, deploy production, or activate agents. Protected actions remain owner-gated.</p>
</main>
<script>
(() => {
  const byId = (id) => document.getElementById(id);
  const keyInput = byId("owner-key");
  const message = byId("message");
  let csrfToken = "";
  const setMessage = (value, kind="muted") => { message.textContent=value; message.className=kind; };
  const clear = (id, label) => { byId(id).replaceChildren(); const p=document.createElement("p"); p.className="muted"; p.textContent=label; byId(id).append(p); };
  const addCard = (container, title, description, state) => {
    const card=document.createElement("article"); card.className="item";
    const row=document.createElement("div"); row.className="row";
    const heading=document.createElement("h3"); heading.textContent=title; row.append(heading);
    if(state){const badge=document.createElement("span");badge.className="pill";badge.textContent=state;row.append(badge);}
    card.append(row);
    if(description){const p=document.createElement("p");p.textContent=description;card.append(p);}
    container.append(card);
  };
  const request = async (path, options={}) => {
    const headers = new Headers(options.headers || {});
    const method=(options.method || "GET").toUpperCase();
    if(method!=="GET" && method!=="HEAD" && csrfToken) headers.set("X-CSRF-Token",csrfToken);
    if(options.body) headers.set("Content-Type","application/json");
    const response=await fetch(path,{...options,headers,credentials:"same-origin",cache:"no-store"});
    if(!response.ok) throw new Error(response.status===401?"Owner key rejected.":response.status===503?"Owner authentication is not configured on the server.":"Request failed ("+response.status+").");
    return response.json();
  };
  async function load(){
    byId("provision").disabled=true;
    setMessage("Loading owner records…");
    try{
      const [org,agents,work,provider,media,workforce]=await Promise.all([
        request("/organization/departments"),request("/agents"),request("/work-items"),
        request("/providers/status"),request("/media/capabilities"),request("/workforce/roles")
      ]);
      byId("department-count").textContent=org.count;
      byId("agent-count").textContent=agents.count;
      byId("specialist-count").textContent=workforce.specialist_count+" · "+workforce.team_count+" teams";
      byId("work-count").textContent=work.count;
      byId("provider-state").textContent=provider.gateway_enabled?"Free model configured":"Disabled";
      clear("departments","No departments returned.");
      org.departments.forEach(d=>addCard(byId("departments"),d.name,d.mission,d.role_keys.length+" role assignment(s)"));
      clear("agents","No manager profiles yet. Use Provision managers to create draft profiles.");
      agents.agents.forEach(a=>addCard(byId("agents"),a.name,a.department+" · "+a.capabilities.join(", "),a.state));
      clear("capabilities","No capability data returned.");
      addCard(byId("capabilities"),"Model gateway",provider.gateway_enabled?"Configured model: "+provider.model+". Live inference is not yet verified.":"No provider is active. Paid fallback is disabled.",provider.billing_mode);
      media.capabilities.forEach(v=>addCard(byId("capabilities"),v.display_name,v.generation_modes.join(", ")+". "+v.execution_requirements.join("; "),v.state));
      clear("work-items","No work items.");
      work.items.forEach(w=>{
        const card=document.createElement("article");card.className="item";
        const row=document.createElement("div");row.className="row";
        const heading=document.createElement("h3");heading.textContent=w.title;row.append(heading);
        const badge=document.createElement("span");badge.className="pill";badge.textContent=w.state;row.append(badge);
        card.append(row);
        const detail=document.createElement("p");detail.textContent=w.department+" · "+w.objective;card.append(detail);
        if(w.state==="review"){
          const actions=document.createElement("div");actions.className="auth";
          const view=document.createElement("button");view.textContent="View draft";
          view.addEventListener("click",async()=>{
            view.disabled=true;
            try{
              const result=await request("/work-items/"+w.id+"/deliverables");
              result.deliverables.forEach(d=>{
                const draft=document.createElement("pre");draft.style.whiteSpace="pre-wrap";draft.style.overflowWrap="anywhere";draft.textContent=d.content;card.append(draft);
              });
              if(result.count){
                const approve=document.createElement("button");approve.textContent="Approve draft";
                approve.addEventListener("click",async()=>{
                  approve.disabled=true;
                  try{await request("/work-items/"+w.id+"/review",{method:"POST",body:JSON.stringify({approved:true,rationale:"Approved by owner after dashboard review."})});setMessage("Draft approved and work completed.","success");await load();}
                  catch(error){setMessage(error.message,"error");approve.disabled=false;}
                });
                const revise=document.createElement("button");revise.textContent="Request revision";
                revise.addEventListener("click",async()=>{
                  revise.disabled=true;
                  try{await request("/work-items/"+w.id+"/review",{method:"POST",body:JSON.stringify({approved:false,rationale:"Please revise the draft and resubmit for owner review."})});setMessage("Revision requested. Work returned to READY.","success");await load();}
                  catch(error){setMessage(error.message,"error");revise.disabled=false;}
                });
                actions.append(approve,revise);
              }
            }catch(error){setMessage(error.message,"error");}
            finally{view.disabled=false;}
          });
          actions.append(view);card.append(actions);
        }
        byId("work-items").append(card);
      });
      byId("provision").disabled=false;
      byId("provision-executive").disabled=false;
      byId("provision-specialists").disabled=false;
      setMessage("Connected. Private records loaded. No agents were activated and no external actions were performed.","success");
    }catch(error){setMessage(error.message,"error");}
  }
  byId("connect").addEventListener("click",async()=>{
    const apiKey=keyInput.value.trim();
    if(!apiKey){setMessage("Enter the owner API key first.","error");return;}
    byId("connect").disabled=true;
    try{
      const response=await fetch("/auth/session",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",cache:"no-store",body:JSON.stringify({api_key:apiKey})});
      if(!response.ok) throw new Error(response.status===401?"Owner key rejected.":"Could not establish owner session.");
      const session=await response.json();csrfToken=session.csrf_token;keyInput.value="";await load();
    }catch(error){setMessage(error.message,"error");}
    finally{byId("connect").disabled=false;}
  });
  byId("disconnect").addEventListener("click",async()=>{
    try{if(csrfToken) await fetch("/auth/logout",{method:"POST",headers:{"X-CSRF-Token":csrfToken},credentials:"same-origin",cache:"no-store"});}
    finally{
      csrfToken="";keyInput.value="";
      ["departments","agents","capabilities","work-items"].forEach(id=>clear(id,"Disconnected."));
      ["department-count","agent-count","specialist-count","work-count","provider-state"].forEach(id=>byId(id).textContent="—");
      byId("provision").disabled=true;byId("provision-executive").disabled=true;byId("provision-specialists").disabled=true;setMessage("Disconnected. The server session has been revoked.");
    }
  });
  byId("provision").addEventListener("click",async()=>{
    byId("provision").disabled=true;
    try{const result=await request("/agents/bootstrap",{method:"POST",body:"{}"});setMessage(result.count+" department manager profiles are saved as drafts. No worker was started.","success");await load();}
    catch(error){setMessage(error.message,"error");byId("provision").disabled=false;}
  });
  byId("provision-executive").addEventListener("click",async()=>{
    byId("provision-executive").disabled=true;
    try{const result=await request("/agents/bootstrap-executive",{method:"POST",body:"{}"});setMessage(result.agent.name+" profile saved as a draft. No worker was started.","success");await load();}
    catch(error){setMessage(error.message,"error");byId("provision-executive").disabled=false;}
  });
  byId("provision-specialists").addEventListener("click",async()=>{
    byId("provision-specialists").disabled=true;
    try{const result=await request("/agents/bootstrap-specialists",{method:"POST",body:"{}"});setMessage(result.count+" specialist profiles saved as drafts. No workers were started.","success");await load();}
    catch(error){setMessage(error.message,"error");byId("provision-specialists").disabled=false;}
  });
})();
</script>
</body>
</html>"""
