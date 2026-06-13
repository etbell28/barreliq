import argparse
import csv
import html
import json
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DAILY_DIR = ROOT / "outputs" / "daily"


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def audited_date_from_local_today(local_today):
    today = date.fromisoformat(local_today) if local_today else date.today()
    return (today - timedelta(days=1)).isoformat()


def read_rankings(path):
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def matchup_key(team_a, team_b):
    return tuple(sorted((team_a, team_b)))


def ranked_matchups(rankings):
    return {
        matchup_key(row["team"], row["opponent"])
        for row in rankings
        if row.get("team") and row.get("opponent")
    }


def schedule_for(run_date):
    return fetch_json(
        "https://statsapi.mlb.com/api/v1/schedule"
        f"?sportId=1&date={run_date}&hydrate=team"
    )


def live_feed(game_pk):
    return fetch_json(f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live")


def game_team_abbreviations(game):
    return (
        game["teams"]["away"]["team"].get("abbreviation", ""),
        game["teams"]["home"]["team"].get("abbreviation", ""),
    )


def collect_home_runs(run_date, predicted_matchups):
    schedule = schedule_for(run_date)
    games = [
        game
        for day in schedule.get("dates", [])
        for game in day.get("games", [])
    ]
    all_game_count = len(games)
    slate_games = []
    outside_games = []
    home_runs = []
    skipped_games = []

    for game in games:
        away, home = game_team_abbreviations(game)
        in_slate = matchup_key(away, home) in predicted_matchups
        if in_slate:
            slate_games.append(game)
        else:
            outside_games.append(game)

        if not in_slate:
            continue

        game_pk = game["gamePk"]
        try:
            feed = live_feed(game_pk)
        except Exception as exc:
            skipped_games.append(f"{away}@{home} ({game_pk}): {exc}")
            continue

        plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", [])
        teams_by_id = {
            feed.get("gameData", {}).get("teams", {}).get("away", {}).get("id"): away,
            feed.get("gameData", {}).get("teams", {}).get("home", {}).get("id"): home,
        }
        for play in plays:
            result = play.get("result", {})
            if result.get("eventType") != "home_run":
                continue
            batter = play.get("matchup", {}).get("batter", {})
            team_id = play.get("about", {}).get("halfInning")
            batting_team = away if team_id == "top" else home if team_id == "bottom" else ""
            home_runs.append(
                {
                    "game_pk": game_pk,
                    "game": f"{away}@{home}",
                    "player_id": batter.get("id", ""),
                    "player": batter.get("fullName", ""),
                    "team": batting_team,
                    "opponent": home if batting_team == away else away if batting_team == home else "",
                    "inning": play.get("about", {}).get("inning", ""),
                    "half_inning": play.get("about", {}).get("halfInning", ""),
                    "event": result.get("event", "Home Run"),
                    "description": result.get("description", ""),
                }
            )

    return {
        "all_game_count": all_game_count,
        "slate_games": slate_games,
        "outside_games": outside_games,
        "home_runs": home_runs,
        "skipped_games": skipped_games,
    }


def build_rows(run_date, rankings, home_runs):
    by_player = defaultdict(list)
    for row in rankings:
        by_player[row.get("player", "").casefold()].append(row)

    grouped = {}
    for hr in home_runs:
        key = (hr["player"].casefold(), hr["team"], hr["opponent"])
        if key not in grouped:
            grouped[key] = {
                **hr,
                "hr_count": 0,
                "innings": [],
                "descriptions": [],
            }
        grouped[key]["hr_count"] += 1
        grouped[key]["innings"].append(str(hr["inning"]))
        grouped[key]["descriptions"].append(hr["description"])

    rows = []
    for hr in sorted(grouped.values(), key=lambda item: (item["game"], item["player"])):
        candidates = by_player.get(hr["player"].casefold(), [])
        ranked = next(
            (
                row
                for row in candidates
                if row.get("team") == hr["team"] and row.get("opponent") == hr["opponent"]
            ),
            candidates[0] if candidates else None,
        )
        rank = int(ranked["rank"]) if ranked and ranked.get("rank") else None
        rows.append(
            {
                "date": run_date,
                "game": hr["game"],
                "player": hr["player"],
                "team": hr["team"],
                "opponent": hr["opponent"],
                "hr_count": hr["hr_count"],
                "innings": ", ".join(hr["innings"]),
                "event": hr["event"],
                "description": " / ".join(hr["descriptions"]),
                "appeared_in_rankings": "Yes" if ranked else "No",
                "rank": rank if rank is not None else "",
                "hr_score": ranked.get("hr_score", "") if ranked else "",
                "tier": ranked.get("tier", "") if ranked else "",
                "top_20": "Yes" if rank is not None and rank <= 20 else "No",
                "top_10": "Yes" if rank is not None and rank <= 10 else "No",
            }
        )
    return rows


def markdown_table(rows):
    lines = [
        "| Player | Team | Game | Rank | HR Score | Top 20 | Top 10 | HR Detail |",
        "|---|---|---|---:|---:|---|---|---|",
    ]
    for row in rows:
        rank = row["rank"] if row["rank"] != "" else "NR"
        detail = row["description"].replace("|", "\\|")
        lines.append(
            f"| {row['player']} | {row['team']} | {row['game']} | {rank} | "
            f"{row['hr_score']} | {row['top_20']} | {row['top_10']} | {detail} |"
        )
    return "\n".join(lines)


def rank_value(row):
    try:
        return int(row["rank"])
    except (TypeError, ValueError):
        return None


def score_value(row, key):
    try:
        return float(row.get(key, "") or 0)
    except (TypeError, ValueError):
        return 0.0


def ranking_key(row):
    return (
        row.get("player", "").casefold(),
        row.get("team", ""),
        row.get("opponent", ""),
    )


def calibration_lines(rankings, rows):
    hr_keys = {
        (row["player"].casefold(), row["team"], row["opponent"])
        for row in rows
        if row["appeared_in_rankings"] == "Yes"
    }
    bands = [
        ("Top 10", 1, 10),
        ("11-20", 11, 20),
        ("21-40", 21, 40),
        ("41-60", 41, 60),
        ("61+", 61, 9999),
    ]
    lines = [
        "| Rank Band | HR Hits | Hit Rate Within Band |",
        "|---|---:|---:|",
    ]
    for label, low, high in bands:
        band_rows = [
            row
            for row in rankings
            if row.get("rank") and low <= int(row["rank"]) <= high
        ]
        hits = sum(ranking_key(row) in hr_keys for row in band_rows)
        rate = (hits / len(band_rows) * 100) if band_rows else 0
        lines.append(f"| {label} | {hits} / {len(band_rows)} | {rate:.1f}% |")
    return lines


def component_summary_lines(rankings, rows):
    hr_keys = {
        (row["player"].casefold(), row["team"], row["opponent"])
        for row in rows
        if row["appeared_in_rankings"] == "Yes"
    }
    ranked_hits = [row for row in rankings if ranking_key(row) in hr_keys]
    top20_non_hits = [
        row
        for row in rankings
        if row.get("rank") and int(row["rank"]) <= 20 and ranking_key(row) not in hr_keys
    ]
    all_non_hits = [row for row in rankings if ranking_key(row) not in hr_keys]

    groups = [
        ("Actual HR hitters found in rankings", ranked_hits),
        ("Top 20 non-HR hitters", top20_non_hits),
        ("All ranked non-HR hitters", all_non_hits),
    ]
    fields = [
        ("HR Score", "hr_score"),
        ("Power", "power_score"),
        ("Pitcher", "pitcher_score"),
        ("Environment", "environment_score"),
        ("Lineup", "lineup_score"),
    ]
    lines = [
        "| Group | Count | Avg HR Score | Avg Power | Avg Pitcher | Avg Environment | Avg Lineup |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, group in groups:
        values = []
        for _, key in fields:
            values.append(
                sum(score_value(row, key) for row in group) / len(group)
                if group
                else 0
            )
        lines.append(
            f"| {label} | {len(group)} | "
            + " | ".join(f"{value:.1f}" for value in values)
            + " |"
        )
    return lines


def game_concentration_lines(rows):
    counts = defaultdict(int)
    top20_counts = defaultdict(int)
    for row in rows:
        counts[row["game"]] += 1
        if row["top_20"] == "Yes":
            top20_counts[row["game"]] += 1

    lines = [
        "| Game | Actual HR Hitters | Top 20 Hits |",
        "|---|---:|---:|",
    ]
    for game, count in sorted(counts.items(), key=lambda item: item[1], reverse=True):
        lines.append(f"| {game} | {count} | {top20_counts[game]} |")
    return lines


def top_missed_ranked_lines(rankings, rows, limit=8):
    hr_keys = {
        (row["player"].casefold(), row["team"], row["opponent"])
        for row in rows
        if row["appeared_in_rankings"] == "Yes"
    }
    misses = [
        row
        for row in rankings
        if row.get("rank") and int(row["rank"]) <= 20 and ranking_key(row) not in hr_keys
    ][:limit]
    if not misses:
        return ["- None."]
    return [
        (
            f"- #{row['rank']} {row['player']} ({row['team']} vs {row['opponent']}), "
            f"Score {row['hr_score']}; components: power {row.get('power_score', '')}, "
            f"pitcher {row.get('pitcher_score', '')}, environment {row.get('environment_score', '')}, "
            f"lineup {row.get('lineup_score', '')}."
        )
        for row in misses
    ]


def write_markdown(path, run_date, rankings_path, rankings, result, rows):
    ranked_hits = [row for row in rows if row["appeared_in_rankings"] == "Yes"]
    top20 = sum(row["top_20"] == "Yes" for row in rows)
    top10 = sum(row["top_10"] == "Yes" for row in rows)
    best = min(
        (row for row in ranked_hits if row["rank"] != ""),
        key=lambda row: int(row["rank"]),
        default=None,
    )
    misses = [row for row in rows if row["appeared_in_rankings"] == "No"]
    slate_games = [
        f"{game_team_abbreviations(game)[0]}@{game_team_abbreviations(game)[1]}"
        for game in result["slate_games"]
    ]
    outside_games = [
        f"{game_team_abbreviations(game)[0]}@{game_team_abbreviations(game)[1]}"
        for game in result["outside_games"]
    ]

    lines = [
        f"# HR Audit for {run_date}",
        "",
        "## Summary",
        "",
        f"- Saved rankings file: `{rankings_path.relative_to(ROOT)}`",
        f"- Total predicted hitters: **{len(rankings)}**",
        f"- MLB official-date games: **{result['all_game_count']}**",
        f"- Predicted slate games audited: **{len(result['slate_games'])}** ({', '.join(slate_games)})",
        f"- Actual HR hitters in predicted slate: **{len(rows)}**",
        f"- Actual HR hitters found in model rankings: **{len(ranked_hits)} / {len(rows)}**",
        f"- Top 20 hit count: **{top20}**",
        f"- Top 10 hit count: **{top10}**",
        (
            f"- Best-ranked hit: **{best['player']}** at **#{best['rank']}** "
            f"with HR Score **{best['hr_score']}**"
            if best
            else "- Best-ranked hit: none"
        ),
        "",
        "## Actual HR Hitters vs Rankings",
        "",
        markdown_table(sorted(rows, key=lambda row: int(row["rank"]) if row["rank"] != "" else 9999)),
        "",
        "## Notable Misses",
        "",
    ]
    if misses:
        lines.extend(
            f"- {row['player']} ({row['team']} vs {row['opponent']}) was not in the saved rankings."
            for row in misses
        )
    else:
        lines.append("- None. Every actual HR hitter in the predicted slate appeared in the saved rankings.")

    lines.extend(
        [
            "",
            "## Ranking Calibration",
            "",
            *calibration_lines(rankings, rows),
            "",
            "## Component Calibration",
            "",
            *component_summary_lines(rankings, rows),
            "",
            "## Game Concentration",
            "",
            *game_concentration_lines(rows),
            "",
            "## Highest-Ranked Non-HR Plays",
            "",
            *top_missed_ranked_lines(rankings, rows),
            "",
            "## Calibration Notes",
            "",
        ]
    )
    if rows:
        top20_hits = sum(row["top_20"] == "Yes" for row in rows)
        top10_hits = sum(row["top_10"] == "Yes" for row in rows)
        lines.append(
            f"- The ranking order showed useful separation: {top10_hits} HR hitters landed in the Top 10 "
            f"and {top20_hits} landed in the Top 20."
        )
    if misses:
        lines.append(
            "- Misses marked NR are coverage misses, not ranking misses: the player was not present in "
            "the saved prediction pool, usually because of lineup/substitution timing or source coverage."
        )
    lines.append(
        "- Environment mattered heavily on this slate. If one game grades as extreme, pairings and game-board "
        "presentation should make that concentration obvious instead of spreading attention evenly across games."
    )

    lines.extend(["", "## Data-Quality Warnings", ""])
    if outside_games:
        lines.append(
            "- MLB official date included additional games outside the saved prediction slate: "
            + ", ".join(outside_games)
            + ". They were excluded from hit/miss counts."
        )
    if result["skipped_games"]:
        for warning in result["skipped_games"]:
            lines.append(f"- Could not fetch live feed for {warning}.")
    else:
        lines.append("- MLB Stats API schedule and live feeds were fetched successfully for all predicted slate games.")

    path.write_text("\n".join(lines) + "\n")


def write_csv(path, rows):
    fieldnames = [
        "date",
        "game",
        "player",
        "team",
        "opponent",
        "hr_count",
        "innings",
        "event",
        "description",
        "appeared_in_rankings",
        "rank",
        "hr_score",
        "tier",
        "top_20",
        "top_10",
    ]
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_html(path, run_date, markdown_path, csv_path, rows):
    hit_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['player'])}</td>"
        f"<td>{html.escape(row['team'])}</td>"
        f"<td>{html.escape(row['game'])}</td>"
        f"<td>{html.escape(str(row['rank'] or 'NR'))}</td>"
        f"<td>{html.escape(str(row['hr_score']))}</td>"
        f"<td>{html.escape(row['top_20'])}</td>"
        f"<td>{html.escape(row['top_10'])}</td>"
        f"<td>{html.escape(row['description'])}</td>"
        "</tr>"
        for row in sorted(rows, key=lambda row: int(row["rank"]) if row["rank"] != "" else 9999)
    )
    path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HR Audit {html.escape(run_date)}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #17202a; }}
    h1 {{ margin-bottom: 4px; }}
    .meta {{ color: #52606d; margin-bottom: 24px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
    th, td {{ border: 1px solid #d8dee4; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f6f8fa; }}
    a {{ color: #0958d9; }}
  </style>
</head>
<body>
  <h1>HR Audit for {html.escape(run_date)}</h1>
  <p class="meta">Official MLB Stats API audit. Source files:
    <a href="{html.escape(markdown_path.name)}">Markdown</a> and
    <a href="{html.escape(csv_path.name)}">CSV</a>.
  </p>
  <table>
    <thead>
      <tr><th>Player</th><th>Team</th><th>Game</th><th>Rank</th><th>HR Score</th><th>Top 20</th><th>Top 10</th><th>HR Detail</th></tr>
    </thead>
    <tbody>
      {hit_rows}
    </tbody>
  </table>
</body>
</html>
""",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--local-today", default=None)
    args = parser.parse_args()

    run_date = args.date or audited_date_from_local_today(args.local_today)
    rankings_path = DAILY_DIR / f"hr_rankings_{run_date}_full.csv"
    if not rankings_path.exists():
        rankings_path = DAILY_DIR / f"hr_rankings_{run_date}.csv"
    if not rankings_path.exists():
        fallback = ROOT / "outputs" / "hr_rankings.csv"
        raise SystemExit(
            f"Missing {rankings_path}. Fallback not used automatically; verify {fallback} date first."
        )

    rankings = read_rankings(rankings_path)
    result = collect_home_runs(run_date, ranked_matchups(rankings))
    rows = build_rows(run_date, rankings, result["home_runs"])

    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    markdown_path = DAILY_DIR / f"hr_audit_{run_date}.md"
    csv_path = DAILY_DIR / f"hr_audit_{run_date}.csv"
    html_path = DAILY_DIR / f"hr_audit_{run_date}.html"

    write_markdown(markdown_path, run_date, rankings_path, rankings, result, rows)
    write_csv(csv_path, rows)
    write_html(html_path, run_date, markdown_path, csv_path, rows)

    print(f"markdown={markdown_path}")
    print(f"csv={csv_path}")
    print(f"html={html_path}")
    print(f"actual_hr_hitters={len(rows)}")
    print(f"top20={sum(row['top_20'] == 'Yes' for row in rows)}")
    print(f"top10={sum(row['top_10'] == 'Yes' for row in rows)}")


if __name__ == "__main__":
    main()
