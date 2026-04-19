from pathlib import Path
import json
import datetime as dt

from hr_v40_2_json_export_ready import main as run_v40_main

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def _latest_v40_json():
    files = sorted(
        OUTPUT_DIR.glob("HR_Hit_Drought_v40_appdata-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def _load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(payload: dict, target_date: str):
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    out = OUTPUT_DIR / f"HR_Hit_Drought_v41_appdata-2026_{target_date}_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return out


def _num(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def _top_hit_candidates(research):
    refined = research.get("refined_picks", []) or []
    hits = [r for r in refined if str(r.get("category")) == "Hit Pick"]
    hits.sort(
        key=lambda r: (_num(r.get("Hit_score")), -_num(r.get("batting_order_slot"), 99)),
        reverse=True,
    )
    return hits


def _top_hr_candidates(research):
    refined = research.get("refined_picks", []) or []
    hrs = [r for r in refined if str(r.get("category")) == "HR Pick"]

    if not hrs:
        top_picks = research.get("top_picks", []) or []
        hrs = [r for r in top_picks if str(r.get("type")) == "HR"]
        for r in hrs:
            r.setdefault("category", "HR Pick")

    filtered = []
    for r in hrs:
        park = str(r.get("park_favorability") or "")
        opp = str(r.get("opponent_pitcher_pick_type") or "")
        hr_score = _num(r.get("HR_score"))
        home_runs = _num(r.get("homeRuns"), 0)
        avg_between = _num(r.get("avg_games_between_hrs"), 99)

        power_ok = (home_runs >= 3) or (avg_between <= 2.5)
        opp_ok = opp in ("Short Leash Risk", "Attack With Hitters", "Low Sample", "")
        park_ok = park in ("Favorable", "")

        if hr_score >= 5.5 and opp_ok and park_ok and power_ok:
            filtered.append(r)

    filtered.sort(
        key=lambda r: (_num(r.get("HR_score")), -_num(r.get("batting_order_slot"), 99)),
        reverse=True,
    )
    return filtered


def _top_k_pick(research):
    rows = research.get("pitcher_line_value", []) or []
    rows = [
        r for r in rows
        if str(r.get("k_value_tier")) in ("Hammer", "Strong")
        and not str(r.get("short_leash_flag") or "").startswith("Yes")
    ]
    rows.sort(
        key=lambda r: (_num(r.get("projected_k_mid")), _num(r.get("pitcher_score_adj"))),
        reverse=True,
    )
    return rows[0] if rows else None


def _top_ml_pick(research, hit_candidates, hr_candidates):
    rows = research.get("game_rankings", []) or []

    supported_teams = {r.get("teamName") for r in hit_candidates if r.get("teamName")}
    supported_teams.update({r.get("teamName") for r in hr_candidates if r.get("teamName")})

    candidates = []
    for r in rows:
        team = r.get("teamName")
        if team not in supported_teams:
            continue
        if _num(r.get("edge_vs_opponent")) < 10:
            continue
        if str(r.get("recommended_play") or "").lower().startswith("avoid"):
            continue
        if str(r.get("pitcher_pick_type") or "") not in ("Strong SP", "K Upside", "Neutral"):
            continue
        if str(r.get("opponent_pitcher_pick_type") or "") not in (
            "Short Leash Risk", "Attack With Hitters", "Low Sample", "Neutral"
        ):
            continue
        candidates.append(r)

    candidates.sort(
        key=lambda r: (_num(r.get("edge_vs_opponent")), _num(r.get("team_score"))),
        reverse=True,
    )
    return candidates[0] if candidates else None


def _build_final_card(payload):
    research = payload.get("research", {}) or {}

    hit_candidates = _top_hit_candidates(research)
    hr_candidates = _top_hr_candidates(research)
    k_pick = _top_k_pick(research)
    ml_pick = _top_ml_pick(research, hit_candidates, hr_candidates)

    rows = []
    used = set()
    team_counts = {}

    def can_use(team, limit=2):
        return team_counts.get(team, 0) < limit

    def add(slot, bet_type, pick, team, opponent, confidence, why, source):
        rows.append({
            "slot": slot,
            "bet_type": bet_type,
            "pick": pick,
            "team": team,
            "opponent": opponent,
            "confidence": confidence,
            "why_it_made_the_card": why,
            "source_tab": source,
        })
        team_counts[team] = team_counts.get(team, 0) + 1
        used.add((team, pick))

    if ml_pick:
        add(
            "Core 1",
            "Moneyline",
            f"{ml_pick['teamName']} ML",
            ml_pick["teamName"],
            ml_pick.get("opponentTeam"),
            "A",
            f"Edge {ml_pick.get('edge_vs_opponent')}; ML supported by same-team hitter/HR signal; "
            f"{ml_pick.get('pitcher_pick_type')} vs {ml_pick.get('opponent_pitcher_pick_type')}",
            "Game_Rankings",
        )

    hit_added = 0
    for r in hit_candidates:
        if hit_added >= 2:
            break
        team = r.get("teamName")
        if not can_use(team, 2) or (team, r.get("playerName")) in used:
            continue
        add(
            f"Core {len(rows)+1}",
            "1+ Hit",
            r.get("playerName"),
            team,
            r.get("opponent_pitcher_team"),
            "A",
            f"Hit_score {r.get('Hit_score')}; slot {r.get('batting_order_slot')}; "
            f"opp {r.get('opponent_pitcher_pick_type') or 'Neutral'}",
            "Refined_Picks",
        )
        hit_added += 1

    hr_added = 0
    for r in hr_candidates:
        if hr_added >= 2:
            break
        team = r.get("teamName")
        if not can_use(team, 2) or (team, r.get("playerName")) in used:
            continue
        add(
            f"Power {hr_added+1}",
            "HR",
            r.get("playerName"),
            team,
            r.get("opponent_pitcher_team"),
            "B",
            f"HR_score {r.get('HR_score')}; park {r.get('park_favorability') or 'Favorable'}; "
            f"opp {r.get('opponent_pitcher_pick_type') or 'Neutral'}",
            "Refined_Picks",
        )
        hr_added += 1

    if k_pick and can_use(k_pick.get("teamName"), 2):
        add(
            "Pitch 1",
            "K Prop",
            k_pick.get("pitcherName"),
            k_pick.get("teamName"),
            k_pick.get("opponentTeam"),
            "A" if str(k_pick.get("k_value_tier")) == "Hammer" else "B",
            f"{k_pick.get('recommended_k_action')}; projected "
            f"{k_pick.get('projected_k_floor')}-{k_pick.get('projected_k_ceiling')} Ks",
            "Pitcher_Line_Value",
        )

    payload["final_card"] = {"generated_section": "final_card", "plays": rows}
    return payload


def _build_games(payload):
    research = payload.get("research", {}) or {}
    rankings = research.get("game_rankings", []) or []
    refined = research.get("refined_picks", []) or []
    top_picks = research.get("top_picks", []) or []
    pitcher_value = research.get("pitcher_line_value", []) or []

    games = {}

    for r in rankings:
        game = r.get("game")
        if not game:
            continue
        if game not in games:
            games[game] = {
                "game": game,
                "ml_lean": None,
                "top_hit_picks": [],
                "top_hr_picks": [],
                "top_k_pick": None,
            }
        if games[game]["ml_lean"] is None or _num(r.get("edge_vs_opponent")) > _num(
            games[game]["ml_lean"].get("edge_vs_opponent")
        ):
            games[game]["ml_lean"] = {
                "team": r.get("teamName"),
                "opponent": r.get("opponentTeam"),
                "edge_vs_opponent": r.get("edge_vs_opponent"),
                "recommended_play": r.get("recommended_play"),
            }

    for game, info in games.items():
        teams = {info["ml_lean"].get("team"), info["ml_lean"].get("opponent")}

        game_hits = [
            r for r in refined
            if str(r.get("category")) == "Hit Pick" and r.get("teamName") in teams
        ]
        game_hits.sort(key=lambda r: _num(r.get("Hit_score")), reverse=True)
        if not game_hits:
            game_hits = [
                r for r in top_picks
                if str(r.get("type")) == "HIT" and r.get("teamName") in teams
            ]
            game_hits.sort(key=lambda r: _num(r.get("Hit_score")), reverse=True)

        info["top_hit_picks"] = [
            {
                "playerName": r.get("playerName"),
                "teamName": r.get("teamName"),
                "Hit_score": r.get("Hit_score"),
            }
            for r in game_hits[:2]
        ]

        game_hrs = [
            r for r in refined
            if str(r.get("category")) == "HR Pick" and r.get("teamName") in teams
        ]
        game_hrs.sort(key=lambda r: _num(r.get("HR_score")), reverse=True)
        if not game_hrs:
            game_hrs = [
                r for r in top_picks
                if str(r.get("type")) == "HR" and r.get("teamName") in teams
            ]
            game_hrs.sort(key=lambda r: _num(r.get("HR_score")), reverse=True)

        info["top_hr_picks"] = [
            {
                "playerName": r.get("playerName"),
                "teamName": r.get("teamName"),
                "HR_score": r.get("HR_score"),
            }
            for r in game_hrs[:2]
        ]

        team_pitchers = [r for r in pitcher_value if r.get("teamName") in teams]
        team_pitchers.sort(key=lambda r: _num(r.get("projected_k_mid")), reverse=True)
        if team_pitchers:
            r = team_pitchers[0]
            info["top_k_pick"] = {
                "pitcherName": r.get("pitcherName"),
                "teamName": r.get("teamName"),
                "recommended_k_action": r.get("recommended_k_action"),
                "projected_k_floor": r.get("projected_k_floor"),
                "projected_k_ceiling": r.get("projected_k_ceiling"),
                "max_playable_k_line": r.get("max_playable_k_line"),
            }

    payload["games"] = list(games.values())
    return payload


def main(season: int = 2026, target_date: str | None = None):
    if target_date is None:
        target_date = dt.date.today().strftime("%Y-%m-%d")

    run_v40_main(season, target_date)

    latest = _latest_v40_json()
    if not latest:
        raise FileNotFoundError("No v40 appdata JSON was created.")

    payload = _load_json(latest)
    payload = _build_final_card(payload)
    payload = _build_games(payload)

    out = _save_json(payload, target_date)
    print(f"✅ v41 JSON created: {out}")
    return payload


if __name__ == "__main__":
    main()
