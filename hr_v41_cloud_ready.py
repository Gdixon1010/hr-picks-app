import os
import json
import re
from pathlib import Path
from datetime import datetime

import requests

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


def _matching_v40_json(target_date: str) -> Path:
    pattern = f"HR_Hit_Drought_v40_appdata-*_{target_date}_*.json"
    files = sorted(
        OUTPUT_DIR.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(f"No v40 appdata JSON was created for target_date={target_date} in {OUTPUT_DIR}.")
    return files[0]


def _write_v41_json(data: dict, season: int, target_date: str) -> Path:
    now_stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = OUTPUT_DIR / (
        f"HR_Hit_Drought_v41_appdata-{season}_{target_date}_{target_date}_{now_stamp}.json"
    )
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return out


def _get_json(url: str, params=None):
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _norm(s) -> str:
    if s is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def _is_final_game(game: dict) -> bool:
    status = (game.get("status") or {})
    state = str(status.get("detailedState") or status.get("abstractGameState") or "").lower()
    coded = str(status.get("codedGameState") or "").upper()
    return "final" in state or coded in {"F", "O"}


def _find_game(schedule: dict, team: str, opponent: str):
    team_n = _norm(team)
    opp_n = _norm(opponent)
    for d in schedule.get("dates", []) or []:
        for g in d.get("games", []) or []:
            teams = g.get("teams") or {}
            home = ((teams.get("home") or {}).get("team") or {}).get("name")
            away = ((teams.get("away") or {}).get("team") or {}).get("name")
            names = {_norm(home), _norm(away)}
            if team_n in names and opp_n in names:
                return g
    return None


def _score_for_team(game: dict, team: str):
    teams = game.get("teams") or {}
    team_n = _norm(team)
    for side in ("home", "away"):
        block = teams.get(side) or {}
        name = ((block.get("team") or {}).get("name"))
        if _norm(name) == team_n:
            return block.get("score")
    return None


def _line_from_why(text: str):
    if not text:
        return None
    m = re.search(r"(?:up to|at|max line)\s*(\d+(?:\.\d+)?)", str(text), re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"over\s*(\d+(?:\.\d+)?)", str(text), re.I)
    if m:
        return float(m.group(1))
    return None


def _load_boxscore(game_pk):
    return _get_json(f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore")


def _find_box_player(box: dict, player_name: str, team_name: str | None = None):
    target = _norm(player_name)
    target_team = _norm(team_name) if team_name else ""
    teams = (box.get("teams") or {})
    for side in ("home", "away"):
        block = teams.get(side) or {}
        bteam = ((block.get("team") or {}).get("name"))
        if target_team and _norm(bteam) != target_team:
            continue
        players = block.get("players") or {}
        for p in players.values():
            full = ((p.get("person") or {}).get("fullName"))
            if _norm(full) == target:
                return p
    for side in ("home", "away"):
        block = teams.get(side) or {}
        players = block.get("players") or {}
        for p in players.values():
            full = ((p.get("person") or {}).get("fullName"))
            if _norm(full) == target:
                return p
    return None


def _stat_int(player: dict, group: str, key: str):
    try:
        return int(((player.get("stats") or {}).get(group) or {}).get(key) or 0)
    except Exception:
        return 0


def _grade_one_pick(play: dict, game: dict):
    bet_type = str(play.get("bet_type") or "")
    pick = str(play.get("pick") or "")
    team = str(play.get("team") or "")
    opponent = str(play.get("opponent") or "")
    why = str(play.get("why_it_made_the_card") or "")

    base = {
        "target_date": None,
        "bet_type": bet_type,
        "pick": pick,
        "team": team,
        "opponent": opponent,
        "confidence": play.get("confidence"),
        "result_status": "Pending",
        "result_detail": "Game not final yet.",
    }

    if not game:
        base["result_detail"] = "Could not match pick to scheduled game."
        return base

    if not _is_final_game(game):
        base["result_detail"] = "Game not final yet."
        return base

    game_pk = game.get("gamePk")

    if bet_type == "Moneyline":
        team_score = _score_for_team(game, team)
        opp_score = _score_for_team(game, opponent)
        if team_score is None or opp_score is None:
            base["result_status"] = "Pending"
            base["result_detail"] = "Final score unavailable."
        elif team_score > opp_score:
            base["result_status"] = "Win"
            base["result_detail"] = f"{team} won {team_score}-{opp_score}."
        else:
            base["result_status"] = "Loss"
            base["result_detail"] = f"{team} lost {team_score}-{opp_score}."
        return base

    if not game_pk:
        base["result_detail"] = "Missing gamePk for boxscore."
        return base

    box = _load_boxscore(game_pk)
    player = _find_box_player(box, pick, team)

    if not player:
        base["result_status"] = "Pending"
        base["result_detail"] = "Could not find player in final boxscore."
        return base

    if bet_type == "K Prop":
        line = _line_from_why(why)
        ks = _stat_int(player, "pitching", "strikeOuts")
        if line is None:
            base["result_status"] = "Pending"
            base["result_detail"] = f"Pitcher had {ks} Ks, but K line could not be parsed."
        elif ks > line:
            base["result_status"] = "Win"
            base["result_detail"] = f"{pick} had {ks} Ks over {line}."
        else:
            base["result_status"] = "Loss"
            base["result_detail"] = f"{pick} had {ks} Ks, not over {line}."
        return base

    if bet_type in {"1+ Hit", "Hit", "Best Hit"}:
        hits = _stat_int(player, "batting", "hits")
        if hits >= 1:
            base["result_status"] = "Win"
            base["result_detail"] = f"{pick} had {hits} hit(s)."
        else:
            base["result_status"] = "Loss"
            base["result_detail"] = f"{pick} had 0 hits."
        return base

    if bet_type in {"HR", "Home Run", "Best HR"}:
        hrs = _stat_int(player, "batting", "homeRuns")
        if hrs >= 1:
            base["result_status"] = "Win"
            base["result_detail"] = f"{pick} hit {hrs} HR(s)."
        else:
            base["result_status"] = "Loss"
            base["result_detail"] = f"{pick} hit 0 HRs."
        return base

    base["result_status"] = "Pending"
    base["result_detail"] = f"No grading rule for bet type: {bet_type}"
    return base


def _write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def grade_results(data: dict, target_date: str):
    plays = ((data.get("final_card") or {}).get("plays") or [])
    plays = [
        p for p in plays
        if str(p.get("bet_type") or "") != "No Plays"
        and not str(p.get("pick") or "").lower().startswith("no final card")
    ]

    if not plays:
        summary = {
            "overall": {"graded_picks": 0, "wins": 0, "losses": 0, "win_rate": None},
            "by_bet_type": [],
            "by_confidence": [],
            "recent_results": [],
        }
        latest = {"target_date": target_date, "graded_rows": 0, "rows": []}
        _write_json(HISTORY_DIR / "performance_summary_latest.json", summary)
        _write_json(HISTORY_DIR / "results_history_latest.json", latest)
        return {"graded_rows": 0, "rows": []}

    schedule = _get_json(
        "https://statsapi.mlb.com/api/v1/schedule",
        params={"sportId": 1, "date": target_date, "hydrate": "team,probablePitcher,venue"},
    )

    graded_rows = []
    for play in plays:
        game = _find_game(schedule, play.get("team"), play.get("opponent"))
        row = _grade_one_pick(play, game)
        row["target_date"] = target_date
        graded_rows.append(row)

    completed = [r for r in graded_rows if r.get("result_status") in {"Win", "Loss"}]
    wins = sum(1 for r in completed if r.get("result_status") == "Win")
    losses = sum(1 for r in completed if r.get("result_status") == "Loss")
    graded_count = len(completed)
    win_rate = round(wins / graded_count, 4) if graded_count else None

    def _group_summary(key):
        out = []
        groups = sorted(set(str(r.get(key) or "") for r in completed))
        for g in groups:
            sub = [r for r in completed if str(r.get(key) or "") == g]
            gw = sum(1 for r in sub if r.get("result_status") == "Win")
            gl = sum(1 for r in sub if r.get("result_status") == "Loss")
            total = gw + gl
            out.append({
                key: g,
                "graded_picks": total,
                "wins": gw,
                "losses": gl,
                "win_rate": round(gw / total, 4) if total else None,
            })
        return out

    summary = {
        "overall": {
            "graded_picks": graded_count,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
        },
        "by_bet_type": _group_summary("bet_type"),
        "by_confidence": _group_summary("confidence"),
        "recent_results": completed[-25:],
    }
    latest = {"target_date": target_date, "graded_rows": graded_count, "rows": graded_rows}

    _write_json(HISTORY_DIR / "performance_summary_latest.json", summary)
    _write_json(HISTORY_DIR / "results_history_latest.json", latest)

    try:
        with open(HISTORY_DIR / "results_history.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(latest, ensure_ascii=False) + "\n")
    except Exception:
        pass

    return latest


def main(season: int, target_date: str):
    os.environ["HR_APP_DATA_DIR"] = str(OUTPUT_DIR)

    run_v40_main(season, target_date)

    matching_v40 = _matching_v40_json(target_date)

    with open(matching_v40, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["date"] = target_date

    grade_info = grade_results(data, target_date)
    print(f"✅ results graded: {grade_info.get('graded_rows', 0)} completed pick(s)")

    v41_path = _write_v41_json(data, season, target_date)

    print(f"✅ v41 JSON created: {v41_path}")

    return {
        "status": "success",
        "message": "v41 built successfully",
        "target_date": target_date,
        "output_dir": str(OUTPUT_DIR),
        "v40_source": str(matching_v40),
        "v41_output": str(v41_path),
        "graded_rows": grade_info.get("graded_rows", 0),
    }


if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    print(main(2026, today))
