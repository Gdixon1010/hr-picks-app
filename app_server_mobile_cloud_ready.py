from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
from pathlib import Path
import json
import datetime as dt
import os
import time
import re
import requests
from threading import Lock
from zoneinfo import ZoneInfo

from hr_v41_cloud_ready import main as run_model_main

app = FastAPI()

# Server-side refresh lock: prevents multiple users from running the model at the same time.
refresh_lock = Lock()
is_refreshing = False


def resolve_storage_dir() -> Path:
    configured = os.getenv("HR_APP_DATA_DIR")
    if configured:
        p = Path(configured)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Helpful default for Render Disk users if they mount to /var/data
    render_default = Path("/var/data/hr-picks/output")
    if render_default.parent.exists():
        render_default.mkdir(parents=True, exist_ok=True)
        return render_default

    local_default = Path("output")
    local_default.mkdir(parents=True, exist_ok=True)
    return local_default


OUTPUT_DIR = resolve_storage_dir()


def get_latest_json_file():
    patterns = [
        "HR_Hit_Drought_v41_appdata-*.json",
        "HR_Hit_Drought_v40_appdata-*.json",
    ]
    files = []
    for pat in patterns:
        files.extend(OUTPUT_DIR.glob(pat))
    files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None




def read_json_file(path: Path, default):
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def load_latest_data():
    history_dir = OUTPUT_DIR / "history"
    latest = get_latest_json_file()

    if latest and latest.exists():
        with open(latest, "r", encoding="utf-8") as f:
            data = json.load(f)
        filename = latest.name
        path_str = str(latest)
        try:
            eastern_now = dt.datetime.fromtimestamp(latest.stat().st_mtime, ZoneInfo("America/New_York"))
            display = eastern_now.strftime("%b %d, %Y %I:%M %p ET").replace(" 0", " ")
        except Exception:
            eastern_now = None
            display = None
    else:
        snapshot = read_json_file(history_dir / "latest_app_data.json", {})
        data = snapshot.get("app_payload") or {
            "date": None,
            "final_card": {"generated_section": "final_card", "plays": []},
            "games": [],
            "research": {},
        }
        filename = snapshot.get("json_filename")
        path_str = str(history_dir / "latest_app_data.json") if snapshot else None
        eastern_now = None
        saved_label = snapshot.get("saved_at_et")
        display = saved_label

    frozen_latest = read_json_file(history_dir / "final_card_by_date_latest.json", {})
    frozen_rows = frozen_latest.get("rows") or []
    frozen_date = frozen_latest.get("target_date")

    data_date = str(data.get("date")) if data.get("date") else None
    if frozen_rows and frozen_date and (data_date is None or frozen_date == data_date):
        data["final_card"] = {"generated_section": "final_card", "plays": frozen_rows}
        if not data.get("date"):
            data["date"] = frozen_date

    data["results"] = read_json_file(history_dir / "performance_summary_latest.json", {"overall": {}, "by_bet_type": [], "by_confidence": [], "recent_results": []})
    data["results_latest"] = read_json_file(history_dir / "results_history_latest.json", {"graded_rows": 0, "rows": []})
    data["info"] = {
        "purpose": "This app finds MLB betting edges by combining player trends, drought logic, matchup strength, pitcher quality, lineup context, and park factors.",
        "how_to_use": [
            "Start on Final Card for the strongest condensed plays.",
            "Use Games to see matchup context, start time, and top game-level picks.",
            "Use Research to drill into HR drought, hit drought, pitcher metrics, and game rankings.",
            "Filter for overdue players, favorable parks, and weaker pitcher types to isolate stronger spots.",
            "Treat Strong SP as a warning for hitter props and Short Leash Risk or Attack With Hitters as friendlier hitting environments."
        ],
        "card_logic": [
            {"label": "Core 1", "meaning": "Highest-priority main play on the card. Usually the cleanest overall edge among the non-HR hitter or ML plays."},
            {"label": "Core 2", "meaning": "Strong play that ranks just below Core 1. Still a main card option, but slightly less clean than the top play."},
            {"label": "Core 3", "meaning": "Solid playable pick that made the card, but with a little less edge or a little more volatility than the top two cores."},
            {"label": "Pitch 1", "meaning": "Top strikeout prop on the card based on projected Ks versus the listed line and matchup context."},
            {"label": "Power 1", "meaning": "Top home run upside play on the card. This is the highest-variance play type and should usually be bet smaller."}
        ],
        "unit_strategy": [
            "Use a consistent unit size instead of changing bet size emotionally. A common baseline is 1 unit = 1% of bankroll.",
            "Suggested sizing: Core 1 = 1.0u, Core 2 = 0.75u, Core 3 = 0.5u to 0.75u, Pitch 1 = 0.75u to 1.0u, Power 1 = 0.25u to 0.5u.",
            "Treat HR picks as the most volatile part of the card. They can be valuable, but they should usually carry the smallest risk.",
            "Do not chase losses, double units after a bad day, or force action on every pick. The card works best when sizing stays disciplined over time."
        ],
        "terms": [
            {"term": "Model Insight", "meaning": "A short plain-English explanation of why a pick made the card based on the model's edge, matchup, and context signals."},
            {"term": "Attack With Hitters", "meaning": "Pitcher or pitching environment is vulnerable enough to target hitters."},
            {"term": "Strong SP", "meaning": "Strong starting pitcher. Usually a downgrade for hitter props."},
            {"term": "Short Leash Risk", "meaning": "Pitcher may not work deep into the game, which can help hitters later against the bullpen."},
            {"term": "K Upside", "meaning": "Pitcher has a favorable strikeout profile for K props."},
            {"term": "On Pace", "meaning": "Current drought is normal relative to the player’s average pattern."},
            {"term": "Slightly Overdue", "meaning": "Player is running a bit longer than usual without the event."},
            {"term": "Overdue", "meaning": "Player is well beyond normal drought range and may be due for regression."},
            {"term": "Hit Score", "meaning": "Composite score for hit probability using matchup, context, and trend inputs. Higher is better."},
            {"term": "HR Score", "meaning": "Composite score for home run appeal using power, park, matchup, and drought context. Higher is better."},
            {"term": "Moneyline Lean", "meaning": "The model sees an edge on that team, but size depends on edge strength and matchup quality."}
        ]
    }
    data["_meta"] = {
        "filename": filename,
        "path": path_str,
        "last_updated_display": display,
        "eastern_now": eastern_now.strftime("%Y-%m-%d %I:%M %p ET").replace(" 0", " ") if eastern_now else None,
    }
    return data


# -----------------------------
# Auto Results Grading (runs first refresh after 4 AM ET)
# -----------------------------
MLB_API = "https://statsapi.mlb.com/api/v1"


def _history_dir() -> Path:
    d = OUTPUT_DIR / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _api_get(path: str, params=None, timeout: int = 30):
    url = path if str(path).startswith("http") else f"{MLB_API}{path}"
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _norm_name(value) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _safe_date(value) -> str:
    return str(value or "").strip()[:10]


def _is_placeholder_pick(row: dict) -> bool:
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


def _get_card_history(card_type: str) -> dict:
    """card_type = final_card or refined_picks"""
    filename = "final_card_by_date.json" if card_type == "final_card" else "refined_picks_by_date.json"
    return read_json_file(_history_dir() / filename, {})


def _card_rows_for_date_from_history(target_date: str, card_type: str) -> list:
    hist = _get_card_history(card_type)
    if isinstance(hist, dict):
        payload = hist.get(target_date) or {}
        rows = payload.get("rows") if isinstance(payload, dict) else []
        if isinstance(rows, list) and rows:
            return [r for r in rows if isinstance(r, dict) and not _is_placeholder_pick(r)]
    return []


