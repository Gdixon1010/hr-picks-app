import os
import json
from pathlib import Path
from datetime import datetime

from hr_v40_2_json_export_ready import main as run_v40_main


def resolve_storage_dir() -> Path:
    configured = os.getenv("HR_APP_DATA_DIR")
    if configured:
        p = Path(configured)
        p.mkdir(parents=True, exist_ok=True)
        return p

    render_default = Path("/var/data/hr-picks/output")
    if render_default.parent.exists():
        render_default.mkdir(parents=True, exist_ok=True)
        return render_default

    local_default = Path("output")
    local_default.mkdir(parents=True, exist_ok=True)
    return local_default


OUTPUT_DIR = resolve_storage_dir()


def _latest_v40_json() -> Path:
    files = sorted(
        OUTPUT_DIR.glob("HR_Hit_Drought_v40_appdata-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(f"No v40 JSON found in {OUTPUT_DIR}")
    return files[0]


def _latest_v41_today_json(target_date: str) -> Path | None:
    files = sorted(
        OUTPUT_DIR.glob(f"HR_Hit_Drought_v41_appdata-*-{target_date}_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def _write_v41_json(data: dict, season: int, target_date: str) -> Path:
    now_stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = OUTPUT_DIR / (
        f"HR_Hit_Drought_v41_appdata-{season}_{target_date}_{target_date}_{now_stamp}.json"
    )
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return out


def _merge_final_cards(old_card: list, new_card: list) -> list:
    seen = set()
    merged = []

    for pick in old_card + new_card:
        key = (
            pick.get("playerName"),
            pick.get("team"),
            pick.get("opponent"),
            pick.get("bet_type"),
        )
        if key not in seen:
            seen.add(key)
            merged.append(pick)

    return merged


def main(season: int, target_date: str):

    os.environ["HR_APP_DATA_DIR"] = str(OUTPUT_DIR)

    # Run model
    run_v40_main(season, target_date)

    latest_v40 = _latest_v40_json()

    with open(latest_v40, "r", encoding="utf-8") as f:
        new_data = json.load(f)

    # 🔥 Load previous SAME-DAY card if exists
    prev_file = _latest_v41_today_json(target_date)

    if prev_file:
        with open(prev_file, "r", encoding="utf-8") as f:
            old_data = json.load(f)

        old_card = old_data.get("final_card", [])
        new_card = new_data.get("final_card", [])

        merged_card = _merge_final_cards(old_card, new_card)

        new_data["final_card"] = merged_card

        # 🔥 KEEP previous graded results
        if "graded_results" in old_data:
            new_data["graded_results"] = old_data["graded_results"]

    v41_path = _write_v41_json(new_data, season, target_date)

    print(f"✅ v41 JSON created: {v41_path}")

    return {
        "status": "success",
        "message": "v41 built successfully",
        "v41_output": str(v41_path),
    }


if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    print(main(2026, today))
