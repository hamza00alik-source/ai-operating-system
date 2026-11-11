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
.owner-connection-title{font-size:1.05rem;margin:0 0 10px}.provider-state{font-size:1.05rem}.section-title.compact{margin:0}.research-results{white-space:pre-wrap;overflow-wrap:anywhere}.worker-actions{margin-top:12px}.console-footer{font-size:.8rem;margin:18px 4px}.confirmation-label{display:flex;gap:10px;align-items:center;margin:12px 0}.warn{color:#ffd58a}.error{color:#ff9c9c}.success{color:#91e0bd}.section-title{margin:22px 0 8px;font-size:1.15rem}
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
    <h2 class="owner-connection-title">Secure owner connection</h2>
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
    <div class="metric"><span class="muted">Queued tasks</span><strong id="queue-count">—</strong></div>
    <div class="metric"><span class="muted">Model gateway</span><strong id="provider-state" class="provider-state">—</strong></div>
  </section>
  <section class="panel">
    <div class="row"><h2 class="section-title compact">Departments</h2><span class="pill">Original OpenCompany design</span></div>
    <div id="departments" class="list"><p class="muted">Connect to load departments.</p></div>
  </section>
  <section class="panel">
    <div class="row">
      <div><h2 class="section-title compact">Company agent profiles</h2><p class="muted">CEO, managers and specialists are created as drafts; provisioning does not start workers.</p></div>
      <div class="auth"><button id="provision-executive" disabled>Provision CEO</button><button id="provision" disabled>Provision managers</button><button id="provision-specialists" disabled>Provision 500 specialists</button></div>
    </div>
    <div id="agents" class="list"><p class="muted">Connect to view manager profiles.</p></div>
  </section>
  <section class="panel">
    <h2 class="section-title compact">AI capabilities</h2>
    <div id="capabilities" class="list"><p class="muted">Connect to inspect provider and media readiness.</p></div>
  </section>
  <section class="panel">
    <h2 class="section-title">CEO objective planner</h2>
    <p class="muted">The active Chief Executive Orchestrator can turn an owner-approved objective into draft department tasks. Draft tasks are not queued or executed until you review them.</p>
    <label for="executive-title">Plan title</label>
    <input id="executive-title" maxlength="240" placeholder="Example: Launch an international digital product business">
    <label for="executive-objective">Company objective</label>
    <textarea id="executive-objective" rows="4" maxlength="12000" placeholder="Describe the outcome, constraints, audience, and success measures."></textarea>
    <button id="create-executive-plan" disabled>Create CEO draft plan</button>
  </section>
  <section class="panel">
    <div class="row"><h2 class="section-title">External research connector</h2><span id="api-anything-status" class="pill">Not configured</span></div>
    <p class="muted">API Anything is connected in read-only tier-one mode. This console can discover public operations and call them without browser automation or write permissions.</p>
    <label for="research-query">Search available research operations</label>
    <input id="research-query" maxlength="300" placeholder="Example: market demand, competitor reviews, software trends">
    <button id="search-research" disabled>Search research connector</button>
    <pre id="research-results" class="muted research-results">No research results loaded.</pre>
  </section>
  <section class="panel">
    <h2 class="section-title">AI code evolution</h2>
    <p class="muted">Ask the free model to propose edits to up to three selected source, test, or documentation files. OpenCompany writes only an isolated feature branch and a DRAFT GitHub pull request; it never merges or deploys the change.</p>
    <label for="code-problem">Problem to solve</label>
    <textarea id="code-problem" rows="3" maxlength="3000" placeholder="Describe a specific bug, reliability gap, or improvement supported by evidence."></textarea>
    <label for="code-paths">File paths (comma-separated; source, tests, or docs only)</label>
    <input id="code-paths" placeholder="src/opencompany_core/example.py, tests/test_example.py">
    <button id="create-code-pr" disabled>Generate isolated code PR</button>
    <div id="code-pr-result" class="muted" aria-live="polite"></div>
  </section>
  <section class="panel">
    <h2 class="section-title">Learning and improvement proposals</h2>
    <p class="muted">Owner-reviewed evaluations can produce AI improvement proposals. Approved role notes are injected into future specialist prompts; proposals are not applied before owner approval.</p>
    <div id="learning-proposals" class="stack"><p class="muted">No proposals loaded.</p></div>
  </section>
  <section class="panel">
    <div class="row"><h2 class="section-title compact">Work queue</h2><span id="worker-status" class="pill">Workers stopped</span></div>
    <div class="auth worker-actions"><button id="start-workers" disabled>Start worker fleet</button><button id="stop-workers" disabled>Stop worker fleet</button></div>
    <div id="work-items" class="list"><p class="muted">Connect to view work items.</p></div>
  </section>
  <p class="muted console-footer">This console does not publish content, contact customers, spend money, or deploy production. Agent activation, task admission, and worker startup remain owner-gated.</p>
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
      const [org,agents,work,provider,media,workforce,queue,fleet,learning,codeEvolution,apiAnything]=await Promise.all([
        request("/organization/departments"),request("/agents"),request("/work-items"),
        request("/providers/status"),request("/media/capabilities"),request("/workforce/roles"),request("/workers/queue"),request("/workers/status"),request("/learning/proposals"),request("/code-evolution/config-status"),request("/integrations/api-anything/status")
      ]);
      byId("department-count").textContent=org.count;
      byId("agent-count").textContent=agents.count;
      byId("specialist-count").textContent=workforce.specialist_count+" · "+workforce.team_count+" teams";
      byId("work-count").textContent=work.count;
      byId("provider-state").textContent=provider.gateway_enabled?"Free model configured":"Disabled";
      byId("queue-count").textContent=queue.counts.queued||0;
      byId("worker-status").textContent=fleet.running?"Workers running · "+fleet.concurrency+" threads":"Workers stopped · "+fleet.concurrency+" configured";
      byId("start-workers").disabled=fleet.running;
      byId("stop-workers").disabled=!fleet.running;
      byId("create-executive-plan").disabled=!agents.agents.some(a=>a.role_key==="chief_executive_orchestrator" && a.state==="active");
      byId("api-anything-status").textContent=apiAnything.enabled?(apiAnything.healthy===false?"Connector error":"Read-only connected"):"Not configured";
      byId("search-research").disabled=!apiAnything.enabled || apiAnything.healthy===false;
      byId("create-code-pr").disabled=!codeEvolution.enabled;
      byId("code-pr-result").textContent=codeEvolution.enabled?"Verified · "+codeEvolution.repository+" · branch "+codeEvolution.base_branch:(codeEvolution.configured?(codeEvolution.access_verified&&!codeEvolution.provider_verified?"GitHub access verified. Run the live zero-cost UnoRouter test before creating draft PRs.":"Token saved but repository access is not verified. Test GitHub access in Integrations before creating draft PRs."):"GitHub code-evolution credentials are not configured on the server.");
      clear("learning-proposals","No learning proposals yet.");
      learning.proposals.forEach(proposal=>{
        const card=document.createElement("article");card.className="item";
        const title=document.createElement("h3");title.textContent=proposal.target+" · "+proposal.state;card.append(title);
        const summary=document.createElement("p");summary.textContent=proposal.change_summary;card.append(summary);
        const rationale=document.createElement("p");rationale.textContent=proposal.rationale;card.append(rationale);
        if(proposal.state==="proposed"){
          const approve=document.createElement("button");approve.textContent="Approve learning proposal";
          approve.addEventListener("click",async()=>{approve.disabled=true;try{await request("/learning/proposals/"+proposal.id+"/decision",{method:"POST",body:JSON.stringify({approved:true,rationale:"Approved by owner for role-level learning."})});await load();}catch(error){setMessage(error.message,"error");approve.disabled=false;}});
          const reject=document.createElement("button");reject.textContent="Reject";
          reject.addEventListener("click",async()=>{reject.disabled=true;try{await request("/learning/proposals/"+proposal.id+"/decision",{method:"POST",body:JSON.stringify({approved:false,rationale:"Not approved for role-level learning."})});await load();}catch(error){setMessage(error.message,"error");reject.disabled=false;}});
          card.append(approve,reject);
        }else if(proposal.state==="approved"){
          const apply=document.createElement("button");apply.textContent="Apply approved role note";
          apply.addEventListener("click",async()=>{apply.disabled=true;try{await request("/learning/proposals/"+proposal.id+"/apply-note",{method:"POST",body:"{}"});setMessage("Approved learning note is now available to future "+proposal.target+" tasks.","success");await load();}catch(error){setMessage(error.message,"error");apply.disabled=false;}});
          card.append(apply);
        }
        byId("learning-proposals").append(card);
      });
      clear("departments","No departments returned.");
      org.departments.forEach(d=>{
        addCard(byId("departments"),d.name,d.mission,d.role_keys.length+" role assignment(s)");
        const departmentCard=byId("departments").lastElementChild;
        const draftProfiles=agents.agents.filter(a=>a.department===d.key && a.state==="draft");
        if(!draftProfiles.length)return;
        const departmentButton=document.createElement("button");
        departmentButton.textContent="Activate all "+draftProfiles.length+" draft profile(s) in department";
        departmentButton.addEventListener("click",async()=>{
          departmentButton.disabled=true;
          try{
            const result=await request("/agents/activate",{method:"POST",body:JSON.stringify({department:d.key})});
            setMessage(result.activated_count+" profiles activated in "+d.name+". Workers were not started and no tasks were queued.","success");
            await load();
          }catch(error){setMessage(error.message,"error");departmentButton.disabled=false;}
        });
        departmentCard.append(departmentButton);
        const byTeam=new Map();
        draftProfiles.forEach(profile=>{
          if(!byTeam.has(profile.team_key))byTeam.set(profile.team_key,[]);
          byTeam.get(profile.team_key).push(profile);
        });
        byTeam.forEach((profiles,teamKey)=>{
          const teamButton=document.createElement("button");
          teamButton.style.margin="8px 6px 0 0";
          teamButton.textContent="Activate "+teamKey+" ("+profiles.length+")";
          teamButton.addEventListener("click",async()=>{
            teamButton.disabled=true;
            try{
              const result=await request("/agents/activate",{method:"POST",body:JSON.stringify({department:d.key,team_key:teamKey})});
              setMessage(result.activated_count+" profiles activated in "+d.name+" / "+teamKey+". Workers were not started.","success");
              await load();
            }catch(error){setMessage(error.message,"error");teamButton.disabled=false;}
          });
          departmentCard.append(teamButton);
        });
      });
      clear("agents","No agent profiles yet. Provision the CEO, managers and specialists first.");
      agents.agents.forEach(a=>{
        const card=document.createElement("article");card.className="item";
        const row=document.createElement("div");row.className="row";
        const heading=document.createElement("h3");heading.textContent=a.name;row.append(heading);
        const badge=document.createElement("span");badge.className="pill";badge.textContent=a.state;row.append(badge);
        card.append(row);
        const detail=document.createElement("p");detail.textContent=a.department+" · "+(a.role_key||"unassigned role")+" · "+(a.team_key||"unassigned team");card.append(detail);
        if(a.state==="draft" || a.state==="paused"){
          const activate=document.createElement("button");activate.textContent="Activate agent";
          activate.addEventListener("click",async()=>{activate.disabled=true;try{await request("/agents/"+a.id+"/state",{method:"POST",body:JSON.stringify({target_state:"active",expected_revision:a.revision})});setMessage(a.name+" activated. No task was automatically queued.","success");await load();}catch(error){setMessage(error.message,"error");activate.disabled=false;}});
          card.append(activate);
        }else if(a.state==="active"){
          const pause=document.createElement("button");pause.textContent="Pause agent";
          pause.addEventListener("click",async()=>{pause.disabled=true;try{await request("/agents/"+a.id+"/state",{method:"POST",body:JSON.stringify({target_state:"paused",expected_revision:a.revision})});setMessage(a.name+" paused.","success");await load();}catch(error){setMessage(error.message,"error");pause.disabled=false;}});
          card.append(pause);
        }
        byId("agents").append(card);
      });
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
        if((w.state==="draft" || w.state==="ready") && !w.assigned_agent_id){
          const managerButton=document.createElement("button");managerButton.textContent="Ask department manager";
          managerButton.addEventListener("click",async()=>{
            managerButton.disabled=true;
            try{
              const result=await request("/work-items/"+w.id+"/manager-proposal",{method:"POST",body:JSON.stringify({max_specialists:5})});
              const proposal=result.proposal;
              const note=document.createElement("p");note.textContent="Manager recommendation ("+result.manager_ai.provider+"): "+result.manager_ai.rationale;card.append(note);
              const roster=document.createElement("p");roster.textContent="Recommended team: "+(proposal.children||[]).map(child=>child.role_key).join(", ");card.append(roster);
              if(proposal.children && proposal.children.length){
                const approveTeam=document.createElement("button");approveTeam.textContent="Approve team and create assigned drafts";
                approveTeam.addEventListener("click",async()=>{
                  approveTeam.disabled=true;
                  try{await request("/work-items/"+w.id+"/delegation-proposals/"+proposal.id+"/approve",{method:"POST",body:"{}"});setMessage("Owner approved manager proposal. Assigned child tasks are READY but not queued.","success");await load();}
                  catch(error){setMessage(error.message,"error");approveTeam.disabled=false;}
                });
                card.append(approveTeam);
              }else{
                const warning=document.createElement("p");warning.textContent="Manager recommends owner review; no team was assigned.";card.append(warning);
              }
            }catch(error){setMessage(error.message,"error");managerButton.disabled=false;}
          });
          card.append(managerButton);
        }
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
        if(w.state==="ready" && w.assigned_agent_id){
          const queueButton=document.createElement("button");queueButton.textContent="Admit to worker queue";
          queueButton.addEventListener("click",async()=>{queueButton.disabled=true;try{await request("/work-items/"+w.id+"/enqueue",{method:"POST",body:"{}"});setMessage("Task admitted to the durable queue. No worker was started by this action.","success");await load();}catch(error){setMessage(error.message,"error");queueButton.disabled=false;}});
          card.append(queueButton);
        }
        if(w.state==="queued" && w.assigned_agent_id){
          const runButton=document.createElement("button");runButton.textContent="Run one worker cycle";
          runButton.addEventListener("click",async()=>{runButton.disabled=true;try{const result=await request("/workers/"+w.assigned_agent_id+"/run-once",{method:"POST",body:"{}"});setMessage("Worker cycle result: "+result.result,"success");await load();}catch(error){setMessage(error.message,"error");runButton.disabled=false;}});
          card.append(runButton);
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
      ["department-count","agent-count","specialist-count","work-count","queue-count","provider-state"].forEach(id=>byId(id).textContent="—");
      byId("provision").disabled=true;byId("provision-executive").disabled=true;byId("provision-specialists").disabled=true;byId("start-workers").disabled=true;byId("stop-workers").disabled=true;byId("create-executive-plan").disabled=true;byId("create-code-pr").disabled=true;byId("search-research").disabled=true;setMessage("Disconnected. The server session has been revoked.");
    }
  });
  byId("search-research").addEventListener("click",async()=>{
    const query=byId("research-query").value.trim();
    if(!query){setMessage("Enter a research query.","error");return;}
    byId("search-research").disabled=true;
    try{
      const result=await request("/integrations/api-anything/find?q="+encodeURIComponent(query));
      byId("research-results").textContent=JSON.stringify(result,null,2);
      setMessage("Research operations discovered. No external write actions were performed.","success");
    }catch(error){setMessage(error.message,"error");}
    finally{byId("search-research").disabled=false;}
  });
  byId("create-code-pr").addEventListener("click",async()=>{
    const problem=byId("code-problem").value.trim();
    const filePaths=byId("code-paths").value.split(",").map(value=>value.trim()).filter(Boolean);
    if(!problem||!filePaths.length){setMessage("Describe the problem and select one to three files.","error");return;}
    byId("create-code-pr").disabled=true;
    try{
      const result=await request("/code-evolution/proposals",{method:"POST",body:JSON.stringify({problem,file_paths:filePaths})});
      const link=document.createElement("a");link.href=result.url;link.textContent="Open draft pull request #"+result.pull_request_number;link.target="_blank";link.rel="noopener noreferrer";
      const output=byId("code-pr-result");output.replaceChildren(link);
      setMessage("AI code proposal committed to an isolated branch. GitHub Actions and owner review are required; nothing was merged or deployed.","success");
      byId("code-problem").value="";
    }catch(error){setMessage(error.message,"error");}
    finally{byId("create-code-pr").disabled=false;}
  });
  byId("create-executive-plan").addEventListener("click",async()=>{
    const title=byId("executive-title").value.trim();
    const objective=byId("executive-objective").value.trim();
    if(!title||!objective){setMessage("Enter a plan title and objective.","error");return;}
    byId("create-executive-plan").disabled=true;
    try{
      const result=await request("/executive/plan",{method:"POST",body:JSON.stringify({title,objective,max_tasks:8})});
      setMessage("CEO created "+result.created_count+" draft tasks. Review them in Work queue before moving any to READY.","success");
      byId("executive-title").value="";byId("executive-objective").value="";
      await load();
    }catch(error){setMessage(error.message,"error");byId("create-executive-plan").disabled=false;}
  });
  byId("start-workers").addEventListener("click",async()=>{
    byId("start-workers").disabled=true;
    try{await request("/workers/start",{method:"POST",body:"{}"});setMessage("Worker fleet started. It will process only owner-admitted tasks assigned to ACTIVE profiles.","success");await load();}
    catch(error){setMessage(error.message,"error");byId("start-workers").disabled=false;}
  });
  byId("stop-workers").addEventListener("click",async()=>{
    byId("stop-workers").disabled=true;
    try{await request("/workers/stop",{method:"POST",body:"{}"});setMessage("Worker fleet stopped.","success");await load();}
    catch(error){setMessage(error.message,"error");byId("stop-workers").disabled=false;}
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
