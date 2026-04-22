from __future__ import annotations

import json
import argparse
import datetime as dt
import re
import time
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from openpyxl import load_workbook
from openpyxl.styles import PatternFill



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
def _clean_value(v):
    """Convert pandas/numpy values into JSON-safe Python values."""
    try:
        import math
        import numpy as np
        import pandas as pd
    except Exception:
        np = None
        pd = None
        math = None

    if v is None:
        return None

    if pd is not None and pd.isna(v):
        return None

    if np is not None:
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return None if np.isnan(v) else float(v)
        if isinstance(v, (np.bool_,)):
            return bool(v)

    if isinstance(v, float):
        if math is not None and math.isnan(v):
            return None
        return float(v)

    if isinstance(v, (int, str, bool)):
        return v

    return str(v)


def df_to_records(df):
    """Convert dataframe to JSON-safe list of dicts."""
    if df is None or len(df) == 0:
        return []

    records = df.to_dict(orient="records")
    cleaned = []
    for row in records:
        cleaned.append({k: _clean_value(v) for k, v in row.items()})
    return cleaned


def build_final_card_json(final_card_df):
    """Layer 1: final betting card."""
    return {
        "generated_section": "final_card",
        "plays": df_to_records(final_card_df)
    }


def build_game_cards_json(player_rows, game_rankings, pitcher_line_value):
    """
    Layer 2: group picks by game.
    Each game gets:
    - game_time_et
    - venue
    - ml_lean
    - top 2 HR picks
    - top 2 hit picks
    - top K prop if available
    """
    games_output = []

    if game_rankings is None or len(game_rankings) == 0:
        return games_output

    gr = game_rankings.copy()
    pr = player_rows.copy() if player_rows is not None else None
    plv = pitcher_line_value.copy() if pitcher_line_value is not None else None

    unique_games = gr["game"].dropna().unique().tolist()

    for game_name in unique_games:
        game_rank = gr[gr["game"] == game_name].copy()

        venue = None
        game_time_et = None
        game_datetime_utc = None
        if len(game_rank) > 0:
            venue = _clean_value(game_rank.iloc[0].get("venue"))
            game_time_et = _clean_value(game_rank.iloc[0].get("game_time_et"))
            game_datetime_utc = _clean_value(game_rank.iloc[0].get("game_datetime_utc"))

        ml_lean = None
        if len(game_rank) > 0:
            best_ml_row = game_rank.sort_values("edge_vs_opponent", ascending=False).iloc[0]
            ml_lean = {
                "team": _clean_value(best_ml_row.get("teamName")),
                "opponent": _clean_value(best_ml_row.get("opponentTeam")),
                "edge_vs_opponent": _clean_value(best_ml_row.get("edge_vs_opponent")),
                "recommended_play": _clean_value(best_ml_row.get("recommended_play")),
                "pitcher_pick_type": _clean_value(best_ml_row.get("pitcher_pick_type")),
                "opponent_pitcher_pick_type": _clean_value(best_ml_row.get("opponent_pitcher_pick_type")),
            }

        game_hit_picks = []
        game_hr_picks = []
        game_k_pick = None

        if pr is not None and len(pr) > 0:
            game_players = pr[pr["game"] == game_name].copy() if "game" in pr.columns else pd.DataFrame()

            if len(game_players) > 0:
                if "Hit_score" in game_players.columns:
                    top_hits = game_players.sort_values("Hit_score", ascending=False).head(2)
                    hit_cols = [c for c in [
                        "playerName", "teamName", "opponent_pitcher",
                        "opponent_pitcher_pick_type", "Hit_score",
                        "lineup_status", "batting_order_slot", "park_favorability"
                    ] if c in top_hits.columns]
                    game_hit_picks = df_to_records(top_hits[hit_cols])

                if "HR_score" in game_players.columns:
                    top_hrs = game_players.sort_values("HR_score", ascending=False).head(2)
                    hr_cols = [c for c in [
                        "playerName", "teamName", "opponent_pitcher",
                        "opponent_pitcher_pick_type", "HR_score",
                        "lineup_status", "batting_order_slot", "park_favorability"
                    ] if c in top_hrs.columns]
                    game_hr_picks = df_to_records(top_hrs[hr_cols])

        if plv is not None and len(plv) > 0 and len(game_rank) > 0:
            teams_in_game = set(game_rank["teamName"].dropna().tolist())
            game_pitchers = plv[plv["teamName"].isin(teams_in_game)].copy()

            if len(game_pitchers) > 0:
                sort_col = "projected_k_mid" if "projected_k_mid" in game_pitchers.columns else "pitcher_score_adj"
                game_pitchers = game_pitchers.sort_values(sort_col, ascending=False)
                best_k = game_pitchers.iloc[0]
                game_k_pick = {
                    "pitcherName": _clean_value(best_k.get("pitcherName")),
                    "teamName": _clean_value(best_k.get("teamName")),
                    "opponentTeam": _clean_value(best_k.get("opponentTeam")),
                    "recommended_k_action": _clean_value(best_k.get("recommended_k_action")),
                    "max_playable_k_line": _clean_value(best_k.get("max_playable_k_line")),
                    "projected_k_floor": _clean_value(best_k.get("projected_k_floor")),
                    "projected_k_mid": _clean_value(best_k.get("projected_k_mid")),
                    "projected_k_ceiling": _clean_value(best_k.get("projected_k_ceiling")),
                    "pick_type": _clean_value(best_k.get("pick_type")),
                }

        games_output.append({
            "game": game_name,
            "game_time_et": game_time_et,
            "game_datetime_utc": game_datetime_utc,
            "venue": venue,
            "ml_lean": ml_lean,
            "top_hit_picks": game_hit_picks,
            "top_hr_picks": game_hr_picks,
            "top_k_pick": game_k_pick
        })

    return games_output

def build_research_json(
    game_rankings,
    pitcher_metrics,
    pitcher_line_value,
    hr_drought,
    hit_drought,
    top_picks,
    refined_picks,
    final_card_df
):
    """Layer 3: all research tabs for app browsing."""
    return {
        "game_rankings": df_to_records(game_rankings),
        "pitcher_metrics": df_to_records(pitcher_metrics),
        "pitcher_line_value": df_to_records(pitcher_line_value),
        "hr_drought": df_to_records(hr_drought),
        "hit_drought": df_to_records(hit_drought),
        "top_picks": df_to_records(top_picks),
        "refined_picks": df_to_records(refined_picks),
        "final_card": df_to_records(final_card_df),
    }


def build_app_payload(
    target_date,
    final_card_df,
    player_rows,
    game_rankings,
    pitcher_metrics,
    pitcher_line_value,
    hr_drought,
    hit_drought,
    top_picks,
    refined_picks
):
    """Full JSON payload for the future iPhone app."""
    return {
        "date": str(target_date),
        "final_card": build_final_card_json(final_card_df),
        "games": build_game_cards_json(player_rows, game_rankings, pitcher_line_value),
        "research": build_research_json(
            game_rankings=game_rankings,
            pitcher_metrics=pitcher_metrics,
            pitcher_line_value=pitcher_line_value,
            hr_drought=hr_drought,
            hit_drought=hit_drought,
            top_picks=top_picks,
            refined_picks=refined_picks,
            final_card_df=final_card_df
        )
    }


