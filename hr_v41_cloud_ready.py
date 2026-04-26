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
    files = [
        p for p in OUTPUT_DIR.glob("HR_Hit_Drought_v41_appdata-*.json")
        if target_date in p.name
    ]
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _write_v41_json(data: dict, season: int, target_date: str) -> Path:
    now_stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = OUTPUT_DIR / (
        f"HR_Hit_Drought_v41_appdata-{season}_{target_date}_{target_date}_{now_stamp}.json"
    )
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return out


def _norm(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def _is_placeholder(row: dict) -> bool:
    if not isinstance(row, dict):
        return True

    text = " ".join(str(v).lower() for v in row.values())

    return (
        "no plays" in text
        or "no qualified" in text
        or "no final card plays qualified" in text
        or row.get("category") == "Info"
        or row.get("bet_type") == "No Plays"
    )


def _merge_rows(old_rows: list, new_rows: list, key_fields: list) -> list:
    old_rows = old_rows if isinstance(old_rows, list) else []
    new_rows = new_rows if isinstance(new_rows, list) else []

    old_real = [r for r in old_rows if isinstance(r, dict) and not _is_placeholder(r)]
    new_real = [r for r in new_rows if isinstance(r, dict) and not _is_placeholder(r)]

    rows_to_merge = old_real + new_real

    if not rows_to_merge:
        return old_rows if old_rows else new_rows

    merged = []
    seen = set()

    for row in rows_to_merge:
        key = tuple(_norm(row.get(field)) for field in key_fields)

        if key not in seen:
            seen.add(key)
            merged.append(row)

    return merged


def main(season: int, target_date: str):

    os.environ["HR_APP_DATA_DIR"] = str(OUTPUT_DIR)

    run_v40_main(season, target_date)

    latest_v40 = _latest_v40_json()

    with open(latest_v40, "r", encoding="utf-8") as f:
        new_data = json.load(f)

    prev_file = _latest_v41_today_json(target_date)

    if prev_file:
        print(f"🔒 Loading previous same-day v41 file: {prev_file}")

        with open(prev_file, "r", encoding="utf-8") as f:
            old_data = json.load(f)

        new_data["final_card"] = _merge_rows(
            old_data.get("final_card", []),
            new_data.get("final_card", []),
            ["pick", "playerName", "team", "opponent", "bet_type"]
        )

        new_data["refined_picks"] = _merge_rows(
            old_data.get("refined_picks", []),
            new_data.get("refined_picks", []),
            ["category", "bet_type", "playerName", "teamName", "opponent_pitcher"]
        )

        if "top_picks" in old_data or "top_picks" in new_data:
            new_data["top_picks"] = _merge_rows(
                old_data.get("top_picks", []),
                new_data.get("top_picks", []),
                ["category", "bet_type", "playerName", "teamName"]
            )

        for key in [
            "graded_results",
            "results",
            "performance_summary",
            "performance_summary_latest",
            "results_history",
            "results_history_latest",
        ]:
            if key in old_data and key not in new_data:
                new_data[key] = old_data[key]

    else:
        print(f"⚠️ No previous v41 file found for {target_date}; starting fresh.")

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
