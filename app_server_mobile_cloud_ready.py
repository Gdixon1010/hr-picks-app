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
        reverse=True,
    )
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
        "message": "HR Picks cloud app is running",
        "endpoints": ["/app", "/latest", "/final-card", "/games", "/research", "/refresh-data"],
    }


@app.api_route("/refresh-data", methods=["GET", "POST"])
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
<title>HR Picks</title>
<style>
:root{--bg:#070b24;--panel:#121938;--panel2:#1a2248;--line:#3a4b9a;--text:#f2f4ff;--muted:#adb4da;--accent:#8ea2ff}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:linear-gradient(180deg,#05091d 0%, #070b24 100%);color:var(--text)}
.wrap{max-width:980px;margin:0 auto;padding:22px 16px 48px}
h1{font-size:32px;line-height:1.1;margin:12px 0 10px}
.meta{color:var(--muted);font-size:16px;margin-bottom:18px}
.row{display:flex;gap:12px;flex-wrap:wrap}
.btn{border:none;border-radius:18px;padding:16px 20px;background:var(--panel2);color:var(--text);font-size:15px;font-weight:700;border:1px solid #334181;cursor:pointer}
.btn.primary{background:var(--accent);color:#fff}
.tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:18px 0 20px}
.tab{text-align:center;padding:18px 10px;border-radius:22px;background:var(--panel);border:1px solid #334181;color:var(--text);font-size:17px;font-weight:800;cursor:pointer}
.tab.active{outline:2px solid var(--accent)}
.section{display:none}.section.active{display:block}
.card{background:rgba(18,25,56,.95);border:1px solid #2e3b7d;border-radius:26px;padding:18px 18px 16px;margin:14px 0}
.eyebrow{font-size:14px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:800}
.big{font-size:24px;font-weight:900;line-height:1.15;margin:4px 0}
.mid{font-size:18px;color:var(--muted);margin:3px 0}
.small{font-size:14px;color:var(--muted);margin-top:8px}
.pill{width:56px;height:56px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#27326f;border:1px solid #3a4b9a;font-weight:900;font-size:28px}
.flex{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}
.kv{margin-top:8px;color:var(--muted);font-size:15px}
.notice{padding:14px 16px;background:#171f43;border:1px dashed #5066c7;border-radius:18px;color:var(--muted)}
.game-title{font-size:22px;font-weight:900;line-height:1.2;margin:0 0 12px}
.subtle{color:var(--muted);font-size:13px;text-transform:uppercase;letter-spacing:.08em;font-weight:800}
.pickline{margin:8px 0 0;font-size:17px;line-height:1.4}
.pickline strong{color:#fff}
.hr{height:1px;background:#2a376f;margin:14px 0}
.panel{background:rgba(18,25,56,.95);border:1px solid #2e3b7d;border-radius:22px;margin:12px 0;overflow:hidden}
.panel-head{padding:18px 18px;font-size:19px;font-weight:900;border-bottom:1px solid #28366e}
.details-body{padding:0 12px 14px}
.table-wrap{overflow:auto;max-height:65vh}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:10px 12px;border-bottom:1px solid #28366e;vertical-align:top;text-align:left}
th{color:#c8cff5;font-size:13px;position:sticky;top:0;background:#141c40}
td{color:#eef1ff}
.empty{color:var(--muted);font-size:17px;padding:8px 2px}
</style>
</head>
<body>
<div class="wrap">
  <h1>HR Picks</h1>
  <div class="meta" id="meta">Loading…</div>
  <div class="row">
    <button class="btn primary" onclick="refreshData()">Refresh Data</button>
    <button class="btn" onclick="loadData()">Reload App</button>
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
let APPDATA=null;

function esc(s){return String(s??"").replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function nice(v){if(v===null||v===undefined||v==="") return "—"; return String(v)}
function fmtNum(v){if(v===null||v===undefined||v==="") return "—"; const n=Number(v); return Number.isNaN(n)?String(v):n.toFixed(3).replace(/\.000$/,'')}
function tabSetup(){
  document.querySelectorAll('.tab').forEach(btn=>{
    btn.onclick=()=>{
      document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
      document.querySelectorAll('.section').forEach(x=>x.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.target).classList.add('active');
    };
  });
}

async function refreshData(){
  document.getElementById('meta').textContent='Refreshing server data...';
  const res = await fetch('/refresh-data');
  const data = await res.json();
  document.getElementById('meta').textContent=`Date: ${data.date} • Refresh finished`;
  await loadData();
}

async function loadData(){
  const res = await fetch('/latest');
  APPDATA = await res.json();
  renderAll();
}

function renderMeta(){
  const d=APPDATA.date||'—';
  const file=APPDATA._meta?.filename||'No data file yet';
  document.getElementById('meta').textContent=`Date: ${d} • Source: ${file}`;
}

function renderFinalCard(){
  const el=document.getElementById('final-card');
  const plays=APPDATA.final_card?.plays||[];
  if(!plays.length){
    el.innerHTML=`<div class="notice">No final card plays qualified yet. Tap Refresh Data first.</div>`;
    return;
  }
  el.innerHTML = plays.map(p=>`
    <div class="card">
      <div class="flex">
        <div style="flex:1">
          <div class="eyebrow">${esc(p.slot)} · ${esc(p.bet_type)}</div>
          <div class="big">${esc(p.pick)}</div>
          <div class="mid">${esc(p.team)} vs ${esc(p.opponent)}</div>
          <div class="kv">${esc(p.why_it_made_the_card)}</div>
          <div class="small">Source: ${esc(p.source_tab)}</div>
        </div>
        <div class="pill">${esc(p.confidence||'')}</div>
      </div>
    </div>
  `).join('');
}

function renderGames(){
  const el=document.getElementById('games');
  const games=APPDATA.games||[];
  if(!games.length){
    el.innerHTML=`<div class="notice">No game cards available yet.</div>`;
    return;
  }
  el.innerHTML = games.map(g=>{
    const ml=g.ml_lean||{};
    const hits=g.top_hit_picks||[];
    const hrs=g.top_hr_picks||[];
    const k=g.top_k_pick||null;
    return `
      <div class="card">
        <div class="game-title">${esc(g.game)}</div>
        <div class="subtle">Model Lean</div>
        <div class="pickline"><strong>${esc(ml.team||'No side')}</strong> vs ${esc(ml.opponent||'—')}</div>
        <div class="kv">Model edge: ${fmtNum(ml.edge_vs_opponent)} · ${esc(ml.recommended_play||'—')}</div>
        <div class="hr"></div>
        <div class="subtle">Top Hit Picks</div>
        ${hits.length ? hits.map(p=>`<div class="pickline"><strong>${esc(p.playerName)}</strong> · ${esc(p.teamName)} · Hit score ${fmtNum(p.Hit_score)}</div>`).join('') : `<div class="empty">No hit picks for this game.</div>`}
        <div class="hr"></div>
        <div class="subtle">Top HR Picks</div>
        ${hrs.length ? hrs.map(p=>`<div class="pickline"><strong>${esc(p.playerName)}</strong> · ${esc(p.teamName)} · HR score ${fmtNum(p.HR_score)}</div>`).join('') : `<div class="empty">No HR picks for this game.</div>`}
        <div class="hr"></div>
        <div class="subtle">Top K Pick</div>
        ${k ? `<div class="pickline"><strong>${esc(k.pitcherName||'—')}</strong> · ${esc(k.teamName||'—')} · ${esc(k.recommended_k_action||'—')}</div>` : `<div class="empty">No K pick for this game.</div>`}
      </div>
    `;
  }).join('');
}

function renderResearch(){
  const el=document.getElementById('research');
  const sections=APPDATA.research||{};
  const order=['game_rankings','pitcher_line_value','pitcher_metrics','top_picks','refined_picks','hr_drought','hit_drought'];
  const labels={game_rankings:'Game Rankings',pitcher_line_value:'Pitcher Line Value',pitcher_metrics:'Pitcher Metrics',top_picks:'Top Picks',refined_picks:'Refined Picks',hr_drought:'HR Drought',hit_drought:'Hit Drought'};
  el.innerHTML = order.map(name=>{
    const rows = sections[name] || [];
    if(!rows.length){
      return `<div class="panel"><div class="panel-head">${labels[name]}</div><div class="details-body"><div class="empty">No rows available.</div></div></div>`;
    }
    const cols = Object.keys(rows[0]);
    return `
      <div class="panel">
        <div class="panel-head">${labels[name]}</div>
        <div class="details-body table-wrap">
          <table>
            <thead><tr>${cols.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead>
            <tbody>
              ${rows.slice(0,50).map(r=>`<tr>${cols.map(c=>`<td>${esc(r[c]??'—')}</td>`).join('')}</tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }).join('');
}

function renderAll(){
  renderMeta();
  renderFinalCard();
  renderGames();
  renderResearch();
}

tabSetup();
loadData();
</script>
</body>
</html>
"""

@app.get("/app")
def app_page():
    return HTMLResponse(HTML)
