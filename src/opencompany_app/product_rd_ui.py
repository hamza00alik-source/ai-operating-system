PRODUCT_RD_HTML = r'''
<section class="panel" id="product-rd-panel">
  <div class="row"><div><h2 class="section-title compact">Product &amp; R&amp;D studio</h2><p class="muted">Create internal products, delegate research and planning to approved OpenCompany roles, generate local prototypes, inspect QA evidence, and prepare listing drafts. Publishing remains disabled.</p></div><span class="pill">USD 0 ceiling · owner-gated</span></div>
  <label for="prd-business">Business unit</label>
  <select id="prd-business"><option value="digital-products" selected>Digital products</option><option value="physical-agency">Physical-products agency</option><option value="physical-brand">Own physical-product brand</option></select>
  <label for="prd-title">Product / project title</label>
  <input id="prd-title" maxlength="240" placeholder="OUTPOST Sci-Fi Survival UI Icon Pack">
  <label for="prd-brief">Product brief</label>
  <textarea id="prd-brief" rows="4" maxlength="12000" placeholder="Describe the target buyer, problem, product deliverables, formats, quality criteria, and constraints."></textarea>
  <button id="prd-create" disabled>Create Product &amp; R&amp;D workflow</button>
  <div id="prd-workflows" class="list"><p class="muted">Connect to load Product &amp; R&amp;D workflows.</p></div>
</section>
'''

