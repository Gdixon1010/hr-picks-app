import os
import json
import time
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from threading import Lock

from hr_v41_cloud_ready import main as run_model_main

app = FastAPI()

# 🔒 GLOBAL LOCK
refresh_lock = Lock()
is_refreshing = False

OUTPUT_DIR = Path(os.getenv("HR_APP_DATA_DIR", "/var/data/hr-picks/output"))


def load_latest_json():
    files = sorted(
        OUTPUT_DIR.glob("HR_Hit_Drought_v41_appdata-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return {}
    with open(files[0], "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/refresh-data")
def refresh_data():
    global is_refreshing

    # 🔒 BLOCK if already running
    if is_refreshing:
        return JSONResponse(
            status_code=200,
            content={
                "status": "busy",
                "message": "⚠️ Refresh already in progress. Please wait."
            }
        )

    with refresh_lock:
        try:
            is_refreshing = True

            today = datetime.now().strftime("%Y-%m-%d")

            print("🚀 Starting refresh...")
            start = time.time()

            run_model_main(2026, today)

            duration = round(time.time() - start, 2)
            print(f"✅ Refresh complete in {duration}s")

            return {
                "status": "success",
                "message": f"Refresh complete in {duration}s"
            }

        except Exception as e:
            print("❌ Refresh failed:", str(e))
            return {
                "status": "error",
                "message": str(e)
            }

        finally:
            is_refreshing = False


@app.get("/app-data")
def app_data():
    data = load_latest_json()
    return data
