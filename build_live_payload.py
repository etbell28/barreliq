import json
from pathlib import Path

from build_dashboard import build_payload, json_safe


ROOT = Path(__file__).parent
OUTPUTS = ROOT / "outputs"
LIVE_PAYLOAD = OUTPUTS / "live_payload.json"
SITE_DATA = ROOT / "dashboard_site" / "data" / "slate.json"


def main():
    payload = build_payload()
    text = json.dumps(json_safe(payload), ensure_ascii=False, default=json_safe, indent=2, allow_nan=False)

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    LIVE_PAYLOAD.write_text(text, encoding="utf-8")

    SITE_DATA.parent.mkdir(parents=True, exist_ok=True)
    SITE_DATA.write_text(text, encoding="utf-8")

    print(f"Wrote {LIVE_PAYLOAD}")
    print(f"Wrote {SITE_DATA}")


if __name__ == "__main__":
    main()
