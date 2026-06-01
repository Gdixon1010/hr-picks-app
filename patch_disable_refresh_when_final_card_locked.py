from pathlib import Path
import re
from datetime import datetime

p = Path("app_server_mobile_cloud_ready.py")
text = p.read_text(encoding="utf-8")
backup = p.with_name(f"app_server_mobile_cloud_ready_BACKUP_before_freeze_refresh_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py")
backup.write_text(text, encoding="utf-8")

helper = """
def _locked_final_card_rows_for_today():
    \"""Return existing locked Elite Final Card rows for the active app date, if any.\"""
    try:
        import json
        hist = OUTPUT_DIR / "history" / "final_card_by_date_latest.json"
        if not hist.exists():
            return []
        d = json.load(open(hist, "r", encoding="utf-8"))
        rows = d.get("rows", []) or []
        return [
            r for r in rows
            if isinstance(r, dict)
            and str(r.get("slot", "")).startswith("Elite")
            and str(r.get("confidence", "")) == "A+"
            and "no elite" not in " ".join(str(v).lower() for v in r.values())
        ]
    except Exception:
        return []
"""

if "def _locked_final_card_rows_for_today(" not in text:
    m = re.search(r"OUTPUT_DIR\s*=\s*Path\([^\n]+\)\s*\n", text)
    if m:
        text = text[:m.end()] + helper + "\n" + text[m.end():]
    else:
        text = helper + "\n" + text

m = re.search(r'@app\.get\("/refresh-data"\).*?(?=\n@app\.|\Z)', text, flags=re.S)
if not m:
    m = re.search(r'@app\.post\("/refresh-data"\).*?(?=\n@app\.|\Z)', text, flags=re.S)
if not m:
    raise SystemExit("Could not find /refresh-data route.")

section = m.group(0)

if "_locked_final_card_rows_for_today()" not in section:
    defline = re.search(r"def\s+\w+\s*\([^)]*\):\s*\n", section)
    if not defline:
        raise SystemExit("Could not find refresh-data function definition.")
    guard = """    # HARD SAFETY: If Final Card already has locked Elite A+ rows, do not rerun model.
    # This prevents the app Refresh button from wiping the card after games start.
    locked_rows = _locked_final_card_rows_for_today()
    if locked_rows:
        return {
            "status": "locked",
            "message": "Final Card already locked; refresh skipped to prevent overwrite.",
            "final_card_rows": len(locked_rows),
        }

"""
    section = section[:defline.end()] + guard + section[defline.end():]
    text = text[:m.start()] + section + text[m.end():]

p.write_text(text, encoding="utf-8")
print("✅ Patched app Refresh button: if Final Card is already locked, refresh is skipped.")
print(f"✅ Backup saved: {backup}")
print("Next: redeploy/restart Render. Tomorrow: run refresh before games; once Elite picks lock, app refresh cannot wipe them.")
