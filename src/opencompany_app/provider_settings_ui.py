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
  <p class="muted">Connection testing sends one short test prompt only when you press the test button. It does not create tasks, start workers, or use paid models.</p>
</section>
"""

OWNER_PROVIDER_SETTINGS_JS = r"""
  async function loadUnoRouterSettings(){
    try{
      const status=await request("/settings/providers/unorouter");
      byId("unorouter-state").textContent=status.configured?"Credentials saved · "+(status.model||"free model"):"Not configured";
      byId("unorouter-detail").textContent=status.configured
        ?"Encrypted credentials are saved on the server. API key: hidden. Model: "+status.model+". Live inference: "+(status.real_inference_verified?"verified":"not yet tested")+"."
        :"No saved UnoRouter credentials. The provider gateway remains disabled.";
      byId("unorouter-test").disabled=!status.configured;
      byId("unorouter-remove").disabled=!status.configured;
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
      setMessage("UnoRouter credentials encrypted and saved. The free-only gateway is now configured; run the connection test before enabling workers.","success");
      await loadUnoRouterSettings();
    }catch(error){setMessage(error.message,"error");}
    finally{byId("unorouter-save").disabled=false;}
  });
  byId("unorouter-test").addEventListener("click",async()=>{
    byId("unorouter-test").disabled=true;
    try{
      const result=await request("/settings/providers/unorouter/test",{method:"POST",body:"{}"});
      setMessage("UnoRouter test succeeded: "+result.model+" · "+result.cost_usd+" USD reported cost · "+result.output_preview,"success");
      await loadUnoRouterSettings();
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
      await loadUnoRouterSettings();
    }catch(error){setMessage(error.message,"error");byId("unorouter-remove").disabled=false;}
  });
  byId("connect").addEventListener("click",()=>{setTimeout(loadUnoRouterSettings,0);});
"""
