import os
import json
from pathlib import Path
from datetime import datetime

from hr_v40_2_json_export_ready import main as run_v40_main


OUTPUT_DIR = Path(os.getenv("HR_APP_DATA_DIR", "output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _latest_v40_json() -> Path:
    files = sorted(
        OUTPUT_DIR.glob("HR_Hit_Drought_v40_appdata-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError("No v40 appdata JSON was created.")
    return files[0]


def _write_v41_json(data: dict, season: int, target_date: str) -> Path:
    now_stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = OUTPUT_DIR / (
        f"HR_Hit_Drought_v41_appdata-{season}_{target_date}_{target_date}_{now_stamp}.json"
    )
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return out


def main(season: int, target_date: str):
    # Run the v40 builder first. This creates the latest app snapshot on disk.
    run_v40_main(season, target_date)

    latest_v40 = _latest_v40_json()

    with open(latest_v40, "r", encoding="utf-8") as f:
        data = json.load(f)

    # For now, v41 is a pass-through wrapper around the latest v40 appdata.
    v41_path = _write_v41_json(data, season, target_date)

    print(f"✅ v41 JSON created: {v41_path}")

    return {
        "status": "success",
        "message": "v41 built successfully",
        "v40_source": str(latest_v40),
        "v41_output": str(v41_path),
    }


if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    print(main(2026, today))
