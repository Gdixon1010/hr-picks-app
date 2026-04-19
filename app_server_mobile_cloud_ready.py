
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from pathlib import Path
import json
import datetime as dt
from hr_v40_2_json_export_ready import main as run_model_main

app = FastAPI()

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

def get_latest_json_file():
    files = sorted(
        OUTPUT_DIR.glob("HR_Hit_Drought_v40_appdata-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    return files[0] if files else None

def load_latest_data():
    latest_file = get_latest_json_file()
    if not latest_file:
        raise HTTPException(status_code=404, detail="No JSON file found in output folder")
    with open(latest_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["_meta"] = {
        "filename": latest_file.name,
        "modified": latest_file.stat().st_mtime,
        "path": str(latest_file),
    }
    return data

@app.get("/")
def home():
    return {
        "message": "HR app server v3 is running",
        "endpoints": ["/app", "/refresh-data", "/latest", "/final-card", "/games", "/research"]
    }

@app.post("/refresh-data")
def refresh_data():
    today = dt.date.today().strftime("%Y-%m-%d")
    run_model_main(2026, today)
    return {"status": "ok", "message": "Data refreshed", "date": today}

@app.get("/latest")
def latest():
    return JSONResponse(content=load_latest_data())

@app.get("/final-card")
def final_card():
    data = load_latest_data()
    return JSONResponse(content=data.get("final_card", {}))

@app.get("/games")
def games():
    data = load_latest_data()
    return JSONResponse(content=data.get("games", []))

@app.get("/research")
def research():
    data = load_latest_data()
    return JSONResponse(content=data.get("research", {}))


HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover" />
<title>HR Picks v4</title>
<style>
:root{--bg:#070b24;--panel:#121938;--panel2:#1a2248;--line:#3a4b9a;--text:#f2f4ff;--muted:#adb4da;--accent:#8ea2ff;--good:#45d483;--warn:#f2c66d}
*{box-sizing:border-box} body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:linear-gradient(180deg,#05091d 0%, #070b24 100%);color:var(--text)}
.wrap{max-width:980px;margin:0 auto;padding:22px 16px 48px} h1{font-size:32px;line-height:1.1;margin:12px 0 10px} .meta{color:var(--muted);font-size:16px;margin-bottom:18px}
.row{display:flex;gap:12px;flex-wrap:wrap}.btn{border:none;border-radius:18px;padding:18px 22px;background:var(--panel2);color:var(--text);font-size:15px;font-weight:700;border:1px solid #334181}.btn.primary{background:var(--accent);color:#fff}
.tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:18px 0 20px}.tab{text-align:center;padding:20px 10px;border-radius:22px;background:var(--panel);border:1px solid #334181;color:var(--text);font-size:17px;font-weight:800}.tab.active{outline:2px solid var(--accent)}
.section{display:none}.section.active{display:block}.card{background:rgba(18,25,56,.95);border:1px solid #2e3b7d;border-radius:26px;padding:18px 18px 16px;margin:14px 0}.eyebrow{font-size:14px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:800}.big{font-size:24px;font-weight:900;line-height:1.15;margin:4px 0}.mid{font-size:18px;color:var(--muted);margin:3px 0}.small{font-size:14px;color:var(--muted);margin-top:8px}.pill{width:56px;height:56px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#27326f;border:1px solid #3a4b9a;font-weight:900;font-size:28px}.flex{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.kv{margin-top:8px;color:var(--muted);font-size:15px}.notice{padding:14px 16px;background:#171f43;border:1px dashed #5066c7;border-radius:18px;color:var(--muted)}.game-title{font-size:22px;font-weight:900;line-height:1.2;margin:0 0 12px}.subtle{color:var(--muted);font-size:13px;text-transform:uppercase;letter-spacing:.08em;font-weight:800}.pickline{margin:8px 0 0;font-size:17px;line-height:1.4}.pickline strong{color:#fff}.hr{height:1px;background:#2a376f;margin:14px 0}
.panel{background:rgba(18,25,56,.95);border:1px solid #2e3b7d;border-radius:22px;margin:12px 0;overflow:hidden}.panel-head{padding:18px 18px;font-size:19px;font-weight:900;border-bottom:1px solid #28366e}.details-body{padding:0 12px 14px}
.tools{display:flex;gap:10px;flex-wrap:wrap;padding:12px}.tools input[type="text"], .tools input[type="number"], .tools select{background:#0f1532;color:#fff;border:1px solid #344281;border-radius:12px;padding:10px 12px;font-size:14px}
.table-wrap{overflow:auto;max-height:65vh}.filter-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:0 12px 12px}.filter-box{background:#0f1532;border:1px solid #344281;border-radius:16px;padding:10px 12px}.filter-title{font-size:12px;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}.check-list{display:grid;grid-template-columns:1fr;gap:6px;max-height:170px;overflow:auto;padding-right:4px}.check-item{display:flex;align-items:center;gap:8px;font-size:14px;color:#eef1ff}.check-item input{width:16px;height:16px}.action-row{display:flex;gap:10px;flex-wrap:wrap;padding:0 12px 12px}.mini-btn{background:#27326f;color:#fff;border:1px solid #4153a5;padding:10px 12px;border-radius:12px;font-weight:700}
table{width:100%;border-collapse:collapse;font-size:14px} th,td{padding:10px 12px;border-bottom:1px solid #28366e;vertical-align:top;text-align:left} th{color:#c8cff5;font-size:13px;cursor:pointer;position:sticky;top:0;background:#141c40} td{color:#eef1ff}
.badge{display:inline-block;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:800;background:#27326f;border:1px solid #4153a5;color:#fff}.empty{color:var(--muted);font-size:17px;padding:8px 2px}
@media (max-width:700px){.filter-grid{grid-template-columns:1fr}.big{font-size:18px}.game-title{font-size:18px}th,td{padding:8px 10px;font-size:13px}}
</style>
</head>
<body>
<div class="wrap">
  <h1>HR Picks</h1>
  <div class="meta" id="meta">Loading…</div>
  <div class="row">
    <button class="btn primary" onclick="reloadData()">Refresh Data on Server</button>
    <button class="btn" onclick="location.reload()">Reload App</button>
  </div>
  <div class="tabs">
    <button class="tab active" data-target="final-card">Final Card</button>
    <button class="tab" data-target="games">Games</button>
    <button class="tab" data-target="research">Research</button>
  </div>
  <section id="final-card" class="section active"></section>
  <section id="games" class="section"></section>
  <section id="research" class="section"></section>
</div>
<script>
let APPDATA=null; let RESEARCH_SORT={}; let RESEARCH_FILTER_STATE={}; let RESEARCH_OPEN_STATE={};
function nice(v){if(v===null||v===undefined||v==="") return "—"; return String(v)}
function fmtNum(v){if(v===null||v===undefined||v==="") return "—"; const n=Number(v); return Number.isNaN(n)?String(v):n.toFixed(3).replace(/\.000$/,'')}
function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function tabSetup(){document.querySelectorAll('.tab').forEach(btn=>{btn.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.section').forEach(x=>x.classList.remove('active'));btn.classList.add('active');document.getElementById(btn.dataset.target).classList.add('active')}})}
async function loadData(){const res=await fetch('/latest'); APPDATA=await res.json(); renderAll()}
async function reloadData(){
  document.getElementById('meta').textContent='Refreshing server data…';
  const res = await fetch('/refresh-data', {method:'POST'});
  if(!res.ok){
    document.getElementById('meta').textContent='Refresh failed';
    return;
  }
  await loadData();
}
function renderMeta(){const d=APPDATA.date||'—'; const loaded=new Date().toLocaleTimeString(); const file=APPDATA._meta?.filename||''; document.getElementById('meta').textContent=`Date: ${d} • Loaded ${loaded} • ${file}`}
function renderFinalCard(){const el=document.getElementById('final-card'); const plays=APPDATA.final_card?.plays||[]; if(!plays.length){el.innerHTML=`<div class="notice">No final card plays qualified today.</div>`; return}
const grouped={Moneyline:[], '1+ Hit':[], HR:[], 'K Prop':[]}; plays.forEach(p=>{if(!grouped[p.bet_type]) grouped[p.bet_type]=[]; grouped[p.bet_type].push(p)});
function block(title, items, emptyMsg){if(!items.length){return `<div class="card"><div class="eyebrow">${esc(title)}</div><div class="empty">${esc(emptyMsg)}</div></div>`} return items.map(p=>`<div class="card"><div class="flex"><div style="flex:1"><div class="eyebrow">${esc(p.slot)} · ${esc(p.bet_type)}</div><div class="big">${esc(p.pick)}</div><div class="mid">${esc(p.team)} vs ${esc(p.opponent)}</div><div class="kv">${esc(p.why_it_made_the_card)}</div><div class="small">Source: ${esc(p.source_tab)}</div></div><div class="pill">${esc(p.confidence||'')}</div></div></div>`).join('')}
el.innerHTML=`${block('Moneyline', grouped['Moneyline']||[], 'No qualified moneyline play today.')}${block('Hit Picks', grouped['1+ Hit']||[], 'No qualified hit picks today.')}${block('HR Picks', grouped['HR']||[], 'No qualified HR picks today.')}${block('K Prop', grouped['K Prop']||[], 'No qualified K prop today.')}`}
function buildGameCards(){const games=APPDATA.games||[]; const topPicks=APPDATA.research?.top_picks||[]; const pitcherVals=APPDATA.research?.pitcher_line_value||[]; return games.map(g=>{let hits=Array.isArray(g.top_hit_picks)?[...g.top_hit_picks]:[]; let hrs=Array.isArray(g.top_hr_picks)?[...g.top_hr_picks]:[]; const teams=[]; if(g.ml_lean?.team) teams.push(g.ml_lean.team); if(g.ml_lean?.opponent) teams.push(g.ml_lean.opponent); if(!hits.length){hits=topPicks.filter(r=>r.type==='HIT'&&teams.includes(r.teamName)).sort((a,b)=>(Number(b.Hit_score||0)-Number(a.Hit_score||0))).slice(0,2).map(r=>({playerName:r.playerName,teamName:r.teamName,Hit_score:r.Hit_score,lineup_status:r.lineup_status,batting_order_slot:r.batting_order_slot}))} if(!hrs.length){hrs=topPicks.filter(r=>r.type==='HR'&&teams.includes(r.teamName)).sort((a,b)=>(Number(b.HR_score||0)-Number(a.HR_score||0))).slice(0,2).map(r=>({playerName:r.playerName,teamName:r.teamName,HR_score:r.HR_score,lineup_status:r.lineup_status,batting_order_slot:r.batting_order_slot}))} let k=g.top_k_pick; if(!k&&teams.length){const p=pitcherVals.filter(r=>teams.includes(r.teamName)).sort((a,b)=>Number(b.projected_k_mid||0)-Number(a.projected_k_mid||0))[0]; if(p){k=p}} return {...g, top_hit_picks:hits, top_hr_picks:hrs, top_k_pick:k}})}
function renderGames(){const el=document.getElementById('games'); const cards=buildGameCards(); if(!cards.length){el.innerHTML=`<div class="notice">No game cards available.</div>`; return} el.innerHTML=cards.map(g=>{const ml=g.ml_lean||{}; const hits=g.top_hit_picks||[]; const hrs=g.top_hr_picks||[]; const k=g.top_k_pick||null; return `<div class="card"><div class="game-title">${esc(g.game)}</div><div class="subtle">Model Lean</div><div class="pickline"><strong>${esc(ml.team||'No side')}</strong> vs ${esc(ml.opponent||'—')}</div><div class="kv">Model edge: ${fmtNum(ml.edge_vs_opponent)} · Model note: ${esc(ml.recommended_play||'—')}</div><div class="hr"></div><div class="subtle">Top Hit Picks</div>${hits.length?hits.map(p=>`<div class="pickline"><strong>${esc(p.playerName)}</strong> · ${esc(p.teamName)} · Hit score ${fmtNum(p.Hit_score)}</div>`).join(''):`<div class="empty">No qualified hit picks shown for this game.</div>`}<div class="hr"></div><div class="subtle">Top HR Picks</div>${hrs.length?hrs.map(p=>`<div class="pickline"><strong>${esc(p.playerName)}</strong> · ${esc(p.teamName)} · HR score ${fmtNum(p.HR_score)}</div>`).join(''):`<div class="empty">No qualified HR picks shown for this game.</div>`}<div class="hr"></div><div class="subtle">Top K Pick</div>${k?`<div class="pickline"><strong>${esc(k.pitcherName||'—')}</strong> · ${esc(k.teamName||'—')} · ${esc(k.recommended_k_action||'—')}</div><div class="kv">Projected Ks: ${fmtNum(k.projected_k_floor)}-${fmtNum(k.projected_k_ceiling)} · Max line: ${nice(k.max_playable_k_line)}</div>`:`<div class="empty">No K pick for this game.</div>`}</div>`}).join('')}
function getResearchTableColumns(rows){const set=new Set(); rows.slice(0,50).forEach(r=>Object.keys(r).forEach(k=>set.add(k))); return Array.from(set)}
function sortRows(rows,key,dir){const copy=[...rows]; copy.sort((a,b)=>{const av=a[key], bv=b[key]; const an=Number(av), bn=Number(bv); const aNum=!Number.isNaN(an)&&av!==null&&av!==""; const bNum=!Number.isNaN(bn)&&bv!==null&&bv!==""; let cmp=0; if(aNum&&bNum) cmp=an-bn; else cmp=String(av??"").localeCompare(String(bv??"")); return dir==='asc'?cmp:-cmp}); return copy}
function getUniqueValues(rows,key){const vals=new Set(); (rows||[]).forEach(r=>{const v=r[key]; if(v!==null&&v!==undefined&&String(v).trim()!=='') vals.add(String(v))}); return Array.from(vals).sort((a,b)=>a.localeCompare(b))}
function initFilterState(name, rows){if(RESEARCH_FILTER_STATE[name]) return; RESEARCH_FILTER_STATE[name]={search:'', teams:[], statuses:[], parks:[], opps:[], overdueOnly:false, minDrought:''}; if(name==='top_picks') RESEARCH_OPEN_STATE[name]=true;}
function updateTextFilter(name, value){initFilterState(name,[]); RESEARCH_FILTER_STATE[name].search=value; renderOneResearchTable(name, APPDATA.research?.[name]||[])}
function updateCheckArray(name,key,val,checked){initFilterState(name,[]); const arr=RESEARCH_FILTER_STATE[name][key]; const idx=arr.indexOf(val); if(checked && idx===-1) arr.push(val); if(!checked && idx!==-1) arr.splice(idx,1); renderOneResearchTable(name, APPDATA.research?.[name]||[])}
function updateSimpleFilter(name,key,val){initFilterState(name,[]); RESEARCH_FILTER_STATE[name][key]=val; renderOneResearchTable(name, APPDATA.research?.[name]||[])}
function clearFilters(name){initFilterState(name,[]); RESEARCH_FILTER_STATE[name]={search:'', teams:[], statuses:[], parks:[], opps:[], overdueOnly:false, minDrought:''}; RESEARCH_SORT[name]=RESEARCH_SORT[name]||{}; renderResearch()}
function toggleSort(name,key){if(!RESEARCH_SORT[name]||RESEARCH_SORT[name].key!==key){RESEARCH_SORT[name]={key,dir:'desc'}}else{RESEARCH_SORT[name].dir=RESEARCH_SORT[name].dir==='desc'?'asc':'desc'} renderOneResearchTable(name, APPDATA.research?.[name]||[])}
function applyAdvancedFilters(name, rows){let data=[...rows]; const f=RESEARCH_FILTER_STATE[name]||{}; const q=(f.search||'').toLowerCase().trim(); if(q){data=data.filter(r=>JSON.stringify(r).toLowerCase().includes(q))} if(['hr_drought','hit_drought'].includes(name)){ if(f.teams?.length) data=data.filter(r=>f.teams.includes(String(r.teamName||''))); if(f.statuses?.length) data=data.filter(r=>f.statuses.includes(String(r.status||''))); if(f.parks?.length) data=data.filter(r=>f.parks.includes(String(r.park_favorability||''))); if(f.opps?.length) data=data.filter(r=>f.opps.includes(String(r.opponent_pitcher_pick_type||''))); if(f.overdueOnly) data=data.filter(r=>String(r.status||'').toLowerCase().includes('overdue')); if(f.minDrought!==''){const threshold=Number(f.minDrought); const col=name==='hr_drought'?'current_games_without_hr':'current_games_without_hit'; if(!Number.isNaN(threshold)) data=data.filter(r=>Number(r[col]||0)>=threshold)}} return data}
function buildCheckboxGroup(name,key,title,vals){const state=RESEARCH_FILTER_STATE[name]||{}; const selected=state[key]||[]; return `<div class="filter-box"><div class="filter-title">${esc(title)}</div><div class="check-list">${vals.map(v=>`<label class="check-item"><input type="checkbox" ${selected.includes(v)?'checked':''} onchange="updateCheckArray('${name}','${key}', ${JSON.stringify(v)}, this.checked)"><span>${esc(v)}</span></label>`).join('') || '<div class="empty">No options</div>'}</div></div>`}
function buildAdvancedFilterUI(name, rows){if(!['hr_drought','hit_drought'].includes(name)) return ''; initFilterState(name, rows); const state=RESEARCH_FILTER_STATE[name]; const teams=getUniqueValues(rows,'teamName'); const statuses=getUniqueValues(rows,'status'); const parks=getUniqueValues(rows,'park_favorability'); const opps=getUniqueValues(rows,'opponent_pitcher_pick_type'); const label=name==='hr_drought'?'Min HR Drought':'Min Hit Drought'; return `<div class="tools"><input type="text" placeholder="Search this table" value="${esc(state.search)}" oninput="updateTextFilter('${name}', this.value)"><label class="check-item filter-box" style="max-width:220px"><input type="checkbox" ${state.overdueOnly?'checked':''} onchange="updateSimpleFilter('${name}','overdueOnly', this.checked)"><span>Overdue only</span></label><input type="number" min="0" placeholder="${label}" value="${esc(state.minDrought)}" oninput="updateSimpleFilter('${name}','minDrought', this.value)"></div><div class="filter-grid">${buildCheckboxGroup(name,'teams','Teams',teams)}${buildCheckboxGroup(name,'statuses','Status',statuses)}${buildCheckboxGroup(name,'parks','Park',parks)}${buildCheckboxGroup(name,'opps','Opponent Pitcher Type',opps)}</div><div class="action-row"><button class="mini-btn" onclick="clearFilters('${name}')">Clear Filters</button></div>`}
function renderOneResearchTable(name, rows){initFilterState(name, rows); const sortKey=RESEARCH_SORT[name]?.key||null; const sortDir=RESEARCH_SORT[name]?.dir||'desc'; let data=Array.isArray(rows)?[...rows]:[]; data=applyAdvancedFilters(name, data); if(sortKey){data=sortRows(data, sortKey, sortDir)} const cols=getResearchTableColumns(data.length?data:rows); const target=document.getElementById(`tbl_${name}`); if(!target) return; if(!data.length){target.innerHTML=`<div class="details-body"><div class="empty">No rows to show.</div></div>`; return} target.innerHTML=`<div class="details-body table-wrap"><table><thead><tr>${cols.map(c=>`<th onclick="toggleSort('${name}','${c}')">${esc(c)}${sortKey===c?(sortDir==='asc'?' ▲':' ▼'):''}</th>`).join('')}</tr></thead><tbody>${data.map(r=>`<tr>${cols.map(c=>`<td>${esc(r[c]??'—')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}
function renderResearch(){const el=document.getElementById('research'); const sections=APPDATA.research||{}; const order=['game_rankings','pitcher_line_value','pitcher_metrics','top_picks','refined_picks','hr_drought','hit_drought']; const labels={game_rankings:'Game Rankings',pitcher_line_value:'Pitcher Line Value',pitcher_metrics:'Pitcher Metrics',top_picks:'Top Picks',refined_picks:'Refined Picks',hr_drought:'HR Drought',hit_drought:'Hit Drought'}; if(!el.dataset.built){ el.innerHTML=order.map(name=>`<div class="panel"><div class="panel-head">${labels[name]}</div>${['hr_drought','hit_drought'].includes(name)?buildAdvancedFilterUI(name, sections[name]||[]):`<div class="tools"><input type="text" placeholder="Search this table" oninput="updateTextFilter('${name}', this.value)"></div>`}<div id="tbl_${name}"></div></div>`).join(''); el.dataset.built='1'; } order.forEach(name=>renderOneResearchTable(name, sections[name]||[]))}
function renderAll(){renderMeta();renderFinalCard();renderGames(); document.getElementById('research').innerHTML=''; document.getElementById('research').dataset.built=''; renderResearch()}
tabSetup(); loadData();
</script>
</body>
</html>
"""

@app.get("/app")
def app_page():
    return HTMLResponse(HTML)
HTML = """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>HR Picks</title>
<style>
:root{--bg:#070d2a;--panel:#121a44;--panel2:#172055;--text:#f3f5ff;--muted:#aeb7e6;--line:#33408d;--accent:#8ea2ff}
*{box-sizing:border-box} body{margin:0;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background:linear-gradient(180deg,#05091d,#07113a 40%,#05091d);color:var(--text)}
.wrap{max-width:980px;margin:0 auto;padding:22px 16px 40px}.title{font-size:30px;font-weight:800;margin:8px 0 6px}.meta{color:var(--muted);font-size:14px;margin-bottom:14px}.row{display:flex;gap:12px;flex-wrap:wrap}.btn,.tab{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:18px;padding:14px 18px;font-weight:700}.btn.primary{background:var(--accent);color:#fff;border-color:transparent}.tabs{margin:14px 0 18px}.tab.active{outline:2px solid var(--accent)}.section{display:none}.section.active{display:block}.card,.panel{background:rgba(18,26,68,.92);border:1px solid var(--line);border-radius:24px;padding:18px;margin:14px 0}.eyebrow,.subtle{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:700}.big,.game-title{font-size:18px;font-weight:800;margin:8px 0}.mid,.pickline,.kv,.small,.empty{color:var(--muted)}.flex{display:flex;gap:14px;align-items:flex-start}.pill{background:#26306e;border:1px solid var(--line);width:44px;height:44px;border-radius:999px;display:flex;align-items:center;justify-content:center;font-weight:800}.notice{padding:18px;border:1px dashed var(--line);border-radius:18px;color:var(--muted)}
.panel-head{font-size:16px;font-weight:800;margin-bottom:12px}.tools{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}.tools input[type=text],.tools input[type=number],.tools select{background:#0b1235;color:var(--text);border:1px solid var(--line);border-radius:14px;padding:12px 14px;min-width:150px}.mini-btn{background:#26306e;color:#fff;border:1px solid var(--line);border-radius:14px;padding:10px 14px;font-weight:700}.filter-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0}@media(max-width:700px){.filter-grid{grid-template-columns:1fr}}
.filter-box{border:1px solid var(--line);border-radius:18px;padding:12px;background:#0b1235}.filter-title{font-size:12px;color:var(--muted);text-transform:uppercase;font-weight:800;margin-bottom:8px}.check-list{max-height:160px;overflow:auto;padding-right:6px}.check-item{display:flex;gap:10px;align-items:flex-start;margin:8px 0;color:var(--text)}
.table-wrap{overflow:auto;max-height:560px}.table-wrap table{width:100%;border-collapse:collapse;font-size:14px}.table-wrap th,.table-wrap td{padding:12px 10px;border-bottom:1px solid rgba(142,162,255,.2);vertical-align:top;text-align:left}.table-wrap th{position:sticky;top:0;background:#152057;cursor:pointer}
.hr{height:1px;background:rgba(142,162,255,.18);margin:12px 0}
</style>
</head>
<body>
<div class="wrap">
  <div class="title">HR Picks</div>
  <div id="meta" class="meta">Loading…</div>
  <div class="row">
    <button class="btn primary" onclick="reloadData()">Refresh</button>
    <button class="btn" onclick="location.reload()">Reload App</button>
  </div>
  <div class="row tabs">
    <button class="tab active" data-target="final-card">Final Card</button>
    <button class="tab" data-target="games">Games</button>
    <button class="tab" data-target="research">Research</button>
  </div>
  <section id="final-card" class="section active"></section>
  <section id="games" class="section"></section>
  <section id="research" class="section"></section>
</div>
<script>
let APPDATA=null; let RESEARCH_SORT={}; let RESEARCH_SEARCH={};
function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function nice(v){if(v===null||v===undefined||v==="") return "—"; return String(v)}
function fmtNum(v){if(v===null||v===undefined||v==="") return "—"; const n=Number(v); return Number.isNaN(n)?String(v):n.toFixed(3).replace(/\.000$/,'')}
function tabSetup(){document.querySelectorAll('.tab').forEach(btn=>btn.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.section').forEach(x=>x.classList.remove('active'));btn.classList.add('active');document.getElementById(btn.dataset.target).classList.add('active')})}
async function loadData(){const res=await fetch('/latest'); APPDATA=await res.json(); renderAll()}
async function reloadData(){
  document.getElementById('meta').textContent='Refreshing server data…';
  const res = await fetch('/refresh-data', {method:'POST'});
  if(!res.ok){
    document.getElementById('meta').textContent='Refresh failed';
    return;
  }
  await loadData();
}
function renderMeta(){const d=APPDATA.date||'—'; document.getElementById('meta').textContent=`Date: ${d} • Loaded ${new Date().toLocaleTimeString()}`}
function renderFinalCard(){const el=document.getElementById('final-card'); const plays=APPDATA.final_card?.plays||[]; if(!plays.length){el.innerHTML='<div class="notice">No final card plays qualified today.</div>'; return} const groups={'Moneyline':[],'1+ Hit':[],'HR':[],'K Prop':[]}; plays.forEach(p=>{if(!groups[p.bet_type]) groups[p.bet_type]=[]; groups[p.bet_type].push(p)}); function block(title,items,emptyMsg){if(!items.length) return `<div class="card"><div class="eyebrow">${esc(title)}</div><div class="empty">${esc(emptyMsg)}</div></div>`; return items.map(p=>`<div class="card"><div class="flex"><div style="flex:1"><div class="eyebrow">${esc(p.slot)} · ${esc(p.bet_type)}</div><div class="big">${esc(p.pick)}</div><div class="mid">${esc(p.team)} vs ${esc(p.opponent)}</div><div class="kv">${esc(p.why_it_made_the_card)}</div><div class="small">Source: ${esc(p.source_tab)}</div></div><div class="pill">${esc(p.confidence||'')}</div></div></div>`).join('')} el.innerHTML=block('Moneyline',groups['Moneyline']||[],'No qualified moneyline play today.')+block('Hit Picks',groups['1+ Hit']||[],'No qualified hit picks today.')+block('HR Picks',groups['HR']||[],'No qualified HR picks today.')+block('K Prop',groups['K Prop']||[],'No qualified K prop today.')}
function buildGameCards(){const games=APPDATA.games||[]; const topPicks=APPDATA.research?.top_picks||[]; const pitcherVals=APPDATA.research?.pitcher_line_value||[]; return games.map(g=>{let hits=Array.isArray(g.top_hit_picks)?[...g.top_hit_picks]:[]; let hrs=Array.isArray(g.top_hr_picks)?[...g.top_hr_picks]:[]; const teams=[]; if(g.ml_lean?.team) teams.push(g.ml_lean.team); if(g.ml_lean?.opponent) teams.push(g.ml_lean.opponent); if(!hits.length){hits=topPicks.filter(r=>r.type==='HIT'&&teams.includes(r.teamName)).sort((a,b)=>(Number(b.Hit_score||0)-Number(a.Hit_score||0))).slice(0,2).map(r=>({playerName:r.playerName,teamName:r.teamName,Hit_score:r.Hit_score}))} if(!hrs.length){hrs=topPicks.filter(r=>r.type==='HR'&&teams.includes(r.teamName)).sort((a,b)=>(Number(b.HR_score||0)-Number(a.HR_score||0))).slice(0,2).map(r=>({playerName:r.playerName,teamName:r.teamName,HR_score:r.HR_score}))} let k=g.top_k_pick; if(!k&&teams.length){const p=pitcherVals.filter(r=>teams.includes(r.teamName)).sort((a,b)=>Number(b.projected_k_mid||0)-Number(a.projected_k_mid||0))[0]; if(p) k=p} return {...g,top_hit_picks:hits,top_hr_picks:hrs,top_k_pick:k}})}
function renderGames(){const el=document.getElementById('games'); const cards=buildGameCards(); if(!cards.length){el.innerHTML='<div class="notice">No game cards available.</div>'; return} el.innerHTML=cards.map(g=>{const ml=g.ml_lean||{}; const hits=g.top_hit_picks||[]; const hrs=g.top_hr_picks||[]; const k=g.top_k_pick||null; return `<div class="card"><div class="game-title">${esc(g.game)}</div><div class="subtle">Model Lean</div><div class="pickline"><strong>${esc(ml.team||'No side')}</strong> vs ${esc(ml.opponent||'—')}</div><div class="kv">Model edge: ${fmtNum(ml.edge_vs_opponent)} · Model note: ${esc(ml.recommended_play||'—')}</div><div class="hr"></div><div class="subtle">Top Hit Picks</div>${hits.length?hits.map(p=>`<div class="pickline"><strong>${esc(p.playerName)}</strong> · ${esc(p.teamName)} · Hit score ${fmtNum(p.Hit_score)}</div>`).join(''):'<div class="empty">No qualified hit picks shown for this game.</div>'}<div class="hr"></div><div class="subtle">Top HR Picks</div>${hrs.length?hrs.map(p=>`<div class="pickline"><strong>${esc(p.playerName)}</strong> · ${esc(p.teamName)} · HR score ${fmtNum(p.HR_score)}</div>`).join(''):'<div class="empty">No qualified HR picks shown for this game.</div>'}<div class="hr"></div><div class="subtle">Top K Pick</div>${k?`<div class="pickline"><strong>${esc(k.pitcherName||'—')}</strong> · ${esc(k.teamName||'—')} · ${esc(k.recommended_k_action||'—')}</div><div class="kv">Projected Ks: ${fmtNum(k.projected_k_floor)}-${fmtNum(k.projected_k_ceiling)} · Max line: ${nice(k.max_playable_k_line)}</div>`:'<div class="empty">No K pick for this game.</div>'}</div>`}).join('')}
function getResearchTableColumns(rows){const s=new Set(); rows.slice(0,50).forEach(r=>Object.keys(r).forEach(k=>s.add(k))); return Array.from(s)}
function sortRows(rows,key,dir){const copy=[...rows]; copy.sort((a,b)=>{const av=a[key],bv=b[key]; const an=Number(av),bn=Number(bv); const aNum=!Number.isNaN(an)&&av!==null&&av!==''; const bNum=!Number.isNaN(bn)&&bv!==null&&bv!==''; let cmp=0; if(aNum&&bNum) cmp=an-bn; else cmp=String(av??'').localeCompare(String(bv??'')); return dir==='asc'?cmp:-cmp}); return copy}
function toggleSort(name,key){if(!RESEARCH_SORT[name]||RESEARCH_SORT[name].key!==key){RESEARCH_SORT[name]={key,dir:'desc'}}else{RESEARCH_SORT[name].dir=RESEARCH_SORT[name].dir==='desc'?'asc':'desc'} renderOneResearchTable(name)}
function getRows(name){return Array.isArray(APPDATA.research?.[name])?[...APPDATA.research[name]]:[]}
function getSelectedValues(prefix){return Array.from(document.querySelectorAll(`input[data-group="${prefix}"]:checked`)).map(x=>x.value)}
function applyPanelFilters(name, rows){let data=[...rows]; const search=(document.getElementById(`${name}-search`)?.value||'').toLowerCase().trim(); if(search) data=data.filter(r=>JSON.stringify(r).toLowerCase().includes(search)); if(['hr_drought','hit_drought'].includes(name)){
 const teams=getSelectedValues(`${name}-teams`); const statuses=getSelectedValues(`${name}-statuses`); const parks=getSelectedValues(`${name}-parks`); const opps=getSelectedValues(`${name}-opps`); const overdue=document.getElementById(`${name}-overdue`)?.checked; const minVal=Number(document.getElementById(`${name}-mindrought`)?.value||'');
 if(teams.length) data=data.filter(r=>teams.includes(String(r.teamName||'')));
 if(statuses.length) data=data.filter(r=>statuses.includes(String(r.status||'')));
 if(parks.length) data=data.filter(r=>parks.includes(String(r.park_favorability||'')));
 if(opps.length) data=data.filter(r=>opps.includes(String(r.opponent_pitcher_pick_type||'')));
 if(overdue) data=data.filter(r=>String(r.status||'').toLowerCase().includes('overdue'));
 if(!Number.isNaN(minVal)){const col=name==='hr_drought'?'current_games_without_hr':'current_games_without_hit'; data=data.filter(r=>Number(r[col]||0)>=minVal)}
 }
 return data}
function renderCheckboxGroup(id,title,vals){return `<div class="filter-box"><div class="filter-title">${esc(title)}</div><div class="check-list">${vals.map(v=>`<label class="check-item"><input type="checkbox" data-group="${id}" value="${esc(v)}"><span>${esc(v)}</span></label>`).join('')||'<div class="empty">No options</div>'}</div></div>`}
function uniq(rows,key){return [...new Set(rows.map(r=>String(r[key]??'')).filter(v=>v.trim()!==''))].sort((a,b)=>a.localeCompare(b))}
function buildResearchPanel(name,label){const rows=getRows(name); const searchable=['hr_drought','hit_drought'].includes(name); let html=`<div class="panel"><div class="panel-head">${esc(label)}</div>`;
 if(searchable){html += `<div class="tools"><input id="${name}-search" type="text" placeholder="Search this table"><label class="check-item filter-box" style="max-width:220px"><input id="${name}-overdue" type="checkbox"><span>Overdue only</span></label><input id="${name}-mindrought" type="number" min="0" placeholder="${name==='hr_drought'?'Min HR Drought':'Min Hit Drought'}"></div>`;
 html += `<div class="filter-grid">${renderCheckboxGroup(name+'-teams','Teams',uniq(rows,'teamName'))}${renderCheckboxGroup(name+'-statuses','Status',uniq(rows,'status'))}${renderCheckboxGroup(name+'-parks','Park',uniq(rows,'park_favorability'))}${renderCheckboxGroup(name+'-opps','Opponent Pitcher Type',uniq(rows,'opponent_pitcher_pick_type'))}</div>`;
 html += `<div class="row"><button class="mini-btn" onclick="applyResearchFilters('${name}')">Apply Filters</button><button class="mini-btn" onclick="clearResearchFilters('${name}')">Clear Filters</button></div>`;
 } else {html += `<div class="tools"><input id="${name}-search" type="text" placeholder="Search this table"><button class="mini-btn" onclick="applyResearchFilters('${name}')">Apply Filters</button><button class="mini-btn" onclick="clearResearchFilters('${name}')">Clear Filters</button></div>`}
 html += `<div id="tbl_${name}"></div></div>`; return html}
function applyResearchFilters(name){renderOneResearchTable(name)}
function clearResearchFilters(name){const panel=document.getElementById(`tbl_${name}`).closest('.panel'); panel.querySelectorAll('input[type="checkbox"]').forEach(x=>x.checked=false); panel.querySelectorAll('input[type="text"], input[type="number"]').forEach(x=>x.value=''); RESEARCH_SORT[name]=RESEARCH_SORT[name]||{}; renderOneResearchTable(name)}
function renderOneResearchTable(name){const baseRows=getRows(name); let rows=applyPanelFilters(name,baseRows); const search=document.getElementById(`${name}-search`)?.value||''; if(search&&!['hr_drought','hit_drought'].includes(name)){rows=rows.filter(r=>JSON.stringify(r).toLowerCase().includes(search.toLowerCase().trim()))} const sortKey=RESEARCH_SORT[name]?.key||null; const sortDir=RESEARCH_SORT[name]?.dir||'desc'; if(sortKey) rows=sortRows(rows,sortKey,sortDir); const cols=getResearchTableColumns(rows.length?rows:baseRows); const target=document.getElementById(`tbl_${name}`); if(!target) return; if(!rows.length){target.innerHTML='<div class="notice">No rows to show.</div>'; return} target.innerHTML=`<div class="table-wrap"><table><thead><tr>${cols.map(c=>`<th onclick="toggleSort('${name}','${c}')">${esc(c)}${sortKey===c?(sortDir==='asc'?' ▲':' ▼'):''}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${cols.map(c=>`<td>${esc(r[c]??'—')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}
function renderResearch(){const el=document.getElementById('research'); const labels={game_rankings:'Game Rankings',pitcher_line_value:'Pitcher Line Value',pitcher_metrics:'Pitcher Metrics',top_picks:'Top Picks',refined_picks:'Refined Picks',hr_drought:'HR Drought',hit_drought:'Hit Drought'}; const order=['game_rankings','pitcher_line_value','pitcher_metrics','top_picks','refined_picks','hr_drought','hit_drought']; el.innerHTML=order.map(name=>buildResearchPanel(name,labels[name])).join(''); order.forEach(name=>renderOneResearchTable(name))}
function renderAll(){renderMeta(); renderFinalCard(); renderGames(); renderResearch()}
tabSetup(); loadData();
</script>
</body>
</html>
"""
