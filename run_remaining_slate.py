import subprocess
import sys
import shutil
from datetime import date
from pathlib import Path


ROOT = Path(__file__).parent
PYTHON = sys.executable
REMAINING_SLATE = ROOT / "outputs" / "auto_slate_remaining.csv"


def run(command):
    subprocess.run(command, cwd=ROOT, check=True)


def snapshot_outputs(label):
    daily = ROOT / "outputs" / "daily"
    today = date.today().isoformat()
    daily.mkdir(parents=True, exist_ok=True)
    copies = [
        (ROOT / "outputs" / "hr_rankings.csv", daily / f"hr_rankings_{today}_{label}.csv"),
        (ROOT / "outputs" / "hr_rankings.xlsx", daily / f"hr_rankings_{today}_{label}.xlsx"),
        (ROOT / "outputs" / "hr_rankings.md", daily / f"hr_rankings_{today}_{label}.md"),
    ]
    for source, target in copies:
        if source.exists():
            shutil.copy2(source, target)


def main():
    run([PYTHON, "build_automated_slate.py", "--mode", "upcoming", "--output", str(REMAINING_SLATE)])
    (ROOT / "outputs" / "active_slate.txt").write_text("remaining", encoding="utf-8")
    run([PYTHON, "hitter_tool.py", str(REMAINING_SLATE)])
    run([PYTHON, "build_dashboard.py"])
    run([PYTHON, "publish_dashboard.py"])
    snapshot_outputs("remaining")
    print("Remaining-game slate and HR rankings are ready.")
    print("Only games that have not started are included.")
    print(f"Slate: {REMAINING_SLATE}")
    print(f"Rankings CSV: {ROOT / 'outputs' / 'hr_rankings.csv'}")
    print(f"Rankings Excel: {ROOT / 'outputs' / 'hr_rankings.xlsx'}")
    print(f"Dashboard: {ROOT / 'outputs' / 'hitter_tool_dashboard.html'}")
    print(f"Deployable site: {ROOT / 'dashboard_site' / 'index.html'}")
    print(f"Report: {ROOT / 'outputs' / 'hr_rankings.md'}")


if __name__ == "__main__":
    main()
