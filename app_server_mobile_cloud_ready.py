from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
from pathlib import Path
import json
import datetime as dt
import os
from zoneinfo import ZoneInfo

from hr_v41_cloud_ready import main as run_model_main

app = FastAPI()



def resolve_storage_dir() -> Path:
    configured = os.getenv("HR_APP_DATA_DIR")
    if configured:
        p = Path(configured)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Helpful default for Render Disk users if they mount to /var/data
    render_default = Path("/var/data/hr-picks/output")
    if render_default.parent.exists():
        render_default.mkdir(parents=True, exist_ok=True)
        return render_default

    local_default = Path("output")
    local_default.mkdir(parents=True, exist_ok=True)
    return local_default


OUTPUT_DIR = resolve_storage_dir()


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




def read_json_file(path: Path, default):
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def load_latest_data():
    history_dir = OUTPUT_DIR / "history"
    latest = get_latest_json_file()

    if latest and latest.exists():
        with open(latest, "r", encoding="utf-8") as f:
            data = json.load(f)
        filename = latest.name
        path_str = str(latest)
        try:
            eastern_now = dt.datetime.fromtimestamp(latest.stat().st_mtime, ZoneInfo("America/New_York"))
            display = eastern_now.strftime("%b %d, %Y %I:%M %p ET").replace(" 0", " ")
        except Exception:
            eastern_now = None
            display = None
    else:
        snapshot = read_json_file(history_dir / "latest_app_data.json", {})
        data = snapshot.get("app_payload") or {
            "date": None,
            "final_card": {"generated_section": "final_card", "plays": []},
            "games": [],
            "research": {},
        }
        filename = snapshot.get("json_filename")
        path_str = str(history_dir / "latest_app_data.json") if snapshot else None
        eastern_now = None
        saved_label = snapshot.get("saved_at_et")
        display = saved_label

    lock_dir = OUTPUT_DIR / "final_card_lock"
    frozen_latest = read_json_file(lock_dir / "final_card_by_date_latest.json", {})
    if not frozen_latest:
        frozen_latest = read_json_file(history_dir / "final_card_by_date_latest.json", {})
    frozen_rows = frozen_latest.get("rows") or []
    frozen_date = frozen_latest.get("target_date")

    data_date = str(data.get("date")) if data.get("date") else None
    if frozen_rows and frozen_date and (data_date is None or frozen_date == data_date):
        data["final_card"] = {"generated_section": "final_card", "plays": frozen_rows}
        if not data.get("date"):
            data["date"] = frozen_date

    data["results"] = read_json_file(history_dir / "performance_summary_latest.json", {"overall": {}, "by_bet_type": [], "by_confidence": [], "recent_results": []})
    data["results_latest"] = read_json_file(history_dir / "results_history_latest.json", {"graded_rows": 0, "rows": []})
    data["info"] = {
        "purpose": "This app finds MLB betting edges by combining player trends, drought logic, matchup strength, pitcher quality, lineup context, and park factors.",
        "how_to_use": [
            "Start on Final Card for the strongest condensed plays.",
            "Use Games to see matchup context, start time, and top game-level picks.",
            "Use Research to drill into HR drought, hit drought, pitcher metrics, and game rankings.",
            "Filter for overdue players, favorable parks, and weaker pitcher types to isolate stronger spots.",
            "Treat Strong SP as a warning for hitter props and Short Leash Risk or Attack With Hitters as friendlier hitting environments."
        ],
        "terms": [
            {"term": "Attack With Hitters", "meaning": "Pitcher or pitching environment is vulnerable enough to target hitters."},
            {"term": "Strong SP", "meaning": "Strong starting pitcher. Usually a downgrade for hitter props."},
            {"term": "Short Leash Risk", "meaning": "Pitcher may not work deep into the game, which can help hitters later against the bullpen."},
            {"term": "K Upside", "meaning": "Pitcher has a favorable strikeout profile for K props."},
            {"term": "On Pace", "meaning": "Current drought is normal relative to the player’s average pattern."},
            {"term": "Slightly Overdue", "meaning": "Player is running a bit longer than usual without the event."},
            {"term": "Overdue", "meaning": "Player is well beyond normal drought range and may be due for regression."},
            {"term": "Hit Score", "meaning": "Composite score for hit probability using matchup, context, and trend inputs. Higher is better."},
            {"term": "HR Score", "meaning": "Composite score for home run appeal using power, park, matchup, and drought context. Higher is better."},
            {"term": "Moneyline Lean", "meaning": "The model sees an edge on that team, but size depends on edge strength and matchup quality."}
        ]
    }
    data["_meta"] = {
        "filename": filename,
        "path": path_str,
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
      <button class="tab" data-view="info">Info</button>
      <button class="tab" data-view="results">Results</button>
    </div>

    <section id="view-final"></section>
    <section id="view-games" class="hidden"></section>
    <section id="view-research" class="hidden"></section>
    <section id="view-info" class="hidden"></section>
    <section id="view-results" class="hidden"></section>
  </div>

<script>
let APP_DATA = null;
let currentView = "final";
let CURRENT_RESEARCH_KEY = null;
let CURRENT_RESEARCH_ROWS = [];
let CURRENT_SORT_COLUMN = "";
let CURRENT_SORT_DIR = "asc";

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
        <select id="sortSelect" onchange="filterResearchTable()">
          <option value="">Default order</option>
          <option value="asc">A → Z</option>
          <option value="desc">Z → A</option>
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
          <thead><tr>${columns.map(c => `<th data-col="${esc(c)}" class="sortable ${String(c).length > 18 ? 'wrap' : ''}">${esc(c)}</th>`).join("")}</tr></thead>
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
  mount.querySelectorAll("thead th.sortable").forEach(th => {
    th.style.cursor = "pointer";
    th.addEventListener("click", () => {
      const col = th.dataset.col || "";
      if (CURRENT_SORT_COLUMN === col) {
        CURRENT_SORT_DIR = CURRENT_SORT_DIR === "asc" ? "desc" : "asc";
      } else {
        CURRENT_SORT_COLUMN = col;
        CURRENT_SORT_DIR = "asc";
      }
      filterResearchTable();
    });
  });

  filterResearchTable();
}

