# BarrelIQ Setup Steps

Use this file as the literal checklist.

## 1. Create New GitHub Repo

1. Go to `https://github.com`.
2. Click the `+` button near the top right.
3. Click `New repository`.
4. Repository name: `barreliq`.
5. Set visibility to `Public`.
6. Do not add README, license, or gitignore.
7. Click `Create repository`.

## 2. Upload Project Files

1. Open the local folder:
   `/Users/ebell/Documents/Codex/BarrelIQ`
2. Open your new GitHub repo:
   `https://github.com/etbell28/barreliq`
3. Click `uploading an existing file`.
4. Drag everything inside the local `BarrelIQ` folder into GitHub.
5. Commit message: `Initial BarrelIQ live build`.
6. Click `Commit changes`.

## 3. Enable GitHub Actions Write Access

1. In the GitHub repo, click `Settings`.
2. Click `Actions`.
3. Click `General`.
4. Scroll to `Workflow permissions`.
5. Select `Read and write permissions`.
6. Check `Allow GitHub Actions to create and approve pull requests` if visible.
7. Click `Save`.

## 4. Create New Vercel Project

1. Go to `https://vercel.com/dashboard`.
2. Click `Add New`.
3. Click `Project`.
4. Import the GitHub repo named `barreliq`.
5. Framework preset: `Other`.
6. Root directory: leave blank.
7. Build command: leave blank.
8. Output directory: leave blank.
9. Install command: leave blank.
10. Click `Deploy`.

## 5. First Manual Data Run

1. Open the GitHub repo.
2. Click `Actions`.
3. Click `BarrelIQ Live Refresh`.
4. Click `Run workflow`.
5. Choose `full` if no games have started.
6. Choose `remaining` if games are close or already started.
7. Click the green `Run workflow`.
8. Wait for the run to turn green.

## 6. Confirm Live Site

1. Open the Vercel URL.
2. The page should show `BarrelIQ`.
3. The top status should say `Live JSON Loaded`.
4. The date/time should match the latest workflow run.
5. Open:
   `/outputs/live_payload.json`
   on the Vercel site to confirm the raw data is available.

## 7. Daily Use

After setup, you should not upload files daily.

- GitHub Actions runs automatically.
- The site refreshes its JSON every 60 seconds.
- You only come back to Codex for model upgrades, dashboard changes, or troubleshooting.
