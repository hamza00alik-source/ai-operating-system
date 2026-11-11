"""Owner-console controls for managing UnoRouter credentials safely."""

OWNER_PROVIDER_SETTINGS_HTML = r"""
<section class="panel" id="unorouter-settings">
  <div class="row"><h2 class="section-title" style="margin:0">UnoRouter free AI provider</h2><span id="unorouter-state" class="pill">Not configured</span></div>
  <p class="muted">Enter your private API key here. It is sent only to this OpenCompany server, encrypted before database storage, and never displayed again. Choose a model whose ID ends with :free. No paid fallback is allowed. Encryption uses the server-side OPENCOMPANY_SECRET_ENCRYPTION_KEY; if unset, it derives from the owner API key. Keep that key stable or re-enter credentials after rotating it.</p>
  <label for="unorouter-api-key">UnoRouter API key</label>
  <input id="unorouter-api-key" type="password" autocomplete="new-password" maxlength="512" placeholder="Paste private API key">
  <label for="unorouter-model">Free model ID</label>
  <input id="unorouter-model" maxlength="200" autocomplete="off" placeholder="e.g. provider/model:free">
  <label style="display:flex;gap:10px;align-items:center;margin:12px 0"><input id="unorouter-confirm-free" type="checkbox"> I confirm this selected model is listed as free by UnoRouter. Stop if the provider reports any charge.</label>
  <div class="auth">
    <button id="unorouter-save" type="button">Save encrypted credentials</button>
    <button id="unorouter-test" type="button" disabled>Test free connection</button>
    <button id="unorouter-remove" type="button" disabled>Remove credentials</button>
    <button id="unorouter-refresh" type="button">Refresh status</button>
  </div>
  <p id="unorouter-detail" class="muted" aria-live="polite">Credentials are not configured.</p>
  <p class="muted">Connection testing sends one short prompt. After a successful zero-cost test, the worker fleet starts automatically only when owner-configured autostart is enabled. Paid fallback is never used.</p>
</section>
<section class="panel" id="github-evolution-settings">
  <div class="row"><h2 class="section-title" style="margin:0">GitHub code evolution</h2><span id="github-evolution-state" class="pill">Not connected</span></div>
  <p class="muted">Save a fine-grained GitHub token here, encrypted on the server. Grant repository access with Contents: Read and write, Pull requests: Read and write, and Metadata: Read. This integration creates isolated draft pull requests only; it cannot merge or deploy.</p>
  <label for="github-evolution-token">GitHub fine-grained token</label>
  <input id="github-evolution-token" type="password" autocomplete="new-password" maxlength="512" placeholder="Paste private GitHub token">
  <label style="display:flex;gap:10px;align-items:center;margin:12px 0"><input id="github-evolution-confirm" type="checkbox"> I authorize draft pull request creation only. I retain merge and deployment approval.</label>
  <div class="auth">
    <button id="github-evolution-save" type="button">Save encrypted token</button>
    <button id="github-evolution-test" type="button" disabled>Test repository access</button>
    <button id="github-evolution-remove" type="button" disabled>Remove token</button>
    <button id="github-evolution-refresh" type="button">Refresh status</button>
  </div>
  <p id="github-evolution-detail" class="muted" aria-live="polite">Code evolution is not connected.</p>
</section>
<section class="panel" id="model-usage">
  <div class="row"><h2 class="section-title" style="margin:0">AI usage & cost ledger</h2><button id="usage-refresh" type="button">Refresh usage</button></div>
  <div class="row">
    <div><strong id="usage-requests">0</strong><p class="muted">Successful requests</p></div>
    <div><strong id="usage-cost">0.000000</strong><p class="muted">Reported USD cost</p></div>
    <div><strong id="usage-tokens">0 / 0</strong><p class="muted">Input / output tokens</p></div>
  </div>
  <p id="usage-detail" class="muted" aria-live="polite">Usage events are recorded after successful specialist inference.</p>
  <div id="usage-events"></div>
  <p class="muted">Provider-reported usage is operational accounting, not an independent invoice. API keys, prompts and completion text are not stored here.</p>
</section>
"""