function clearResearchFilters() {
  const search = document.getElementById("searchBox");
  const col = document.getElementById("columnSelect");
  const overdue = document.getElementById("overdueOnly");
  const sortSel = document.getElementById("sortSelect");
  const minAvg = document.getElementById("minAvgInput");
  const minCurrent = document.getElementById("minCurrentInput");

  if (search) search.value = "";
  if (col) col.value = "";
  if (overdue) overdue.checked = false;
  if (sortSel) sortSel.value = "";
  if (minAvg) minAvg.value = "";
  if (minCurrent) minCurrent.value = "";
  document.querySelectorAll(".facet-check").forEach(c => c.checked = false);
  CURRENT_SORT_COLUMN = "";
  CURRENT_SORT_DIR = "asc";
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
  const sortValue = document.getElementById("sortSelect")?.value || "";

  const table = document.getElementById("researchTable");
  if (!table) return;

  const headers = Array.from(table.querySelectorAll("thead th")).map(th => th.dataset.col || th.textContent || "");
  const tbody = table.querySelector("tbody");
  if (!tbody) return;

  let rows = Array.isArray(CURRENT_RESEARCH_ROWS) ? [...CURRENT_RESEARCH_ROWS] : [];

  rows = rows.filter(r => {
    const getVal = (key) => String(r?.[key] ?? "");
    const headerVals = headers.map(h => getVal(h));
    const lowerHeaderVals = headerVals.map(v => v.toLowerCase());

    if (search) {
      if (column) {
        const hay = getVal(column).toLowerCase();
        if (!hay.includes(search)) return false;
      } else {
        if (!lowerHeaderVals.join(" | ").includes(search)) return false;
      }
    }

    if (overdueOnly) {
      const statusVal = getVal("status").toLowerCase();
      if (!statusVal.includes("overdue")) return false;
    }

    if (!Number.isNaN(minAvg)) {
      const avgKey = headers.includes("avg_games_between_hrs") ? "avg_games_between_hrs" : (headers.includes("avg_games_between_hits") ? "avg_games_between_hits" : "");
      if (avgKey) {
        const num = parseFloat(getVal(avgKey));
        if (Number.isNaN(num) || num < minAvg) return false;
      }
    }

    if (!Number.isNaN(minCurrent)) {
      const curKey = headers.includes("current_games_without_hr") ? "current_games_without_hr" : (headers.includes("current_games_without_hit") ? "current_games_without_hit" : "");
      if (curKey) {
        const num = parseFloat(getVal(curKey));
        if (Number.isNaN(num) || num < minCurrent) return false;
      }
    }

    for (const [key, valSet] of Object.entries(facetMap)) {
      const val = getVal(key);
      if (!valSet.has(String(val))) return false;
    }

    return true;
  });

  if (CURRENT_SORT_COLUMN) {
    rows.sort((a, b) => {
      const av = String(a?.[CURRENT_SORT_COLUMN] ?? "");
      const bv = String(b?.[CURRENT_SORT_COLUMN] ?? "");
      const an = parseFloat(av);
      const bn = parseFloat(bv);
      const bothNumeric = !Number.isNaN(an) && !Number.isNaN(bn) && av.trim() !== "" && bv.trim() !== "";
      if (bothNumeric) {
        return CURRENT_SORT_DIR === "asc" ? an - bn : bn - an;
      }
      return CURRENT_SORT_DIR === "asc"
        ? av.localeCompare(bv, undefined, {numeric:true, sensitivity:"base"})
        : bv.localeCompare(av, undefined, {numeric:true, sensitivity:"base"});
    });
  } else if (sortValue) {
    const sortKey = headers.includes("playerName") ? "playerName" : headers[0];
    rows.sort((a, b) => {
      const av = String(a?.[sortKey] ?? "");
      const bv = String(b?.[sortKey] ?? "");
      return sortValue === "asc"
        ? av.localeCompare(bv, undefined, {numeric:true, sensitivity:"base"})
        : bv.localeCompare(av, undefined, {numeric:true, sensitivity:"base"});
    });
  }

  tbody.innerHTML = rows.map(r => `<tr>${headers.map(c => `<td class="${String(c).length > 18 ? 'wrap' : ''}">${esc(fmt(r[c]))}</td>`).join("")}</tr>`).join("");

  document.querySelectorAll("thead th.sortable").forEach(th => {
    const col = th.dataset.col || "";
    const base = col;
    if (CURRENT_SORT_COLUMN === col) {
      th.textContent = `${base} ${CURRENT_SORT_DIR === 'asc' ? '↑' : '↓'}`;
    } else {
      th.textContent = base;
    }
  });
}



