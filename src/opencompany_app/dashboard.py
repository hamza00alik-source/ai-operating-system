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
.row{display:flex;gap:8px;align-items:center;justify-content:space-between;flex-wrap:wrap}.approval-inbox-filter-row{margin-top:12px}.pill{font-size:.75rem;border-radius:999px;background:#263653;color:#cfe0ff;padding:5px 9px}
.owner-connection-title{font-size:1.05rem;margin:0 0 10px}.provider-state{font-size:1.05rem}.section-title.compact{margin:0}.research-results{white-space:pre-wrap;overflow-wrap:anywhere}.worker-actions{margin-top:12px}.console-footer{font-size:.8rem;margin:18px 4px}.confirmation-label{display:flex;gap:10px;align-items:center;margin:12px 0}.warn{color:#ffd58a}.error{color:#ff9c9c}.success{color:#91e0bd}.section-title{margin:22px 0 8px;font-size:1.15rem}
@media(max-width:520px){main{padding:16px 12px 32px}.panel{padding:13px}.auth{flex-direction:column}.auth button{width:100%}}
</style>
</head>
<body>
<main>
  <div class="top">
    <div><h1>OpenCompany Owner Console</h1><div class="muted">One company · one intelligence engine · owner-governed operations</div></div>
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
    <label for="executive-business">Business unit</label>
    <select id="executive-business">
      <option value="core">Core / internal operations</option>
      <option value="physical-agency">Physical-products agency</option>
      <option value="physical-brand">Own physical-product brand</option>
      <option value="digital-products">Digital products business</option>
    </select>
    <label for="executive-title">Plan title</label>
    <input id="executive-title" maxlength="240" placeholder="Example: Research buyer demand and prepare a scoped plan for one business unit">
    <label for="executive-objective">Company objective</label>
    <textarea id="executive-objective" rows="4" maxlength="12000" placeholder="Describe the outcome, constraints, audience, and success measures."></textarea>
    <button id="create-executive-plan" disabled>Create CEO draft plan</button>
  </section>
  <section class="panel">
    <h2 class="section-title">Commercial workspace · separate businesses</h2>
    <p class="muted">Each customer opportunity and catalogue entry belongs to exactly one business. Core is internal only. No automatic cross-selling, substitution, customer contact, or publishing occurs here.</p>
    <div class="grid">
      <div class="item">
        <h3>Record customer opportunity</h3>
        <label for="opportunity-business">Business serving this need</label>
        <select id="opportunity-business">
          <option value="physical-agency">Physical-products agency</option>
          <option value="physical-brand">Own physical-product brand</option>
          <option value="digital-products">Digital products</option>
        </select>
        <label for="opportunity-customer">Customer / company</label>
        <input id="opportunity-customer" maxlength="200" placeholder="Customer name">
        <label for="opportunity-contact">Contact (optional)</label>
        <input id="opportunity-contact" maxlength="320" placeholder="Email or contact reference">
        <label for="opportunity-need">What did the customer ask for?</label>
        <textarea id="opportunity-need" rows="3" maxlength="4000" placeholder="Record only the customer's stated need."></textarea>
        <label class="confirmation-label"><input id="opportunity-scope" type="checkbox"> I confirm this is one relevant business and no unrelated offer is being added.</label>
        <button id="create-opportunity" disabled>Save opportunity</button>
      </div>
      <div class="item">
        <h3>Add a product / service catalogue entry</h3>
        <label for="catalog-business">Owning business</label>
        <select id="catalog-business">
          <option value="physical-agency">Physical-products agency</option>
          <option value="physical-brand">Own physical-product brand</option>
          <option value="digital-products">Digital products</option>
        </select>
        <label for="catalog-name">Name</label>
        <input id="catalog-name" maxlength="200" placeholder="Product or service name">
        <label for="catalog-category">Category</label>
        <input id="catalog-category" maxlength="120" placeholder="e.g. Himalayan pink salt / downloadable tool">
        <label for="catalog-description">Description</label>
        <textarea id="catalog-description" rows="3" maxlength="4000" placeholder="Describe only what this business actually provides."></textarea>
        <button id="create-catalog-product" disabled>Save as private draft</button>
      </div>
    </div>
    <div class="grid">
      <div><h3>Customer opportunities</h3><div id="commercial-opportunities" class="list"><p class="muted">Connect to load opportunities.</p></div></div>
      <div><h3>Separate catalogues</h3><div id="commercial-products" class="list"><p class="muted">Connect to load catalogue drafts.</p></div></div>
    </div>
    <div class="grid">
      <div><h3>Proposals & quotations</h3><div id="commercial-quotes" class="list"><p class="muted">Connect to load quotations.</p></div></div>
      <div><h3>Orders · record only</h3><div id="commercial-orders" class="list"><p class="muted">Connect to load orders.</p></div></div>
    </div>
    <div class="item">
      <h3>Financial overview · owner-verified records</h3>
      <p class="muted">Revenue and costs remain separated by business and currency. Agency revenue counts commissions only. This is an accounting view, not a bank balance or payment processor.</p>
      <div id="commercial-financial-summary" class="list"><p class="muted">Connect to load financial summaries.</p></div>
    </div>
  </section>
  <section class="panel">
    <h2 class="section-title">Supplier relationships · separate physical businesses</h2>
    <p class="muted">Agency suppliers are third-party manufacturers/suppliers represented by the agency. Own-brand suppliers belong only to your separate brand supply chain. Records stay private; saving or verifying does not contact, purchase from, or commit any supplier.</p>
    <div class="grid">
      <div class="item">
        <label for="supplier-business">Owning business</label>
        <select id="supplier-business">
          <option value="physical-agency">Physical-products agency · third-party supplier</option>
          <option value="physical-brand">Own physical-product brand · own supply chain</option>
        </select>
        <label for="supplier-name">Supplier / manufacturer name</label>
        <input id="supplier-name" maxlength="200" placeholder="Company name">
        <label for="supplier-contact">Contact person (optional)</label>
        <input id="supplier-contact" maxlength="200" placeholder="Contact name">
        <label for="supplier-email">Email (optional)</label>
        <input id="supplier-email" type="email" maxlength="320" placeholder="Email address">
        <label for="supplier-phone">Phone (optional)</label>
        <input id="supplier-phone" maxlength="80" placeholder="Phone number">
        <label for="supplier-country">Country (optional)</label>
        <input id="supplier-country" maxlength="100" placeholder="Country">
        <label for="supplier-categories">Product categories (comma-separated)</label>
        <input id="supplier-categories" maxlength="1000" placeholder="Pink salt, edible salt, salt lamps">
        <label for="supplier-notes">Private notes</label>
        <textarea id="supplier-notes" rows="2" maxlength="3000" placeholder="Evidence still needed, certifications to check, etc."></textarea>
        <button id="create-supplier" disabled>Save private supplier draft</button>
      </div>
      <div><h3>Supplier register</h3><div id="commercial-suppliers" class="list"><p class="muted">Connect to load supplier records.</p></div></div>
    </div>
  </section>
  <section class="panel">
    <h2 class="section-title">Store integrations · WooCommerce</h2>
    <p class="muted">Each business has its own encrypted store connection. Credentials are sent only to this owner-authenticated server, never shown again, and are not saved in browser storage. Saving credentials makes no network request. Test and read actions contact the selected store and are read-only.</p>
    <div class="grid">
      <div class="item">
        <label for="woo-business">Business connection</label>
        <select id="woo-business">
          <option value="physical-agency">Physical-products agency</option>
          <option value="physical-brand">Own physical-product brand</option>
          <option value="digital-products">Digital products</option>
        </select>
        <p id="woo-status" class="muted">Connect to inspect this business's store status.</p>
        <label for="woo-url">Store URL (HTTPS)</label>
        <input id="woo-url" type="url" maxlength="500" placeholder="https://store.example.com" autocomplete="url">
        <label for="woo-key">WooCommerce read-only consumer key</label>
        <input id="woo-key" type="password" maxlength="256" autocomplete="off" placeholder="ck_…">
        <label for="woo-secret">WooCommerce read-only consumer secret</label>
        <input id="woo-secret" type="password" maxlength="256" autocomplete="new-password" placeholder="cs_…">
        <button id="woo-save" disabled>Save encrypted connection</button>
        <button id="woo-test" disabled>Test read-only access</button>
        <button id="woo-disconnect" disabled>Disconnect store</button>
      </div>
      <div class="item">
        <h3>Read-only store preview</h3>
        <div class="row">
          <button id="woo-products" disabled>Read products</button>
          <button id="woo-orders" disabled>Read orders</button>
        </div>
        <pre id="woo-results" class="muted research-results">No store data loaded. Orders are minimized and exclude customer personal information.</pre>
      </div>
    </div>
    <p class="muted">No product publishing, stock updates, order-status changes, customer messaging, refunds, payments, or fulfilment actions are available here.</p>
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
    <label for="business-filter">Show business unit</label>
    <select id="business-filter">
      <option value="">All business units</option>
      <option value="core">Core / internal operations</option>
      <option value="physical-agency">Physical-products agency</option>
      <option value="physical-brand">Own physical-product brand</option>
      <option value="digital-products">Digital products business</option>
    </select>
    <div class="auth worker-actions"><button id="start-workers" disabled>Start worker fleet</button><button id="stop-workers" disabled>Stop worker fleet</button></div>
    <div id="work-items" class="list"><p class="muted">Connect to view work items.</p></div>
  </section>
  <p class="muted console-footer">This console does not publish content, contact customers, spend money, deploy production, or activate agents. Protected actions remain owner-gated.</p>

  <section class="panel">
    <h2 class="section-title">Company-wide venture portfolio</h2>
    <p class="muted">Discover opportunities across any legitimate business model. This portfolio is separate from the three existing operating businesses. Validation never creates a business, spends money, publishes, contacts customers, or changes fulfilment.</p>
    <div class="grid">
      <div class="item">
        <label for="venture-title">Opportunity name</label>
        <input id="venture-title" maxlength="160" placeholder="e.g. Research subscription for niche buyers">
        <label for="venture-slug">Unique ID (lowercase, hyphens)</label>
        <input id="venture-slug" maxlength="63" placeholder="research-subscription">
        <label for="venture-model">Business model</label>
        <input id="venture-model" maxlength="80" placeholder="e.g. SaaS, services, licensing, digital downloads">
        <label for="venture-market">Target market</label>
        <input id="venture-market" maxlength="300" placeholder="Who might pay for this?">
        <label for="venture-description">Opportunity description</label>
        <textarea id="venture-description" rows="3" maxlength="5000" placeholder="Problem, offer, possible revenue model, and constraints"></textarea>
        <label for="venture-evidence">Evidence URL (optional, HTTPS)</label>
        <input id="venture-evidence" maxlength="2000" placeholder="https://...">
        <button id="create-venture" disabled>Save opportunity for research</button>
      </div>
      <div>
        <h3>Opportunity pipeline</h3>
        <div id="venture-opportunities" class="list"><p class="muted">Connect to load opportunities.</p></div>
      </div>
    </div>
  </section>
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
    if(!response.ok){
      let detail="";
      try{const payload=await response.json();if(typeof payload.detail==="string")detail=payload.detail;}catch{}
      if(!detail) detail=response.status===401?"Owner key rejected.":"Request failed ("+response.status+").";
      throw new Error(detail);
    }
    return response.json();
  };
  async function loadWooCommerceStatus(){
    const business=byId("woo-business").value;
    const status=await request("/integrations/woocommerce/"+encodeURIComponent(business)+"/status");
    byId("woo-status").textContent=status.configured
      ? "Encrypted connection saved · "+status.mode+" · writes disabled"
      : "No store connection saved for this business.";
    byId("woo-test").disabled=!status.configured;
    byId("woo-disconnect").disabled=!status.configured;
    byId("woo-products").disabled=!status.configured;
    byId("woo-orders").disabled=!status.configured;
    byId("woo-save").disabled=false;
  }
  async function readWooCommerce(resource){
    const business=byId("woo-business").value;
    const button=byId("woo-"+resource);button.disabled=true;
    try{
      const result=await request("/integrations/woocommerce/"+encodeURIComponent(business)+"/"+resource+"?page=1&per_page=10");
      byId("woo-results").textContent=JSON.stringify(result,null,2);
      setMessage("Read "+result.count+" "+resource+" record(s). No store data was changed.","success");
    }catch(error){setMessage(error.message,"error");}
    finally{button.disabled=false;}
  }
  async function loadCommercial(){
    const [opportunities,products,quotes,orders,suppliers,financial]=await Promise.all([
      request("/commercial/opportunities"),request("/commercial/products"),
      request("/commercial/quotes"),request("/commercial/orders"),request("/commercial/suppliers"),
      request("/commercial/financial-summary")
    ]);
    clear("commercial-opportunities","No customer opportunities recorded.");
    opportunities.opportunities.forEach(o=>{
      const card=document.createElement("article");card.className="item";
      const heading=document.createElement("h3");heading.textContent=o.customer_name+" · "+o.business_id;card.append(heading);
      const need=document.createElement("p");need.textContent=o.customer_need;card.append(need);
      const stage=document.createElement("span");stage.className="pill";stage.textContent=o.stage;card.append(stage);
      const matching=document.createElement("button");matching.textContent="View this business's active catalogue";
      matching.addEventListener("click",async()=>{
        matching.disabled=true;
        try{
          const result=await request("/commercial/opportunities/"+o.id+"/catalogue");
          const listing=document.createElement("pre");listing.style.whiteSpace="pre-wrap";listing.style.overflowWrap="anywhere";
          listing.textContent=result.count?JSON.stringify(result.products.map(p=>({name:p.name,category:p.category,description:p.description})),null,2):"No active catalogue entries in "+result.business_id+". Drafts and other businesses are excluded.";
          card.append(listing);
        }catch(error){setMessage(error.message,"error");}
        finally{matching.disabled=false;}
      });
      card.append(matching);
      const quoteForm=document.createElement("div");quoteForm.className="item";
      const quoteHeading=document.createElement("h4");quoteHeading.textContent="Prepare a quote for this opportunity";quoteForm.append(quoteHeading);
      const activeProducts=products.products.filter(p=>p.business_id===o.business_id&&p.status==="active");
      const productSelect=document.createElement("select");
      activeProducts.forEach(p=>{const option=document.createElement("option");option.value=p.id;option.textContent=p.name+" · "+p.category;productSelect.append(option);});
      if(!activeProducts.length){const option=document.createElement("option");option.textContent="No active catalogue entries for this business";option.value="";productSelect.append(option);}
      quoteForm.append(productSelect);
      const quoteTitle=document.createElement("input");quoteTitle.maxLength=200;quoteTitle.placeholder="Quote title";quoteTitle.value="Proposal for "+o.customer_name;quoteForm.append(quoteTitle);
      const currency=document.createElement("input");currency.maxLength=3;currency.value="USD";currency.placeholder="ISO currency code";quoteForm.append(currency);
      const exponent=document.createElement("input");exponent.type="number";exponent.min="0";exponent.max="3";exponent.value="2";exponent.placeholder="Currency decimal places (0, 2 or 3)";quoteForm.append(exponent);
      const quantity=document.createElement("input");quantity.type="number";quantity.min="1";quantity.max="10000";quantity.value="1";quantity.placeholder="Quantity";quoteForm.append(quantity);
      const unitPrice=document.createElement("input");unitPrice.type="number";unitPrice.min="1";unitPrice.step="1";unitPrice.placeholder="Unit price in minor units (decimal places set above)";quoteForm.append(unitPrice);
      const terms=document.createElement("textarea");terms.rows=2;terms.maxLength=4000;terms.placeholder="Quote terms, validity, exclusions and delivery assumptions";quoteForm.append(terms);
      const makeQuote=document.createElement("button");makeQuote.textContent="Save quote as draft";
      makeQuote.disabled=!activeProducts.length;
      makeQuote.addEventListener("click",async()=>{
        const q=Number(quantity.value),price=Number(unitPrice.value);
        if(!productSelect.value||!quoteTitle.value.trim()||!/^[A-Za-z]{3}$/.test(currency.value)||!Number.isInteger(q)||q<1||!Number.isInteger(price)||price<1||![0,2,3].includes(Number(exponent.value))||!terms.value.trim()){
          setMessage("Complete the product, title, ISO currency, quantity, minor-unit price and terms.","error");return;
        }
        makeQuote.disabled=true;
        try{
          const selected=activeProducts.find(p=>p.id===productSelect.value);
          await request("/commercial/quotes",{method:"POST",body:JSON.stringify({
            opportunity_id:o.id,title:quoteTitle.value.trim(),currency:currency.value.toUpperCase(),currency_exponent:Number(exponent.value),terms:terms.value.trim(),
            items:[{product_id:selected.id,description:selected.name+" — "+selected.description,quantity:q,unit_price_minor:price}]
          })});
          await loadCommercial();
          setMessage("Draft quote saved under "+o.business_id+". It was not sent to the customer.","success");
        }catch(error){setMessage(error.message,"error");makeQuote.disabled=false;}
      });
      quoteForm.append(makeQuote);card.append(quoteForm);
    byId("commercial-opportunities").append(card);
    });
    clear("commercial-products","No catalogue drafts yet.");
    products.products.forEach(p=>{
      const card=document.createElement("article");card.className="item";
      const heading=document.createElement("h3");heading.textContent=p.name+" · "+p.business_id;card.append(heading);
      const detail=document.createElement("p");detail.textContent=p.category+" · "+p.description;card.append(detail);
      const state=document.createElement("span");state.className="pill";state.textContent="Private catalogue · "+p.status;card.append(state);
      if(p.status==="draft"){
        const activate=document.createElement("button");activate.textContent="Approve for internal matching";
        activate.addEventListener("click",async()=>{
          activate.disabled=true;
          try{
            await request("/commercial/products/"+p.id+"/status",{method:"POST",body:JSON.stringify({status:"active",confirm_owner_approval:true})});
            await loadCommercial();setMessage("Catalogue entry approved for internal matching only. It was not published.","success");
          }catch(error){setMessage(error.message,"error");activate.disabled=false;}
        });
        card.append(activate);
      }
      byId("commercial-products").append(card);
    });
    clear("commercial-quotes","No proposals or quotations recorded.");
    quotes.quotes.forEach(q=>{
      const card=document.createElement("article");card.className="item";
      const heading=document.createElement("h3");heading.textContent=q.title+" · "+q.business_id;card.append(heading);
      const detail=document.createElement("p");detail.textContent=q.customer_name+" · "+q.currency+" "+(q.subtotal_minor/(10**q.currency_exponent)).toFixed(q.currency_exponent)+" · "+q.items.length+" line(s)";card.append(detail);
      const state=document.createElement("span");state.className="pill";state.textContent=q.status;card.append(state);
      const lines=document.createElement("p");lines.textContent=q.items.map(i=>i.description+" × "+i.quantity).join(" | ");card.append(lines);
      if(q.status==="draft"){
        const approve=document.createElement("button");approve.textContent="Approve quote for owner delivery";
        approve.addEventListener("click",async()=>{
          if(!confirm("Approve this quote for you to deliver to the customer outside OpenCompany? Nothing will be sent automatically."))return;
          approve.disabled=true;
          try{await request("/commercial/quotes/"+q.id+"/decision",{method:"POST",body:JSON.stringify({status:"approved_for_delivery",confirm_owner_decision:true})});await loadCommercial();setMessage("Quote approved for manual owner delivery. No message was sent.","success");}
          catch(error){setMessage(error.message,"error");approve.disabled=false;}
        });card.append(approve);
      }else if(q.status==="approved_for_delivery"){
        const evidence=document.createElement("input");evidence.maxLength=1000;evidence.placeholder="Customer acceptance evidence reference (e.g. email/order ref)";
        const accept=document.createElement("button");accept.textContent="Record customer acceptance";
        accept.addEventListener("click",async()=>{
          if(!evidence.value.trim()||!confirm("Confirm the customer has accepted this exact quote? This only records your confirmation; it does not contact the customer.")){setMessage("Acceptance evidence reference and confirmation are required.","error");return;}
          accept.disabled=true;
          try{await request("/commercial/quotes/"+q.id+"/decision",{method:"POST",body:JSON.stringify({status:"accepted",confirm_owner_decision:true,acceptance_reference:evidence.value.trim()})});await loadCommercial();setMessage("Customer acceptance recorded with your evidence reference.","success");}
          catch(error){setMessage(error.message,"error");accept.disabled=false;}
        });card.append(evidence,accept);
        const reject=document.createElement("button");reject.textContent="Record rejected / void";
        reject.addEventListener("click",async()=>{if(!confirm("Record this quote as rejected?"))return;try{await request("/commercial/quotes/"+q.id+"/decision",{method:"POST",body:JSON.stringify({status:"rejected",confirm_owner_decision:true})});await loadCommercial();}catch(error){setMessage(error.message,"error");}});card.append(reject);
      }else if(q.status==="accepted"){
        const orderButton=document.createElement("button");orderButton.textContent="Create order record";
        orderButton.addEventListener("click",async()=>{
          if(!confirm("Create an internal order record for this accepted quote? This does not take payment or start fulfilment."))return;
          orderButton.disabled=true;
          try{await request("/commercial/orders",{method:"POST",body:JSON.stringify({quote_id:q.id,confirm_owner_order_record:true})});await loadCommercial();setMessage("Order record created. Payment and fulfilment remain manual and separate.","success");}
          catch(error){setMessage(error.message,"error");orderButton.disabled=false;}
        });card.append(orderButton);
      }
      byId("commercial-quotes").append(card);
    });
    clear("commercial-financial-summary","No owner-verified financial events recorded yet.");
    if(financial.summaries.length){
      clear("commercial-financial-summary","");
      financial.summaries.forEach(summary=>{
        const card=document.createElement("article");card.className="item";
        const heading=document.createElement("h3");heading.textContent=summary.business_id+" · "+summary.currency;card.append(heading);
        const fractionDigits=new Intl.NumberFormat(undefined,{style:"currency",currency:summary.currency}).resolvedOptions().maximumFractionDigits;
        const formatMinor=value=>new Intl.NumberFormat(undefined,{style:"currency",currency:summary.currency}).format(Number(value)/(10**fractionDigits));
        const details=document.createElement("p");
        details.textContent="Recognized revenue: "+formatMinor(summary.recognized_revenue_minor)
          +" · Operating costs: "+formatMinor(summary.operating_costs_minor)
          +" · Net contribution: "+formatMinor(summary.net_contribution_minor);
        card.append(details);
        const cash=document.createElement("p");
        cash.textContent="Cash received: "+formatMinor(summary.cash_received_minor)
          +" · Cash refunded: "+formatMinor(summary.cash_refunded_minor)
          +" · "+summary.event_count+" evidence event(s)";
        card.append(cash);
        const basis=document.createElement("span");basis.className="pill";basis.textContent=summary.revenue_basis+" · no FX conversion";card.append(basis);
        byId("commercial-financial-summary").append(card);
      });
    }
    clear("commercial-orders","No order records yet.");
    orders.orders.forEach(o=>{
      const card=document.createElement("article");card.className="item";
      const heading=document.createElement("h3");heading.textContent=o.customer_name+" · "+o.business_id;card.append(heading);
      const detail=document.createElement("p");detail.textContent="Order "+o.id+" · Quote "+o.quote_id;card.append(detail);
      const state=document.createElement("span");state.className="pill";state.textContent=o.status;card.append(state);
      const next=o.status==="awaiting_owner_fulfilment"?"in_progress":o.status==="in_progress"?"fulfilled":null;
      if(next){
        const action=document.createElement("button");action.textContent=next==="in_progress"?"Mark work in progress":"Record fulfilment complete";
        action.addEventListener("click",async()=>{
          if(!confirm("Confirm order "+o.id+" should be marked "+next+"? This records your status only; it does not contact suppliers, take payment, or trigger shipment."))return;
          action.disabled=true;
          try{await request("/commercial/orders/"+o.id+"/status",{method:"POST",body:JSON.stringify({status:next,confirm_owner_status:true})});await loadCommercial();setMessage("Order status updated. No external fulfilment action was triggered.","success");}
          catch(error){setMessage(error.message,"error");action.disabled=false;}
        });card.append(action);
      }
      if(o.status==="awaiting_owner_fulfilment"||o.status==="in_progress"){
        const cancel=document.createElement("button");cancel.textContent="Cancel order record";
        cancel.addEventListener("click",async()=>{
          if(!confirm("Cancel this internal order record? This does not contact the customer or supplier."))return;
          try{await request("/commercial/orders/"+o.id+"/status",{method:"POST",body:JSON.stringify({status:"cancelled",confirm_owner_status:true})});await loadCommercial();}
          catch(error){setMessage(error.message,"error");}
        });card.append(cancel);
      }
      byId("commercial-orders").append(card);
    });
    clear("commercial-suppliers","No supplier relationships recorded.");
    suppliers.suppliers.forEach(supplier=>{
      const card=document.createElement("article");card.className="item";
      const heading=document.createElement("h3");heading.textContent=supplier.name+" · "+supplier.business_id;card.append(heading);
      const meta=document.createElement("p");
      meta.textContent=[supplier.relationship_type,supplier.country,supplier.product_categories.join(", ")].filter(Boolean).join(" · ");
      card.append(meta);
      if(supplier.contact_name||supplier.email||supplier.phone){
        const contact=document.createElement("p");contact.textContent=[supplier.contact_name,supplier.email,supplier.phone].filter(Boolean).join(" · ");card.append(contact);
      }
      if(supplier.notes){const notes=document.createElement("p");notes.textContent=supplier.notes;card.append(notes);}
      const state=document.createElement("span");state.className="pill";state.textContent=supplier.verification_status;card.append(state);
      if(supplier.verification_status==="draft"||supplier.verification_status==="verified"){
        const verify=document.createElement("button");verify.textContent="Mark verified";
        verify.addEventListener("click",async()=>{
          if(!confirm("Confirm you have independently checked this supplier's identity and evidence? This only changes the private record; it does not confirm stock, quality, pricing, or export eligibility."))return;
          verify.disabled=true;
          try{await request("/commercial/suppliers/"+supplier.id+"/status",{method:"POST",body:JSON.stringify({status:"verified",confirm_owner_decision:true})});await loadCommercial();}
          catch(error){setMessage(error.message,"error");verify.disabled=false;}
        });
        const block=document.createElement("button");block.textContent="Block supplier";
        block.addEventListener("click",async()=>{
          if(!confirm("Block this supplier record? This prevents it from being marked verified later."))return;
          block.disabled=true;
          try{await request("/commercial/suppliers/"+supplier.id+"/status",{method:"POST",body:JSON.stringify({status:"blocked",confirm_owner_decision:true})});await loadCommercial();}
          catch(error){setMessage(error.message,"error");block.disabled=false;}
        });
        card.append(verify,block);
      }
      byId("commercial-suppliers").append(card);
    });
    ["create-opportunity","create-catalog-product","create-supplier"].forEach(id=>byId(id).disabled=false);
  }

  async function loadVenturePortfolio(){
    const data=await request("/venture-opportunities");
    clear("venture-opportunities","No opportunities recorded yet.");
    data.items.forEach(item=>{
      const card=document.createElement("article");card.className="item";
      const heading=document.createElement("h3");heading.textContent=item.title+" · "+item.status;card.append(heading);
      const details=document.createElement("p");details.textContent=item.business_model+" · "+item.target_market;card.append(details);
      const description=document.createElement("p");description.textContent=item.description;card.append(description);
      const evidence=document.createElement("p");evidence.textContent="Evidence references: "+item.evidence.length;card.append(evidence);
      const next={discovered:"researching",researching:"validated",validated:"approved_to_launch",rejected:"researching",approved_to_launch:"launched"}[item.status];
      if(next){
        const action=document.createElement("button");
        action.textContent=({researching:"Start research",validated:"Mark validated",approved_to_launch:"Approve launch planning",launched:"Confirm launched"}[next]||"Continue");
        action.addEventListener("click",async()=>{
          const protectedStep=next==="approved_to_launch"||next==="launched";
          if(protectedStep&&!window.confirm(next==="approved_to_launch"?"Approve this opportunity for launch planning? This does not create accounts or spend money.":"Confirm that this venture has actually launched?"))return;
          action.disabled=true;
          try{
            await request("/venture-opportunities/"+item.id+"/status",{method:"POST",body:JSON.stringify({status:next,rationale:"Owner decision recorded in OpenCompany.",confirm_owner_approval:protectedStep})});
            await loadVenturePortfolio();
            setMessage("Opportunity moved to "+next+". No external action was performed.","success");
          }catch(error){setMessage(error.message,"error");action.disabled=false;}
        });
        card.append(action);
      }
      byId("venture-opportunities").append(card);
    });
    byId("create-venture").disabled=false;
  }
  async function load(){
    byId("provision").disabled=true;
    setMessage("Loading owner records…");
    try{
      const businessFilter=byId("business-filter").value;
      const workItemsUrl=businessFilter?"/work-items?business_id="+encodeURIComponent(businessFilter):"/work-items";
      const [org,agents,work,provider,media,workforce,queue,fleet,learning,codeEvolution,apiAnything]=await Promise.all([
        request("/organization/departments"),request("/agents"),request(workItemsUrl),
        request("/providers/status"),request("/media/capabilities"),request("/workforce/roles"),request(businessFilter?"/workers/queue?business_id="+encodeURIComponent(businessFilter):"/workers/queue"),request("/workers/status"),request(businessFilter?"/learning/proposals?business_id="+encodeURIComponent(businessFilter):"/learning/proposals"),request("/code-evolution/config-status"),request("/integrations/api-anything/status")
      ]);
      await loadCommercial();
      await loadWooCommerceStatus();
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
        const title=document.createElement("h3");title.textContent=(proposal.business_id||"core")+" · "+proposal.target+" · "+proposal.state;card.append(title);
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
          apply.addEventListener("click",async()=>{apply.disabled=true;try{await request("/learning/proposals/"+proposal.id+"/apply-note",{method:"POST",body:"{}"});setMessage("Approved learning note is now available to future "+proposal.target+" tasks in "+(proposal.business_id||"core")+".","success");await load();}catch(error){setMessage(error.message,"error");apply.disabled=false;}});
          card.append(apply);
        }
        byId("learning-proposals").append(card);
      });
      clear("departments","No departments returned.");
      org.departments.forEach(d=>addCard(byId("departments"),d.name,d.mission,d.role_keys.length+" role assignment(s)"));
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
        const detail=document.createElement("p");detail.textContent=(w.business_id||"core")+" · "+w.department+" · "+w.objective;card.append(detail);
        const workflowButton=document.createElement("button");workflowButton.textContent="Workflow details";
        workflowButton.addEventListener("click",async()=>{
          workflowButton.disabled=true;
          try{
            const result=await request("/work-items/"+w.id+"/workflow");
            const panel=document.createElement("pre");
            panel.style.whiteSpace="pre-wrap";panel.style.overflowWrap="anywhere";
            panel.style.maxHeight="360px";panel.style.overflow="auto";
            panel.textContent=JSON.stringify({
              next_action:result.next_action,
              prerequisites:result.prerequisites,
              dependents:result.dependents,
              queue:result.queue,
              delegation_proposals:(result.delegation_proposals||[]).map(p=>({id:p.id,status:p.status,mode:p.mode,children:p.children})),
              handoffs:(result.handoffs||[]).map(h=>({id:h.id,state:h.state,purpose:h.purpose})),
              deliverables:result.deliverables,
              counts:result.counts
            },null,2);
            const existing=card.querySelector("[data-workflow-details]");
            if(existing)existing.remove();
            panel.dataset.workflowDetails="true";card.append(panel);
            const previousHandoffActions=card.querySelector("[data-handoff-actions]");
            if(previousHandoffActions)previousHandoffActions.remove();
            const handoffActions=document.createElement("div");
            handoffActions.className="stack";
            (result.handoffs||[]).forEach(h=>{
              const handoffRow=document.createElement("div");
              handoffRow.className="row";
              const handoffLabel=document.createElement("span");
              handoffLabel.textContent="Handoff · "+h.purpose+" · "+h.state;
              handoffRow.append(handoffLabel);
              if(h.state==="proposed"){
                for(const action of ["accept","decline"]){
                  const actionButton=document.createElement("button");
                  actionButton.textContent=action==="accept"?"Accept handoff":"Decline handoff";
                  actionButton.addEventListener("click",async()=>{
                    actionButton.disabled=true;
                    try{
                      await request("/handoffs/"+h.id+"/"+action,{method:"POST",body:"{}"});
                      setMessage("Handoff "+(action==="accept"?"accepted":"declined")+". Refreshing workflow.","success");
                      workflowButton.click();
                    }catch(error){setMessage(error.message,"error");actionButton.disabled=false;}
                  });
                  handoffRow.append(actionButton);
                }
              }
              handoffActions.append(handoffRow);
            });
            if((result.handoffs||[]).length){handoffActions.dataset.handoffActions="true";card.append(handoffActions);}
            setMessage("Workflow state loaded from the live API.","success");
          }catch(error){setMessage(error.message,"error");}
          finally{workflowButton.disabled=false;}
        });
        card.append(workflowButton);
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
        if(w.state==="failed"){
          const retryButton=document.createElement("button");retryButton.textContent="Retry failed task";
          retryButton.addEventListener("click",async()=>{
            retryButton.disabled=true;
            try{
              await request("/work-items/"+w.id+"/transition",{method:"POST",body:JSON.stringify({target_state:"ready"})});
              setMessage("Failed task returned to READY. Review the assignment, then admit it to the queue again.","success");
              await load();
            }catch(error){setMessage(error.message,"error");retryButton.disabled=false;}
          });
          card.append(retryButton);
        }
        if(["draft","ready","blocked","review","failed"].includes(w.state)){
          const cancelButton=document.createElement("button");cancelButton.textContent="Cancel task";
          cancelButton.addEventListener("click",async()=>{
            cancelButton.disabled=true;
            try{
              await request("/work-items/"+w.id+"/transition",{method:"POST",body:JSON.stringify({target_state:"cancelled"})});
              setMessage("Task cancelled. No external action was performed.","success");
              await load();
            }catch(error){setMessage(error.message,"error");cancelButton.disabled=false;}
          });
          card.append(cancelButton);
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

  byId("create-venture").addEventListener("click",async()=>{
    const title=byId("venture-title").value.trim(),slug=byId("venture-slug").value.trim();
    const evidenceUrl=byId("venture-evidence").value.trim();
    if(!title||!slug||!byId("venture-model").value.trim()||!byId("venture-market").value.trim()||!byId("venture-description").value.trim()){setMessage("Complete the required opportunity fields first.","error");return;}
    const evidence=evidenceUrl?[{url:evidenceUrl,note:"Owner-supplied research lead"}]:[];
    const button=byId("create-venture");button.disabled=true;
    try{
      await request("/venture-opportunities",{method:"POST",body:JSON.stringify({title,slug,business_model:byId("venture-model").value.trim(),target_market:byId("venture-market").value.trim(),description:byId("venture-description").value.trim(),evidence})});
      ["venture-title","venture-slug","venture-model","venture-market","venture-description","venture-evidence"].forEach(id=>byId(id).value="");
      await loadVenturePortfolio();setMessage("Opportunity added to the company-wide research portfolio.","success");
    }catch(error){setMessage(error.message,"error");button.disabled=false;}
  });
  byId("business-filter").addEventListener("change",()=>{if(csrfToken)load();});
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
      ["departments","agents","capabilities","work-items","commercial-opportunities","commercial-products","commercial-quotes","commercial-orders","venture-opportunities"].forEach(id=>clear(id,"Disconnected."));
      ["department-count","agent-count","specialist-count","work-count","queue-count","provider-state"].forEach(id=>byId(id).textContent="—");
      byId("provision").disabled=true;byId("provision-executive").disabled=true;byId("provision-specialists").disabled=true;byId("start-workers").disabled=true;byId("stop-workers").disabled=true;byId("create-executive-plan").disabled=true;byId("create-code-pr").disabled=true;byId("create-venture").disabled=true;byId("search-research").disabled=true;setMessage("Disconnected. The server session has been revoked.");
    }
  });
  byId("create-opportunity").addEventListener("click",async()=>{
    const customer=byId("opportunity-customer").value.trim();
    const need=byId("opportunity-need").value.trim();
    if(!customer||!need||!byId("opportunity-scope").checked){setMessage("Enter the customer and stated need, then confirm the single-business scope.","error");return;}
    const button=byId("create-opportunity");button.disabled=true;
    try{
      await request("/commercial/opportunities",{method:"POST",body:JSON.stringify({
        business_id:byId("opportunity-business").value,customer_name:customer,
        customer_contact:byId("opportunity-contact").value.trim()||null,
        customer_need:need,scope_confirmed:true
      })});
      byId("opportunity-customer").value="";byId("opportunity-contact").value="";
      byId("opportunity-need").value="";byId("opportunity-scope").checked=false;
      await loadCommercial();setMessage("Opportunity saved under one business unit. No customer was contacted.","success");
    }catch(error){setMessage(error.message,"error");}
    finally{button.disabled=false;}
  });
  byId("create-catalog-product").addEventListener("click",async()=>{
    const name=byId("catalog-name").value.trim(),description=byId("catalog-description").value.trim(),category=byId("catalog-category").value.trim();
    if(!name||!description||!category){setMessage("Complete the catalogue name, category and description.","error");return;}
    const button=byId("create-catalog-product");button.disabled=true;
    try{
      await request("/commercial/products",{method:"POST",body:JSON.stringify({
        business_id:byId("catalog-business").value,name,description,category
      })});
      byId("catalog-name").value="";byId("catalog-description").value="";byId("catalog-category").value="";
      await loadCommercial();setMessage("Catalogue entry saved as a private draft. Nothing was published.","success");
    }catch(error){setMessage(error.message,"error");}
    finally{button.disabled=false;}
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
    const businessId=byId("executive-business").value;
    if(!title||!objective){setMessage("Enter a plan title and objective.","error");return;}
    byId("create-executive-plan").disabled=true;
    try{
      const result=await request("/executive/plan",{method:"POST",body:JSON.stringify({title,objective,max_tasks:8,business_id:businessId})});
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
  byId("woo-business").addEventListener("change",async()=>{
    // Never carry one business's unsaved credentials into another business scope.
    byId("woo-url").value="";byId("woo-key").value="";byId("woo-secret").value="";
    byId("woo-status").textContent="Checking selected business connection…";
    byId("woo-results").textContent="No store data loaded.";
    try{await loadWooCommerceStatus();}catch(error){setMessage(error.message,"error");}
  });
  byId("woo-save").addEventListener("click",async()=>{
    const button=byId("woo-save");button.disabled=true;
    try{
      await request("/integrations/woocommerce/"+encodeURIComponent(byId("woo-business").value)+"/connection",{
        method:"PUT",body:JSON.stringify({
          store_url:byId("woo-url").value.trim(),
          consumer_key:byId("woo-key").value.trim(),
          consumer_secret:byId("woo-secret").value.trim()
        })
      });
      byId("woo-key").value="";byId("woo-secret").value="";
      await loadWooCommerceStatus();
      setMessage("Credentials encrypted and saved. No request was made to the store yet.","success");
    }catch(error){setMessage(error.message,"error");}
    finally{button.disabled=false;}
  });
  byId("woo-test").addEventListener("click",async()=>{
    const button=byId("woo-test");button.disabled=true;
    try{
      const result=await request("/integrations/woocommerce/"+encodeURIComponent(byId("woo-business").value)+"/test",{method:"POST"});
      byId("woo-results").textContent=JSON.stringify(result,null,2);
      setMessage("Read-only connection test succeeded.","success");
    }catch(error){setMessage(error.message,"error");}
    finally{button.disabled=false;}
  });
  byId("woo-products").addEventListener("click",()=>readWooCommerce("products"));
  byId("woo-orders").addEventListener("click",()=>readWooCommerce("orders"));
  byId("woo-disconnect").addEventListener("click",async()=>{
    if(!confirm("Disconnect the WooCommerce connection for this business? This deletes its encrypted credentials from OpenCompany."))return;
    const button=byId("woo-disconnect");button.disabled=true;
    try{
      await request("/integrations/woocommerce/"+encodeURIComponent(byId("woo-business").value)+"/connection",{method:"DELETE"});
      byId("woo-results").textContent="Store disconnected.";
      await loadWooCommerceStatus();
      setMessage("This business's WooCommerce credentials were disconnected.","success");
    }catch(error){setMessage(error.message,"error");button.disabled=false;}
  });
  byId("create-supplier").addEventListener("click",async()=>{
    const name=byId("supplier-name").value.trim();
    if(!name){setMessage("Enter a supplier or manufacturer name.","error");return;}
    const button=byId("create-supplier");button.disabled=true;
    try{
      await request("/commercial/suppliers",{method:"POST",body:JSON.stringify({
        business_id:byId("supplier-business").value,name,
        contact_name:byId("supplier-contact").value.trim()||null,
        email:byId("supplier-email").value.trim()||null,
        phone:byId("supplier-phone").value.trim()||null,
        country:byId("supplier-country").value.trim()||null,
        product_categories:byId("supplier-categories").value.split(",").map(v=>v.trim()).filter(Boolean),
        notes:byId("supplier-notes").value.trim()
      })});
      ["supplier-name","supplier-contact","supplier-email","supplier-phone","supplier-country","supplier-categories","supplier-notes"].forEach(id=>byId(id).value="");
      await loadCommercial();setMessage("Private supplier draft saved. No supplier was contacted.","success");
    }catch(error){setMessage(error.message,"error");button.disabled=false;}
  });
  // Restore the HttpOnly cookie session on every page load. Never persist the API key or CSRF token in browser storage.
  (async()=>{
    byId("connect").disabled=true;
    try{
      const response=await fetch("/auth/session",{method:"GET",credentials:"same-origin",cache:"no-store"});
      if(!response.ok){setMessage("Enter the owner API key to connect. Your previous session may have expired.");return;}
      const session=await response.json();
      csrfToken=session.csrf_token;
      await load();
    }catch(error){setMessage("Could not restore the owner session: "+error.message,"error");}
    finally{byId("connect").disabled=false;}
  })();
})();
</script>
</body>
</html>"""
