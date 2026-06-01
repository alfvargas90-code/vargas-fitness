# VeSync scale — what Alfie does tomorrow

Stub is built and committed. Auth, device discovery, file-writing, git-push, and
logging all follow the working `polar/` pattern. Only the live credentials are
missing. ~5 minutes to wire in.

## 1. Create your `.env`

```sh
cd "/Volumes/Alfie&Co2/alfredo.v/04_Projects/fitness-dashboard/vesync"
cp .env.example .env
```

Open `.env` and fill in:
- `VESYNC_EMAIL` — your **VeSync app account** email (the login for the VeSync
  phone app), NOT the scale's model name.
- `VESYNC_PASSWORD` — your VeSync account password.
- Leave `VESYNC_DEVICE_ID` blank for now (auto-detects the scale).
- `VESYNC_TIMEZONE` defaults to `America/Chicago` — fine.

`.env` is gitignored. It will not be committed.

## 2. Step on the scale, then test-run once

Take a weigh-in first so there's fresh data, then:

```sh
.venv/bin/python3 sync.py
```

What you want to see:
- `auth: logged in …`
- `scale: <name> (cid=…, type=…)` — confirms it found your scale
- `saved: daily/<date>.json (…kg, …% fat)`

**If it logs in but finds no scale or no reading:** the fat-scale endpoint's
field names vary by account/firmware. The script logs the full raw payload —
paste that back to me and I'll correct the body/response mapping (the spots are
marked `VERIFY` in `sync.py`; see `RECON_NOTES.md` "Open items"). This is the one
expected manual loop — budget for it.

## 3. ⚠️ Privacy gate — confirm BEFORE turning on the LaunchAgent

This dashboard deploys to **public GitHub Pages**. Turning on the sync publishes
your **weight + body-fat + BMI + muscle/water/BMR/visceral fat** to a public URL,
same tradeoff you already accepted for Polar + nutrition. If you're good with
body-comp being public too, proceed. If not, stop here — we can gate it behind a
private repo or strip fields first.

## 4. Install the LaunchAgent (only after steps 2–3 pass)

```sh
cp "/Volumes/Alfie&Co2/alfredo.v/04_Projects/fitness-dashboard/vesync/com.alfredo.vesync-sync.plist" \
   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.alfredo.vesync-sync.plist
```

Runs hourly (readings only change when you step on the scale). Logs:
`~/Library/Logs/vesync-sync.{out,err}.log`.

To stop later: `launchctl unload ~/Library/LaunchAgents/com.alfredo.vesync-sync.plist`

## 5. Dashboard UI (separate task)

`vesync/daily/` + `manifest.json` will hold the data. The dashboard card/JS is
NOT built yet — that's the next session, once real readings are flowing.
