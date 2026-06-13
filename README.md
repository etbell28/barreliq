# BarrelIQ

BarrelIQ is a live MLB home run target dashboard.

## Free-Plan Architecture

- GitHub Actions runs the Python model.
- The model writes `outputs/live_payload.json`.
- Vercel hosts `index.html`.
- The dashboard fetches `/outputs/live_payload.json` every 60 seconds.
- No Vercel Pro.
- No Vercel Blob.
- No Vercel Cron.

## Data Refresh Modes

- `full`: use before games start to scan the full slate.
- `remaining`: use near first pitch and after games begin so started games do not pollute the actionable board.
- `audit`: post-slate model review.

## Important Limitation

On the free stack, this is near-live, not second-by-second livestreaming. GitHub scheduled workflows can run every 5 minutes, but GitHub notes that scheduled workflows may be delayed or dropped during high load.