def _all_appdata_files_for_date(target_date: str):
    files = [p for p in OUTPUT_DIR.glob("HR_Hit_Drought_v*_appdata-*.json") if target_date in p.name]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _latest_appdata_for_date(target_date: str) -> Path | None:
    files = _all_appdata_files_for_date(target_date)
    return files[0] if files else None


def _extract_rows_from_appdata(payload: dict, card_type: str) -> list:
    if card_type == "final_card":
        fc = payload.get("final_card")
        if isinstance(fc, dict):
            rows = fc.get("plays") or []
        elif isinstance(fc, list):
            rows = fc
        else:
            rows = []
        if not rows:
            rows = (((payload.get("research") or {}).get("final_card")) or [])
    else:
        rows = (((payload.get("research") or {}).get("refined_picks")) or payload.get("refined_picks") or [])
    return [r for r in rows if isinstance(r, dict) and not _is_placeholder_pick(r)]


def _card_rows_for_date(target_date: str, card_type: str) -> list:
    # Prefer locked history because that is the true "never remove until 4 AM" source.
    rows = _card_rows_for_date_from_history(target_date, card_type)
    if rows:
        return rows
    app_file = _latest_appdata_for_date(target_date)
    if not app_file:
        return []
    try:
        payload = json.loads(app_file.read_text(encoding="utf-8"))
        return _extract_rows_from_appdata(payload, card_type)
    except Exception:
        return []


def _schedule_games_by_date(target_date: str) -> list:
    try:
        data = _api_get("/schedule", params={"sportId": 1, "date": target_date, "hydrate": "team,linescore"})
        games = []
        for d in data.get("dates", []) or []:
            games.extend(d.get("games", []) or [])
        return games
    except Exception:
        return []


def _live_score_for_game(game_pk):
    if not game_pk:
        return {"is_final": False, "away_score": None, "home_score": None, "away_name": "", "home_name": ""}
    try:
        live = _api_get(f"/game/{game_pk}/feed/live")
        game_data = live.get("gameData") or {}
        live_data = live.get("liveData") or {}
        status = game_data.get("status") or {}
        teams = game_data.get("teams") or {}
        linescore = live_data.get("linescore") or {}
        away_team = teams.get("away") or {}
        home_team = teams.get("home") or {}
        away_ls = (linescore.get("teams") or {}).get("away", {})
        home_ls = (linescore.get("teams") or {}).get("home", {})
        status_values = " ".join(str(status.get(k) or "").lower() for k in ["abstractGameState", "codedGameState", "detailedState", "statusCode"])
        is_final = "final" in status_values or "game over" in status_values or str(status.get("statusCode") or "").upper() in {"F", "O"}
        return {
            "is_final": is_final,
            "away_score": away_ls.get("runs"),
            "home_score": home_ls.get("runs"),
            "away_name": away_team.get("name") or "",
            "home_name": home_team.get("name") or "",
        }
    except Exception:
        return {"is_final": False, "away_score": None, "home_score": None, "away_name": "", "home_name": ""}


def _boxscore_for_game(game_pk) -> dict:
    try:
        return _api_get(f"/game/{game_pk}/boxscore")
    except Exception:
        return {}


def _iter_boxscore_players(game: dict, target_team: str | None = None):
    box = _boxscore_for_game(game.get("gamePk")) if game.get("gamePk") else {}
    teams = box.get("teams") or {}
    target_norm = _norm_name(target_team) if target_team else ""
    for side in ("away", "home"):
        block = teams.get(side) or {}
        team_name = ((block.get("team") or {}).get("name")) or ""
        if target_norm and _norm_name(team_name) != target_norm:
            continue
        for pdata in (block.get("players") or {}).values():
            person = pdata.get("person") or {}
            yield team_name, pdata, person


def _boxscore_player_stat_by_name(target_date: str, player_name: str, group: str, team_name: str | None = None) -> dict | None:
    target = _norm_name(player_name)
    if not target:
        return None
    games = _schedule_games_by_date(target_date)
    # Try exact team first, then all teams. This avoids wrong saved team fields breaking grading.
    for use_team in (True, False):
        for game in games:
            for team, pdata, person in _iter_boxscore_players(game, team_name if use_team else None):
                full = person.get("fullName") or ""
                if _norm_name(full) == target:
                    return (pdata.get("stats") or {}).get(group, {}) or {}
    return None


def _team_map() -> dict:
    try:
        data = _api_get("/teams", params={"sportId": 1})
        return {t.get("name"): int(t.get("id")) for t in data.get("teams", []) if t.get("name") and t.get("id")}
    except Exception:
        return {}


def _team_id_for_name(team_name: str) -> int | None:
    teams = _team_map()
    if team_name in teams:
        return teams[team_name]
    n = _norm_name(team_name)
    for name, tid in teams.items():
        if _norm_name(name) == n:
            return tid
    return None


def _find_player_id_on_team(player_name: str, team_name: str, season: int = 2026) -> int | None:
    team_id = _team_id_for_name(team_name)
    if not team_id:
        return None
    try:
        data = _api_get(f"/teams/{team_id}/roster", params={"rosterType": "fullSeason", "season": season})
        target = _norm_name(player_name)
        for item in data.get("roster", []) or []:
            person = item.get("person") or {}
            if _norm_name(person.get("fullName")) == target:
                return int(person.get("id"))
    except Exception:
        return None
    return None


def _player_game_log_for_date(player_id: int, group: str, season: int, target_date: str) -> dict | None:
    try:
        data = _api_get(f"/people/{int(player_id)}/stats", params={"stats": "gameLog", "group": group, "season": season, "gameType": "R"})
        stats = data.get("stats") or []
        splits = stats[0].get("splits", []) if stats else []
        for split in splits:
            if _safe_date(split.get("date")) == target_date:
                return split.get("stat") or {}
    except Exception:
        return None
    return None


def _parse_k_line(row: dict) -> float | None:
    text = " ".join(str(row.get(k) or "") for k in ["why_it_made_the_card", "reason", "pick", "bet_type"])
    for pat in [r"over\s+up\s+to\s+(\d+(?:\.5)?)", r"max\s+line\s+(\d+(?:\.5)?)", r"line\s+(\d+(?:\.5)?)", r"(\d+(?:\.5)?)\s*ks"]:
        m = re.search(pat, text, flags=re.I)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                pass
    return None


def _grade_moneyline(row: dict, target_date: str) -> tuple[str, str]:
    team = str(row.get("team") or row.get("teamName") or "").strip()
    if not team:
        team = str(row.get("pick") or "").replace(" ML", "").strip()
    if not team:
        return "Unable to Grade", "Missing team name"
    team_norm = _norm_name(team)
    for game in _schedule_games_by_date(target_date):
        teams = game.get("teams") or {}
        away = teams.get("away") or {}
        home = teams.get("home") or {}
        away_name = ((away.get("team") or {}).get("name")) or ""
        home_name = ((home.get("team") or {}).get("name")) or ""
        if team_norm not in {_norm_name(away_name), _norm_name(home_name)}:
            continue
        live_score = _live_score_for_game(game.get("gamePk"))
        away_score = away.get("score") if away.get("score") is not None else live_score.get("away_score")
        home_score = home.get("score") if home.get("score") is not None else live_score.get("home_score")
        away_name = away_name or live_score.get("away_name")
        home_name = home_name or live_score.get("home_name")
        if away_score is not None and home_score is not None:
            winner = away_name if int(away_score) > int(home_score) else home_name
            result = "Win" if _norm_name(winner) == team_norm else "Loss"
            return result, f"{away_name} {away_score}, {home_name} {home_score}; winner={winner}"
        return "Pending", f"{away_name} @ {home_name} score not available yet"
    return "Unable to Grade", f"Could not find game for {team} on {target_date}"


