#!/usr/bin/env python3
"""
Keeps the Three-Lens astrology dashboard fresh end-to-end.

Two artifacts drive the live dashboard, and BOTH must refresh daily:
  1. ephemeris.json  — raw Swiss-Ephemeris transit snapshot (ephemeris.py)
  2. state.json      — the forecast + daily/monthly readings + currentDate that
                       the dashboard actually DISPLAYS (engine.py). The dashboard
                       reads currentDate from state.json, so if engine.py doesn't
                       run, the dashboard freezes on the last run's date.

Before 2026-06-14 this cron only refreshed ephemeris.json; engine.py had no
scheduled job and was run by hand, so the displayed date silently froze whenever
nobody ran it (06-08→06-11, 06-13→06-14). This now runs engine.py too, bumps
version.json (PWA cache-bust), and commits/pushes everything in one rebase-safe
shot — so the dashboard date can never drift again.

Run by a launchd LaunchAgent a few times a day via the FDA python (polar/.venv);
launchd bash is TCC-blocked from the external volume, so this is a python entry
point. engine.py's Codex calls are each bounded (timeout=180) and non-fatal, so a
flaky council degrades a reading to null — it never hangs this job.

Self-contained: pulls --rebase before pushing so it never fights the polar-sync /
deploy-watch jobs that also commit to this repo.
"""
import os, sys, subprocess, importlib.util
from datetime import datetime

REPO = "/Volumes/Alfie&Co2/alfredo.v/04_Projects/fitness-dashboard"
SUBDIR = os.path.join(REPO, "timing-weather/design_exploration_2026-06-12")
LIVE = os.path.join(REPO, "timing-weather")        # the live PWA serves ephemeris.json + state.json from here
ENGINE = os.path.join(LIVE, "engine.py")
VERSION = os.path.join(LIVE, "version.json")
# everything the dashboard fetches that this job refreshes
RELS = ["timing-weather/ephemeris.json",
        "timing-weather/design_exploration_2026-06-12/ephemeris.json",
        "timing-weather/state.json",
        "timing-weather/version.json"]

def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True)

def regen(outdir):
    os.chdir(outdir)
    spec = importlib.util.spec_from_file_location("ephem", os.path.join(SUBDIR, "ephemeris.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()

def run_engine():
    """Regenerate state.json (the displayed forecast + currentDate). Best-effort:
    bounded by an overall timeout; on failure the run still pushes whatever else
    changed and the next slot retries."""
    try:
        out = subprocess.run([sys.executable, ENGINE], cwd=LIVE,
                             capture_output=True, text=True, timeout=1500)
        if out.returncode == 0:
            print("engine.py:", (out.stdout.strip().splitlines() or ["ok"])[-1])
        else:
            print(f"engine.py exited {out.returncode}: {out.stderr.strip()[:300]}")
    except Exception as e:
        print(f"engine.py failed (non-fatal): {e}")

def bump_version():
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    with open(VERSION, "w") as f:
        f.write('{\n  "version": "%s",\n  "built_at": "%s"\n}\n' % (ts, ts))
    print("version.json ->", ts)

def main():
    # 1) refresh the raw transit snapshot (live PWA dir + exploration dir)
    regen(LIVE)
    regen(SUBDIR)

    # 2) refresh the DISPLAYED forecast + currentDate, then bust the PWA cache
    run_engine()
    bump_version()

    # 3) commit + push the dashboard artifacts (rebase to avoid racing the other auto-commit jobs)
    git("add", *RELS)
    if git("diff", "--cached", "--quiet").returncode == 0:
        print("no change")
        return
    git("commit", "-m", "chore: refresh astro ephemeris.json + state.json (daily)")
    for _ in range(3):
        git("pull", "--rebase", "origin", "main")
        if git("push", "origin", "main").returncode == 0:
            print("pushed")
            return
    print("push failed after retries")

if __name__ == "__main__":
    main()
