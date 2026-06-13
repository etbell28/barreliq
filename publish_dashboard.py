import shutil
from pathlib import Path


ROOT = Path(__file__).parent
SITE_DIR = ROOT / "dashboard_site"
SOURCE_DASHBOARD = ROOT / "outputs" / "hitter_tool_dashboard.html"


def main():
    if not SOURCE_DASHBOARD.exists():
        raise SystemExit(f"Missing dashboard file: {SOURCE_DASHBOARD}")

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_DASHBOARD, SITE_DIR / "index.html")

    print(f"Published dashboard site to {SITE_DIR}")
    print(f"Vercel entry file: {SITE_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