def _grade_hitter(row: dict, target_date: str, season: int, mode: str) -> tuple[str, str]:
    player = str(row.get("pick") or row.get("playerName") or "").strip()
    team = str(row.get("team") or row.get("teamName") or "").strip()
    if not player:
        return "Unable to Grade", "Missing player"
    stat = _boxscore_player_stat_by_name(target_date, player, "batting", team_name=team)
    if stat is None:
        pid = row.get("playerId") or (_find_player_id_on_team(player, team, season) if team else None)
        if pid:
            stat = _player_game_log_for_date(int(pid), "hitting", season, target_date)
    if not stat:
        return "No Action", f"No hitting boxscore/game log found for {player} on {target_date}"
    hits = int(stat.get("hits", 0) or 0)
    hrs = int(stat.get("homeRuns", 0) or 0)
    if mode == "hit":
        return ("Win" if hits >= 1 else "Loss"), f"{player}: {hits} hit(s), {hrs} HR"
    return ("Win" if hrs >= 1 else "Loss"), f"{player}: {hrs} HR, {hits} hit(s)"


def _grade_k_prop(row: dict, target_date: str, season: int) -> tuple[str, str]:
    player = str(row.get("pick") or row.get("pitcherName") or row.get("playerName") or "").strip()
    team = str(row.get("team") or row.get("teamName") or "").strip()
    if not player:
        return "Unable to Grade", "Missing pitcher"
    line = _parse_k_line(row)
    if line is None:
        return "Unable to Grade", "Could not determine K line from card text"
    stat = _boxscore_player_stat_by_name(target_date, player, "pitching", team_name=team)
    if stat is None:
        pid = row.get("playerId") or (_find_player_id_on_team(player, team, season) if team else None)
        if pid:
            stat = _player_game_log_for_date(int(pid), "pitching", season, target_date)
    if not stat:
        return "No Action", f"No pitching boxscore/game log found for {player} on {target_date}"
    ks = int(stat.get("strikeOuts", 0) or 0)
    return ("Win" if ks > line else "Loss"), f"{player}: {ks} Ks vs line {line}"


def _grade_pick(row: dict, target_date: str, season: int = 2026, card_type: str = "Final Card") -> dict:
    bet_type = str(row.get("bet_type") or row.get("play_type") or "").strip()
    lower = bet_type.lower()
    if "moneyline" in lower or lower == "ml":
        result, detail = _grade_moneyline(row, target_date)
    elif "hit" in lower and "hr" not in lower and "home" not in lower:
        result, detail = _grade_hitter(row, target_date, season, "hit")
    elif lower == "hr" or "home run" in lower:
        result, detail = _grade_hitter(row, target_date, season, "hr")
    elif "k prop" in lower or "strikeout" in lower or lower in {"ks", "k"}:
        result, detail = _grade_k_prop(row, target_date, season)
    else:
        result, detail = "Unable to Grade", f"Unsupported bet type: {bet_type}"
    return {
        "target_date": target_date,
        "card_type": card_type,
        "bet_type": bet_type,
        "pick": row.get("pick") or row.get("playerName") or row.get("pitcherName"),
        "team": row.get("team") or row.get("teamName"),
        "opponent": row.get("opponent") or row.get("opponentTeam") or row.get("opponent_pitcher_team"),
        "confidence": row.get("confidence"),
        "slot": row.get("slot") or row.get("play_type") or row.get("section") or row.get("category"),
        "result_status": result,
        "result_detail": detail,
        "source_tab": row.get("source_tab") or ("Refined_Picks" if card_type == "Refined Picks" else "Final_Card"),
        "graded_at_et": dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M %p ET").replace(" 0", " "),
    }


def _dedupe_result_rows(rows: list) -> list:
    seen = set(); out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        key = (r.get("target_date"), r.get("card_type"), str(r.get("bet_type") or "").lower(), _norm_name(r.get("pick")), _norm_name(r.get("team")), _norm_name(r.get("opponent")), str(r.get("confidence") or ""))
        if key in seen:
            continue
        seen.add(key); out.append(r)
    return out


def _build_performance_summary(rows: list) -> dict:
    graded = [r for r in rows if r.get("result_status") in {"Win", "Loss"}]
    wins = sum(1 for r in graded if r.get("result_status") == "Win")
    losses = sum(1 for r in graded if r.get("result_status") == "Loss")
    total = wins + losses
    def group_summary(field):
        groups = {}
        for r in graded:
            k = str(r.get(field) or "Unknown")
            groups.setdefault(k, {"graded_picks": 0, "wins": 0, "losses": 0})
            groups[k]["graded_picks"] += 1
            if r.get("result_status") == "Win": groups[k]["wins"] += 1
            else: groups[k]["losses"] += 1
        out=[]
        for k,v in sorted(groups.items()):
            denom = v["wins"] + v["losses"]
            out.append({field: k, **v, "win_rate": round(v["wins"] / denom, 4) if denom else None})
        return out
    recent = sorted(rows, key=lambda r: (str(r.get("target_date") or ""), str(r.get("graded_at_et") or "")), reverse=True)[:100]
    return {
        "overall": {"graded_picks": total, "wins": wins, "losses": losses, "win_rate": round(wins / total, 4) if total else None},
        "by_bet_type": group_summary("bet_type"),
        "by_confidence": group_summary("confidence"),
        "by_card_type": group_summary("card_type"),
        "recent_results": recent,
    }


