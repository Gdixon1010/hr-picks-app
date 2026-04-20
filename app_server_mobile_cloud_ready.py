
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

    eastern_now = None
    try:
        eastern_now = dt.datetime.fromtimestamp(latest.stat().st_mtime, ZoneInfo("America/New_York"))
        display = eastern_now.strftime("%b %d, %Y %I:%M %p ET").replace(" 0", " ")
    except Exception:
        display = None

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
      --good: #7fd48b;
      --warn: #f2ca68;
      --bad: #ff8e8e;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    .wrap { max-width: 1400px; margin: 0 auto; padding: 28px 22px 60px; }
    h1 { margin: 0 0 6px; font-size: 56px; line-height: 1; font-weight: 900; }
    .meta { color: var(--muted); font-size: 18px; margin-bottom: 18px; }
    .topbar {
      display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap;
    }
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
    .btn.secondary {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text);
      box-shadow: none;
    }
    .tabs {
      display: flex; gap: 12px; flex-wrap: wrap; margin: 18px 0 20px;
    }
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
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 18px; }
    .card {
      background: linear-gradient(180deg, var(--card), var(--card2));
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 22px 22px 18px;
      box-shadow: 0 14px 40px rgba(0,0,0,.25);
    }
    .card h2 { margin: 0 0 14px; font-size: 24px; line-height: 1.2; }
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
    .toolbar {
      display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 14px;
    }
    .input, select {
      background: #0c1320;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 12px 14px;
      font-size: 15px;
      min-width: 180px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    th, td {
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid #1f2940;
      vertical-align: top;
    }
    th { color: var(--text); position: sticky; top: 0; background: #0f1726; }
    td { color: var(--muted); }
    .table-wrap { overflow: auto; max-height: 70vh; border-radius: 16px; }
    .backrow { margin-bottom: 14px; }
    @media (max-width: 700px) {
      h1 { font-size: 42px; }
      .wrap { padding: 24px 16px 40px; }
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

async function loadData() {
  const res = await fetch("/latest?t=" + Date.now(), {cache: "no-store"});
  APP_DATA = await res.json();
  renderAll();
}

function setMeta() {
  const date = APP_DATA?.date || "—";
  const lu = APP_DATA?._meta?.last_updated_display || "—";
  document.getElementById("meta").textContent = "Date: " + date + " • Last Updated: " + lu;
}

function renderFinal() {
  const mount = document.getElementById("view-final");
  const plays = APP_DATA?.final_card?.plays || APP_DATA?.research?.final_card || [];
  if (!plays.length) {
    mount.innerHTML = '<div class="card"><h2>No final card available.</h2></div>';
    return;
  }
  mount.innerHTML = '<div class="cards">' + plays.map(p => `
    <div class="card">
      <div class="pill">${esc(fmt(p.slot || p.play_type || p.section || "Play"))}</div>
      <h2>${esc(fmt(p.pick))}</h2>
      <div class="line"><span class="label">Bet Type:</span> ${esc(fmt(p.bet_type))}</div>
      <div class="line"><span class="label">Team:</span> ${esc(fmt(p.team))}</div>
      <div class="line"><span class="label">Opponent:</span> ${esc(fmt(p.opponent))}</div>
      <div class="line"><span class="label">Confidence:</span> ${esc(fmt(p.confidence))}</div>
      <div class="kicker">${esc(fmt(p.why_it_made_the_card || p.reason))}</div>
      <div class="muted">Source: ${esc(fmt(p.source_tab))}</div>
    </div>
  `).join("") + "</div>";
}

function renderGames() {
  const mount = document.getElementById("view-games");
  const games = APP_DATA?.games || [];
  if (!games.length) {
    mount.innerHTML = '<div class="card"><h2>No game cards available.</h2></div>';
    return;
  }
  mount.innerHTML = '<div class="cards">' + games.map(g => {
    const time = g.game_time_et || g.start_time_et || g.startTimeEt || "not available yet";
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
        <p class="line"><span class="label">Start Time:</span> ${esc(time)}</p>
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
  }).join("") + "</div>";
}

function renderResearchHome() {
  const mount = document.getElementById("view-research");
  const research = APP_DATA?.research || {};
  const entries = Object.entries(research).filter(([k, v]) => Array.isArray(v));
  if (!entries.length) {
    mount.innerHTML = '<div class="card"><h2>No research tables available.</h2></div>';
    return;
  }
  mount.innerHTML = '<div class="research-grid">' + entries.map(([k, rows]) => `
    <div class="card research-card" onclick="openResearchTable('${k.replaceAll("'", "\\'")}')">
      <div class="research-title">${esc(k.replaceAll("_", " ").replace(/\\b\\w/g, m => m.toUpperCase()))}</div>
      <div class="muted">${rows.length} rows</div>
    </div>
  `).join("") + "</div>";
}

function openResearchTable(key) {
  const rows = APP_DATA?.research?.[key] || [];
  const mount = document.getElementById("view-research");
  const columns = rows.length ? Object.keys(rows[0]) : [];
  const options = columns.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
  mount.innerHTML = `
    <div class="backrow">
      <button class="btn secondary" onclick="renderResearchHome()">← Back</button>
    </div>
    <div class="table-shell">
      <h2 style="margin-top:0;">${esc(key.replaceAll("_", " ").replace(/\\b\\w/g, m => m.toUpperCase()))}</h2>
      <div class="toolbar">
        <input id="searchBox" class="input" placeholder="Search this table" oninput="filterResearchTable()">
        <select id="columnSelect" onchange="filterResearchTable()">
          <option value="">All columns</option>
          ${options}
        </select>
      </div>
      <div class="table-wrap">
        <table id="researchTable">
          <thead><tr>${columns.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead>
          <tbody>
            ${rows.map(r => `<tr>${columns.map(c => `<td>${esc(fmt(r[c]))}</td>`).join("")}</tr>`).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function filterResearchTable() {
  const search = (document.getElementById("searchBox")?.value || "").toLowerCase();
  const column = document.getElementById("columnSelect")?.value || "";
  const table = document.getElementById("researchTable");
  if (!table) return;
  const headers = Array.from(table.querySelectorAll("thead th")).map(th => th.textContent);
  const colIndex = column ? headers.indexOf(column) : -1;
  Array.from(table.querySelectorAll("tbody tr")).forEach(tr => {
    const cells = Array.from(tr.querySelectorAll("td")).map(td => (td.textContent || "").toLowerCase());
    const hay = colIndex >= 0 ? (cells[colIndex] || "") : cells.join(" | ");
    tr.style.display = hay.includes(search) ? "" : "none";
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
  document.querySelectorAll(".tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
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
