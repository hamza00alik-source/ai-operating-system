"""Small responsive owner dashboard for supervised technology discovery."""
from fastapi.responses import HTMLResponse

OWNER_HTML = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIOS · Company Control Center</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#121a2d;--line:#26334d;--muted:#9aa9c3;--text:#edf3ff;--accent:#7c9cff;--green:#51d6a1;--amber:#f4c66a;--red:#ff8585}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 15% 0%,#17264b 0,transparent 42%),var(--bg);color:var(--text);font:15px/1.5 system-ui, sans-serif}
main{max-width:1180px;margin:auto;padding:24px 18px 60px}.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
h1{font-size:clamp(25px,4vw,36px);margin:0}.muted,.hint{color:var(--muted)}.tag{border:1px solid var(--line);border-radius:99px;padding:5px 10px;color:var(--green);font-size:12px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:22px 0}
.panel,.metric{background:linear-gradient(145deg,#151f35,#10182a);border:1px solid var(--line);border-radius:15px;padding:16px}
.metric strong{display:block;font-size:28px}.metric span{color:var(--muted);font-size:13px}
h2{font-size:18px;margin:0 0 14px}.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
button,input,select{font:inherit;border-radius:9px;border:1px solid var(--line);padding:10px 12px;background:#0c1425;color:var(--text)}
button{cursor:pointer;background:#263d75;border-color:#4564ac}button.secondary{background:#172238}button:disabled{opacity:.55;cursor:wait}
label{display:flex;gap:7px;align-items:center;color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;min-width:760px}th,td{text-align:left;padding:11px 10px;border-bottom:1px solid var(--line);vertical-align:top;font-size:13px}th{color:var(--muted);font-weight:600}
.scroll{overflow:auto}.pill{display:inline-block;border:1px solid var(--line);border-radius:99px;padding:2px 8px;font-size:11px}.good{color:var(--green)}.warn{color:var(--amber)}.bad{color:var(--red)}
.status{margin:12px 0;color:var(--muted);min-height:24px}.small{font-size:12px;color:var(--muted)}a{color:#a9c0ff}.section{margin-top:18px}
main{max-width:1240px;padding:28px 24px 72px}
.top{position:relative;align-items:flex-start;padding:10px 0 18px;border-bottom:1px solid rgba(120,145,190,.18)}
.top .hint{margin-top:6px;max-width:680px}
nav.main-nav{position:sticky;top:0;z-index:10;display:flex;gap:7px;align-items:center;flex-wrap:nowrap;overflow-x:auto;padding:12px 0;margin:0 0 18px;background:rgba(11,16,32,.92);backdrop-filter:blur(14px);scrollbar-width:thin}
nav.main-nav a{flex:0 0 auto;text-decoration:none;color:#c6d4ef;background:#141f35;border:1px solid #293957;border-radius:9px;padding:8px 12px;font-size:13px;font-weight:600}
nav.main-nav a:hover,nav.main-nav a:focus{background:#263d75;border-color:#5475c0;color:white}
.panel{padding:20px;margin-top:18px;box-shadow:0 12px 32px rgba(0,0,0,.12)}
.panel>h2{display:flex;align-items:center;gap:10px;margin-bottom:10px;font-size:19px;letter-spacing:-.2px}
.panel>p.small{line-height:1.6;max-width:900px}
.grid{gap:14px;margin:18px 0}
.metric{min-width:0;padding:18px;background:linear-gradient(145deg,rgba(27,40,67,.95),rgba(16,25,43,.98))}
.metric strong{font-size:30px;line-height:1.2;margin-bottom:5px}
.metric span{display:block;line-height:1.45}
.toolbar{gap:9px}
.toolbar input:not([type=checkbox]),.toolbar select{min-height:42px}
button{min-height:40px;font-weight:600;transition:filter .15s,transform .15s}
button:hover{filter:brightness(1.13)}button:active{transform:translateY(1px)}
input:focus,select:focus,textarea:focus,button:focus-visible,a:focus-visible{outline:2px solid #89a7ff;outline-offset:2px}
.scroll{border:1px solid rgba(89,112,151,.22);border-radius:10px}
table{min-width:720px}th{position:sticky;top:0;background:#121b2e;z-index:1}
td{line-height:1.5}
#departmentChips{max-height:100px;overflow:auto;padding:2px 0}
#departmentChips .pill{padding:4px 9px;background:#101a2d}
#taskForm{display:grid;grid-template-columns:minmax(0,1fr) minmax(150px,210px) auto;align-items:center}
#taskApprovalPanel{line-height:1.6}
#taskApprovalPanel h3{margin:22px 0 10px}
#providerStatus,#credentialStatus{white-space:pre-line}
#modelOutput{max-height:420px;overflow:auto;line-height:1.55}
#discovery{margin-top:18px}
#discovery .toolbar{margin:14px 0}
#discovery label{background:#101a2d;border:1px solid var(--line);border-radius:9px;padding:8px 10px}
#discovery label input{accent-color:#7c9cff}
#models textarea{min-height:90px}
#models pre{font-size:13px}
@media(max-width:760px){
 main{padding:16px 12px 48px}
 .top{gap:14px;padding-top:4px}
 .top .toolbar{width:100%;justify-content:space-between}
 .top .tag{max-width:70%;line-height:1.4}
 h1{font-size:26px;line-height:1.2}
 nav.main-nav{margin:0 -12px 12px;padding:10px 12px}
 .panel{padding:15px;margin-top:14px;border-radius:13px}
 .panel>h2{font-size:17px}
 .grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:12px 0}
 .metric{padding:14px 12px;border-radius:12px}
 .metric strong{font-size:26px}
 .metric span{font-size:12px}
 .toolbar{align-items:stretch}
 .toolbar button{flex:0 0 auto}
 #taskForm{grid-template-columns:1fr;gap:9px}
 #taskForm input,#taskForm select,#taskForm button{width:100%;min-width:0}
 #agentSearch{min-width:0!important;width:100%}
 #departmentFilter{flex:1;min-width:0}
 #loadAgents{width:auto}
 #departmentChips{max-height:82px}
 #discovery .toolbar{gap:7px}
 #discovery label{font-size:12px}
 #models .toolbar{display:grid;grid-template-columns:1fr 1fr}
 #providerSelect{grid-column:1/-1;width:100%}
 #models .toolbar button{width:100%}
 #providerApiKey{min-width:0!important;width:100%}
 #saveProviderKey{width:100%}
 #models pre{font-size:12px}
}
[data-view-panel]{display:none}[data-view-panel].active-view{display:block}
nav.main-nav a.active{background:#29477f;border-color:#7899e8;color:#fff;box-shadow:0 0 0 1px #7899e844}
.view-heading{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:8px 0 16px}
.view-heading p{margin:0;color:var(--muted);font-size:13px}
@media(max-width:760px){nav.main-nav{position:sticky;top:0;gap:6px;padding:9px 10px}nav.main-nav a{padding:9px 11px;font-size:12px}.view-heading{align-items:flex-start;flex-direction:column}}
@media(min-width:1100px){
 #overview .grid{grid-template-columns:repeat(4,minmax(0,1fr))}
 #workforce .scroll,#sources .scroll,#tasks .scroll,#discovery+.panel .scroll{max-height:560px}
}

:root{--bg:#080d18;--panel:#101a2c;--line:#253653;--muted:#9aabc7;--text:#eef4ff;--accent:#88a9ff;--green:#55e0ae;--amber:#ffd27b;--red:#ff8585}
body{background:radial-gradient(900px 520px at 8% -10%,rgba(59,99,190,.28),transparent 65%),radial-gradient(700px 420px at 100% 0%,rgba(91,62,180,.16),transparent 65%),#080d18;letter-spacing:.005em}
main{max-width:1380px;padding:30px 30px 84px}
.top{padding:22px 24px 24px;border:1px solid rgba(132,162,220,.2);border-radius:22px;background:linear-gradient(120deg,rgba(25,43,76,.92),rgba(14,23,41,.9) 58%,rgba(34,29,68,.75));box-shadow:0 24px 70px rgba(0,0,0,.25);overflow:hidden}
.top:before{content:"";position:absolute;width:250px;height:250px;right:12%;top:-180px;border-radius:50%;background:#7597ff;filter:blur(90px);opacity:.24;pointer-events:none}
.top>div:first-child{position:relative;z-index:1}.top .muted{font-size:11px;font-weight:800;letter-spacing:.16em;color:#a9c2f5}
h1{font-size:clamp(28px,4vw,42px);letter-spacing:-.045em;margin:5px 0 2px}.top .hint{font-size:14px;color:#b4c4df}
.tag{display:inline-flex;align-items:center;gap:7px;padding:7px 12px;border-color:rgba(112,146,220,.35);background:rgba(9,18,35,.38);color:#c7d8ff;font-weight:650}
#apiHealth{border-color:rgba(85,224,174,.32);color:var(--green)}#apiHealth.offline{color:var(--red);border-color:rgba(255,133,133,.4)}#apiHealth.degraded{color:var(--amber);border-color:rgba(255,210,123,.4)}
nav.main-nav{top:8px;margin:14px 0 22px;padding:9px;border:1px solid rgba(112,140,190,.18);border-radius:15px;background:rgba(9,15,27,.88);box-shadow:0 12px 32px rgba(0,0,0,.18)}
nav.main-nav a{border-radius:10px;padding:10px 14px;background:transparent;border-color:transparent;color:#aebed9;transition:all .18s ease}
nav.main-nav a:hover{background:rgba(115,148,218,.12);border-color:rgba(115,148,218,.2);transform:translateY(-1px)}
nav.main-nav a.active{background:linear-gradient(135deg,#35599c,#263f78);border-color:#7899e8;box-shadow:0 5px 18px rgba(53,89,156,.3);color:#fff}
.panel{border:1px solid rgba(112,140,190,.2);border-radius:18px;background:linear-gradient(155deg,rgba(19,30,51,.98),rgba(12,20,35,.98));box-shadow:0 16px 42px rgba(0,0,0,.16);padding:22px;transition:border-color .18s ease,transform .18s ease}
.panel:hover{border-color:rgba(132,162,220,.34)}.panel>h2{font-size:20px;letter-spacing:-.025em}
.grid{gap:13px}.metric{position:relative;overflow:hidden;border:1px solid rgba(119,148,201,.2);border-radius:16px;background:linear-gradient(145deg,rgba(31,48,78,.92),rgba(15,25,43,.98));padding:20px}
.metric:after{content:"";position:absolute;width:80px;height:80px;right:-36px;top:-38px;border-radius:50%;background:rgba(116,151,235,.13);filter:blur(3px)}
.metric strong{font-size:32px;letter-spacing:-.04em;font-variant-numeric:tabular-nums}.metric span{font-size:12px;letter-spacing:.015em}
button{border-radius:10px;background:linear-gradient(135deg,#4269b3,#2d4e8b);border-color:#547bc6;box-shadow:0 5px 14px rgba(25,52,102,.22)}
button.secondary{background:#17243a;border-color:#304563;box-shadow:none}button:hover:not(:disabled){filter:brightness(1.13);transform:translateY(-1px)}button:disabled{opacity:.48;box-shadow:none}
input,select,textarea{background:#0a1425;border-color:#2a3c5a;border-radius:10px}input::placeholder,textarea::placeholder{color:#7183a1}
.scroll{border-color:rgba(112,140,190,.2);border-radius:12px}th{background:#111d31;color:#a9bbd9}td{border-bottom-color:rgba(112,140,190,.14)}
.pill{padding:4px 9px;background:rgba(12,22,39,.55);font-weight:650}.status{padding:9px 12px;border-radius:10px;background:rgba(12,22,39,.55);border:1px solid rgba(112,140,190,.15)}
#runtimeStatus{margin-top:12px;padding:12px 14px;border:1px solid rgba(85,224,174,.2);border-radius:12px;background:rgba(23,70,63,.14);color:#b8d9d1}
#agentRunOutput .card,#brain .card{border:1px solid rgba(112,140,190,.2);border-radius:13px;padding:14px;background:rgba(8,15,28,.52)}
#agentRunOutput pre,#brain pre,#modelOutput{border:1px solid rgba(112,140,190,.18)!important;border-radius:12px!important;background:#091323!important;padding:14px!important}
#loginPanel{background:rgba(4,8,16,.88)!important;backdrop-filter:blur(18px)}#loginPanel form{border-radius:20px!important;border:1px solid rgba(132,162,220,.28)!important;background:linear-gradient(145deg,#172742,#0d1729)!important;box-shadow:0 28px 90px rgba(0,0,0,.48)!important;padding:26px!important}
#loginPanel h2{font-size:24px;letter-spacing:-.03em}a{color:#a9c4ff;text-decoration-thickness:1px;text-underline-offset:3px}a:hover{color:#d4e1ff}
@media(max-width:760px){main{padding:14px 12px 48px}.top{padding:18px 16px;border-radius:17px}.top .toolbar{justify-content:flex-start}.top .tag{max-width:none}nav.main-nav{top:4px;margin:10px -12px 14px;padding:8px 10px;border-radius:0 0 13px 13px}nav.main-nav a{padding:9px 11px}.panel{padding:16px;border-radius:15px}.metric{padding:15px 12px}.metric strong{font-size:27px}.toolbar button{min-height:42px}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}


/* SCI-FI COMMAND DECK — visual layer only; existing API and workflows remain intact */
:root{--neon:#6ce9ff;--violet:#a78bfa;--mint:#67f3c0;--ink:#070b16}
body{background-color:var(--ink);background-image:linear-gradient(rgba(74,119,183,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(74,119,183,.045) 1px,transparent 1px),radial-gradient(ellipse at 12% 0%,rgba(36,115,181,.28),transparent 48%),radial-gradient(ellipse at 95% 12%,rgba(115,70,190,.2),transparent 42%),linear-gradient(180deg,#080e1d,#070b16 70%);background-size:32px 32px,32px 32px,auto,auto,auto}
main{max-width:1500px}
.top{border-color:rgba(108,233,255,.24);background:linear-gradient(112deg,rgba(13,35,59,.96),rgba(13,19,39,.96) 55%,rgba(35,24,65,.88));box-shadow:0 0 0 1px rgba(108,233,255,.035),0 24px 80px rgba(0,0,0,.4),inset 0 1px rgba(255,255,255,.05)}
.top:after{content:"";position:absolute;inset:auto -5% -90px 45%;height:150px;background:radial-gradient(ellipse,rgba(108,233,255,.15),transparent 68%);pointer-events:none}
.top .muted{color:#80d9f1}h1{background:linear-gradient(100deg,#f2fbff 8%,#9cecff 50%,#c2b5ff 95%);-webkit-background-clip:text;background-clip:text;color:transparent}
.tag{border-color:rgba(108,233,255,.28);background:rgba(8,24,40,.58)}
nav.main-nav{border-color:rgba(108,233,255,.17);background:rgba(5,12,25,.9);box-shadow:0 12px 36px rgba(0,0,0,.35)}
nav.main-nav a.active{background:linear-gradient(120deg,rgba(22,117,154,.75),rgba(79,60,145,.72));border-color:rgba(108,233,255,.65);box-shadow:0 0 22px rgba(108,233,255,.12)}
.panel{border-color:rgba(102,169,207,.2);background:linear-gradient(150deg,rgba(13,27,47,.97),rgba(9,16,31,.98));box-shadow:0 18px 48px rgba(0,0,0,.22),inset 0 1px rgba(255,255,255,.025)}
.panel:hover{border-color:rgba(108,233,255,.34)}.metric{border-color:rgba(108,233,255,.17);background:linear-gradient(145deg,rgba(17,46,68,.92),rgba(13,22,41,.98))}.metric:after{background:rgba(108,233,255,.16)}
button{background:linear-gradient(120deg,#176b91,#394d9a);border-color:rgba(108,233,255,.55);box-shadow:0 0 18px rgba(47,174,213,.12)}button.secondary{background:rgba(17,34,56,.9);border-color:rgba(116,155,203,.32)}
input,select,textarea{border-color:rgba(108,157,197,.28);background:rgba(5,14,29,.9)}.pill{border-color:rgba(108,233,255,.2)}
#runtimeStatus{border-color:rgba(103,243,192,.23);background:rgba(19,79,72,.15)}
.command-stage{position:relative;overflow:hidden;margin:18px 0 4px;padding:22px;border:1px solid rgba(108,233,255,.22);border-radius:20px;background:linear-gradient(115deg,rgba(8,24,42,.96),rgba(16,21,46,.96));box-shadow:inset 0 1px rgba(255,255,255,.04),0 22px 55px rgba(0,0,0,.22)}
.command-stage:before{content:"";position:absolute;inset:0;background:linear-gradient(90deg,transparent 49.8%,rgba(108,233,255,.07) 50%,transparent 50.2%),linear-gradient(0deg,transparent 49.8%,rgba(108,233,255,.05) 50%,transparent 50.2%);background-size:48px 48px;mask-image:linear-gradient(90deg,transparent,#000 35%,#000 90%,transparent);pointer-events:none}
.stage-head{position:relative;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.eyebrow{font-size:10px;font-weight:850;letter-spacing:.2em;color:var(--neon);text-transform:uppercase}.stage-title{font-size:20px;font-weight:800;letter-spacing:-.03em;margin:4px 0}.stage-note{font-size:12px;color:#9eb2d1}
.stage-indicator{display:inline-flex;align-items:center;gap:8px;padding:7px 10px;border:1px solid rgba(103,243,192,.25);border-radius:99px;background:rgba(7,35,37,.45);font-size:11px;color:#a6e9d4}
.stage-indicator:before{content:"";width:7px;height:7px;border-radius:50%;background:#67f3c0;box-shadow:0 0 12px #67f3c0}
.employee-stage{position:relative;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.employee-card{position:relative;display:grid;grid-template-columns:78px minmax(0,1fr);align-items:center;gap:12px;min-height:126px;padding:12px;border:1px solid rgba(114,165,210,.2);border-radius:15px;background:linear-gradient(145deg,rgba(20,42,68,.88),rgba(10,18,35,.94));overflow:hidden}
.employee-card:after{content:"";position:absolute;right:-30px;top:-35px;width:100px;height:100px;border-radius:50%;background:var(--avatar-glow,rgba(108,233,255,.14));filter:blur(24px);pointer-events:none}
.employee-copy{position:relative;z-index:1;min-width:0}.employee-name{font-size:13px;font-weight:800;line-height:1.25;overflow-wrap:anywhere}.employee-dept{font-size:11px;color:#a9bdd9;margin-top:5px}.employee-state{font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:#7de6f4;margin-top:8px}
.avatar-scene{position:relative;width:76px;height:98px;display:flex;align-items:flex-end;justify-content:center;filter:drop-shadow(0 8px 12px rgba(0,0,0,.35))}
.avatar-halo{position:absolute;width:70px;height:70px;top:7px;border:1px solid rgba(108,233,255,.35);border-radius:50%;box-shadow:0 0 18px rgba(108,233,255,.12),inset 0 0 16px rgba(108,233,255,.08)}
.avatar-body{position:absolute;bottom:0;width:62px;height:42px;border-radius:25px 25px 10px 10px;background:linear-gradient(120deg,var(--avatar-main,#247a9c),#182e55 68%,#10182d);border:1px solid rgba(176,234,255,.42);box-shadow:inset 0 3px 10px rgba(255,255,255,.12)}
.avatar-neck{position:absolute;bottom:37px;width:15px;height:17px;background:#b8a4a0;border-radius:4px;z-index:2}.avatar-head{position:absolute;bottom:49px;width:37px;height:42px;border-radius:45% 45% 42% 42%;background:linear-gradient(130deg,#f1c7b5,#9e7889);border:1px solid rgba(255,255,255,.4);z-index:3;box-shadow:inset -5px -3px 0 rgba(58,42,69,.15)}
.avatar-hair{position:absolute;bottom:73px;width:42px;height:24px;border-radius:60% 55% 25% 20%;background:linear-gradient(120deg,var(--avatar-hair,#a6c8e8),#26385f);z-index:4;transform:rotate(-4deg);box-shadow:inset 0 -4px rgba(0,0,0,.18)}
.avatar-visor{position:absolute;bottom:61px;width:38px;height:10px;border-radius:7px;background:linear-gradient(90deg,rgba(13,35,63,.95),var(--avatar-glow,#6ce9ff));border:1px solid rgba(190,250,255,.75);z-index:5;box-shadow:0 0 12px var(--avatar-glow,#6ce9ff)}
.avatar-badge{position:absolute;bottom:7px;z-index:6;width:18px;height:18px;border-radius:50%;display:grid;place-items:center;background:#09182b;border:1px solid rgba(108,233,255,.6);color:#b7f5ff;font-size:9px;font-weight:900}
.employee-card:nth-child(2){--avatar-main:#684b9b;--avatar-hair:#d0a9f7;--avatar-glow:rgba(181,133,255,.25)}.employee-card:nth-child(3){--avatar-main:#247b70;--avatar-hair:#78d8c2;--avatar-glow:rgba(103,243,192,.24)}.employee-card:nth-child(4){--avatar-main:#9a633c;--avatar-hair:#efbd7d;--avatar-glow:rgba(255,190,112,.24)}
.stage-footer{position:relative;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:14px;padding-top:12px;border-top:1px solid rgba(108,233,255,.12);font-size:11px;color:#8fa7c8}
.stage-empty{grid-column:1/-1;padding:18px;border:1px dashed rgba(108,233,255,.2);border-radius:12px;color:#9eb2d1;font-size:12px}
@media(max-width:900px){.employee-stage{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:520px){.command-stage{padding:15px}.employee-stage{grid-template-columns:1fr}.employee-card{min-height:112px}.stage-title{font-size:18px}}

</style></head>
<body><div id="loginPanel" style="position:fixed;inset:0;z-index:20;background:#080d19ee;display:flex;align-items:center;justify-content:center;padding:20px"><form id="loginForm" class="panel" style="width:min(420px,100%)"><h2>Owner sign in</h2><p class="small">Enter your Owner API Key once. AIOS will create a secure 14-day browser session. The key is not saved in browser storage.</p><input id="loginKey" type="password" autocomplete="current-password" placeholder="AIOS Owner API Key" required style="width:100%;margin:8px 0"><button id="loginButton" type="submit" style="width:100%">Sign in securely</button><div id="loginStatus" class="status" role="status"></div></form></div><main>
<div class="top"><div><div class="muted">AI OPERATING SYSTEM / OWNER CONSOLE</div><h1>AI Company Control Center</h1><div class="hint">Your AI company, workforce, research pipeline and approvals — in one supervised workspace.</div></div><div class="toolbar"><span class="tag">Owner-supervised · bounded AI execution</span><span id="apiHealth" class="tag">Checking API…</span><button id="logoutButton" class="secondary">Log out</button></div></div>
<nav class="toolbar main-nav" aria-label="Main sections"><a href="#overview" data-view="overview">Company</a><a href="#workforce" data-view="workforce">Workforce</a><a href="#sources" data-view="sources">Repositories</a><a href="#tasks" data-view="tasks">Tasks & approvals</a><a href="#discovery" data-view="discovery">Technology</a><a href="#models" data-view="models">AI models</a><a href="#brain" data-view="brain">AI Brain</a></nav>
<section class="command-stage" aria-label="AI employee command stage">
 <div class="stage-head"><div><div class="eyebrow">Neural command deck / workforce visualization</div><div class="stage-title">Meet the AI workforce</div><div class="stage-note">Stylized role representations generated from the live workforce catalogue — not fabricated active-worker status.</div></div><span id="stageRuntime" class="stage-indicator">Runtime status loading</span></div>
 <div id="employeeStage" class="employee-stage"><div class="stage-empty">Loading real specialist roles from the AIOS workforce catalogue…</div></div>
 <div class="stage-footer"><span>ROLE STATUS · ON-DEMAND INVOCATION</span><span>Owner-supervised execution · no external actions without approval</span></div>
</section>
<section id="overview" class="panel section" data-view-panel="overview"><h2>Company operations</h2><div class="grid" style="margin:10px 0"><div class="metric"><strong id="workforceCount">283</strong><span>Catalogued specialists</span></div><div class="metric"><strong id="departmentCount">18</strong><span>Departments</span></div><div class="metric"><strong id="taskCount">—</strong><span>Tasks</span></div><div class="metric"><strong id="approvalCount">—</strong><span>Pending approvals</span></div></div><div id="companyStatus" class="small">Workforce catalog loaded. Bounded specialist execution and CEO review are available for text-only tasks; external actions remain disabled.</div><div id="runtimeStatus" class="small" role="status">Checking agent worker health…</div></section>
<section id="workforce" class="panel section" data-view-panel="workforce"><h2>Agency workforce · 283 specialists</h2><p class="small">18 departments · 284 roles including CEO. Source: <a href="https://github.com/hamza00alik-source/agency-agents" target="_blank" rel="noopener">Agency Agents repository</a> · MIT. Roles are invoked on demand by a shared worker; they are not 283 always-on processes.</p><div class="toolbar"><input id="agentSearch" placeholder="Search 283 specialists…" style="flex:1;min-width:180px"><select id="departmentFilter"><option value="">All departments</option></select><button id="loadAgents" class="secondary">Refresh roster</button></div><div id="departmentChips" class="toolbar section"></div><div class="scroll section"><table><thead><tr><th>Specialist</th><th>Department</th><th>Runtime state</th><th>Source</th></tr></thead><tbody id="agentRows"><tr><td colspan="4">Loading workforce catalog…</td></tr></tbody></table></div></section>
<section id="sources" class="panel section" data-view-panel="sources"><h2>Repository intelligence · 12 sources</h2><p class="small">The Agency Agents workforce and Automaton runtime reference are separated from the ten company/platform comparison repositories. Reference status does not mean code is installed or trusted.</p><div class="scroll"><table><thead><tr><th>Repository</th><th>Role</th><th>Current state</th><th>Purpose</th><th>License</th></tr></thead><tbody id="sourceRows"><tr><td colspan="5">Loading repository inventory…</td></tr></tbody></table></div></section>
<section id="tasks" class="panel section" data-view-panel="tasks"><h2>Tasks & owner approvals</h2><form id="taskForm" class="toolbar"><input id="taskTitle" required maxlength="200" placeholder="New company task" style="flex:1;min-width:180px"><select id="taskDepartment"><option value="general">General</option><option value="research">Research</option><option value="engineering">Engineering</option><option value="product">Product</option><option value="marketing">Marketing</option><option value="sales">Sales</option><option value="finance">Finance</option><option value="operations">Operations</option><option value="support">Support</option></select><button type="submit">Create task</button></form><div class="toolbar section"><button id="loadOperations" class="secondary">Refresh operations</button><span class="small">Owner approval remains mandatory for consequential actions.</span></div><div id="taskApprovalPanel" class="small">No operational data loaded.</div><div id="agentRunOutput" class="section" aria-live="polite"></div></section>
<section id="discovery" class="panel" data-view-panel="discovery">
<h2>Technology discovery</h2>
<div class="grid discovery-metrics"><div class="metric"><strong id="scans">—</strong><span>Discovery scans</span></div><div class="metric"><strong id="candidates">—</strong><span>Candidate projects</span></div><div class="metric"><strong id="review">—</strong><span>Needs review</span></div><div class="metric"><strong id="integrated">0</strong><span>Integrated from this pipeline</span></div></div>
<h2>Run a discovery scan</h2>
<div class="toolbar">
<label><input type="checkbox" name="cat" value="agent-frameworks" checked> Agent frameworks</label>
<label><input type="checkbox" name="cat" value="mcp-servers" checked> MCP servers</label>
<label><input type="checkbox" name="cat" value="rag-storage"> RAG & storage</label>
<label><input type="checkbox" name="cat" value="self-hosted"> Self-hosted</label>
<label><input type="checkbox" name="cat" value="llm-tools"> LLM tools</label>
<button id="run">Queue scan</button><button class="secondary" id="refresh">Refresh</button>
</div>
<div class="small">Scans read public GitHub repository metadata only. They do not install software, connect accounts, or change production.</div>
<div id="message" class="status" role="status">Connect with your owner API key to load live data.</div>
</section>
<section id="scanHistory" class="panel section" data-view-panel="discovery"><h2>Recent scans</h2><div class="scroll"><table><thead><tr><th>Created</th><th>Categories</th><th>Status</th><th>Results</th><th>Error</th></tr></thead><tbody id="scanRows"><tr><td colspan="5" class="muted">No data loaded</td></tr></tbody></table></div></section>
<section id="discoveredProjects" class="panel section" data-view-panel="discovery"><h2>Discovered projects</h2><div class="scroll"><table><thead><tr><th>Project</th><th>Category</th><th>License</th><th>Maintenance</th><th>Stars</th><th>Review state</th><th>Evidence</th></tr></thead><tbody id="candidateRows"><tr><td colspan="7" class="muted">No data loaded</td></tr></tbody></table></div></section>
<p class="small section" data-view-panel="discovery">Cost, security, commercial-use rights, and provider terms remain unverified unless the evidence record explicitly says otherwise. A discovered project is not an approved integration.</p>

<section id="brain" class="panel section" data-view-panel="brain">
<h2>Company AI Brain · persistent learning</h2>
<p class="small">Provider-independent memory stored in our own SQLite database. Completed runs become experiences automatically. Reusable lessons remain proposed until you approve them; only approved memories are supplied to future agents.</p>
<div class="grid"><div class="metric"><strong id="brainExperiences">—</strong><span>Stored experiences</span></div><div class="metric"><strong id="brainApproved">—</strong><span>Approved memories</span></div><div class="metric"><strong id="brainProposed">—</strong><span>Awaiting owner review</span></div><div class="metric"><strong id="brainRejected">—</strong><span>Rejected memories</span></div></div>
<div class="toolbar section"><button class="secondary" id="refreshBrain">Refresh brain</button><span id="brainMode" class="small">Loading brain status…</span></div>
<h3>Proposed lessons · owner review required</h3><div id="brainProposals" class="small">Loading proposed memories…</div>
<h3>Approved knowledge used by agents</h3><div id="brainApprovedList" class="small">Loading approved memories…</div>
<p class="small">Current learning is persistent experience capture plus approved-memory retrieval, not neural-network training. Local lexical retrieval needs no embeddings or additional model calls. The model gateway is still required for advanced reasoning.</p>
</section>
<section id="models" class="panel section" data-view-panel="models"><h2>Live AI model gateway</h2>
<div class="small">OpenRouter keys are encrypted on the server before storage. The first connection uses only the free-model router and has no paid fallback. Use HTTPS.</div>
<div class="section" style="border:1px solid var(--line);border-radius:10px;padding:12px"><strong>Provider credentials · OpenRouter</strong><div class="small">Enter your OpenRouter key here. It is sent only to the authenticated server, encrypted at rest, and never returned to this page. Do not paste it into chat or GitHub.</div><div class="toolbar" style="margin-top:10px"><input id="providerApiKey" type="password" autocomplete="off" placeholder="OpenRouter API key" style="flex:1;min-width:220px"><button id="saveProviderKey">Save encrypted key</button></div><label style="margin-top:10px"><input id="confirmFreeOnly" type="checkbox"> I confirm this connection must use the free-only router, with no paid model or paid fallback.</label><div id="credentialStatus" class="status">Credential status not loaded.</div></div></div>
<div class="toolbar" style="margin-top:12px"><select id="providerSelect"><option value="">Loading providers…</option></select><button class="secondary" id="loadProviders">Refresh providers</button><button id="testProvider">Test live connection</button></div>
<div id="providerStatus" class="status">Provider status not loaded.</div>
<textarea id="modelPrompt" rows="3" style="width:100%;margin:8px 0" placeholder="Enter a small test prompt. This sends a real request to the selected provider."></textarea>
<button id="runModel">Run real model request</button>
<pre id="modelOutput" style="white-space:pre-wrap;overflow-wrap:anywhere;background:#0c1425;border:1px solid var(--line);border-radius:9px;padding:12px;min-height:60px">No live inference run yet.</pre>
</section>
</main>
<script>
const $=id=>document.getElementById(id);let authenticated=false;
function activateView(name){document.querySelectorAll("[data-view-panel]").forEach(el=>el.classList.toggle("active-view",el.dataset.viewPanel===name));document.querySelectorAll("nav.main-nav a[data-view]").forEach(a=>{const active=a.dataset.view===name;a.classList.toggle("active",active);if(active)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current")});if(location.hash!=="#"+name)history.replaceState(null,"","#"+name);window.scrollTo({top:0,behavior:"smooth"});}
document.querySelectorAll("nav.main-nav a[data-view]").forEach(a=>a.addEventListener("click",e=>{e.preventDefault();activateView(a.dataset.view)}));

const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function say(s){$("message").textContent=s}
activateView(location.hash.slice(1)||"overview");
function setApiHealth(label,state=""){const el=$("apiHealth");if(!el)return;el.textContent=label;el.classList.toggle("offline",state==="offline");el.classList.toggle("degraded",state==="degraded");}
async function api(path,options={}){
 let response;
 try{response=await fetch(path,{...options,credentials:"same-origin",headers:{"Content-Type":"application/json",...(options.headers||{})}});}
 catch(error){setApiHealth("API unreachable","offline");throw Error("Cannot reach the AIOS API. Check your connection and reload the dashboard.");}
 setApiHealth("API connected");
 let raw="";try{raw=await response.text()}catch(_){}
 let payload=null;try{payload=raw?JSON.parse(raw):null}catch(_){}
 if(response.status===401){showLogin("Your owner session expired. Sign in again.");throw Error("Owner session expired. Please sign in again.");}
 if(!response.ok){const detail=payload?.detail||payload?.error||raw.slice(0,300)||"No error details returned.";setApiHealth("API error · "+response.status,"degraded");throw Error("API "+response.status+": "+detail);}
 if(!raw)return {};
 try{return JSON.parse(raw)}catch(_){throw Error("The AIOS API returned an invalid JSON response for "+path+".");}
}
function date(s){return s?new Date(s).toLocaleString():"—"}
function failureAdvice(message){
 const value=String(message||"");
 if(/empty or placeholder text/i.test(value))return "The API is reachable, but OpenRouter returned no usable model text. This is an upstream model-response failure, not a dashboard route failure. Check the selected free model's availability or quota, run the provider connection test, then retry manually. AIOS did not auto-retry or consume another request.";
 if(/Provider HTTP 429|rate limit/i.test(value))return "The provider appears to have rate-limited this request. Wait for its free quota window to reset, test the connection, then retry manually.";
 if(/Provider HTTP 401|Provider HTTP 403/i.test(value))return "The provider rejected the credential or access. Review the saved provider connection in AI models; never paste the key into chat.";
 if(/Provider connection failed|timed out/i.test(value))return "The upstream provider did not respond in time. Check provider availability and retry after a manual connection test.";
 return "The run stopped safely. Review the error above and the execution timeline before retrying.";
}
async function refresh(){try{const [scans,candidates]=await Promise.all([api("/discovery/scans"),api("/discovery/candidates")]);$("scans").textContent=scans.length;$("candidates").textContent=candidates.length;$("review").textContent=candidates.filter(c=>c.status==="needs-review").length;
$("scanRows").innerHTML=scans.length?scans.map(s=>'<tr><td>'+esc(date(s.created_at))+'</td><td>'+esc((s.categories||[]).join(", "))+'</td><td><span class="pill">'+esc(s.status)+'</span></td><td>'+esc(s.result_count)+'</td><td class="bad">'+esc(s.error||"—")+'</td></tr>').join():'<tr><td colspan="5">No scans yet</td></tr>';
$("candidateRows").innerHTML=candidates.length?candidates.map(c=>'<tr><td><a target="_blank" rel="noopener" href="'+esc(c.canonical_url)+'">'+esc(c.full_name)+'</a><div class="small">'+esc(c.description)+'</div></td><td>'+esc(c.category)+'</td><td>'+esc(c.license)+'</td><td>'+esc(c.maintenance)+'</td><td>'+esc(c.stars)+'</td><td><span class="pill '+(c.review_state==="rejected"?"bad":c.review_state==="approved-for-sandbox"?"good":"warn")+'">'+esc(c.review_state||"pending")+'</span><div class="small">Metadata: '+esc(c.status)+'</div><button class="secondary" data-url="'+esc(c.canonical_url)+'" data-decision="approved-for-sandbox" onclick="reviewCandidate(this.dataset.url,this.dataset.decision)">Approve sandbox</button> <button class="secondary" data-url="'+esc(c.canonical_url)+'" data-decision="rejected" onclick="reviewCandidate(this.dataset.url,this.dataset.decision)">Reject</button></td><td><a target="_blank" rel="noopener" href="'+esc(c.evidence?.url||c.canonical_url)+'">Source</a><div class="small">Cost: '+esc(c.evidence?.cost||"unknown")+' · Security: '+esc(c.evidence?.security||"not-tested")+'</div></td></tr>').join():'<tr><td colspan="7">No candidates yet. Queue a scan to discover projects.</td></tr>';
say("Live data loaded at "+new Date().toLocaleTimeString()+".");}catch(e){say(e.message)}}
$("run").onclick=async()=>{const categories=[...document.querySelectorAll('input[name="cat"]:checked')].map(x=>x.value);if(!categories.length){say("Select at least one category.");return}try{$("run").disabled=true;const result=await api("/discovery/scans",{method:"POST",body:JSON.stringify({categories})});say("Scan queued: "+result.id+". The background worker must be running to process it.");await refresh()}catch(e){say(e.message)}finally{$("run").disabled=false}};
$("refresh").onclick=refresh;
window.reviewCandidate=async(url,decision)=>{const label=decision==="approved-for-sandbox"?"Approve for isolated sandbox review":"Reject candidate";if(!confirm(label+"? This records your decision only; it will not install or execute anything."))return;const notes=prompt("Optional review notes:")||"";try{await api("/discovery/candidates/review",{method:"POST",body:JSON.stringify({repository_url:url,decision,notes})});say("Owner decision saved. No software was installed or executed.");await refresh()}catch(e){say(e.message)}};


async function loadAgents(){
 try{
  const q=$("agentSearch").value.trim(),dep=$("departmentFilter").value;
  const params=new URLSearchParams();if(q)params.set("q",q);if(dep)params.set("department",dep);
  const data=await api("/workforce/agents?"+params.toString());
  $("workforceCount").textContent=data.agent_count;$("departmentCount").textContent=data.department_count;
  const select=$("departmentFilter"),current=select.value;
  if(select.options.length===1){for(const d of data.departments){const o=document.createElement("option");o.value=d.id;o.textContent=d.name+" ("+d.agent_count+")";select.appendChild(o)}}
  if(current)select.value=current;
  $("departmentChips").innerHTML=data.departments.map(d=>'<span class="pill">'+esc(d.name)+': '+esc(d.agent_count)+'</span>').join("");
  const stageAgents=data.agents.slice(0,4);
  $("employeeStage").innerHTML=stageAgents.length?stageAgents.map((a,i)=>'<article class="employee-card"><div class="avatar-scene" aria-hidden="true"><div class="avatar-halo"></div><div class="avatar-body"></div><div class="avatar-neck"></div><div class="avatar-head"></div><div class="avatar-hair"></div><div class="avatar-visor"></div><div class="avatar-badge">'+(i+1)+'</div></div><div class="employee-copy"><div class="employee-name">'+esc(a.name)+'</div><div class="employee-dept">'+esc(a.department)+'</div><div class="employee-state">Available on demand</div></div></article>').join(""):'<div class="stage-empty">No matching role records returned by the workforce API.</div>';
  $("agentRows").innerHTML=data.agents.map(a=>'<tr><td><strong>'+esc(a.name)+'</strong><div class="small">'+esc(a.id)+'</div></td><td>'+esc(a.department)+'</td><td><span class="pill warn">Available on demand</span></td><td><a href="'+esc(a.source_url)+'" target="_blank" rel="noopener">Agent instructions</a></td></tr>').join("")||'<tr><td colspan="4">No matching specialists.</td></tr>';
  $("companyStatus").textContent="Source: "+data.source_repository+" · License: "+data.license+" · 283 specialist definitions indexed. Shared agent worker: invokes the best-matched specialist instructions for each task, then performs CEO review. Check worker health in Company operations.";
 }catch(e){$("agentRows").innerHTML='<tr><td colspan="4">'+esc(e.message)+'</td></tr>'}
}

async function loadSources(){
 try{
  const data=await api("/company/sources");
  $("sourceRows").innerHTML=data.sources.map(s=>'<tr><td><a href="https://github.com/'+esc(s.repository)+'" target="_blank" rel="noopener">'+esc(s.repository)+'</a></td><td>'+esc(s.role)+'</td><td><span class="pill '+(s.status==="catalogued"?"good":"warn")+'">'+esc(s.status)+'</span></td><td>'+esc(s.purpose)+'</td><td>'+esc(s.license)+'</td></tr>').join("");
 }catch(e){$("sourceRows").innerHTML='<tr><td colspan="5">'+esc(e.message)+'</td></tr>'}
}
async function loadOperations(){
 try{
  const [overview,tasks,approvals,runs]=await Promise.all([api("/company/overview"),api("/tasks"),api("/approvals"),api("/agent-runs")]);
  $("taskCount").textContent=Object.values(overview.tasks).reduce((a,b)=>a+b,0);
  $("approvalCount").textContent=overview.approvals.pending||0;$("stageRuntime").textContent=overview.agent_worker_running?"Shared worker online":"Shared worker offline";
  $("stageRuntime").style.borderColor=overview.agent_worker_running?"rgba(103,243,192,.35)":"rgba(255,133,133,.35)";
  $("stageRuntime").style.color=overview.agent_worker_running?"#a6e9d4":"#ffaaaa";
  $("runtimeStatus").textContent=overview.agent_worker_running?"● Agent worker online · queue processor active · owner approval remains required":"● Agent worker offline · API is responding, but queued work will not execute until the worker is restored.";if(!overview.agent_worker_running)setApiHealth("API online · worker offline","degraded");else setApiHealth("API + worker online");
  const latest={};runs.forEach(r=>{if(!latest[r.task_id])latest[r.task_id]=r});
  $("taskApprovalPanel").innerHTML='<p><strong>Tasks</strong>: '+tasks.length+' · <strong>Approvals pending</strong>: '+(overview.approvals.pending||0)+' · <strong>Agent worker</strong>: '+esc(overview.execution_runtime)+'</p><div class="scroll"><table><thead><tr><th>Task</th><th>Department</th><th>Status</th><th>AI team</th></tr></thead><tbody>'+tasks.slice(0,30).map(t=>{const r=latest[t.id];return '<tr><td>'+esc(t.title)+'</td><td>'+esc(t.department)+'</td><td>'+esc(t.status)+'</td><td>'+(r?'<span class="pill">'+esc(r.status)+'</span> ':'')+(r&&["queued","running"].includes(r.status)?'<button class="secondary" disabled>Already running</button>':'<button class="secondary" data-id="'+esc(t.id)+'" onclick="runTask(this.dataset.id)">Run AI team</button>')+'</td></tr>'}).join("")+'</tbody></table></div><h3>Approval inbox</h3><div class="scroll"><table><thead><tr><th>Requested action</th><th>Details</th><th>Status</th><th>Owner decision</th></tr></thead><tbody>'+approvals.slice(0,20).map(a=>'<tr><td>'+esc(a.action)+'</td><td>'+esc(a.details)+'</td><td>'+esc(a.status)+'</td><td>'+(a.status==="pending"?'<button class="secondary" data-id="'+esc(a.id)+'" onclick="decideApproval(this.dataset.id,\'approved\')">Approve</button> <button class="secondary" data-id="'+esc(a.id)+'" onclick="decideApproval(this.dataset.id,\'rejected\')">Reject</button>':'—')+'</td></tr>').join("")+'</tbody></table></div>';
 }catch(e){$("taskApprovalPanel").textContent=e.message}
}
window.runTask=async(taskId)=>{try{$("agentRunOutput").textContent="Queuing specialist and CEO review…";const run=await api("/tasks/"+encodeURIComponent(taskId)+"/execute",{method:"POST"});$("agentRunOutput").textContent="AI team run "+run.id+" · "+run.status+". Waiting for specialist and CEO review…";await loadOperations();pollAgentRun(run.id)}catch(e){$("agentRunOutput").textContent=e.message}};
async function pollAgentRun(runId){try{const r=await api("/agent-runs/"+encodeURIComponent(runId));const events=await api("/agent-runs/"+encodeURIComponent(runId)+"/events");const steps=await api("/agent-runs/"+encodeURIComponent(runId)+"/steps");const timeline=events.map(x=>"• "+x.stage+": "+x.message).join("\n");const contributions=steps.map(s=>'<section class="card" style="margin:10px 0"><h4>'+esc(String(s.sequence_no)+". "+s.role+" · "+s.agent_name)+'</h4><p class="small">Status: '+esc(s.status)+' · '+esc(s.agent_id)+'</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(s.output||s.error||"Working…")+'</pre></section>').join("");if(r.status==="completed"){$("agentRunOutput").innerHTML='<h3>Collaborative run completed</h3><p class="small">Three live model calls · lead specialist + independent collaborator + CEO integration</p><h4>Execution timeline</h4><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(timeline)+'</pre><h4>Agent contributions</h4>'+contributions+'<h4>Final CEO-reviewed deliverable</h4><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(r.ceo_review)+'</pre><p class="small">Usage: '+esc(JSON.stringify(r.usage||{}))+'</p>';await loadOperations();return}if(r.status==="failed"){$("agentRunOutput").innerHTML='<h3 class="bad">Agent run failed safely</h3><p>'+esc(r.error||"Unknown error")+'</p><p class="small">'+esc(failureAdvice(r.error))+'</p><h4>Execution timeline</h4><pre style="white-space:pre-wrap">'+esc(timeline)+'</pre>'+contributions;await loadOperations();return}$("agentRunOutput").innerHTML='<h3>Collaborative team run '+esc(r.status)+'…</h3><p class="small">Lead specialist → independent collaborator → CEO integration</p><pre style="white-space:pre-wrap">'+esc(timeline)+'</pre>'+contributions;setTimeout(()=>pollAgentRun(runId),3000)}catch(e){$("agentRunOutput").textContent=e.message}}

window.decideApproval=async(id,decision)=>{if(!confirm("Confirm "+decision+" this requested action? The CEO/agent must still execute it through the approved runtime."))return;try{await api("/approvals/"+encodeURIComponent(id)+"/decision",{method:"POST",body:JSON.stringify({decision})});await loadOperations()}catch(e){say(e.message)}};
$("taskForm").addEventListener("submit",async e=>{e.preventDefault();const title=$("taskTitle").value.trim();if(!title)return;try{await api("/tasks",{method:"POST",body:JSON.stringify({title,department:$("taskDepartment").value})});$("taskTitle").value="";await loadOperations()}catch(e){say(e.message)}});
$("loadAgents").onclick=loadAgents;$("agentSearch").addEventListener("input",()=>{clearTimeout(window.agentSearchTimer);window.agentSearchTimer=setTimeout(loadAgents,250)});$("departmentFilter").onchange=loadAgents;$("loadOperations").onclick=loadOperations;
async function loadBrain(){
 try{
  const [status,proposed,approved]=await Promise.all([api("/brain/status"),api("/brain/memories?status=proposed"),api("/brain/memories?status=approved")]);
  $("brainExperiences").textContent=status.experiences;
  $("brainApproved").textContent=status.memories.approved;
  $("brainProposed").textContent=status.memories.proposed;
  $("brainRejected").textContent=status.memories.rejected;
  $("brainMode").textContent=status.learning_mode+" · local persistent storage";
  $("brainProposals").innerHTML=proposed.length?proposed.map(m=>'<article class="card" style="margin:10px 0"><h4>'+esc(m.title)+'</h4><p class="small">'+esc(m.department)+' · '+esc(m.category)+' · confidence '+esc(m.confidence)+'</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(m.content)+'</pre><button data-id="'+esc(m.id)+'" onclick="reviewBrainMemory(this.dataset.id,\'approved\')">Approve into brain</button> <button class="secondary" data-id="'+esc(m.id)+'" onclick="reviewBrainMemory(this.dataset.id,\'rejected\')">Reject</button></article>').join(""):'No proposed memories yet. Completed task outcomes will appear here.';
  $("brainApprovedList").innerHTML=approved.length?approved.slice(0,15).map(m=>'<article class="card" style="margin:8px 0"><strong>'+esc(m.title)+'</strong><p class="small">'+esc(m.department)+' · '+esc(m.created_at)+'</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(m.content.slice(0,1200))+'</pre></article>').join(""):'No approved memories yet. Approve a proposed lesson to make it available to future agents.';
 }catch(e){$("brainMode").textContent=e.message}
}
window.reviewBrainMemory=async(id,decision)=>{if(!confirm("Are you sure you want to "+decision+" this memory?"))return;try{await api("/brain/memories/"+encodeURIComponent(id)+"/review",{method:"POST",body:JSON.stringify({decision,note:"Owner reviewed in dashboard"})});await loadBrain()}catch(e){$("brainMode").textContent=e.message}};
$("refreshBrain").onclick=loadBrain;
async function loadProviders(){try{const providers=await api("/llm/providers");const select=$("providerSelect");const previous=select.value;select.innerHTML=providers.map(p=>'<option value="'+esc(p.id)+'">'+esc(p.name)+' · '+(p.eligible?'eligible':'blocked')+'</option>').join("");const preferred=providers.find(p=>p.eligible);select.value=providers.some(p=>p.id===previous&&p.eligible)?previous:(preferred?preferred.id:"");$("providerStatus").textContent=providers.map(p=>p.name+": "+(p.eligible?"eligible (free status owner-confirmed)":p.reason)).join("\n")+(preferred?"\nSelected automatically: "+preferred.name:"\nNo provider is eligible. Configure and confirm a free endpoint first.");}catch(e){$("providerStatus").textContent=e.message}}
async function runModel(test){const provider=$("providerSelect").value;if(!provider){$("modelOutput").textContent="No eligible free provider is selected. Check AI models and configure/confirm a free endpoint.";return}const prompt=test?"Reply with exactly: AIOS live connection successful":$("modelPrompt").value.trim();if(!prompt){$("modelOutput").textContent="Enter a prompt first.";return}const button=test?$("testProvider"):$("runModel");button.disabled=true;$("modelOutput").textContent="Sending live request…";try{const result=await api(test?"/llm/test":"/llm/run",{method:"POST",body:JSON.stringify({provider,prompt})});$("modelOutput").textContent=JSON.stringify(result,null,2)}catch(e){$("modelOutput").textContent="Live request failed: "+e.message}finally{button.disabled=false}}
$("loadProviders").onclick=loadProviders;$("testProvider").onclick=()=>runModel(true);$("runModel").onclick=()=>runModel(false);
async function saveProviderKey(){const api_key=$("providerApiKey").value.trim();if(!api_key){$("credentialStatus").textContent="Enter your OpenRouter key.";return}if(!$("confirmFreeOnly").checked){$("credentialStatus").textContent="Confirm free-only routing before saving.";return}const b=$("saveProviderKey");b.disabled=true;$("credentialStatus").textContent="Encrypting and saving on the server…";try{const result=await api("/llm/credentials/openrouter",{method:"POST",body:JSON.stringify({api_key,confirm_free_only:true})});$("providerApiKey").value="";$("credentialStatus").textContent="Saved securely in encrypted storage. Secret was not returned.";await loadProviders()}catch(e){$("credentialStatus").textContent=e.message}finally{b.disabled=false}}
$("saveProviderKey").onclick=saveProviderKey;

function showLogin(message=""){ $("loginPanel").style.display="flex"; $("loginStatus").textContent=message; $("loginKey").focus(); }
async function startDashboard(){authenticated=true;$("loginPanel").style.display="none";refresh();loadProviders();loadAgents();loadSources();loadOperations();loadBrain();api("/llm/credentials").then(x=>$("credentialStatus").textContent=x.openrouter.configured?"OpenRouter credential is saved (encrypted).":"No OpenRouter credential saved yet.").catch(e=>$("credentialStatus").textContent=e.message);if(!window.aiosRefreshTimer)window.aiosRefreshTimer=setInterval(refresh,10000)}
$("loginForm").addEventListener("submit",async e=>{e.preventDefault();const b=$("loginButton");b.disabled=true;$("loginStatus").textContent="Validating owner key…";try{const r=await fetch("/auth/session",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({api_key:$("loginKey").value})});if(!r.ok)throw Error("Owner key was rejected. Check the key in Railway Variables.");$("loginKey").value="";await startDashboard()}catch(err){$("loginStatus").textContent=err.message}finally{b.disabled=false}});
$("logoutButton").onclick=async()=>{try{await fetch("/auth/session",{method:"DELETE",credentials:"same-origin"});}finally{authenticated=false;showLogin("You have been signed out.")}};
fetch("/auth/session",{credentials:"same-origin"}).then(r=>r.json()).then(s=>{if(s.authenticated)startDashboard();else showLogin()}).catch(()=>showLogin("Sign in to continue."));
</script></body></html>
"""

def owner_dashboard() -> HTMLResponse:
    return HTMLResponse(OWNER_HTML)
