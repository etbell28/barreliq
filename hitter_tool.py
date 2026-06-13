import csv
import sys
from datetime import date
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).parent
INPUT_PATH = ROOT / "work" / "sample_slate.csv"
NUMBERS_EXPORT_PATH = ROOT / "outputs" / "data_1_export.csv"
ENRICHED_NUMBERS_EXPORT_PATH = ROOT / "outputs" / "data_1_enriched.csv"
NORMALIZED_INPUT_PATH = ROOT / "work" / "normalized_slate.csv"
OUTPUT_CSV = ROOT / "outputs" / "hr_rankings.csv"
OUTPUT_MD = ROOT / "outputs" / "hr_rankings.md"
OUTPUT_XLSX = ROOT / "outputs" / "hr_rankings.xlsx"
DAILY_DIR = ROOT / "outputs" / "daily"


WEIGHTS = {
    "power": 0.33,
    "pitcher": 0.24,
    "environment": 0.15,
    "lineup": 0.14,
    "platoon": 0.09,
    "form": 0.05,
}


def number(row, key, default=0.0):
    value = row.get(key, "")
    if value is None or value == "":
        return default
    return float(value)


def clean_hand(value):
    hand = str(value or "").strip().upper()
    if hand.startswith("R"):
        return "R"
    if hand.startswith("L"):
        return "L"
    if hand.startswith("S"):
        return "S"
    return hand


def normalize(value, low, high):
    if high == low:
        return 0.0
    score = (value - low) / (high - low) * 100
    return max(0.0, min(100.0, score))


def confirmed(row):
    return row.get("confirmed_lineup", "").strip().lower() in {"yes", "y", "true", "1"}


def projected(row):
    return bool(str(row.get("batting_order", "")).strip()) or "projected" in row.get("lineup_sources_used", "").lower()


def power_score(row):
    barrel = normalize(number(row, "barrel_pct"), 3, 20)
    hard_hit = normalize(number(row, "hard_hit_pct"), 25, 60)
    exit_velocity = normalize(number(row, "avg_exit_velocity"), 84, 96)
    xiso = normalize(number(row, "xiso", number(row, "iso")), 0.080, 0.350)
    xslg = normalize(number(row, "xslg"), 0.300, 0.650)
    bat_speed = normalize(number(row, "bat_speed", 72), 66, 80)
    fb_pct = normalize(number(row, "fb_pct", 35), 20, 55)
    return (
        barrel * 0.25
        + hard_hit * 0.15
        + exit_velocity * 0.15
        + xiso * 0.20
        + xslg * 0.10
        + bat_speed * 0.08
        + fb_pct * 0.07
    )


def pitcher_score(row):
    hitter_hand = row.get("hitter_hand", "").strip().upper()
    barrel_allowed = normalize(number(row, "pitcher_barrel_pct_allowed", 8), 4, 14)
    hard_hit_allowed = normalize(number(row, "pitcher_hard_hit_pct_allowed", 38), 25, 55)
    exit_velocity_allowed = normalize(number(row, "pitcher_avg_exit_velocity_allowed", 89), 84, 94)
    xslg_allowed = normalize(number(row, "pitcher_xslg_allowed", 0.400), 0.300, 0.600)
    xiso_allowed = normalize(number(row, "pitcher_xiso_allowed", 0.160), 0.080, 0.300)
    fb_allowed = normalize(number(row, "pitcher_fb_pct_allowed", 35), 20, 55)

    if hitter_hand == "L":
        hr_allowed = normalize(number(row, "pitcher_hr_allowed_vs_lhh", number(row, "pitcher_hr_allowed", 10)), 0, 20)
    elif hitter_hand == "R":
        hr_allowed = normalize(number(row, "pitcher_hr_allowed_vs_rhh", number(row, "pitcher_hr_allowed", 10)), 0, 20)
    else:
        hr_allowed = normalize(number(row, "pitcher_hr_allowed", 10), 0, 35)

    return (
        barrel_allowed * 0.25
        + hard_hit_allowed * 0.15
        + exit_velocity_allowed * 0.15
        + xslg_allowed * 0.15
        + xiso_allowed * 0.15
        + fb_allowed * 0.10
        + hr_allowed * 0.05
    )


