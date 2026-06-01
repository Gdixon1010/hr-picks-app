import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

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
HISTORY_DIR = OUTPUT_DIR / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def active_slate_date(now_et=None) -> str:
    """Slate day runs 4:00 AM ET to 3:59 AM ET next calendar day."""
    if now_et is None:
        now_et = datetime.now(ZoneInfo("America/New_York"))
    if now_et.tzinfo is None:
        now_et = now_et.replace(tzinfo=ZoneInfo("America/New_York"))
    if now_et.hour < 4:
        return (now_et.date() - timedelta(days=1)).strftime("%Y-%m-%d")
    return now_et.date().strftime("%Y-%m-%d")


def _latest_v40_json(target_date: str | None = None) -> Path:
    files = list(OUTPUT_DIR.glob("HR_Hit_Drought_v40_appdata-*.json"))
    if target_date:
        files = [p for p in files if target_date in p.name]
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No v40 JSON found in {OUTPUT_DIR} for {target_date or 'any date'}")
    return files[0]


def _latest_v41_json_for_date(target_date: str) -> Path | None:
    files = [p for p in OUTPUT_DIR.glob("HR_Hit_Drought_v41_appdata-*.json") if target_date in p.name]
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _write_v41_json(data: dict, season: int, target_date: str) -> Path:
    now_stamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d_%H%M")
    out = OUTPUT_DIR / f"HR_Hit_Drought_v41_appdata-{season}_{target_date}_{target_date}_{now_stamp}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return out


def _read_json(path: Path, default: Any):
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


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
        or "no plus-money prop candidates" in text
        or "no plus money prop candidates" in text
        or row.get("category") == "Info"
        or row.get("bet_type") == "No Plays"
    )


def _rows(value) -> list:
    return value if isinstance(value, list) else []


def _merge_rows(old_rows: list, new_rows: list, key_fields: list) -> list:
    """Non-destructive same-slate merge.

    Preserves locked rows during refresh, but enriches them with new fields when the
    model adds fields later. This is important for recent_cash_* and plus-money
    bet_type/prop_type fixes.
    """
    old_rows = _rows(old_rows)
    new_rows = _rows(new_rows)
    old_real = [dict(r) for r in old_rows if isinstance(r, dict) and not _is_placeholder(r)]
    new_real = [dict(r) for r in new_rows if isinstance(r, dict) and not _is_placeholder(r)]
    rows_to_merge = old_real + new_real
    if not rows_to_merge:
        return old_rows if old_rows else new_rows

    def has_value(v) -> bool:
        if v is None:
            return False
        return str(v).strip() not in {"", "—", "None", "nan", "NaN"}

    merged = []
    index_by_key = {}
    for row in rows_to_merge:
        key = tuple(_norm(row.get(field)) for field in key_fields)
        if not any(key):
            key = tuple(sorted((str(k), _norm(v)) for k, v in row.items()))
        if key not in index_by_key:
            index_by_key[key] = len(merged)
            merged.append(dict(row))
            continue

        existing = merged[index_by_key[key]]
        for k, v in row.items():
            if not has_value(existing.get(k)) and has_value(v):
                existing[k] = v
            elif k.startswith("recent_cash") and has_value(v):
                existing[k] = v
            elif k in {"bet_type", "prop_type"} and has_value(v):
                existing[k] = v

    return merged


def _normalize_plus_money_rows(rows: list) -> list:
    """Guarantee Plus Money Props always carry a gradeable bet_type."""
    out = []
    for r in _rows(rows):
        if not isinstance(r, dict):
            continue
        row = dict(r)
        prop = row.get("prop_type")
        bet = row.get("bet_type")
        if (bet is None or str(bet).strip() in {"", "—", "None", "nan"}) and prop not in (None, "", "—"):
            row["bet_type"] = prop
        out.append(row)
    return out



def _elite_final_rows(rows: list) -> list:
    """Final Card reset filter for elite-only mode.

    Same-day Final Card is allowed to tighten/remove old Core rows when the
    model rules change. This prevents old locked Moneyline/Core picks from
    surviving after the user switches to elite-only Final Card logic.
    """
    out = []
    for r in _rows(rows):
        if not isinstance(r, dict) or _is_placeholder(r):
            continue
        bet = str(r.get("bet_type") or "").strip()
        slot = str(r.get("slot") or "").strip()
        conf = str(r.get("confidence") or "").strip()
        # Official Final Card now only accepts explicitly elite rows created by v40.
        if slot.startswith("Elite") and conf == "A+" and bet in {"1+ Hit", "K Prop"}:
            out.append(dict(r))
    return out

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