function renderInfo() {
  const mount = document.getElementById("view-info");
  const info = APP_DATA?.info || {};
  const terms = Array.isArray(info.terms) ? info.terms : [];
  const how = Array.isArray(info.how_to_use) ? info.how_to_use : [];
  mount.innerHTML = `
    <div class="cards">
      <div class="card">
        <h2>What This App Does</h2>
        <div class="line">${esc(fmt(info.purpose || "This app ranks MLB betting edges across hits, HRs, Ks, and moneyline spots."))}</div>
      </div>
      <div class="card">
        <h2>What To Look For</h2>
        <ul class="list">${how.map(x => `<li>${esc(x)}</li>`).join("")}</ul>
      </div>
    </div>
    <div class="table-shell" style="margin-top:18px;">
      <h2 style="margin-top:0;">Key Terms</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Term</th><th class="wrap">Meaning</th></tr></thead>
          <tbody>${terms.map(t => `<tr><td>${esc(fmt(t.term))}</td><td class="wrap">${esc(fmt(t.meaning))}</td></tr>`).join("")}</tbody>
        </table>
      </div>
    </div>
  `;
}

function renderResults() {
  const mount = document.getElementById("view-results");
  const results = APP_DATA?.results || {};
  const overall = results.overall || {};
  const byType = Array.isArray(results.by_bet_type) ? results.by_bet_type : [];
  const byConf = Array.isArray(results.by_confidence) ? results.by_confidence : [];
  const recent = Array.isArray(results.recent_results) ? results.recent_results : [];
  mount.innerHTML = `
    <div class="cards">
      <div class="card"><h2>Overall Performance</h2>
        <div class="line"><span class="label">Graded Picks:</span> ${esc(fmt(overall.graded_picks))}</div>
        <div class="line"><span class="label">Wins:</span> ${esc(fmt(overall.wins))}</div>
        <div class="line"><span class="label">Losses:</span> ${esc(fmt(overall.losses))}</div>
        <div class="line"><span class="label">Win Rate:</span> ${overall.win_rate !== undefined && overall.win_rate !== null ? esc((overall.win_rate * 100).toFixed(1) + '%') : '—'}</div>
      </div>
      <div class="card"><h2>What This Is For</h2>
        <div class="line">This tab tracks how saved picks perform over time so you can see what the model does well and where it needs tightening.</div>
      </div>
    </div>
    <div class="cards" style="margin-top:18px;">
      <div class="table-shell">
        <h2 style="margin-top:0;">By Bet Type</h2>
        <div class="table-wrap"><table><thead><tr><th>Bet Type</th><th>Graded</th><th>Wins</th><th>Losses</th><th>Win Rate</th></tr></thead><tbody>
        ${byType.map(r => `<tr><td>${esc(fmt(r.bet_type))}</td><td>${esc(fmt(r.graded_picks))}</td><td>${esc(fmt(r.wins))}</td><td>${esc(fmt(r.losses))}</td><td>${r.win_rate !== undefined && r.win_rate !== null ? esc((Number(r.win_rate) * 100).toFixed(1) + '%') : '—'}</td></tr>`).join("") || '<tr><td colspan="5">No graded results yet.</td></tr>'}
        </tbody></table></div>
      </div>
      <div class="table-shell">
        <h2 style="margin-top:0;">By Confidence</h2>
        <div class="table-wrap"><table><thead><tr><th>Confidence</th><th>Graded</th><th>Wins</th><th>Losses</th><th>Win Rate</th></tr></thead><tbody>
        ${byConf.map(r => `<tr><td>${esc(fmt(r.confidence))}</td><td>${esc(fmt(r.graded_picks))}</td><td>${esc(fmt(r.wins))}</td><td>${esc(fmt(r.losses))}</td><td>${r.win_rate !== undefined && r.win_rate !== null ? esc((Number(r.win_rate) * 100).toFixed(1) + '%') : '—'}</td></tr>`).join("") || '<tr><td colspan="5">No confidence-level results yet.</td></tr>'}
        </tbody></table></div>
      </div>
    </div>
    <div class="table-shell" style="margin-top:18px;">
      <h2 style="margin-top:0;">Recent Graded Picks</h2>
      <div class="table-wrap"><table><thead><tr><th>Date</th><th>Bet Type</th><th>Pick</th><th>Team</th><th>Opponent</th><th>Confidence</th><th>Result</th><th class="wrap">Detail</th></tr></thead><tbody>
      ${recent.map(r => `<tr><td>${esc(fmt(r.target_date))}</td><td>${esc(fmt(r.bet_type))}</td><td>${esc(fmt(r.pick))}</td><td>${esc(fmt(r.team))}</td><td>${esc(fmt(r.opponent))}</td><td>${esc(fmt(r.confidence))}</td><td>${esc(fmt(r.result_status))}</td><td class="wrap">${esc(fmt(r.result_detail))}</td></tr>`).join("") || '<tr><td colspan="8">No graded picks yet.</td></tr>'}
      </tbody></table></div>
    </div>
  `;
}

function renderAll() {
  setMeta();
  renderFinal();
  renderGames();
  renderResearchHome();
  renderInfo();
  renderResults();
  switchView(currentView);
}

function switchView(view) {
  currentView = view;
  document.getElementById("view-final").classList.toggle("hidden", view !== "final");
  document.getElementById("view-games").classList.toggle("hidden", view !== "games");
  document.getElementById("view-research").classList.toggle("hidden", view !== "research");
  document.getElementById("view-info").classList.toggle("hidden", view !== "info");
  document.getElementById("view-results").classList.toggle("hidden", view !== "results");
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