def save_app_json(payload, output_path):
    """Write JSON file to disk."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def append_jsonl_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def upsert_history_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    new_df = pd.DataFrame(rows)
    if path.exists():
        try:
            old_df = pd.read_csv(path)
            combined = pd.concat([old_df, new_df], ignore_index=True)
        except Exception:
            combined = new_df.copy()
    else:
        combined = new_df.copy()

    # Track ONLY official frozen Final Card picks and dedupe them across refreshes.
    if "history_type" in combined.columns:
        combined = combined[combined["history_type"].astype(str).eq("final_card")].copy()

    for col in [
        "target_date", "history_type", "bet_type", "pick", "team", "opponent", "slot",
        "confidence", "source_tab", "result_status", "result_detail", "generated_at_et", "json_filename"
    ]:
        if col not in combined.columns:
            combined[col] = None

    # Dedupe official picks across refreshes. Do NOT include slot or run_id,
    # because the same official pick may move positions on the card during the day.
    dedupe_cols = [c for c in ["target_date", "history_type", "bet_type", "pick", "team", "opponent"] if c in combined.columns]
    if dedupe_cols:
        combined = combined.drop_duplicates(subset=dedupe_cols, keep="last")

    combined = combined.sort_values([c for c in ["target_date", "slot", "bet_type", "pick"] if c in combined.columns], ascending=True)
    combined.to_csv(path, index=False)


def build_pick_history_rows(target_date: str, run_ts_et: dt.datetime, json_filename: str, final_card_df: pd.DataFrame, top_picks_df: pd.DataFrame, game_rankings_df: pd.DataFrame, pitcher_line_value_df: pd.DataFrame) -> list[dict]:
    run_id = f"{target_date}_{run_ts_et.strftime('%Y%m%d_%H%M%S')}"
    run_ts_label = run_ts_et.strftime("%Y-%m-%d %I:%M:%S %p ET")
    rows: list[dict] = []

    # Official tracking = Final Card only.
    if final_card_df is not None and not final_card_df.empty:
        for _, r in final_card_df.iterrows():
            pick = _clean_value(r.get("pick"))
            bet_type = _clean_value(r.get("bet_type"))
            if not pick or str(bet_type).lower() == "no plays":
                continue
            rows.append({
                "run_id": run_id,
                "history_type": "final_card",
                "target_date": target_date,
                "generated_at_et": run_ts_label,
                "json_filename": json_filename,
                "slot": _clean_value(r.get("slot")),
                "bet_type": bet_type,
                "pick": pick,
                "team": _clean_value(r.get("team")),
                "opponent": _clean_value(r.get("opponent")),
                "game": None,
                "confidence": _clean_value(r.get("confidence")),
                "score": None,
                "why_it_made_the_card": _clean_value(r.get("why_it_made_the_card")),
                "source_tab": _clean_value(r.get("source_tab")),
                "result_status": "pending",
                "result_detail": None,
            })

    return rows


def save_pick_history(target_date: str, json_filename: str, final_card_df: pd.DataFrame, top_picks_df: pd.DataFrame, game_rankings_df: pd.DataFrame, pitcher_line_value_df: pd.DataFrame) -> dict:
    history_dir = OUTPUT_DIR / "history"
    run_ts_et = dt.datetime.now(ZoneInfo("America/New_York"))
    rows = build_pick_history_rows(target_date, run_ts_et, json_filename, final_card_df, top_picks_df, game_rankings_df, pitcher_line_value_df)

    jsonl_path = history_dir / "pick_history.jsonl"
    csv_path = history_dir / "pick_history.csv"
    latest_path = history_dir / "pick_history_latest.json"

    append_jsonl_rows(jsonl_path, rows)
    upsert_history_csv(csv_path, rows)

    latest_payload = {
        "target_date": target_date,
        "generated_at_et": run_ts_et.strftime("%Y-%m-%d %I:%M:%S %p ET"),
        "json_filename": json_filename,
        "records_saved": len(rows),
        "history_jsonl": str(jsonl_path),
        "history_csv": str(csv_path),
        "rows": rows,
    }
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(latest_payload, f, indent=2, ensure_ascii=False)

    return {
        "rows_saved": len(rows),
        "history_jsonl": jsonl_path,
        "history_csv": csv_path,
        "latest_json": latest_path,
    }




def save_latest_app_snapshot(target_date: str, app_payload: dict, json_filename: str) -> Path:
    history_dir = OUTPUT_DIR / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    latest_path = history_dir / "latest_app_data.json"
    payload = {
        "target_date": target_date,
        "saved_at_et": dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M:%S %p ET"),
        "json_filename": json_filename,
        "app_payload": app_payload,
    }
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return latest_path


def save_frozen_daily_final_card(target_date: str, final_card_df: pd.DataFrame) -> pd.DataFrame:
    # Store the frozen day-level Final Card separately from results/history cleanup.
    lock_dir = OUTPUT_DIR / "final_card_lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    store_path = lock_dir / "final_card_by_date.json"
    latest_path = lock_dir / "final_card_by_date_latest.json"

    try:
        store = json.loads(store_path.read_text(encoding="utf-8")) if store_path.exists() else {}
    except Exception:
        store = {}

    incoming_rows = df_to_records(final_card_df) if final_card_df is not None and not final_card_df.empty else []
    existing_rows = store.get(str(target_date), []) or []

    combined = existing_rows + incoming_rows
    frozen_rows = []
    seen = set()
    for row in combined:
        key = (
            str(row.get("bet_type") or ""),
            str(row.get("pick") or row.get("playerName") or ""),
            str(row.get("team") or row.get("teamName") or ""),
            str(row.get("opponent") or row.get("opponentTeam") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        frozen_rows.append(row)

    store[str(target_date)] = frozen_rows

    with open(store_path, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)

    latest_payload = {
        "target_date": str(target_date),
        "saved_at_et": dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M:%S %p ET"),
        "rows": frozen_rows,
    }
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(latest_payload, f, indent=2, ensure_ascii=False)

    # Backward-compatible mirror in history for older app readers, but the lock dir is source of truth.
    history_dir = OUTPUT_DIR / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    try:
        with open(history_dir / "final_card_by_date.json", "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2, ensure_ascii=False)
        with open(history_dir / "final_card_by_date_latest.json", "w", encoding="utf-8") as f:
            json.dump(latest_payload, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return pd.DataFrame(frozen_rows)


def get_schedule_results_for_date(target_date: str) -> pd.DataFrame:
    try:
        data = get_json(
            "https://statsapi.mlb.com/api/v1/schedule",
            params={"sportId": 1, "date": target_date, "hydrate": "team,linescore"},
        )
    except Exception:
        return pd.DataFrame(columns=["game","home_team","away_team","home_score","away_score","winner_team","completed","status"])

    rows = []
    for d in data.get("dates", []):
        for g in d.get("games", []):
            teams = g.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            home_team = (home.get("team") or {}).get("name")
            away_team = (away.get("team") or {}).get("name")
            home_score = home.get("score")
            away_score = away.get("score")
            status = ((g.get("status") or {}).get("detailedState") or "")
            completed = str(status).lower() in {"final", "game over", "completed early"}
            winner_team = None
            if completed and home_score is not None and away_score is not None:
                if int(home_score) > int(away_score):
                    winner_team = home_team
                elif int(away_score) > int(home_score):
                    winner_team = away_team
            game_name = f"{away_team} @ {home_team}"
            rows.append({
                "game": game_name,
                "home_team": home_team,
                "away_team": away_team,
                "home_score": home_score,
                "away_score": away_score,
                "winner_team": winner_team,
                "completed": completed,
                "status": status,
            })
    return pd.DataFrame(rows)


def get_player_game_log_for_date(player_id: int, season: int, target_date: str, group: str = "hitting") -> dict:
    logs = get_json(
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats",
        params={"stats": "gameLog", "group": group, "season": season, "gameType": "R"},
    )
    stats = logs.get("stats") or []
    if not stats:
        return {}
    for s in stats[0].get("splits", []) or []:
        if s.get("date") == target_date:
            return s.get("stat") or {}
    return {}


def get_player_id_by_name_team(player_name: str, team_name: str, season: int) -> int | None:
    try:
        teams = get_json("https://statsapi.mlb.com/api/v1/teams", params={"sportId": 1}).get("teams", []) or []
        team_lookup = {t.get("name"): t.get("id") for t in teams if t.get("name") and t.get("id")}
        team_id = team_lookup.get(team_name)
        if not team_id:
            return None
        roster = get_team_roster(int(team_id), season)
        target = normalize_name(player_name)
        for pid, meta in roster.items():
            if normalize_name(meta.get("playerName")) == target:
                return int(pid)
    except Exception:
        return None
    return None


def parse_line_from_text(text_val):
    txt = str(text_val or "")
    m = re.search(r"(?:up to|at)\s+(\d+(?:\.\d+)?)", txt)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    return None


def grade_pending_history_rows(current_target_date: str, season: int) -> dict:
    history_dir = OUTPUT_DIR / "history"
    csv_path = history_dir / "pick_history.csv"
    jsonl_results = history_dir / "results_history.jsonl"
    csv_results = history_dir / "results_history.csv"
    latest_results = history_dir / "results_history_latest.json"
    perf_latest = history_dir / "performance_summary_latest.json"

    if not csv_path.exists():
        latest_payload = {"graded_rows": 0, "message": "No pick history found", "rows": []}
        latest_results.write_text(json.dumps(latest_payload, indent=2), encoding="utf-8")
        perf_latest.write_text(json.dumps({"overall": {}, "by_bet_type": [], "by_confidence": [], "recent_results": []}, indent=2), encoding="utf-8")
        return {"graded_rows": 0, "latest_results": latest_results, "performance": perf_latest}

    hist = pd.read_csv(csv_path)
    # Clean up any duplicate official picks already stored from earlier versions.
    hist_dedupe_cols = [c for c in ["target_date", "history_type", "bet_type", "pick", "team", "opponent"] if c in hist.columns]
    if hist_dedupe_cols:
        hist = hist.drop_duplicates(subset=hist_dedupe_cols, keep="last")
        hist.to_csv(csv_path, index=False)
    if hist.empty:
        latest_payload = {"graded_rows": 0, "message": "Pick history empty", "rows": []}
        latest_results.write_text(json.dumps(latest_payload, indent=2), encoding="utf-8")
        perf_latest.write_text(json.dumps({"overall": {}, "by_bet_type": [], "by_confidence": [], "recent_results": []}, indent=2), encoding="utf-8")
        return {"graded_rows": 0, "latest_results": latest_results, "performance": perf_latest}

    if "result_status" not in hist.columns:
        hist["result_status"] = "pending"
    if "result_detail" not in hist.columns:
        hist["result_detail"] = None
    if "actual_value" not in hist.columns:
        hist["actual_value"] = None
    if "graded_at_et" not in hist.columns:
        hist["graded_at_et"] = None

    # Force flexible dtypes for grading output columns so string details do not
    # crash when older CSVs were inferred as float-only by pandas.
    hist["result_status"] = hist["result_status"].astype("object")
    hist["result_detail"] = hist["result_detail"].astype("object")
    hist["actual_value"] = hist["actual_value"].astype("object")
    hist["graded_at_et"] = hist["graded_at_et"].astype("object")

    to_grade = hist[(hist["target_date"].astype(str) <= str(current_target_date)) & (hist["result_status"].fillna("pending") == "pending")].copy()
    graded_rows = []
    if not to_grade.empty:
        schedule_cache = {}
        team_map_cache = {}
        for idx, row in to_grade.iterrows():
            tdate = str(row.get("target_date"))
            if tdate not in schedule_cache:
                schedule_cache[tdate] = get_schedule_results_for_date(tdate)
            sched = schedule_cache[tdate]
            bet_type = str(row.get("bet_type") or "")
            team = row.get("team")
            opponent = row.get("opponent")
            pick = row.get("pick")
            status = "pending"
            detail = None
            actual = None

            game_row = sched[(sched["home_team"] == opponent) & (sched["away_team"] == team)]
            if game_row.empty:
                game_row = sched[((sched["home_team"] == team) & (sched["away_team"] == opponent)) | ((sched["home_team"] == opponent) & (sched["away_team"] == team))]
            game_completed = bool(game_row.iloc[0].get("completed")) if not game_row.empty else False
            game_status = str(game_row.iloc[0].get("status") or "") if not game_row.empty else ""

            try:
                if bet_type == "Moneyline":
                    if not game_row.empty and game_completed:
                        winner = game_row.iloc[0].get("winner_team")
                        actual = winner
                        status = "win" if winner == team else "loss"
                        detail = f"Winner: {winner}"
                    else:
                        detail = f"Pending — game not final ({game_status or 'Not Started'})"
                elif bet_type in ("1+ Hit", "HR"):
                    if not game_completed:
                        detail = f"Pending — game not final ({game_status or 'In Progress'})"
                    else:
                        pid = get_player_id_by_name_team(str(pick), str(team), season)
                        if pid:
                            stat = get_player_game_log_for_date(pid, season, tdate, "hitting")
                            if stat:
                                hits = int(stat.get("hits", 0) or 0)
                                hrs = int(stat.get("homeRuns", 0) or 0)
                                actual = hits if bet_type == "1+ Hit" else hrs
                                status = "win" if (hits > 0 if bet_type == "1+ Hit" else hrs > 0) else "loss"
                                detail = f"Hits: {hits}; HR: {hrs}"
                            else:
                                detail = "Pending — no final player log yet"
                elif bet_type == "K Prop":
                    if not game_completed:
                        detail = f"Pending — game not final ({game_status or 'In Progress'})"
                    else:
                        pid = get_player_id_by_name_team(str(pick), str(team), season)
                        if pid:
                            stat = get_player_game_log_for_date(pid, season, tdate, "pitching")
                            if stat:
                                ks = float(stat.get("strikeOuts", 0) or 0)
                                line = parse_line_from_text(row.get("why_it_made_the_card"))
                                actual = ks
                                if line is not None:
                                    status = "win" if ks > line else "loss"
                                    detail = f"Ks: {ks}; line: {line}"
                                else:
                                    detail = f"Ks: {ks}"
                            else:
                                detail = "Pending — no final pitcher log yet"
            except Exception as e:
                detail = f"Grade error: {e}"

            if status in ("win", "loss"):
                hist.at[idx, "result_status"] = status
                hist.at[idx, "result_detail"] = detail
                hist.at[idx, "actual_value"] = actual
                hist.at[idx, "graded_at_et"] = dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M:%S %p ET")
                graded_rows.append({k: _clean_value(v) for k, v in hist.loc[idx].to_dict().items()})

        hist.to_csv(csv_path, index=False)
        append_jsonl_rows(jsonl_results, graded_rows)
        if csv_results.exists():
            old = pd.read_csv(csv_results)
            combined = pd.concat([old, pd.DataFrame(graded_rows)], ignore_index=True) if graded_rows else old
        else:
            combined = pd.DataFrame(graded_rows)
        if not combined.empty:
            # Dedupe graded results by official-pick identity, not by run_id.
            dedupe_cols = [c for c in ["target_date", "history_type", "bet_type", "pick", "team", "opponent"] if c in combined.columns]
            if dedupe_cols:
                combined = combined.drop_duplicates(subset=dedupe_cols, keep="last")
            combined.to_csv(csv_results, index=False)
    else:
        combined = pd.read_csv(csv_results) if csv_results.exists() else pd.DataFrame()

    latest_payload = {
        "graded_rows": len(graded_rows),
        "graded_for_run_date": current_target_date,
        "rows": graded_rows[-50:],
    }
    latest_results.write_text(json.dumps(latest_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {"overall": {}, "by_bet_type": [], "by_confidence": [], "recent_results": []}
    if not combined.empty:
        graded = combined[combined["result_status"].isin(["win", "loss"])].copy()
        if not graded.empty:
            total = len(graded)
            wins = int((graded["result_status"] == "win").sum())
            summary["overall"] = {"graded_picks": total, "wins": wins, "losses": total - wins, "win_rate": round(wins / total, 3)}
            bt = graded.groupby("bet_type")["result_status"].agg([("graded_picks", "count"), ("wins", lambda s: int((s == "win").sum()))]).reset_index()
            bt["losses"] = bt["graded_picks"] - bt["wins"]
            bt["win_rate"] = (bt["wins"] / bt["graded_picks"]).round(3)
            summary["by_bet_type"] = df_to_records(bt)
            if "confidence" in graded.columns:
                cf = graded.groupby("confidence")["result_status"].agg([("graded_picks", "count"), ("wins", lambda s: int((s == "win").sum()))]).reset_index()
                cf["losses"] = cf["graded_picks"] - cf["wins"]
                cf["win_rate"] = (cf["wins"] / cf["graded_picks"]).round(3)
                summary["by_confidence"] = df_to_records(cf)
            recent_cols = [c for c in ["target_date", "bet_type", "pick", "team", "opponent", "confidence", "result_status", "result_detail"] if c in graded.columns]
            recent = graded.sort_values(["target_date", "graded_at_et"], ascending=[False, False])[recent_cols].head(25)
            summary["recent_results"] = df_to_records(recent)
    perf_latest.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"graded_rows": len(graded_rows), "latest_results": latest_results, "performance": perf_latest}

DEFAULT_SEASON = 2026
SLEEP_BETWEEN_CALLS = 0.02

GREEN = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
YELLOW = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
RED = PatternFill(start_color="F8CBAD", end_color="F8CBAD", fill_type="solid")

PARK_FAVORABILITY_MAP = {
    "Athletics": "Neutral", "Cincinnati Reds": "Favorable", "New York Yankees": "Favorable",
    "Los Angeles Dodgers": "Favorable", "Los Angeles Angels": "Favorable", "Atlanta Braves": "Favorable",
    "Texas Rangers": "Favorable", "Philadelphia Phillies": "Favorable", "New York Mets": "Favorable",
    "Minnesota Twins": "Favorable", "Chicago Cubs": "Neutral", "Seattle Mariners": "Unfavorable",
    "Kansas City Royals": "Unfavorable", "Cleveland Guardians": "Unfavorable", "Detroit Tigers": "Unfavorable",
    "Tampa Bay Rays": "Unfavorable", "Oakland Athletics": "Unfavorable", "Baltimore Orioles": "Unfavorable",
    "San Francisco Giants": "Unfavorable", "Milwaukee Brewers": "Unfavorable", "Miami Marlins": "Neutral",
    "Houston Astros": "Neutral", "Toronto Blue Jays": "Neutral", "Boston Red Sox": "Neutral",
    "Washington Nationals": "Neutral", "Chicago White Sox": "Neutral", "San Diego Padres": "Neutral",
    "Pittsburgh Pirates": "Neutral", "Arizona Diamondbacks": "Neutral", "St. Louis Cardinals": "Neutral",
    "Colorado Rockies": "Favorable",
}

TEAM_VOLATILITY_MAP = {
    "Seattle Mariners": 1.25,
    "Minnesota Twins": 1.10,
    "Tampa Bay Rays": 1.10,
    "Cincinnati Reds": 1.08,
    "New York Yankees": 1.05,
}

PUBLIC_BIAS_MAP = {
    "New York Yankees": 1.15,
    "Los Angeles Dodgers": 1.12,
    "New York Mets": 1.06,
    "Atlanta Braves": 1.05,
}

MAX_REFINED_PICKS_PER_TEAM = 2
BULLPEN_STRONG_ERA = 3.4
BULLPEN_WEAK_ERA = 4.25
BULLPEN_STRONG_WHIP = 1.20
BULLPEN_WEAK_WHIP = 1.35
TEAM_K_LOW = 0.195
TEAM_K_HIGH = 0.235

def print_step(msg: str) -> None:
    print(msg, flush=True)

def get_json(url: str, params=None):
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def nz(x, fallback=0.0):
    return fallback if x is None or pd.isna(x) else x

def pct(h, ab):
    try:
        h = float(h)
        ab = float(ab)
        if ab <= 0:
            return None
        return round(100.0 * h / ab, 1)
    except Exception:
        return None

def normalize_name(v: str) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower().replace("’", "'").replace("`", "'")
    return re.sub(r"[^a-z0-9]+", "", s)


def format_game_time_et(game_date_str: str | None) -> str | None:
    if not game_date_str:
        return None
    try:
        s = str(game_date_str).replace("Z", "+00:00")
        dt_utc = dt.datetime.fromisoformat(s)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=dt.timezone.utc)
        dt_et = dt_utc.astimezone(ZoneInfo("America/New_York"))
        try:
            return dt_et.strftime("%-I:%M %p ET")
        except Exception:
            return dt_et.strftime("%I:%M %p ET").lstrip("0")
    except Exception:
        return None


def game_has_started(game_datetime_utc: str | None, now_et: dt.datetime | None = None, buffer_minutes: int = 5) -> bool:
    """Return True when first pitch time has arrived (with a small safety buffer)."""
    if not game_datetime_utc:
        return False
    try:
        s = str(game_datetime_utc).replace("Z", "+00:00")
        game_dt = dt.datetime.fromisoformat(s)
        if game_dt.tzinfo is None:
            game_dt = game_dt.replace(tzinfo=dt.timezone.utc)
        game_et = game_dt.astimezone(ZoneInfo("America/New_York"))
        now_et = now_et or dt.datetime.now(ZoneInfo("America/New_York"))
        return now_et >= (game_et - dt.timedelta(minutes=buffer_minutes))
    except Exception:
        return False

def filter_pregame_schedule_rows(schedule_rows: pd.DataFrame, now_et: dt.datetime | None = None, buffer_minutes: int = 5) -> pd.DataFrame:
    """Only games that have not started yet are eligible for NEW picks."""
    if schedule_rows is None or schedule_rows.empty:
        return schedule_rows.copy()
    now_et = now_et or dt.datetime.now(ZoneInfo("America/New_York"))
    out = schedule_rows.copy()
    out["game_started_flag"] = out["game_datetime_utc"].apply(lambda x: game_has_started(x, now_et, buffer_minutes))
    return out[out["game_started_flag"] == False].copy()

def park_value(s: str) -> float:
    return {"Favorable": 10.0, "Neutral": 5.0, "Unfavorable": 0.0}.get(s or "Neutral", 5.0)

def overdue_value(status: str) -> float:
    if not status:
        return 0.0
    s = str(status).lower()
    if s.startswith("overdue"):
        m = re.search(r"\+(\d+)", status)
        return 8.0 + (float(m.group(1)) * 0.5 if m else 0.0)
    if s.startswith("slightly overdue"):
        m = re.search(r"\+(\d+)", status)
        return 5.0 + (float(m.group(1)) * 0.25 if m else 0.0)
    return 0.0

def innings_to_float(ip):
    if ip in (None, ""):
        return None
    if isinstance(ip, (int, float)):
        return float(ip)
    s = str(ip).strip()
    if "." not in s:
        try:
            return float(s)
        except Exception:
            return None
    whole, frac = s.split(".", 1)
    try:
        whole_i = int(whole)
        frac_i = int(frac)
    except Exception:
        try:
            return float(s)
        except Exception:
            return None
    return whole_i + {0: 0.0, 1: 1 / 3, 2: 2 / 3}.get(frac_i, 0.0)


def safe_int(v):
    try:
        if v is None or pd.isna(v):
            return None
        return int(float(v))
    except Exception:
        return None

def safe_div(n, d, fallback=0.0):

    try:
        n = float(n)
        d = float(d)
        if d == 0:
            return fallback
        return n / d
    except Exception:
        return fallback

def get_team_volatility(team_name: str) -> float:
    return float(TEAM_VOLATILITY_MAP.get(team_name, 1.0))

def get_public_bias(team_name: str) -> float:
    return float(PUBLIC_BIAS_MAP.get(team_name, 1.0))

def get_volatility_penalty(team_name: str, mode: str) -> float:
    vol = get_team_volatility(team_name)
    if vol <= 1.0:
        return 0.0
    if mode == "hit":
        return round((vol - 1.0) * 3.0, 3)
    if mode == "ml":
        return round((vol - 1.0) * 2.0, 3)
    return round((vol - 1.0) * 1.5, 3)

def get_public_bias_penalty(team_name: str, mode: str) -> float:
    pb = get_public_bias(team_name)
    if pb <= 1.0:
        return 0.0
    if mode == "ml":
        return round((pb - 1.0) * 2.0, 3)
    if mode == "hr":
        return round((pb - 1.0) * 1.25, 3)
    return round((pb - 1.0), 3)

def get_pitcher_game_logs(player_id: int, season: int) -> pd.DataFrame:
    data = get_json(
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats",
        params={"stats": "gameLog", "group": "pitching", "season": season, "gameType": "R"},
    )
    stats = data.get("stats") or []
    if not stats:
        return pd.DataFrame(columns=["date", "inningsPitched", "strikeOuts", "pitchesThrown", "battersFaced", "earnedRuns", "hitsAllowed", "walks"])
    rows = []
    for s in stats[0].get("splits", []) or []:
        stat = s.get("stat", {})
        rows.append({
            "date": pd.to_datetime(s.get("date")).normalize() if s.get("date") else pd.NaT,
            "inningsPitched": innings_to_float(stat.get("inningsPitched")),
            "strikeOuts": float(stat.get("strikeOuts", 0) or 0),
            "pitchesThrown": float(stat.get("numberOfPitches", 0) or 0),
            "battersFaced": float(stat.get("battersFaced", 0) or 0),
            "earnedRuns": float(stat.get("earnedRuns", 0) or 0),
            "hitsAllowed": float(stat.get("hits", 0) or 0),
            "walks": float(stat.get("baseOnBalls", 0) or 0),
        })
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

def summarize_recent_pitcher_form(logs: pd.DataFrame) -> dict:
    if logs is None or logs.empty:
        return {
            "last2_ip_avg": None, "last3_ip_avg": None, "last2_k_avg": None, "last3_k_avg": None,
            "last2_pitch_avg": None, "last_start_ip": None, "last_start_k": None, "last_start_pitch_count": None,
            "last2_under5_count": None, "short_leash_flag": "Unknown", "recent_form_score": 0.0,
        }
    last2 = logs.tail(2).copy()
    last3 = logs.tail(3).copy()
    last2_ip_avg = round(last2["inningsPitched"].dropna().mean(), 3) if not last2.empty else None
    last3_ip_avg = round(last3["inningsPitched"].dropna().mean(), 3) if not last3.empty else None
    last2_k_avg = round(last2["strikeOuts"].dropna().mean(), 3) if not last2.empty else None
    last3_k_avg = round(last3["strikeOuts"].dropna().mean(), 3) if not last3.empty else None
    last2_pitch_avg = round(last2["pitchesThrown"].dropna().mean(), 3) if not last2.empty else None
    last_start = logs.tail(1).iloc[0]
    under5 = int((last2["inningsPitched"].fillna(0) < 5).sum()) if not last2.empty else None
    short_flag = "No"
    if len(last2) < 2:
        short_flag = "Unknown"
    elif under5 >= 2:
        short_flag = "Yes - last 2 starts under 5 IP"
    elif nz(last2_ip_avg) < 5:
        short_flag = "Yes - recent IP under 5"
    elif nz(last2_pitch_avg) and nz(last2_pitch_avg) < 85:
        short_flag = "Yes - pitch count risk"
    recent_form_score = round((nz(last2_ip_avg) * 1.4) + (nz(last2_k_avg) * 1.1) + (nz(last2_pitch_avg) * 0.03) - (under5 or 0) * 1.5, 3)
    return {
        "last2_ip_avg": last2_ip_avg,
        "last3_ip_avg": last3_ip_avg,
        "last2_k_avg": last2_k_avg,
        "last3_k_avg": last3_k_avg,
        "last2_pitch_avg": last2_pitch_avg,
        "last_start_ip": last_start.get("inningsPitched"),
        "last_start_k": last_start.get("strikeOuts"),
        "last_start_pitch_count": last_start.get("pitchesThrown"),
        "last2_under5_count": under5,
        "short_leash_flag": short_flag,
        "recent_form_score": recent_form_score,
    }

def apply_team_pick_caps(df: pd.DataFrame, max_per_team: int = MAX_REFINED_PICKS_PER_TEAM) -> pd.DataFrame:
    if df is None or df.empty or "teamName" not in df.columns:
        return df
    frames = []
    for _, grp in df.groupby("teamName", sort=False):
        frames.append(grp.head(max_per_team))
    if not frames:
        return df.iloc[0:0].copy()
    return pd.concat(frames, ignore_index=True)


def classify_team_k_tendency(k_rate: float) -> str:
    kr = nz(k_rate, None)
    if kr is None:
        return "Unknown"
    if kr >= TEAM_K_HIGH:
        return "High K"
    if kr <= TEAM_K_LOW:
        return "Low K"
    return "Neutral"


def classify_bullpen_grade(era: float, whip: float) -> str:
    e = nz(era, None)
    w = nz(whip, None)
    if e is None and w is None:
        return "Unknown"
    if (e is not None and e <= BULLPEN_STRONG_ERA) and (w is None or w <= BULLPEN_STRONG_WHIP):
        return "Strong"
    if (e is not None and e >= BULLPEN_WEAK_ERA) or (w is not None and w >= BULLPEN_WEAK_WHIP):
        return "Weak"
    return "Neutral"


def bullpen_hitter_adjustment(grade: str, mode: str = "hit") -> float:
    g = str(grade or "Unknown")
    if g == "Weak":
        return 0.35 if mode == "hit" else 0.20
    if g == "Strong":
        return -0.25 if mode == "hit" else -0.15
    return 0.0


def bullpen_pitcher_adjustment(grade: str) -> float:
    g = str(grade or "Unknown")
    if g == "Strong":
        return 0.35
    if g == "Weak":
        return -0.35
    return 0.0


def k_matchup_bonus_from_rate(k_rate: float) -> float:
    kr = nz(k_rate, None)
    if kr is None:
        return 0.0
    if kr >= 0.245:
        return 1.1
    if kr >= 0.235:
        return 0.7
    if kr >= 0.225:
        return 0.35
    if kr <= 0.185:
        return -0.7
    if kr <= 0.195:
        return -0.35
    return 0.0


def get_team_hitting_context(team_id: int, season: int) -> dict:
    try:
        data = get_json(
            "https://statsapi.mlb.com/api/v1/stats",
            params={
                "stats": "season",
                "group": "hitting",
                "season": season,
                "gameType": "R",
                "teamId": team_id,
            },
        )
        splits = data.get("stats", [{}])[0].get("splits", []) or []
        if not splits:
            return {}
        stat = splits[0].get("stat") or {}
        games = float(stat.get("gamesPlayed", 0) or 0)
        strikeouts = float(stat.get("strikeOuts", 0) or 0)
        at_bats = float(stat.get("atBats", 0) or 0)
        walks = float(stat.get("baseOnBalls", 0) or 0)
        hbp = float(stat.get("hitByPitch", 0) or 0)
        sac_flies = float(stat.get("sacFlies", 0) or 0)
        pa = at_bats + walks + hbp + sac_flies
        k_rate = round(safe_div(strikeouts, pa, None), 4) if pa else None
        return {
            "team_k_rate": k_rate,
            "team_k_per_game": round(safe_div(strikeouts, games, None), 3) if games else None,
            "team_pa": pa,
            "team_k_tendency": classify_team_k_tendency(k_rate),
        }
    except Exception:
        return {}


def _extract_pitching_stat_block(team_id: int, season: int, sit_codes: str | None = None) -> dict:
    params = {
        "stats": "season",
        "group": "pitching",
        "season": season,
        "gameType": "R",
        "teamId": team_id,
    }
    if sit_codes:
        params["sitCodes"] = sit_codes
    data = get_json("https://statsapi.mlb.com/api/v1/stats", params=params)
    stats = data.get("stats") or []
    splits = stats[0].get("splits", []) if stats else []
    if not splits:
        return {}
    return splits[0].get("stat") or {}


def get_team_pitching_context(team_id: int, season: int) -> dict:
    total_stat = {}
    relief_stat = {}
    try:
        total_stat = _extract_pitching_stat_block(team_id, season)
    except Exception:
        total_stat = {}
    try:
        relief_stat = _extract_pitching_stat_block(team_id, season, sit_codes="rp")
    except Exception:
        relief_stat = {}
    stat = relief_stat or total_stat
    if not stat:
        return {}
    bullpen_era = float(stat.get("era", 0) or 0) if stat.get("era") not in (None, "") else None
    bullpen_whip = float(stat.get("whip", 0) or 0) if stat.get("whip") not in (None, "") else None
    return {
        "bullpen_era": bullpen_era,
        "bullpen_whip": bullpen_whip,
        "bullpen_grade": classify_bullpen_grade(bullpen_era, bullpen_whip),
        "bullpen_source": "relief_split" if relief_stat else "team_total_fallback",
        "team_pitching_era": float(total_stat.get("era", 0) or 0) if total_stat.get("era") not in (None, "") else bullpen_era,
        "team_pitching_whip": float(total_stat.get("whip", 0) or 0) if total_stat.get("whip") not in (None, "") else bullpen_whip,
    }


def build_team_context_df(schedule_rows: pd.DataFrame, season: int) -> pd.DataFrame:
    team_map = get_team_map(schedule_rows)
    rows = []
    total = max(len(team_map), 1)
    for i, (team_name, team_id) in enumerate(team_map.items(), 1):
        print_step(f"📊 Team context {i}/{total}: {team_name}")
        hit_ctx = get_team_hitting_context(team_id, season)
        pitch_ctx = get_team_pitching_context(team_id, season)
        rows.append({"teamName": team_name, **hit_ctx, **pitch_ctx})
        time.sleep(SLEEP_BETWEEN_CALLS)
    return pd.DataFrame(rows)


def enrich_player_rows_with_team_context(player_rows: pd.DataFrame, pitcher_metrics: pd.DataFrame, team_context_df: pd.DataFrame) -> pd.DataFrame:
    if player_rows is None or player_rows.empty:
        return player_rows
    rows = player_rows.copy()
    if pitcher_metrics is not None and not pitcher_metrics.empty:
        opp_lookup = pitcher_metrics[["teamName", "opponentTeam"]].drop_duplicates().rename(columns={"teamName": "opponentTeam", "opponentTeam": "teamName"})
        rows = rows.merge(opp_lookup, on="teamName", how="left")
    if team_context_df is not None and not team_context_df.empty:
        offense_ctx = team_context_df[["teamName", "team_k_rate", "team_k_per_game", "team_k_tendency"]].drop_duplicates()
        opp_ctx = team_context_df[["teamName", "bullpen_era", "bullpen_whip", "bullpen_grade", "bullpen_source", "team_pitching_era", "team_pitching_whip"]].drop_duplicates().rename(columns={
            "teamName": "opponentTeam",
            "bullpen_era": "opp_bullpen_era",
            "bullpen_whip": "opp_bullpen_whip",
            "bullpen_grade": "opp_bullpen_grade",
            "bullpen_source": "opp_bullpen_source",
            "team_pitching_era": "opp_team_pitching_era",
            "team_pitching_whip": "opp_team_pitching_whip",
        })
        rows = rows.merge(offense_ctx, on="teamName", how="left")
        rows = rows.merge(opp_ctx, on="opponentTeam", how="left")
    rows["k_tendency_hit_penalty"] = rows["team_k_rate"].apply(lambda x: round(max(0.0, nz(x) - 0.215) * 8.0, 3) if pd.notna(x) else 0.0)
    rows["bullpen_hit_adjustment"] = rows["opp_bullpen_grade"].apply(lambda x: bullpen_hitter_adjustment(x, "hit"))
    rows["bullpen_hr_adjustment"] = rows["opp_bullpen_grade"].apply(lambda x: bullpen_hitter_adjustment(x, "hr"))
    rows["Hit_score"] = (rows["Hit_score"].fillna(0) - rows["k_tendency_hit_penalty"] + rows["bullpen_hit_adjustment"]).round(3)
    rows["HR_score"] = (rows["HR_score"].fillna(0) + rows["bullpen_hr_adjustment"]).round(3)
    return rows


def enrich_pitcher_metrics_with_team_context(pitcher_metrics: pd.DataFrame, team_context_df: pd.DataFrame) -> pd.DataFrame:
    if pitcher_metrics is None or pitcher_metrics.empty:
        return pitcher_metrics
    rows = pitcher_metrics.copy()
    if team_context_df is not None and not team_context_df.empty:
        opp_hit_ctx = team_context_df[["teamName", "team_k_rate", "team_k_tendency"]].drop_duplicates().rename(columns={
            "teamName": "opponentTeam",
            "team_k_rate": "opp_team_k_rate",
            "team_k_tendency": "opp_team_k_tendency",
        })
        own_pen_ctx = team_context_df[["teamName", "bullpen_era", "bullpen_whip", "bullpen_grade", "bullpen_source"]].drop_duplicates().rename(columns={
            "bullpen_era": "own_bullpen_era",
            "bullpen_whip": "own_bullpen_whip",
            "bullpen_grade": "own_bullpen_grade",
            "bullpen_source": "own_bullpen_source",
        })
        rows = rows.merge(opp_hit_ctx, on="opponentTeam", how="left")
        rows = rows.merge(own_pen_ctx, on="teamName", how="left")
    rows["opp_k_matchup_bonus"] = rows["opp_team_k_rate"].apply(k_matchup_bonus_from_rate)
    rows["bullpen_support_adjustment"] = rows["own_bullpen_grade"].apply(bullpen_pitcher_adjustment)
    rows["pitcher_score_adj"] = (rows["pitcher_score_adj"].fillna(0) + rows["opp_k_matchup_bonus"] + rows["bullpen_support_adjustment"]).round(3)
    def _upgrade_pick_type(row):
        current = str(row.get("pick_type") or "Neutral")
        if str(row.get("short_leash_flag") or "").startswith("Yes"):
            return "Short Leash Risk"
        bonus = nz(row.get("opp_k_matchup_bonus"))
        score = nz(row.get("pitcher_score_adj"))
        if current == "Neutral" and bonus >= 0.7 and score >= 5.5:
            return "K Upside"
        if current == "K Upside" and bonus >= 0.7 and score >= 6.5:
            return "Strong SP"
        if current == "Strong SP" and bonus <= -0.35:
            return "Neutral"
        return current
    rows["pick_type"] = rows.apply(_upgrade_pick_type, axis=1)
    return rows

def get_schedule_rows(target_date: str) -> pd.DataFrame:
    print_step(f"📅 Pulling schedule for {target_date} ...")
    data = get_json(
        "https://statsapi.mlb.com/api/v1/schedule",
        params={"sportId": 1, "date": target_date, "hydrate": "team,probablePitcher,venue"},
    )
    rows = []
    for d in data.get("dates", []):
        for g in d.get("games", []):
            teams = g.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            game_datetime_utc = g.get("gameDate")
            rows.append({
                "game_date": target_date,
                "game_datetime_utc": game_datetime_utc,
                "game_time_et": format_game_time_et(game_datetime_utc),
                "away_team": (away.get("team") or {}).get("name"),
                "home_team": (home.get("team") or {}).get("name"),
                "venue": (g.get("venue") or {}).get("name"),
                "away_probable_pitcher": (away.get("probablePitcher") or {}).get("fullName"),
                "away_probable_pitcher_id": (away.get("probablePitcher") or {}).get("id"),
                "home_probable_pitcher": (home.get("probablePitcher") or {}).get("fullName"),
                "home_probable_pitcher_id": (home.get("probablePitcher") or {}).get("id"),
                "gamePk": g.get("gamePk"),
            })
    return pd.DataFrame(rows)

def get_pitcher_hand(pid):
    if not pid:
        return None
    try:
        p = get_json(f"https://statsapi.mlb.com/api/v1/people/{pid}")
        ppl = p.get("people", [])
        if ppl:
            ph = ppl[0].get("pitchHand") or {}
            code = (ph.get("code") or ph.get("description") or "").upper()
            if code.startswith("R"):
                return "R"
            if code.startswith("L"):
                return "L"
    except Exception:
        return None
    return None

def get_schedule_game_context(target_date: str):
    schedule_rows = get_schedule_rows(target_date)
    ctx = {}
    for _, g in schedule_rows.iterrows():
        home_team = g.get("home_team")
        away_team = g.get("away_team")
        pf = PARK_FAVORABILITY_MAP.get(home_team, "Neutral")
        ctx[home_team] = {
            "opp_pitcher_name": g.get("away_probable_pitcher"),
            "opp_pitcher_id": g.get("away_probable_pitcher_id"),
            "opp_pitcher_hand": get_pitcher_hand(g.get("away_probable_pitcher_id")),
            "game_park_team": home_team,
            "game_park_name": g.get("venue"),
            "park_favorability": pf,
        }
        ctx[away_team] = {
            "opp_pitcher_name": g.get("home_probable_pitcher"),
            "opp_pitcher_id": g.get("home_probable_pitcher_id"),
            "opp_pitcher_hand": get_pitcher_hand(g.get("home_probable_pitcher_id")),
            "game_park_team": home_team,
            "game_park_name": g.get("venue"),
            "park_favorability": pf,
        }
    return ctx, schedule_rows

def get_team_roster(team_id: int, season: int):
    data = get_json(
        f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster",
        params={"rosterType": "fullSeason", "season": season},
    )
    roster = data.get("roster", []) or []
    out = {}
    for r in roster:
        person = r.get("person") or {}
        pos = (r.get("position") or {}).get("abbreviation", "")
        out[int(person.get("id"))] = {"playerName": person.get("fullName"), "pos": pos}
    return out

def get_team_map(schedule_rows: pd.DataFrame):
    data = get_json("https://statsapi.mlb.com/api/v1/teams", params={"sportId": 1})
    teams = data.get("teams", []) or []
    team_lookup = {t.get("name"): int(t.get("id")) for t in teams if t.get("name") and t.get("id")}
    scheduled = set(schedule_rows["home_team"].dropna().tolist() + schedule_rows["away_team"].dropna().tolist())
    return {name: team_lookup[name] for name in scheduled if name in team_lookup}

def get_team_hitting_pool(team_id: int, season: int):
    data = get_json(
        "https://statsapi.mlb.com/api/v1/stats",
        params={
            "stats": "season",
            "group": "hitting",
            "season": season,
            "gameType": "R",
            "teamId": team_id,
        },
    )
    splits = data.get("stats", [{}])[0].get("splits", []) or []
    rows = []
    for s in splits:
        player = s.get("player", {})
        stat = s.get("stat", {})
        rows.append({
            "playerId": int(player.get("id")),
            "playerName": player.get("fullName"),
            "homeRuns": int(stat.get("homeRuns", 0)),
            "hits": int(stat.get("hits", 0)),
            "gamesPlayed": int(stat.get("gamesPlayed", 0)),
            "atBats": int(stat.get("atBats", 0)),
        })
    return pd.DataFrame(rows)

def build_scheduled_player_pool(schedule_rows: pd.DataFrame, season: int):
    print_step("📡 Pulling all scheduled-team hitters ...")
    team_map = get_team_map(schedule_rows)
    frames = []
    for i, (team_name, team_id) in enumerate(team_map.items(), 1):
        print_step(f"🏟️ Team {i}/{len(team_map)}: {team_name}")
        pool = get_team_hitting_pool(team_id, season)
        if not pool.empty:
            pool["teamName"] = team_name
            frames.append(pool)
        time.sleep(SLEEP_BETWEEN_CALLS)
    if not frames:
        return pd.DataFrame(columns=["playerId", "playerName", "homeRuns", "hits", "gamesPlayed", "atBats", "teamName"])
    df = pd.concat(frames, ignore_index=True)
    return df.drop_duplicates(subset=["playerId", "teamName"]).reset_index(drop=True)

def get_player_game_logs(player_id: int, season: int) -> pd.DataFrame:
    data = get_json(
        f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats",
        params={"stats": "gameLog", "group": "hitting", "season": season, "gameType": "R"},
    )
    stats = data.get("stats") or []
    if not stats:
        return pd.DataFrame(columns=["date", "homeRuns", "hits"])
    rows = []
    for s in stats[0].get("splits", []) or []:
        stat = s.get("stat", {})
        rows.append({
            "date": pd.to_datetime(s.get("date")).normalize() if s.get("date") else pd.NaT,
            "homeRuns": int(stat.get("homeRuns", 0)),
            "hits": int(stat.get("hits", 0)),
        })
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

def compute_drought_metrics(df: pd.DataFrame, col: str) -> dict:
    total = len(df)
    if total == 0:
        return {"last_event_date": None, "current_gap": None, "avg_games_between": None, "longest_drought": None}
    idxs = df.index[df[col] > 0].tolist()
    if not idxs:
        return {"last_event_date": None, "current_gap": total, "avg_games_between": None, "longest_drought": total}
    last_idx = idxs[-1]
    current_gap = total - last_idx - 1
    last_event_date = df.loc[last_idx, "date"]
    if len(idxs) == 1:
        longest = max(idxs[0], current_gap)
        return {"last_event_date": last_event_date.date() if pd.notna(last_event_date) else None, "current_gap": current_gap, "avg_games_between": None, "longest_drought": longest}
    gaps = [idxs[i + 1] - idxs[i] - 1 for i in range(len(idxs) - 1)]
    return {"last_event_date": last_event_date.date() if pd.notna(last_event_date) else None, "current_gap": current_gap, "avg_games_between": round(sum(gaps) / len(gaps), 2) if gaps else None, "longest_drought": max(idxs[0], current_gap, max(gaps))}

def determine_status(current_gap, avg_gap):
    if avg_gap is None or current_gap is None:
        return "N/A"
    if current_gap <= avg_gap:
        return "On Pace"
    if current_gap <= 1.5 * avg_gap:
        return f"Slightly Overdue (+{current_gap - int(avg_gap)})"
    return f"Overdue (+{current_gap - int(avg_gap)})"


def average_games_per_event(games_played, event_count):
    gp = nz(games_played, None)
    ec = nz(event_count, None)
    if gp is None or ec is None or ec <= 0:
        return None
    return round(float(gp) / float(ec), 2)

def get_pitcher_season_stats(pid: int, season: int) -> dict:
    if not pid:
        return {}
    try:
        data = get_json(
            f"https://statsapi.mlb.com/api/v1/people/{int(float(pid))}/stats",
            params={"stats": "season", "group": "pitching", "season": season, "gameType": "R"},
        )
        stats = data.get("stats") or []
        splits = stats[0].get("splits", []) if stats else []
        if not splits:
            return {}
        stat = splits[0].get("stat") or {}
        return {
            "inningsPitched": innings_to_float(stat.get("inningsPitched")),
            "strikeOuts": float(stat.get("strikeOuts", 0) or 0),
            "earnedRuns": float(stat.get("earnedRuns", 0) or 0),
            "hitsAllowed": float(stat.get("hits", 0) or 0),
            "baseOnBalls": float(stat.get("baseOnBalls", 0) or 0),
            "gamesStarted": float(stat.get("gamesStarted", 0) or 0),
            "era": float(stat.get("era", 0) or 0) if stat.get("era") not in (None, "") else None,
            "whip": float(stat.get("whip", 0) or 0) if stat.get("whip") not in (None, "") else None,
        }
    except Exception:
        return {}

def compute_pitcher_score(ip, so, er, ha, bb):
    return round((nz(so) * 1.5) + (nz(ip) * 1.2) - (nz(er) * 2.0) - (nz(ha) * 0.8) - (nz(bb) * 1.2), 3)

def classify_pitcher_pick(score_adj, ip, so, er, ha):
    if nz(ip) < 3:
        return "Low Sample"
    if nz(score_adj) >= 6:
        return "Strong SP"
    if nz(so) >= 6 and nz(ip) >= 4:
        return "K Upside"
    if nz(er) >= 3 or nz(ha) >= 6:
        return "Attack With Hitters"
    return "Neutral"

def build_pitcher_metrics(schedule_rows: pd.DataFrame, season: int) -> pd.DataFrame:
    rows = []
    total = max(len(schedule_rows) * 2, 1)
    counter = 0
    for _, g in schedule_rows.iterrows():
        for team, opp, pitcher_name, pitcher_id in [
            (g.get("away_team"), g.get("home_team"), g.get("away_probable_pitcher"), g.get("away_probable_pitcher_id")),
            (g.get("home_team"), g.get("away_team"), g.get("home_probable_pitcher"), g.get("home_probable_pitcher_id")),
        ]:
            counter += 1
            if not team or not opp or not pitcher_name:
                continue
            print_step(f"🎯 Pitcher {counter}/{total}: {pitcher_name} ({team})")
            stat = get_pitcher_season_stats(pitcher_id, season)
            pid = safe_int(pitcher_id)
            logs = get_pitcher_game_logs(pid, season) if pid is not None else pd.DataFrame()
            recent = summarize_recent_pitcher_form(logs)
            ip = stat.get("inningsPitched")
            so = stat.get("strikeOuts")
            er = stat.get("earnedRuns")
            ha = stat.get("hitsAllowed")
            bb = stat.get("baseOnBalls")
            raw_score = compute_pitcher_score(ip, so, er, ha, bb)
            short_leash_penalty = 0.0
            if str(recent.get("short_leash_flag") or "").startswith("Yes"):
                short_leash_penalty = 3.0
            elif str(recent.get("short_leash_flag") or "") == "Unknown":
                short_leash_penalty = 1.0
            score_adj = round(raw_score - short_leash_penalty + nz(recent.get("recent_form_score")) * 0.15, 3)
            pick_type = classify_pitcher_pick(score_adj, ip, so, er, ha)
            if str(recent.get("short_leash_flag") or "").startswith("Yes"):
                pick_type = "Short Leash Risk"
            rows.append({
                "pitcherName": pitcher_name, "teamName": team, "opponentTeam": opp,
                "innings_pitched": ip, "strikeouts": so, "earned_runs": er, "hits_allowed": ha, "walks": bb,
                "games_started": stat.get("gamesStarted"), "era": stat.get("era"), "whip": stat.get("whip"),
                "pitcher_score": raw_score, "pitcher_score_adj": score_adj,
                "recent_form_score": recent.get("recent_form_score"),
                "last2_ip_avg": recent.get("last2_ip_avg"), "last3_ip_avg": recent.get("last3_ip_avg"),
                "last2_k_avg": recent.get("last2_k_avg"), "last3_k_avg": recent.get("last3_k_avg"),
                "last2_pitch_avg": recent.get("last2_pitch_avg"),
                "last_start_ip": recent.get("last_start_ip"), "last_start_k": recent.get("last_start_k"),
                "last_start_pitch_count": recent.get("last_start_pitch_count"),
                "last2_under5_count": recent.get("last2_under5_count"),
                "short_leash_flag": recent.get("short_leash_flag"),
                "sample_flag": "Low Sample" if nz(ip) < 3 else "OK",
                "pick_type": pick_type, "probable_starter_name": pitcher_name, "starter_status": "Confirmed",
            })
            time.sleep(SLEEP_BETWEEN_CALLS)
    cols = ["pitcherName","teamName","opponentTeam","innings_pitched","strikeouts","earned_runs","hits_allowed","walks","games_started","era","whip","pitcher_score","pitcher_score_adj","recent_form_score","last2_ip_avg","last3_ip_avg","last2_k_avg","last3_k_avg","last2_pitch_avg","last_start_ip","last_start_k","last_start_pitch_count","last2_under5_count","short_leash_flag","sample_flag","pick_type","probable_starter_name","starter_status"]
    return pd.DataFrame(rows, columns=cols).sort_values(["pitcher_score_adj","pitcher_score"], ascending=False).reset_index(drop=True)

def get_confirmed_lineups(target_date: str):
    print_step("🧾 Pulling confirmed lineups ...")
    status_map = {}
    slot_map = {}
    try:
        schedule = get_json("https://statsapi.mlb.com/api/v1/schedule", params={"sportId": 1, "date": target_date})
        for d in schedule.get("dates", []):
            for g in d.get("games", []):
                game_pk = g.get("gamePk")
                if not game_pk:
                    continue
                try:
                    box = get_json(f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore")
                except Exception:
                    continue
                for side in ("home", "away"):
                    tblock = ((box.get("teams") or {}).get(side) or {})
                    team_name = ((tblock.get("team") or {}).get("name"))
                    batting_order = tblock.get("battingOrder") or []
                    players = tblock.get("players") or {}
                    if len(batting_order) < 9:
                        continue
                    for pid in batting_order:
                        p = players.get(f"ID{pid}") or {}
                        full_name = ((p.get("person") or {}).get("fullName"))
                        bo = str(p.get("battingOrder") or "").strip()
                        if team_name and full_name and bo:
                            key = (team_name, normalize_name(full_name))
                            status_map[key] = "Confirmed Starter"
                            try:
                                slot_map[key] = int(bo[:3]) // 100
                            except Exception:
                                slot_map[key] = None
    except Exception:
        pass
    return status_map, slot_map

def build_locked_player_pool(all_players: pd.DataFrame, lineup_map: dict, slot_map: dict) -> pd.DataFrame:
    print_step("🔒 Locking players to confirmed lineups ...")
    if all_players.empty:
        return all_players.copy()
    out = all_players.copy()
    out["lineup_status"] = out.apply(lambda r: lineup_map.get((r["teamName"], normalize_name(r["playerName"])), "Unknown"), axis=1)
    out["batting_order_slot"] = out.apply(lambda r: slot_map.get((r["teamName"], normalize_name(r["playerName"])), None), axis=1)
    out["starter_only_flag"] = out["lineup_status"].eq("Confirmed Starter")
    out = out[out["starter_only_flag"] == True].copy()
    out = out[out["batting_order_slot"].notna()].copy()
    return out

def build_hit_hr_rows(pool_df: pd.DataFrame, season: int, sched_ctx: dict) -> pd.DataFrame:
    rows = []
    total = max(len(pool_df), 1)
    for i, (_, row) in enumerate(pool_df.iterrows(), 1):
        print_step(f"👤 Player {i}/{total}: {row['playerName']} ({row['teamName']})")
        logs = get_player_game_logs(int(row["playerId"]), season)
        hr_d = compute_drought_metrics(logs, "homeRuns")
        hit_d = compute_drought_metrics(logs, "hits")

        avg_hr = average_games_per_event(row.get("gamesPlayed"), row.get("homeRuns"))
        avg_hit = average_games_per_event(row.get("gamesPlayed"), row.get("hits"))

        hr_status = determine_status(hr_d["current_gap"], avg_hr)
        hit_status = determine_status(hit_d["current_gap"], avg_hit)

        last10 = logs.tail(10)
        hit_pct_last_10 = round((len(last10[last10["hits"] > 0]) / 10) * 100, 1) if len(last10) == 10 else None
        ctx = sched_ctx.get(row["teamName"], {})
        season_hit_pct = pct(row["hits"], row.get("atBats", 0))
        slot_raw = row.get("batting_order_slot")
        slot = 9 if pd.isna(slot_raw) else int(slot_raw)
        lineup_bonus = max(0, 10 - slot) * 0.12
        team_volatility = get_team_volatility(row["teamName"])
        public_bias = get_public_bias(row["teamName"])
        hit_vol_penalty = get_volatility_penalty(row["teamName"], "hit")
        hr_vol_penalty = get_volatility_penalty(row["teamName"], "hr")
        hr_public_penalty = get_public_bias_penalty(row["teamName"], "hr")
        hr_score_raw = (row["homeRuns"] / max(row["gamesPlayed"], 1) * 10 * 0.40) + (overdue_value(hr_status) * 0.25) + (park_value(ctx.get("park_favorability")) * 0.20) + lineup_bonus
        hit_score_raw = (nz(season_hit_pct) / 10.0 * 0.40) + (nz(hit_pct_last_10) / 10.0 * 0.20) + (park_value(ctx.get("park_favorability")) * 0.05) + lineup_bonus
        hr_score = round(hr_score_raw - hr_vol_penalty - hr_public_penalty, 3)
        hit_score = round(hit_score_raw - hit_vol_penalty, 3)
        rows.append({
            "season": season, "teamName": row["teamName"], "playerName": row["playerName"], "playerId": row["playerId"],
            "homeRuns": row["homeRuns"], "gamesPlayed": row["gamesPlayed"], "totalHits": row["hits"],
            "avg_games_between_hrs": avg_hr, "current_games_without_hr": hr_d["current_gap"],
            "longest_games_without_hr": hr_d["longest_drought"], "last_hr_date": hr_d["last_event_date"],
            "hr_status": hr_status, "avg_games_between_hits": avg_hit,
            "current_games_without_hit": hit_d["current_gap"], "longestHitDrought": hit_d["longest_drought"],
            "hit_status": hit_status, "hit_pct_last_10": hit_pct_last_10, "season_hit_pct": season_hit_pct,
            "auto_pitcher_name": ctx.get("opp_pitcher_name"), "auto_pitcher_hand": ctx.get("opp_pitcher_hand"),
            "park_favorability": ctx.get("park_favorability"), "game_park_team": ctx.get("game_park_team"),
            "game_park_name": ctx.get("game_park_name"),
            "HR_score_raw": round(hr_score_raw, 3), "Hit_score_raw": round(hit_score_raw, 3),
            "HR_score": hr_score, "Hit_score": hit_score,
            "team_volatility": team_volatility, "public_bias": public_bias,
            "volatility_penalty_hit": hit_vol_penalty, "volatility_penalty_hr": hr_vol_penalty, "public_bias_penalty_hr": hr_public_penalty,
            "lineup_status": row.get("lineup_status"), "batting_order_slot": row.get("batting_order_slot"),
            "starter_only_flag": row.get("starter_only_flag"),
        })
        time.sleep(SLEEP_BETWEEN_CALLS)
    return pd.DataFrame(rows)

def build_game_rankings(schedule_rows, hr_rows, hit_rows, pitcher_metrics):
    hr_map = hr_rows.groupby("teamName")["HR_score"].mean().to_dict() if not hr_rows.empty else {}
    hit_map = hit_rows.groupby("teamName")["Hit_score"].mean().to_dict() if not hit_rows.empty else {}
    pmap = {r["teamName"]: r for _, r in pitcher_metrics.iterrows()} if not pitcher_metrics.empty else {}
    rows = []
    for _, g in schedule_rows.iterrows():
        for team, opp in [(g.get("away_team"), g.get("home_team")), (g.get("home_team"), g.get("away_team"))]:
            offense_hr = round(nz(hr_map.get(team)), 3)
            offense_hit = round(nz(hit_map.get(team)), 3)
            offense_score = round(offense_hr * 0.45 + offense_hit * 0.55, 3)
            p_self = pmap.get(team, {})
            p_opp = pmap.get(opp, {})
            vol_penalty_ml = get_volatility_penalty(team, "ml")
            public_penalty_ml = get_public_bias_penalty(team, "ml")
            short_leash_adj = 0.0
            if str(p_self.get("short_leash_flag") or "").startswith("Yes"):
                short_leash_adj = -2.0
            elif str(p_self.get("short_leash_flag") or "") == "Unknown":
                short_leash_adj = -0.5
            team_score = round((offense_score * 0.55) + (nz(p_self.get("pitcher_score_adj")) * 0.45) - vol_penalty_ml - public_penalty_ml + short_leash_adj, 3)
            rows.append({
                "game": f"{g.get('away_team')} @ {g.get('home_team')}",
                "teamName": team, "opponentTeam": opp, "venue": g.get("venue"),
                "game_time_et": g.get("game_time_et"), "game_datetime_utc": g.get("game_datetime_utc"),
                "offense_hr_score": offense_hr, "offense_hit_score": offense_hit, "offense_score": offense_score,
                "team_volatility": get_team_volatility(team), "public_bias": get_public_bias(team),
                "volatility_penalty_ml": vol_penalty_ml, "public_penalty_ml": public_penalty_ml,
                "pitcherName": p_self.get("pitcherName"), "pitcher_score": p_self.get("pitcher_score"),
                "pitcher_score_adj": p_self.get("pitcher_score_adj"), "pitcher_pick_type": p_self.get("pick_type"),
                "short_leash_flag": p_self.get("short_leash_flag"),
                "opponent_pitcher": p_opp.get("pitcherName"), "opponent_pitcher_score": p_opp.get("pitcher_score"),
                "opponent_pitcher_score_adj": p_opp.get("pitcher_score_adj"), "opponent_pitcher_pick_type": p_opp.get("pick_type"),
                "team_score": team_score,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    gm = df.groupby("game")["team_score"].transform("mean")
    df["edge_vs_opponent"] = (df["team_score"] - (gm * 2 - df["team_score"])).round(3)
    def classify(row):
        edge = nz(row.get("edge_vs_opponent"))
        offense = nz(row.get("offense_score"))
        opp_pt = str(row.get("opponent_pitcher_pick_type") or "")
        own_pt = str(row.get("pitcher_pick_type") or "")
        own_short = str(row.get("short_leash_flag") or "")
        rating = "Strong" if edge >= 3 else "Lean" if edge >= 2.5 else "Fade" if edge <= -3 else "Slight Fade" if edge <= -2.5 else "Neutral"
        if own_short.startswith("Yes"):
            play = "Avoid"
        elif edge >= 2.5 and opp_pt == "Attack With Hitters":
            play = "Stack Spot"
        elif edge >= 2.5 and own_pt in ("Strong SP", "K Upside") and offense >= 2.2:
            play = "Moneyline Lean"
        elif edge <= -2.5:
            play = "Avoid"
        else:
            play = "Pass / Small Edge"
        return pd.Series([rating, play])
    df[["win_rating", "recommended_play"]] = df.apply(classify, axis=1)
    return df.sort_values(["game", "team_score"], ascending=[True, False]).reset_index(drop=True)

def build_refined_picks(player_rows, pitcher_metrics, game_rankings):
    cols = ["category","bet_type","playerName","teamName","game","opponent_pitcher","opponent_pitcher_team","opponent_pitcher_pick_type","opponent_pitcher_sample","lineup_status","batting_order_slot","starter_only_flag","HR_score","Hit_score","park_favorability","stack_tag","reason"]
    if player_rows.empty or pitcher_metrics.empty:
        return pd.DataFrame([{"category":"Info","bet_type":"No Plays","reason":"No refined picks met today’s filters"}], columns=cols)

    pm = pitcher_metrics[["teamName","opponentTeam","pitcherName","pick_type","sample_flag","short_leash_flag"]].rename(columns={
        "teamName":"opponent_pitcher_team","opponentTeam":"teamName","pitcherName":"opponent_pitcher","pick_type":"opponent_pitcher_pick_type","sample_flag":"opponent_pitcher_sample"
    })
    ctx = game_rankings[["teamName","opponentTeam","game","offense_score","edge_vs_opponent","recommended_play"]].drop_duplicates()
    rows = player_rows.merge(pm, on="teamName", how="left")
    merge_keys = ["teamName", "opponentTeam"] if "opponentTeam" in rows.columns and "opponentTeam" in ctx.columns else ["teamName"]
    rows = rows.merge(ctx, on=merge_keys, how="left")

    picks = []
    hit_pool = rows[
        (rows["Hit_score"].notna()) &
        (rows["opponent_pitcher_pick_type"].fillna("Neutral") != "Strong SP") &
        (rows["starter_only_flag"] == True) &
        ((rows["offense_score"].fillna(0) >= 2.5) | (rows["edge_vs_opponent"].fillna(0) > 0))
    ].copy().sort_values(["Hit_score","batting_order_slot"], ascending=[False, True])
    hit_pool = apply_team_pick_caps(hit_pool, MAX_REFINED_PICKS_PER_TEAM)
    for _, r in hit_pool.head(5).iterrows():
        picks.append({
            "category":"Hit Pick","bet_type":"1+ Hit","playerName":r["playerName"],"teamName":r["teamName"],"game":r.get("game"),
            "opponent_pitcher":r.get("opponent_pitcher"),"opponent_pitcher_team":r.get("opponent_pitcher_team"),
            "opponent_pitcher_pick_type":r.get("opponent_pitcher_pick_type"),"opponent_pitcher_sample":r.get("opponent_pitcher_sample"),
            "lineup_status":r.get("lineup_status"),"batting_order_slot":r.get("batting_order_slot"),"starter_only_flag":r.get("starter_only_flag"),
            "HR_score":r.get("HR_score"),"Hit_score":r.get("Hit_score"),"park_favorability":r.get("park_favorability"),
            "stack_tag":"","reason":f"Hit_score {r.get('Hit_score'):.3f}; team vol {r.get('team_volatility')}; own K {r.get('team_k_tendency')}; opp pen {r.get('opp_bullpen_grade')}"
        })

    hr_pool = rows[
        (rows["HR_score"] >= 6.2) &
        (rows["opponent_pitcher_pick_type"].fillna("Neutral") != "Strong SP") &
        (rows["starter_only_flag"] == True)
    ].copy().sort_values(["HR_score","batting_order_slot"], ascending=[False, True])
    hr_pool = apply_team_pick_caps(hr_pool, MAX_REFINED_PICKS_PER_TEAM)
    team_counts = hr_pool.head(4)["teamName"].value_counts().to_dict()
    for _, r in hr_pool.head(4).iterrows():
        picks.append({
            "category":"HR Pick","bet_type":"HR","playerName":r["playerName"],"teamName":r["teamName"],"game":r.get("game"),
            "opponent_pitcher":r.get("opponent_pitcher"),"opponent_pitcher_team":r.get("opponent_pitcher_team"),
            "opponent_pitcher_pick_type":r.get("opponent_pitcher_pick_type"),"opponent_pitcher_sample":r.get("opponent_pitcher_sample"),
            "lineup_status":r.get("lineup_status"),"batting_order_slot":r.get("batting_order_slot"),"starter_only_flag":r.get("starter_only_flag"),
            "HR_score":r.get("HR_score"),"Hit_score":r.get("Hit_score"),"park_favorability":r.get("park_favorability"),
            "stack_tag":"STACK HR SPOT" if team_counts.get(r["teamName"], 0) >= 2 else "",
            "reason":f"HR_score {r.get('HR_score'):.3f}; public bias {r.get('public_bias')}; opp pen {r.get('opp_bullpen_grade')}"
        })

    out = pd.DataFrame(picks, columns=cols)
    if out.empty:
        out = pd.DataFrame([{"category":"Info","bet_type":"No Plays","reason":"No refined picks met today’s filters"}], columns=cols)
    return out


def build_pitcher_line_value(pitcher_metrics):
    rows = []
    for _, r in pitcher_metrics.iterrows():
        ip = nz(r.get("innings_pitched"))
        ks = nz(r.get("strikeouts"))
        gs = max(nz(r.get("games_started"), 1), 1)
        avg_ip = round(ip / gs, 3) if gs else ip
        avg_k = round(ks / gs, 3) if gs else ks
        kpi = round(ks / ip, 3) if ip else 0
        recent_ip = nz(r.get("last2_ip_avg"), avg_ip)
        recent_k = nz(r.get("last2_k_avg"), avg_k)
        recent_pitches = nz(r.get("last2_pitch_avg"), 0)
        opp_k_bonus = nz(r.get("opp_k_matchup_bonus"), 0)
        proj_base = round((avg_k * 0.40) + (recent_k * 0.50) + (opp_k_bonus * 0.90), 3)
        mid = max(0, round(proj_base))
        floor = max(0, mid - 1)
        ceil = mid + 1
        short_leash_flag = str(r.get("short_leash_flag") or "Unknown")
        if short_leash_flag.startswith("Yes"):
            max_line, tier, action = "", "Pass", "Pass - short leash risk"
        elif recent_ip >= 5.4 and recent_k >= 7 and recent_pitches >= 90 and opp_k_bonus >= 0.35:
            max_line, tier, action = 6.5, "Hammer", "Bet over up to 6.5"
        elif recent_ip >= 5.0 and recent_k >= 6 and recent_pitches >= 85:
            max_line, tier, action = 5.5, "Strong", "Bet over up to 5.5"
        elif recent_ip >= 4.5 and recent_k >= 5 and recent_pitches >= 80 and opp_k_bonus >= 0:
            max_line, tier, action = 4.5, "Lean", "Only bet over at 4.5"
        else:
            max_line, tier, action = "", "Pass", "Pass"
        safest = "Avoid" if tier == "Pass" else ("Over Ks / Over outs / Under ER" if tier in ("Hammer","Strong") else "Over outs / Under ER")
        rows.append({
            "pitcherName":r["pitcherName"],"teamName":r["teamName"],"opponentTeam":r["opponentTeam"],"pick_type":r["pick_type"],"sample_flag":r["sample_flag"],
            "innings_pitched":ip,"strikeouts":ks,"earned_runs":r.get("earned_runs"),"hits_allowed":r.get("hits_allowed"),"walks":r.get("walks"),
            "pitcher_score_adj":r.get("pitcher_score_adj"),"avg_ip_per_start":avg_ip,"avg_k_per_start":avg_k,"k_per_inning":kpi,
            "last2_ip_avg":r.get("last2_ip_avg"),"last2_k_avg":r.get("last2_k_avg"),"last2_pitch_avg":r.get("last2_pitch_avg"),
            "short_leash_flag":short_leash_flag,
            "opp_team_k_rate":r.get("opp_team_k_rate"),"opp_team_k_tendency":r.get("opp_team_k_tendency"),"opp_k_matchup_bonus":opp_k_bonus,
            "own_bullpen_grade":r.get("own_bullpen_grade"),
            "projected_k_floor":floor,"projected_k_mid":mid,"projected_k_ceiling":ceil,"max_playable_k_line":max_line,
            "k_value_tier":tier,"recommended_k_action":action,"safest_pitching_play":safest,
            "notes":f"Starter locked; recent form + team K layer + bullpen support. oppK={r.get('opp_team_k_tendency')} pen={r.get('own_bullpen_grade')}",
            "probable_starter_name":r.get("probable_starter_name"),"starter_status":r.get("starter_status"),
        })
    return pd.DataFrame(rows).sort_values(["projected_k_mid","pitcher_score_adj"], ascending=False).reset_index(drop=True)


def build_daily_card(game_rankings, refined_picks, pitcher_line_value, hr_drought):
    rows = []
    used_teams = set()

    ml = game_rankings[game_rankings["recommended_play"].isin(["Moneyline Lean","Stack Spot"])].sort_values("edge_vs_opponent", ascending=False)
    if not ml.empty:
        for _, best in ml.iterrows():
            if best["teamName"] in used_teams:
                continue
            rows.append({"section":"Best Overall","play_type":"Best Moneyline","pick":f"{best['teamName']} ML","team":best["teamName"],"opponent":best["opponentTeam"],"confidence":best["win_rating"],"why_it_made_the_card":f"Edge {best['edge_vs_opponent']}; {best['pitcher_pick_type']} vs {best['opponent_pitcher_pick_type']}; volatility pen {best['volatility_penalty_ml']}","source_tab":"Game_Rankings"})
            used_teams.add(best["teamName"])
            break
    else:
        rows.append({"section":"Best Overall","play_type":"Best Moneyline","pick":"No qualified ML play","confidence":"Pass","why_it_made_the_card":"No qualifying ML edge","source_tab":"Game_Rankings"})

    hit = refined_picks[refined_picks["category"].eq("Hit Pick")] if not refined_picks.empty and "category" in refined_picks.columns else pd.DataFrame()
    if not hit.empty:
        for _, best in hit.sort_values(["Hit_score","batting_order_slot"], ascending=[False, True]).iterrows():
            if best["teamName"] in used_teams:
                continue
            rows.append({"section":"Best Overall","play_type":"Best Hit","pick":best["playerName"],"team":best["teamName"],"opponent":best.get("opponent_pitcher_team"),"confidence":"Strong" if (best.get("batting_order_slot") or 99) <= 6 else "Lean","why_it_made_the_card":best.get("reason"),"source_tab":"Refined_Picks"})
            used_teams.add(best["teamName"])
            break
    else:
        rows.append({"section":"Best Overall","play_type":"Best Hit","pick":"No qualified hit play","confidence":"Pass","why_it_made_the_card":"Refined picks sheet was empty","source_tab":"Refined_Picks"})

    hr = refined_picks[refined_picks["category"].eq("HR Pick")] if not refined_picks.empty and "category" in refined_picks.columns else pd.DataFrame()
    if not hr.empty:
        for _, best in hr.sort_values(["HR_score","batting_order_slot"], ascending=[False, True]).iterrows():
            if best["teamName"] in used_teams:
                continue
            rows.append({"section":"Best Overall","play_type":"Best HR","pick":best["playerName"],"team":best["teamName"],"opponent":best.get("opponent_pitcher_team"),"confidence":"Strong","why_it_made_the_card":best.get("reason"),"source_tab":"Refined_Picks"})
            used_teams.add(best["teamName"])
            break
    else:
        rows.append({"section":"Best Overall","play_type":"Best HR","pick":"No qualified HR play","confidence":"Pass","why_it_made_the_card":"Refined picks sheet was empty","source_tab":"Refined_Picks"})

    kval = pitcher_line_value[pitcher_line_value["starter_status"].eq("Confirmed")] if not pitcher_line_value.empty and "starter_status" in pitcher_line_value.columns else pitcher_line_value
    if kval is not None and not kval.empty:
        for _, best in kval.sort_values(["projected_k_mid","pitcher_score_adj"], ascending=False).iterrows():
            if best["teamName"] in used_teams or str(best.get("short_leash_flag") or "").startswith("Yes"):
                continue
            rows.append({"section":"Best Overall","play_type":"Best K Prop","pick":best["pitcherName"],"team":best["teamName"],"opponent":best["opponentTeam"],"confidence":best["k_value_tier"],"why_it_made_the_card":f"{best['recommended_k_action']}; projected {best['projected_k_floor']}-{best['projected_k_ceiling']} Ks; max line {best['max_playable_k_line']}","source_tab":"Pitcher_Line_Value"})
            rows.append({"section":"Secondary","play_type":"Safest Pitching Play","pick":best["pitcherName"],"team":best["teamName"],"opponent":best["opponentTeam"],"confidence":best["k_value_tier"],"why_it_made_the_card":best["safest_pitching_play"],"source_tab":"Pitcher_Line_Value"})
            used_teams.add(best["teamName"])
            break
    else:
        rows.append({"section":"Best Overall","play_type":"Best K Prop","pick":"No qualified K play","confidence":"Pass","why_it_made_the_card":"No confirmed probable starter qualified","source_tab":"Pitcher_Line_Value"})

    if not hr_drought.empty:
        watch = hr_drought[hr_drought["status"].astype(str).str.contains("Overdue", na=False)].copy()
        if not watch.empty:
            watch["status_rank"] = watch["status"].astype(str).str.extract(r"\+(\d+)").fillna(0).astype(int)
            for _, best in watch.sort_values(["status_rank","homeRuns"], ascending=[False, False]).iterrows():
                if best["teamName"] in used_teams:
                    continue
                rows.append({"section":"Secondary","play_type":"Drought HR Watch","pick":best["playerName"],"team":best["teamName"],"confidence":best["status"],"why_it_made_the_card":f"{best['homeRuns']} HR; park={best['park_favorability']}; drought={best['current_games_without_hr']} games","source_tab":"HR_Drought"})
                break
    return pd.DataFrame(rows)

def build_final_card(player_rows, game_rankings, pitcher_line_value):
    cols = ["slot","bet_type","pick","team","opponent","confidence","why_it_made_the_card","source_tab"]
    rows = []
    used_players = set()
    team_counts = {}

    def can_use_team(team, limit=2):
        return team_counts.get(team, 0) < limit

    def add_row(slot, bet_type, pick, team, opponent, confidence, why, source_tab):
        rows.append({
            "slot": slot, "bet_type": bet_type, "pick": pick, "team": team, "opponent": opponent,
            "confidence": confidence, "why_it_made_the_card": why, "source_tab": source_tab
        })
        team_counts[team] = team_counts.get(team, 0) + 1
        used_players.add((team, pick))

    # High-edge ML only
    if game_rankings is not None and not game_rankings.empty:
        ml_pool = game_rankings[
            (game_rankings["edge_vs_opponent"].fillna(0) >= 10) &
            (~game_rankings["recommended_play"].astype(str).str.contains("Avoid", na=False)) &
            (game_rankings["pitcher_pick_type"].isin(["Strong SP", "K Upside", "Neutral"])) &
            (game_rankings["opponent_pitcher_pick_type"].isin(["Short Leash Risk", "Attack With Hitters", "Low Sample", "Neutral"]))
        ].copy().sort_values(["edge_vs_opponent","team_score"], ascending=[False, False])
        if not ml_pool.empty:
            best = ml_pool.iloc[0]
            rows.append({
                "slot": "Core 1", "bet_type": "Moneyline", "pick": f"{best['teamName']} ML", "team": best["teamName"],
                "opponent": best["opponentTeam"], "confidence": "A",
                "why_it_made_the_card": f"Edge {best['edge_vs_opponent']}; {best['pitcher_pick_type']} vs {best['opponent_pitcher_pick_type']}",
                "source_tab": "Game_Rankings"
            })
            team_counts[best["teamName"]] = 1

    if player_rows is None or player_rows.empty:
        if not rows:
            return pd.DataFrame([{"slot":"Info","bet_type":"No Plays","pick":"No final card plays qualified","team":"","opponent":"","confidence":"Pass","why_it_made_the_card":"No data available","source_tab":"Final_Card"}], columns=cols)
        return pd.DataFrame(rows, columns=cols)

    base = player_rows.copy()
    base = base[base["auto_pitcher_name"].notna()].copy()
    base["lineup_ok"] = base["starter_only_flag"].fillna(False)
    base["slot_num"] = pd.to_numeric(base.get("batting_order_slot"), errors="coerce").fillna(9)
    base["power_filter"] = (base["homeRuns"].fillna(0) >= 3) | (base["avg_games_between_hrs"].fillna(99) <= 2.5)

    # Hits: two strongest only
    hit_pool = base[
        (base["lineup_ok"] == True) &
        (base["Hit_score"].fillna(0) >= 4.0) &
        (base["opponent_pitcher_pick_type"].fillna("Neutral") != "Strong SP") &
        (base["slot_num"] <= 5)
    ].copy().sort_values(["Hit_score","slot_num","totalHits"], ascending=[False, True, False])

    hit_added = 0
    for _, r in hit_pool.iterrows():
        if hit_added >= 2:
            break
        if (r["teamName"], r["playerName"]) in used_players or not can_use_team(r["teamName"], 2):
            continue
        add_row(
            f"Core {len(rows)+1}", "1+ Hit", r["playerName"], r["teamName"], r.get("opponentTeam"), "A",
            f"Hit_score {r['Hit_score']:.3f}; slot {int(r['slot_num'])}; opp {r.get('opponent_pitcher_pick_type')}; park {r.get('park_favorability')}",
            "Refined_Picks"
        )
        hit_added += 1

    # HRs: exactly two if available, strict filters
    hr_pool = base[
        (base["lineup_ok"] == True) &
        (base["HR_score"].fillna(0) >= 5.5) &
        (base["park_favorability"] == "Favorable") &
        (base["opponent_pitcher_pick_type"].fillna("Neutral").isin(["Short Leash Risk", "Attack With Hitters", "Low Sample"])) &
        (base["power_filter"] == True) &
        (base["slot_num"] <= 5)
    ].copy().sort_values(["HR_score","slot_num","homeRuns"], ascending=[False, True, False])

    hr_added = 0
    for _, r in hr_pool.iterrows():
        if hr_added >= 2:
            break
        if (r["teamName"], r["playerName"]) in used_players or not can_use_team(r["teamName"], 2):
            continue
        add_row(
            f"Power {hr_added+1}", "HR", r["playerName"], r["teamName"], r.get("opponentTeam"), "B",
            f"HR_score {r['HR_score']:.3f}; slot {int(r['slot_num'])}; power ok; opp {r.get('opponent_pitcher_pick_type')}; park Favorable",
            "Refined_Picks"
        )
        hr_added += 1

    # K prop: one elite only
    if pitcher_line_value is not None and not pitcher_line_value.empty:
        k_pool = pitcher_line_value[
            (pitcher_line_value["starter_status"] == "Confirmed") &
            (~pitcher_line_value["short_leash_flag"].astype(str).str.startswith("Yes", na=False)) &
            (pitcher_line_value["k_value_tier"].isin(["Hammer", "Strong"])) &
            (pitcher_line_value["max_playable_k_line"].astype(str) != "")
        ].copy().sort_values(["projected_k_mid","pitcher_score_adj"], ascending=[False, False])
        for _, r in k_pool.iterrows():
            if not can_use_team(r["teamName"], 2):
                continue
            add_row(
                f"Pitch {1}", "K Prop", r["pitcherName"], r["teamName"], r["opponentTeam"],
                "A" if r["k_value_tier"] == "Hammer" else "B",
                f"{r['recommended_k_action']}; projected {r['projected_k_floor']}-{r['projected_k_ceiling']} Ks",
                "Pitcher_Line_Value"
            )
            break

    if not rows:
        return pd.DataFrame([{"slot":"Info","bet_type":"No Plays","pick":"No final card plays qualified","team":"","opponent":"","confidence":"Pass","why_it_made_the_card":"Final-card thresholds removed all plays","source_tab":"Final_Card"}], columns=cols)

    return pd.DataFrame(rows, columns=cols)


def header_map(ws):
    return {cell.value: idx + 1 for idx, cell in enumerate(ws[1])}

def color_status_col(ws, header_name="status"):
    h = header_map(ws)
    c = h.get(header_name)
    if not c:
        return
    for r in range(2, ws.max_row + 1):
        v = str(ws.cell(row=r, column=c).value or "")
        if v.startswith("On Pace"):
            ws.cell(row=r, column=c).fill = GREEN
        elif v.startswith("Slightly Overdue"):
            ws.cell(row=r, column=c).fill = YELLOW
        elif v.startswith("Overdue"):
            ws.cell(row=r, column=c).fill = RED

def highlight_top_rows(ws, n=10):
    for r in range(2, min(ws.max_row, n + 1) + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(row=r, column=c).fill = GREEN

def main(season: int, target_date: str):
    OUTPUT_DIR.mkdir(exist_ok=True)
    print_step("🚀 V40.1 final-card rebuild started...")
    sched_ctx, schedule_rows = get_schedule_game_context(target_date)
    now_et = dt.datetime.now(ZoneInfo("America/New_York"))
    eligible_schedule_rows = filter_pregame_schedule_rows(schedule_rows, now_et=now_et, buffer_minutes=5)
    print_step(f"⏱️ Pregame-eligible games: {len(eligible_schedule_rows)} of {len(schedule_rows)}")

    all_players = build_scheduled_player_pool(schedule_rows, season)
    lineup_map, slot_map = get_confirmed_lineups(target_date)
    locked_players = build_locked_player_pool(all_players, lineup_map, slot_map)

    print_step("🧠 Building full-slate player pool (all scheduled players) and tagging confirmed lineups when available ...")
    scoring_pool = all_players.copy()
    if scoring_pool.empty:
        player_rows = pd.DataFrame()
    else:
        scoring_pool["lineup_status"] = scoring_pool.apply(
            lambda r: lineup_map.get((r["teamName"], normalize_name(r["playerName"])), "Unknown"), axis=1
        )
        scoring_pool["batting_order_slot"] = scoring_pool.apply(
            lambda r: slot_map.get((r["teamName"], normalize_name(r["playerName"])), None), axis=1
        )
        scoring_pool["starter_only_flag"] = scoring_pool["lineup_status"].eq("Confirmed Starter")
        player_rows = build_hit_hr_rows(scoring_pool, season, sched_ctx)
    player_rows = player_rows[player_rows["auto_pitcher_name"].notna()].copy() if not player_rows.empty else player_rows

    pitcher_metrics = build_pitcher_metrics(schedule_rows, season)
    team_context_df = build_team_context_df(schedule_rows, season)
    player_rows = enrich_player_rows_with_team_context(player_rows, pitcher_metrics, team_context_df)
    pitcher_metrics = enrich_pitcher_metrics_with_team_context(pitcher_metrics, team_context_df)
    pitcher_line_value = build_pitcher_line_value(pitcher_metrics)
    game_rankings = build_game_rankings(schedule_rows, player_rows, player_rows, pitcher_metrics)

    eligible_games = set((eligible_schedule_rows.get("away_team", pd.Series(dtype=object)).fillna("") + " @ " + eligible_schedule_rows.get("home_team", pd.Series(dtype=object)).fillna("")).tolist())
    eligible_teams = set(eligible_schedule_rows.get("away_team", pd.Series(dtype=object)).dropna().tolist() + eligible_schedule_rows.get("home_team", pd.Series(dtype=object)).dropna().tolist())

    pregame_player_rows = player_rows[player_rows["teamName"].isin(eligible_teams)].copy() if not player_rows.empty else player_rows
    pregame_pitcher_line_value = pitcher_line_value[pitcher_line_value["teamName"].isin(eligible_teams)].copy() if not pitcher_line_value.empty else pitcher_line_value
    pregame_game_rankings = game_rankings[game_rankings["game"].isin(eligible_games)].copy() if not game_rankings.empty else game_rankings
    refined_picks = build_refined_picks(pregame_player_rows, pitcher_metrics, pregame_game_rankings)

    opp_map = pitcher_metrics[["opponentTeam","pitcherName","pick_type"]].drop_duplicates().rename(columns={
        "opponentTeam":"teamName","pitcherName":"opponent_pitcher","pick_type":"opponent_pitcher_pick_type"
    }) if not pitcher_metrics.empty else pd.DataFrame(columns=["teamName","opponent_pitcher","opponent_pitcher_pick_type"])

    # Ensure Final_Card logic always has opponent pitcher type available on player rows.
    if not player_rows.empty:
        if "opponent_pitcher_pick_type" not in player_rows.columns:
            player_rows = player_rows.merge(opp_map[["teamName", "opponent_pitcher_pick_type"]].drop_duplicates(), on="teamName", how="left")
        else:
            missing_mask = player_rows["opponent_pitcher_pick_type"].isna()
            if missing_mask.any():
                fill_map = opp_map[["teamName", "opponent_pitcher_pick_type"]].drop_duplicates()
                player_rows = player_rows.merge(fill_map, on="teamName", how="left", suffixes=("", "_fill"))
                player_rows["opponent_pitcher_pick_type"] = player_rows["opponent_pitcher_pick_type"].fillna(player_rows["opponent_pitcher_pick_type_fill"])
                player_rows = player_rows.drop(columns=["opponent_pitcher_pick_type_fill"])

    hr_drought = player_rows[["season","teamName","playerName","avg_games_between_hrs","current_games_without_hr","longest_games_without_hr","hr_status","homeRuns","last_hr_date","gamesPlayed","park_favorability","lineup_status","batting_order_slot","starter_only_flag"]].rename(columns={"hr_status":"status"}).merge(opp_map, on="teamName", how="left")
    hit_drought = player_rows[["season","teamName","playerName","avg_games_between_hits","current_games_without_hit","longestHitDrought","hit_status","totalHits","gamesPlayed","park_favorability","lineup_status","batting_order_slot","starter_only_flag"]].rename(columns={"hit_status":"status"}).merge(opp_map, on="teamName", how="left")

    daily_card = build_daily_card(pregame_game_rankings, refined_picks, pregame_pitcher_line_value, hr_drought[hr_drought['teamName'].isin(eligible_teams)].copy() if not hr_drought.empty else hr_drought)
    final_card = build_final_card(pregame_player_rows, pregame_game_rankings, pregame_pitcher_line_value)
    frozen_final_card = save_frozen_daily_final_card(target_date, final_card)

    ts = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    outfile = OUTPUT_DIR / f"HR_Hit_Drought_v40_stats-{season}_{ts}.xlsx"

    print_step("💾 Writing workbook ...")
    with pd.ExcelWriter(outfile, engine="openpyxl") as writer:
        pd.DataFrame([
            ("requested_season", season),
            ("target_game_date", target_date),
            ("message", "v39.3 full-slate rebuild with lineup tagging plus Top 200 HR and Top 50 HIT output"),
            ("locked_players_count", len(locked_players)),
        ], columns=["field","value"]).to_excel(writer, sheet_name="Run_Info", index=False)

        schedule_rows.to_excel(writer, sheet_name="Schedule_Context", index=False)
        team_context_df.to_excel(writer, sheet_name="Team_Context", index=False)
        hr_drought.to_excel(writer, sheet_name="HR_Drought", index=False)
        hit_drought.to_excel(writer, sheet_name="Hit_Drought", index=False)
        pitcher_metrics.to_excel(writer, sheet_name="Pitcher_Metrics", index=False)
        pitcher_line_value.to_excel(writer, sheet_name="Pitcher_Line_Value", index=False)
        game_rankings.to_excel(writer, sheet_name="Game_Rankings", index=False)
        refined_picks.to_excel(writer, sheet_name="Refined_Picks", index=False)
        daily_card.to_excel(writer, sheet_name="Daily_Card", index=False)
        frozen_final_card.to_excel(writer, sheet_name="Final_Card", index=False)

        top_hr = pd.DataFrame()
        top_hit = pd.DataFrame()
        if not pregame_player_rows.empty:
            top_hr = pregame_player_rows.nlargest(6, "HR_score")[["playerName","teamName","auto_pitcher_name","auto_pitcher_hand","HR_score","batting_order_slot","lineup_status","starter_only_flag"]].copy()
            top_hr.insert(0, "type", "HR")
            top_hit = pregame_player_rows.nlargest(6, "Hit_score")[["playerName","teamName","auto_pitcher_name","auto_pitcher_hand","Hit_score","batting_order_slot","lineup_status","starter_only_flag"]].copy()
            top_hit.insert(0, "type", "HIT")
        top_picks = pd.concat([top_hr, top_hit], ignore_index=True)
        top_picks.to_excel(writer, sheet_name="Top_Picks", index=False)

    wb = load_workbook(outfile)
    for s in ["HR_Drought","Hit_Drought"]:
        if s in wb.sheetnames:
            color_status_col(wb[s], "status")
    for s in ["Pitcher_Metrics","Pitcher_Line_Value","Game_Rankings","Daily_Card","Final_Card","Top_Picks","Team_Context"]:
        if s in wb.sheetnames:
            highlight_top_rows(wb[s], 10)
    wb.save(outfile)

    json_filename = f"HR_Hit_Drought_v40_appdata-{season}_{target_date}_{ts}.json"
    json_output_path = OUTPUT_DIR / json_filename

    app_payload = build_app_payload(
        target_date=target_date,
        final_card_df=frozen_final_card,
        player_rows=player_rows,
        game_rankings=game_rankings,
        pitcher_metrics=pitcher_metrics,
        pitcher_line_value=pitcher_line_value,
        hr_drought=hr_drought,
        hit_drought=hit_drought,
        top_picks=top_picks,
        refined_picks=refined_picks
    )

    save_app_json(app_payload, json_output_path)
    latest_snapshot = save_latest_app_snapshot(target_date, app_payload, json_filename)
    print_step(f"🧾 JSON created: {json_output_path}")
    print_step(f"🧾 Latest app snapshot: {latest_snapshot}")

    history_info = save_pick_history(
        target_date=target_date,
        json_filename=json_filename,
        final_card_df=frozen_final_card,
        top_picks_df=top_picks,
        game_rankings_df=game_rankings,
        pitcher_line_value_df=pitcher_line_value,
    )
    print_step(f"🗂️ Pick history saved: {history_info['rows_saved']} rows")
    print_step(f"🗂️ History CSV: {history_info['history_csv']}")

    results_info = grade_pending_history_rows(target_date, season)
    print_step(f"📈 Results graded this run: {results_info['graded_rows']}")
    print_step(f"📈 Performance summary: {results_info['performance']}")

    print_step("✅ DONE!")
    print_step(f"Created: {outfile}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="v40 final-card rebuild")
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    parser.add_argument("--date", type=str, default=dt.date.today().strftime("%Y-%m-%d"), help="Game date in YYYY-MM-DD format. Defaults to today if omitted.")
    args = parser.parse_args()
    main(args.season, args.date)
