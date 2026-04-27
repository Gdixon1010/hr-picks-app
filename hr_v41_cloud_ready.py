import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from hr_v40_2_json_export_ready import main as run_v40_main

EASTERN = ZoneInfo("America/New_York")


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
HISTORY_DIR = OUTPUT_DIR / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any):
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ Could not read JSON {path}: {e}")
    return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def _now_et() -> datetime:
    return datetime.now(EASTERN)


def _locked_until_for_slate(target_date: str) -> str:
    slate_day = datetime.strptime(target_date, "%Y-%m-%d").date()
    unlock_dt = datetime.combine(slate_day + timedelta(days=1), datetime.min.time(), tzinfo=EASTERN).replace(hour=4)
    return unlock_dt.isoformat()


def _is_before_unlock(target_date: str) -> bool:
    try:
        return _now_et() < datetime.fromisoformat(_locked_until_for_slate(target_date))
    except Exception:
        return True


def _latest_v40_json() -> Path:
    files = sorted(
        OUTPUT_DIR.glob("HR_Hit_Drought_v40_appdata-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(f"No v40 JSON found in {OUTPUT_DIR}")
    return files[0]


def _all_v41_for_date(target_date: str) -> list[Path]:
    files = [p for p in OUTPUT_DIR.glob("HR_Hit_Drought_v41_appdata-*.json") if target_date in p.name]
    return sorted(files, key=lambda p: p.stat().st_mtime)


def _write_v41_json(data: dict, season: int, target_date: str) -> Path:
    now_stamp = _now_et().strftime("%Y%m%d_%H%M")
    out = OUTPUT_DIR / f"HR_Hit_Drought_v41_appdata-{season}_{target_date}_{target_date}_{now_stamp}.json"
    _write_json(out, data)
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


def _rows(value) -> list:
    return value if isinstance(value, list) else []


def _merge_rows(*row_sets: list, key_fields: list) -> list:
    merged = []
    seen = set()
    for rows in row_sets:
        for row in _rows(rows):
            if not isinstance(row, dict) or _is_placeholder(row):
                continue
            key = tuple(_norm(row.get(field)) for field in key_fields)
            if not any(key):
                key = tuple(sorted((str(k), _norm(v)) for k, v in row.items()))
            if key not in seen:
                seen.add(key)
                merged.append(row)
    return merged


def _get_final_card_plays(data: dict) -> list:
    fc = data.get("final_card")
    if isinstance(fc, dict):
        rows = _rows(fc.get("plays"))
    elif isinstance(fc, list):
        rows = _rows(fc)
    else:
        rows = []
    if not rows and isinstance(data.get("research"), dict):
        rows = _rows(data["research"].get("final_card"))
    return rows


def _set_final_card_plays(data: dict, rows: list) -> None:
    data["final_card"] = {"generated_section": "final_card", "plays": rows}
    data.setdefault("research", {})
    if isinstance(data["research"], dict):
        data["research"]["final_card"] = rows


def _get_research_rows(data: dict, key: str) -> list:
    research = data.get("research") if isinstance(data.get("research"), dict) else {}
    return _rows(research.get(key)) or _rows(data.get(key))


def _set_research_rows(data: dict, key: str, rows: list) -> None:
    data.setdefault("research", {})
    if isinstance(data["research"], dict):
        data["research"][key] = rows
    data[key] = rows


def _by_date_path(card_name: str) -> Path:
    return HISTORY_DIR / f"{card_name}_by_date.json"


def _latest_path(card_name: str) -> Path:
    return HISTORY_DIR / f"{card_name}_by_date_latest.json"


def _load_locked_rows(card_name: str, target_date: str) -> list:
    by_date = _read_json(_by_date_path(card_name), {})
    if isinstance(by_date, dict):
        entry = by_date.get(target_date) or {}
        if isinstance(entry, dict):
            return _rows(entry.get("rows"))
        if isinstance(entry, list):
            return _rows(entry)
    return []


def _save_locked_rows(card_name: str, target_date: str, rows: list, source_file: str | None = None) -> None:
    real_rows = [r for r in _rows(rows) if isinstance(r, dict) and not _is_placeholder(r)]
    payload = {
        "target_date": target_date,
        "locked_until_et": _locked_until_for_slate(target_date),
        "updated_at_et": _now_et().strftime("%Y-%m-%d %I:%M %p ET").replace(" 0", " "),
        "source_file": source_file,
        "rows": real_rows,
    }

    by_date_path = _by_date_path(card_name)
    by_date = _read_json(by_date_path, {})
    if not isinstance(by_date, dict):
        by_date = {}
    by_date[target_date] = payload
    _write_json(by_date_path, by_date)
    _write_json(_latest_path(card_name), payload)


def _recover_rows_from_existing_v41(target_date: str, row_getter) -> list:
    rows = []
    for path in _all_v41_for_date(target_date):
        data = _read_json(path, {})
        rows.extend(row_getter(data))
    return rows


def main(season: int, target_date: str):
    os.environ["HR_APP_DATA_DIR"] = str(OUTPUT_DIR)

    run_v40_main(season, target_date)

    latest_v40 = _latest_v40_json()
    with open(latest_v40, "r", encoding="utf-8") as f:
        new_data = json.load(f)

    # Gather every source that might contain same-slate picks:
    # 1) persistent history lock, 2) all previous same-date v41 files, 3) the new v40 run.
    locked_final_rows = _load_locked_rows("final_card", target_date)
    locked_refined_rows = _load_locked_rows("refined_picks", target_date)

    recovered_final_rows = _recover_rows_from_existing_v41(target_date, _get_final_card_plays)
    recovered_refined_rows = _recover_rows_from_existing_v41(target_date, lambda d: _get_research_rows(d, "refined_picks"))
    recovered_top_rows = _recover_rows_from_existing_v41(target_date, lambda d: _get_research_rows(d, "top_picks"))

    new_final_rows = _get_final_card_plays(new_data)
    new_refined_rows = _get_research_rows(new_data, "refined_picks")
    new_top_rows = _get_research_rows(new_data, "top_picks")

    final_rows = _merge_rows(
        locked_final_rows,
        recovered_final_rows,
        new_final_rows,
        key_fields=["bet_type", "pick", "playerName", "pitcherName", "team", "teamName", "opponent", "opponentTeam"],
    )
    refined_rows = _merge_rows(
        locked_refined_rows,
        recovered_refined_rows,
        new_refined_rows,
        key_fields=["category", "bet_type", "playerName", "pick", "teamName", "team", "game", "opponent_pitcher"],
    )
    top_rows = _merge_rows(
        recovered_top_rows,
        new_top_rows,
        key_fields=["type", "category", "bet_type", "playerName", "pick", "teamName", "team"],
    )

    # Before 4 AM ET the next day, nothing from this slate may be removed.
    # After 4 AM, this still preserves the historical lock file, but today's new target_date starts fresh.
    _set_final_card_plays(new_data, final_rows)
    _set_research_rows(new_data, "refined_picks", refined_rows)
    if top_rows:
        _set_research_rows(new_data, "top_picks", top_rows)

    _save_locked_rows("final_card", target_date, final_rows, source_file=latest_v40.name)
    _save_locked_rows("refined_picks", target_date, refined_rows, source_file=latest_v40.name)

    # Keep any existing result snapshots that v40 does not create.
    for key in [
        "graded_results",
        "results",
        "performance_summary",
        "performance_summary_latest",
        "results_history",
        "results_history_latest",
    ]:
        if key not in new_data:
            old_value = _read_json(HISTORY_DIR / f"{key}.json", None)
            if old_value is not None:
                new_data[key] = old_value

    v41_path = _write_v41_json(new_data, season, target_date)

    print(f"✅ v41 JSON created: {v41_path}")
    print(f"🔒 4AM lock active for slate {target_date}: {_is_before_unlock(target_date)}")
    print(f"🔒 Final Card locked rows: {len(final_rows)}")
    print(f"🔒 Refined Picks locked rows: {len(refined_rows)}")
    print(f"🔒 Locked until ET: {_locked_until_for_slate(target_date)}")

    return {
        "status": "success",
        "message": "v41 built successfully with 4AM Final Card + Refined Picks lock",
        "v41_output": str(v41_path),
        "final_card_locked_rows": len(final_rows),
        "refined_picks_locked_rows": len(refined_rows),
        "locked_until_et": _locked_until_for_slate(target_date),
    }


def _active_slate_date() -> str:
    now = _now_et()
    if now.hour < 4:
        return (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")
    return now.date().strftime("%Y-%m-%d")


if __name__ == "__main__":
    print(main(2026, _active_slate_date()))
