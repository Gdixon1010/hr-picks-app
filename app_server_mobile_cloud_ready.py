from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
from pathlib import Path
import json
import datetime as dt

from hr_v41_cloud_ready import main as run_model_main

app = FastAPI()

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def get_latest_json_file():
    files = []
    for pat in ("HR_Hit_Drought_v41_appdata-*.json", "HR_Hit_Drought_v40_appdata-*.json"):
        files.extend(OUTPUT_DIR.glob(pat))
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def load_latest_data():
    latest_file = get_latest_json_file()
    if not latest_file:
        return {
            "date": None,
            "final_card": {"generated_section": "final_card", "plays": []},
            "games": [],
            "research": {},
            "_meta": {"filename": None},
        }

    with open(latest_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["_meta"] = {
        "filename": latest_file.name,
        "path": str(latest_file),
    }
    return data


@app.get("/")
def home():
    return {
        "message": "HR Picks cloud app v41",
        "endpoints": ["/app", "/latest", "/refresh-data"],
    }


@app.api_route("/refresh-data", methods=["GET", "POST"])
def refresh_data():
    today = dt.date.today().strftime("%Y-%m-%d")
    run_model_main(2026, today)
    return {"status": "ok", "message": "Data refreshed", "date": today}


@app.get("/latest")
def latest():
    return JSONResponse(content=load_latest_data())


HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>HR Picks v41</title>
<style>
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;background:#070b24;color:#f2f4ff}
.wrap{max-width:960px;margin:auto;padding:16px}
.meta{color:#adb4da;margin:12px 0}
.row{display:flex;gap:8px;flex-wrap:wrap}
.btn{padding:12px 14px;border:none;border-radius:14px;background:#1a2248;color:#fff;font-weight:700;cursor:pointer}
.tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:14px 0}
.tab{padding:12px;border:1px solid #334181;border-radius:14px;background:#121938;color:#fff;font-weight:800;cursor:pointer}
.tab.active{outline:2px solid #8ea2ff}
.sec{display:none}.sec.on{display:block}
.card,.panel{background:#121938;border:1px solid #2e3b7d;border-radius:18px;padding:14px;margin:12px 0}
.m{color:#adb4da}.pill{float:right;background:#27326f;border-radius:999px;padding:10px 14px;font-weight:800}
.tools{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.tools input{background:#0f1532;color:#fff;border:1px solid #344281;border-radius:10px;padding:10px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.box{background:#0f1532;border:1px solid #344281;border-radius:12px;padding:10px}
.list{max-height:150px;overflow:auto}
.item{display:flex;gap:8px;align-items:center;margin:6px 0}
.tbl{overflow:auto;max-height:60vh}
table{width:100%;border-collapse:collapse}
th,td{padding:8px 10px;border-bottom:1px solid #28366e;text-align:left}
th{position:sticky;top:0;background:#141c40;cursor:pointer}
.empty{color:#adb4da;padding:12px}
@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <h1>HR Picks</h1>
  <div id="meta" class="meta">Loading…</div>
  <div class="row">
    <button class="btn" onclick="refreshData()">Refresh Data</button>
    <button class="btn" onclick="loadData()">Reload App</button>
  </div>
  <div class="tabs">
    <button class="tab active" data-x="final">Final Card</button>
    <button class="tab" data-x="games">Games</button>
    <button class="tab" data-x="research">Research</button>
  </div>
  <div id="final" class="sec on"></div>
  <div id="games" class="sec"></div>
  <div id="research" class="sec"></div>
</div>

<script>
let D=null,S={},F={};
const e=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const n=v=>{let x=Number(v);return Number.isNaN(x)?String(v??'—'):x.toFixed(3).replace(/\.000$/,'')};

document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.sec').forEach(x=>x.classList.remove('on'));
  b.classList.add('active');
  document.getElementById(b.dataset.x).classList.add('on');
});

async function refreshData(){
  meta.textContent='Refreshing...';
  await fetch('/refresh-data');
  await loadData();
}
async function loadData(){
  D=await (await fetch('/latest')).json();
  meta.textContent=`Date: ${D.date||'—'} • ${D._meta?.filename||'No data yet'}`;
  renderFinal();
  renderGames();
  renderResearch();
}

function renderFinal(){
  let p=D.final_card?.plays||[];
  final.innerHTML=!p.length
    ? '<div class="card">No final card plays yet.</div>'
    : p.map(r=>`<div class="card">
        <span class="pill">${e(r.confidence||'')}</span>
        <div class="m">${e(r.slot)} · ${e(r.bet_type)}</div>
        <div><b>${e(r.pick)}</b></div>
        <div class="m">${e(r.team)} vs ${e(r.opponent)}</div>
        <div class="m">${e(r.why_it_made_the_card)}</div>
      </div>`).join('');
}

function renderGames(){
  let g=D.games||[];
  games.innerHTML=!g.length
    ? '<div class="card">No games yet.</div>'
    : g.map(x=>`<div class="card">
        <div><b>${e(x.game)}</b></div>
        <div class="m">Model Lean: ${e(x.ml_lean?.team||'No side')} vs ${e(x.ml_lean?.opponent||'—')} · Edge ${n(x.ml_lean?.edge_vs_opponent)}</div>
        <hr style="border-color:#2a376f">
        <div><b>Top Hit Picks</b>
          ${(x.top_hit_picks||[]).map(p=>`<div class="m">${e(p.playerName)} · ${e(p.teamName)} · ${n(p.Hit_score)}</div>`).join('') || '<div class="m">None</div>'}
        </div>
        <hr style="border-color:#2a376f">
        <div><b>Top HR Picks</b>
          ${(x.top_hr_picks||[]).map(p=>`<div class="m">${e(p.playerName)} · ${e(p.teamName)} · ${n(p.HR_score)}</div>`).join('') || '<div class="m">None</div>'}
        </div>
      </div>`).join('');
}

function cols(rows){let s=new Set();rows.slice(0,50).forEach(r=>Object.keys(r).forEach(k=>s.add(k)));return [...s]}
function sortRows(rows,k,d){
  let c=[...rows];
  c.sort((a,b)=>{
    let av=a[k],bv=b[k],an=Number(av),bn=Number(bv);
    let cmp=!Number.isNaN(an)&&!Number.isNaN(bn) ? an-bn : String(av??'').localeCompare(String(bv??''));
    return d==='asc'?cmp:-cmp;
  });
  return c;
}
function uniq(rows,k){return [...new Set((rows||[]).map(r=>String(r[k]??'')).filter(v=>v.trim()!==''))].sort((a,b)=>a.localeCompare(b))}
function init(name){if(!F[name])F[name]={q:'',teams:[],status:[],parks:[],opps:[],over:false,min:''}}
function checkBox(name,key,title,vals){
  let s=(F[name]||{})[key]||[];
  return `<div class="box"><div class="m">${title}</div><div class="list">${
    vals.map(v=>`<label class="item"><input type="checkbox" ${s.includes(v)?'checked':''} onchange="setChk('${name}','${key}',${JSON.stringify(v)},this.checked)"><span>${e(v)}</span></label>`).join('') || 'None'
  }</div></div>`;
}
function setChk(name,key,v,on){
  init(name);
  let a=F[name][key],i=a.indexOf(v);
  if(on&&i===-1)a.push(v);
  if(!on&&i!==-1)a.splice(i,1);
}
function apply(name,rows){
  init(name);
  let f=F[name],q=(f.q||'').toLowerCase().trim(),d=[...rows];
  if(q)d=d.filter(r=>JSON.stringify(r).toLowerCase().includes(q));
  if(['hr_drought','hit_drought'].includes(name)){
    if(f.teams.length)d=d.filter(r=>f.teams.includes(String(r.teamName||'')));
    if(f.status.length)d=d.filter(r=>f.status.includes(String(r.status||'')));
    if(f.parks.length)d=d.filter(r=>f.parks.includes(String(r.park_favorability||'')));
    if(f.opps.length)d=d.filter(r=>f.opps.includes(String(r.opponent_pitcher_pick_type||'')));
    if(f.over)d=d.filter(r=>String(r.status||'').toLowerCase().includes('overdue'));
    if(f.min!==''){
      let t=Number(f.min),c=name==='hr_drought'?'current_games_without_hr':'current_games_without_hit';
      if(!Number.isNaN(t))d=d.filter(r=>Number(r[c]||0)>=t);
    }
  }
  return d;
}
function one(name,rows){
  init(name);
  let d=apply(name,Array.isArray(rows)?rows:[]), sk=S[name]?.k, sd=S[name]?.d||'desc';
  if(sk)d=sortRows(d,sk,sd);
  let c=cols(d.length?d:rows), tgt=document.getElementById('tbl_'+name);
  if(!tgt)return;
  if(!d.length){tgt.innerHTML='<div class="card">No rows to show.</div>'; return;}
  tgt.innerHTML=`<div class="tbl"><table><thead><tr>${
    c.map(k=>`<th onclick="tog('${name}','${k}')">${e(k)}${sk===k?(sd==='asc'?' ▲':' ▼'):''}</th>`).join('')
  }</tr></thead><tbody>${
    d.map(r=>`<tr>${c.map(k=>`<td>${e(r[k]??'—')}</td>`).join('')}</tr>`).join('')
  }</tbody></table></div>`;
}
function tog(name,k){
  if(!S[name]||S[name].k!==k)S[name]={k,d:'desc'};
  else S[name].d=S[name].d==='desc'?'asc':'desc';
  one(name,D.research?.[name]||[]);
}
function clearF(name){
  F[name]={q:'',teams:[],status:[],parks:[],opps:[],over:false,min:''};
  renderResearch();
}
function renderResearch(){
  let s=D.research||{},
      order=['game_rankings','pitcher_line_value','pitcher_metrics','top_picks','refined_picks','hr_drought','hit_drought'],
      labels={game_rankings:'Game Rankings',pitcher_line_value:'Pitcher Line Value',pitcher_metrics:'Pitcher Metrics',top_picks:'Top Picks',refined_picks:'Refined Picks',hr_drought:'HR Drought',hit_drought:'Hit Drought'};

  research.innerHTML=order.map(name=>{
    let rows=s[name]||[], adv=['hr_drought','hit_drought'].includes(name);
    init(name);
    return `<div class="panel">
      <div><b>${labels[name]}</b></div>
      ${adv
        ? `<div class="tools">
             <input type="text" placeholder="Search this table" value="${e(F[name].q)}" oninput="F['${name}'].q=this.value;one('${name}',D.research?.['${name}']||[])">
             <label class="item"><input type="checkbox" ${F[name].over?'checked':''} onchange="F['${name}'].over=this.checked"><span>Overdue only</span></label>
             <input type="number" placeholder="Min drought" value="${e(F[name].min)}" oninput="F['${name}'].min=this.value">
           </div>
           <div class="grid">
             ${checkBox(name,'teams','Teams',uniq(rows,'teamName'))}
             ${checkBox(name,'status','Status',uniq(rows,'status'))}
             ${checkBox(name,'parks','Park',uniq(rows,'park_favorability'))}
             ${checkBox(name,'opps','Opponent Pitcher Type',uniq(rows,'opponent_pitcher_pick_type'))}
           </div>
           <div class="tools">
             <button class="btn" onclick="one('${name}',D.research?.['${name}']||[])">Apply Filters</button>
             <button class="btn" onclick="clearF('${name}')">Clear Filters</button>
           </div>`
        : `<div class="tools"><input type="text" placeholder="Search this table" oninput="F['${name}']={q:this.value,teams:[],status:[],parks:[],opps:[],over:false,min:''};one('${name}',D.research?.['${name}']||[])"></div>`
      }
      <div id="tbl_${name}"></div>
    </div>`;
  }).join('');

  order.forEach(name=>one(name,s[name]||[]));
}

loadData();
</script>
</body>
</html>
"""

@app.get("/app")
def app_page():
    return HTMLResponse(HTML)