def environment_score(row):
    temp = normalize(number(row, "weather_temp"), 45, 95)
    wind = normalize(number(row, "wind_speed"), 0, 20)
    direction = row.get("wind_direction", "").strip().lower()

    if "out" in direction:
        wind_direction_score = 100.0
    elif "in" in direction:
        wind_direction_score = 20.0
    else:
        wind_direction_score = 55.0

    park_factor = normalize(number(row, "park_hr_factor", 100), 80, 125)
    return temp * 0.25 + wind * 0.20 + wind_direction_score * 0.30 + park_factor * 0.25


def lineup_score(row):
    order = int(number(row, "batting_order", 9))
    scores = {
        1: 92,
        2: 100,
        3: 96,
        4: 94,
        5: 84,
        6: 72,
        7: 58,
        8: 44,
        9: 35,
    }
    return scores.get(order, 25)


def opportunity_score(row):
    starter_score = 100 if confirmed(row) else 70 if projected(row) else 0
    return lineup_score(row) * 0.85 + starter_score * 0.15


def platoon_score(row):
    hitter_hand = clean_hand(row.get("hitter_hand", ""))
    pitcher_hand = clean_hand(row.get("pitcher_hand", ""))

    if hitter_hand == "S":
        return 75.0
    if hitter_hand == "L" and pitcher_hand == "R":
        return 80.0
    if hitter_hand == "R" and pitcher_hand == "L":
        return 78.0
    if hitter_hand and pitcher_hand and hitter_hand == pitcher_hand:
        return 50.0
    return 60.0


def recent_form_score(row):
    games = number(row, "recent_games", 0)
    hits = number(row, "recent_hits", 0)
    at_bats = number(row, "recent_abs", 0)
    homers = number(row, "recent_hr", 0)
    if games <= 0:
        return 50.0
    average_score = normalize(hits / at_bats if at_bats else 0, 0.120, 0.420)
    hr_score = normalize(homers, 0, 3)
    return average_score * 0.45 + hr_score * 0.55


def tier(score):
    if score >= 80:
        return "Tier 1"
    if score >= 70:
        return "Tier 2"
    if score >= 60:
        return "Tier 3"
    return "Longshot"


def play_type(row, score):
    public_attention = row.get("public_attention", "").strip().lower()
    odds = number(row, "odds", 0)

    if score >= 76:
        return "Best Overall"
    if score >= 64 and public_attention in {"low", "medium"}:
        return "Best Value"
    if score >= 55 and odds >= 500:
        return "Longshot"
    return "Watch List"


def reason_tags(row, scores):
    tags = []
    if not confirmed(row):
        tags.append("Projected Lineup")
    if scores["power"] >= 75:
        tags.append("Elite Power")
    if number(row, "barrel_pct") >= 10:
        tags.append("Strong Barrel")
    if scores["pitcher"] >= 70:
        tags.append("Pitcher Vulnerable")
    if scores["environment"] >= 70:
        tags.append("Good Environment")
    if int(number(row, "batting_order", 9)) <= 4:
        tags.append("Premium Lineup Spot")
    if scores["platoon"] >= 75:
        tags.append("Platoon Edge")
    if scores.get("form", 0) >= 70:
        tags.append("Hot Hitter/Streak")
    return ", ".join(tags) if tags else "No major boost"


def score_row(row):
    scores = {
        "power": power_score(row),
        "pitcher": pitcher_score(row),
        "environment": environment_score(row),
        "lineup": opportunity_score(row),
        "platoon": platoon_score(row),
        "form": recent_form_score(row),
    }
    total = sum(scores[name] * WEIGHTS[name] for name in WEIGHTS)
    row["power_score"] = round(scores["power"], 1)
    row["pitcher_score"] = round(scores["pitcher"], 1)
    row["environment_score"] = round(scores["environment"], 1)
    row["lineup_score"] = round(scores["lineup"], 1)
    row["platoon_score"] = round(scores["platoon"], 1)
    row["recent_form_score"] = round(scores["form"], 1)
    row["hr_score"] = round(total, 1)
    row["tier"] = tier(total)
    row["play_type"] = play_type(row, total)
    row["reason_tags"] = reason_tags(row, scores)
    return row


