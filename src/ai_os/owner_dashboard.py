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

</style><style>
.office-toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:12px 0}
.office-viewport{height:480px;position:relative;overflow:hidden;border:1px solid rgba(108,233,255,.28);border-radius:16px;background:radial-gradient(ellipse at 50% 10%,#1b3154,#080e1b 70%);isolation:isolate}
#officeCanvas{display:block;width:100%;height:100%;touch-action:pan-y}
.office-hud{position:absolute;top:12px;left:14px;right:14px;display:flex;justify-content:space-between;pointer-events:none;color:#a9dfff;font-size:10px;letter-spacing:.16em;font-weight:800;text-shadow:0 0 12px #43cfff}
.office-fallback{position:absolute;inset:0;display:grid;place-items:center;color:#a9bbd9;font-size:13px;pointer-events:none}
.office-legend{display:flex;gap:18px;flex-wrap:wrap;margin:12px 0;color:var(--muted);font-size:12px}
.office-legend span{display:flex;align-items:center;gap:7px}.dot{width:8px;height:8px;border-radius:50%;display:inline-block}.dot.idle{background:#7896bc}.dot.working{background:#55e0ae;box-shadow:0 0 10px #55e0ae}.dot.review{background:#ffd27b}
.office-roster{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}
.office-employee{padding:11px;border:1px solid rgba(112,140,190,.2);border-radius:11px;background:rgba(8,15,28,.5);min-width:0}
.office-employee strong{display:block;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.office-employee span{display:block;color:var(--muted);font-size:11px;margin-top:3px}
@media(max-width:760px){.office-viewport{height:350px}.office-roster{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(prefers-reduced-motion:reduce){.office-viewport{scroll-behavior:auto}}
.office-viewport{height:540px;cursor:grab;touch-action:none;background:radial-gradient(ellipse at 50% 12%,#1b3658,#070d18 72%)}
.office-viewport:active{cursor:grabbing}
#officeCanvas{touch-action:none}
.office-selected{display:flex;flex-direction:column;gap:4px;margin:12px 0;padding:13px 15px;border:1px solid rgba(108,233,255,.2);border-radius:11px;background:rgba(8,22,38,.7)}
.office-selected strong{font-size:13px;color:#eaf7ff}.office-selected span{font-size:12px;color:var(--muted)}
#officeDepartmentGrid{grid-template-columns:repeat(4,minmax(0,1fr))}
.office-department{appearance:none;text-align:left;display:flex;flex-direction:column;gap:6px;min-width:0;padding:12px;border:1px solid rgba(108,157,197,.24);border-radius:11px;background:#0b1728;box-shadow:none;min-height:90px}
.office-department[aria-pressed="true"]{border-color:#6ce9ff;background:#10283b;box-shadow:0 0 0 1px rgba(108,233,255,.18)}
.office-department strong{font-size:12px;line-height:1.3}.office-department span{font-size:11px;color:#9aabc7;line-height:1.35}
.office-department .office-state{font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:#67f3c0}
@media(max-width:760px){.office-viewport{height:420px}.office-roster{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(prefers-reduced-motion:reduce){.office-department{transition:none}}


/* OWNER CONSOLE REFERENCE IMPLEMENTATION */
:root{--bg:#070c16;--panel:#0e1727;--line:#1d2b42;--muted:#91a2bd;--text:#edf3ff;--accent:#477de8;--green:#35d69a;--amber:#f2bd59}
html{scroll-behavior:smooth}
body{background:#070c16;background-image:radial-gradient(ellipse at 35% -18%,rgba(34,77,145,.22),transparent 54%);font-size:13px}
main{max-width:none;margin:0 0 0 226px;padding:22px 24px 48px}
nav.main-nav{position:fixed;z-index:30;left:0;top:0;bottom:0;width:210px;height:100vh;margin:0;padding:18px 12px 20px;display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;gap:5px;overflow-y:auto;overflow-x:hidden;border:0;border-right:1px solid #1b2940;border-radius:0;background:#080f1c;box-shadow:8px 0 30px rgba(0,0,0,.18)}
nav.main-nav:before{content:"AIOS  /  AI Operating System";display:block;padding:7px 9px 22px;margin-bottom:7px;border-bottom:1px solid #1a2940;color:#e7efff;font-weight:850;font-size:15px;letter-spacing:.02em}
nav.main-nav a{display:flex;align-items:center;min-height:37px;width:100%;padding:9px 10px;border:1px solid transparent;border-radius:8px;color:#a8b7d0;font-size:12px;font-weight:600;white-space:normal}
nav.main-nav a:before{content:"";width:6px;height:6px;margin-right:10px;border-radius:2px;background:#62748f;flex:0 0 auto}
nav.main-nav a.active{background:#18366c;border-color:#244b8c;color:#fff;box-shadow:none}
nav.main-nav a.active:before{background:#6ba0ff;box-shadow:0 0 9px #6ba0ff}
.top{padding:12px 16px 15px;border:0;border-bottom:1px solid #1b2940;border-radius:0;background:transparent;box-shadow:none;align-items:center}
.top:before,.top:after{display:none}
.top .muted{font-size:10px;letter-spacing:.14em;color:#7f96b8}
h1{font-size:25px;letter-spacing:-.035em;background:none;color:#f0f5ff;-webkit-text-fill-color:initial}
.top .hint{font-size:12px;color:#93a4bf}
.top .toolbar{gap:8px}
.tag{font-size:10px;padding:5px 9px;background:#0d1a2b}
.command-stage{display:none}
.panel{margin-top:14px;padding:17px;border:1px solid #1c2b43;border-radius:12px;background:#0d1625;box-shadow:none}
.panel:hover{border-color:#2a4164}
.panel>h2{font-size:15px;letter-spacing:0;margin-bottom:12px}
.grid{gap:10px;margin:12px 0}
.metric{padding:14px;border:1px solid #1d2d46;border-radius:10px;background:#101d30;box-shadow:none}
.metric:after{display:none}
.metric strong{font-size:25px;letter-spacing:-.03em}
.metric span{font-size:11px;color:#94a6c2}
button{min-height:36px;padding:8px 11px;border-radius:8px;box-shadow:none}
button.secondary{background:#14233a}
input,select,textarea{min-height:36px;border-radius:8px}
.scroll{border-radius:9px}
th{background:#101b2c}
#overview .grid{grid-template-columns:repeat(4,minmax(0,1fr))}
#workforce .grid{grid-template-columns:repeat(3,minmax(0,1fr))}
#companyDepartmentCards{grid-template-columns:repeat(4,minmax(0,1fr))}
#runtimeStatus{background:#0d2828;border-color:#1a4b45}
#loginPanel form{max-width:390px}
@media(min-width:1200px){main{padding-left:28px;padding-right:28px}#overview .grid{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:900px){main{margin-left:200px;padding:16px 14px 40px}nav.main-nav{width:184px}#companyDepartmentCards{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:680px){
 main{margin:0;padding:12px 11px 38px}
 nav.main-nav{position:sticky;top:0;left:auto;bottom:auto;width:auto;height:auto;flex-direction:row;flex-wrap:nowrap;align-items:center;gap:5px;margin:0 -11px 10px;padding:8px 10px;border:0;border-bottom:1px solid #1b2940;border-radius:0;background:rgba(7,12,22,.96);backdrop-filter:blur(12px);overflow-x:auto;overflow-y:hidden;overscroll-behavior-x:contain;-webkit-overflow-scrolling:touch;scrollbar-width:thin}
 nav.main-nav:before{display:none}
 nav.main-nav a{width:auto;min-height:34px;flex:0 0 auto;padding:8px 10px;font-size:11px}
 nav.main-nav a:before{display:none}
 .top{padding:8px 2px 13px}
 .top .toolbar{width:100%;justify-content:flex-start}
 h1{font-size:22px}
 #overview .grid{grid-template-columns:repeat(2,minmax(0,1fr))}
 #companyDepartmentCards{grid-template-columns:repeat(2,minmax(0,1fr))}
 .panel{padding:13px}
}


/* Executive overview: compact, actionable command centre */
.overview-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;margin-bottom:12px}
.overview-head h2{margin:4px 0 3px;font-size:23px}.overview-head p{margin:0}
.overview-kpis{grid-template-columns:repeat(6,minmax(0,1fr))}
.overview-layout{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px;margin-top:15px}
.overview-card{min-width:0;padding:17px;border:1px solid rgba(108,233,255,.17);border-radius:15px;background:linear-gradient(145deg,rgba(15,33,54,.92),rgba(8,17,32,.96))}
.overview-card h3{margin:0;font-size:15px;letter-spacing:-.015em}.overview-card-head{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.overview-stat-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0}
.overview-stat-grid>div{padding:12px;border:1px solid rgba(108,157,197,.18);border-radius:11px;background:rgba(5,14,29,.48)}
.overview-stat-grid strong{display:block;font-size:25px;font-variant-numeric:tabular-nums}.overview-stat-grid span{font-size:11px;color:var(--muted)}
.overview-list{display:grid;gap:8px;min-height:54px;margin:8px 0 13px}
.overview-item{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;padding:9px 10px;border:1px solid rgba(108,157,197,.14);border-radius:10px;background:rgba(5,14,29,.42)}
.overview-item strong{display:block;font-size:12px;overflow-wrap:anywhere}.overview-item .small{margin-top:3px;font-size:11px}
.overview-quick-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px}.overview-quick-actions button{min-width:0;white-space:normal}
@media(max-width:1050px){.overview-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:680px){.overview-head .toolbar{width:100%}.overview-head .toolbar button{flex:1}.overview-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.overview-layout{grid-template-columns:1fr}.overview-quick-actions{grid-template-columns:1fr 1fr}}
</style>
</head>
<body><div id="loginPanel" style="position:fixed;inset:0;z-index:20;background:#080d19ee;display:flex;align-items:center;justify-content:center;padding:20px"><form id="loginForm" class="panel" style="width:min(420px,100%)"><h2>Owner sign in</h2><p class="small">Enter your Owner API Key once. AIOS will create a secure 14-day browser session. The key is not saved in browser storage.</p><input id="loginKey" type="password" autocomplete="current-password" placeholder="AIOS Owner API Key" required style="width:100%;margin:8px 0"><button id="loginButton" type="submit" style="width:100%">Sign in securely</button><div id="loginStatus" class="status" role="status"></div></form></div><main>
<div class="top"><div><div class="muted">AI OPERATING SYSTEM / OWNER CONSOLE</div><h1>AI Company Control Center</h1><div class="hint">Your AI company, workforce, research pipeline and approvals — in one supervised workspace.</div></div><div class="toolbar"><span class="tag">Owner-supervised · bounded AI execution</span><span id="apiHealth" class="tag">Checking API…</span><button id="logoutButton" class="secondary">Log out</button></div></div>
<nav class="toolbar main-nav" aria-label="Main sections"><a href="#overview" data-view="overview">Company</a><a href="#workforce" data-view="workforce">Workforce</a><a href="#sources" data-view="sources">Repositories</a><a href="#tasks" data-view="tasks">Tasks & approvals</a><a href="#workflows" data-view="workflows">Department workflows</a><a href="#discovery" data-view="discovery">Technology</a><a href="#models" data-view="models">AI models</a><a href="#research" data-view="research">Research Evidence</a><a href="#brain" data-view="brain">AI Brain</a><a href="#virtual-office" data-view="virtual-office">3D Office</a><a href="#business" data-view="business">Business</a><a href="#ventures" data-view="ventures">Venture Discovery</a><a href="#code-assets" data-view="code-assets">Code Assets</a></nav>
<section class="command-stage" aria-label="AI employee command stage">
 <div class="stage-head"><div><div class="eyebrow">Neural command deck / workforce visualization</div><div class="stage-title">Meet the AI workforce</div><div class="stage-note">Stylized role representations generated from the live workforce catalogue — not fabricated active-worker status.</div></div><span id="stageRuntime" class="stage-indicator">Runtime status loading</span></div>
 <div id="employeeStage" class="employee-stage"><div class="stage-empty">Loading real specialist roles from the AIOS workforce catalogue…</div></div>
 <div class="stage-footer"><span>ROLE STATUS · ON-DEMAND INVOCATION</span><span>Owner-supervised execution · no external actions without approval</span></div>
</section>
<section id="virtual-office" class="panel section" data-view-panel="virtual-office">
<h2>OpenCompany HQ · interactive 3D headquarters</h2>
<p class="small">Twelve department workspaces mapped to the live AIOS department registry. Activity indicators come from saved tasks and agent runs; catalogued roles are on-demand, not 12 always-on processes.</p>
<div class="office-toolbar"><span id="officeConnection" class="pill warn">Connecting to AIOS…</span><span id="officeActivity" class="small">Loading live company operations</span><button id="officeRefresh" class="secondary" type="button">Refresh data</button><button id="officeReset" class="secondary" type="button">Reset camera</button></div>
<div id="officeViewport" class="office-viewport"><canvas id="officeCanvas" aria-label="Interactive 3D OpenCompany headquarters with twelve department workspaces. Drag to rotate, scroll or pinch to zoom, tap a workspace for details."></canvas><div class="office-hud"><span>OPENCOMPANY / HQ-01</span><span id="officeClock">INITIALISING</span></div><div id="officeFallback" class="office-fallback">Building the 3D headquarters…</div></div>
<div class="office-legend"><span><i class="dot idle"></i> Available / no active task</span><span><i class="dot working"></i> Active task or run</span><span><i class="dot review"></i> Queued / awaiting next step</span></div>
<div id="officeSelected" class="office-selected" aria-live="polite"><strong>Company overview</strong><span>Select any department workspace to inspect its current task counts and role availability.</span></div>
<div id="officeDepartmentGrid" class="office-roster" aria-live="polite"><div class="small">Loading 12 department workspaces…</div></div>
<p class="small">Owner approvals, spending, publishing and customer commitments remain controlled by the existing AIOS workflows. The 3D scene is a visualization layer and does not create or imply additional running agents.</p>
</section>
<section id="overview" class="panel section" data-view-panel="overview">
<div class="overview-head"><div><div class="eyebrow">Live company status</div><h2>Executive overview</h2><p class="small">A real-time snapshot of workload, AI execution and decisions waiting for you.</p></div><div class="toolbar"><span id="overviewLastUpdated" class="pill">Waiting for live data</span><button id="overviewRefresh" class="secondary" type="button">Refresh overview</button></div></div>
<div class="grid overview-kpis"><div class="metric"><strong id="workforceCount">283</strong><span>Catalogued specialists</span></div><div class="metric"><strong id="departmentCount">18</strong><span>Source categories</span></div><div class="metric"><strong id="taskCount">—</strong><span>Saved company tasks</span></div><div class="metric"><strong id="approvalCount">—</strong><span>Pending owner approvals</span></div><div class="metric"><strong id="overviewActiveRuns">—</strong><span>Active / queued AI runs</span></div><div class="metric"><strong id="overviewCompletedRuns">—</strong><span>Completed AI runs</span></div></div>
<div id="companyStatus" class="small">Loading company registry and operating status…</div><div id="runtimeStatus" class="small" role="status">Checking agent worker health…</div>
<div class="overview-layout">
<section class="overview-card"><div class="overview-card-head"><h3>Execution snapshot</h3><span id="overviewWorkerState" class="pill warn">Checking worker</span></div><div class="overview-stat-grid"><div><strong id="overviewQueuedTasks">—</strong><span>Queued tasks</span></div><div><strong id="overviewFailedRuns">—</strong><span>Failed / partial runs</span></div></div><p class="small">Specialist roles are invoked on demand through the shared worker. A catalogue entry does not mean an agent is running.</p><button class="secondary" type="button" data-overview-view="workforce">View AI workforce</button></section>
<section class="overview-card"><div class="overview-card-head"><h3>Owner approval inbox</h3><span class="pill warn">Your decision required</span></div><div id="overviewApprovalPreview" class="overview-list" aria-live="polite">Loading pending approvals…</div><button class="secondary" type="button" data-overview-view="tasks">Open tasks & approvals</button></section>
<section class="overview-card"><div class="overview-card-head"><h3>Recent AI activity</h3><span class="pill">Execution history</span></div><div id="overviewActivity" class="overview-list" aria-live="polite">Loading recent runs…</div><button class="secondary" type="button" data-overview-view="tasks">Inspect execution details</button></section>
<section class="overview-card"><div class="overview-card-head"><h3>Quick launch</h3><span class="pill good">Owner-controlled</span></div><p class="small">Jump directly to the workspace you need. Creating tasks and starting workflows remains an explicit action.</p><div class="overview-quick-actions"><button type="button" data-overview-view="tasks">＋ New task / approvals</button><button class="secondary" type="button" data-overview-view="workflows">Department workflows</button><button class="secondary" type="button" data-overview-view="models">AI models & providers</button><button class="secondary" type="button" data-overview-view="business">Business operations</button></div></section>
</div></section>
<section id="workforce" class="panel section" data-view-panel="workforce"><h2>Company departments & AI workforce</h2><p class="small">12 company departments mapped to 18 source-catalogue categories and 283 specialist definitions. Specialist roles are available on demand through one shared worker; department cards do not imply independent always-on teams or completed business workflows.</p><div id="companyDepartmentCards" class="grid" aria-live="polite"><div class="metric">Loading department registry…</div></div><h3>Source specialist catalogue</h3><div class="toolbar"><input id="agentSearch" placeholder="Search 283 specialists…" style="flex:1;min-width:180px"><select id="departmentFilter"><option value="">All source categories</option></select><button id="loadAgents" class="secondary">Refresh roster</button></div><div id="departmentChips" class="toolbar section"></div><div class="scroll section"><table><thead><tr><th>Specialist</th><th>Source category</th><th>Runtime state</th><th>Source</th></tr></thead><tbody id="agentRows"><tr><td colspan="4">Loading workforce catalog…</td></tr></tbody></table></div></section>
<section id="sources" class="panel section" data-view-panel="sources"><h2>Repository intelligence · 12 sources</h2><p class="small">The Agency Agents workforce and Automaton runtime reference are separated from the ten company/platform comparison repositories. Reference status does not mean code is installed or trusted.</p><div class="scroll"><table><thead><tr><th>Repository</th><th>Role</th><th>Current state</th><th>Purpose</th><th>License</th></tr></thead><tbody id="sourceRows"><tr><td colspan="5">Loading repository inventory…</td></tr></tbody></table></div></section>
<section id="workflows" class="panel section" data-view-panel="workflows">
<h2>Department workflow orchestration</h2>
<p class="small">Create a multi-department workflow. Starting a workflow authorizes its first internal task. Each next department is queued automatically after successful handoff. The bounded worker uses the existing free-only model policy; external actions remain approval-gated.</p>
<div class="toolbar"><button id="refreshWorkflows" class="secondary" type="button">Refresh workflows</button><span id="workflowStatus" class="status">Loading workflow templates…</span></div>
<div id="workflowTemplates" class="grid"></div>
<div id="workflowInstances" class="section"></div>
<h3>Interdepartmental inbox & delegation</h3>
<p class="small">Internal messages remain inside the selected business. Workflow handoffs arrive automatically. Owner-created delegated tasks stay queued until explicitly run.</p>
<div class="toolbar"><label>Inbox department <select id="collaborationDepartment"><option value="executive">Executive</option><option value="research">Research</option><option value="product">Product</option><option value="design">Design</option><option value="engineering">Engineering</option><option value="legal-compliance">Legal & Compliance</option><option value="quality-assurance">Quality Assurance</option><option value="marketing">Marketing</option><option value="sales-marketplace">Sales & Marketplace</option><option value="customer-support">Customer Support</option><option value="finance">Finance</option><option value="people-workforce">People & Workforce</option></select></label><button id="refreshCollaboration" class="secondary" type="button">Refresh inbox</button></div>
<div id="collaborationInbox" class="section small">Loading department inbox…</div>
<div class="grid section">
<form id="departmentMessageForm" class="metric"><strong>Send internal message</strong>
<select name="sender_department" required><option value="executive">From: Executive</option><option value="research">From: Research</option><option value="product">From: Product</option><option value="design">From: Design</option><option value="engineering">From: Engineering</option><option value="legal-compliance">From: Legal & Compliance</option><option value="quality-assurance">From: Quality Assurance</option><option value="marketing">From: Marketing</option><option value="sales-marketplace">From: Sales & Marketplace</option><option value="customer-support">From: Customer Support</option><option value="finance">From: Finance</option><option value="people-workforce">From: People & Workforce</option></select>
<select name="recipient_department" required><option value="research">To: Research</option><option value="executive">To: Executive</option><option value="product">To: Product</option><option value="design">To: Design</option><option value="engineering">To: Engineering</option><option value="legal-compliance">To: Legal & Compliance</option><option value="quality-assurance">To: Quality Assurance</option><option value="marketing">To: Marketing</option><option value="sales-marketplace">To: Sales & Marketplace</option><option value="customer-support">To: Customer Support</option><option value="finance">To: Finance</option><option value="people-workforce">To: People & Workforce</option></select>
<input name="subject" required maxlength="200" placeholder="Message subject"><textarea name="body" required maxlength="12000" placeholder="Internal handoff, request or findings"></textarea><button type="submit">Send internal message</button><span id="messageFormStatus" class="small"></span></form>
<form id="departmentDelegationForm" class="metric"><strong>Delegate department task</strong>
<select name="from_department" required><option value="executive">From: Executive</option><option value="research">From: Research</option><option value="product">From: Product</option><option value="design">From: Design</option><option value="engineering">From: Engineering</option><option value="legal-compliance">From: Legal & Compliance</option><option value="quality-assurance">From: Quality Assurance</option><option value="marketing">From: Marketing</option><option value="sales-marketplace">From: Sales & Marketplace</option><option value="customer-support">From: Customer Support</option><option value="finance">From: Finance</option><option value="people-workforce">From: People & Workforce</option></select>
<select name="to_department" required><option value="research">To: Research</option><option value="executive">To: Executive</option><option value="product">To: Product</option><option value="design">To: Design</option><option value="engineering">To: Engineering</option><option value="legal-compliance">To: Legal & Compliance</option><option value="quality-assurance">To: Quality Assurance</option><option value="marketing">To: Marketing</option><option value="sales-marketplace">To: Sales & Marketplace</option><option value="customer-support">To: Customer Support</option><option value="finance">To: Finance</option><option value="people-workforce">To: People & Workforce</option></select>
<input name="title" required maxlength="200" placeholder="Delegated task title"><textarea name="description" maxlength="12000" placeholder="Task instructions and expected result"></textarea><button type="submit">Create queued task</button><span id="delegationFormStatus" class="small"></span></form></div>
<div id="collaborationDelegations" class="section small">Loading task delegations…</div>
</section>
<section id="tasks" class="panel section" data-view-panel="tasks"><h2>Tasks & owner approvals</h2><form id="taskForm" class="toolbar"><input id="taskTitle" required maxlength="200" placeholder="New company task" style="flex:1;min-width:180px"><select id="taskBusiness"><option value="core">AIOS Core / internal</option><option value="physical-agency">Physical Products Agency</option><option value="physical-brand">Own Physical Products Brand</option><option value="digital-products">Digital Products</option></select><select id="taskDepartment"><option value="general">General / unassigned</option><option value="executive">Executive & Strategy</option><option value="research">Research & Intelligence</option><option value="product">Product & R&amp;D</option><option value="design">Design & 3D Production</option><option value="engineering">Engineering & Technology</option><option value="marketing">Marketing & Growth</option><option value="sales-marketplace">Sales & Marketplace Operations</option><option value="customer-support">Customer Support</option><option value="finance">Finance & Accounting</option><option value="legal-compliance">Legal & Compliance</option><option value="quality-assurance">Quality Assurance</option><option value="people-workforce">People & AI Workforce</option></select><button type="submit">Create task</button></form><div class="toolbar section"><button id="loadOperations" class="secondary">Refresh operations</button><span class="small">Owner approval remains mandatory for consequential actions.</span></div><div id="taskApprovalPanel" class="small">No operational data loaded.</div><div id="agentRunOutput" class="section" aria-live="polite"></div></section>
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
<div class="toolbar"><span id="githubStatus" class="status" role="status">GitHub API connection has not been checked.</span><button id="githubCheck" class="secondary" type="button">Test GitHub API</button></div>
<div class="small">Scans read public GitHub repository metadata only. They do not install software, connect accounts, or change production.</div>
<div id="message" class="status" role="status">Connect with your owner API key to load live data.</div>
</section>
<section id="scanHistory" class="panel section" data-view-panel="discovery"><h2>Recent scans</h2><div class="scroll"><table><thead><tr><th>Created</th><th>Categories</th><th>Status</th><th>Results</th><th>Error</th></tr></thead><tbody id="scanRows"><tr><td colspan="5" class="muted">No data loaded</td></tr></tbody></table></div></section>
<section id="discoveredProjects" class="panel section" data-view-panel="discovery"><h2>Discovered projects</h2><div class="scroll"><table><thead><tr><th>Project</th><th>Category</th><th>License</th><th>Maintenance</th><th>Stars</th><th>Review state</th><th>Evidence</th></tr></thead><tbody id="candidateRows"><tr><td colspan="7" class="muted">No data loaded</td></tr></tbody></table></div></section>
<p class="small section" data-view-panel="discovery">Cost, security, commercial-use rights, and provider terms remain unverified unless the evidence record explicitly says otherwise. A discovered project is not an approved integration.</p>
<section id="freeApiCatalog" class="panel section" data-view-panel="discovery">
<h2>Free API research catalog</h2>
<p class="small">Read-only import of public provider research. AIOS records free-tier claims, primary-source links, privacy/training policy, commercial-use notes, verification dates, and upstream probe status. It does not connect, enable, or call these providers.</p>
<div class="toolbar"><button id="syncFreeApiCatalog" type="button">Sync public API catalogs</button><button id="refreshFreeApiCatalog" class="secondary" type="button">Refresh catalog</button><span id="freeApiCatalogStatus" class="status">Catalog not synced yet.</span></div>
<div class="grid"><div class="metric"><strong id="freeApiCount">—</strong><span>Provider records</span></div><div class="metric"><strong id="freeApiLive">—</strong><span>Upstream live probes</span></div><div class="metric"><strong id="freeApiReview">—</strong><span>Policy review needed</span></div><div class="metric"><strong id="freeApiFresh">—</strong><span>Last upstream status check</span></div></div>
<div class="scroll"><table><thead><tr><th>Provider</th><th>Category</th><th>Free-tier evidence</th><th>Data policy</th><th>Commercial use</th><th>Upstream check</th><th>Sources</th></tr></thead><tbody id="freeApiRows"><tr><td colspan="7">Sync catalog to load provider records.</td></tr></tbody></table></div>
<h3>Source quality decisions</h3><div id="freeApiSourceNotes" class="small">Source assessments load after sync.</div>
</section>


<section id="research" class="panel section" data-view-panel="research">
<h2>Research evidence library · owner-triggered capture</h2>
<p class="small">Capture public HTTPS pages for research tasks. AIOS stores the URL, capture time and readable page text, then supplies relevant excerpts to the lead specialist. Pages are reference material, not automatically verified truth. HTTPS only; redirects, private-network targets, non-text files and pages over 1 MB are blocked.</p>
<div class="toolbar"><select id="researchBusiness" aria-label="Research business scope"><option value="core">AIOS Core / internal</option><option value="physical-agency">Physical Products Agency</option><option value="physical-brand">Own Physical Products Brand</option><option value="digital-products">Digital Products</option></select><input id="researchSourceUrl" type="url" placeholder="https://example.com/research-report" style="flex:1;min-width:220px"><button id="captureResearchSource">Capture source</button><button id="refreshResearchSources" class="secondary">Refresh library</button></div>
<div id="researchSourceStatus" class="status" role="status">No source capture requested.</div>
<div id="researchSources" class="small">Loading captured sources…</div>
</section>

<section id="brain" class="panel section" data-view-panel="brain">
<h2>Company AI Brain · persistent learning</h2>
<p class="small">Provider-independent memory stored in our own SQLite database. Completed runs become experiences automatically. Reusable lessons remain proposed until you approve them; only approved memories are supplied to future agents.</p>
<div class="grid"><div class="metric"><strong id="brainExperiences">—</strong><span>Stored experiences</span></div><div class="metric"><strong id="brainApproved">—</strong><span>Approved memories</span></div><div class="metric"><strong id="brainProposed">—</strong><span>Awaiting owner review</span></div><div class="metric"><strong id="brainRejected">—</strong><span>Rejected memories</span></div></div>
<div class="toolbar section"><select id="brainBusiness"><option value="core">AIOS Core / internal</option><option value="physical-agency">Physical Products Agency</option><option value="physical-brand">Own Physical Products Brand</option><option value="digital-products">Digital Products</option></select><button class="secondary" id="refreshBrain">Refresh selected brain</button><span id="brainMode" class="small">Loading brain status…</span></div>
<h3>Proposed lessons · owner review required</h3><div id="brainProposals" class="small">Loading proposed memories…</div>
<h3>Approved knowledge used by agents</h3><div id="brainApprovedList" class="small">Loading approved memories…</div>
<p class="small">Current learning is persistent experience capture plus approved-memory retrieval, not neural-network training. Local lexical retrieval needs no embeddings or additional model calls. The model gateway is still required for advanced reasoning.</p>
</section>
<section id="apiAnything" class="panel section" data-view-panel="discovery">
<h2>API Anything · website-to-API bridge</h2>
<p class="small">Discover and run installed API Anything reads through the private Railway service. Calls require your owner session and are restricted to plain HTTP tier 1. API Anything login imports a browser session on the runtime host; it is not a hosted dashboard OAuth flow. Use the Business section for supported WordPress/WooCommerce account connections.</p>
<div class="toolbar"><span id="apiAnythingStatus" class="status">Checking API Anything configuration…</span><button id="apiAnythingRefresh" class="secondary" type="button">Refresh connection</button><button id="apiAnythingSites" class="secondary" type="button">List installed sites</button></div>
<div class="toolbar section"><input id="apiAnythingQuery" placeholder="Find a site or operation" style="flex:1;min-width:180px"><button id="apiAnythingFind" type="button">Find</button></div>
<pre id="apiAnythingResults" style="max-height:260px;overflow:auto;white-space:pre-wrap;background:#091323;padding:12px;border-radius:10px">No results loaded.</pre>
<h3>Owner-triggered read operation</h3>
<div class="toolbar"><input id="apiAnythingSite" placeholder="site e.g. hacker-news"><button class="secondary" id="apiAnythingOperations" type="button">Show site operations</button><input id="apiAnythingOperation" placeholder="operation e.g. search"></div>
<textarea id="apiAnythingArgs" rows="3" style="width:100%;margin-top:8px" placeholder='{"query":"sqlite"}'></textarea>
<div class="toolbar section"><button id="apiAnythingCall" type="button">Run read-only operation</button><span class="small">Never use this for purchases, publishing, messages, account changes or other writes.</span></div>
<pre id="apiAnythingOutput" style="max-height:320px;overflow:auto;white-space:pre-wrap;background:#091323;padding:12px;border-radius:10px">No operation executed.</pre>
</section>
<section id="supabaseIntegration" class="panel section" data-view-panel="discovery">
<h2>Supabase · database connection</h2>
<p class="small">The Supabase ↔ GitHub repository link manages source/migration versioning; Railway must separately connect to the live Supabase PostgreSQL database. This panel only checks configuration and runs a read-only SELECT 1 probe. It never applies migrations or changes data.</p>
<div class="toolbar"><span id="supabaseStatus" class="status">Checking Supabase configuration…</span><button class="secondary" id="supabaseRefresh" type="button">Refresh status</button><button id="supabaseTest" type="button">Test database connection</button></div>
<pre id="supabaseOutput" style="max-height:220px;overflow:auto;white-space:pre-wrap;background:#091323;padding:12px;border-radius:10px">No connection test run.</pre>
<p class="small">Required Railway variable: AI_OS_DATABASE_URL (Supabase PostgreSQL Session Pooler URL, SSL enabled). Never paste the URL or password into this dashboard/chat. Production migrations remain blocked pending a reviewed baseline, backup and separate owner approval.</p>
</section>
<section id="models" class="panel section" data-view-panel="models"><h2>Live AI model gateway</h2>
<div class="small">OpenRouter keys are encrypted on the server before storage. The first connection uses only the free-model router and has no paid fallback. Use HTTPS.</div>
<div class="section" style="border:1px solid var(--line);border-radius:10px;padding:12px"><strong>Provider credentials · OpenRouter</strong><div class="small">Enter your OpenRouter key here. It is sent only to the authenticated server, encrypted at rest, and never returned to this page. Do not paste it into chat or GitHub.</div><div class="toolbar" style="margin-top:10px"><input id="providerApiKey" type="password" autocomplete="off" placeholder="OpenRouter API key" style="flex:1;min-width:220px"><button id="saveProviderKey">Save encrypted key</button></div><label style="margin-top:10px"><input id="confirmFreeOnly" type="checkbox"> I confirm this connection must use the free-only router, with no paid model or paid fallback.</label><div id="credentialStatus" class="status">Credential status not loaded.</div></div>
<div class="section" style="border:1px solid var(--line);border-radius:10px;padding:12px;margin-top:10px"><strong>Additional free-provider connections</strong><p class="small">UnoRouter is the default provider for pre-launch AIOS development and internal testing. Save one API key and confirm one currently free :free model; AIOS then automatically selects among all account-accessible free chat models for each task. You do not need to save models one by one. Gemini, Groq, and Mistral can be free-confirmed backups. Use synthetic, non-sensitive test prompts and review each model provider's data terms.</p><div class="toolbar"><select id="vaultProvider"><option value="gemini">Google Gemini</option><option value="groq">Groq</option><option value="mistral">Mistral</option><option value="unorouter">UnoRouter · primary</option></select><input id="vaultModel" placeholder="Provider model ID" style="flex:1;min-width:180px"><input id="vaultApiKey" type="password" autocomplete="off" placeholder="Provider API key" style="flex:1;min-width:180px"></div><div class="toolbar" style="margin-top:8px"><button class="secondary" id="loadUnoRouterModels" type="button">Load full UnoRouter catalogue</button><select id="unorouterModelSelect" aria-label="UnoRouter available models" style="flex:1;min-width:220px"><option value="">Load catalogue to see models</option></select></div><div id="unorouterCatalogStatus" class="small">Read-only lookup: shows free and paid entries. Exact selectable IDs are loaded from the saved API key. No prompts are sent.</div><label style="margin-top:10px"><input id="vaultFreeOnly" type="checkbox"> Confirm this selected model is :free to enable free-only automatic routing. The task router independently chooses a suitable account-accessible free chat model; paid and non-chat models are excluded.</label><button id="saveVaultProvider" style="margin-top:10px">Save encrypted provider</button><div id="vaultProviderStatus" class="status">No additional provider selected.</div></div><div class="section" style="border:1px solid var(--line);border-radius:10px;padding:12px;margin-top:10px"><strong>UnoRouter · owner-approved test bench</strong><p class="small">A request is sent only when you press the test button. Free models may be tested directly. Paid models require the separate approval checkbox below for that individual request. Agent routing remains free-only and never uses paid models.</p><textarea id="unorouterPersonalPrompt" rows="2" style="width:100%;margin:8px 0" placeholder="Example: Explain the difference between JSON and YAML."></textarea><label style="margin:8px 0"><input id="approveUnoRouterPaid" type="checkbox"> I explicitly approve sending this specific prompt to the selected paid model and accept any resulting charge.</label><button class="secondary" id="testUnoRouterPersonal" type="button">Send approved test request</button><pre id="unorouterPersonalOutput" style="white-space:pre-wrap;overflow-wrap:anywhere;background:#0c1425;border:1px solid var(--line);border-radius:9px;padding:12px;min-height:48px">No personal test run yet.</pre></div></div>
<div class="toolbar" style="margin-top:12px"><select id="providerSelect"><option value="">Loading providers…</option></select><button class="secondary" id="loadProviders">Refresh providers</button><button id="testProvider">Test live connection</button></div>
<div id="providerStatus" class="status">Provider status not loaded.</div>
<textarea id="modelPrompt" rows="3" style="width:100%;margin:8px 0" placeholder="Enter a small test prompt. This sends a real request to the selected provider."></textarea>
<button id="runModel">Run real model request</button>
<pre id="modelOutput" style="white-space:pre-wrap;overflow-wrap:anywhere;background:#0c1425;border:1px solid var(--line);border-radius:9px;padding:12px;min-height:60px">No live inference run yet.</pre>
</section>

<section id="ventures" class="panel section" data-view-panel="ventures">
<h2>Venture Discovery & Growth</h2>
<p class="small">Company-wide opportunity pipeline for any legitimate revenue model. Research customer demand, competition, costs, margins, distribution and risks before deciding what deserves investment. Research does not spend money or contact customers.</p>
<div class="grid discovery-metrics"><div class="metric"><strong id="ventureTotal">—</strong><span>Opportunities</span></div><div class="metric"><strong id="ventureResearch">—</strong><span>Research queued</span></div><div class="metric"><strong id="ventureShortlist">—</strong><span>Shortlisted</span></div><div class="metric"><strong id="ventureLaunched">—</strong><span>Separate ventures</span></div></div>
<div class="panel section"><h3>Add opportunity hypothesis</h3><form id="ventureForm">
<input name="title" required minlength="3" maxlength="160" placeholder="Opportunity name" style="width:100%;margin:6px 0">
<textarea name="thesis" required minlength="20" maxlength="6000" placeholder="What is the opportunity and why might customers pay?" style="width:100%;min-height:90px;margin:6px 0"></textarea>
<div class="toolbar"><input name="customer_segment" maxlength="500" placeholder="Target customer" style="flex:1;min-width:180px"><input name="problem" maxlength="1000" placeholder="Customer problem" style="flex:1;min-width:180px"><input name="revenue_model" maxlength="100" placeholder="Revenue model" value="unknown" style="flex:1;min-width:150px"><input name="market_scope" maxlength="120" placeholder="Market / geography" value="global" style="flex:1;min-width:150px"><button type="submit">Add opportunity</button></div>
</form><div id="ventureMessage" class="status" aria-live="polite">No opportunity created yet.</div></div>
<h3>Opportunity portfolio</h3><div class="scroll"><table><thead><tr><th>Opportunity</th><th>Customer / model</th><th>Status</th><th>Provisional score</th><th>Evidence</th><th>Actions</th></tr></thead><tbody id="ventureRows"><tr><td colspan="6">Loading…</td></tr></tbody></table></div>
<div class="panel section"><h3>Record research assessment</h3><p class="small">Rate each dimension from 0–5 only after reviewing evidence. Launch approval requires all six ratings and at least three HTTPS sources.</p>
<form id="ventureAssessmentForm"><select id="assessmentOpportunity" name="opportunity_id" required style="width:100%;margin:6px 0"><option value="">Select opportunity</option></select>
<div class="grid" style="grid-template-columns:repeat(2,minmax(0,1fr))"><label class="small">Demand (0–5)<input name="demand" type="number" min="0" max="5" required style="width:100%"></label><label class="small">Competition (0–5)<input name="competition" type="number" min="0" max="5" required style="width:100%"></label><label class="small">Economics (0–5)<input name="economics" type="number" min="0" max="5" required style="width:100%"></label><label class="small">Distribution (0–5)<input name="distribution" type="number" min="0" max="5" required style="width:100%"></label><label class="small">Execution (0–5)<input name="execution" type="number" min="0" max="5" required style="width:100%"></label><label class="small">Risk (0–5)<input name="risk" type="number" min="0" max="5" required style="width:100%"></label></div>
<textarea name="summary" maxlength="4000" placeholder="Findings, pricing, startup costs, unit economics, break-even assumptions, risks and recommended low-cost validation" style="width:100%;min-height:100px;margin:8px 0"></textarea><textarea name="sources" placeholder="HTTPS source URLs, one per line" style="width:100%;min-height:80px;margin:8px 0"></textarea><button type="submit">Save assessment</button></form></div>
</section>
<section id="business" class="panel section" data-view-panel="business">
<h2>Business operations · financial ledger & customers</h2>
<p class="small">Select one independent business environment before viewing or recording customers, revenue and expenses. Only owner-confirmed payments count as revenue; no payment is initiated here.</p><div class="toolbar section"><label for="businessScope">Business records scope</label><select id="businessScope"><option value="core">AIOS Core / internal</option><option value="physical-agency">Physical Products Agency</option><option value="physical-brand">Own Physical Products Brand</option><option value="digital-products">Digital Products</option></select><span class="small">Records and reports below are isolated to this selection.</span></div><div class="panel section"><h3>Expand OpenCompany - register a new venture</h3><p class="small">Add a business unit for any legitimate revenue model. Customers, finances, credentials, research and memory are scoped separately. Registration does not spend money or publish anything.</p><form id="businessUnitForm" class="toolbar"><input name="name" required minlength="2" maxlength="120" placeholder="Business / venture name"><input name="business_type" required minlength="2" maxlength="64" placeholder="Type slug (e.g. services, saas, content)" value="general"><input name="description" maxlength="3000" placeholder="What it sells and how it operates" style="flex:1;min-width:220px"><button type="submit">Register business unit</button></form><div id="businessUnitMessage" class="small" aria-live="polite"></div></div>
<div id="businessSummary" class="grid"><div class="metric"><strong>—</strong><span>Customers</span></div><div class="metric"><strong>—</strong><span>Verified revenue records</span></div><div class="metric"><strong>—</strong><span>Expenses awaiting approval</span></div></div>
<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(250px,1fr))">
<div class="panel"><h3>Add customer</h3><form id="customerForm"><input name="title" required maxlength="160" placeholder="Customer / company name" style="width:100%;margin:6px 0"><input name="contact" maxlength="200" placeholder="Email or contact (optional)" style="width:100%;margin:6px 0"><textarea name="notes" maxlength="2000" placeholder="Notes" style="width:100%;margin:6px 0"></textarea><button type="submit">Save customer</button></form></div><div class="panel"><h3>Add investor / partner</h3><form id="investorForm"><input name="name" required maxlength="180" placeholder="Investor / partner name" style="width:100%;margin:6px 0"><input name="organization" maxlength="180" placeholder="Organization" style="width:100%;margin:6px 0"><input name="contact" maxlength="200" placeholder="Contact details" style="width:100%;margin:6px 0"><select name="stage" style="width:100%;margin:6px 0"><option value="prospect">Prospect</option><option value="contacted">Contacted</option><option value="interested">Interested</option><option value="due_diligence">Due diligence</option><option value="committed">Committed (record only)</option><option value="declined">Declined</option></select><textarea name="notes" maxlength="2000" placeholder="Notes / discussion history" style="width:100%;margin:6px 0"></textarea><button type="submit">Save investor</button></form></div>
<div class="panel"><h3>Record verified revenue</h3><form id="revenueForm"><input name="title" required maxlength="160" placeholder="Sale / order reference" style="width:100%;margin:6px 0"><input name="amount" required type="number" min="0" step="0.01" placeholder="Amount" style="width:100%;margin:6px 0"><select name="currency" style="width:100%;margin:6px 0"><option>USD</option><option>PKR</option><option>EUR</option><option>GBP</option></select><label><input name="verified_payment" type="checkbox"> Payment actually received and verified</label><textarea name="notes" maxlength="2000" placeholder="Payment reference / notes" style="width:100%;margin:6px 0"></textarea><button type="submit">Record revenue</button></form></div>
<div class="panel"><h3>Record expense for approval</h3><form id="expenseForm"><input name="title" required maxlength="160" placeholder="Expense / invoice" style="width:100%;margin:6px 0"><input name="amount" required type="number" min="0" step="0.01" placeholder="Amount" style="width:100%;margin:6px 0"><select name="currency" style="width:100%;margin:6px 0"><option>USD</option><option>PKR</option><option>EUR</option><option>GBP</option></select><textarea name="notes" maxlength="2000" placeholder="Purpose / vendor" style="width:100%;margin:6px 0"></textarea><button type="submit">Submit for owner review</button></form></div>
</div>
<div id="businessMessage" class="status" role="status"></div>
<div class="panel section">
<h3>Connect platform accounts · owner dashboard</h3>
<p class="small">Connections are isolated to the selected business. WordPress uses an Application Password; WooCommerce uses a REST API consumer key and secret. AIOS verifies access with a read-only request before encrypting credentials. Create read-only API keys wherever possible. No products, orders, posts or messages are changed by connection tests.</p>
<div class="toolbar section">
<select id="integrationProvider"><option value="wordpress">WordPress site</option><option value="woocommerce">WooCommerce store</option></select>
<input id="integrationSiteUrl" type="url" placeholder="https://your-domain.com" style="flex:1;min-width:200px">
</div>
<div class="toolbar section" id="wordpressFields"><input id="integrationUsername" autocomplete="username" placeholder="WordPress username" style="flex:1;min-width:180px"><input id="integrationSecret" type="password" autocomplete="new-password" placeholder="WordPress Application Password" style="flex:1;min-width:220px"></div>
<div class="toolbar section" id="woocommerceFields" style="display:none"><input id="integrationConsumerKey" autocomplete="off" placeholder="WooCommerce consumer key" style="flex:1;min-width:180px"><input id="integrationSecretWoo" type="password" autocomplete="new-password" placeholder="WooCommerce consumer secret" style="flex:1;min-width:220px"></div>
<div class="toolbar section"><button id="saveBusinessIntegration">Connect & verify account</button><span class="small">Credentials are sent only to your authenticated AIOS backend and encrypted at rest.</span></div>
<div id="integrationMessage" class="status" role="status">No integration action taken.</div><div id="integrationRows" class="small">Loading integration status…</div>
<div class="section" style="border:1px solid var(--line);border-radius:12px;padding:14px;margin-top:12px">
<strong>Social account sign-in · official OAuth</strong>
<p class="small">Connect through each platform's official authorization page. AIOS requests read-oriented permissions only. Tokens are encrypted server-side and scoped to the selected business. No posts, videos, messages, ads or account settings are changed.</p>
<div id="socialOAuthRows" class="grid"><div class="small">Checking social OAuth app setup…</div></div>
<div id="socialOAuthMessage" class="status">No social account authorization started.</div>
</div>
<div class="section" style="border:1px solid var(--line);border-radius:12px;padding:14px;margin-top:12px">
<strong>Gaming marketplace account connections</strong>
<p class="small">PlayerAuctions supports a documented seller API. Enter its API key and secret below. AIOS signs a read-only offer-list request to verify access; no listing, price, inventory or order changes occur.</p>
<div class="toolbar section"><input id="playerAuctionsKey" autocomplete="off" placeholder="PlayerAuctions API key" style="flex:1;min-width:180px"><input id="playerAuctionsSecret" type="password" autocomplete="new-password" placeholder="PlayerAuctions API secret" style="flex:1;min-width:200px"><button id="connectPlayerAuctions" type="button">Connect & verify</button></div>
<div id="marketplaceMessage" class="status">No marketplace connection action taken.</div>
<h3>Other selected marketplaces · readiness</h3>
<div class="small">Eldorado.gg — Seller API exists for verified sellers, but it has no test environment and covers live offers/orders. AIOS connector is not enabled until the exact auth contract and owner-approved action safeguards are completed.</div>
<div class="small">G2G — OpenAPI requires platform approval; its published eligibility currently limits applications to business-account sellers in Malaysia and Indonesia. Verify seller-entity eligibility before investing in setup.</div>
<div class="small">Z2U — No public seller API authentication specification was located. AIOS will not scrape the seller dashboard or imitate browser login.</div>
<h3>Digital storefronts · integration readiness</h3>
<div class="small">Etsy — owner-shop OAuth connection available above; configure the Seller App API keystring, shared secret and callback URL first.</div>
<div class="small">Gumroad — official API and Gumroad-hosted MCP connector exist; standard API cannot create products or upload content. AIOS needs its own supported OAuth/MCP client adapter. Not connected.</div>
<div class="small">itch.io — publishing requires the official Butler CLI; integration depends on the dedicated worker runtime and owner approval. Not connected.</div>
<div class="small">CGTrader — OAuth API access requires an API-key request/approval. Not connected.</div>
<div class="small">Fab — creator portal supports publisher listings, asset upload, review and publish; no public seller API contract was verified. Not connected.</div>
</div>

</div>
<h3>Customers</h3><div class="scroll"><table><thead><tr><th>Name</th><th>Contact</th><th>Notes</th><th>Created</th></tr></thead><tbody id="customerRows"><tr><td colspan="4">Loading…</td></tr></tbody></table></div><h3>Investors & partners</h3><div class="scroll"><table><thead><tr><th>Name</th><th>Organization</th><th>Contact</th><th>Stage</th><th>Notes</th></tr></thead><tbody id="investorRows"><tr><td colspan="5">Loading…</td></tr></tbody></table></div>
<h3>Financial ledger</h3><div class="scroll"><table><thead><tr><th>Type</th><th>Description</th><th>Amount</th><th>Status</th><th>Created</th></tr></thead><tbody id="ledgerRows"><tr><td colspan="5">Loading…</td></tr></tbody></table></div>
</section>
<section id="code-assets" class="panel section" data-view-panel="code-assets">
<h2>Code Asset Management & Licensing</h2>
<p class="small">Inventory original code and track ownership, dependency review and token estimates. A licensing offer can only be drafted after ownership and dependency clearance. Drafts create an approval request; no repository, source code or token is shared externally.</p>
<div class="grid"><div class="metric"><strong id="assetCount">—</strong><span>Registered assets</span></div><div class="metric"><strong id="offerCount">—</strong><span>Draft licensing offers</span></div><div class="metric"><strong id="licensedCount">0</strong><span>Completed licenses (tracked)</span></div></div>
<div class="panel"><h3>Register code asset</h3><form id="assetForm" class="grid" style="grid-template-columns:repeat(auto-fit,minmax(210px,1fr));align-items:start">
<input name="name" required maxlength="180" placeholder="Asset / repository name">
<input name="repository_url" type="url" placeholder="https://github.com/owner/repo">
<input name="path" maxlength="500" placeholder="Path inside repository (optional)">
<select name="asset_type"><option value="source_code">Source code</option><option value="library">Library</option><option value="template">Template</option><option value="automation">Automation</option><option value="documentation">Documentation</option><option value="other">Other</option></select>
<select name="ownership_status"><option value="unverified">Ownership unverified</option><option value="verified">Ownership verified</option><option value="owner_confirmed">Owner confirmed</option><option value="third_party">Third-party owned</option></select>
<select name="license"><option value="unknown">License unknown</option><option value="proprietary">Proprietary / original</option><option value="MIT">MIT</option><option value="Apache-2.0">Apache-2.0</option><option value="GPL">GPL family</option><option value="mixed">Mixed licenses</option></select>
<select name="dependency_review"><option value="not_reviewed">Dependencies not reviewed</option><option value="passed">Dependency review passed</option><option value="reviewed_clear">Reviewed / clear</option><option value="issues_found">Issues found</option></select>
<input name="token_estimate" type="number" min="0" step="1" placeholder="Token estimate (optional)">
<input name="token_method" maxlength="100" placeholder="Estimate method / source">
<textarea name="notes" maxlength="2000" placeholder="Ownership evidence, dependency notes, source details"></textarea>
<button type="submit">Register asset</button>
</form></div>
<div id="assetMessage" class="status" role="status"></div>
<h3>Asset inventory</h3><div class="scroll"><table><thead><tr><th>Asset</th><th>Repository / path</th><th>Ownership</th><th>License</th><th>Dependencies</th><th>Token estimate</th></tr></thead><tbody id="assetRows"><tr><td colspan="6">Loading…</td></tr></tbody></table></div>
<div class="panel"><h3>Prepare licensing offer (draft only)</h3><form id="licenseForm" class="grid" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr));align-items:start"><select name="asset_id" id="licenseAsset" required><option value="">Select eligible asset</option></select><input name="buyer" required maxlength="180" placeholder="Prospective buyer"><textarea name="terms" required maxlength="3000" placeholder="Draft scope, license type, price and restrictions"></textarea><button type="submit">Create draft & request approval</button></form></div>
<h3>Licensing pipeline</h3><div class="scroll"><table><thead><tr><th>Asset</th><th>Prospective buyer</th><th>Draft terms</th><th>Status</th><th>Created</th></tr></thead><tbody id="offerRows"><tr><td colspan="5">Loading…</td></tr></tbody></table></div>
</section>
</main>
<script>
const $=id=>document.getElementById(id);let authenticated=false;
function activateView(name){document.querySelectorAll("[data-view-panel]").forEach(el=>el.classList.toggle("active-view",el.dataset.viewPanel===name));document.querySelectorAll("nav.main-nav a[data-view]").forEach(a=>{const active=a.dataset.view===name;a.classList.toggle("active",active);if(active)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current")});if(location.hash!=="#"+name)history.replaceState(null,"","#"+name);window.scrollTo({top:0,behavior:"smooth"});}
document.querySelectorAll("nav.main-nav a[data-view]").forEach(a=>a.addEventListener("click",e=>{e.preventDefault();activateView(a.dataset.view)}));

const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function say(s){$("message").textContent=s}
activateView(location.hash.slice(1)||"overview");
if(location.hash==="#workflows")loadWorkflows();
document.querySelector('nav.main-nav a[data-view="workflows"]')?.addEventListener("click",loadWorkflows);
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
async function loadVentureOpportunities(){
 try{
  const items=await api("/venture-opportunities");
  $("ventureTotal").textContent=items.length;
  $("ventureResearch").textContent=items.filter(x=>x.status==="research_queued").length;
  $("ventureShortlist").textContent=items.filter(x=>x.status==="shortlisted").length;
  $("ventureLaunched").textContent=items.filter(x=>x.status==="launched").length;
  $("assessmentOpportunity").innerHTML='<option value="">Select opportunity</option>'+items.filter(x=>x.status!=="launched"&&x.status!=="rejected").map(x=>'<option value="'+esc(x.id)+'">'+esc(x.title)+'</option>').join("");
  $("ventureRows").innerHTML=items.length?items.map(x=>{
   const score=x.assessment?.scorecard||{};
   const scoreText=score.score==null?"Not scored":score.score+"/100 · provisional";
   const evidence=(x.evidence||[]).length;
   return '<tr><td><strong>'+esc(x.title)+'</strong><div class="small">'+esc(x.thesis)+'</div></td><td>'+esc(x.customer_segment||"Unknown")+'<div class="small">'+esc(x.revenue_model)+' · '+esc(x.market_scope)+'</div></td><td>'+esc(x.status)+'</td><td>'+esc(scoreText)+'</td><td>'+evidence+' sources</td><td><button class="secondary" data-v-action="research" data-v-id="'+esc(x.id)+'" '+(["research_queued","launch_approved","launched","rejected"].includes(x.status)?"disabled":"")+'>Research</button> <button class="secondary" data-v-action="shortlisted" data-v-id="'+esc(x.id)+'">Shortlist</button> <button class="secondary" data-v-action="launch_approved" data-v-id="'+esc(x.id)+'">Approve launch</button> <button class="secondary" data-v-action="launch" data-v-id="'+esc(x.id)+'" '+(x.status!=="launch_approved"?"disabled":"")+'>Create business</button> <button class="secondary" data-v-action="rejected" data-v-id="'+esc(x.id)+'">Reject</button></td></tr>';
  }).join(""):'<tr><td colspan="6">No opportunities yet. Add a hypothesis above.</td></tr>';
 }catch(e){$("ventureMessage").textContent="Portfolio load failed: "+e.message}
}
async function loadBusinessUnits(){
 const result=await api("/business-units");const units=result.business_units||[];
 ["taskBusiness","researchBusiness","brainBusiness","businessScope"].forEach(id=>{const select=$(id);if(!select)return;const current=select.value||"core";const options=units.map(b=>"<option value=\'"+esc(b.id)+"\'>"+esc(b.name)+(b.built_in?"":" - venture")+"</option>").join("");select.innerHTML=options;select.value=units.some(b=>b.id===current)?current:"core";});
 return units;
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
async function loadFreeApiCatalog(){
 const el=$("freeApiCatalogStatus");if(el)el.textContent="Loading provider catalog…";
 try{
  const data=await api("/discovery/provider-catalog");
  const rows=data.providers||[];
  $("freeApiCount").textContent=rows.length;
  $("freeApiLive").textContent=rows.filter(p=>p.status?.live?.state==="up").length;
  $("freeApiReview").textContent=rows.filter(p=>(p.policy?.trains_on_your_data||"unknown")!=="no"||(p.policy?.commercial_use||"unknown")!=="yes"||p.confidence!=="verified").length;
  const checked=rows.map(p=>p.status?.checked_at).filter(Boolean).sort().slice(-1)[0];
  $("freeApiFresh").textContent=checked?date(checked):"No check";
  $("freeApiRows").innerHTML=rows.length?rows.map(p=>{
   const train=p.policy?.trains_on_your_data||"unknown",commercial=p.policy?.commercial_use||"unknown";
   const live=p.status?.live?.state||"not-probed",docs=p.status?.docs?.state||"unknown";
   const sourceLinks=(p.sources||[]).slice(0,3).map(s=>'<a target="_blank" rel="noopener" href="'+esc(s.url)+'">'+esc(s.title||"Official source")+'</a>').join(" · ");
   return '<tr><td><strong>'+esc(p.name)+'</strong><div class="small">'+(p.website?'<a target="_blank" rel="noopener" href="'+esc(p.website)+'">Website</a>':'')+(p.api_key_url?' · <a target="_blank" rel="noopener" href="'+esc(p.api_key_url)+'">API signup</a>':'')+'</div></td><td>'+esc(p.category)+'</td><td>'+esc(p.free_tier?.headline||p.free_tier?.summary||"No summary supplied")+'<div class="small">Confidence: '+esc(p.confidence)+' · Last verified: '+esc(p.last_verified||"unknown")+'</div></td><td><span class="pill '+(train==="no"?"good":"warn")+'">Training: '+esc(train)+'</span><div class="small">'+esc(p.policy?.training_note||"No training detail")+'</div></td><td><span class="pill '+(commercial==="yes"?"good":"warn")+'">'+esc(commercial)+'</span><div class="small">'+esc(p.policy?.commercial_note||"No commercial-use detail")+'</div></td><td><span class="pill '+(live==="up"?"good":live==="down"?"bad":"warn")+'">'+esc(live)+'</span><div class="small">Docs: '+esc(docs)+' · '+esc(p.status?.live?.detail||p.status?.docs?.detail||"No probe detail")+'</div></td><td><a target="_blank" rel="noopener" href="'+esc(p.source_url)+'">Catalog</a>'+'<div class="small">'+sourceLinks+'</div></td></tr>';
  }).join(""):'<tr><td colspan="7">No provider records. Sync the catalog.</td></tr>';
  $("freeApiSourceNotes").innerHTML=(data.secondary_sources||[]).map(s=>'<p><strong>'+esc(s.repository)+'</strong> · '+esc(s.license)+' · <span class="pill">'+esc(s.decision)+'</span><br>'+esc(s.reason)+' <a target="_blank" rel="noopener" href="'+esc(s.url)+'">Open repository</a></p>').join("");
  if(el)el.textContent="Loaded "+rows.length+" public provider records · synced "+(rows[0]?date(rows[0].synced_at):"not yet");
 }catch(e){if(el)el.textContent="Catalog load failed: "+e.message}
}
$("refreshFreeApiCatalog").onclick=loadFreeApiCatalog;
$("syncFreeApiCatalog").onclick=async()=>{
 const b=$("syncFreeApiCatalog");b.disabled=true;
 try{
  const result=await api("/discovery/provider-catalog/sync",{method:"POST",body:"{}"});
  $("freeApiCatalogStatus").textContent="Synced "+result.imported+" providers from "+result.source+" · status checked "+(result.status_checked_at||"unknown");
  await loadFreeApiCatalog();
 }catch(e){$("freeApiCatalogStatus").textContent="Sync failed: "+e.message}
 finally{b.disabled=false}
};
async function checkGithubStatus(){const el=$("githubStatus");if(!el)return;el.textContent="Checking GitHub API…";try{const s=await api("/discovery/status");const g=s.github||{};el.textContent=g.connected?"GitHub API connected · "+g.authentication+" · search quota "+(g.search_remaining??"unknown")+"/"+(g.search_limit??"unknown")+" · discovery worker "+(s.worker_running?"running":"stopped"):"GitHub API unavailable · "+(g.error||"unknown error");el.className="status "+(g.connected&&s.worker_running?"good":"warn");}catch(e){el.textContent="GitHub check failed: "+e.message;el.className="status bad"}}
$("githubCheck").onclick=checkGithubStatus;
$("run").onclick=async()=>{const categories=[...document.querySelectorAll('input[name="cat"]:checked')].map(x=>x.value);if(!categories.length){say("Select at least one category.");return}try{$("run").disabled=true;const result=await api("/discovery/scans",{method:"POST",body:JSON.stringify({categories})});say("Scan queued: "+result.id+". The background worker must be running to process it.");await refresh()}catch(e){say(e.message)}finally{$("run").disabled=false}};
$("refresh").onclick=refresh;
window.reviewCandidate=async(url,decision)=>{const label=decision==="approved-for-sandbox"?"Approve for isolated sandbox review":"Reject candidate";if(!confirm(label+"? This records your decision only; it will not install or execute anything."))return;const notes=prompt("Optional review notes:")||"";try{await api("/discovery/candidates/review",{method:"POST",body:JSON.stringify({repository_url:url,decision,notes})});say("Owner decision saved. No software was installed or executed.");await refresh()}catch(e){say(e.message)}};


async function loadCompanyDepartments(){
 try{
  const data=await api("/company/departments");
  $("companyDepartmentCards").innerHTML=data.departments.map(d=>'<article class="metric"><strong style="font-size:17px">'+esc(d.name)+'</strong><span>'+esc(d.owner_role)+'</span><div class="small" style="margin-top:8px">'+esc(d.specialist_count)+' mapped catalogue roles · '+(d.roles_available?'roles available on demand':'no mapped roles')+'</div><div class="small" style="margin-top:6px">Sequential workflow + inbox handoffs</div><div class="small" style="margin-top:6px">'+esc(d.responsibilities.slice(0,2).join(' · '))+'</div></article>').join("");
 }catch(e){$("companyDepartmentCards").innerHTML='<div class="metric">'+esc(e.message)+'</div>'}
}

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
async function loadCollaboration(){
 try{
  const businessId=$("taskBusiness").value,department=$("collaborationDepartment").value;
  const [messages,delegations]=await Promise.all([
   api("/company/collaboration/messages?business_id="+encodeURIComponent(businessId)+"&department="+encodeURIComponent(department)),
   api("/company/collaboration/delegations?business_id="+encodeURIComponent(businessId))
  ]);
  $("collaborationInbox").innerHTML=messages.length?'<div class="scroll"><table><thead><tr><th>Subject</th><th>From</th><th>To</th><th>Status</th><th>Received</th><th>Action</th></tr></thead><tbody>'+messages.map(m=>'<tr><td><strong>'+esc(m.subject)+'</strong><div class="small">'+esc(m.body)+'</div></td><td>'+esc(m.sender_department)+'</td><td>'+esc(m.recipient_department)+'</td><td>'+esc(m.status)+'</td><td>'+esc(date(m.created_at))+'</td><td>'+(m.recipient_department===department&&m.status==="unread"?'<button class="secondary" data-id="'+esc(m.id)+'" onclick="readDepartmentMessage(this.dataset.id)">Mark read</button>':'—')+'</td></tr>').join("")+'</tbody></table></div>':'<p>No messages for this department in the selected business.</p>';
  $("collaborationDelegations").innerHTML=delegations.length?'<h4>Department task delegations</h4><div class="scroll"><table><thead><tr><th>Task</th><th>From</th><th>To</th><th>Status</th><th>Task ID</th></tr></thead><tbody>'+delegations.map(x=>'<tr><td>'+esc(x.title)+'</td><td>'+esc(x.from_department)+'</td><td>'+esc(x.to_department)+'</td><td>'+esc(x.status)+'</td><td>'+esc(x.child_task_id)+'</td></tr>').join("")+'</tbody></table></div>':'<p>No department delegations in this business.</p>';
 }catch(e){$("collaborationInbox").textContent=e.message;$("collaborationDelegations").textContent=e.message}
}
window.readDepartmentMessage=async(id)=>{
 try{const businessId=$("taskBusiness").value,department=$("collaborationDepartment").value;
  await api("/company/collaboration/messages/"+encodeURIComponent(id)+"/read?business_id="+encodeURIComponent(businessId)+"&department="+encodeURIComponent(department),{method:"POST"});await loadCollaboration();
 }catch(e){$("collaborationInbox").textContent=e.message}
};
$("refreshCollaboration").addEventListener("click",loadCollaboration);
$("collaborationDepartment").addEventListener("change",loadCollaboration);
$("departmentMessageForm").addEventListener("submit",async ev=>{
 ev.preventDefault();const f=new FormData(ev.currentTarget);
 try{await api("/company/collaboration/messages",{method:"POST",body:JSON.stringify({business_id:$("taskBusiness").value,sender_department:f.get("sender_department"),recipient_department:f.get("recipient_department"),subject:f.get("subject"),body:f.get("body")})});
  $("messageFormStatus").textContent="Message saved to the internal inbox.";ev.currentTarget.reset();await loadCollaboration();
 }catch(e){$("messageFormStatus").textContent=e.message}
});
$("departmentDelegationForm").addEventListener("submit",async ev=>{
 ev.preventDefault();const f=new FormData(ev.currentTarget);
 try{await api("/company/collaboration/delegations",{method:"POST",body:JSON.stringify({business_id:$("taskBusiness").value,from_department:f.get("from_department"),to_department:f.get("to_department"),title:f.get("title"),description:f.get("description")})});
  $("delegationFormStatus").textContent="Delegated task queued for internal worker execution. External actions remain approval-gated.";ev.currentTarget.reset();await loadCollaboration();await loadOperations();
 }catch(e){$("delegationFormStatus").textContent=e.message}
});
async function loadWorkflows(){
 try{
  const data=await api("/company/workflows");
  $("workflowTemplates").innerHTML=(data.templates||[]).map(t=>'<div class="metric"><strong style="font-size:17px">'+esc(t.name)+'</strong><span>'+esc(t.description)+'</span><p class="small">'+esc(t.step_count)+' department steps · '+esc((t.departments||[]).join(" → "))+'</p><button data-id="'+esc(t.id)+'" onclick="startWorkflow(this.dataset.id)">Create workflow</button></div>').join("");
  const instances=await api("/company/workflows/instances?business_id="+encodeURIComponent($("taskBusiness").value));
  $("workflowInstances").innerHTML=instances.length?'<h3>Saved workflows</h3>'+instances.map(w=>'<div class="toolbar" style="justify-content:space-between;border-bottom:1px solid var(--line);padding:9px 0"><span><strong>'+esc(w.name)+'</strong> <span class="pill">'+esc(w.status)+'</span><span class="small"> · '+esc(w.steps.filter(s=>s.status==="completed").length)+'/'+esc(w.steps.length)+' steps complete</span></span><button class="secondary" data-id="'+esc(w.id)+'" onclick="showWorkflow(this.dataset.id)">Open</button></div>').join(""):'<p class="small">No workflows started yet.</p>';
  $("workflowStatus").textContent="Workflow templates loaded. Creating a workflow queues only its first step.";
  await loadCollaboration();
 }catch(e){$("workflowStatus").textContent=e.message}
}
window.startWorkflow=async(templateId)=>{
 try{
  $("workflowStatus").textContent="Creating workflow…";
  const result=await api("/company/workflows/"+encodeURIComponent(templateId)+"/start?business_id="+encodeURIComponent($("taskBusiness").value),{method:"POST"});
  $("workflowStatus").textContent="Created "+result.name+" · "+result.steps.length+" steps. First department queued automatically; later steps follow successful handoffs.";
  await showWorkflow(result.id);await loadOperations();
 }catch(e){$("workflowStatus").textContent=e.message}
};
window.showWorkflow=async(workflowId)=>{
 try{
  const w=await api("/company/workflows/"+encodeURIComponent(workflowId)+"?business_id="+encodeURIComponent($("taskBusiness").value));
  $("workflowInstances").innerHTML='<h3>'+esc(w.name)+' <span class="pill">'+esc(w.status)+'</span></h3><div class="scroll"><table><thead><tr><th>Step</th><th>Department</th><th>Status</th><th>Action</th></tr></thead><tbody>'+w.steps.map(s=>'<tr><td>'+esc(s.sequence_no)+'. '+esc(s.title)+'</td><td>'+esc(s.department)+'</td><td><span class="pill '+(s.status==="completed"?"good":s.status==="failed"?"bad":s.status==="queued"?"warn":"")+'">'+esc(s.status)+'</span></td><td>'+(s.status==="queued"?'<button data-id="'+esc(s.task_id)+'" onclick="runTask(this.dataset.id)">Run this department</button>':s.status==="blocked"?"Waiting for previous step":"—")+'</td></tr>').join("")+'</tbody></table></div><p class="small">Workflow ID: '+esc(w.id)+'</p>';
 }catch(e){$("workflowStatus").textContent=e.message}
};
$("refreshWorkflows").addEventListener("click",loadWorkflows);
function renderExecutiveOverview(overview,tasks,approvals,runs){
 const taskCounts={queued:0,running:0,in_progress:0,completed:0,failed:0};
 (tasks||[]).forEach(t=>{const state=String(t.status||"").toLowerCase();if(Object.prototype.hasOwnProperty.call(taskCounts,state))taskCounts[state]++});
 const runState=r=>String(r.status||"").toLowerCase();
 const active=(runs||[]).filter(r=>["queued","running","in_progress"].includes(runState(r)));
 const completed=(runs||[]).filter(r=>runState(r)==="completed");
 const failed=(runs||[]).filter(r=>["failed","partial"].includes(runState(r)));
 $("overviewActiveRuns").textContent=active.length;$("overviewCompletedRuns").textContent=completed.length;
 $("overviewQueuedTasks").textContent=taskCounts.queued;$("overviewFailedRuns").textContent=failed.length;
 const online=Boolean(overview.agent_worker_running);
 $("overviewWorkerState").textContent=online?"Shared worker online":"Worker offline / idle";
 $("overviewWorkerState").className="pill "+(online?"good":"warn");
 $("overviewLastUpdated").textContent="Updated "+new Date().toLocaleTimeString();
 const taskById=new Map((tasks||[]).map(t=>[t.id,t]));
 const recent=[...(runs||[])].sort((a,b)=>String(b.created_at||"").localeCompare(String(a.created_at||""))).slice(0,5);
 $("overviewActivity").innerHTML=recent.length?recent.map(r=>{const task=taskById.get(r.task_id);const state=runState(r);const tone=state==="completed"?"good":(["failed","partial"].includes(state)?"bad":(["queued","running","in_progress"].includes(state)?"warn":""));return '<div class="overview-item"><div><strong>'+esc(task?.title||r.task_id||"AI run")+'</strong><div class="small">'+esc(date(r.created_at))+'</div></div><span class="pill '+tone+'">'+esc(r.status||"unknown")+'</span></div>'}).join(""):'<div class="small">No AI runs recorded yet. Create a task when you are ready to start work.</div>';
 const pending=(approvals||[]).filter(a=>String(a.status||"").toLowerCase()==="pending").slice(0,4);
 $("overviewApprovalPreview").innerHTML=pending.length?pending.map(a=>'<div class="overview-item"><div><strong>'+esc(a.action||"Approval request")+'</strong><div class="small">'+esc(String(a.details||"").slice(0,125))+'</div></div><span class="pill warn">Pending</span></div>').join(""):'<div class="small">No owner decisions are waiting right now.</div>';
}
async function loadOperations(){
 try{
  const businessId=$("taskBusiness").value;const scope="?business_id="+encodeURIComponent(businessId);const [overview,tasks,approvals,runs]=await Promise.all([api("/company/overview"),api("/tasks"+scope),api("/approvals"+scope),api("/agent-runs"+scope)]);
  $("taskCount").textContent=tasks.length;
  $("approvalCount").textContent=approvals.filter(a=>a.status==="pending").length;$("stageRuntime").textContent=overview.agent_worker_running?"Shared worker online":"Shared worker offline";
  $("stageRuntime").style.borderColor=overview.agent_worker_running?"rgba(103,243,192,.35)":"rgba(255,133,133,.35)";
  $("stageRuntime").style.color=overview.agent_worker_running?"#a6e9d4":"#ffaaaa";
  $("runtimeStatus").textContent=overview.agent_worker_running?"● Agent worker online · queue processor active · owner approval remains required":"● Agent worker offline · API is responding, but queued work will not execute until the worker is restored.";if(!overview.agent_worker_running)setApiHealth("API online · worker offline","degraded");else setApiHealth("API + worker online");
  const latest={};runs.forEach(r=>{if(!latest[r.task_id])latest[r.task_id]=r});
  $("taskApprovalPanel").innerHTML='<p><strong>Tasks</strong>: '+tasks.length+' · <strong>Approvals pending</strong>: '+approvals.filter(a=>a.status==="pending").length+' · <strong>Agent worker</strong>: '+esc(overview.execution_runtime)+'</p><div class="scroll"><table><thead><tr><th>Task</th><th>Business environment</th><th>Department</th><th>Status</th><th>AI team</th></tr></thead><tbody>'+tasks.slice(0,30).map(t=>{const r=latest[t.id];return '<tr><td>'+esc(t.title)+'</td><td>'+esc(t.business_id||'core')+'</td><td>'+esc(t.department)+'</td><td>'+esc(t.status)+'</td><td>'+(r?'<span class="pill">'+esc(r.status)+'</span> ':'')+(r&&["queued","running"].includes(r.status)?'<button class="secondary" disabled>Already running</button>':'<button class="secondary" data-id="'+esc(t.id)+'" onclick="runTask(this.dataset.id)">Run AI team</button>')+'</td></tr>'}).join("")+'</tbody></table></div><h3>Approval inbox</h3><div class="scroll"><table><thead><tr><th>Requested action</th><th>Details</th><th>Status</th><th>Owner decision</th></tr></thead><tbody>'+approvals.slice(0,20).map(a=>'<tr><td>'+esc(a.action)+'</td><td>'+esc(a.details)+'</td><td>'+esc(a.status)+'</td><td>'+(a.status==="pending"?'<button class="secondary" data-id="'+esc(a.id)+'" onclick="decideApproval(this.dataset.id,\'approved\')">Approve</button> <button class="secondary" data-id="'+esc(a.id)+'" onclick="decideApproval(this.dataset.id,\'rejected\')">Reject</button>':'—')+'</td></tr>').join("")+'</tbody></table></div>';
  renderExecutiveOverview(overview,tasks,approvals,runs);
 }catch(e){$("taskApprovalPanel").textContent=e.message}
}
window.runTask=async(taskId)=>{try{$("agentRunOutput").textContent="Queuing specialist and CEO review…";const run=await api("/tasks/"+encodeURIComponent(taskId)+"/execute?business_id="+encodeURIComponent($("taskBusiness").value),{method:"POST"});$("agentRunOutput").textContent="AI team run "+run.id+" · "+run.status+". Waiting for specialist and CEO review…";await loadOperations();pollAgentRun(run.id,$("taskBusiness").value)}catch(e){$("agentRunOutput").textContent=e.message}};
async function pollAgentRun(runId,businessId){const scope="?business_id="+encodeURIComponent(businessId);try{const r=await api("/agent-runs/"+encodeURIComponent(runId)+scope);const events=await api("/agent-runs/"+encodeURIComponent(runId)+"/events"+scope);const steps=await api("/agent-runs/"+encodeURIComponent(runId)+"/steps"+scope);const timeline=events.map(x=>"• "+x.stage+": "+x.message).join("\n");const contributions=steps.map(s=>'<section class="card" style="margin:10px 0"><h4>'+esc(String(s.sequence_no)+". "+s.role+" · "+s.agent_name)+'</h4><p class="small">Status: '+esc(s.status)+' · '+esc(s.agent_id)+'</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(s.output||s.error||"Working…")+'</pre></section>').join("");if(r.status==="completed"){$("agentRunOutput").innerHTML='<h3>Collaborative run completed</h3><p class="small">Three live model calls · lead specialist + independent collaborator + CEO integration</p><h4>Execution timeline</h4><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(timeline)+'</pre><h4>Agent contributions</h4>'+contributions+'<h4>Final CEO-reviewed deliverable</h4><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(r.ceo_review)+'</pre><p class="small">Usage: '+esc(JSON.stringify(r.usage||{}))+'</p>';await loadOperations();return}if(r.status==="partial"||r.status==="failed"){$("agentRunOutput").innerHTML='<h3 class="'+(r.status==="partial"?"":"bad")+'">'+(r.status==="partial"?"Partial result preserved":"Agent run failed safely")+'</h3>'+(r.specialist_output?'<h4>Saved lead specialist deliverable</h4><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(r.specialist_output)+'</pre>':'')+'<p>'+esc(r.error||"Unknown error")+'</p><p class="small">'+esc(failureAdvice(r.error))+'</p><button class="secondary" id="retryAgentRun">Retry incomplete stage(s)</button><p class="small">Completed stages are reused; only failed or incomplete stages will make new model requests. Free-confirmed providers only; no paid fallback.</p><h4>Execution timeline</h4><pre style="white-space:pre-wrap">'+esc(timeline)+'</pre>'+contributions;const retryButton=$("retryAgentRun");if(retryButton)retryButton.onclick=async()=>{retryButton.disabled=true;retryButton.textContent="Queueing retry…";try{const queued=await api("/agent-runs/"+encodeURIComponent(runId)+"/retry?business_id="+encodeURIComponent(businessId),{method:"POST"});$("agentRunOutput").textContent="Retry queued · "+queued.id;await loadOperations();pollAgentRun(runId,businessId)}catch(e){retryButton.disabled=false;retryButton.textContent="Retry incomplete stage(s)";say(e.message)}};await loadOperations();return}$("agentRunOutput").innerHTML='<h3>Collaborative team run '+esc(r.status)+'…</h3><p class="small">Lead specialist → independent collaborator → CEO integration</p><pre style="white-space:pre-wrap">'+esc(timeline)+'</pre>'+contributions;setTimeout(()=>pollAgentRun(runId,businessId),3000)}catch(e){$("agentRunOutput").textContent=e.message}}

window.decideApproval=async(id,decision)=>{if(!confirm("Confirm "+decision+" this requested action? The CEO/agent must still execute it through the approved runtime."))return;try{await api("/approvals/"+encodeURIComponent(id)+"/decision?business_id="+encodeURIComponent($("taskBusiness").value),{method:"POST",body:JSON.stringify({decision})});await loadOperations()}catch(e){say(e.message)}};
$("taskForm").addEventListener("submit",async e=>{e.preventDefault();const title=$("taskTitle").value.trim();if(!title)return;try{await api("/tasks",{method:"POST",body:JSON.stringify({title,department:$("taskDepartment").value,business_id:$("taskBusiness").value})});$("taskTitle").value="";await loadOperations()}catch(e){say(e.message)}});
$("overviewRefresh").addEventListener("click",loadOperations);
document.querySelectorAll("[data-overview-view]").forEach(button=>button.addEventListener("click",()=>activateView(button.dataset.overviewView)));
$("loadAgents").onclick=loadAgents;$("agentSearch").addEventListener("input",()=>{clearTimeout(window.agentSearchTimer);window.agentSearchTimer=setTimeout(loadAgents,250)});$("departmentFilter").onchange=loadAgents;$("loadOperations").onclick=loadOperations;$("taskBusiness").addEventListener("change",()=>{loadOperations();loadWorkflows()});
async function loadResearchSources(){
 try{
  const rows=await api("/research/sources?business_id="+encodeURIComponent($("researchBusiness").value));
  $("researchSources").innerHTML=rows.length?rows.map(s=>'<article class="card" style="margin:9px 0;padding:12px"><strong>'+esc(s.title||"Untitled source")+'</strong><div class="small"><a href="'+esc(s.url)+'" target="_blank" rel="noopener">'+esc(s.url)+'</a></div><div class="small">Captured '+esc(date(s.captured_at))+' · '+esc(s.characters)+' characters</div></article>').join(""):'No captured sources yet. Add a public HTTPS page above.';
 }catch(e){$("researchSources").textContent=e.message}
}
async function captureResearchSource(){
 const field=$("researchSourceUrl");const url=field.value.normalize("NFC").replace(/[\\u200B-\\u200F\\u2060\\uFEFF]/g,"").trim();field.value=url;if(!url){$("researchSourceStatus").textContent="Enter a public HTTPS URL.";return}
 const b=$("captureResearchSource");b.disabled=true;$("researchSourceStatus").textContent="Fetching and extracting page text…";
 try{const result=await api("/research/sources",{method:"POST",body:JSON.stringify({url,business_id:$("researchBusiness").value})});$("researchSourceUrl").value="";const redirectNote=result.redirected?" WARNING: The submitted URL redirected ("+result.redirect_count+" hop(s)). Final page: "+result.url+". Check that this is the intended evidence before relying on it.":"Source URL matched the submitted destination.";const partialNote=result.truncated?" PARTIAL: only the first 1 MB was inspected.":"";$("researchSourceStatus").textContent="Captured: "+(result.title||result.url)+" · "+result.characters+" characters. "+redirectNote+partialNote+" Capture success does not mean the content is relevant.";await loadResearchSources()}
 catch(e){$("researchSourceStatus").textContent=e.message}
 finally{b.disabled=false}
}
$("captureResearchSource").onclick=captureResearchSource;
$("refreshResearchSources").onclick=loadResearchSources;$("researchBusiness").addEventListener("change",loadResearchSources);$("businessScope").addEventListener("change",()=>{loadBusiness();loadBusinessIntegrations()});

async function loadBrain(){
 try{
  const businessId=$("brainBusiness").value;const scope="?business_id="+encodeURIComponent(businessId);const [status,proposed,approved]=await Promise.all([api("/brain/status"+scope),api("/brain/memories?status=proposed&business_id="+encodeURIComponent(businessId)),api("/brain/memories?status=approved&business_id="+encodeURIComponent(businessId))]);
  $("brainExperiences").textContent=status.experiences;
  $("brainApproved").textContent=status.memories.approved;
  $("brainProposed").textContent=status.memories.proposed;
  $("brainRejected").textContent=status.memories.rejected;
  const autonomy=status.autonomy||{};const last=autonomy.last_cycle&&autonomy.last_cycle.created_at?(" · last cycle "+autonomy.last_cycle.created_at):" · first cycle pending";$("brainMode").textContent=status.business_id+" · "+status.learning_mode+" · "+(autonomy.pending_improvement_proposals||0)+" improvement proposals · "+(autonomy.learning_cycles||0)+" cycles"+last;
  $("brainProposals").innerHTML=proposed.length?proposed.map(m=>'<article class="card" style="margin:10px 0"><h4>'+esc(m.title)+'</h4><p class="small">'+esc(m.department)+' · '+esc(m.category)+' · confidence '+esc(m.confidence)+'</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(m.content)+'</pre><button data-id="'+esc(m.id)+'" onclick="reviewBrainMemory(this.dataset.id,\'approved\')">Approve into brain</button> <button class="secondary" data-id="'+esc(m.id)+'" onclick="reviewBrainMemory(this.dataset.id,\'rejected\')">Reject</button></article>').join(""):'No proposed memories yet. Completed task outcomes will appear here.';
  $("brainApprovedList").innerHTML=approved.length?approved.slice(0,15).map(m=>'<article class="card" style="margin:8px 0"><strong>'+esc(m.title)+'</strong><p class="small">'+esc(m.department)+' · '+esc(m.created_at)+'</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(m.content.slice(0,1200))+'</pre></article>').join(""):'No approved memories yet. Approve a proposed lesson to make it available to future agents.';
 }catch(e){$("brainMode").textContent=e.message}
}
window.reviewBrainMemory=async(id,decision)=>{if(!confirm("Are you sure you want to "+decision+" this memory?"))return;try{await api("/brain/memories/"+encodeURIComponent(id)+"/review",{method:"POST",body:JSON.stringify({decision,note:"Owner reviewed in dashboard"})});await loadBrain()}catch(e){$("brainMode").textContent=e.message}};
$("refreshBrain").onclick=loadBrain;$("brainBusiness").addEventListener("change",loadBrain);
async function loadProviders(){try{const providers=await api("/llm/providers");const select=$("providerSelect");const previous=select.value;select.innerHTML='<option value="auto">AUTO · free-only failover</option>'+providers.map(p=>'<option value="'+esc(p.id)+'">'+esc(p.name)+' · '+(p.eligible?'eligible':'blocked')+'</option>').join("");const preferred=providers.find(p=>p.id==="unorouter"&&p.eligible)||providers.find(p=>p.eligible);select.value=previous==="auto"||providers.some(p=>p.id===previous&&p.eligible)?previous:"auto";$("providerStatus").textContent="Automatic mode tries UnoRouter first, then other eligible free-confirmed providers. No paid fallback.\n"+providers.map(p=>p.name+": "+(p.eligible?"eligible (free status owner-confirmed)":p.reason)).join("\n")+(preferred?"\nFirst eligible provider: "+preferred.name:"\nNo provider is eligible. Configure and confirm a free endpoint first.");}catch(e){$("providerStatus").textContent=e.message}}
async function runModel(test){const provider=$("providerSelect").value;if(!provider){$("modelOutput").textContent="No eligible free provider is selected. Check AI models and configure/confirm a free endpoint.";return}const prompt=test?"Reply with exactly: AIOS live connection successful":$("modelPrompt").value.trim();if(!prompt){$("modelOutput").textContent="Enter a prompt first.";return}const button=test?$("testProvider"):$("runModel");button.disabled=true;$("modelOutput").textContent="Sending live request…";try{const result=await api(test?"/llm/test":"/llm/run",{method:"POST",body:JSON.stringify({provider,prompt})});$("modelOutput").textContent=JSON.stringify(result,null,2)}catch(e){$("modelOutput").textContent="Live request failed: "+e.message}finally{button.disabled=false}}
$("loadProviders").onclick=loadProviders;$("testProvider").onclick=()=>runModel(true);$("runModel").onclick=()=>runModel(false);
async function saveProviderKey(){const api_key=$("providerApiKey").value.trim();if(!api_key){$("credentialStatus").textContent="Enter your OpenRouter key.";return}if(!$("confirmFreeOnly").checked){$("credentialStatus").textContent="Confirm free-only routing before saving.";return}const b=$("saveProviderKey");b.disabled=true;$("credentialStatus").textContent="Encrypting and saving on the server…";try{const result=await api("/llm/credentials/openrouter",{method:"POST",body:JSON.stringify({api_key,confirm_free_only:true})});$("providerApiKey").value="";$("credentialStatus").textContent="Saved securely in encrypted storage. Secret was not returned.";await loadProviders()}catch(e){$("credentialStatus").textContent=e.message}finally{b.disabled=false}}
$("saveProviderKey").onclick=saveProviderKey;
async function saveVaultProvider(){const provider=$("vaultProvider").value,api_key=$("vaultApiKey").value.trim(),model=$("vaultModel").value.trim(),freeConfirmed=$("vaultFreeOnly").checked;if(provider==="unorouter"&&!api_key&&!model){$("vaultProviderStatus").textContent="Enter the API key first, or choose a model to update the saved connection.";return}if(provider==="unorouter"&&model&&model!=="__catalog_only__"&&model.endsWith(":free")&&!freeConfirmed){$("vaultProviderStatus").textContent="Confirm the :free model before enabling free-only routing.";return}if(provider==="unorouter"&&model&&model!=="__catalog_only__"&&!model.endsWith(":free")&&freeConfirmed){$("vaultProviderStatus").textContent="A paid model cannot be marked free. Uncheck free-only routing.";return}if(provider!=="unorouter"&&!freeConfirmed){$("vaultProviderStatus").textContent="Confirm this provider/model is free before saving.";return}const b=$("saveVaultProvider");b.disabled=true;$("vaultProviderStatus").textContent="Saving encrypted provider configuration…";try{if(provider==="unorouter"&&!api_key){await api("/llm/credentials/unorouter/model",{method:"POST",body:JSON.stringify({model,confirm_free_only:freeConfirmed})})}else{const savedModel=provider==="unorouter"&&!model?"__catalog_only__":model;await api("/llm/credentials/"+encodeURIComponent(provider),{method:"POST",body:JSON.stringify({api_key,model:savedModel,confirm_free_only:freeConfirmed})});$("vaultApiKey").value=""}$("vaultProviderStatus").textContent="Saved securely. "+(model.endsWith(":free")?"Free-only automatic routing enabled.":model==="__catalog_only__"?"Key saved. Load the catalogue to select an exact model ID.":"Paid model saved but blocked from automatic routing; per-request approval required.");await loadProviders()}catch(e){$("vaultProviderStatus").textContent=e.message}finally{b.disabled=false}}
$("saveVaultProvider").onclick=saveVaultProvider;

async function loadUnoRouterModels(){const b=$("loadUnoRouterModels");b.disabled=true;$("unorouterCatalogStatus").textContent="Reading public pricing and key-accessible models. No prompt is sent…";try{const data=await api("/llm/unorouter/catalog");const select=$("unorouterModelSelect");const options=['<option value="">Choose an available model…</option>'];for(const m of data.models||[]){const price=m.free?"FREE · $0":("PAID · $"+(m.input_price_per_million??"n/a")+"/$"+(m.output_price_per_million??"n/a")+" per 1M tokens");options.push('<option value="'+esc(m.id)+'" data-free="'+(m.free?"true":"false")+'">'+(m.free?"FREE · ":"PAID · ")+esc(m.id)+' · '+esc(m.vendor||"provider")+' · '+price+'</option>')}select.innerHTML=options.join("");const counts=data.counts||{};$("unorouterCatalogStatus").textContent="Public catalogue: "+(counts.models??data.public_models?.length??0)+" models ("+(counts.free??"—")+" free, "+(counts.paid??"—")+" paid). Available to saved key: "+data.available_to_key_count+" ("+data.available_free_count+" free, "+data.available_paid_count+" paid). Exact IDs preserved. "+(data.account_key_configured?"":"Save your UnoRouter key first to load models available to your account.")+" Read-only lookup complete; no prompt or inference request was sent.";}catch(e){$("unorouterCatalogStatus").textContent="Catalog unavailable: "+e.message}finally{b.disabled=false}}
$("loadUnoRouterModels").onclick=loadUnoRouterModels;$("unorouterModelSelect").onchange=()=>{const selected=$("unorouterModelSelect").selectedOptions[0];if($("unorouterModelSelect").value){$("vaultProvider").value="unorouter";$("vaultModel").value=$("unorouterModelSelect").value;$("vaultFreeOnly").checked=selected?.dataset?.free==="true";$("approveUnoRouterPaid").checked=false;}};
async function testUnoRouterPersonal(){const prompt=$("unorouterPersonalPrompt").value.trim();if(!prompt){$("unorouterPersonalOutput").textContent="Enter a small synthetic test prompt.";return}const selected=$("unorouterModelSelect").selectedOptions[0];const selectedIsFree=selected?.dataset?.free==="true";const approvePaid=$("approveUnoRouterPaid").checked;if(!selected?.value){$("unorouterPersonalOutput").textContent="Load the catalogue and select a model first.";return}if(!selectedIsFree&&!approvePaid){$("unorouterPersonalOutput").textContent="Blocked: this is a paid model. Explicitly approve this specific request first.";return}if($("vaultModel").value!==selected.value){$("unorouterPersonalOutput").textContent="The selected model differs from the saved credential model. Save the exact selected model first.";return}if(!selectedIsFree&&!window.confirm("Send this prompt to the selected PAID model? Charges may apply. Approval applies only to this request.")){return}const b=$("testUnoRouterPersonal");b.disabled=true;$("unorouterPersonalOutput").textContent="Sending the owner-approved request…";try{const result=await api("/llm/unorouter/personal-test",{method:"POST",body:JSON.stringify({provider:"unorouter",prompt,approve_paid_request:!selectedIsFree&&approvePaid})});$("unorouterPersonalOutput").textContent=JSON.stringify(result,null,2);$("approveUnoRouterPaid").checked=false}catch(e){$("unorouterPersonalOutput").textContent="Personal test failed: "+e.message}finally{b.disabled=false}}
$("testUnoRouterPersonal").onclick=testUnoRouterPersonal;

// The earlier change handler also syncs the selected model's verified free/paid state.

async function loadSupabaseStatus(){try{const s=await api("/integrations/supabase/status");const ready=s.database_configured;const provider=s.database_provider||"not configured";$("supabaseStatus").textContent=ready?"PostgreSQL target configured · "+provider:"Database URL not configured or not PostgreSQL";$("supabaseStatus").className="status "+(ready?"good":"warn");$("supabaseOutput").textContent=JSON.stringify(s,null,2)}catch(e){$("supabaseStatus").textContent="Status unavailable: "+e.message;$("supabaseStatus").className="status warn"}}
async function testSupabaseConnection(){const b=$("supabaseTest");b.disabled=true;$("supabaseOutput").textContent="Running a TLS-required read-only SELECT 1 probe (maximum 5 seconds)…";try{const result=await api("/integrations/supabase/test",{method:"POST",body:"{}"});$("supabaseOutput").textContent=JSON.stringify(result,null,2);$("supabaseStatus").textContent=result.connected?"Supabase database connection verified":"Connection test failed · "+(result.error_type||"unknown error");$("supabaseStatus").className="status "+(result.connected?"good":"warn")}catch(e){$("supabaseOutput").textContent="Connection test failed: "+e.message;$("supabaseStatus").textContent="Connection test failed";$("supabaseStatus").className="status warn"}finally{b.disabled=false}}
$("supabaseRefresh").onclick=loadSupabaseStatus;
$("supabaseTest").onclick=testSupabaseConnection;

async function loadApiAnythingStatus(){try{const s=await api("/integrations/api-anything/status");$("apiAnythingStatus").textContent=s.connected?"Connected · "+(s.version||"version unknown")+" · "+s.execution_policy:(s.configured?"Configured but offline · ":"Not configured · ")+(s.error||"Set private Railway variables to connect.");$("apiAnythingStatus").className="status "+(s.connected?"good":"warn")}catch(e){$("apiAnythingStatus").textContent=e.message;$("apiAnythingStatus").className="status warn"}}
async function apiAnythingShow(path){const out=$("apiAnythingResults");out.textContent="Loading…";try{const result=await api(path);out.textContent=JSON.stringify(result,null,2)}catch(e){out.textContent="Request failed: "+e.message}}
$("apiAnythingRefresh").onclick=loadApiAnythingStatus;
$("apiAnythingSites").onclick=()=>apiAnythingShow("/integrations/api-anything/sites");
$("apiAnythingOperations").onclick=()=>{const site=$("apiAnythingSite").value.trim();if(!site){$("apiAnythingResults").textContent="Enter a site name first.";return}apiAnythingShow("/integrations/api-anything/sites/"+encodeURIComponent(site))};
$("apiAnythingFind").onclick=()=>apiAnythingShow("/integrations/api-anything/find?q="+encodeURIComponent($("apiAnythingQuery").value));
$("apiAnythingCall").onclick=async()=>{const out=$("apiAnythingOutput");let args;try{args=JSON.parse($("apiAnythingArgs").value||"{}");if(!args||Array.isArray(args)||typeof args!=="object")throw Error("Arguments must be a JSON object.")}catch(e){out.textContent="Invalid JSON: "+e.message;return}const site=$("apiAnythingSite").value.trim(),op=$("apiAnythingOperation").value.trim();if(!site||!op){out.textContent="Enter both a site and an operation.";return}const b=$("apiAnythingCall");b.disabled=true;out.textContent="Running owner-triggered read-only request…";try{const result=await api("/integrations/api-anything/call/"+encodeURIComponent(site)+"/"+encodeURIComponent(op),{method:"POST",body:JSON.stringify({args})});out.textContent=JSON.stringify(result,null,2)}catch(e){out.textContent="Operation failed: "+e.message}finally{b.disabled=false}};
function showLogin(message=""){ $("loginPanel").style.display="flex"; $("loginStatus").textContent=message; $("loginKey").focus(); }
async function startDashboard(){authenticated=true;$("loginPanel").style.display="none";loadApiAnythingStatus();loadSupabaseStatus();refresh();checkGithubStatus();loadFreeApiCatalog();loadProviders();loadCompanyDepartments();loadAgents();loadSources();loadOperations();loadBrain();loadResearchSources();loadBusiness();loadBusinessIntegrations();api("/llm/credentials").then(x=>{$("credentialStatus").textContent=x.openrouter.configured?"OpenRouter credential is saved (encrypted).":"No OpenRouter credential saved yet.";const saved=Object.entries(x.providers||{}).filter(([id,v])=>v.configured).map(([id,v])=>id+" · "+v.model+" · "+(v.free_confirmed?"free-confirmed":"blocked"));$("vaultProviderStatus").textContent=saved.length?"Encrypted provider connections: "+saved.join(" | "):"No additional provider credentials saved yet."}).catch(e=>$("credentialStatus").textContent=e.message);if(!window.aiosRefreshTimer)window.aiosRefreshTimer=setInterval(refresh,10000)}
$("loginForm").addEventListener("submit",async e=>{e.preventDefault();const b=$("loginButton");b.disabled=true;$("loginStatus").textContent="Validating owner key…";try{const r=await fetch("/auth/session",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json"},body:JSON.stringify({api_key:$("loginKey").value})});if(!r.ok)throw Error("Owner key was rejected. Check the key in Railway Variables.");$("loginKey").value="";await startDashboard()}catch(err){$("loginStatus").textContent=err.message}finally{b.disabled=false}});
$("logoutButton").onclick=async()=>{try{await fetch("/auth/session",{method:"DELETE",credentials:"same-origin"});}finally{authenticated=false;showLogin("You have been signed out.")}};
fetch("/auth/session",{credentials:"same-origin"}).then(r=>r.json()).then(s=>{if(s.authenticated)startDashboard();else showLogin()}).catch(()=>showLogin("Sign in to continue."));
</script><script type="module">
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js";
(()=>{
const canvas=document.getElementById("officeCanvas"),fallback=document.getElementById("officeFallback");
if(!canvas)return;
const scene=new THREE.Scene();scene.background=new THREE.Color(0x070e1b);scene.fog=new THREE.Fog(0x070e1b,28,58);
const camera=new THREE.PerspectiveCamera(43,1,.1,100);let az=.12,polar=.92,distance=31,target=new THREE.Vector3(0,0,0);
const renderer=new THREE.WebGLRenderer({canvas,antialias:false,alpha:false,powerPreference:"low-power"});
renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.25));renderer.outputColorSpace=THREE.SRGBColorSpace;
scene.add(new THREE.HemisphereLight(0xc8e5ff,0x182238,2.0));
const key=new THREE.DirectionalLight(0xc3e2ff,2.2);key.position.set(-8,15,10);scene.add(key);
const cyan=new THREE.PointLight(0x38cfff,1.2,32);cyan.position.set(-10,7,-5);scene.add(cyan);
const violet=new THREE.PointLight(0x9d7cff,1.0,30);violet.position.set(10,6,5);scene.add(violet);
function mat(color,rough=.58,metal=.16,emissive=0){return new THREE.MeshStandardMaterial({color,roughness:rough,metalness:metal,emissive:emissive})}
function addBox(parent,w,h,d,color,x,y,z,rough=.58){const mesh=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),mat(color,rough));mesh.position.set(x,y,z);parent.add(mesh);return mesh}
const floor=new THREE.Mesh(new THREE.PlaneGeometry(34,28),mat(0x0c1728,.88,.12));floor.rotation.x=-Math.PI/2;floor.position.y=-.08;scene.add(floor);
const grid=new THREE.GridHelper(34,34,0x276084,0x172d48);grid.position.y=-.065;scene.add(grid);
const outer=new THREE.Mesh(new THREE.BoxGeometry(34,.18,28),mat(0x152844,.55,.3));outer.position.y=-.18;scene.add(outer);
const center=new THREE.Group();scene.add(center);
const core=new THREE.Mesh(new THREE.CylinderGeometry(2.2,2.6,.22,48),mat(0x173858,.35,.45,0x06223a));core.position.set(0,.04,0);center.add(core);
const coreRing=new THREE.Mesh(new THREE.TorusGeometry(2.5,.035,8,64),new THREE.MeshBasicMaterial({color:0x62eaff}));coreRing.rotation.x=Math.PI/2;coreRing.position.y=.18;center.add(coreRing);
function makeLabel(text,color){
 const c=document.createElement("canvas");c.width=512;c.height=100;const ctx=c.getContext("2d");
 ctx.fillStyle="rgba(5,14,28,.92)";ctx.fillRect(0,0,512,100);ctx.strokeStyle=color;ctx.lineWidth=4;ctx.strokeRect(3,3,506,94);
 ctx.fillStyle="#edf7ff";ctx.font="700 28px system-ui";ctx.textAlign="center";ctx.textBaseline="middle";
 const words=String(text||"DEPARTMENT").toUpperCase();ctx.fillText(words.length>25?words.slice(0,23)+"…":words,256,52);
 const texture=new THREE.CanvasTexture(c);const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,transparent:true,depthWrite:false}));
 sprite.scale.set(3.0,.59,1);return sprite;
}
const palette=[0x58b7ff,0x9a86ff,0x54d9c1,0xf2bd69,0x72e0a8,0xf08fb8,0x8bb7ff,0xb69cff,0x6bd7ed,0xf0a36b,0x8dd3a8,0xffd16f];
const hairPalette=[0x243d70,0x5d3a70,0x9a5d35,0x263d48,0x4c6b58,0x783f5c,0x3b4d7a,0x654d82,0x28616c,0x8a5938,0x426b57,0x8a7040];
const coatPalette=[0x315f91,0x624b91,0x277c73,0x94643b,0x286b54,0x85445c,0x3d5c91,0x72558e,0x286e80,0x805334,0x3d7558,0x80652f];
const stations=[],people=[],rings=[],pickables=[];
function limb(parent,r1,r2,len,color,x,y,z){const pivot=new THREE.Group();pivot.position.set(x,y,z);parent.add(pivot);const mesh=new THREE.Mesh(new THREE.CylinderGeometry(r2,r1,len,7),mat(color,.72));mesh.position.y=-len/2;pivot.add(mesh);return pivot}
function makePerson(parent,index,color){
 const root=new THREE.Group();parent.add(root);const body=new THREE.Group();root.add(body);
 const skin=0xffd3bd;
 const torso=new THREE.Mesh(new THREE.CapsuleGeometry(.25,.42,3,7),mat(coatPalette[index%12],.62));torso.position.y=.98;body.add(torso);
 const neck=new THREE.Mesh(new THREE.CylinderGeometry(.075,.09,.15,7),mat(skin));neck.position.y=1.34;body.add(neck);
 const head=new THREE.Mesh(new THREE.SphereGeometry(.265,10,8),mat(skin));head.position.y=1.61;body.add(head);
 const hair=new THREE.Mesh(new THREE.SphereGeometry(.28,10,7,0,Math.PI*2,0,Math.PI*.64),mat(hairPalette[index%12]));hair.position.set(0,1.7,-.025);body.add(hair);
 const visor=new THREE.Mesh(new THREE.BoxGeometry(.31,.055,.035),new THREE.MeshStandardMaterial({color:color,emissive:color,emissiveIntensity:.38,roughness:.25}));visor.position.set(0,1.63,.245);body.add(visor);
 const arms=[limb(body,.075,.06,.38,skin,-.31,1.12,0),limb(body,.075,.06,.38,skin,.31,1.12,0)];
 const sleeves=[limb(body,.105,.09,.32,coatPalette[index%12],-.29,1.13,0),limb(body,.105,.09,.32,coatPalette[index%12],.29,1.13,0)];
 const legs=[limb(body,.105,.09,.43,0x253953,-.12,.47,0),limb(body,.105,.09,.43,0x253953,.12,.47,0)];
 const badge=new THREE.Mesh(new THREE.SphereGeometry(.055,7,6),new THREE.MeshBasicMaterial({color}));badge.position.set(.18,1.05,.2);body.add(badge);
 return {root,body,arms,sleeves,legs,phase:index*1.31,mode:"idle",color};
}
function buildStation(dept,index){
 const x=-10.2+(index%4)*6.8,z=-7+Math.floor(index/4)*7;
 const color=palette[index%palette.length],group=new THREE.Group();group.position.set(x,0,z);scene.add(group);
 const pad=new THREE.Mesh(new THREE.CylinderGeometry(2.55,2.7,.12,6),mat(0x142a43,.48,.3));pad.position.y=.02;group.add(pad);
 const rim=new THREE.Mesh(new THREE.TorusGeometry(2.35,.025,6,48),new THREE.MeshBasicMaterial({color,transparent:true,opacity:.65}));rim.rotation.x=Math.PI/2;rim.position.y=.1;group.add(rim);
 addBox(group,1.5,.13,.75,0x294765,0,.62,.45);addBox(group,1.35,.06,.62,0x081525,0,.72,.45);
 addBox(group,.92,.72,.07,color,0,1.18,-.35,.28);addBox(group,.78,.53,.035,0x09192a,0,1.18,-.30,.2);
 const monitorGlow=new THREE.Mesh(new THREE.PlaneGeometry(.68,.42),new THREE.MeshBasicMaterial({color,transparent:true,opacity:.32}));monitorGlow.position.set(0,1.18,-.275);group.add(monitorGlow);
 const person=makePerson(group,index,color);person.root.position.set(0,0,1.35);
 const name=makeLabel(dept.name||dept.title||dept.id,color.toString(16).padStart(6,"0"));name.position.set(0,2.55,-.05);group.add(name);
 const number=new THREE.Mesh(new THREE.TorusGeometry(.43,.025,6,32),new THREE.MeshBasicMaterial({color,transparent:true,opacity:.75}));number.rotation.x=Math.PI/2;number.position.set(0,.14,1.35);group.add(number);
 group.userData.department=dept;group.userData.index=index;
 stations.push({group,person,dept,index,x,z,color,ring:number});
 pickables.push(pad,group);
 return stations[stations.length-1];
}
let departments=[],tasks=[],runs=[],overview=null,selectedIndex=-1,refreshing=false,lastSync=0;
function setSelected(index){
 selectedIndex=index;
 const selected=stations[index];if(!selected)return;
 const d=selected.dept;
 const ownTasks=tasks.filter(t=>t.department===d.id);
 const activeRuns=runs.filter(r=>ownTasks.some(t=>t.id===r.task_id)&&["queued","running","in_progress"].includes(String(r.status).toLowerCase()));
 const queued=ownTasks.filter(t=>String(t.status).toLowerCase()==="queued").length;
 const completed=ownTasks.filter(t=>String(t.status).toLowerCase()==="completed").length;
 const failed=ownTasks.filter(t=>String(t.status).toLowerCase()==="failed").length;
 document.getElementById("officeSelected").innerHTML="<strong>"+escapeHtml(d.name||d.id)+" · "+(d.specialist_count??0)+" catalogued roles</strong><span>"+activeRuns.length+" active run(s) · "+queued+" queued task(s) · "+completed+" completed · "+failed+" failed. Roles are invoked on demand through the shared worker.</span>";
 document.querySelectorAll(".office-department").forEach((el,i)=>el.setAttribute("aria-pressed",i===index?"true":"false"));
 target.set(selected.x,0,selected.z);distance=Math.min(distance,17);
}
function escapeHtml(s){return String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function renderDepartmentCards(){
 const root=document.getElementById("officeDepartmentGrid");
 root.innerHTML=departments.map((d,i)=>{
 const own=tasks.filter(t=>t.department===d.id),active=own.filter(t=>["running","in_progress"].includes(String(t.status).toLowerCase())).length;
 const queued=own.filter(t=>String(t.status).toLowerCase()==="queued").length;
 const completed=own.filter(t=>String(t.status).toLowerCase()==="completed").length;
 const state=active?"Active task":queued?"Queued":"On-demand pool";
 return '<button class="office-department" type="button" data-office-index="'+i+'" aria-pressed="'+(selectedIndex===i)+'"><strong>'+escapeHtml(d.name||d.id)+'</strong><span>'+((d.specialist_count??0))+' catalogued roles · '+own.length+' saved tasks</span><span class="office-state">'+state+' · '+completed+' completed</span></button>';
 }).join("");
 root.querySelectorAll("[data-office-index]").forEach(el=>el.addEventListener("click",()=>setSelected(Number(el.dataset.officeIndex))));
}
async function refresh(){
 if(refreshing)return;refreshing=true;
 try{
  const [deptData,taskData,runData,overviewData]=await Promise.all(["/company/departments","/tasks","/agent-runs","/company/overview"].map(url=>api(url)));
  const nextDepartments=deptData.departments||[];
  if(!stations.length){
   departments=nextDepartments;
   if(!departments.length)throw new Error("The AIOS department registry returned no departments.");
   departments.forEach(buildStation);
  }else{departments=nextDepartments;stations.forEach((s,i)=>{s.dept=departments[i]||s.dept;s.group.userData.department=s.dept})}
  tasks=taskData||[];runs=runData||[];overview=overviewData;lastSync=Date.now();
  stations.forEach((s,i)=>{
   const own=tasks.filter(t=>t.department===s.dept.id);
   const activeIds=new Set(runs.filter(r=>["queued","running","in_progress"].includes(String(r.status).toLowerCase())).map(r=>r.task_id));
   const active=own.some(t=>activeIds.has(t.id));
   const queued=own.some(t=>String(t.status).toLowerCase()==="queued");
   s.person.mode=active?"working":queued?"queued":"idle";
   s.ring.material.color.setHex(active?0x55e0ae:queued?0xffd27b:s.color);
  });
  document.getElementById("officeConnection").textContent=overview.agent_worker_running?"API connected · agent worker online":"API connected · worker idle/unavailable";
  document.getElementById("officeConnection").className="pill "+(overview.agent_worker_running?"good":"warn");
  const activeCount=runs.filter(r=>["queued","running","in_progress"].includes(String(r.status).toLowerCase())).length;
  document.getElementById("officeActivity").textContent=departments.length+" departments · "+tasks.length+" saved tasks · "+activeCount+" active/queued runs";
  renderDepartmentCards();if(selectedIndex>=0)setSelected(selectedIndex);
 }catch(e){
  document.getElementById("officeConnection").textContent="Live data unavailable";
  document.getElementById("officeConnection").className="pill warn";
  document.getElementById("officeActivity").textContent=e.message;
 }finally{refreshing=false}
}
const raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2();
let drag=null,dragged=0,pointers=new Map(),pinchStart=0,distStart=distance;
canvas.addEventListener("pointerdown",e=>{canvas.setPointerCapture(e.pointerId);pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});drag={x:e.clientX,y:e.clientY};dragged=0;if(pointers.size===2){const p=[...pointers.values()];pinchStart=Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y);distStart=distance}});
canvas.addEventListener("pointermove",e=>{
 if(!pointers.has(e.pointerId))return;
 const prev=pointers.get(e.pointerId),dx=e.clientX-prev.x,dy=e.clientY-prev.y;dragged+=Math.abs(dx)+Math.abs(dy);
 pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
 if(pointers.size===2){const p=[...pointers.values()],d=Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y);if(pinchStart>0)distance=Math.max(17,Math.min(48,distStart*pinchStart/Math.max(d,1)))}
 else{az-=dx*.006;polar=Math.max(.48,Math.min(1.28,polar+dy*.004))}
});
function updateCamera(){camera.position.set(target.x+distance*Math.sin(az)*Math.cos(polar),target.y+distance*Math.sin(polar),target.z+distance*Math.cos(az)*Math.cos(polar));camera.lookAt(target)}
canvas.addEventListener("pointerup",e=>{
 pointers.delete(e.pointerId);if(dragged<9){const rect=canvas.getBoundingClientRect();pointer.set((e.clientX-rect.left)/rect.width*2-1,-((e.clientY-rect.top)/rect.height*2-1));raycaster.setFromCamera(pointer,camera);const hits=raycaster.intersectObjects(stations.map(s=>s.group),true);if(hits.length){let o=hits[0].object;while(o&&!o.userData.department)o=o.parent;if(o?.userData?.index!==undefined)setSelected(o.userData.index)}}if(!pointers.size){drag=null;pinchStart=0}
});
canvas.addEventListener("pointercancel",e=>{pointers.delete(e.pointerId);if(!pointers.size)drag=null});
canvas.addEventListener("wheel",e=>{distance=Math.max(17,Math.min(48,distance*(1+e.deltaY*.001)));e.preventDefault()},{passive:false});
document.getElementById("officeRefresh").addEventListener("click",refresh);
document.getElementById("officeReset").addEventListener("click",()=>{az=.12;polar=.92;distance=31;target.set(0,0,0);selectedIndex=-1;document.getElementById("officeSelected").innerHTML="<strong>Company overview</strong><span>Select any department workspace to inspect its current task counts and role availability.</span>";document.querySelectorAll(".office-department").forEach(el=>el.setAttribute("aria-pressed","false"))});
const resize=()=>{const w=canvas.clientWidth,h=canvas.clientHeight;if(w&&h){renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix()}};new ResizeObserver(resize).observe(canvas);resize();
function animate(t){
 requestAnimationFrame(animate);const time=t*.001;
 stations.forEach((s,i)=>{const p=s.person,active=p.mode==="working",queued=p.mode==="queued";p.body.position.y=Math.sin(time*2+p.phase)*.025;p.body.rotation.y=Math.sin(time*.7+p.phase)*.035;p.arms.forEach((a,j)=>{a.rotation.z=active?Math.sin(time*8+p.phase+j)*.18+(j===0?-.28:.28):Math.sin(time*1.4+p.phase+j)*.045});p.sleeves.forEach((a,j)=>{a.rotation.z=active?Math.sin(time*8+p.phase+j)*.15+(j===0?-.24:.24):Math.sin(time*1.4+p.phase+j)*.04});p.legs.forEach((l,j)=>{l.rotation.x=active?Math.sin(time*4+p.phase+j)*.025:0});s.ring.material.opacity=.42+Math.sin(time*2+i)*.15;if(queued)s.ring.material.opacity=.45+Math.sin(time*5+i)*.3});
 coreRing.rotation.z=time*.12;updateCamera();renderer.render(scene,camera);
 document.getElementById("officeClock").textContent="SYNC "+new Date().toLocaleTimeString();
 if(Date.now()-lastSync>10000)refresh();
}
requestAnimationFrame(animate);refresh();
fallback.style.display="none";
})().catch(e=>{const f=document.getElementById("officeFallback");if(f)f.textContent="3D office could not start: "+e.message;});
</script>
<script>
(function(){
 const formData=form=>Object.fromEntries(new FormData(form).entries());
 const send=async(path,body)=>api(path,{method:"POST",body:JSON.stringify(body)});
 const money=(amount,currency)=>amount==null?"—":Number(amount).toLocaleString(undefined,{maximumFractionDigits:2})+" "+currency;
 async function loadSocialOAuth(){
  const root=$("socialOAuthRows");if(!root)return;
  try{
   const [status,connected]=await Promise.all([api("/business-integrations/social/status"),api("/business-integrations/"+encodeURIComponent($("businessScope").value))]);
   const linked=new Set((connected.integrations||[]).map(x=>x.provider));
   root.innerHTML=(status.providers||[]).map(p=>'<article class="metric"><strong style="font-size:16px">'+esc(p.label)+'</strong><span>'+(linked.has(p.provider)?'<span class="good">Account linked to this business</span>':p.app_configured?'<span class="warn">Ready for owner sign-in</span>':'<span class="warn">Developer app setup required</span>')+'</span><span class="small">Read-only scopes: '+esc((p.read_only_scopes||[]).join(", "))+'</span>'+(p.reason?'<span class="small">'+esc(p.reason)+'</span>':'')+'<button class="secondary" type="button" data-social-provider="'+esc(p.provider)+'" '+(!p.app_configured||linked.has(p.provider)?'disabled':'')+'>'+(linked.has(p.provider)?'Connected':p.app_configured?'Connect account':'Not configured')+'</button></article>').join("");
  }catch(e){root.textContent="Social connection status unavailable: "+e.message}
 }
 $("socialOAuthRows")?.addEventListener("click",async e=>{
  const button=e.target.closest("[data-social-provider]");if(!button)return;
  const provider=button.dataset.socialProvider;button.disabled=true;$("socialOAuthMessage").textContent="Preparing secure "+provider+" authorization…";
  try{const result=await api("/business-integrations/"+encodeURIComponent($("businessScope").value)+"/social/"+encodeURIComponent(provider)+"/start",{method:"POST",body:"{}"});window.location.assign(result.authorize_url)}
  catch(err){$("socialOAuthMessage").textContent="Could not start authorization: "+err.message;button.disabled=false}
 });
 $("connectPlayerAuctions")?.addEventListener("click",async()=>{
  const apiKey=$("playerAuctionsKey").value.trim(),secret=$("playerAuctionsSecret").value;
  if(!apiKey||!secret){$("marketplaceMessage").textContent="Enter both PlayerAuctions API key and API secret.";return}
  const button=$("connectPlayerAuctions");button.disabled=true;$("marketplaceMessage").textContent="Verifying PlayerAuctions seller API with a signed read-only offer-list request…";
  try{
   const result=await api("/business-integrations/"+encodeURIComponent($("businessScope").value)+"/playerauctions/connect",{method:"POST",body:JSON.stringify({secret,config:{api_key:apiKey}})});
   $("playerAuctionsKey").value="";$("playerAuctionsSecret").value="";
   $("marketplaceMessage").textContent="PlayerAuctions connected: "+result.verification.capability+". Sampled offers: "+result.verification.sampled_offers+". No marketplace data changed.";
   await loadBusinessIntegrations();
  }catch(e){$("marketplaceMessage").textContent="PlayerAuctions connection failed; credentials were not saved: "+e.message}
  finally{button.disabled=false}
 });
 async function loadBusinessIntegrations(){
  try{
   const scope=encodeURIComponent($("businessScope").value);
   const data=await api("/business-integrations/"+scope);
   $("integrationRows").innerHTML=(data.integrations||[]).map(x=>'<div class="toolbar" style="justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--line)"><span>'+esc(x.provider)+' · <span class="good">Encrypted credential stored</span></span><span class="toolbar">'+(["wordpress","woocommerce","playerauctions","etsy","meta","tiktok","youtube","pinterest","reddit","x"].includes(x.provider)?'<button class="secondary" data-provider="'+esc(x.provider)+'" onclick="testBusinessIntegration(this.dataset.provider)">Test</button>':'')+'<button class="secondary" data-provider="'+esc(x.provider)+'" onclick="deleteBusinessIntegration(this.dataset.provider)">Delete</button></span></div>').join("")||"No platform accounts connected to this business.";
  }catch(e){$("integrationRows").textContent=e.message}
  await loadSocialOAuth();
 }
 window.testBusinessIntegration=async provider=>{
  $("integrationMessage").textContent="Testing saved "+provider+" credentials with a read-only request…";
  try{const result=await api("/business-integrations/"+encodeURIComponent($("businessScope").value)+"/"+encodeURIComponent(provider)+"/test",{method:"POST"});$("integrationMessage").textContent="Connected and verified: "+provider+" · "+(result.account||result.site_url)+" · "+result.capability+"."}
  catch(e){$("integrationMessage").textContent="Connection test failed: "+e.message}
 };
 window.deleteBusinessIntegration=async provider=>{
  if(!confirm("Delete the stored "+provider+" credential for "+$("businessScope").value+"?"))return;
  try{await api("/business-integrations/"+encodeURIComponent($("businessScope").value)+"/"+encodeURIComponent(provider),{method:"DELETE"});$("integrationMessage").textContent="Stored credentials deleted.";await loadBusinessIntegrations()}catch(e){$("integrationMessage").textContent=e.message}
 };
 function updateIntegrationFields(){
  const woo=$("integrationProvider").value==="woocommerce";
  $("wordpressFields").style.display=woo?"none":"flex";
  $("woocommerceFields").style.display=woo?"flex":"none";
 }
 $("integrationProvider").addEventListener("change",updateIntegrationFields);
 $("saveBusinessIntegration").addEventListener("click",async()=>{
  const provider=$("integrationProvider").value;
  const secret=provider==="wordpress"?$("integrationSecret").value:$("integrationSecretWoo").value;
  const config={site_url:$("integrationSiteUrl").value.trim()};
  if(provider==="wordpress")config.username=$("integrationUsername").value.trim();
  else config.consumer_key=$("integrationConsumerKey").value.trim();
  if(!config.site_url||!secret||(provider==="wordpress"&&!config.username)||(provider==="woocommerce"&&!config.consumer_key)){
   $("integrationMessage").textContent="Enter the site URL and all required account credentials.";return;
  }
  const button=$("saveBusinessIntegration");button.disabled=true;
  $("integrationMessage").textContent="Verifying account access. Only a read-only GET request will be sent…";
  try{
   const result=await api("/business-integrations/"+encodeURIComponent($("businessScope").value)+"/"+encodeURIComponent(provider)+"/connect",{method:"POST",body:JSON.stringify({secret,config})});
   $("integrationSecret").value="";$("integrationSecretWoo").value="";
   $("integrationMessage").textContent="Account connected and verified: "+provider+" · "+(result.verification.account||result.verification.site_url)+". Credentials encrypted at rest.";
   await loadBusinessIntegrations();
  }catch(e){$("integrationMessage").textContent="Connection failed; credentials were not saved: "+e.message}
  finally{button.disabled=false}
 });
 updateIntegrationFields();
 async function loadBusiness(){
  try{
   const businessId=$("businessScope").value;const scope="?business_id="+encodeURIComponent(businessId);const [summary,customers,investors,expenses,revenue]=await Promise.all([api("/business/summary"+scope),api("/business/customers"+scope),api("/business/investors"+scope),api("/business/expenses"+scope),api("/business/revenue"+scope)]);
   const verified=revenue.filter(x=>x.verified);
   const mtd=(summary.verified_revenue_mtd_by_currency||[]).map(x=>money(x.total,x.currency)).join(" / ")||"0.00";
   $("businessSummary").innerHTML='<div class="metric"><strong>'+summary.customers+'</strong><span>Customers</span></div><div class="metric"><strong>'+esc(mtd)+'</strong><span>Verified revenue · MTD</span></div><div class="metric"><strong>'+summary.expenses_awaiting_owner_approval+'</strong><span>Expenses awaiting approval</span></div>';
   $("customerRows").innerHTML=customers.map(x=>'<tr><td>'+esc(x.title)+'</td><td>'+esc(x.contact||"—")+'</td><td>'+esc(x.notes||"—")+'</td><td>'+date(x.created_at)+'</td></tr>').join("")||'<tr><td colspan="4">No customers recorded.</td></tr>';
   $("investorRows").innerHTML=investors.map(x=>'<tr><td>'+esc(x.name)+'</td><td>'+esc(x.organization||"—")+'</td><td>'+esc(x.contact||"—")+'</td><td>'+esc(x.stage)+'</td><td>'+esc(x.notes||"—")+'</td></tr>').join("")||'<tr><td colspan="5">No investor records yet.</td></tr>';
   const rows=[...expenses,...revenue].sort((a,b)=>b.created_at.localeCompare(a.created_at));
   $("ledgerRows").innerHTML=rows.map(x=>'<tr><td>'+esc(x.record_type)+'</td><td>'+esc(x.title)+'</td><td>'+money(x.amount,x.currency)+'</td><td>'+esc(x.status)+'</td><td>'+date(x.created_at)+'</td></tr>').join("")||'<tr><td colspan="5">No ledger entries yet.</td></tr>';
  }catch(e){$("businessMessage").textContent=e.message}
 }
 $("investorForm").addEventListener("submit",async e=>{e.preventDefault();try{await send("/business/investors",{...formData(e.currentTarget),business_id:$("businessScope").value});e.currentTarget.reset();$("businessMessage").textContent="Investor record saved.";await loadBusiness()}catch(err){$("businessMessage").textContent=err.message}});
 ["customer","revenue","expense"].forEach(kind=>{
  const form=$(kind+"Form");form.addEventListener("submit",async e=>{e.preventDefault();const data={...formData(form),business_id:$("businessScope").value};if(kind==="revenue")data.verified_payment=form.elements.verified_payment.checked;try{await send("/business/"+(kind==="customer"?"customers":(kind==="expense"?"expenses":"revenue")),data);form.reset();$("businessMessage").textContent=kind==="expense"?"Expense recorded for owner approval.":kind==="revenue"?"Revenue record saved; only verified receipts count.":"Customer saved.";await loadBusiness()}catch(err){$("businessMessage").textContent=err.message}});
 });
 async function loadAssets(){
  try{
   const [assets,offers]=await Promise.all([api("/code-assets"),api("/code-assets/license-offers")]);
   $("assetCount").textContent=assets.length;$("offerCount").textContent=offers.length;
   const eligible=assets.filter(a=>["verified","owner_confirmed"].includes(a.ownership_status)&&["passed","reviewed_clear"].includes(a.dependency_review));
   $("licenseAsset").innerHTML='<option value="">Select eligible asset</option>'+eligible.map(a=>'<option value="'+esc(a.id)+'">'+esc(a.name)+'</option>').join("");
   $("assetRows").innerHTML=assets.map(a=>'<tr><td>'+esc(a.name)+'</td><td>'+esc(a.repository_url||"—")+'<br>'+esc(a.path||"")+'</td><td>'+esc(a.ownership_status)+'</td><td>'+esc(a.license)+'</td><td>'+esc(a.dependency_review)+'</td><td>'+(a.token_estimate==null?"Not measured":Number(a.token_estimate).toLocaleString())+' <small>'+esc(a.token_method)+'</small></td></tr>').join("")||'<tr><td colspan="6">No assets registered.</td></tr>';
   $("offerRows").innerHTML=offers.map(o=>'<tr><td>'+esc(o.asset_name||o.asset_id)+'</td><td>'+esc(o.buyer)+'</td><td>'+esc(o.terms)+'</td><td>'+esc(o.status)+'</td><td>'+date(o.created_at)+'</td></tr>').join("")||'<tr><td colspan="5">No licensing offers.</td></tr>';
  }catch(e){$("assetMessage").textContent=e.message}
 }
 $("assetForm").addEventListener("submit",async e=>{e.preventDefault();const data=formData(e.currentTarget);data.token_estimate=data.token_estimate?Number(data.token_estimate):null;try{await send("/code-assets",data);e.currentTarget.reset();$("assetMessage").textContent="Asset registered. Ownership and dependency checks remain explicit.";await loadAssets()}catch(err){$("assetMessage").textContent=err.message}});
 $("licenseForm").addEventListener("submit",async e=>{e.preventDefault();try{const result=await send("/code-assets/license-offers",formData(e.currentTarget));$("assetMessage").textContent="Draft created. Owner approval request "+result.approval_id+" is pending. No code was shared.";e.currentTarget.reset();await loadAssets()}catch(err){$("assetMessage").textContent=err.message}});
 $("businessUnitForm")?.addEventListener("submit",async e=>{e.preventDefault();const form=e.currentTarget;const data=formData(form);try{const created=await api("/business-units",{method:"POST",body:JSON.stringify(data)});$("businessUnitMessage").textContent="Registered "+created.name+" as a separate business unit. No spending or publishing occurred.";form.reset();await loadBusinessUnits();["taskBusiness","researchBusiness","brainBusiness","businessScope"].forEach(id=>{const el=$(id);if(el)el.value=created.id});await Promise.all([loadOperations(),loadBusiness()]);}catch(err){$("businessUnitMessage").textContent=err.message}});
 $("ventureForm")?.addEventListener("submit",async e=>{e.preventDefault();try{const r=await api("/venture-opportunities",{method:"POST",body:JSON.stringify(formData(e.currentTarget))});$("ventureMessage").textContent="Opportunity added: "+r.title;e.currentTarget.reset();await loadVentureOpportunities()}catch(err){$("ventureMessage").textContent=err.message}});
$("ventureRows")?.addEventListener("click",async e=>{const button=e.target.closest("[data-v-action]");if(!button)return;const id=button.dataset.vId;const action=button.dataset.vAction;try{button.disabled=true;if(action==="research"){const r=await api("/venture-opportunities/"+encodeURIComponent(id)+"/research",{method:"POST",body:"{}"});$("ventureMessage").textContent="Research task queued: "+r.task.id+". Free-confirmed models only."}else if(action==="launch"){if(!confirm("Create this separate business unit? No spending or external actions will occur.")){button.disabled=false;return}const r=await api("/venture-opportunities/"+encodeURIComponent(id)+"/launch",{method:"POST",body:"{}"});$("ventureMessage").textContent="Created business unit "+r.business_unit.id;await loadBusinessUnits()}else{if(action==="launch_approved"&&!confirm("Approve launch planning? This does not spend money or publish anything.")){button.disabled=false;return}const notes=action==="launch_approved"?"Owner approved launch planning; business registration remains a separate action.":"Owner decision recorded.";await api("/venture-opportunities/"+encodeURIComponent(id)+"/decision",{method:"POST",body:JSON.stringify({decision:action,notes})});$("ventureMessage").textContent="Decision saved: "+action}await loadVentureOpportunities()}catch(err){$("ventureMessage").textContent=err.message;button.disabled=false}});
$("ventureAssessmentForm")?.addEventListener("submit",async e=>{e.preventDefault();const form=e.currentTarget;const ratings={};["demand","competition","economics","distribution","execution","risk"].forEach(k=>ratings[k]=Number(form.elements[k].value));const urls=form.elements.sources.value.split("\n").map(x=>x.trim()).filter(x=>x.startsWith("https://"));const evidence=urls.map(url=>({url,claim:"Source supplied for venture assessment"}));try{await api("/venture-opportunities/"+encodeURIComponent(form.elements.opportunity_id.value)+"/assessment",{method:"POST",body:JSON.stringify({assessment:{ratings,summary:form.elements.summary.value,source_urls:urls},evidence})});$("ventureMessage").textContent="Assessment saved. Score is provisional and depends on evidence quality.";form.reset();await loadVentureOpportunities()}catch(err){$("ventureMessage").textContent=err.message}});
const businessLink=document.querySelector('nav.main-nav a[data-view="business"]');businessLink?.addEventListener("click",loadBusiness);
 const assetsLink=document.querySelector('nav.main-nav a[data-view="code-assets"]');assetsLink?.addEventListener("click",loadAssets);
 try{await loadBusinessUnits()}catch(e){setApiHealth("Business registry unavailable","degraded")}
 if(location.hash==="#ventures")loadVentureOpportunities();
 if(location.hash==="#business"){loadBusiness();loadBusinessIntegrations();}if(location.hash==="#code-assets")loadAssets();
 window.addEventListener("hashchange",()=>{if(location.hash==="#business"){loadBusiness();loadBusinessIntegrations();}if(location.hash==="#ventures")loadVentureOpportunities();if(location.hash==="#code-assets")loadAssets()});
})();
</script>
</body></html>
"""

def owner_dashboard() -> HTMLResponse:
    return HTMLResponse(OWNER_HTML)