def _best_previous_final_rows_for_date(target_date: str) -> list:
    """Recover the newest real Elite Final Card rows from any same-day v41/v40 file.

    This is a safety net for cases where a newer refresh wrote an empty card before
    the append-only lock was installed.
    """
    files = sorted(
        list(OUTPUT_DIR.glob("HR_Hit_Drought_v41_appdata-*.json")) +
        list(OUTPUT_DIR.glob("HR_Hit_Drought_v40_appdata-*.json")),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    for f in files:
        if target_date not in f.name:
            continue
        try:
            data = _read_json(f, {})
            rows = _elite_final_rows(_get_final_card_plays(data))
            if rows:
                print(f"🔒 Recovered previous Final Card from {f}: {len(rows)} rows")
                return rows
        except Exception:
            pass
    return []


def _merge_final_card_append_only(old_rows: list, new_rows: list, max_rows: int = 3) -> list:
    """Append-only Final Card merge.

    Old rows win and stay in place. New rows can only add if there is room.
    Duplicate players are ignored even if their Elite slot number changed.
    """
    merged = []
    seen = set()

    def key_for(row: dict):
        return (
            _norm(row.get("bet_type")),
            _norm(row.get("pick")),
            _norm(row.get("team")),
            _norm(row.get("opponent")),
        )

    for source_rows in (_rows(old_rows), _rows(new_rows)):
        for r in source_rows:
            if not isinstance(r, dict) or _is_placeholder(r):
                continue
            row = dict(r)
            key = key_for(row)
            if not any(key) or key in seen:
                continue
            seen.add(key)
            merged.append(row)
            if len(merged) >= max_rows:
                break
        if len(merged) >= max_rows:
            break

    for i, r in enumerate(merged, 1):
        r["slot"] = f"Elite {i}"
        r["confidence"] = "A+"
        r["final_card_tier"] = r.get("final_card_tier") or "Elite"

    return merged


def _refined_to_elite_final_rows(data: dict) -> list:
    """Promote qualified Refined Picks into Elite Final Card when v40 final_card is empty/placeholder.

    This is a fallback only. It uses the same strict Elite hit gate:
    Confirmed Starter, batting 1-5, Hit_score >= 5.00, contact >= 3.40,
    L10 hit >= 80%, recent cash >= 70%, and opponent is not Strong SP.
    """
    rows = _get_research_rows(data, "refined_picks")
    out = []

    def num(v, default=0.0):
        try:
            if v is None:
                return default
            return float(v)
        except Exception:
            return default

    candidates = []
    for r in _rows(rows):
        if not isinstance(r, dict) or _is_placeholder(r):
            continue
        if str(r.get("bet_type") or "") != "1+ Hit":
            continue
        lineup = str(r.get("lineup_status") or "")
        slot = num(r.get("batting_order_slot"), 99)
        if lineup != "Confirmed Starter" or slot > 5:
            continue
        if num(r.get("Hit_score")) < 5.00:
            continue
        if num(r.get("contact_quality_score")) < 3.40:
            continue
        if num(r.get("hit_pct_last_10")) < 80:
            continue
        if num(r.get("recent_cash_rate"), -1) < 0.70:
            continue
        if str(r.get("opponent_pitcher_pick_type") or "Neutral") == "Strong SP":
            continue
        candidates.append(r)

    candidates = sorted(
        candidates,
        key=lambda r: (
            num(r.get("Hit_score")),
            num(r.get("contact_quality_score")),
            num(r.get("hit_pct_last_10")),
            num(r.get("recent_cash_rate")),
            -num(r.get("batting_order_slot"), 99),
        ),
        reverse=True,
    )

    used_teams = set()
    for r in candidates:
        team = r.get("teamName")
        if team in used_teams:
            continue
        used_teams.add(team)
        out.append({
            "slot": f"Elite {len(out) + 1}",
            "bet_type": "1+ Hit",
            "pick": r.get("playerName"),
            "team": team,
            "opponent": r.get("opponentTeam") or r.get("opponent_pitcher_team"),
            "confidence": "A+",
            "why_it_made_the_card": (
                f"Elite refined fallback; Hit_score {r.get('Hit_score')}; "
                f"contact {r.get('contact_quality_score')}; "
                f"L10 hit {r.get('hit_pct_last_10')}%; "
                f"slot {r.get('batting_order_slot')}; "
                f"recent cash {r.get('recent_cash_rate')}; "
                f"opp {r.get('opponent_pitcher_pick_type')}"
            ),
            "source_tab": "Refined_Picks",
            "final_card_tier": "Elite",
        })
        if len(out) >= 3:
            break

    return out

def _get_research_rows(data: dict, key: str) -> list:
    research = data.get("research") if isinstance(data.get("research"), dict) else {}
    rows = _rows(research.get(key))
    if not rows:
        rows = _rows(data.get(key))
    return rows


def _set_research_rows(data: dict, key: str, rows: list) -> None:
    data.setdefault("research", {})
    if isinstance(data["research"], dict):
        data["research"][key] = rows
    data[key] = rows


def _history_rows(kind: str, target_date: str) -> list:
    path = HISTORY_DIR / f"{kind}_by_date.json"
    by_date = _read_json(path, {})
    if isinstance(by_date, dict):
        return _rows((by_date.get(target_date) or {}).get("rows"))
    return []


def _update_history(kind: str, target_date: str, rows: list) -> None:
    real_rows = [r for r in _rows(rows) if isinstance(r, dict) and not _is_placeholder(r)]
    by_date_path = HISTORY_DIR / f"{kind}_by_date.json"
    latest_path = HISTORY_DIR / f"{kind}_by_date_latest.json"
    by_date = _read_json(by_date_path, {})
    if not isinstance(by_date, dict):
        by_date = {}

    # HARD SAFETY: Final Card must never be overwritten with an empty list
    # during the same active slate. It can reset naturally after the 4 AM slate rollover.
    if kind == "final_card" and not real_rows:
        existing_payload = by_date.get(target_date) if isinstance(by_date.get(target_date), dict) else {}
        existing_rows = _rows(existing_payload.get("rows"))
        if existing_rows:
            print(f"🔒 Final Card overwrite blocked: keeping {len(existing_rows)} locked rows for {target_date}")
            _write_json(latest_path, existing_payload)
            return
        latest_payload = _read_json(latest_path, {})
        if isinstance(latest_payload, dict) and latest_payload.get("target_date") == target_date:
            latest_rows = _rows(latest_payload.get("rows"))
            if latest_rows:
                print(f"🔒 Final Card empty overwrite blocked from latest file: keeping {len(latest_rows)} rows for {target_date}")
                by_date[target_date] = latest_payload
                _write_json(by_date_path, by_date)
                return

    payload = {
        "target_date": target_date,
        "saved_at_et": datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M %p ET").replace(" 0", " "),
        "locked_until_et": f"{(datetime.strptime(target_date, '%Y-%m-%d').date() + timedelta(days=1)).strftime('%Y-%m-%d')} 04:00 AM ET",
        "rows": real_rows,
    }
    by_date[target_date] = payload
    _write_json(by_date_path, by_date)
    _write_json(latest_path, payload)

def main(season: int, target_date: str):
    """Build V41 payload with non-destructive 4AM slate locking.

    The server should pass the active slate date. If called before 4 AM ET with the
    calendar date by mistake, this function still corrects it to yesterday.
    """
    now_et = datetime.now(ZoneInfo("America/New_York"))
    corrected_slate = active_slate_date(now_et)
    if now_et.hour < 4 and target_date != corrected_slate:
        print(f"🔒 Before 4 AM ET: overriding requested date {target_date} -> active slate {corrected_slate}")
        target_date = corrected_slate

    os.environ["HR_APP_DATA_DIR"] = str(OUTPUT_DIR)

    run_v40_main(season, target_date)
    latest_v40 = _latest_v40_json(target_date)

    with open(latest_v40, "r", encoding="utf-8") as f:
        new_data = json.load(f)

    _set_research_rows(new_data, "plus_money_props", _normalize_plus_money_rows(_get_research_rows(new_data, "plus_money_props")))

    prev_file = _latest_v41_json_for_date(target_date)
    old_data = {}
    if prev_file:
        print(f"🔒 Loading previous same-slate v41 file: {prev_file}")
        with open(prev_file, "r", encoding="utf-8") as f:
            old_data = json.load(f)
    else:
        print(f"⚠️ No previous v41 file found for {target_date}; using history locks if present.")

    # Pull locked history too. This protects against a bad/empty latest v41 file.
    old_final_candidates = []
    old_final_candidates.extend(_get_final_card_plays(old_data))
    old_final_candidates.extend(_history_rows("final_card", target_date))

    old_refined_candidates = []
    old_refined_candidates.extend(_get_research_rows(old_data, "refined_picks"))
    old_refined_candidates.extend(_history_rows("refined_picks", target_date))

    old_plus_money_candidates = []
    old_plus_money_candidates.extend(_normalize_plus_money_rows(_get_research_rows(old_data, "plus_money_props")))
    old_plus_money_candidates.extend(_normalize_plus_money_rows(_history_rows("plus_money_props", target_date)))

    # Elite Final Card append-only lock:
    # - old Elite plays stay locked until 4 AM ET
    # - new Elite plays may be added if room remains
    # - an empty/placeholder refresh can never wipe the existing Final Card
    old_elite_final = _elite_final_rows(old_final_candidates)
    if not old_elite_final:
        old_elite_final = _best_previous_final_rows_for_date(target_date)

    new_elite_final = _elite_final_rows(_get_final_card_plays(new_data))
    if not new_elite_final:
        new_elite_final = _refined_to_elite_final_rows(new_data)

    merged_final = _merge_final_card_append_only(old_elite_final, new_elite_final, max_rows=3)
    _set_final_card_plays(new_data, merged_final)

    merged_refined = _merge_rows(
        old_refined_candidates,
        _get_research_rows(new_data, "refined_picks"),
        ["category", "bet_type", "playerName", "teamName", "game", "opponent_pitcher"],
    )
    _set_research_rows(new_data, "refined_picks", merged_refined)

    merged_plus_money = _merge_rows(
        old_plus_money_candidates,
        _get_research_rows(new_data, "plus_money_props"),
        ["prop_type", "bet_type", "pick", "playerName", "team", "teamName", "opponent", "game"],
    )
    if merged_plus_money:
        _set_research_rows(new_data, "plus_money_props", merged_plus_money)

    merged_top = _merge_rows(
        _get_research_rows(old_data, "top_picks"),
        _get_research_rows(new_data, "top_picks"),
        ["type", "category", "bet_type", "playerName", "teamName"],
    )
    if merged_top:
        _set_research_rows(new_data, "top_picks", merged_top)

    new_data["date"] = target_date
    new_data.setdefault("_meta", {})
    if isinstance(new_data["_meta"], dict):
        new_data["_meta"]["active_slate_date"] = target_date
        new_data["_meta"]["locked_until_et"] = f"{(datetime.strptime(target_date, '%Y-%m-%d').date() + timedelta(days=1)).strftime('%Y-%m-%d')} 04:00 AM ET"

    _update_history("final_card", target_date, _get_final_card_plays(new_data))
    _update_history("refined_picks", target_date, _get_research_rows(new_data, "refined_picks"))
    _set_research_rows(new_data, "plus_money_props", _normalize_plus_money_rows(_get_research_rows(new_data, "plus_money_props")))
    _update_history("plus_money_props", target_date, _get_research_rows(new_data, "plus_money_props"))

    v41_path = _write_v41_json(new_data, season, target_date)

    print(f"✅ v41 JSON created: {v41_path}")
    print(f"🔒 Active slate date: {target_date}")
    print(f"🔒 Final Card locked rows: {len(_get_final_card_plays(new_data))}")
    print(f"🔒 Refined Picks locked rows: {len(_get_research_rows(new_data, 'refined_picks'))}")
    print(f"🔒 Plus Money Props locked rows: {len(_get_research_rows(new_data, 'plus_money_props'))}")

    return {
        "status": "success",
        "message": "v41 built successfully with true 4AM active-slate lock",
        "active_slate_date": target_date,
        "v41_output": str(v41_path),
    }


if __name__ == "__main__":
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    print(main(2026, today))