def read_rows():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        with path.open(newline="") as file:
            return list(csv.DictReader(file))

    if ENRICHED_NUMBERS_EXPORT_PATH.exists():
        rows = read_numbers_export(ENRICHED_NUMBERS_EXPORT_PATH)
        write_normalized_input(rows)
        return rows

    if NUMBERS_EXPORT_PATH.exists():
        rows = read_numbers_export(NUMBERS_EXPORT_PATH)
        write_normalized_input(rows)
        return rows

    with INPUT_PATH.open(newline="") as file:
        return list(csv.DictReader(file))


def read_numbers_export(path):
    with path.open(newline="") as file:
        reader = csv.reader(file)
        headers = next(reader)
        raw_rows = [values + [""] * (len(headers) - len(values)) for values in reader]

    pitcher_metrics = {}
    for values in raw_rows:
        pitcher = cell(values, 3)
        if pitcher and any(cell(values, index) != "" for index in range(23, 49)):
            pitcher_metrics[pitcher] = values[23:49]

    rows = []
    for values in raw_rows:
        pitcher = cell(values, 3)
        metrics = pitcher_metrics.get(pitcher)
        if metrics:
            for offset, metric in enumerate(metrics, start=23):
                if cell(values, offset) == "" and metric != "":
                    values[offset] = metric
        rows.append(normalize_numbers_row(values))
    return rows


def cell(values, index, default=""):
    if index >= len(values):
        return default
    value = values[index]
    return default if value is None else value


def split_hr_allowed(values, hitter_hand):
    total_hr_allowed = number({"value": cell(values, 24)}, "value")
    if clean_hand(hitter_hand) == "L":
        return total_hr_allowed, total_hr_allowed * 0.6, total_hr_allowed * 0.4
    if clean_hand(hitter_hand) == "R":
        return total_hr_allowed, total_hr_allowed * 0.4, total_hr_allowed * 0.6
    return total_hr_allowed, total_hr_allowed * 0.5, total_hr_allowed * 0.5


def normalize_numbers_row(values):
    hitter_hand = clean_hand(cell(values, 4))
    pitcher_hand = clean_hand(cell(values, 5))
    pitcher_hr, pitcher_hr_vs_lhh, pitcher_hr_vs_rhh = split_hr_allowed(values, hitter_hand)

    return {
        "player": cell(values, 0),
        "team": cell(values, 1),
        "opponent": cell(values, 2),
        "pitcher": cell(values, 3),
        "hitter_hand": hitter_hand,
        "pitcher_hand": pitcher_hand,
        "barrel_pct": cell(values, 21),
        "iso": cell(values, 13),
        "avg_exit_velocity": cell(values, 18),
        "hard_hit_pct": cell(values, 22),
        "hr_total": cell(values, 8),
        "pitcher_barrel_pct_allowed": cell(values, 38),
        "pitcher_hr_allowed": round(pitcher_hr, 1),
        "pitcher_hr_allowed_vs_lhh": round(pitcher_hr_vs_lhh, 1),
        "pitcher_hr_allowed_vs_rhh": round(pitcher_hr_vs_rhh, 1),
        "ballpark": cell(values, 49),
        "park_hr_factor": cell(values, 50, 100),
        "weather_temp": cell(values, 51),
        "wind_speed": cell(values, 52),
        "wind_direction": cell(values, 53),
        "batting_order": cell(values, 54, 9),
        "confirmed_lineup": cell(values, 55),
        "public_attention": cell(values, 56),
        "odds": "",
    }


