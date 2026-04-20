from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
from pathlib import Path
import json
import datetime as dt
from zoneinfo import ZoneInfo

from hr_v41_cloud_ready import main as run_model_main

app = FastAPI()

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def get_latest_json_file():
    patterns = [
        "HR_Hit_Drought_v41_appdata-*.json",
        "HR_Hit_Drought_v40_appdata-*.json",
    ]
    files = []
    for pat in patterns:
        files.extend(OUTPUT_DIR.glob(pat))
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def load_latest_data():
    latest = get_latest_json_file()
    if not latest:
        return {
            "date": None,
            "final_card": {"generated_section": "final_card", "plays": []},
            "games": [],
            "research": {},
            "_meta": {"filename": None, "last_updated_display": None},
        }

    with open(latest, "r", encoding="utf-8") as f:
        data = json.load(f)

    display = None
    eastern_now = None
    try:
        eastern_now = dt.datetime.fromtimestamp(latest.stat().st_mtime, ZoneInfo("America/New_York"))
        display = eastern_now.strftime("%b %d, %Y %I:%M %p ET").replace(" 0", " ")
    except Exception:
        pass

    data["_meta"] = {
        "filename": latest.name,
        "path": str(latest),
        "last_updated_display": display,
        "eastern_now": eastern_now.strftime("%Y-%m-%d %I:%M %p ET").replace(" 0", " ") if eastern_now else None,
    }
    return data


@app.get("/latest")
def latest():
    return JSONResponse(load_latest_data())


@app.get("/refresh-data")
def refresh_data():
    today = dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    run_model_main(2026, today)
    return JSONResponse({"status": "ok", "message": "Data refreshed", "date": today, "timezone": "America/New_York"})


