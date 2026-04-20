
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def get_latest_json_file() -> Path | None:
    patterns = [
        "HR_Hit_Drought_v41_appdata-*.json",
        "HR_Hit_Drought_v40_appdata-*.json",
        "HR_Hit_Drought_v41_appdata-*.JSON",
        "HR_Hit_Drought_v40_appdata-*.JSON",
    ]
    files: list[Path] = []
    for pat in patterns:
        files.extend(OUTPUT_DIR.glob(pat))
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def load_latest_data() -> dict:
    latest_file = get_latest_json_file()
    if not latest_file:
        return {
            "date": None,
            "final_card": {"generated_section": "final_card", "plays": []},
            "games": [],
            "research": {},
            "_meta": {"filename": None, "path": None, "eastern_now": None},
        }

    with open(latest_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta = data.get("_meta", {})
    eastern_now = meta.get("eastern_now")
    if not eastern_now:
        try:
            modified = dt.datetime.fromtimestamp(latest_file.stat().st_mtime, tz=ZoneInfo("America/New_York"))
            eastern_now = modified.strftime("%b %d, %Y %I:%M %p ET").replace(" 0", " ")
        except Exception:
            eastern_now = None

    data["_meta"] = {
        "filename": latest_file.name,
        "path": str(latest_file),
        "eastern_now": eastern_now,
    }
    return data


def format_game_time_value(v: str | None) -> str | None:
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    return s


def games_with_time_fallback(data: dict) -> list[dict]:
    games = list(data.get("games") or [])
    rankings = data.get("research", {}).get("game_rankings", []) or []

    rank_lookup: dict[str, dict] = {}
    for row in rankings:
        game = row.get("game")
        if game and game not in rank_lookup:
            rank_lookup[game] = row

    out = []
    for g in games:
        g2 = dict(g)
        fallback = rank_lookup.get(g.get("game"), {})
        game_time = (
            g.get("game_time_et")
            or g.get("start_time_et")
            or g.get("start_time")
            or fallback.get("game_time_et")
            or fallback.get("start_time_et")
            or fallback.get("start_time")
        )
        venue = g.get("venue") or fallback.get("venue")
        g2["game_time_et"] = format_game_time_value(game_time)
        g2["venue"] = venue
        out.append(g2)

    def sort_key(g: dict):
        raw = g.get("game_time_et") or ""
        if not raw:
            return (99, 99)
        try:
            txt = raw.replace(" ET", "").strip()
            t = dt.datetime.strptime(txt, "%I:%M %p")
            return (t.hour, t.minute)
        except Exception:
            return (99, 99)

    out.sort(key=sort_key)
    return out


def esc_js_text(v) -> str:
    return json.dumps("" if v is None else str(v), ensure_ascii=False)


@app.get("/latest")
def latest():
    return JSONResponse(load_latest_data())


@app.get("/refresh-data")
def refresh_data():
    import hr_v41_cloud_ready  # local import so app can still start if backend changes

    eastern = ZoneInfo("America/New_York")
    today = dt.datetime.now(eastern).date().isoformat()
    hr_v41_cloud_ready.main(2026, today)
    return JSONResponse({
        "status": "ok",
        "message": "Data refreshed",
        "date": today,
        "timezone": "America/New_York",
    })


@app.get("/app")
def app_page():
    data = load_latest_data()
    data["games"] = games_with_time_fallback(data)

    initial_data_json = json.dumps(data, ensure_ascii=False)

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>HR Picks App</title>
  <style>
    :root {{
      --bg: #020617;
      --card: #111827;
      --card2: #0f172a;
      --text: #f8fafc;
      --muted: #cbd5e1;
      --line: #24324d;
      --pill: #22314f;
      --accent: #5b8cff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    .wrap {{ max-width: 1720px; margin: 0 auto; padding: 20px 24px 40px; }}
    .topbar {{
      display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom: 18px;
    }}
    h1 {{
      margin:0 0 8px 0; font-size: 3.8rem; line-height: 1; font-weight: 900; letter-spacing: -.04em;
    }}
    .sub {{
      color: var(--muted); font-size: 1rem;
    }}
    .reload-btn, .tab-btn, .back-btn, .card-btn, select, input {{
      border-radius: 18px; border:1px solid #334155; color: white; background:#182235;
      font-size: 1rem;
    }}
    .reload-btn {{
      background: #638bf5; border-color:#638bf5; padding: 14px 24px; font-weight: 800; cursor:pointer;
      color: white; min-width: 160px;
    }}
    .reload-btn:disabled {{ opacity:.7; cursor: wait; }}
    .tabs {{ display:flex; gap:16px; margin: 20px 0 24px; flex-wrap: wrap; }}
    .tab-btn {{
      padding: 12px 22px; cursor:pointer; background:#162033;
    }}
    .tab-btn.active {{ background:#263754; }}
    .panel {{ display:none; }}
    .panel.active {{ display:block; }}
    .grid {{
      display:grid; grid-template-columns: repeat(4, minmax(260px, 1fr)); gap:18px;
    }}
    .card {{
      background: linear-gradient(180deg, rgba(17,24,39,.96), rgba(15,23,42,.98));
      border:1px solid var(--line); border-radius: 28px; padding: 22px 24px; box-shadow: 0 0 0 1px rgba(255,255,255,0.02) inset;
    }}
    .card h3 {{ margin:0 0 10px 0; font-size: 1.1rem; }}
    .muted {{ color: var(--muted); }}
    .small {{ font-size: .95rem; }}
    .game-grid {{ display:grid; grid-template-columns: repeat(3, minmax(300px,1fr)); gap:18px; }}
    .game-card h2 {{ margin:0 0 16px 0; font-size: 1.15rem; line-height: 1.2; }}
    .section-label {{ font-weight: 800; font-size: 1rem; margin-top: 16px; }}
    .bullet-list {{ margin: 8px 0 0 18px; padding:0; }}
    .bullet-list li {{ margin: 6px 0; }}
    .hero-grid {{ display:grid; grid-template-columns: repeat(3, minmax(260px,1fr)); gap:22px; }}
    .play-card .slot {{
      display:inline-block; padding:6px 12px; background:var(--pill); border-radius:999px; color:#dbeafe; font-size:.9rem; margin-bottom: 10px;
    }}
    .play-card h2 {{ margin:0 0 14px 0; font-size: 1.15rem; line-height: 1.15; }}
    .kv {{ margin: 6px 0; font-size: 1rem; }}
    .research-grid {{ display:grid; grid-template-columns: repeat(4, minmax(260px, 1fr)); gap:18px; }}
    .research-card {{ cursor:pointer; }}
    .research-card h3 {{ font-size: 1.2rem; margin:0 0 14px 0; }}
    .toolbar {{
      display:flex; gap:12px; flex-wrap: wrap; margin-bottom: 16px; align-items:center;
    }}
    .toolbar input, .toolbar select {{
      padding: 12px 14px; background:#091223; min-width: 220px;
    }}
    .back-btn {{
      padding: 12px 18px; background:#091223; cursor:pointer; margin: 4px 0 18px;
    }}
    table {{ width:100%; border-collapse: collapse; }}
    th, td {{
      text-align:left; padding: 12px 10px; border-bottom:1px solid #24324d; vertical-align: top;
      font-size: .98rem;
    }}
    th {{ font-weight: 800; }}
    .table-wrap {{ overflow:auto; background: transparent; }}
    .status {{
      display:inline-block; padding: 4px 10px; border-radius:999px; background:#1f2b45; font-size:.9rem;
    }}
    @media (max-width: 1400px) {{
      .research-grid {{ grid-template-columns: repeat(3, minmax(260px, 1fr)); }}
      .game-grid {{ grid-template-columns: repeat(2, minmax(300px,1fr)); }}
    }}
    @media (max-width: 980px) {{
      h1 {{ font-size: 3rem; }}
      .hero-grid, .game-grid, .grid, .research-grid {{ grid-template-columns: 1fr; }}
      .topbar {{ flex-direction:column; }}
      .reload-btn {{ align-self:flex-start; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <h1>HR Picks App</h1>
        <div class="sub" id="headerSub"></div>
      </div>
      <button class="reload-btn" id="reloadBtn" onclick="reloadApp()">Reload App</button>
    </div>

    <div class="tabs">
      <button class="tab-btn active" onclick="showPanel('finalCardPanel', this)">Final Card</button>
      <button class="tab-btn" onclick="showPanel('gamesPanel', this)">Games</button>
      <button class="tab-btn" onclick="showPanel('researchPanel', this)">Research</button>
    </div>

    <div id="finalCardPanel" class="panel active"></div>
    <div id="gamesPanel" class="panel"></div>
    <div id="researchPanel" class="panel"></div>
  </div>

<script>
const initialData = {initial_data_json};
let appData = initialData;
let researchState = {{
  openKey: null,
  search: '',
  column: '__all__',
  sort: ''
}};

function esc(v) {{
  if (v === null || v === undefined) return '';
  return String(v)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}}

function showPanel(id, btn) {{
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}}

function fmtHeader() {{
  const d = appData.date || '—';
  const u = appData._meta?.eastern_now || '—';
  document.getElementById('headerSub').innerHTML = `Date: ${esc(d)} • Last Updated: ${esc(u)}`;
}}

function timeToSortValue(t) {{
  if (!t) return 99999;
  const m = String(t).match(/(\\d{{1,2}}):(\\d{{2}})\\s*(AM|PM)/i);
  if (!m) return 99999;
  let hh = parseInt(m[1], 10);
  const mm = parseInt(m[2], 10);
  const ap = m[3].toUpperCase();
  if (ap === 'PM' && hh !== 12) hh += 12;
  if (ap === 'AM' && hh === 12) hh = 0;
  return hh * 60 + mm;
}}

function getGamesSorted() {{
  const games = Array.isArray(appData.games) ? [...appData.games] : [];
  const rankings = appData.research?.game_rankings || [];
  const fallbackMap = new Map();
  rankings.forEach(r => {{
    if (r.game && !fallbackMap.has(r.game)) fallbackMap.set(r.game, r);
  }});
  games.forEach(g => {{
    const fb = fallbackMap.get(g.game) || {{}};
    g.game_time_et = g.game_time_et || g.start_time_et || g.start_time || fb.game_time_et || fb.start_time_et || fb.start_time || null;
    g.venue = g.venue || fb.venue || null;
  }});
  games.sort((a,b) => timeToSortValue(a.game_time_et) - timeToSortValue(b.game_time_et));
  return games;
}}

function renderFinalCard() {{
  const panel = document.getElementById('finalCardPanel');
  const plays = appData.final_card?.plays || [];
  if (!plays.length) {{
    panel.innerHTML = `<div class="card">No final card plays available.</div>`;
    return;
  }}
  panel.innerHTML = `<div class="hero-grid">${plays.map(p => `
    <div class="card play-card">
      <div class="slot">${esc(p.slot || '')}</div>
      <h2>${esc(p.pick || '—')}</h2>
      <div class="kv"><strong>Bet Type:</strong> ${esc(p.bet_type || '—')}</div>
      <div class="kv"><strong>Team:</strong> ${esc(p.team || '—')}</div>
      <div class="kv"><strong>Opponent:</strong> ${esc(p.opponent || '—')}</div>
      <div class="kv"><strong>Confidence:</strong> ${esc(p.confidence || '—')}</div>
      <div class="kv muted">${esc(p.why_it_made_the_card || '')}</div>
      <div class="kv muted">Source: ${esc(p.source_tab || '—')}</div>
    </div>
  `).join('')}</div>`;
}}

function renderGames() {{
  const panel = document.getElementById('gamesPanel');
  const games = getGamesSorted();
  if (!games.length) {{
    panel.innerHTML = `<div class="card">No games available.</div>`;
    return;
  }}
  panel.innerHTML = `<div class="game-grid">${games.map(g => `
    <div class="card game-card">
      <h2>${esc(g.game || '—')}</h2>
      <div class="kv"><strong>Start Time:</strong> ${esc(g.game_time_et || 'not available yet')}</div>
      ${g.venue ? `<div class="kv"><strong>Venue:</strong> ${esc(g.venue)}</div>` : ``}
      <div class="kv"><strong>ML Lean:</strong> ${esc(g.ml_lean?.team || '—')} ${g.ml_lean?.edge_vs_opponent !== undefined && g.ml_lean?.edge_vs_opponent !== null ? `(edge ${esc(g.ml_lean.edge_vs_opponent)})` : ''}</div>
      <div class="kv muted">${esc(g.ml_lean?.recommended_play || '')}</div>

      <div class="section-label">Top Hit Picks</div>
      ${g.top_hit_picks?.length ? `<ul class="bullet-list">${g.top_hit_picks.map(x => `<li>${esc(x.playerName)} (${esc(x.teamName)})</li>`).join('')}</ul>` : `<ul class="bullet-list"><li>—</li></ul>`}

      <div class="section-label">Top HR Picks</div>
      ${g.top_hr_picks?.length ? `<ul class="bullet-list">${g.top_hr_picks.map(x => `<li>${esc(x.playerName)} (${esc(x.teamName)})</li>`).join('')}</ul>` : `<ul class="bullet-list"><li>—</li></ul>`}

      <div class="section-label">Top K Pick</div>
      <div class="kv">${g.top_k_pick ? `${esc(g.top_k_pick.pitcherName)} (${esc(g.top_k_pick.teamName)}) — ${esc(g.top_k_pick.recommended_k_action)}` : '—'}</div>
    </div>
  `).join('')}</div>`;
}}

function labelForKey(key) {{
  const map = {{
    game_rankings: 'Game Rankings',
    pitcher_metrics: 'Pitcher Metrics',
    pitcher_line_value: 'Pitcher Line Value',
    hr_drought: 'HR Drought',
    hit_drought: 'Hit Drought',
    top_picks: 'Top Picks',
    refined_picks: 'Refined Picks'
  }};
  return map[key] || key;
}}

function renderResearchHome() {{
  const panel = document.getElementById('researchPanel');
  const research = appData.research || {{}};
  const keys = ['game_rankings','pitcher_metrics','pitcher_line_value','hr_drought','hit_drought','top_picks','refined_picks'];
  panel.innerHTML = `<div class="research-grid">${keys.map(key => `
    <div class="card research-card" onclick="openResearch('${key}')">
      <h3>${esc(labelForKey(key))}</h3>
      <div class="muted">${Array.isArray(research[key]) ? research[key].length : 0} rows</div>
    </div>
  `).join('')}</div>`;
}}

function openResearch(key) {{
  researchState.openKey = key;
  researchState.search = '';
  researchState.column = '__all__';
  researchState.sort = '';
  renderResearchDetail();
}}

function backToResearch() {{
  researchState.openKey = null;
  renderResearchHome();
}}

function setResearchSearch(v) {{
  researchState.search = v || '';
  renderResearchDetail();
}}

function setResearchColumn(v) {{
  researchState.column = v || '__all__';
  renderResearchDetail();
}}

function setResearchSort(v) {{
  researchState.sort = v || '';
  renderResearchDetail();
}}

function applyResearchFilters(rows, columns) {{
  let out = [...rows];
  const q = researchState.search.trim().toLowerCase();
  if (q) {{
    out = out.filter(r => {{
      if (researchState.column && researchState.column !== '__all__') {{
        return String(r[researchState.column] ?? '').toLowerCase().includes(q);
      }}
      return columns.some(c => String(r[c] ?? '').toLowerCase().includes(q));
    }});
  }}
  if (researchState.sort === 'asc' || researchState.sort === 'desc') {{
    const primaryCol =
      columns.find(c => /playerName/i.test(c)) ||
      columns.find(c => /teamName/i.test(c)) ||
      columns[0];
    out.sort((a,b) => {{
      const av = String(a[primaryCol] ?? '').toLowerCase();
      const bv = String(b[primaryCol] ?? '').toLowerCase();
      return researchState.sort === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    }});
  }}
  return out;
}}

function renderResearchDetail() {{
  const panel = document.getElementById('researchPanel');
  const key = researchState.openKey;
  const rows = appData.research?.[key] || [];
  const columns = rows.length ? Object.keys(rows[0]) : [];

  const filtered = applyResearchFilters(rows, columns);

  panel.innerHTML = `
    <button class="back-btn" onclick="backToResearch()">← Back</button>
    <div class="card">
      <h3 style="margin-top:0; font-size:1.8rem;">${esc(labelForKey(key))}</h3>
      <div class="toolbar">
        <input type="text" placeholder="Search this table" value="${esc(researchState.search)}" oninput="setResearchSearch(this.value)" />
        <select onchange="setResearchColumn(this.value)">
          <option value="__all__"${researchState.column === '__all__' ? ' selected' : ''}>All columns</option>
          ${columns.map(c => `<option value="${esc(c)}"${researchState.column === c ? ' selected' : ''}>${esc(c)}</option>`).join('')}
        </select>
        <select onchange="setResearchSort(this.value)">
          <option value=""${!researchState.sort ? ' selected' : ''}>Sort</option>
          <option value="asc"${researchState.sort === 'asc' ? ' selected' : ''}>A → Z</option>
          <option value="desc"${researchState.sort === 'desc' ? ' selected' : ''}>Z → A</option>
        </select>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr>${columns.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead>
          <tbody>
            ${filtered.map(r => `<tr>${columns.map(c => `<td>${esc(r[c] ?? '')}</td>`).join('')}</tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}}

async function reloadApp() {{
  const btn = document.getElementById('reloadBtn');
  const oldText = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Reloading...';
  try {{
    const res = await fetch(`/latest?t=${{Date.now()}}`, {{ cache: 'no-store' }});
    const data = await res.json();
    data.games = getGamesSortedFromIncoming(data);
    appData = data;
    researchState.openKey = null;
    fmtHeader();
    renderFinalCard();
    renderGames();
    renderResearchHome();
  }} catch (e) {{
    console.error(e);
    alert('Reload failed.');
  }} finally {{
    btn.disabled = false;
    btn.textContent = oldText;
  }}
}}

function getGamesSortedFromIncoming(data) {{
  const games = Array.isArray(data.games) ? [...data.games] : [];
  const rankings = data.research?.game_rankings || [];
  const fallbackMap = new Map();
  rankings.forEach(r => {{
    if (r.game && !fallbackMap.has(r.game)) fallbackMap.set(r.game, r);
  }});
  games.forEach(g => {{
    const fb = fallbackMap.get(g.game) || {{}};
    g.game_time_et = g.game_time_et || g.start_time_et || g.start_time || fb.game_time_et || fb.start_time_et || fb.start_time || null;
    g.venue = g.venue || fb.venue || null;
  }});
  games.sort((a,b) => timeToSortValue(a.game_time_et) - timeToSortValue(b.game_time_et));
  return games;
}}

fmtHeader();
renderFinalCard();
renderGames();
renderResearchHome();
</script>
</body>
</html>"""
    return HTMLResponse(html)