def write_normalized_input(rows):
    NORMALIZED_INPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "player",
        "team",
        "opponent",
        "pitcher",
        "hitter_hand",
        "pitcher_hand",
        "barrel_pct",
        "iso",
        "avg_exit_velocity",
        "hard_hit_pct",
        "hr_total",
        "pitcher_barrel_pct_allowed",
        "pitcher_hr_allowed",
        "pitcher_hr_allowed_vs_lhh",
        "pitcher_hr_allowed_vs_rhh",
        "ballpark",
        "park_hr_factor",
        "weather_temp",
        "wind_speed",
        "wind_direction",
        "batting_order",
        "confirmed_lineup",
        "public_attention",
        "odds",
    ]
    with NORMALIZED_INPUT_PATH.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_csv(rows):
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank",
        "hitter_id",
        "player",
        "team",
        "opponent",
        "game_start_time",
        "game_status",
        "batting_order",
        "pitcher",
        "pitcher_id",
        "pitcher_hand",
        "hr_score",
        "tier",
        "play_type",
        "reason_tags",
        "power_score",
        "pitcher_score",
        "environment_score",
        "lineup_score",
        "platoon_score",
        "recent_form_score",
        "confirmed_lineup",
        "rotowire_confirmed_lineup",
        "rotowire_batting_order",
        "rotowire_player_found",
        "lineup_disagreement",
        "lineup_sources_used",
        "source_warnings",
        "stat_years_used",
        "bvp_pa",
        "bvp_hr",
        "bvp_note",
        "recent_games",
        "recent_hits",
        "recent_abs",
        "recent_hr",
        "recent_form_note",
        "split_matchup_note",
        "pitch_mix_note",
        "barrel_pct",
        "hard_hit_pct",
        "avg_exit_velocity",
        "ev50",
        "xslg",
        "xiso",
        "xwoba",
        "bat_speed",
        "fast_swing_pct",
        "pull_pct",
        "fb_pct",
        "hr_total",
        "iso",
        "pitcher_barrel_pct_allowed",
        "pitcher_hard_hit_pct_allowed",
        "pitcher_avg_exit_velocity_allowed",
        "pitcher_xslg_allowed",
        "pitcher_xiso_allowed",
        "pitcher_fb_pct_allowed",
        "wind_direction",
        "weather_temp",
        "ballpark",
        "odds",
    ]
    with OUTPUT_CSV.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    write_excel_and_daily(rows, fields)


def write_excel_and_daily(rows, fields):
    today = date.today().isoformat()
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    daily_csv = DAILY_DIR / f"hr_rankings_{today}.csv"
    daily_xlsx = DAILY_DIR / f"hr_rankings_{today}.xlsx"
    daily_top20_csv = DAILY_DIR / f"top_20_hr_hitters_{today}.csv"

    frame = pd.DataFrame([{field: row.get(field, "") for field in fields} for row in rows])
    frame.to_csv(daily_csv, index=False)
    frame.head(20).to_csv(daily_top20_csv, index=False)
    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="HR Rankings", index=False)
        frame.head(20).to_excel(writer, sheet_name="Top 20", index=False)
    with pd.ExcelWriter(daily_xlsx, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="HR Rankings", index=False)
        frame.head(20).to_excel(writer, sheet_name="Top 20", index=False)


def write_markdown(rows):
    lines = [
        "# Daily HR Rankings",
        "",
        "| Rank | Player | Team | Pitcher | Order | HR Score | Tier | Play Type | Reasons |",
        "|---:|---|---|---|---:|---:|---|---|---|",
    ]
    for row in rows[:20]:
        lines.append(
            f"| {row['rank']} | {row['player']} | {row['team']} | {row['pitcher']} | "
            f"{row['batting_order']} | {row['hr_score']} | {row['tier']} | "
            f"{row['play_type']} | {row['reason_tags']} |"
        )

    lines.extend(["", "## Best 2-Leg Pairings", ""])
    for combo in make_pairings(rows, 2)[:5]:
        lines.append(f"- {combo}")

    lines.extend(["", "## Best 3-Leg Pairings", ""])
    for combo in make_pairings(rows, 3)[:5]:
        lines.append(f"- {combo}")

    lines.extend(["", "## Best 4-Leg Pairings", ""])
    for combo in make_pairings(rows, 4)[:5]:
        lines.append(f"- {combo}")

    OUTPUT_MD.write_text("\n".join(lines) + "\n")


def make_pairings(rows, size):
    candidates = rows[:10]
    pairings = []
    for start in range(0, max(0, len(candidates) - size + 1)):
        group = candidates[start : start + size]
        avg_score = sum(number(row, "hr_score") for row in group) / size
        names = " + ".join(row["player"] for row in group)
        pairings.append(f"{names} | Avg HR Score: {avg_score:.1f}")
    return pairings


def main():
    if not INPUT_PATH.exists():
        raise SystemExit(f"Missing input file: {INPUT_PATH}")

    rows = [
        score_row(row)
        for row in read_rows()
        if row.get("player") and row.get("team") and row.get("opponent")
    ]
    rows.sort(key=lambda row: row["hr_score"], reverse=True)

    for index, row in enumerate(rows, start=1):
        row["rank"] = index

    write_csv(rows)
    write_markdown(rows)
    print(f"Wrote {OUTPUT_CSV}")
    print(f"Wrote {OUTPUT_MD}")


if __name__ == "__main__":
    main()
