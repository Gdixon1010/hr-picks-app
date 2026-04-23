import os
import json
from pathlib import Path
from datetime import datetime

from hr_v40_2_json_export_ready import main as run_v40_main


# Force BOTH v40 and v41 to use the same shared Render output directory.
RENDER_OUTPUT_DIR = "/var/data/hr-picks/output"
os.environ["HR_APP_DATA_DIR"] = RENDER_OUTPUT_DIR

OUTPUT_DIR = Path(os.getenv("HR_APP_DATA_DIR", RENDER_OUTPUT_DIR))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _matching_v40_json(target_date: str) -> Path:
    """
    Find the newest v40 appdata JSON whose filename matches the requested target_date.
    Example:
    HR_Hit_Drought_v40_appdata-2026_2026-04-23_2026-04-23_1047.json
    """
    pattern = f"HR_Hit_Drought_v40_appdata-*_{target_date}_{target_date}_*.json"
    files = sorted(
        OUTPUT_DIR.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(
            f"No v40 appdata JSON was created for target_date={target_date} in {OUTPUT_DIR}."
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

    # Pick the newest v40 file that matches the requested date.
    matching_v40 = _matching_v40_json(target_date)

    with open(matching_v40, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Safety: force payload date to match the requested target date.
    data["date"] = target_date

    # v41 is currently a pass-through wrapper around the date-matched v40 appdata.
    v41_path = _write_v41_json(data, season, target_date)

    print(f"✅ v41 JSON created: {v41_path}")

    return {
        "status": "success",
        "message": "v41 built successfully",
        "target_date": target_date,
        "output_dir": str(OUTPUT_DIR),
        "v40_source": str(matching_v40),
        "v41_output": str(v41_path),
    }


if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    print(main(2026, today))