def grade_date_results(target_date: str, season: int = 2026, include_refined: bool = True) -> dict:
    hist = _history_dir()
    final_rows = _card_rows_for_date(target_date, "final_card")
    refined_rows = _card_rows_for_date(target_date, "refined_picks") if include_refined else []
    new_rows = []
    new_rows.extend(_grade_pick(play, target_date, season, "Final Card") for play in final_rows)
    new_rows.extend(_grade_pick(play, target_date, season, "Refined Picks") for play in refined_rows)
    if not new_rows:
        return {"status": "no_plays", "date": target_date, "message": "No locked/appdata picks found to grade"}
    latest_path = hist / "results_history_latest.json"
    existing_rows = []
    if latest_path.exists():
        try:
            existing_rows = (json.loads(latest_path.read_text(encoding="utf-8")).get("rows") or [])
        except Exception:
            existing_rows = []
    all_rows = _dedupe_result_rows(new_rows + existing_rows)
    summary = _build_performance_summary(all_rows)
    latest_payload = {"graded_rows": len(all_rows), "rows": all_rows, "updated_at_et": dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %I:%M %p ET").replace(" 0", " ")}
    latest_path.write_text(json.dumps(latest_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (hist / "performance_summary_latest.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (hist / "results_history.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in all_rows) + "\n", encoding="utf-8")
    return {"status": "ok", "date": target_date, "final_card_rows": len(final_rows), "refined_rows": len(refined_rows), "graded_new_rows": len(new_rows), "total_rows": len(all_rows), "summary": summary.get("overall")}


def auto_grade_after_4am(season: int = 2026) -> dict:
    hist = _history_dir()
    now = dt.datetime.now(ZoneInfo("America/New_York"))
    state_path = hist / "auto_grade_state.json"
    state = read_json_file(state_path, {})
    if now.hour < 4:
        return {"status": "skipped", "reason": "before_4am_et", "now_et": now.isoformat()}
    run_key = now.strftime("%Y-%m-%d")
    if state.get("last_auto_grade_run_key") == run_key:
        return {"status": "skipped", "reason": "already_ran_today", "run_key": run_key}
    results = []
    # Grade the previous 4 slate dates; this catches late games and any missed deploys.
    for i in range(1, 5):
        d = (now.date() - dt.timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            results.append(grade_date_results(d, season, include_refined=True))
        except Exception as e:
            results.append({"status": "error", "date": d, "message": str(e)})
    state["last_auto_grade_run_key"] = run_key
    state["last_auto_grade_at_et"] = now.strftime("%Y-%m-%d %I:%M %p ET").replace(" 0", " ")
    state["last_auto_grade_results"] = results
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "ok", "run_key": run_key, "results": results}


@app.get("/latest")
def latest():
    return JSONResponse(load_latest_data())


@app.get("/health")
def health():
    return JSONResponse({"status": "ok", "service": "hr-picks-app"})


@app.get("/grade-results")
def grade_results(date: str | None = None):
    try:
        if date:
            return JSONResponse(grade_date_results(date, 2026, include_refined=True))
        return JSONResponse(auto_grade_after_4am(season=2026))
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/refresh-data")
def refresh_data():
    global is_refreshing

    if is_refreshing:
        return JSONResponse({
            "status": "busy",
            "message": "Refresh already in progress. Please wait a few minutes, then click Reload App again.",
            "timezone": "America/New_York",
        })

    with refresh_lock:
        if is_refreshing:
            return JSONResponse({
                "status": "busy",
                "message": "Refresh already in progress. Please wait a few minutes, then click Reload App again.",
                "timezone": "America/New_York",
            })

        is_refreshing = True
        start_time = time.time()
        today = dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

        try:
            auto_grade_result = auto_grade_after_4am(season=2026)
            run_model_main(2026, today)
            duration = round(time.time() - start_time, 2)
            return JSONResponse({
                "status": "ok",
                "message": "Data refreshed",
                "date": today,
                "timezone": "America/New_York",
                "duration_seconds": duration,
                "auto_grade": auto_grade_result,
            })
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": str(e),
                    "date": today,
                    "timezone": "America/New_York",
                },
            )
        finally:
            is_refreshing = False



