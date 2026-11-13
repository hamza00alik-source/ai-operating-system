APPROVAL_INBOX_HTML = r'''
<section class="panel" id="company-approval-inbox">
  <div class="row"><div><h2 class="section-title compact">Company-wide approval inbox</h2><p class="muted">One owner queue for manager proposals, deliverable reviews, and Product &amp; R&amp;D checkpoints. Every decision uses the existing owner-authenticated workflow.</p></div><span class="pill">Owner decision required</span></div>
  <div class="row" style="margin-top:12px"><label for="approval-inbox-business">Business unit</label><select id="approval-inbox-business"><option value="all">All business units</option><option value="core">Core / internal</option><option value="physical-agency">Physical-products agency</option><option value="physical-brand">Own physical-product brand</option><option value="digital-products">Digital products</option></select><button id="approval-inbox-refresh" type="button">Refresh inbox</button></div>
  <div class="grid"><div class="metric"><span class="muted">Pending decisions</span><strong id="approval-inbox-count">—</strong></div><div class="metric"><span class="muted">Manager proposals</span><strong id="approval-inbox-proposals">—</strong></div><div class="metric"><span class="muted">Deliverable reviews</span><strong id="approval-inbox-reviews">—</strong></div><div class="metric"><span class="muted">Product checkpoints</span><strong id="approval-inbox-products">—</strong></div></div>
  <div id="approval-inbox-items" class="list"><p class="muted">Connect as owner to load approval items.</p></div>
  <div class="item" id="external-approval-create">
    <h3>Register an external-action request</h3>
    <p class="muted">Creates an approval record only. It does not publish, send, purchase, pay, deploy, or change accounts.</p>
    <label for="external-approval-business">Business unit</label>
    <select id="external-approval-business"><option value="core">Core / internal</option><option value="physical-agency">Physical-products agency</option><option value="physical-brand">Own physical-product brand</option><option value="digital-products">Digital products</option></select>
    <label for="external-approval-type">Action type</label>
    <select id="external-approval-type"><option value="publish_listing">Publish listing</option><option value="send_customer_message">Send customer message</option><option value="make_customer_commitment">Make customer commitment</option><option value="purchase">Purchase</option><option value="payment">Payment</option><option value="production_change">Production change</option><option value="credential_change">Credential change</option><option value="account_change">Account change</option><option value="deploy_production">Production deployment</option><option value="delete_customer_data">Delete customer data</option><option value="other">Other external action</option></select>
    <label for="external-approval-title">Request title</label><input id="external-approval-title" maxlength="200" placeholder="What action is being requested?">
    <label for="external-approval-description">Details and exact scope</label><textarea id="external-approval-description" rows="3" maxlength="4000" placeholder="Describe target, scope, expected result, risks, and any customer or financial impact. Do not enter passwords or payment credentials."></textarea>
    <button id="external-approval-submit" type="button">Create pending approval request</button>
    <p id="external-approval-create-status" class="muted"></p>
  </div>
  <p class="muted">Authorization records are not execution. Each real external action still needs its own reviewed, scope-limited executor and a separate execution record.</p>
</section>
'''

