from __future__ import annotations
import json
import datetime as dt
from pathlib import Path
import pandas as pd

# ✅ CLOUD OUTPUT DIRECTORY (CRITICAL FIX)
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ✅ SAFE INT CONVERSION (CRITICAL FIX)
def safe_int(val):
    try:
        if val is None:
            return None
        if str(val).lower() in ("nan", "none", ""):
            return None
        return int(float(val))
    except:
        return None

# ---------------------------------------------------
# 🔽 YOUR EXISTING LOGIC SHOULD STAY BELOW THIS LINE
# (we are only fixing the crash + output path)
# ---------------------------------------------------

def get_pitcher_game_logs(pid, season):
    # your existing function (leave as-is if already exists)
    return pd.DataFrame()

def build_pitcher_metrics(schedule_rows, season):
    results = []

    for row in schedule_rows:
        pitcher_id = row.get("pitcher_id")

        # ✅ SAFE FIX (this prevents crash)
        pid = safe_int(pitcher_id)

        if pid is not None:
            logs = get_pitcher_game_logs(pid, season)
        else:
            logs = pd.DataFrame()

        results.append({
            "pitcher_id": pitcher_id,
            "games_found": len(logs)
        })

    return results

# ---------------------------------------------------
# MAIN FUNCTION (called by your app)
# ---------------------------------------------------

def main(season, target_date):
    print("🚀 SAFE V40 RUN STARTED")

    # ⚠️ your real schedule logic runs here
    schedule_rows = []  # your real data will populate this

    pitcher_metrics = build_pitcher_metrics(schedule_rows, season)

    # ✅ FIXED OUTPUT PATH (cloud safe)
    timestamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = OUTPUT_DIR / f"HR_Hit_Drought_v40_appdata-{season}_{target_date}_{timestamp}.json"

    with open(filename, "w") as f:
        json.dump({
            "date": target_date,
            "pitcher_metrics": pitcher_metrics,
            "final_card": {"plays": []},
            "games": [],
            "research": {}
        }, f)

    print(f"🧾 JSON created: {filename}")
    print("✅ DONE")
