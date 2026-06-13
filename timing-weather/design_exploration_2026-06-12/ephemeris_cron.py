#!/usr/bin/env python3
"""
Keeps ephemeris.json fresh for the Three-Lens astrology dashboard.

Regenerates the Swiss-Ephemeris snapshot (ephemeris.py) and commits+pushes the
updated ephemeris.json to main so GitHub Pages serves current transits. Run by a
launchd LaunchAgent a few times a day via the FDA python (polar/.venv) — launchd
bash is TCC-blocked from the external volume, so this is a python entry point.

Self-contained: pulls --rebase before pushing so it never fights the polar-sync /
deploy-watch jobs that also commit to this repo.
"""
import os, subprocess, importlib.util

REPO = "/Volumes/Alfie&Co2/alfredo.v/04_Projects/fitness-dashboard"
SUBDIR = os.path.join(REPO, "timing-weather/design_exploration_2026-06-12")
LIVE = os.path.join(REPO, "timing-weather")        # the live PWA serves ephemeris.json from here
# refresh BOTH the live PWA copy and the dev/exploration copy
RELS = ["timing-weather/ephemeris.json",
        "timing-weather/design_exploration_2026-06-12/ephemeris.json"]

def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True)

def regen(outdir):
    os.chdir(outdir)
    spec = importlib.util.spec_from_file_location("ephem", os.path.join(SUBDIR, "ephemeris.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()

def main():
    # 1) regenerate ephemeris.json into the live PWA dir AND the exploration dir
    regen(LIVE)
    regen(SUBDIR)

    # 2) commit + push only the json files (rebase to avoid racing the other auto-commit jobs)
    git("add", *RELS)
    if git("diff", "--cached", "--quiet").returncode == 0:
        print("no change")
        return
    git("commit", "-m", "chore: refresh astro ephemeris.json")
    for _ in range(3):
        git("pull", "--rebase", "origin", "main")
        if git("push", "origin", "main").returncode == 0:
            print("pushed")
            return
    print("push failed after retries")

if __name__ == "__main__":
    main()