OWNER_PROVIDER_SETTINGS_JS = r"""
  async function loadUnoRouterSettings(){
    try{
      const status=await request("/settings/providers/unorouter");
      byId("unorouter-state").textContent=status.configuration_error?"Recovery needed":(status.configured?"Credentials saved · "+(status.model||"free model"):"Not configured");
      byId("unorouter-detail").textContent=status.configuration_error
        ?status.configuration_error
        :(status.configured
          ?"Encrypted credentials are saved on the server. API key: hidden. Model: "+status.model+". Live inference: "+(status.real_inference_verified?"verified":"not yet tested")+"."
          :"No saved UnoRouter credentials. The provider gateway remains disabled.");
      byId("unorouter-test").disabled=!status.configured;
      byId("unorouter-remove").disabled=!status.api_key_present;
      if(status.configured) byId("unorouter-model").value=status.model||"";
    }catch(error){byId("unorouter-detail").textContent=error.message;}
  }
  byId("unorouter-refresh").addEventListener("click",loadUnoRouterSettings);
  byId("unorouter-save").addEventListener("click",async()=>{
    const apiKey=byId("unorouter-api-key").value.trim();
    const model=byId("unorouter-model").value.trim();
    const confirmed=byId("unorouter-confirm-free").checked;
    if(!apiKey||!model||!confirmed){setMessage("Enter the API key and free model ID, then confirm the model is free.","error");return;}
    if(!model.endsWith(":free")){setMessage("Only model IDs ending in :free are accepted.","error");return;}
    byId("unorouter-save").disabled=true;
    try{
      await request("/settings/providers/unorouter",{method:"PUT",body:JSON.stringify({api_key:apiKey,model,confirm_free:confirmed})});
      byId("unorouter-api-key").value="";
      byId("unorouter-confirm-free").checked=false;
      setMessage("UnoRouter credentials encrypted and saved. Run the connection test; workers can start only after successful free-provider verification when autostart is enabled.","success");
      await load();
    }catch(error){setMessage(error.message,"error");}
    finally{byId("unorouter-save").disabled=false;}
  });
  byId("unorouter-test").addEventListener("click",async()=>{
    byId("unorouter-test").disabled=true;
    try{
      const result=await request("/settings/providers/unorouter/test",{method:"POST",body:"{}"});
      const workerMessage=result.worker_started?"Worker fleet started automatically.":(result.worker_autostart_enabled?"Worker fleet did not start; check the owner worker controls.":"Worker autostart is disabled.");
      setMessage("UnoRouter test succeeded: "+result.model+" · "+result.cost_usd+" USD reported cost. "+workerMessage,"success");
      await load();
    }catch(error){setMessage(error.message,"error");}
    finally{byId("unorouter-test").disabled=false;}
  });
  byId("unorouter-remove").addEventListener("click",async()=>{
    if(!window.confirm("Remove the saved UnoRouter API key and disable this provider?")) return;
    byId("unorouter-remove").disabled=true;
    try{
      await request("/settings/providers/unorouter",{method:"DELETE"});
      byId("unorouter-api-key").value="";byId("unorouter-model").value="";byId("unorouter-confirm-free").checked=false;
      setMessage("UnoRouter credentials removed. No paid fallback was enabled.","success");
      await load();
    }catch(error){setMessage(error.message,"error");byId("unorouter-remove").disabled=false;}
  });
  byId("connect").addEventListener("click",()=>{setTimeout(loadUnoRouterSettings,0);});


  async function loadGitHubEvolutionSettings(){
    try{
      const status=await request("/settings/integrations/github-evolution");
      byId("github-evolution-state").textContent=status.configuration_error?"Recovery needed":(status.configured?"Connected · "+(status.repository||"repository"):"Not connected");
      byId("github-evolution-detail").textContent=status.configuration_error
        ?status.configuration_error
        :(status.configured
          ?"Encrypted token saved. Repository: "+status.repository+" · Base: "+status.base_branch+". Access: "+(status.access_verified?"verified":"not yet verified")+". Draft PR creation only; auto-merge and auto-deploy are disabled."
          :(status.token_present?"A saved token exists but is not active; replace it or remove it.":"No owner-managed GitHub token is saved. The code-evolution PR integration remains disabled."));
      byId("github-evolution-test").disabled=!status.configured;
      byId("github-evolution-remove").disabled=!status.token_present;
    }catch(error){byId("github-evolution-detail").textContent=error.message;}
  }
  byId("github-evolution-refresh").addEventListener("click",loadGitHubEvolutionSettings);
  byId("github-evolution-save").addEventListener("click",async()=>{
    const token=byId("github-evolution-token").value.trim();
    const confirmed=byId("github-evolution-confirm").checked;
    if(!token||!confirmed){setMessage("Enter the GitHub token and confirm draft-PR-only authority.","error");return;}
    byId("github-evolution-save").disabled=true;
    try{
      await request("/settings/integrations/github-evolution",{method:"PUT",body:JSON.stringify({token,confirm_draft_pr_only:confirmed})});
      byId("github-evolution-token").value="";byId("github-evolution-confirm").checked=false;
      setMessage("GitHub token encrypted and saved. Test repository access before using code evolution.","success");
      await load();
    }catch(error){setMessage(error.message,"error");}
    finally{byId("github-evolution-save").disabled=false;}
  });
  byId("github-evolution-test").addEventListener("click",async()=>{
    byId("github-evolution-test").disabled=true;
    try{
      const result=await request("/settings/integrations/github-evolution/test",{method:"POST",body:"{}"});
      setMessage("GitHub access verified for "+result.username+" on "+result.repository+". Push permission reported: "+String(result.push_permission_reported)+". Draft PR only.","success");
      await load();
    }catch(error){setMessage(error.message,"error");}
    finally{byId("github-evolution-test").disabled=false;}
  });
  byId("github-evolution-remove").addEventListener("click",async()=>{
    if(!window.confirm("Remove the encrypted GitHub token and disable owner-managed code evolution?")) return;
    byId("github-evolution-remove").disabled=true;
    try{
      await request("/settings/integrations/github-evolution",{method:"DELETE"});
      byId("github-evolution-token").value="";byId("github-evolution-confirm").checked=false;
      setMessage("GitHub token removed. Draft PR creation is disabled.","success");
      await load();
    }catch(error){setMessage(error.message,"error");byId("github-evolution-remove").disabled=false;}
  });
  async function loadModelUsage(){
    try{
      const usage=await request("/usage/model");
      byId("usage-requests").textContent=String(usage.request_count);
      byId("usage-cost").textContent=Number(usage.total_cost_usd).toFixed(6);
      byId("usage-tokens").textContent=String(usage.total_input_tokens)+" / "+String(usage.total_output_tokens);
      const target=byId("usage-events");
      target.replaceChildren();
      for(const event of usage.events.slice(0,8)){
        const row=document.createElement("div");row.className="row";
        const label=document.createElement("span");
        label.textContent=event.role_key+" · "+event.provider+"/"+event.model;
        const amount=document.createElement("span");
        amount.textContent=Number(event.cost_usd).toFixed(6)+" USD · "+String(event.input_tokens??"—")+"/"+String(event.output_tokens??"—")+" tokens";
        row.append(label,amount);target.append(row);
      }
      byId("usage-detail").textContent=usage.events.length?"Latest "+usage.events.length+" successful inference events shown.":"No successful inference events recorded yet.";
    }catch(error){byId("usage-detail").textContent="Usage ledger unavailable: "+error.message;}
  }
  byId("usage-refresh").addEventListener("click",loadModelUsage);
"""
