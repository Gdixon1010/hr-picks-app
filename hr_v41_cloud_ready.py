import os
import json
from pathlib import Path
from datetime import datetime

from hr_v40_2_json_export_ready import main as run_v40_main


OUTPUT_DIR = Path(os.getenv("HR_APP_DATA_DIR", "output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _matching_v40_json(target_date: str) -> Path:
    """
    Find the newest v40 appdata JSON whose filename includes the requested target_date.
    Example filename:
    HR_Hit_Drought_v40_appdata-2026_2026-04-23_2026-04-23_0647.json
    """
    pattern = f"HR_Hit_Drought_v40_appdata-*_{target_date}_{target_date}_*.json"
    files = sorted(
        OUTPUT_DIR.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(
            f"No v40 appdata JSON was created for target_date={target_date}."
        )
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
    # Run the v40 builder first for the requested date.
    run_v40_main(season, target_date)

    # IMPORTANT: pick the v40 file that matches the requested target_date,
    # not just the most recently modified file overall.
    matching_v40 = _matching_v40_json(target_date)

    with open(matching_v40, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Safety: force the payload date to match the requested target_date.
    data["date"] = target_date

    # For now, v41 is a pass-through wrapper around the matching v40 appdata.
    v41_path = _write_v41_json(data, season, target_date)

    print(f"✅ v41 JSON created: {v41_path}")

    return {
        "status": "success",
        "message": "v41 built successfully",
        "target_date": target_date,
        "v40_source": str(matching_v40),
        "v41_output": str(v41_path),
    }


if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    print(main(2026, today))
