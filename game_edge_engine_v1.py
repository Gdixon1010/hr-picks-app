"""
Game Edge Engine V1
Drop-in helper functions for HR Picks App.

Purpose:
- Convert Game Rankings rows into projected win %
- Add parlay grade
- Add volatility label
- Add model edge vs Vegas implied % when odds are available

This is a helper module/patch, not a full replacement for hr_v40_2_json_export_ready.py.
"""

import math
import pandas as pd


def _safe_float(value, default=0.0):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def american_odds_to_implied_pct(odds):
    odds = _safe_float(odds, None)
    if odds is None or odds == 0:
        return None

    if odds < 0:
        return round(abs(odds) / (abs(odds) + 100) * 100, 1)

    return round(100 / (odds + 100) * 100, 1)


def edge_to_projected_win_pct(row):
    edge = _safe_float(row.get("edge_vs_opponent"))
    offense_adv = _safe_float(row.get("offense_advantage"))
    pitcher_adj = _safe_float(row.get("pitcher_score_adj"))
    opp_pitcher_adj = _safe_float(row.get("opponent_pitcher_score_adj"))
    volatility_penalty = _safe_float(row.get("volatility_penalty_ml"))
    public_penalty = _safe_float(row.get("public_penalty_ml"))

    pitcher_gap = pitcher_adj - opp_pitcher_adj

    win_pct = 50.0

    win_pct += max(min(edge * 0.45, 12), -12)
    win_pct += max(min(pitcher_gap * 0.12, 8), -8)
    win_pct += max(min(offense_adv * 4.0, 5), -5)

    win_pct -= volatility_penalty * 6
    win_pct -= public_penalty * 5

    short_leash = str(row.get("short_leash_flag", "")).lower()
    if "yes" in short_leash:
        win_pct -= 2.5

    opp_type = str(row.get("opponent_pitcher_pick_type", "")).lower()
    if "strong sp" in opp_type:
        win_pct -= 2.0

    win_pct = max(35.0, min(72.0, win_pct))
    return round(win_pct, 1)


def get_volatility_label(row):
    volatility = _safe_float(row.get("team_volatility"), 1.0)
    volatility_penalty = _safe_float(row.get("volatility_penalty_ml"), 0.0)

    if volatility >= 1.18 or volatility_penalty >= 0.35:
        return "High"
    if volatility >= 1.08 or volatility_penalty >= 0.15:
        return "Medium"
    return "Low"


def get_parlay_grade(projected_win_pct, volatility_label, model_edge_pct=None):
    edge = _safe_float(model_edge_pct, 0)

    if projected_win_pct >= 65 and volatility_label == "Low" and edge >= 3:
        return "A"
    if projected_win_pct >= 62 and volatility_label in ["Low", "Medium"] and edge >= 1:
        return "B"
    if projected_win_pct >= 58 and volatility_label != "High":
        return "C"
    return "Pass"


def get_ml_recommendation(projected_win_pct, parlay_grade, volatility_label):
    if parlay_grade == "A":
        return "Elite ML / Parlay Anchor"
    if parlay_grade == "B":
        return "Strong ML Lean"
    if parlay_grade == "C":
        return "Small Edge / Research Only"
    if volatility_label == "High":
        return "Avoid - High Volatility"
    return "Avoid"


def add_game_edge_engine(game_rankings_df, odds_col="moneyline_odds"):
    if game_rankings_df is None or game_rankings_df.empty:
        return game_rankings_df

    df = game_rankings_df.copy()

    df["projected_win_pct"] = df.apply(edge_to_projected_win_pct, axis=1)
    df["volatility_label"] = df.apply(get_volatility_label, axis=1)

    if odds_col in df.columns:
        df["vegas_implied_pct"] = df[odds_col].apply(american_odds_to_implied_pct)
    else:
        df["vegas_implied_pct"] = None

    def calc_edge(row):
        vegas = row.get("vegas_implied_pct")
        if vegas is None:
            return None
        return round(_safe_float(row.get("projected_win_pct")) - _safe_float(vegas), 1)

    df["model_edge_pct"] = df.apply(calc_edge, axis=1)

    df["parlay_grade"] = df.apply(
        lambda r: get_parlay_grade(
            _safe_float(r.get("projected_win_pct")),
            r.get("volatility_label"),
            r.get("model_edge_pct")
        ),
        axis=1
    )

    df["ml_recommendation_v2"] = df.apply(
        lambda r: get_ml_recommendation(
            _safe_float(r.get("projected_win_pct")),
            r.get("parlay_grade"),
            r.get("volatility_label")
        ),
        axis=1
    )

    grade_rank = {"A": 1, "B": 2, "C": 3, "Pass": 4}
    df["_parlay_sort"] = df["parlay_grade"].map(grade_rank).fillna(9)

    df = df.sort_values(
        by=["_parlay_sort", "projected_win_pct"],
        ascending=[True, False]
    ).drop(columns=["_parlay_sort"])

    return df


def select_best_parlay_legs(game_rankings_df, max_legs=3):
    if game_rankings_df is None or game_rankings_df.empty:
        return []

    df = game_rankings_df.copy()

    if "parlay_grade" not in df.columns:
        df = add_game_edge_engine(df)

    candidates = df[
        df["parlay_grade"].isin(["A", "B"])
        & (df["volatility_label"] != "High")
    ].copy()

    selected = []
    used_games = set()

    for _, row in candidates.iterrows():
        game = row.get("game")
        if game in used_games:
            continue

        selected.append(row.to_dict())
        used_games.add(game)

        if len(selected) >= max_legs:
            break

    return selected