@app.get("/")
@app.get("/app")
def app_view():
    html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HR Picks App</title>
  <style>
    :root {
      --bg: #050914;
      --card: #121925;
      --card2: #0e1522;
      --border: #26324a;
      --text: #eef2f8;
      --muted: #b8c1d1;
      --accent: #4c83ff;
      --accent2: #2f5ec7;
      --chip: #172132;
      --soft: #0c1320;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    .wrap { max-width: 1520px; margin: 0 auto; padding: 18px 22px 48px; }
    h1 { margin: 0 0 6px; font-size: 68px; line-height: 0.95; font-weight: 900; letter-spacing: -1px; }
    .meta { color: var(--muted); font-size: 18px; margin-bottom: 18px; }
    .topbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
    .btn {
      background: var(--accent);
      color: white;
      border: 0;
      border-radius: 16px;
      padding: 14px 22px;
      font-weight: 800;
      font-size: 16px;
      cursor: pointer;
      box-shadow: 0 8px 24px rgba(76,131,255,.2);
    }
    .btn:hover { background: var(--accent2); }
    .btn:disabled { opacity: .7; cursor: wait; }
    .btn.secondary {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text);
      box-shadow: none;
    }
    .tabs { display: flex; gap: 12px; flex-wrap: wrap; margin: 18px 0 22px; }
    .tab {
      background: var(--chip);
      border: 1px solid var(--border);
      color: var(--text);
      border-radius: 999px;
      padding: 12px 16px;
      cursor: pointer;
      font-size: 16px;
    }
    .tab.active { background: #24324d; }
    .hidden { display: none !important; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 18px; }
    .card {
      background: linear-gradient(180deg, var(--card), var(--card2));
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 22px 22px 18px;
      box-shadow: 0 14px 40px rgba(0,0,0,.25);
    }
    .card h2 { margin: 0 0 14px; font-size: 24px; line-height: 1.15; }
    .kicker { color: var(--muted); margin: 8px 0 18px; font-size: 15px; }
    .line { margin: 8px 0; font-size: 17px; color: var(--text); }
    .label { font-weight: 800; }
    .muted { color: var(--muted); }
    .pill {
      display: inline-block; padding: 4px 10px; border-radius: 999px; background: #1d2740; border: 1px solid var(--border);
      font-size: 13px; color: var(--muted);
    }
    .list { margin: 8px 0 0; padding-left: 18px; }
    .list li { margin: 6px 0; }
    .research-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
    .research-card { cursor: pointer; }
    .research-card:hover { border-color: #4a5f8b; }
    .research-title { font-size: 22px; font-weight: 900; margin-bottom: 10px; }
    .table-shell {
      background: linear-gradient(180deg, var(--card), var(--card2));
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 18px;
      overflow: hidden;
    }
    .toolbar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 14px; }
    .input, select {
      background: var(--soft);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 12px 14px;
      font-size: 15px;
      min-width: 180px;
    }
    .facet-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; margin: 6px 0 16px; }
    .facet-box {
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 12px;
      background: rgba(23,33,50,.35);
      min-height: 100px;
    }
    .facet-title { font-weight: 800; margin-bottom: 10px; }
    .facet-scroll { max-height: 180px; overflow: auto; padding-right: 4px; }
    .facet-item { display: flex; align-items: center; gap: 10px; margin: 8px 0; color: var(--muted); }
    .facet-item input { transform: scale(1.05); }
    .checkbox-inline { display: flex; align-items: center; gap: 10px; color: var(--text); }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td {
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid #1f2940;
      vertical-align: top;
      white-space: nowrap;
    }
    td.wrap, th.wrap { white-space: normal; }
    th { color: var(--text); position: sticky; top: 0; background: #0f1726; z-index: 1; }
    td { color: var(--muted); }
    .table-wrap { overflow: auto; max-height: 70vh; border-radius: 16px; }
    .backrow { margin-bottom: 14px; }
    .subhead { font-size: 13px; color: var(--muted); margin-top: -4px; margin-bottom: 8px; }
    @media (max-width: 700px) {
      h1 { font-size: 54px; }
      .wrap { padding: 18px 16px 38px; }
      .cards { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <h1>HR Picks App</h1>
        <div id="meta" class="meta">Loading...</div>
      </div>
      <div>
        <button class="btn" id="reloadBtn">Reload App</button>
      </div>
    </div>

    <div class="tabs">
      <button class="tab active" data-view="final">Final Card</button>
      <button class="tab" data-view="games">Games</button>
      <button class="tab" data-view="research">Research</button>
    </div>

    <section id="view-final"></section>
    <section id="view-games" class="hidden"></section>
    <section id="view-research" class="hidden"></section>
  </div>

<script>
let APP_DATA = null;
let currentView = "final";
let CURRENT_RESEARCH_KEY = null;
let CURRENT_RESEARCH_ROWS = [];

function esc(v) {
  if (v === null || v === undefined) return "";
  return String(v)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fmt(v) {
  if (v === null || v === undefined || v === "") return "—";
  return typeof v === "number" ? String(v) : String(v);
}

function titleize(key) {
  return String(key || "").replaceAll("_", " ").replace(/\b\w/g, m => m.toUpperCase());
}

function parseEtTimeToMinutes(t) {
  if (!t) return 99999;
  const s = String(t).toUpperCase().replace("ET", "").trim();
  const m = s.match(/(\d{1,2}):(\d{2})\s*(AM|PM)/);
  if (!m) return 99999;
  let hh = parseInt(m[1], 10);
  const mm = parseInt(m[2], 10);
  const ap = m[3];
  if (ap === "PM" && hh !== 12) hh += 12;
  if (ap === "AM" && hh === 12) hh = 0;
  return hh * 60 + mm;
}

function buildGameTimeLookup() {
  const map = {};
  const games = APP_DATA?.games || [];
  games.forEach(g => {
    const gameName = g?.game;
    if (gameName) {
      map[gameName] = g.game_time_et || g.start_time_et || g.startTimeEt || g.game_datetime_utc || null;
    }
  });
  const rankings = APP_DATA?.research?.game_rankings || [];
  rankings.forEach(r => {
    const gameName = r?.game;
    if (gameName && !map[gameName]) {
      map[gameName] = r.game_time_et || r.start_time_et || r.startTimeEt || r.game_datetime_utc || null;
    }
  });
  return map;
}

function setMeta() {
  const date = APP_DATA?.date || "—";
  const lu = APP_DATA?._meta?.last_updated_display || "—";
  document.getElementById("meta").textContent = "Date: " + date + " • Last Updated: " + lu;
}

async function loadData() {
  const res = await fetch("/latest?t=" + Date.now(), { cache: "no-store" });
  APP_DATA = await res.json();
  renderAll();
}

function finalCardRows() {
  const plays = APP_DATA?.final_card?.plays;
  if (Array.isArray(plays) && plays.length) return plays;
  const fallback = APP_DATA?.research?.final_card;
  return Array.isArray(fallback) ? fallback : [];
}

function renderFinal() {
  const mount = document.getElementById("view-final");
  const plays = finalCardRows();
  if (!plays.length) {
    mount.innerHTML = '<div class="card"><h2>No final card available.</h2></div>';
    return;
  }
  mount.innerHTML = '<div class="cards">' + plays.map(p => `
    <div class="card">
      <div class="pill">${esc(fmt(p.slot || p.play_type || p.section || "Play"))}</div>
      <h2>${esc(fmt(p.pick || p.playerName || "Play"))}</h2>
      <div class="line"><span class="label">Bet Type:</span> ${esc(fmt(p.bet_type))}</div>
      <div class="line"><span class="label">Team:</span> ${esc(fmt(p.team || p.teamName))}</div>
      <div class="line"><span class="label">Opponent:</span> ${esc(fmt(p.opponent || p.opponentTeam))}</div>
      <div class="line"><span class="label">Confidence:</span> ${esc(fmt(p.confidence))}</div>
      <div class="kicker">${esc(fmt(p.why_it_made_the_card || p.reason))}</div>
      <div class="muted">Source: ${esc(fmt(p.source_tab))}</div>
    </div>
  `).join("") + "</div>";
}

function normalizedGames() {
  const rawGames = Array.isArray(APP_DATA?.games) ? APP_DATA.games.slice() : [];
  const timeMap = buildGameTimeLookup();
  return rawGames.map(g => {
    const time = g.game_time_et || g.start_time_et || g.startTimeEt || timeMap[g.game] || null;
    return { ...g, _sortTime: parseEtTimeToMinutes(time), _displayTime: time || "not available yet" };
  }).sort((a, b) => a._sortTime - b._sortTime || String(a.game || "").localeCompare(String(b.game || "")));
}

function renderGames() {
  const mount = document.getElementById("view-games");
  const games = normalizedGames();
  if (!games.length) {
    mount.innerHTML = '<div class="card"><h2>No game cards available.</h2></div>';
    return;
  }

  mount.innerHTML = '<div class="cards">' + games.map(g => {
    const venueHtml = g.venue ? `<p class="line"><span class="label">Venue:</span> ${esc(g.venue)}</p>` : "";
    const hits = (g.top_hit_picks || []).map(x => `<li>${esc(x.playerName)} (${esc(x.teamName)})</li>`).join("") || "<li>—</li>";
    const hrs = (g.top_hr_picks || []).map(x => `<li>${esc(x.playerName)} (${esc(x.teamName)})</li>`).join("") || "<li>—</li>";
    const kp = g.top_k_pick
      ? `${esc(fmt(g.top_k_pick.pitcherName))} (${esc(fmt(g.top_k_pick.teamName))}) — ${esc(fmt(g.top_k_pick.recommended_k_action))}`
      : "—";
    const ml = g.ml_lean || {};
    const mlPlay = `${esc(fmt(ml.team))} (edge ${esc(fmt(ml.edge_vs_opponent))})`;
    return `
      <div class="card">
        <h2>${esc(fmt(g.game))}</h2>
        <p class="line"><span class="label">Start Time:</span> ${esc(g._displayTime)}</p>
        ${venueHtml}
        <p class="line"><span class="label">ML Lean:</span> ${mlPlay}</p>
        <p class="muted">${esc(fmt(ml.recommended_play))}</p>
        <h2 style="font-size:20px;margin-top:18px;">Top Hit Picks</h2>
        <ul class="list">${hits}</ul>
        <h2 style="font-size:20px;margin-top:18px;">Top HR Picks</h2>
        <ul class="list">${hrs}</ul>
        <h2 style="font-size:20px;margin-top:18px;">Top K Pick</h2>
        <p class="line">${kp}</p>
      </div>
    `;
  }).join("") + '</div>';
}

function visibleResearchEntries() {
  const research = APP_DATA?.research || {};
  const hide = new Set(["final_card"]);
  return Object.entries(research).filter(([k, v]) => Array.isArray(v) && !hide.has(k));
}

function renderResearchHome() {
  const mount = document.getElementById("view-research");
  const entries = visibleResearchEntries();
  if (!entries.length) {
    mount.innerHTML = '<div class="card"><h2>No research tables available.</h2></div>';
    return;
  }
  mount.innerHTML = '<div class="research-grid">' + entries.map(([k, rows]) => `
    <div class="card research-card" data-key="${esc(k)}">
      <div class="research-title">${esc(titleize(k))}</div>
      <div class="muted">${rows.length} rows</div>
    </div>
  `).join("") + '</div>';

  mount.querySelectorAll(".research-card").forEach(el => {
    el.addEventListener("click", () => openResearchTable(el.dataset.key));
  });
}

function uniqueValues(rows, key) {
  const set = new Set();
  rows.forEach(r => {
    const v = r[key];
    if (v !== null && v !== undefined && String(v).trim() !== "") set.add(String(v));
  });
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

function buildFacetBox(label, key, values) {
  if (!values.length) return "";
  const checks = values.map(v => `
    <label class="facet-item">
      <input type="checkbox" class="facet-check" data-key="${esc(key)}" value="${esc(v)}">
      <span>${esc(v)}</span>
    </label>
  `).join("");
  return `
    <div class="facet-box">
      <div class="facet-title">${esc(label)}</div>
      <div class="facet-scroll">${checks}</div>
    </div>
  `;
}

function openResearchTable(key) {
  CURRENT_RESEARCH_KEY = key;
  CURRENT_RESEARCH_ROWS = APP_DATA?.research?.[key] || [];

  const rows = CURRENT_RESEARCH_ROWS;
  const mount = document.getElementById("view-research");
  const columns = rows.length ? Object.keys(rows[0]) : [];
  const options = columns.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join("");

  const facets = [];
  const facetColumns = [
    ["Teams", "teamName"],
    ["Status", "status"],
    ["Park", "park_favorability"],
    ["Opponent Pitcher Type", "opponent_pitcher_pick_type"],
    ["Lineup Status", "lineup_status"]
  ];
  facetColumns.forEach(([label, keyName]) => {
    if (columns.includes(keyName)) {
      facets.push(buildFacetBox(label, keyName, uniqueValues(rows, keyName)));
    }
  });

  const numericFilters = [];
  if (columns.includes("avg_games_between_hrs")) {
    numericFilters.push('<input id="minAvgInput" class="input" placeholder="Min avg drought" oninput="filterResearchTable()">');
  }
  if (columns.includes("current_games_without_hr")) {
    numericFilters.push('<input id="minCurrentInput" class="input" placeholder="Min games since HR" oninput="filterResearchTable()">');
  }

  mount.innerHTML = `
    <div class="backrow">
      <button class="btn secondary" id="backBtn">← Back</button>
    </div>
    <div class="table-shell">
      <h2 style="margin-top:0;">${esc(titleize(key))}</h2>
      <div class="subhead">Search + filters are active for this table.</div>
      <div class="toolbar">
        <input id="searchBox" class="input" placeholder="Search this table" oninput="filterResearchTable()">
        <select id="columnSelect" onchange="filterResearchTable()">
          <option value="">All columns</option>
          ${options}
        </select>
        <label class="checkbox-inline">
          <input type="checkbox" id="overdueOnly" onchange="filterResearchTable()">
          <span>Overdue only</span>
        </label>
        ${numericFilters.join("")}
        <button class="btn secondary" id="clearFiltersBtn">Clear Filters</button>
      </div>
      ${facets.length ? `<div class="facet-grid">${facets.join("")}</div>` : ""}
      <div class="table-wrap">
        <table id="researchTable">
          <thead><tr>${columns.map(c => `<th class="${String(c).length > 18 ? 'wrap' : ''}">${esc(c)}</th>`).join("")}</tr></thead>
          <tbody>
            ${rows.map(r => `<tr>${columns.map(c => `<td class="${String(c).length > 18 ? 'wrap' : ''}">${esc(fmt(r[c]))}</td>`).join("")}</tr>`).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;

  document.getElementById("backBtn").addEventListener("click", renderResearchHome);
  const clearBtn = document.getElementById("clearFiltersBtn");
  clearBtn.addEventListener("click", clearResearchFilters);
  mount.querySelectorAll(".facet-check").forEach(el => {
    el.addEventListener("change", filterResearchTable);
  });

  filterResearchTable();
}

function clearResearchFilters() {
  const search = document.getElementById("searchBox");
  const col = document.getElementById("columnSelect");
  const overdue = document.getElementById("overdueOnly");
  const minAvg = document.getElementById("minAvgInput");
  const minCurrent = document.getElementById("minCurrentInput");

  if (search) search.value = "";
  if (col) col.value = "";
  if (overdue) overdue.checked = false;
  if (minAvg) minAvg.value = "";
  if (minCurrent) minCurrent.value = "";
  document.querySelectorAll(".facet-check").forEach(c => c.checked = false);
  filterResearchTable();
}

function selectedFacetMap() {
  const map = {};
  document.querySelectorAll(".facet-check:checked").forEach(el => {
    const key = el.dataset.key;
    map[key] = map[key] || new Set();
    map[key].add(String(el.value));
  });
  return map;
}

function filterResearchTable() {
  const search = (document.getElementById("searchBox")?.value || "").toLowerCase();
  const column = document.getElementById("columnSelect")?.value || "";
  const overdueOnly = !!document.getElementById("overdueOnly")?.checked;
  const minAvg = parseFloat(document.getElementById("minAvgInput")?.value || "");
  const minCurrent = parseFloat(document.getElementById("minCurrentInput")?.value || "");
  const facetMap = selectedFacetMap();

  const table = document.getElementById("researchTable");
  if (!table) return;

  const headers = Array.from(table.querySelectorAll("thead th")).map(th => th.textContent);
  const colIndex = column ? headers.indexOf(column) : -1;
  const rows = Array.from(table.querySelectorAll("tbody tr"));

  rows.forEach(tr => {
    const cellValues = Array.from(tr.querySelectorAll("td")).map(td => td.textContent || "");
    const lowerCells = cellValues.map(v => v.toLowerCase());

    let show = true;

    if (search) {
      const hay = colIndex >= 0 ? (lowerCells[colIndex] || "") : lowerCells.join(" | ");
      if (!hay.includes(search)) show = false;
    }

    if (show && overdueOnly) {
      const statusIdx = headers.indexOf("status");
      const statusVal = statusIdx >= 0 ? (cellValues[statusIdx] || "") : "";
      if (!String(statusVal).toLowerCase().includes("overdue")) show = false;
    }

    if (show && !Number.isNaN(minAvg)) {
      const idx = headers.indexOf("avg_games_between_hrs");
      if (idx >= 0) {
        const num = parseFloat(cellValues[idx]);
        if (Number.isNaN(num) || num < minAvg) show = false;
      }
    }

    if (show && !Number.isNaN(minCurrent)) {
      const idx = headers.indexOf("current_games_without_hr");
      if (idx >= 0) {
        const num = parseFloat(cellValues[idx]);
        if (Number.isNaN(num) || num < minCurrent) show = false;
      }
    }

    if (show) {
      for (const [key, valSet] of Object.entries(facetMap)) {
        const idx = headers.indexOf(key);
        if (idx >= 0) {
          const val = cellValues[idx] || "";
          if (!valSet.has(String(val))) {
            show = false;
            break;
          }
        }
      }
    }

    tr.style.display = show ? "" : "none";
  });
}

function renderAll() {
  setMeta();
  renderFinal();
  renderGames();
  renderResearchHome();
  switchView(currentView);
}

function switchView(view) {
  currentView = view;
  document.getElementById("view-final").classList.toggle("hidden", view !== "final");
  document.getElementById("view-games").classList.toggle("hidden", view !== "games");
  document.getElementById("view-research").classList.toggle("hidden", view !== "research");
  document.querySelectorAll(".tab").forEach(btn => btn.classList.toggle("active", btn.dataset.view === view));
}

document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

document.getElementById("reloadBtn").addEventListener("click", async () => {
  const btn = document.getElementById("reloadBtn");
  const old = btn.textContent;
  btn.textContent = "Reloading...";
  btn.disabled = true;
  try {
    await loadData();
  } finally {
    btn.textContent = old;
    btn.disabled = false;
  }
});

loadData();
</script>
</body>
</html>
"""
    return HTMLResponse(html)
