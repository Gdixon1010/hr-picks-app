from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path
import json
import datetime as dt

from hr_v40_2_json_export_ready import main as run_model_main

app = FastAPI()

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

def load_json(name):
    path = OUTPUT_DIR / name
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.api_route("/refresh-data", methods=["GET", "POST"])
def refresh_data():
    today = dt.date.today().strftime("%Y-%m-%d")
    run_model_main(2026, today)
    return {"status": "ok", "message": "Data refreshed", "date": today}

@app.get("/data")
def get_data():
    final_card = load_json("final_card.json")
    games = load_json("game_cards.json")
    research = load_json("research.json")

    return JSONResponse({
        "final_card": final_card,
        "games": games,
        "research": research
    })

@app.get("/app", response_class=HTMLResponse)
def app_ui():
    return """
<!DOCTYPE html>
<html>
<head>
<title>HR Picks</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { background:#0b0f1c; color:white; font-family:sans-serif; padding:20px; }
button { padding:10px; margin:5px; border-radius:10px; }
.card { background:#151a2e; padding:15px; margin:10px 0; border-radius:12px; }
</style>
</head>
<body>

<h1>HR Picks</h1>

<button onclick="refreshData()">Refresh Data</button>
<button onclick="loadData()">Reload App</button>

<div id="content"></div>

<script>
async function refreshData(){
    document.getElementById("content").innerHTML = "Refreshing server data...";
    await fetch('/refresh-data');
    loadData();
}

async function loadData(){
    let res = await fetch('/data');
    let data = await res.json();

    let html = "";

    if(data.final_card){
        html += "<h2>Final Card</h2>";
        data.final_card.plays.forEach(p=>{
            html += `<div class="card">
                <b>${p.bet_type}</b><br>
                ${p.pick}<br>
                ${p.team} vs ${p.opponent}<br>
                ${p.why_it_made_the_card}
            </div>`;
        });
    }

    if(data.games){
        html += "<h2>Games</h2>";
        data.games.forEach(g=>{
            html += `<div class="card">
                <b>${g.matchup}</b><br>
                ${g.edge}
            </div>`;
        });
    }

    document.getElementById("content").innerHTML = html;
}

loadData();
</script>

</body>
</html>
"""