PRODUCT_RD_JS = r'''

  async function loadProductRD(){
    if(!csrfToken)return;
    const business=byId("prd-business").value;
    const result=await request("/product-rd/workflows?business_id="+encodeURIComponent(business));
    const host=byId("prd-workflows");host.replaceChildren();
    if(!result.count){const p=document.createElement("p");p.className="muted";p.textContent="No Product & R&D workflows for this business unit yet.";host.append(p);}
    for(const workflow of result.workflows){
      const card=document.createElement("article");card.className="item";
      const heading=document.createElement("h3");heading.textContent=workflow.title;card.append(heading);
      const meta=document.createElement("p");meta.textContent=workflow.business_id+" · "+workflow.status+" · cost ceiling USD "+workflow.cost_ceiling_usd;card.append(meta);
      const active=workflow.stages.find(s=>s.status==="in_progress");
      const blocked=workflow.stages.find(s=>s.status==="blocked");
      const stageLine=document.createElement("p");stageLine.textContent=active?"Active stage: "+active.key:(blocked?"Blocked at: "+blocked.key:"No active stage");card.append(stageLine);
      const stageList=document.createElement("p");stageList.className="muted";stageList.textContent=workflow.stages.map(s=>s.key.replaceAll("_"," ")+": "+s.status).join("  ·  ");card.append(stageList);
      const qaStage=workflow.stages.find(s=>s.key==="automated_qa"&&s.qa_result);
      if(qaStage){
        const qaText=document.createElement("p");qaText.textContent="Automated QA passed: "+qaStage.qa_result.passed_checks.length+" · failed: "+qaStage.qa_result.failed_checks.length;card.append(qaText);
        if(qaStage.qa_result.untested_claims&&qaStage.qa_result.untested_claims.length){
          const untested=document.createElement("p");untested.className="warn";untested.textContent="Still untested: "+qaStage.qa_result.untested_claims.join("; ");card.append(untested);
        }
      }
      const actions=document.createElement("div");actions.className="auth";
      const actionButton=(label,fn)=>{const b=document.createElement("button");b.type="button";b.textContent=label;b.addEventListener("click",async()=>{b.disabled=true;try{await fn();await loadProductRD();setMessage("Product & R&D workflow updated. No external action was performed.","success");}catch(e){setMessage(e.message,"error");b.disabled=false;try{await loadProductRD();}catch{}}});actions.append(b);return b;};
      const addLink=(label,url)=>{const a=document.createElement("a");a.href=url;a.textContent=label;a.target="_blank";a.rel="noopener noreferrer";a.style.color="#9cc7ff";a.style.marginRight="12px";card.append(a);};
      if(active){
        if(["opportunity_brief","product_specification","production_plan","packaging","listing_packet","ceo_review"].includes(active.key)){
          if(!active.work_item_id){
            actionButton("Delegate stage to OpenCompany agent",async()=>{await request("/product-rd/workflows/"+workflow.id+"/delegate-stage",{method:"POST",body:"{}"});});
          }else{
            const wi=await request("/work-items/"+active.work_item_id+"/workflow");
            const item=wi.work_item;
            const task=document.createElement("p");task.textContent="Stage task: "+item.id+" · "+item.state+" · "+(item.assigned_agent_id||"awaiting team assignment");card.append(task);
            const proposals=wi.delegation_proposals||[];
            const draftProposal=proposals.find(p=>p.status==="draft");
            const approvedProposal=proposals.find(p=>p.status==="approved");
            const runOnce=async(workItem)=>{
              if(workItem.state==="draft")await request("/work-items/"+workItem.id+"/transition",{method:"POST",body:JSON.stringify({target_state:"ready"})});
              if(workItem.state==="draft"||workItem.state==="ready")await request("/work-items/"+workItem.id+"/enqueue",{method:"POST",body:"{}"});
              await request("/workers/"+workItem.assigned_agent_id+"/run-once",{method:"POST",body:"{}"});
            };
            if(item.state==="draft"&&!item.assigned_agent_id){
              if(!draftProposal){
                actionButton("Ask department manager to plan specialist team",async()=>{
                  await request("/work-items/"+item.id+"/manager-proposal",{method:"POST",body:JSON.stringify({max_specialists:5})});
                });
              }else{
                const summary=document.createElement("p");summary.textContent="Manager proposal: "+draftProposal.mode+" · "+draftProposal.children.length+" proposed specialist task(s).";card.append(summary);
                if(draftProposal.mode==="owner_review"||!draftProposal.children.length){
                  const blockedPlan=document.createElement("p");blockedPlan.className="warn";blockedPlan.textContent="The manager could not safely form a complete team. Improve the brief or resolve missing role profiles before continuing.";card.append(blockedPlan);
                }else{
                  actionButton("Approve manager's team proposal",async()=>{
                    await request("/work-items/"+item.id+"/delegation-proposals/"+draftProposal.id+"/approve",{method:"POST",body:"{}"});
                  });
                }
              }
            }else if(item.state==="draft"&&item.assigned_agent_id){
              actionButton("Approve, enqueue & run CEO review once",async()=>{await runOnce(item);});
            }
            const children=wi.child_work_items||[];
            for(const child of children){
              const childLine=document.createElement("p");childLine.textContent="Team task: "+child.title+" · "+child.state+" · "+child.role_key;card.append(childLine);
              if(child.state==="ready"){
                actionButton("Run specialist: "+child.role_key,async()=>{await runOnce(child);});
              }else if(child.state==="queued"){
                actionButton("Run queued specialist: "+child.role_key,async()=>{await request("/workers/"+child.assigned_agent_id+"/run-once",{method:"POST",body:"{}"});});
              }else if(child.state==="review"){
                actionButton("Approve specialist: "+child.role_key,async()=>{await request("/work-items/"+child.id+"/review",{method:"POST",body:JSON.stringify({approved:true,rationale:"Owner reviewed this internal Product & R&D specialist deliverable."})});});
              }
            }
            if(item.state==="ready"){
              const allChildrenDone=children.length>0&&children.every(child=>child.state==="completed");
              if(item.depends_on.length===0||allChildrenDone){
                actionButton("Enqueue & run stage manager once",async()=>{await runOnce(item);});
              }else{
                const waiting=document.createElement("p");waiting.className="muted";waiting.textContent="Manager synthesis waits for every specialist deliverable to be owner-approved.";card.append(waiting);
              }
            }else if(item.state==="queued"){
              actionButton("Run stage manager once",async()=>{await request("/workers/"+item.assigned_agent_id+"/run-once",{method:"POST",body:"{}"});});
            }else if(item.state==="review"){
              actionButton("Approve stage manager deliverable",async()=>{await request("/work-items/"+item.id+"/review",{method:"POST",body:JSON.stringify({approved:true,rationale:"Owner reviewed the internal Product & R&D stage deliverable."})});});
            }else if(item.state==="completed"){
              actionButton("Sync approved deliverable to stage",async()=>{await request("/product-rd/workflows/"+workflow.id+"/sync-stage",{method:"POST",body:"{}"});});
            }else if(item.state==="in_progress"){
              const status=document.createElement("p");status.className="muted";status.textContent="Agent execution is in progress. Refresh after the worker finishes.";card.append(status);
            }
          }
        }else if(active.key==="artifact_generation"){
          if(workflow.business_id==="digital-products"&&workflow.title.toLowerCase().includes("outpost")){
            actionButton("Generate OUTPOST prototype & run QA",async()=>{await request("/product-rd/workflows/"+workflow.id+"/generate-pilot",{method:"POST",body:"{}"});});
          }else{
            const unavailable=document.createElement("p");unavailable.className="warn";unavailable.textContent="No deterministic artifact generator is configured for this product yet. The OUTPOST prototype generator is the only current pilot.";card.append(unavailable);
          }
        }else if(active.key==="human_preview"){
          actionButton("Confirm human preview review",async()=>{await request("/product-rd/workflows/"+workflow.id+"/stages/human_preview/complete",{method:"POST",body:JSON.stringify({output:"Owner reviewed the generated SVG contact sheet. This is a human visual checkpoint, not engine or legal approval.",evidence:["Owner visually inspected the preview contact sheet."]})});});
          addLink("Open SVG preview","/product-rd/workflows/"+workflow.id+"/artifacts/preview.svg");
        }
      }
      if(blocked){
        const reason=document.createElement("p");reason.className="error";reason.textContent="QA blockers: "+(blocked.blockers||[]).join("; ");card.append(reason);
        actionButton("Return to artifact production",async()=>{await request("/product-rd/workflows/"+workflow.id+"/return-to-production",{method:"POST",body:JSON.stringify({rationale:"Owner-approved rework: resolve the recorded automated QA blockers and regenerate the package."})});});
      }
      if(workflow.status==="awaiting_owner_review"){
        actionButton("Approve internal product workflow",async()=>{await request("/product-rd/workflows/"+workflow.id+"/owner-review",{method:"POST",body:JSON.stringify({approved:true,rationale:"Owner accepts this internal workflow record. This is not approval to publish or sell."})});});
        actionButton("Reject internal product workflow",async()=>{await request("/product-rd/workflows/"+workflow.id+"/owner-review",{method:"POST",body:JSON.stringify({approved:false,rationale:"Owner rejected this internal product workflow."})});});
      }
      const refs=workflow.stages.flatMap(s=>s.artifact_refs||[]);
      if(refs.some(x=>x.endsWith("/package.zip")))addLink("Download ZIP package","/product-rd/workflows/"+workflow.id+"/artifacts/package.zip");
      if(refs.some(x=>x.endsWith("/manifest.json")))addLink("View manifest","/product-rd/workflows/"+workflow.id+"/artifacts/manifest.json");
      card.append(actions);host.append(card);
    }
    byId("prd-create").disabled=false;
  }
  byId("prd-create").addEventListener("click",async()=>{
    const title=byId("prd-title").value.trim(),brief=byId("prd-brief").value.trim();
    if(!title||!brief){setMessage("Enter a product title and brief.","error");return;}
    const b=byId("prd-create");b.disabled=true;
    try{
      await request("/product-rd/workflows",{method:"POST",body:JSON.stringify({title,brief,business_id:byId("prd-business").value})});
      byId("prd-title").value="";byId("prd-brief").value="";
      await loadProductRD();setMessage("Product & R&D workflow created. No agent was started.","success");
    }catch(e){setMessage(e.message,"error");b.disabled=false;}
  });
  byId("prd-business").addEventListener("change",()=>{if(csrfToken)loadProductRD().catch(e=>setMessage(e.message,"error"));});

'''
