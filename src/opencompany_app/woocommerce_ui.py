WOOCOMMERCE_HTML = r'''
<section class="panel" id="woocommerce-panel">
  <div class="row"><div><h2 class="section-title compact">WooCommerce · read-only connection</h2><p class="muted">Store credentials are encrypted by OpenCompany. Only product/order GET requests are available; publishing, order changes, refunds and fulfilment are disabled.</p></div><span class="pill">READ ONLY</span></div>
  <label for="woo-business">Business unit</label>
  <select id="woo-business"><option value="physical-brand">Own physical-product brand</option><option value="digital-products">Digital products</option><option value="physical-agency">Physical-products agency</option></select>
  <div id="woo-status" class="muted" aria-live="polite">Connect to inspect this business unit's WooCommerce status.</div>
  <label for="woo-store-url">Store URL (HTTPS)</label>
  <input id="woo-store-url" type="url" maxlength="500" autocomplete="url" placeholder="https://your-store.example">
  <label for="woo-consumer-key">WooCommerce consumer key</label>
  <input id="woo-consumer-key" type="password" maxlength="256" autocomplete="off" placeholder="ck_…">
  <label for="woo-consumer-secret">WooCommerce consumer secret</label>
  <input id="woo-consumer-secret" type="password" maxlength="256" autocomplete="new-password" placeholder="cs_…">
  <div class="auth">
    <button id="woo-save" disabled>Save encrypted connection</button>
    <button id="woo-test" disabled>Test read-only connection</button>
    <button id="woo-products" disabled>Read products</button>
    <button id="woo-orders" disabled>Read orders</button>
  </div>
  <div id="woo-results" class="list"><p class="muted">No external request is made until you explicitly test or read data.</p></div>
</section>
''';

WOOCOMMERCE_JS = r'''
  async function loadWooCommerce(){
    if(!csrfToken)return;
    const business=byId("woo-business").value;
    try{
      const result=await request("/integrations/woocommerce/"+encodeURIComponent(business)+"/status");
      byId("woo-status").textContent=result.configured
        ?"Configured · encrypted credentials · read-only · external writes disabled"
        :"Not connected · no credentials stored for this business";
      byId("woo-test").disabled=!result.configured;
      byId("woo-products").disabled=!result.configured;
      byId("woo-orders").disabled=!result.configured;
      byId("woo-save").disabled=false;
    }catch(e){
      byId("woo-status").textContent="Status unavailable: "+e.message;
      byId("woo-test").disabled=true;byId("woo-products").disabled=true;byId("woo-orders").disabled=true;
    }
  }
  byId("woo-business").addEventListener("change",loadWooCommerce);
  byId("woo-save").addEventListener("click",async()=>{
    const business=byId("woo-business").value;
    const payload={
      store_url:byId("woo-store-url").value.trim(),
      consumer_key:byId("woo-consumer-key").value.trim(),
      consumer_secret:byId("woo-consumer-secret").value.trim()
    };
    if(!payload.store_url||!payload.consumer_key||!payload.consumer_secret){
      setMessage("Enter the store URL and both WooCommerce credentials.","error");return;
    }
    const button=byId("woo-save");button.disabled=true;
    try{
      const result=await request("/integrations/woocommerce/"+encodeURIComponent(business)+"/connection",{method:"PUT",body:JSON.stringify(payload)});
      byId("woo-store-url").value="";byId("woo-consumer-key").value="";byId("woo-consumer-secret").value="";
      setMessage("WooCommerce credentials saved encrypted. No store request was made; explicitly test the read-only connection next.","success");
      await loadWooCommerce();
    }catch(e){setMessage(e.message,"error");}
    finally{button.disabled=false;}
  });
  byId("woo-test").addEventListener("click",async()=>{
    const business=byId("woo-business").value;
    try{
      const result=await request("/integrations/woocommerce/"+encodeURIComponent(business)+"/test",{method:"POST",body:"{}"});
      byId("woo-results").textContent="Connection test succeeded · sample products returned: "+result.sample_products_returned+" · read-only";
      setMessage("WooCommerce read-only connection verified for "+business+".","success");
    }catch(e){setMessage(e.message,"error");}
  });
  async function readWooCommerce(resource){
    const business=byId("woo-business").value;
    const host=byId("woo-results");host.textContent="Reading "+resource+"…";
    try{
      const result=await request("/integrations/woocommerce/"+encodeURIComponent(business)+"/"+resource);
      const rows=result[resource]||[];
      host.replaceChildren();
      const summary=document.createElement("p");summary.className="muted";
      summary.textContent=rows.length+" "+resource+" returned · read-only · customer personal data omitted";host.append(summary);
      for(const row of rows.slice(0,20)){
        const card=document.createElement("article");card.className="item";
        const title=document.createElement("h3");title.textContent=resource==="orders"?"Order #"+row.id:(row.name||("Product #"+row.id));
        card.append(title);
        const detail=document.createElement("p");detail.textContent=resource==="orders"
          ?"Order #"+row.id+" · "+(row.status||"unknown")+" · "+(row.currency||"")+" "+(row.total||"")
          :"Product #"+row.id+" · "+(row.status||"unknown")+" · "+(row.stock_status||"stock unknown");
        card.append(detail);host.append(card);
      }
    }catch(e){host.textContent="Read failed: "+e.message;setMessage(e.message,"error");}
  }
  byId("woo-products").addEventListener("click",()=>readWooCommerce("products"));
  byId("woo-orders").addEventListener("click",()=>readWooCommerce("orders"));

'''