@app.get("/")
@app.get("/app")
def app_view():
    html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HR Picks App</title>
  <style>
    :root {
      --bg: #050914;
      --card: #121925;
      --card2: #0e1522;
      --border: #26324a;
      --text: #eef2f8;
      --muted: #b8c1d1;
      --accent: #4c83ff;
      --accent2: #2f5ec7;
      --chip: #172132;
      --soft: #0c1320;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    .wrap { max-width: 1520px; margin: 0 auto; padding: 18px 22px 48px; }
    h1 { margin: 0 0 6px; font-size: 68px; line-height: 0.95; font-weight: 900; letter-spacing: -1px; }
    .meta { color: var(--muted); font-size: 18px; margin-bottom: 18px; }
    .topbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
    .btn {
      background: var(--accent);
      color: white;
      border: 0;
      border-radius: 16px;
      padding: 14px 22px;
      font-weight: 800;
      font-size: 16px;
      cursor: pointer;
      box-shadow: 0 8px 24px rgba(76,131,255,.2);
    }
    .btn:hover { background: var(--accent2); }
    .btn:disabled { opacity: .7; cursor: wait; }
    .btn.secondary {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text);
      box-shadow: none;
    }
    .tabs { display: flex; gap: 12px; flex-wrap: wrap; margin: 18px 0 22px; }
    .tab {
      background: var(--chip);
      border: 1px solid var(--border);
      color: var(--text);
      border-radius: 999px;
      padding: 12px 16px;
      cursor: pointer;
      font-size: 16px;
    }
    .tab.active { background: #24324d; }
    .hidden { display: none !important; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 18px; }
    .card {
      background: linear-gradient(180deg, var(--card), var(--card2));
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 22px 22px 18px;
      box-shadow: 0 14px 40px rgba(0,0,0,.25);
    }
    .card h2 { margin: 0 0 14px; font-size: 24px; line-height: 1.15; }
    .kicker { color: var(--muted); margin: 8px 0 18px; font-size: 15px; }
    .line { margin: 8px 0; font-size: 17px; color: var(--text); }
    .label { font-weight: 800; }
    .muted { color: var(--muted); }
    .pill {
      display: inline-block; padding: 4px 10px; border-radius: 999px; background: #1d2740; border: 1px solid var(--border);
      font-size: 13px; color: var(--muted);
    }
    .list { margin: 8px 0 0; padding-left: 18px; }
    .list li { margin: 6px 0; }
    .research-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
    .research-card { cursor: pointer; }
    .research-card:hover { border-color: #4a5f8b; }
    .research-title { font-size: 22px; font-weight: 900; margin-bottom: 10px; }
    .table-shell {
      background: linear-gradient(180deg, var(--card), var(--card2));
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 18px;
      overflow: hidden;
    }
    .toolbar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 14px; }
    .input, select {
      background: var(--soft);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 12px 14px;
      font-size: 15px;
      min-width: 180px;
    }
    .facet-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; margin: 6px 0 16px; }
    .facet-box {
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 12px;
      background: rgba(23,33,50,.35);
      min-height: 100px;
    }
    .facet-title { font-weight: 800; margin-bottom: 10px; }
    .facet-scroll { max-height: 180px; overflow: auto; padding-right: 4px; }
    .facet-item { display: flex; align-items: center; gap: 10px; margin: 8px 0; color: var(--muted); }
    .facet-item input { transform: scale(1.05); }
    .checkbox-inline { display: flex; align-items: center; gap: 10px; color: var(--text); }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td {
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid #1f2940;
      vertical-align: top;
      white-space: nowrap;
    }
    td.wrap, th.wrap { white-space: normal; }
    th { color: var(--text); position: sticky; top: 0; background: #0f1726; z-index: 1; }
    td { color: var(--muted); }
    .table-wrap { overflow: auto; max-height: 70vh; border-radius: 16px; }
    .backrow { margin-bottom: 14px; }
    .subhead { font-size: 13px; color: var(--muted); margin-top: -4px; margin-bottom: 8px; }
    @media (max-width: 700px) {
      h1 { font-size: 54px; }
      .wrap { padding: 18px 16px 38px; }
      .cards { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <h1>HR Picks App</h1>
        <div id="meta" class="meta">Loading...</div>
      </div>
      <div>
        <button class="btn" id="reloadBtn">Reload App</button>
      </div>
    </div>

    <div class="tabs">
      <button class="tab active" data-view="final">Final Card</button>
      <button class="tab" data-view="games">Games</button>
      <button class="tab" data-view="research">Research</button>
      <button class="tab" data-view="info">Info</button>
      <button class="tab" data-view="results">Results</button>
    </div>

    <section id="view-final"></section>
    <section id="view-games" class="hidden"></section>
    <section id="view-research" class="hidden"></section>
    <section id="view-info" class="hidden"></section>
    <section id="view-results" class="hidden"></section>
  </div>

<script>
let APP_DATA = null;
let currentView = "final";
let CURRENT_RESEARCH_KEY = null;
let CURRENT_RESEARCH_ROWS = [];
let CURRENT_SORT_COLUMN = "";
let CURRENT_SORT_DIR = "asc";

function esc(v) {
  if (v === null || v === undefined) return "";
  return String(v)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fmt(v) {
  if (v === null || v === undefined || v === "") return "—";
  return typeof v === "number" ? String(v) : String(v);
}

function titleize(key) {
  return String(key || "").replaceAll("_", " ").replace(/\b\w/g, m => m.toUpperCase());
}

function parseEtTimeToMinutes(t) {
  if (!t) return 99999;
  const s = String(t).toUpperCase().replace("ET", "").trim();
  const m = s.match(/(\d{1,2}):(\d{2})\s*(AM|PM)/);
  if (!m) return 99999;
  let hh = parseInt(m[1], 10);
  const mm = parseInt(m[2], 10);
  const ap = m[3];
  if (ap === "PM" && hh !== 12) hh += 12;
  if (ap === "AM" && hh === 12) hh = 0;
  return hh * 60 + mm;
}

function parseSortableDate(value) {
  const raw = String(value ?? "").trim();
  if (!raw || raw === "—") return null;

  // Only treat true date-looking strings as dates.
  // This avoids decimal values like "2.5" or "1.04" being misread by Date.parse()
  // and breaking numeric sorts in drought tables.
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    const ts = Date.parse(raw + "T00:00:00Z");
    return Number.isNaN(ts) ? null : ts;
  }

  if (/^\d{1,2}\/\d{1,2}\/\d{2,4}$/.test(raw)) {
    const parsed = Date.parse(raw);
    return Number.isNaN(parsed) ? null : parsed;
  }

  if (/^[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4}$/.test(raw)) {
    const parsed = Date.parse(raw);
    return Number.isNaN(parsed) ? null : parsed;
  }

  return null;
}

function compareMixedValues(a, b, dir = "asc") {
  const av = a === null || a === undefined ? "" : String(a).trim();
  const bv = b === null || b === undefined ? "" : String(b).trim();

  const ad = parseSortableDate(av);
  const bd = parseSortableDate(bv);
  if (ad !== null || bd !== null) {
    if (ad === null && bd === null) return 0;
    if (ad === null) return 1;
    if (bd === null) return -1;
    return dir === "asc" ? ad - bd : bd - ad;
  }

  const an = parseFloat(av);
  const bn = parseFloat(bv);
  const aNum = !Number.isNaN(an) && av !== "" && av !== "—";
  const bNum = !Number.isNaN(bn) && bv !== "" && bv !== "—";
  if (aNum || bNum) {
    if (!aNum && !bNum) return 0;
    if (!aNum) return 1;
    if (!bNum) return -1;
    return dir === "asc" ? an - bn : bn - an;
  }

  if (!av && !bv) return 0;
  if (!av || av === "—") return 1;
  if (!bv || bv === "—") return -1;

  return dir === "asc"
    ? av.localeCompare(bv, undefined, { numeric: true, sensitivity: "base" })
    : bv.localeCompare(av, undefined, { numeric: true, sensitivity: "base" });
}


function isStrictNumericColumn(col) {
  const numericCols = new Set([
    "avg_games_between_hrs",
    "avg_games_between_hits",
    "current_games_without_hr",
    "current_games_without_hit",
    "longest_games_without_hr",
    "longestHitDrought",
    "homeRuns",
    "totalHits",
    "gamesPlayed",
    "batting_order_slot",
    "HR_score",
    "Hit_score",
    "edge_vs_opponent",
    "projected_k_floor",
    "projected_k_mid",
    "projected_k_ceiling",
    "max_playable_k_line"
  ]);
  return numericCols.has(String(col || ""));
}

function compareColumnValues(a, b, col, dir = "asc") {
  if (isStrictNumericColumn(col)) {
    const avRaw = a === null || a === undefined ? "" : String(a).trim();
    const bvRaw = b === null || b === undefined ? "" : String(b).trim();

    const aBlank = avRaw === "" || avRaw === "—";
    const bBlank = bvRaw === "" || bvRaw === "—";
    if (aBlank && bBlank) return 0;
    if (aBlank) return 1;
    if (bBlank) return -1;

    const an = Number(avRaw);
    const bn = Number(bvRaw);
    const aNum = !Number.isNaN(an);
    const bNum = !Number.isNaN(bn);

    if (aNum && bNum) {
      return dir === "asc" ? an - bn : bn - an;
    }
    if (aNum && !bNum) return -1;
    if (!aNum && bNum) return 1;
  }

  return compareMixedValues(a, b, dir);
}


function buildGameTimeLookup() {
  const map = {};
  const games = APP_DATA?.games || [];
  games.forEach(g => {
    const gameName = g?.game;
    if (gameName) {
      map[gameName] = g.game_time_et || g.start_time_et || g.startTimeEt || g.game_datetime_utc || null;
    }
  });
  const rankings = APP_DATA?.research?.game_rankings || [];
  rankings.forEach(r => {
    const gameName = r?.game;
    if (gameName && !map[gameName]) {
      map[gameName] = r.game_time_et || r.start_time_et || r.startTimeEt || r.game_datetime_utc || null;
    }
  });
  return map;
}

function setMeta() {
  const date = APP_DATA?.date || "—";
  const lu = APP_DATA?._meta?.last_updated_display || "—";
  document.getElementById("meta").textContent = "Date: " + date + " • Last Updated: " + lu;
}

async function loadData() {
  const res = await fetch("/latest?t=" + Date.now(), { cache: "no-store" });
  APP_DATA = await res.json();
  renderAll();
}

function finalCardRows() {
  const plays = APP_DATA?.final_card?.plays;
  if (Array.isArray(plays) && plays.length) return plays;
  const fallback = APP_DATA?.research?.final_card;
  return Array.isArray(fallback) ? fallback : [];
}

function buildModelInsight(p) {
  if (p?.model_insight) return String(p.model_insight);
  const betType = String(p?.bet_type || "");
  const pickText = String(p?.pick || p?.playerName || "");
  const reason = String(p?.why_it_made_the_card || p?.reason || "");
  const lower = reason.toLowerCase();

  if (betType === "No Plays" || pickText.toLowerCase().includes("no final card plays qualified")) {
    return "Model did not find enough edge after today's filters, matchup checks, and pregame rules.";
  }

  if (betType === "Moneyline") {
    if (lower.includes("strong sp") && lower.includes("short leash")) {
      return "Model sees a starting pitching stability edge here, with the opponent carrying early-exit risk that can force more bullpen exposure.";
    }
    if (lower.includes("strong sp")) {
      return "Model is leaning on the starting pitching advantage and expected game control in this matchup.";
    }
    if (lower.includes("edge")) {
      return "Model shows a meaningful game-level edge based on matchup strength, pitching context, and overall team situation.";
    }
    return "Model sees this team as the stronger side today based on the full matchup profile.";
  }

  if (betType === "1+ Hit") {
    if (lower.includes("short leash")) {
      return "Model likes the hitter's contact opportunity here, especially with a chance to face weaker bullpen arms if the starter exits early.";
    }
    if (lower.includes("slot 1") || lower.includes("slot 2") || lower.includes("slot 3")) {
      return "Model likes the hitter's lineup position and projected plate appearance volume in this matchup.";
    }
    if (lower.includes("park favorable")) {
      return "Model sees a favorable hitting environment here along with enough underlying hit probability to make the card.";
    }
    return "Model sees enough contact probability, matchup support, and opportunity volume to back this hitter for a hit.";
  }

  if (betType === "HR") {
    if (lower.includes("park favorable")) {
      return "Model sees home run upside from the power profile plus a favorable hitting environment, but this remains a higher-variance play.";
    }
    if (lower.includes("short leash")) {
      return "Model sees power upside here, with extra appeal if the starter exits early and the hitter gets bullpen exposure.";
    }
    return "Model sees enough power, matchup, and upside context to justify a smaller-stake HR shot.";
  }

  if (betType === "K Prop") {
    if (lower.includes("projected") && lower.includes("over up to")) {
      return "Model projects strikeouts above the listed number and sees enough matchup support to justify the over.";
    }
    if (lower.includes("k upside")) {
      return "Model likes the strikeout setup here based on the opponent profile and the pitcher's swing-and-miss potential.";
    }
    return "Model sees enough strikeout potential versus the line to put this prop on the card.";
  }

  return "Model found enough edge and supporting context for this pick to make the final card.";
}

function renderFinal() {
  const mount = document.getElementById("view-final");
  const plays = finalCardRows();
  if (!plays.length) {
    mount.innerHTML = '<div class="card"><h2>No final card available.</h2></div>';
    return;
  }
  mount.innerHTML = '<div class="cards">' + plays.map(p => {
    const insight = buildModelInsight(p);
    return `
    <div class="card">
      <div class="pill">${esc(fmt(p.slot || p.play_type || p.section || "Play"))}</div>
      <h2>${esc(fmt(p.pick || p.playerName || "Play"))}</h2>
      <div class="line"><span class="label">Bet Type:</span> ${esc(fmt(p.bet_type))}</div>
      <div class="line"><span class="label">Team:</span> ${esc(fmt(p.team || p.teamName))}</div>
      <div class="line"><span class="label">Opponent:</span> ${esc(fmt(p.opponent || p.opponentTeam))}</div>
      <div class="line"><span class="label">Confidence:</span> ${esc(fmt(p.confidence))}</div>
      <div class="kicker">${esc(fmt(p.why_it_made_the_card || p.reason))}</div>
      <div class="line"><span class="label">Model Insight:</span> ${esc(fmt(insight))}</div>
      <div class="muted">Source: ${esc(fmt(p.source_tab))}</div>
    </div>`;
  }).join("") + "</div>";
}

function normalizedGames() {
  const rawGames = Array.isArray(APP_DATA?.games) ? APP_DATA.games.slice() : [];
  const timeMap = buildGameTimeLookup();
  return rawGames.map(g => {
    const time = g.game_time_et || g.start_time_et || g.startTimeEt || timeMap[g.game] || null;
    return { ...g, _sortTime: parseEtTimeToMinutes(time), _displayTime: time || "not available yet" };
  }).sort((a, b) => a._sortTime - b._sortTime || String(a.game || "").localeCompare(String(b.game || "")));
}

function renderGames() {
  const mount = document.getElementById("view-games");
  const games = normalizedGames();
  if (!games.length) {
    mount.innerHTML = '<div class="card"><h2>No game cards available.</h2></div>';
    return;
  }

  mount.innerHTML = '<div class="cards">' + games.map(g => {
    const venueHtml = g.venue ? `<p class="line"><span class="label">Venue:</span> ${esc(g.venue)}</p>` : "";
    const hits = (g.top_hit_picks || []).map(x => `<li>${esc(x.playerName)} (${esc(x.teamName)})</li>`).join("") || "<li>—</li>";
    const hrs = (g.top_hr_picks || []).map(x => `<li>${esc(x.playerName)} (${esc(x.teamName)})</li>`).join("") || "<li>—</li>";
    const kp = g.top_k_pick
      ? `${esc(fmt(g.top_k_pick.pitcherName))} (${esc(fmt(g.top_k_pick.teamName))}) — ${esc(fmt(g.top_k_pick.recommended_k_action))}`
      : "—";
    const ml = g.ml_lean || {};
    const mlPlay = `${esc(fmt(ml.team))} (edge ${esc(fmt(ml.edge_vs_opponent))})`;
    return `
      <div class="card">
        <h2>${esc(fmt(g.game))}</h2>
        <p class="line"><span class="label">Start Time:</span> ${esc(g._displayTime)}</p>
        ${venueHtml}
        <p class="line"><span class="label">ML Lean:</span> ${mlPlay}</p>
        <p class="muted">${esc(fmt(ml.recommended_play))}</p>
        <h2 style="font-size:20px;margin-top:18px;">Top Hit Picks</h2>
        <ul class="list">${hits}</ul>
        <h2 style="font-size:20px;margin-top:18px;">Top HR Picks</h2>
        <ul class="list">${hrs}</ul>
        <h2 style="font-size:20px;margin-top:18px;">Top K Pick</h2>
        <p class="line">${kp}</p>
      </div>
    `;
  }).join("") + '</div>';
}

function visibleResearchEntries() {
  const research = APP_DATA?.research || {};
  const hide = new Set(["final_card"]);
  return Object.entries(research).filter(([k, v]) => Array.isArray(v) && !hide.has(k));
}

function renderResearchHome() {
  const mount = document.getElementById("view-research");
  const entries = visibleResearchEntries();
  if (!entries.length) {
    mount.innerHTML = '<div class="card"><h2>No research tables available.</h2></div>';
    return;
  }
  mount.innerHTML = '<div class="research-grid">' + entries.map(([k, rows]) => `
    <div class="card research-card" data-key="${esc(k)}">
      <div class="research-title">${esc(titleize(k))}</div>
      <div class="muted">${rows.length} rows</div>
    </div>
  `).join("") + '</div>';

  mount.querySelectorAll(".research-card").forEach(el => {
    el.addEventListener("click", () => openResearchTable(el.dataset.key));
  });
}

function uniqueValues(rows, key) {
  const set = new Set();
  rows.forEach(r => {
    const v = r[key];
    if (v !== null && v !== undefined && String(v).trim() !== "") set.add(String(v));
  });
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

function buildFacetBox(label, key, values) {
  if (!values.length) return "";
  const checks = values.map(v => `
    <label class="facet-item">
      <input type="checkbox" class="facet-check" data-key="${esc(key)}" value="${esc(v)}">
      <span>${esc(v)}</span>
    </label>
  `).join("");
  return `
    <div class="facet-box">
      <div class="facet-title">${esc(label)}</div>
      <div class="facet-scroll">${checks}</div>
    </div>
  `;
}

function openResearchTable(key) {
  CURRENT_RESEARCH_KEY = key;
  CURRENT_RESEARCH_ROWS = APP_DATA?.research?.[key] || [];

  const rows = CURRENT_RESEARCH_ROWS;
  const mount = document.getElementById("view-research");
  const columns = rows.length ? Object.keys(rows[0]) : [];
  const options = columns.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join("");

  const facets = [];
  const facetColumns = [
    ["Teams", "teamName"],
    ["Status", "status"],
    ["Park", "park_favorability"],
    ["Opponent Pitcher Type", "opponent_pitcher_pick_type"],
    ["Lineup Status", "lineup_status"]
  ];
  facetColumns.forEach(([label, keyName]) => {
    if (columns.includes(keyName)) {
      facets.push(buildFacetBox(label, keyName, uniqueValues(rows, keyName)));
    }
  });

  const numericFilters = [];
  if (columns.includes("avg_games_between_hrs")) {
    numericFilters.push('<input id="minAvgInput" class="input" placeholder="Min avg drought" oninput="filterResearchTable()">');
  }
  if (columns.includes("current_games_without_hr")) {
    numericFilters.push('<input id="minCurrentInput" class="input" placeholder="Min games since HR" oninput="filterResearchTable()">');
  }

  const quickButtons = [];
  if (columns.includes("last_hr_date")) {
    quickButtons.push('<button class="btn secondary" id="hrTodayBtn">HR Today</button>');
  }

  mount.innerHTML = `
    <div class="backrow">
      <button class="btn secondary" id="backBtn">← Back</button>
    </div>
    <div class="table-shell">
      <h2 style="margin-top:0;">${esc(titleize(key))}</h2>
      <div class="subhead">Search + filters are active for this table.</div>
      <div class="toolbar">
        <input id="searchBox" class="input" placeholder="Search this table" oninput="filterResearchTable()">
        <select id="columnSelect" onchange="filterResearchTable()">
          <option value="">All columns</option>
          ${options}
        </select>
        <select id="sortSelect" onchange="filterResearchTable()">
          <option value="">Default order</option>
          <option value="asc">A → Z</option>
          <option value="desc">Z → A</option>
        </select>
        <label class="checkbox-inline">
          <input type="checkbox" id="overdueOnly" onchange="filterResearchTable()">
          <span>Overdue only</span>
        </label>
        ${numericFilters.join("")}
        ${quickButtons.join("")}
        <button class="btn secondary" id="clearFiltersBtn">Clear Filters</button>
      </div>
      ${facets.length ? `<div class="facet-grid">${facets.join("")}</div>` : ""}
      <div class="table-wrap">
        <table id="researchTable">
          <thead><tr>${columns.map(c => `<th data-col="${esc(c)}" class="sortable ${String(c).length > 18 ? 'wrap' : ''}">${esc(c)}</th>`).join("")}</tr></thead>
          <tbody>
            ${rows.map(r => `<tr>${columns.map(c => `<td class="${String(c).length > 18 ? 'wrap' : ''}">${esc(fmt(r[c]))}</td>`).join("")}</tr>`).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;

  document.getElementById("backBtn").addEventListener("click", renderResearchHome);
  const clearBtn = document.getElementById("clearFiltersBtn");
  clearBtn.addEventListener("click", clearResearchFilters);
  const hrTodayBtn = document.getElementById("hrTodayBtn");
  if (hrTodayBtn) {
    hrTodayBtn.addEventListener("click", applyHrTodayQuickFilter);
  }
  mount.querySelectorAll(".facet-check").forEach(el => {
    el.addEventListener("change", filterResearchTable);
  });
  mount.querySelectorAll("thead th.sortable").forEach(th => {
    th.style.cursor = "pointer";
    th.addEventListener("click", () => {
      const col = th.dataset.col || "";
      if (CURRENT_SORT_COLUMN === col) {
        CURRENT_SORT_DIR = CURRENT_SORT_DIR === "asc" ? "desc" : "asc";
      } else {
        CURRENT_SORT_COLUMN = col;
        CURRENT_SORT_DIR = col.toLowerCase().includes("date") ? "desc" : "asc";
      }
      filterResearchTable();
    });
  });

  filterResearchTable();
}

function applyHrTodayQuickFilter() {
  const search = document.getElementById("searchBox");
  const col = document.getElementById("columnSelect");
  if (search) search.value = APP_DATA?.date || "";
  if (col) col.value = "last_hr_date";
  filterResearchTable();
}

function clearResearchFilters() {
  const search = document.getElementById("searchBox");
  const col = document.getElementById("columnSelect");
  const overdue = document.getElementById("overdueOnly");
  const sortSel = document.getElementById("sortSelect");
  const minAvg = document.getElementById("minAvgInput");
  const minCurrent = document.getElementById("minCurrentInput");

  if (search) search.value = "";
  if (col) col.value = "";
  if (overdue) overdue.checked = false;
  if (sortSel) sortSel.value = "";
  if (minAvg) minAvg.value = "";
  if (minCurrent) minCurrent.value = "";
  document.querySelectorAll(".facet-check").forEach(c => c.checked = false);
  CURRENT_SORT_COLUMN = "";
  CURRENT_SORT_DIR = "asc";
  filterResearchTable();
}

function selectedFacetMap() {
  const map = {};
  document.querySelectorAll(".facet-check:checked").forEach(el => {
    const key = el.dataset.key;
    map[key] = map[key] || new Set();
    map[key].add(String(el.value));
  });
  return map;
}

function filterResearchTable() {
  const search = (document.getElementById("searchBox")?.value || "").toLowerCase();
  const column = document.getElementById("columnSelect")?.value || "";
  const overdueOnly = !!document.getElementById("overdueOnly")?.checked;
  const minAvg = parseFloat(document.getElementById("minAvgInput")?.value || "");
  const minCurrent = parseFloat(document.getElementById("minCurrentInput")?.value || "");
  const facetMap = selectedFacetMap();
  const sortValue = document.getElementById("sortSelect")?.value || "";

  const table = document.getElementById("researchTable");
  if (!table) return;

  const headers = Array.from(table.querySelectorAll("thead th")).map(th => th.dataset.col || th.textContent || "");
  const tbody = table.querySelector("tbody");
  if (!tbody) return;

  let rows = Array.isArray(CURRENT_RESEARCH_ROWS) ? [...CURRENT_RESEARCH_ROWS] : [];

  rows = rows.filter(r => {
    const getVal = (key) => String(r?.[key] ?? "");
    const headerVals = headers.map(h => getVal(h));
    const lowerHeaderVals = headerVals.map(v => v.toLowerCase());

    if (search) {
      if (column) {
        const hay = getVal(column).toLowerCase();
        if (!hay.includes(search)) return false;
      } else {
        if (!lowerHeaderVals.join(" | ").includes(search)) return false;
      }
    }

    if (overdueOnly) {
      const statusVal = getVal("status").toLowerCase();
      if (!statusVal.includes("overdue")) return false;
    }

    if (!Number.isNaN(minAvg)) {
      const avgKey = headers.includes("avg_games_between_hrs") ? "avg_games_between_hrs" : (headers.includes("avg_games_between_hits") ? "avg_games_between_hits" : "");
      if (avgKey) {
        const num = parseFloat(getVal(avgKey));
        if (Number.isNaN(num) || num < minAvg) return false;
      }
    }

    if (!Number.isNaN(minCurrent)) {
      const curKey = headers.includes("current_games_without_hr") ? "current_games_without_hr" : (headers.includes("current_games_without_hit") ? "current_games_without_hit" : "");
      if (curKey) {
        const num = parseFloat(getVal(curKey));
        if (Number.isNaN(num) || num < minCurrent) return false;
      }
    }

    for (const [key, valSet] of Object.entries(facetMap)) {
      const val = getVal(key);
      if (!valSet.has(String(val))) return false;
    }

    return true;
  });

  if (CURRENT_SORT_COLUMN) {
    rows.sort((a, b) => compareColumnValues(a?.[CURRENT_SORT_COLUMN], b?.[CURRENT_SORT_COLUMN], CURRENT_SORT_COLUMN, CURRENT_SORT_DIR));
  } else if (sortValue) {
    const sortKey = headers.includes("playerName") ? "playerName" : headers[0];
    rows.sort((a, b) => compareColumnValues(a?.[sortKey], b?.[sortKey], sortKey, sortValue));
  }

  tbody.innerHTML = rows.map(r => `<tr>${headers.map(c => `<td class="${String(c).length > 18 ? 'wrap' : ''}">${esc(fmt(r[c]))}</td>`).join("")}</tr>`).join("");

  document.querySelectorAll("thead th.sortable").forEach(th => {
    const col = th.dataset.col || "";
    const base = col;
    if (CURRENT_SORT_COLUMN === col) {
      th.textContent = `${base} ${CURRENT_SORT_DIR === 'asc' ? '↑' : '↓'}`;
    } else {
      th.textContent = base;
    }
  });
}



function renderInfo() {
  const mount = document.getElementById("view-info");
  const info = APP_DATA?.info || {};
  const terms = Array.isArray(info.terms) ? info.terms : [];
  const how = Array.isArray(info.how_to_use) ? info.how_to_use : [];
  const cardLogic = Array.isArray(info.card_logic) ? info.card_logic : [];
  const unitStrategy = Array.isArray(info.unit_strategy) ? info.unit_strategy : [];
  mount.innerHTML = `
    <div class="cards">
      <div class="card">
        <h2>What This App Does</h2>
        <div class="line">${esc(fmt(info.purpose || "This app ranks MLB betting edges across hits, HRs, Ks, and moneyline spots."))}</div>
      </div>
      <div class="card">
        <h2>What To Look For</h2>
        <ul class="list">${how.map(x => `<li>${esc(x)}</li>`).join("")}</ul>
      </div>
    </div>
    <div class="cards" style="margin-top:18px;">
      <div class="card">
        <h2>How To Read The Final Card</h2>
        <ul class="list">${cardLogic.map(x => `<li><strong>${esc(fmt(x.label))}:</strong> ${esc(fmt(x.meaning))}</li>`).join("")}</ul>
      </div>
      <div class="card">
        <h2>Suggested Unit Strategy</h2>
        <ul class="list">${unitStrategy.map(x => `<li>${esc(x)}</li>`).join("")}</ul>
      </div>
    </div>
    <div class="table-shell" style="margin-top:18px;">
      <h2 style="margin-top:0;">Key Terms</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Term</th><th class="wrap">Meaning</th></tr></thead>
          <tbody>${terms.map(t => `<tr><td>${esc(fmt(t.term))}</td><td class="wrap">${esc(fmt(t.meaning))}</td></tr>`).join("")}</tbody>
        </table>
      </div>
    </div>
  `;
}

function renderResults() {
  const mount = document.getElementById("view-results");
  const results = APP_DATA?.results || {};
  const overall = results.overall || {};
  const byType = Array.isArray(results.by_bet_type) ? results.by_bet_type : [];
  const byConf = Array.isArray(results.by_confidence) ? results.by_confidence : [];
  const recent = Array.isArray(results.recent_results) ? results.recent_results : [];
  mount.innerHTML = `
    <div class="cards">
      <div class="card"><h2>Overall Performance</h2>
        <div class="line"><span class="label">Graded Picks:</span> ${esc(fmt(overall.graded_picks))}</div>
        <div class="line"><span class="label">Wins:</span> ${esc(fmt(overall.wins))}</div>
        <div class="line"><span class="label">Losses:</span> ${esc(fmt(overall.losses))}</div>
        <div class="line"><span class="label">Win Rate:</span> ${overall.win_rate !== undefined && overall.win_rate !== null ? esc((overall.win_rate * 100).toFixed(1) + '%') : '—'}</div>
      </div>
      <div class="card"><h2>What This Is For</h2>
        <div class="line">This tab tracks how saved picks perform over time so you can see what the model does well and where it needs tightening.</div>
      </div>
    </div>
    <div class="cards" style="margin-top:18px;">
      <div class="table-shell">
        <h2 style="margin-top:0;">By Bet Type</h2>
        <div class="table-wrap"><table><thead><tr><th>Bet Type</th><th>Graded</th><th>Wins</th><th>Losses</th><th>Win Rate</th></tr></thead><tbody>
        ${byType.map(r => `<tr><td>${esc(fmt(r.bet_type))}</td><td>${esc(fmt(r.graded_picks))}</td><td>${esc(fmt(r.wins))}</td><td>${esc(fmt(r.losses))}</td><td>${r.win_rate !== undefined && r.win_rate !== null ? esc((Number(r.win_rate) * 100).toFixed(1) + '%') : '—'}</td></tr>`).join("") || '<tr><td colspan="5">No graded results yet.</td></tr>'}
        </tbody></table></div>
      </div>
      <div class="table-shell">
        <h2 style="margin-top:0;">By Confidence</h2>
        <div class="table-wrap"><table><thead><tr><th>Confidence</th><th>Graded</th><th>Wins</th><th>Losses</th><th>Win Rate</th></tr></thead><tbody>
        ${byConf.map(r => `<tr><td>${esc(fmt(r.confidence))}</td><td>${esc(fmt(r.graded_picks))}</td><td>${esc(fmt(r.wins))}</td><td>${esc(fmt(r.losses))}</td><td>${r.win_rate !== undefined && r.win_rate !== null ? esc((Number(r.win_rate) * 100).toFixed(1) + '%') : '—'}</td></tr>`).join("") || '<tr><td colspan="5">No confidence-level results yet.</td></tr>'}
        </tbody></table></div>
      </div>
    </div>
    <div class="table-shell" style="margin-top:18px;">
      <h2 style="margin-top:0;">Recent Graded Picks</h2>
      <div class="table-wrap"><table><thead><tr><th>Date</th><th>Bet Type</th><th>Pick</th><th>Team</th><th>Opponent</th><th>Confidence</th><th>Result</th><th class="wrap">Detail</th></tr></thead><tbody>
      ${recent.map(r => `<tr><td>${esc(fmt(r.target_date))}</td><td>${esc(fmt(r.bet_type))}</td><td>${esc(fmt(r.pick))}</td><td>${esc(fmt(r.team))}</td><td>${esc(fmt(r.opponent))}</td><td>${esc(fmt(r.confidence))}</td><td>${esc(fmt(r.result_status))}</td><td class="wrap">${esc(fmt(r.result_detail))}</td></tr>`).join("") || '<tr><td colspan="8">No graded picks yet.</td></tr>'}
      </tbody></table></div>
    </div>
  `;
}

function renderAll() {
  setMeta();
  renderFinal();
  renderGames();
  renderResearchHome();
  renderInfo();
  renderResults();
  switchView(currentView);
}

function switchView(view) {
  currentView = view;
  document.getElementById("view-final").classList.toggle("hidden", view !== "final");
  document.getElementById("view-games").classList.toggle("hidden", view !== "games");
  document.getElementById("view-research").classList.toggle("hidden", view !== "research");
  document.getElementById("view-info").classList.toggle("hidden", view !== "info");
  document.getElementById("view-results").classList.toggle("hidden", view !== "results");
  document.querySelectorAll(".tab").forEach(btn => btn.classList.toggle("active", btn.dataset.view === view));
}

document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

document.getElementById("reloadBtn").addEventListener("click", async () => {
  const btn = document.getElementById("reloadBtn");
  const old = btn.textContent;
  btn.textContent = "Running model...";
  btn.disabled = true;
  try {
    const res = await fetch("/refresh-data?t=" + Date.now(), { cache: "no-store" });
    const payload = await res.json().catch(() => ({}));
    if (payload.status === "busy") {
      alert(payload.message || "Refresh already in progress. Please wait a few minutes.");
      btn.textContent = "Loading app...";
      await loadData();
      return;
    }
    if (!res.ok || payload.status === "error") {
      throw new Error(payload.message || `Refresh failed: ${res.status}`);
    }
    btn.textContent = "Loading app...";
    await loadData();
  } catch (err) {
    console.error(err);
    alert("Refresh failed. Check Render logs for details. " + (err?.message || err));
  } finally {
    btn.textContent = old;
    btn.disabled = false;
  }
});

loadData();
</script>
</body>
</html>
"""
    return HTMLResponse(html)
