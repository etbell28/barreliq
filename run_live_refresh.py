import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).parent
PYTHON = sys.executable
OUTPUTS = ROOT / "outputs"
FULL_SLATE = OUTPUTS / "auto_slate_full.csv"
REMAINING_SLATE = OUTPUTS / "auto_slate_remaining.csv"


def run(command):
    subprocess.run(command, cwd=ROOT, check=True)


def choose_mode(requested):
    if requested in {"full", "remaining"}:
        return requested

    now = datetime.now(ZoneInfo("America/New_York"))
    if now.hour < 12:
        return "full"
    return "remaining"


def snapshot_live_outputs(label):
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    daily = OUTPUTS / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    copies = [
        (OUTPUTS / "hr_rankings.csv", daily / f"hr_rankings_{today}_{label}.csv"),
        (OUTPUTS / "hr_rankings.xlsx", daily / f"hr_rankings_{today}_{label}.xlsx"),
        (OUTPUTS / "hr_rankings.md", daily / f"hr_rankings_{today}_{label}.md"),
        (OUTPUTS / "live_payload.json", daily / f"live_payload_{today}_{label}.json"),
    ]
    for source, target in copies:
        if source.exists():
            shutil.copy2(source, target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["auto", "full", "remaining"], default="auto")
    args = parser.parse_args()
    mode = choose_mode(args.mode)

    if mode == "full":
        slate_path = FULL_SLATE
        build_mode = "all"
    else:
        slate_path = REMAINING_SLATE
        build_mode = "upcoming"

    run([PYTHON, "build_automated_slate.py", "--mode", build_mode, "--output", str(slate_path)])
    (OUTPUTS / "active_slate.txt").write_text(mode, encoding="utf-8")
    run([PYTHON, "hitter_tool.py", str(slate_path)])
    run([PYTHON, "build_dashboard.py"])
    run([PYTHON, "build_live_payload.py"])
    run([PYTHON, "publish_dashboard.py"])
    snapshot_live_outputs(mode)

    print(f"Live refresh complete. Mode: {mode}")
    print(f"Slate: {slate_path}")
    print(f"Payload: {OUTPUTS / 'live_payload.json'}")


if __name__ == "__main__":
    main()