APPROVAL_INBOX_JS = r'''
  async function loadCompanyApprovalInbox(){
    const host=byId("approval-inbox-items");
    if(!csrfToken){host.textContent="Connect as owner to load approval items.";return;}
    host.replaceChildren();
    const business=byId("approval-inbox-business").value;
    const units=business==="all"?["core","physical-agency","physical-brand","digital-products"]:[business];
    const pending=[];
    let proposalScans=0;
    const addText=(parent,tag,value,className)=>{const el=document.createElement(tag);if(className)el.className=className;el.textContent=value||"";parent.append(el);return el;};
    const action=(parent,label,fn)=>{const b=document.createElement("button");b.type="button";b.textContent=label;b.addEventListener("click",async()=>{b.disabled=true;try{await fn();await loadCompanyApprovalInbox();setMessage("Approval inbox refreshed. The selected owner decision was recorded through its existing workflow.","success");}catch(e){setMessage(e.message,"error");b.disabled=false;}});parent.append(b);};
    try{
      for(const unit of units){
        const work=await request("/work-items?business_id="+encodeURIComponent(unit));
        for(const item of (work.items||[])){
          if(item.state==="review"){
            pending.push({kind:"deliverable",business:unit,title:item.title,summary:item.objective||"",created:item.created_at,id:item.id});
          }
          if(item.state==="draft"&&proposalScans<100){
            proposalScans++;
            try{
              const detail=await request("/work-items/"+item.id+"/workflow");
              for(const proposal of (detail.delegation_proposals||[])){
                if(proposal.status==="draft"){
                  pending.push({kind:"proposal",business:unit,title:item.title,summary:(proposal.payload&&proposal.payload.request&&proposal.payload.request.manager_rationale)||"Manager proposal awaiting owner review.",created:proposal.created_at,id:item.id,proposal});
                }
              }
            }catch(_){}
          }
        }
      }
      for(const unit of units.filter(value=>value!=="core")){
        const result=await request("/product-rd/workflows?business_id="+encodeURIComponent(unit));
        for(const workflow of (result.workflows||[])){
          const preview=workflow.stages.find(s=>s.key==="human_preview"&&s.status==="in_progress");
          const executive=workflow.stages.find(s=>s.key==="ceo_review"&&s.status==="in_progress");
          if(preview)pending.push({kind:"product-preview",business:unit,title:workflow.title,summary:"Human preview checkpoint: inspect the generated artifact and record the owner decision in Product & R&D.",id:workflow.id});
          if(executive)pending.push({kind:"product-ceo",business:unit,title:workflow.title,summary:"Internal CEO review checkpoint. This is not marketplace publishing or customer approval.",id:workflow.id});
        }
      }
      if(proposalScans===100)addText(host,"p","Proposal scan capped at 100 draft work items for dashboard responsiveness. Narrow the business filter if older proposals may be pending.","warn");
      for(const unit of units){
        const external=await request("/external-approvals?business_id="+encodeURIComponent(unit)+"&status=pending");
        for(const item of (external.requests||[])){
          pending.push({kind:"external",business:unit,title:item.title,summary:item.description,
            created:item.requested_at,id:item.id,external:item});
        }
      }
      pending.sort((a,b)=>String(b.created||"").localeCompare(String(a.created||"")));
      byId("approval-inbox-count").textContent=String(pending.length);
      byId("approval-inbox-proposals").textContent=String(pending.filter(x=>x.kind==="proposal").length);
      byId("approval-inbox-reviews").textContent=String(pending.filter(x=>x.kind==="deliverable").length);
      byId("approval-inbox-products").textContent=String(pending.filter(x=>x.kind.startsWith("product-")).length);
      if(!pending.length){addText(host,"p","No pending owner decisions were found for the selected business scope.","muted");return;}
      for(const entry of pending){
        const card=document.createElement("article");card.className="item";
        const labels={proposal:"Manager proposal",deliverable:"Deliverable review","product-preview":"Human preview","product-ceo":"CEO review",external:"External-action authorization"};
        const heading=addText(card,"h3",entry.title);
        addText(card,"p",labels[entry.kind]+" · "+entry.business+" · "+(entry.created||"Current checkpoint"),"muted");
        addText(card,"p",entry.summary);
        if(entry.kind==="external"){
          const requestData=entry.external;
          addText(card,"p","Action: "+requestData.action_type.replaceAll("_"," ")+" · Status: "+requestData.status);
          addText(card,"p","Target: "+(requestData.target_reference||"Not specified")+
            (requestData.estimated_amount_minor!==null&&requestData.estimated_amount_minor!==undefined
              ? " · Amount (minor units): "+requestData.estimated_amount_minor+" "+requestData.currency : ""));
          addText(card,"p","Requested by: "+requestData.requested_by+" · No executor is connected.");
          action(card,"Authorize (record only)",async()=>{
            const rationale=window.prompt("Explain exactly what you are authorizing. This records authorization only; it will NOT execute the action.");
            if(!rationale||!rationale.trim())throw new Error("Authorization cancelled; no decision was recorded.");
            const confirmAction=window.prompt("Type AUTHORIZE to confirm this authorization record.");
            await request("/external-approvals/"+entry.id+"/decision",{method:"POST",body:JSON.stringify({decision:"approve",rationale:rationale.trim(),confirm_action:confirmAction||""})});
          });
          action(card,"Reject request",async()=>{
            const rationale=window.prompt("Reason for rejecting this request.");
            if(!rationale||!rationale.trim())return;
            await request("/external-approvals/"+entry.id+"/decision",{method:"POST",body:JSON.stringify({decision:"reject",rationale:rationale.trim()})});
          });
        }else if(entry.kind==="proposal"){
          const proposal=entry.proposal, payload=proposal.payload||{}, requestData=payload.request||{};
          addText(card,"p","Manager: "+(proposal.manager_agent_id||payload.manager_agent_id||"not recorded")+" · Mode: "+(proposal.mode||"unknown")+" · Proposed tasks: "+((proposal.children||[]).length));
          if(requestData.required_capabilities) addText(card,"p","Capabilities: "+requestData.required_capabilities.join(", "));
          if(proposal.mode==="owner_review"||!(proposal.children||[]).length){
            addText(card,"p","Blocked: clarification or a complete team is required. This proposal cannot be approved here.","warn");
          }else{
            addText(card,"p","Approval creates READY delegation tasks only. It does not queue tasks, start agents, or publish.");
            action(card,"Approve manager proposal",async()=>{await request("/work-items/"+entry.id+"/delegation-proposals/"+proposal.id+"/approve",{method:"POST",body:"{}"});});
          }
        }else if(entry.kind==="deliverable"){
          action(card,"Open and review deliverable",async()=>{
            const result=await request("/work-items/"+entry.id+"/deliverables");
            const detail=document.createElement("div");detail.className="item";
            (result.deliverables||[]).forEach(d=>{addText(detail,"h4",d.title||"Submitted deliverable");const pre=addText(detail,"pre",d.content||"");pre.style.whiteSpace="pre-wrap";pre.style.overflowWrap="anywhere";});
            if(result.count){
              const approve=document.createElement("button");approve.textContent="Approve deliverable";approve.addEventListener("click",async()=>{approve.disabled=true;try{await request("/work-items/"+entry.id+"/review",{method:"POST",body:JSON.stringify({approved:true,rationale:"Approved by owner in the company-wide approval inbox."})});await loadCompanyApprovalInbox();setMessage("Deliverable approved through the existing owner-review workflow.","success");}catch(e){setMessage(e.message,"error");approve.disabled=false;}});detail.append(approve);
              const revise=document.createElement("button");revise.textContent="Request revision";revise.addEventListener("click",async()=>{revise.disabled=true;try{await request("/work-items/"+entry.id+"/review",{method:"POST",body:JSON.stringify({approved:false,rationale:"Please revise and resubmit for owner review."})});await loadCompanyApprovalInbox();setMessage("Revision requested through the existing owner-review workflow.","success");}catch(e){setMessage(e.message,"error");revise.disabled=false;}});detail.append(revise);
            }
            card.append(detail);
          });
        }else{
          addText(card,"p","Open the Product & R&D studio below to inspect evidence and use its existing owner checkpoint controls.","muted");
          action(card,"Open Product & R&D checkpoint",async()=>{byId("product-rd-panel").scrollIntoView({behavior:"smooth",block:"start"});});
        }
        host.append(card);
      }
    }catch(error){addText(host,"p","Could not load the full approval inbox: "+error.message,"error");}
  }
  byId("approval-inbox-refresh").addEventListener("click",loadCompanyApprovalInbox);
  byId("approval-inbox-business").addEventListener("change",loadCompanyApprovalInbox);
  byId("external-approval-submit").addEventListener("click",async()=>{
    const button=byId("external-approval-submit"),status=byId("external-approval-create-status");
    button.disabled=true;status.textContent="Creating pending approval record…";
    try{
      const result=await request("/external-approvals",{method:"POST",body:JSON.stringify({
        business_id:byId("external-approval-business").value,
        action_type:byId("external-approval-type").value,
        title:byId("external-approval-title").value,
        description:byId("external-approval-description").value,
        requested_by:"owner"
      })});
      status.textContent="Pending request created: "+result.request_id+". No external action was executed.";
      byId("external-approval-title").value="";byId("external-approval-description").value="";
      await loadCompanyApprovalInbox();
    }catch(error){status.textContent=error.message;}
    finally{button.disabled=false;}
  });
'''
