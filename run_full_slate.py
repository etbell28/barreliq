import subprocess
import sys
import shutil
from datetime import date
from pathlib import Path


ROOT = Path(__file__).parent
PYTHON = sys.executable
FULL_SLATE = ROOT / "outputs" / "auto_slate_full.csv"


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
    run([PYTHON, "build_automated_slate.py", "--mode", "all", "--output", str(FULL_SLATE)])
    (ROOT / "outputs" / "active_slate.txt").write_text("full", encoding="utf-8")
    run([PYTHON, "hitter_tool.py", str(FULL_SLATE)])
    run([PYTHON, "build_dashboard.py"])
    run([PYTHON, "publish_dashboard.py"])
    snapshot_outputs("full")
    print("Full-day slate and HR rankings are ready.")
    print(f"Slate: {FULL_SLATE}")
    print(f"Rankings CSV: {ROOT / 'outputs' / 'hr_rankings.csv'}")
    print(f"Rankings Excel: {ROOT / 'outputs' / 'hr_rankings.xlsx'}")
    print(f"Dashboard: {ROOT / 'outputs' / 'hitter_tool_dashboard.html'}")
    print(f"Deployable site: {ROOT / 'dashboard_site' / 'index.html'}")
    print(f"Report: {ROOT / 'outputs' / 'hr_rankings.md'}")


if __name__ == "__main__":
    main()
