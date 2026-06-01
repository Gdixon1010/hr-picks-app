"""
Patch: Final Card refresh/display safety for HR Picks App

What this does:
1) Backs up app_server_mobile_cloud_ready.py before editing.
2) Adds a recovery helper that finds the newest real Elite Final Card rows from:
   - /var/data/hr-picks/output/history/final_card_by_date_latest.json
   - prior same-date v41/v40 JSON files
3) Patches /latest so a newer empty file can no longer hide an older locked Final Card.
4) Patches /refresh-data so if the refresh creates an empty Final Card after games have started,
   it restores the pre-refresh Elite rows back into the lock file.

Run from /opt/render/project/src:
    python patch_final_card_refresh_safety.py
Then redeploy/restart Render.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from datetime import datetime

APP = Path("app_server_mobile_cloud_ready.py")

if not APP.exists():
    raise SystemExit("ERROR: app_server_mobile_cloud_ready.py not found. Run this from /opt/render/project/src")

backup = APP.with_name(f"app_server_mobile_cloud_ready_BACKUP_before_final_card_safety_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py")
shutil.copy2(APP, backup)

text = APP.read_text(encoding="utf-8")

# Ensure imports needed by refresh subprocess patch exist.
if "import subprocess" not in text:
    text = text.replace("import requests\n", "import requests\nimport subprocess\n", 1) if "import requests\n" in text else "import subprocess\n" + text
if "import sys" not in text:
    text = text.replace("import subprocess\n", "import subprocess\nimport sys\n", 1)

helper = r'''
def recover_real_final_card_rows(target_date):
    """Recover newest real Elite Final Card rows for target_date from lock/history/files."""
    import json

    if not target_date:
        return []

    def _is_real_elite(row):
        if not isinstance(row, dict):
            return False
        blob = " ".join(str(v).lower() for v in row.values())
        if "no elite" in blob or "no final card" in blob or row.get("category") == "Info":
            return False
        return str(row.get("slot", "")).startswith("Elite") and str(row.get("confidence", "")) == "A+"

    def _rows_from_payload(payload):
        fc = payload.get("final_card", {}) if isinstance(payload, dict) else {}
        if isinstance(fc, dict):
            rows = fc.get("plays") or []
        elif isinstance(fc, list):
            rows = fc
        else:
            rows = []
        return [r for r in rows if _is_real_elite(r)]

    # 1) First try the explicit lock file.
    hist_latest = OUTPUT_DIR / "history" / "final_card_by_date_latest.json"
    if hist_latest.exists():
        try:
            d = json.load(open(hist_latest, "r", encoding="utf-8"))
            if str(d.get("target_date")) == str(target_date):
                rows = [r for r in (d.get("rows") or []) if _is_real_elite(r)]
                if rows:
                    return rows
        except Exception:
            pass

    # 2) Then try the per-date lock dictionary.
    hist_by_date = OUTPUT_DIR / "history" / "final_card_by_date.json"
    if hist_by_date.exists():
        try:
            d = json.load(open(hist_by_date, "r", encoding="utf-8"))
            payload = d.get(str(target_date), {}) if isinstance(d, dict) else {}
            rows = [r for r in (payload.get("rows") or []) if _is_real_elite(r)]
            if rows:
                return rows
        except Exception:
            pass

    # 3) Finally scan older same-date v41/v40 files and use the newest one with real Elite rows.
    files = sorted(
        list(OUTPUT_DIR.glob("HR_Hit_Drought_v41_appdata-*.json")) +
        list(OUTPUT_DIR.glob("HR_Hit_Drought_v40_appdata-*.json")),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )

    for f in files:
        if str(target_date) not in f.name:
            continue
        try:
            payload = json.load(open(f, "r", encoding="utf-8"))
            rows = _rows_from_payload(payload)
            if rows:
                return rows
        except Exception:
            pass

    return []

def write_final_card_lock_rows(target_date, rows):
    """Write recovered/locked Elite Final Card rows to history lock files."""
    import json
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        now = _dt.datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        now = _dt.datetime.now()

    if not target_date or not rows:
        return False

    history_dir = OUTPUT_DIR / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    locked_until = now
    try:
        locked_until = (now + _dt.timedelta(days=1)).replace(hour=4, minute=0, second=0, microsecond=0)
    except Exception:
        pass

    payload = {
        "target_date": str(target_date),
        "saved_at_et": now.strftime("%Y-%m-%d %I:%M %p ET").replace(" 0", " "),
        "locked_until_et": locked_until.strftime("%Y-%m-%d %I:%M %p ET").replace(" 0", " "),
        "rows": rows,
    }

    (history_dir / "final_card_by_date_latest.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    hist_path = history_dir / "final_card_by_date.json"
    try:
        hist = json.load(open(hist_path, "r", encoding="utf-8")) if hist_path.exists() else {}
    except Exception:
        hist = {}
    if not isinstance(hist, dict):
        hist = {}
    hist[str(target_date)] = payload
    hist_path.write_text(json.dumps(hist, indent=2, ensure_ascii=False), encoding="utf-8")
    return True
'''

if "def recover_real_final_card_rows(" not in text:
    # Put helper after OUTPUT_DIR is defined if possible, otherwise before first route.
    m = re.search(r"^OUTPUT_DIR\s*=.*$", text, flags=re.MULTILINE)
    if m:
        insert_at = m.end()
        text = text[:insert_at] + "\n" + helper + text[insert_at:]
    else:
        text = helper + "\n" + text

# Patch /latest route: before returning data, recover final_card if empty.
latest_match = re.search(r'@app\.get\("/latest"\)\s*\ndef\s+latest\s*\([^)]*\):', text)
if not latest_match:
    raise SystemExit('ERROR: Could not find @app.get("/latest") route.')

latest_start = latest_match.start()
next_route = text.find("\n@app.", latest_start + 1)
if next_route == -1:
    next_route = len(text)
latest_section = text[latest_start:next_route]

latest_inject = '''    # Final Card display safety: never let a newer empty file hide an older locked card.
    current_plays = []
    if isinstance(data.get("final_card"), dict):
        current_plays = data.get("final_card", {}).get("plays", []) or []

    if not current_plays:
        target_date = data.get("date") or data.get("target_date")
        recovered = recover_real_final_card_rows(target_date)
        if recovered:
            data["final_card"] = {"generated_section": "final_card", "plays": recovered}
            data.setdefault("research", {})
            if isinstance(data["research"], dict):
                data["research"]["final_card"] = recovered
            write_final_card_lock_rows(target_date, recovered)

'''

if "Final Card display safety: never let a newer empty file" not in latest_section:
    if "    return data" in latest_section:
        latest_section = latest_section.replace("    return data", latest_inject + "    return data", 1)
    else:
        # JSONResponse fallback
        latest_section = re.sub(r"(\s+return\s+JSONResponse\s*\([^\n]+\))", "\n" + latest_inject + r"\1", latest_section, count=1)

text = text[:latest_start] + latest_section + text[next_route:]

# Patch /refresh-data route if present.
refresh_match = re.search(r'@app\.get\("/refresh-data"\)\s*\ndef\s+refresh_data\s*\([^)]*\):', text)
if refresh_match:
    refresh_start = refresh_match.start()
    next_route = text.find("\n@app.", refresh_start + 1)
    if next_route == -1:
        next_route = len(text)
    refresh_section = text[refresh_start:next_route]

    # Replace direct imported model call with subprocess, if still present.
    refresh_section = refresh_section.replace(
        "run_model_main(2026, today)",
        '''result = subprocess.run(
                [sys.executable, "hr_v41_cloud_ready.py"],
                cwd=str(Path(__file__).resolve().parent),
                capture_output=True,
                text=True,
                timeout=900,
            )
            if result.returncode != 0:
                raise RuntimeError("Refresh script failed:\\nSTDOUT:\\n" + result.stdout[-4000:] + "\\nSTDERR:\\n" + result.stderr[-4000:])'''
    )

    # Snapshot before subprocess if not already present.
    if "Refresh safety snapshot" not in refresh_section:
        # Put after today is set if possible, else after function line.
        snapshot = '''            # Refresh safety snapshot: keep current Elite Final Card before running model.
            before_data = load_latest_data()
            before_rows = []
            if isinstance(before_data.get("final_card"), dict):
                before_rows = before_data.get("final_card", {}).get("plays", []) or []
            before_rows = [
                r for r in before_rows
                if isinstance(r, dict)
                and str(r.get("slot", "")).startswith("Elite")
                and str(r.get("confidence", "")) == "A+"
            ]
            if not before_rows:
                before_rows = recover_real_final_card_rows(today)
'''
        if "today =" in refresh_section:
            refresh_section = re.sub(r"(\n\s*today\s*=.*\n)", r"\1" + snapshot, refresh_section, count=1)
        else:
            refresh_section = refresh_section.replace(":\n", ":\n" + snapshot, 1)

    # Restore after subprocess/model before grading/return if not present.
    if "Refresh safety restore" not in refresh_section:
        restore = '''
            # Refresh safety restore: if new run is empty after games started, restore previous Elite card.
            after_data = load_latest_data()
            after_rows = []
            if isinstance(after_data.get("final_card"), dict):
                after_rows = after_data.get("final_card", {}).get("plays", []) or []
            if before_rows and not after_rows:
                write_final_card_lock_rows(today, before_rows)
'''
        # Put before auto grading if possible, otherwise before return.
        if "auto_grade_result" in refresh_section:
            refresh_section = refresh_section.replace("            auto_grade_result", restore + "\n            auto_grade_result", 1)
        elif "return" in refresh_section:
            refresh_section = refresh_section.replace("            return", restore + "\n            return", 1)

    text = text[:refresh_start] + refresh_section + text[next_route:]
else:
    print("WARNING: /refresh-data route not found. Only /latest recovery was patched.")

APP.write_text(text, encoding="utf-8")
print(f"✅ Patched {APP}")
print(f"✅ Backup saved: {backup}")
print("Next: redeploy/restart Render, then test /latest and the app Refresh button.")
