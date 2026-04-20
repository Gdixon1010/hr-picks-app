from __future__ import annotations

import json
import os
import subprocess
import datetime as dt
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from zoneinfo import ZoneInfo

app = FastAPI(title="HR Picks App")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

EASTERN = ZoneInfo("America/New_York")


def eastern_now_str() -> str:
    return dt.datetime.now(EASTERN).strftime("%Y-%m-%d %I:%M %p ET").replace(" 0", " ")


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _find_latest_json() -> tuple[dict[str, Any], Path | None]:
    files = sorted(OUTPUT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files:
        payload = _safe_read_json(p)
        if isinstance(payload, dict):
            payload.setdefault("_meta", {})
            payload["_meta"]["filename"] = p.name
            payload["_meta"]["path"] = str(p)
            try:
                updated_et = dt.datetime.fromtimestamp(p.stat().st_mtime, EASTERN)
                payload["_meta"]["last_updated_et"] = updated_et.strftime("%b %d, %Y %I:%M %p ET").replace(" 0", " ")
            except Exception:
                payload["_meta"]["last_updated_et"] = eastern_now_str()
            payload["_meta"]["eastern_now"] = eastern_now_str()
            return payload, p
    return {
        "date": None,
        "final_card": {"generated_section": "final_card", "plays": []},
        "games": [],
        "research": {},
        "_meta": {"filename": None, "path": None, "last_updated_et": None, "eastern_now": eastern_now_str()},
    }, None


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    return HTMLResponse('<meta http-equiv="refresh" content="0; url=/app">')

@app.get("/health")
def health():
    return {"status": "ok", "time": eastern_now_str()}

@app.get("/latest")
def latest():
    payload, _ = _find_latest_json()
    return JSONResponse(payload)

@app.get("/refresh-data")
def refresh_data():
    # Runs the backend refresh and returns the newest JSON metadata if successful
    today = dt.datetime.now(EASTERN).date().isoformat()
    cmd = [
        "python",
        "-c",
        (
            "from hr_v41_cloud_ready import main; "
            f"main(2026, '{today}')"
        ),
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(Path.cwd()),
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

    if result.returncode != 0:
        return JSONResponse(
            {
                "status": "error",
                "message": "Refresh failed",
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            },
            status_code=500,
        )

    payload, path = _find_latest_json()
    return {
        "status": "ok",
        "message": "Data refreshed",
        "date": payload.get("date"),
        "filename": payload.get("_meta", {}).get("filename"),
        "last_updated_et": payload.get("_meta", {}).get("last_updated_et"),
        "path": str(path) if path else None,
    }

HTML = r"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>HR Picks App</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background:#0f1115; color:#f4f4f4; }
    .wrap { max-width: 1100px; margin: 0 auto; padding: 16px; }
    .top { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:12px; margin-bottom:16px; }
    .title { font-size: 28px; font-weight: 700; }
    .meta { color:#b9c0cb; font-size:14px; }
    .btn { background:#1f6feb; color:white; border:none; border-radius:10px; padding:10px 14px; font-size:14px; font-weight:600; cursor:pointer; }
    .btn:disabled { opacity:.65; cursor:default; }
    .tabs { display:flex; flex-wrap:wrap; gap:8px; margin:14px 0 18px; }
    .tab { background:#1b1f27; color:#dce3ed; border:1px solid #2b3240; border-radius:999px; padding:8px 12px; cursor:pointer; }
    .tab.active { background:#2a3444; border-color:#4a5a73; }
    .panel { display:none; }
    .panel.active { display:block; }
    .card { background:#171b22; border:1px solid #29303c; border-radius:16px; padding:14px; margin:0 0 12px; }
    .card h3 { margin:0 0 8px; font-size:18px; }
    .small { color:#b9c0cb; font-size:13px; }
    .grid { display:grid; gap:12px; }
    .grid.two { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
    .pill { display:inline-block; padding:4px 8px; border-radius:999px; background:#263043; font-size:12px; color:#dfe8f5; margin-right:6px; margin-bottom:6px; }
    table { width:100%; border-collapse:collapse; }
    th, td { text-align:left; padding:10px 8px; border-bottom:1px solid #2a3039; font-size:14px; vertical-align:top; }
    th { color:#c7d0dd; }
    .muted { color:#9aa6b2; }
    pre { white-space:pre-wrap; word-break:break-word; background:#11151b; border:1px solid #2a3039; border-radius:12px; padding:12px; overflow:auto; }
  </style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <div class="title">HR Picks App</div>
      <div class="meta" id="metaLine">Loading…</div>
    </div>
    <div>
      <button class="btn" id="reloadBtn" onclick="reloadApp()">Reload App</button>
    </div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="showTab('final')">Final Card</button>
    <button class="tab" onclick="showTab('games')">Games</button>
    <button class="tab" onclick="showTab('research')">Research</button>
    <button class="tab" onclick="showTab('raw')">Raw Data</button>
  </div>

  <div id="final" class="panel active"></div>
  <div id="games" class="panel"></div>
  <div id="research" class="panel"></div>
  <div id="raw" class="panel"></div>
</div>

<script>
let APP_DATA = null;

function esc(v) {
  if (v === null || v === undefined) return "—";
  return String(v)
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;");
}

function showTab(id) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  const btn = [...document.querySelectorAll('.tab')].find(b => b.textContent.replace(/\s+/g,'').toLowerCase().startsWith(id));
  if (btn) btn.classList.add('active');
}

function renderMeta(data) {
  const meta = data._meta || {};
  const line = `Date: ${esc(data.date || "—")} • Last Updated: ${esc(meta.last_updated_et || "—")}`;
  document.getElementById('metaLine').innerHTML = line;
}

function renderFinal(data) {
  const panel = document.getElementById('final');
  const plays = (data.final_card && data.final_card.plays) || (data.research && data.research.final_card) || [];
  if (!plays.length) {
    panel.innerHTML = `<div class="card">No final card plays available.</div>`;
    return;
  }
  let html = '<div class="grid">';
  plays.forEach((p, idx) => {
    html += `
      <div class="card">
        <h3>${esc(p.slot || 'Play ' + (idx+1))} — ${esc(p.bet_type || 'Play')}</h3>
        <div><strong>${esc(p.pick || '')}</strong></div>
        <div class="small">${esc(p.team || '')}${p.opponent ? ' vs ' + esc(p.opponent) : ''}</div>
        <div style="margin-top:8px;"><span class="pill">${esc(p.confidence || '—')}</span><span class="pill">${esc(p.source_tab || '—')}</span></div>
        <div style="margin-top:8px;">${esc(p.why_it_made_the_card || '')}</div>
      </div>`;
  });
  html += '</div>';
  panel.innerHTML = html;
}

function renderGames(data) {
  const panel = document.getElementById('games');
  const games = data.games || [];
  if (!games.length) {
    panel.innerHTML = `<div class="card">No games available.</div>`;
    return;
  }
  let html = '<div class="grid">';
  games.forEach(g => {
    const ml = g.ml_lean || {};
    const hitPicks = g.top_hit_picks || [];
    const hrPicks = g.top_hr_picks || [];
    const k = g.top_k_pick || null;
    html += `<div class="card">
      <h3>${esc(g.game)}</h3>
      <div class="small">Start Time: ${esc(g.game_time_et || 'not available yet')}${g.venue ? ' • ' + esc(g.venue) : ''}</div>
      <div style="margin-top:10px;"><strong>ML Lean:</strong> ${esc(ml.team || '—')} ${ml.edge_vs_opponent !== undefined && ml.edge_vs_opponent !== null ? `(edge ${esc(ml.edge_vs_opponent)})` : ''}</div>
      <div class="small">${esc(ml.recommended_play || '')}</div>
      <div style="margin-top:10px;"><strong>Top Hit Picks</strong></div>
      <div class="small">${hitPicks.length ? hitPicks.map(p => `${esc(p.playerName)} (${esc(p.teamName)})`).join(' • ') : '—'}</div>
      <div style="margin-top:10px;"><strong>Top HR Picks</strong></div>
      <div class="small">${hrPicks.length ? hrPicks.map(p => `${esc(p.playerName)} (${esc(p.teamName)})`).join(' • ') : '—'}</div>
      <div style="margin-top:10px;"><strong>Top K Pick</strong></div>
      <div class="small">${k ? `${esc(k.pitcherName)} (${esc(k.teamName)}) — ${esc(k.recommended_k_action || '')}` : '—'}</div>
    </div>`;
  });
  html += '</div>';
  panel.innerHTML = html;
}

function renderResearch(data) {
  const panel = document.getElementById('research');
  const research = data.research || {};
  const sections = [
    ['Game Rankings', (research.game_rankings || []).length],
    ['Pitcher Metrics', (research.pitcher_metrics || []).length],
    ['Pitcher Line Value', (research.pitcher_line_value || []).length],
    ['HR Drought', (research.hr_drought || []).length],
    ['Hit Drought', (research.hit_drought || []).length],
    ['Top Picks', (research.top_picks || []).length],
    ['Refined Picks', (research.refined_picks || []).length]
  ];
  let html = '<div class="grid two">';
  sections.forEach(([name, count]) => {
    html += `<div class="card"><h3>${esc(name)}</h3><div class="small">${count} rows</div></div>`;
  });
  html += '</div>';
  panel.innerHTML = html;
}

function renderRaw(data) {
  document.getElementById('raw').innerHTML = `<pre>${esc(JSON.stringify(data, null, 2))}</pre>`;
}

function renderAll(data) {
  APP_DATA = data;
  renderMeta(data);
  renderFinal(data);
  renderGames(data);
  renderResearch(data);
  renderRaw(data);
}

async function loadLatest(forceFresh=true) {
  const url = forceFresh ? `/latest?t=${Date.now()}` : `/latest`;
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Load failed (${res.status})`);
  return await res.json();
}

async function reloadApp() {
  const btn = document.getElementById('reloadBtn');
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Reloading...';
  try {
    const data = await loadLatest(true);
    renderAll(data);
    btn.textContent = 'Reloaded';
    setTimeout(() => {
      btn.textContent = original;
      btn.disabled = false;
    }, 900);
  } catch (err) {
    btn.textContent = 'Reload failed';
    setTimeout(() => {
      btn.textContent = original;
      btn.disabled = false;
    }, 1500);
  }
}

window.addEventListener('load', async () => {
  try {
    const data = await loadLatest(true);
    renderAll(data);
  } catch (err) {
    document.getElementById('final').innerHTML = `<div class="card">Could not load app data.</div>`;
    document.getElementById('metaLine').textContent = 'Load failed';
  }
});
</script>
</body>
</html>
"""

@app.get("/app", response_class=HTMLResponse)
def app_page() -> HTMLResponse:
    return HTMLResponse(HTML)
