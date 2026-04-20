
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
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
    latest = get_latest_json_file()
    eastern_now = dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=-4)))
    fallback = {
        "date": None,
        "final_card": {"generated_section": "final_card", "plays": []},
        "games": [],
        "research": {},
        "_meta": {
            "filename": None,
            "path": None,
            "eastern_now": eastern_now.strftime("%Y-%m-%d %I:%M %p ET"),
        },
    }
    if not latest:
        return fallback
    try:
        with open(latest, "r", encoding="utf-8") as f:
            payload = json.load(f)
        payload["_meta"] = payload.get("_meta", {})
        payload["_meta"]["filename"] = latest.name
        payload["_meta"]["path"] = str(latest)
        payload["_meta"].setdefault("eastern_now", eastern_now.strftime("%Y-%m-%d %I:%M %p ET"))
        return payload
    except Exception:
        return fallback

def fmt_last_updated(meta):
    raw = (meta or {}).get("eastern_now")
    if raw:
        return raw
    latest = get_latest_json_file()
    if not latest:
        return "Not available"
    ts = dt.datetime.fromtimestamp(latest.stat().st_mtime, tz=dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=-4)))
    return ts.strftime("%b %d, %Y %I:%M %p ET")

@app.get("/latest")
def latest():
    return JSONResponse(load_latest_data())

@app.get("/refresh-data")
def refresh_data():
    today = dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=-4))).strftime("%Y-%m-%d")
    run_model_main(2026, today)
    data = load_latest_data()
    return JSONResponse({
        "status": "ok",
        "message": "Data refreshed",
        "date": data.get("date"),
        "filename": (data.get("_meta") or {}).get("filename"),
        "timezone": "America/New_York",
    })

@app.get("/app")
def app_ui():
    data = load_latest_data()
    last_updated = fmt_last_updated(data.get("_meta"))
    html = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>HR Picks App</title>
