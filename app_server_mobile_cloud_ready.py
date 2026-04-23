import pandas as pd
import json
from datetime import datetime
from flask import Flask, jsonify
import os

app = Flask(__name__)

DATA_PATH = "/var/data/hr-picks/output/history/final_card_by_date.json"

def load_data():
    if not os.path.exists(DATA_PATH):
        return {}
    with open(DATA_PATH, "r") as f:
        return json.load(f)

@app.route("/app")
def app_data():
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    today_rows = data.get(today, [])

    return jsonify({
        "date": today,
        "last_updated": datetime.now().strftime("%b %d, %Y %I:%M %p ET"),
        "final_card": today_rows
    })

@app.route("/research")
def research_data():
    # Example placeholder — replace with your real refined_picks source if needed
    df = pd.DataFrame([
        {"player": "Example Player", "last_hr_date": "2026-04-22"},
        {"player": "Example Player 2", "last_hr_date": "—"},
        {"player": "Example Player 3", "last_hr_date": "2026-04-18"},
    ])

    # 🔥 THIS IS THE FIX
    if "last_hr_date" in df.columns:
        df["last_hr_date"] = pd.to_datetime(
            df["last_hr_date"],
            errors="coerce"
        )

        df = df.sort_values(
            by="last_hr_date",
            ascending=False,
            na_position="last"
        )

        # convert back to string for display
        df["last_hr_date"] = df["last_hr_date"].dt.strftime("%Y-%m-%d")

    return df.fillna("—").to_json(orient="records")

@app.route("/")
def home():
    return "HR Picks App Running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
