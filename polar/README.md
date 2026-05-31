# Polar data drop

Drop your Polar Flow exports here and Penny will parse them into the dashboard
(a new Training & Recovery section to complement the body-comp data in `../data.js`).

## How to export from Polar (you do this — I never log into your account)
On the web at **flow.polar.com** (signed in as you):
- **Full history (best):** Account/profile menu → Settings → **Export data** (the account/GDPR data export). It produces a downloadable zip of your training history (JSON/CSV).
- **Or individual sessions:** open a training session → the **···** menu → **Export** (TCX / CSV / GPX).

Then drop the file(s) into this folder. Any format is fine — I'll parse it.

## What I'll build from it
- `SEED_TRAINING` — per-session: date, type, duration, calories, avg/max HR, training load
- `SEED_RECOVERY` — Nightly Recharge / sleep / resting HR trends (if present in the export)
- A Training & Recovery panel in the dashboard, alongside body composition

*Later upgrade: Polar AccessLink API for automatic ongoing sync (you OAuth-authorize it; no manual re-export).*