<style>
:root {{
  --bg:#060b16; --card:#111826; --card2:#0f1724; --line:#2a3650;
  --text:#f4f6fb; --muted:#b8c1d1; --blue:#4c82ff; --blue2:#2f5fd9;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  background:linear-gradient(180deg,#040812,#071020 55%,#071020); color:var(--text);
}}
.container {{ max-width: 1320px; margin:0 auto; padding: 22px; }}
.header {{
  display:flex; justify-content:space-between; align-items:flex-start; gap:16px; flex-wrap:wrap;
}}
h1 {{ margin:0 0 6px 0; font-size: clamp(2rem, 4vw, 3.1rem); line-height:1; }}
.sub {{ color:var(--muted); font-size: clamp(1rem, 2vw, 1.1rem); }}
.tabs, .subtabs {{
  display:flex; gap:12px; flex-wrap:wrap; margin-top:18px;
}}
button.tab, button.subtab, .btn {{
  border:1px solid #42506e; background:#151c2b; color:#e9eef9; border-radius: 999px;
  padding: 14px 18px; font-size:1rem; cursor:pointer;
}}
button.tab.active, button.subtab.active {{ background:#273147; border-color:#62739d; }}
.btn.primary {{
  background:linear-gradient(180deg, var(--blue), var(--blue2)); border:none; font-weight:700;
  padding: 14px 22px;
}}
.section {{ display:none; margin-top:22px; }}
.section.active {{ display:block; }}
.grid {{
  display:grid; grid-template-columns: repeat(auto-fit, minmax(320px,1fr)); gap:16px;
}}
.card {{
  background:linear-gradient(180deg,var(--card),var(--card2));
  border:1px solid var(--line); border-radius: 24px; padding: 22px;
  box-shadow: 0 8px 30px rgba(0,0,0,.18);
}}
.card h2, .card h3 {{ margin:0 0 12px 0; }}
.card p {{ margin:8px 0; color:var(--muted); }}
.kv {{ margin:6px 0; }}
.kv strong {{ color:var(--text); }}
.meta-line {{ color:var(--muted); font-size:.98rem; margin-top:6px; }}
.research-grid {{
  display:grid; grid-template-columns: repeat(auto-fit, minmax(260px,1fr)); gap:16px;
}}
.research-card {{
  background:linear-gradient(180deg,var(--card),var(--card2));
  border:1px solid var(--line); border-radius: 22px; padding: 18px; cursor:pointer;
}}
.research-card:hover {{ border-color:#5e719d; transform: translateY(-1px); }}
.filters {{
  background:linear-gradient(180deg,var(--card),var(--card2));
  border:1px solid var(--line); border-radius: 22px; padding: 18px; margin-bottom:16px;
}}
.filters input, .filters select {{
  background:#0d1422; color:var(--text); border:1px solid #394866; border-radius:14px;
  padding:12px 14px; min-width: 160px;
}}
.filters label {{ color:var(--muted); font-size:.95rem; display:flex; align-items:center; gap:8px; }}
.filter-row {{ display:flex; flex-wrap:wrap; gap:12px; margin-bottom:12px; }}
.table-wrap {{
  overflow:auto; background:linear-gradient(180deg,var(--card),var(--card2));
  border:1px solid var(--line); border-radius: 22px; padding: 6px;
}}
table {{ width:100%; border-collapse: collapse; min-width: 980px; }}
th, td {{ padding: 12px 14px; border-bottom:1px solid #22304a; text-align:left; vertical-align:top; }}
th {{ position:sticky; top:0; background:#0f1828; z-index:1; }}
.muted {{ color:var(--muted); }}
.hidden {{ display:none; }}
@media (max-width: 640px) {{
  .container {{ padding:16px; }}
  .btn.primary {{ width:100%; }}
  .header-right {{ width:100%; }}
}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>HR Picks App</h1>
      <div class="sub">Date: <span id="dateText">{data.get("date") or "N/A"}</span> • Last Updated: <span id="updatedText">{last_updated}</span></div>
    </div>
    <div class="header-right">
      <button class="btn primary" id="reloadBtn" onclick="reloadApp()">Reload App</button>
    </div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="showSection('finalCard', this)">Final Card</button>
    <button class="tab" onclick="showSection('games', this)">Games</button>
    <button class="tab" onclick="showSection('research', this)">Research</button>
  </div>

  <div id="finalCard" class="section active"></div>
  <div id="games" class="section"></div>

  <div id="research" class="section">
    <div id="researchHome"></div>
    <div id="researchDetail" class="hidden">
      <div class="subtabs" style="margin-bottom:16px;">
        <button class="subtab active" id="researchBackBtn" onclick="backToResearchHome()">← Back to Research</button>
      </div>
      <div id="researchFilters"></div>
      <div id="researchTable"></div>
    </div>
  </div>
</div>

<script>
let APP_DATA = {json.dumps(data, ensure_ascii=False)};
let CURRENT_RESEARCH_KEY = null;

function esc(v) {{
  if (v === null || v === undefined) return '—';
  return String(v)
    .replaceAll('&','&amp;')
    .replaceAll('<','&lt;')
    .replaceAll('>','&gt;')
    .replaceAll('"','&quot;');
}}

function showSection(id, btn) {{
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
}}

function renderFinalCard() {{
  const mount = document.getElementById('finalCard');
  const plays = (APP_DATA.final_card && APP_DATA.final_card.plays) ? APP_DATA.final_card.plays : [];
  if (!plays.length) {{
    mount.innerHTML = `<div class="card"><h2>No final card available</h2><p class="muted">Run your private refresh link, then tap Reload App.</p></div>`;
    return;
  }}
  mount.innerHTML = `<div class="grid">${{
    plays.map(p => `
      <div class="card">
        <h2>${{esc(p.slot || 'Play')}}</h2>
        <div class="kv"><strong>${{esc(p.bet_type || '')}}</strong></div>
        <div class="kv"><strong>Pick:</strong> ${{esc(p.pick)}}</div>
        <div class="kv"><strong>Team:</strong> ${{esc(p.team)}}</div>
        <div class="kv"><strong>Opponent:</strong> ${{esc(p.opponent)}}</div>
        <div class="kv"><strong>Confidence:</strong> ${{esc(p.confidence)}}</div>
        <p>${{esc(p.why_it_made_the_card || '')}}</p>
        <div class="meta-line">${{esc(p.source_tab || '')}}</div>
      </div>
    `).join('')
  }}</div>`;
}}

function gameTimeValue(g) {{
  return g.game_time_et || g.start_time_et || g.startTimeEt || g.gameTimeET || (g.ml_lean && g.ml_lean.game_time_et) || null;
}}

function renderGames() {{
  const mount = document.getElementById('games');
  const games = APP_DATA.games || [];
  if (!games.length) {{
    mount.innerHTML = `<div class="card"><h2>No games available</h2></div>`;
    return;
  }}
  mount.innerHTML = `<div class="grid">${{
    games.map(g => `
      <div class="card">
        <h2>${{esc(g.game)}}</h2>
        <p><strong>Start Time:</strong> ${{esc(gameTimeValue(g) || 'not available yet')}}</p>
        ${g.venue ? `<p><strong>Venue:</strong> ${{esc(g.venue)}}</p>` : ``}
        <div class="kv"><strong>ML Lean:</strong> ${{esc(g.ml_lean?.team)}} (edge ${{esc(g.ml_lean?.edge_vs_opponent)}})</div>
        <div class="muted">${{esc(g.ml_lean?.recommended_play || '')}}</div>
        <h3 style="margin-top:20px;">Top Hit Picks</h3>
        <p>${{(g.top_hit_picks || []).length ? g.top_hit_picks.map(p => esc(p.playerName)+' ('+esc(p.teamName)+')').join('<br>') : '—'}}</p>
        <h3 style="margin-top:20px;">Top HR Picks</h3>
        <p>${{(g.top_hr_picks || []).length ? g.top_hr_picks.map(p => esc(p.playerName)+' ('+esc(p.teamName)+')').join('<br>') : '—'}}</p>
        <h3 style="margin-top:20px;">Top K Pick</h3>
        <p>${{g.top_k_pick ? esc(g.top_k_pick.pitcherName)+' ('+esc(g.top_k_pick.teamName)+') — '+esc(g.top_k_pick.recommended_k_action) : '—'}}</p>
      </div>
    `).join('')
  }}</div>`;
}}

function prettyLabel(key) {{
  const labels = {{
    game_rankings: 'Game Rankings',
    pitcher_metrics: 'Pitcher Metrics',
    pitcher_line_value: 'Pitcher Line Value',
    hr_drought: 'HR Drought',
    hit_drought: 'Hit Drought',
    top_picks: 'Top Picks',
    refined_picks: 'Refined Picks',
    final_card: 'Final Card'
  }};
  return labels[key] || key;
}}

function renderResearchHome() {{
  const home = document.getElementById('researchHome');
  const research = APP_DATA.research || {{}};
  const keys = Object.keys(research).filter(k => Array.isArray(research[k]));
  home.innerHTML = `<div class="research-grid">${{
    keys.map(key => `
      <div class="research-card" onclick="openResearchTable('${{key}}')">
        <h3>${{prettyLabel(key)}}</h3>
        <p>${{research[key].length}} rows</p>
      </div>
    `).join('')
  }}</div>`;
}}

function backToResearchHome() {{
  CURRENT_RESEARCH_KEY = null;
  document.getElementById('researchHome').classList.remove('hidden');
  document.getElementById('researchDetail').classList.add('hidden');
}}

function buildGenericFilters(key, rows) {{
  return `
    <div class="filters">
      <div class="filter-row">
        <input id="searchBox" placeholder="Search this table" oninput="applyResearchFilters()">
      </div>
    </div>
  `;
}}

function buildDroughtFilters(key, rows) {{
  const teams = [...new Set(rows.map(r => r.teamName).filter(Boolean))].sort();
  const statuses = [...new Set(rows.map(r => r.status).filter(Boolean))].sort();
  const parks = [...new Set(rows.map(r => r.park_favorability).filter(Boolean))].sort();
  const oppTypes = [...new Set(rows.map(r => r.opponent_pitcher_pick_type).filter(Boolean))].sort();
  const opts = arr => arr.map(v => `<option value="${esc(v)}">${esc(v)}</option>`).join('');
  return `
    <div class="filters">
      <div class="filter-row">
        <input id="searchBox" placeholder="Search this table" oninput="applyResearchFilters()">
        <label><input type="checkbox" id="overdueOnly" onchange="applyResearchFilters()"> Overdue only</label>
        <input id="minDrought" type="number" min="0" step="1" placeholder="Min drought" oninput="applyResearchFilters()">
      </div>
      <div class="filter-row">
        <select id="teamFilter" onchange="applyResearchFilters()">
          <option value="">All Teams</option>${opts(teams)}
        </select>
        <select id="statusFilter" onchange="applyResearchFilters()">
          <option value="">All Statuses</option>${opts(statuses)}
        </select>
        <select id="parkFilter" onchange="applyResearchFilters()">
          <option value="">All Parks</option>${opts(parks)}
        </select>
        <select id="oppTypeFilter" onchange="applyResearchFilters()">
          <option value="">All Opp Pitcher Types</option>${opts(oppTypes)}
        </select>
        <button class="btn" onclick="clearResearchFilters()">Clear Filters</button>
      </div>
    </div>
  `;
}}

function tableHtml(rows) {{
  if (!rows.length) return `<div class="card"><h3>No rows match current filters</h3></div>`;
  const cols = [...new Set(rows.flatMap(r => Object.keys(r)))];
  return `
    <div class="table-wrap">
      <table>
        <thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead>
        <tbody>
          ${rows.map(r => `<tr>${cols.map(c => `<td>${esc(r[c])}</td>`).join('')}</tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;
}}

function openResearchTable(key) {{
  CURRENT_RESEARCH_KEY = key;
  document.getElementById('researchHome').classList.add('hidden');
  document.getElementById('researchDetail').classList.remove('hidden');
  const rows = (APP_DATA.research && APP_DATA.research[key]) ? APP_DATA.research[key] : [];
  const filtersMount = document.getElementById('researchFilters');
  filtersMount.innerHTML = (key === 'hr_drought' || key === 'hit_drought') ? buildDroughtFilters(key, rows) : buildGenericFilters(key, rows);
  renderResearchTable(rows);
}}

function applyResearchFilters() {{
  if (!CURRENT_RESEARCH_KEY) return;
  let rows = ((APP_DATA.research || {{}})[CURRENT_RESEARCH_KEY] || []).slice();
  const q = (document.getElementById('searchBox')?.value || '').trim().toLowerCase();
  if (q) {{
    rows = rows.filter(r => Object.values(r).some(v => String(v ?? '').toLowerCase().includes(q)));
  }}
  if (CURRENT_RESEARCH_KEY === 'hr_drought' || CURRENT_RESEARCH_KEY === 'hit_drought') {{
    const overdueOnly = document.getElementById('overdueOnly')?.checked;
    const minDrought = parseFloat(document.getElementById('minDrought')?.value || '');
    const team = document.getElementById('teamFilter')?.value || '';
    const status = document.getElementById('statusFilter')?.value || '';
    const park = document.getElementById('parkFilter')?.value || '';
    const oppType = document.getElementById('oppTypeFilter')?.value || '';
    if (overdueOnly) rows = rows.filter(r => String(r.status || '').toLowerCase().includes('overdue'));
    if (!Number.isNaN(minDrought)) {{
      const field = CURRENT_RESEARCH_KEY === 'hr_drought' ? 'current_games_without_hr' : 'current_games_without_hit';
      rows = rows.filter(r => Number(r[field] || 0) >= minDrought);
    }}
    if (team) rows = rows.filter(r => String(r.teamName || '') === team);
    if (status) rows = rows.filter(r => String(r.status || '') === status);
    if (park) rows = rows.filter(r => String(r.park_favorability || '') === park);
    if (oppType) rows = rows.filter(r => String(r.opponent_pitcher_pick_type || '') === oppType);
  }}
  renderResearchTable(rows);
}}

function clearResearchFilters() {{
  ['searchBox','minDrought'].forEach(id => {{ const el = document.getElementById(id); if (el) el.value=''; }});
  ['teamFilter','statusFilter','parkFilter','oppTypeFilter'].forEach(id => {{ const el = document.getElementById(id); if (el) el.value=''; }});
  const chk = document.getElementById('overdueOnly'); if (chk) chk.checked = false;
  applyResearchFilters();
}}

function renderResearchTable(rows) {{
  document.getElementById('researchTable').innerHTML = tableHtml(rows);
}}

async function reloadApp() {{
  const btn = document.getElementById('reloadBtn');
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Reloading...';
  try {{
    const res = await fetch('/latest?t=' + Date.now(), {{ cache: 'no-store' }});
    const data = await res.json();
    APP_DATA = data;
    document.getElementById('dateText').textContent = APP_DATA.date || 'N/A';
    document.getElementById('updatedText').textContent = (APP_DATA._meta && APP_DATA._meta.eastern_now) ? APP_DATA._meta.eastern_now : 'Not available';
    renderFinalCard();
    renderGames();
    renderResearchHome();
    if (CURRENT_RESEARCH_KEY) openResearchTable(CURRENT_RESEARCH_KEY);
  }} catch (e) {{
    alert('Reload failed.');
  }} finally {{
    btn.disabled = false;
    btn.textContent = original;
  }}
}}

renderFinalCard();
renderGames();
renderResearchHome();
</script>
</body>
</html>
"""
    return HTMLResponse(html)
