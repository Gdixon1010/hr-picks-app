# HR Picks App - ML + Refined Upgrade Patch

def cleanup_refined_picks(refined_picks):
    refined_picks = [
        x for x in refined_picks
        if x.get("playerName")
        and x.get("game")
        and x.get("game") != "—"
    ]

    seen = set()
    clean = []

    for x in refined_picks:
        key = (
            x.get("playerName"),
            x.get("teamName"),
            x.get("game")
        )

        if key in seen:
            continue

        seen.add(key)
        clean.append(x)

    refined_picks = clean

    team_counts = {}
    final_refined = []

    for x in sorted(
        refined_picks,
        key=lambda r: float(r.get("Hit_score") or 0),
        reverse=True
    ):
        team = x.get("teamName")

        if team_counts.get(team, 0) >= 2:
            continue

        team_counts[team] = team_counts.get(team, 0) + 1
        final_refined.append(x)

    return final_refined[:6]


def calculate_ml_edge(row):
    edge = 0

    if float(row.get("sp_edge", 0)) > 0:
        edge += 2

    if float(row.get("bullpen_edge", 0)) > 0:
        edge += 2

    if float(row.get("offense_edge", 0)) > 0:
        edge += 2

    if float(row.get("market_edge", 0)) > 0:
        edge += 2

    if row.get("is_home"):
        edge += 1

    return edge


def filter_ml_plays(ml_rows):
    out = []

    for row in ml_rows:
        edge = calculate_ml_edge(row)

        row["ml_edge_score"] = edge

        if edge >= 7:
            out.append(row)

    out = sorted(
        out,
        key=lambda x: x.get("ml_edge_score", 0),
        reverse=True
    )

    return out[:1]

print("Patch loaded")
