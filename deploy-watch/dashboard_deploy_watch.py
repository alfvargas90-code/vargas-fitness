#!/usr/bin/env python3
"""dashboard_deploy_watch.py — belt-and-suspenders deploy gate for BOTH fitness
dashboards (root + timing-weather). Auto-commits + pushes ONLY the dashboard
meta files when they change, so hand edits never sit un-pushed (the loop that
broke all day 2026-06-05).

SELF-HEALING CACHE BUST (added 2026-06-06)
------------------------------------------
Each dashboard ships a version.json. When a dashboard's CONTENT (its index.html
or app.js) changes, this gate regenerates that dashboard's version.json with a
fresh timestamp and includes it in the same commit. The browser's inline
version check (top of each index.html) then sees the new version and busts its
own cache — no more delete-and-re-add-the-home-screen dance on iOS. version.json
is regenerated ONLY when content changed, so re-runs on a clean tree never loop.

Fired every 5 minutes by LaunchAgent com.alfredo.dashboard-deploy-watch
(+ RunAtLoad).

WHY PYTHON, NOT THE BASH SCRIPT THE SPEC ASKED FOR
--------------------------------------------------
A launchd-spawned /bin/bash has NO Full Disk Access, so TCC blocks it from the
external /Volumes/Alfie&Co2 volume — it cannot even chdir there
("getcwd: ... Operation not permitted"), let alone run git. Proven 2026-06-05:
the bash entrypoint fired under launchd and died before doing anything.
The working pattern in this repo is polar/sync.py + summary.py, which DO
auto-commit+push from launchd via the python.org Python at
polar/.venv/bin/python3 — that interpreter is FDA-granted, and its git
subprocess inherits the access. This script mirrors that exact pattern, so the
gate actually fires unattended. ~/bin/dashboard-deploy-watch.sh remains as a
thin manual "deploy-now" shim that execs THIS file (one source of logic).

SAFE BY CONSTRUCTION — pathspec-scoped commit
---------------------------------------------
polar-sync routinely leaves polar/*.json and nutrition/*.json STAGED in the
index between its own add and commit. A guard that bailed on any staged
non-watched file would false-fire on nearly every run and brick this watcher.
Instead we commit with an explicit pathspec (`git commit -- <watched files>`) —
git's partial-commit mode commits ONLY the named paths and leaves every other
staged entry untouched. Absorbing polar's staged files is therefore
structurally impossible. A post-commit guard still verifies the new commit
touched ONLY watched files and screams [DEPLOY-UNEXPECTED-STAGED] (undoing the
commit) if that ever fails to hold.

Every failure is LOUD: [DEPLOY-FAIL] + stderr + non-zero exit. Never a silent
exit 0 on a real failure (lesson from the 2026-06-04 silent-401 watchdog).

Source-of-truth + live copy is this in-repo file; it is committed to origin so a
Mac reset can redeploy it (the FDA grant on the python.org interpreter is the
one machine-setup step that must be re-done, same as for polar-sync).
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime

# --- config ------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(SCRIPT_DIR)                       # deploy-watch/ -> repo root

# Each dashboard: a directory (relative to repo root; "" = repo root) and the
# CONTENT files whose change warrants a fresh version stamp. version.json + sw.js
# for each dashboard are derived from `dir` below.
DASHBOARDS = [
    {"name": "fitness",        "dir": "",               "content": ["index.html", "app.js"]},
    {"name": "timing-weather", "dir": "timing-weather", "content": ["timing-weather/index.html",
                                                                    "timing-weather/app.js"]},
]
# Non-dashboard files that still auto-push but get NO version stamp.
EXTRA = ["WHEN_HOME.md", "polar/summary.py"]


def _rel(dash, fname):
    """Repo-relative, forward-slash path for a file inside a dashboard dir."""
    return os.path.join(dash["dir"], fname) if dash["dir"] else fname


CONTENT_FILES = [f for d in DASHBOARDS for f in d["content"]]
VERSION_FILES = [_rel(d, "version.json") for d in DASHBOARDS]
SW_FILES = [_rel(d, "sw.js") for d in DASHBOARDS]
WATCHED = CONTENT_FILES + VERSION_FILES + SW_FILES + EXTRA

STATE_DIR = os.path.expanduser("~/.local/state")
LOG_PATH = os.path.join(STATE_DIR, "dashboard-deploy-watch.log")
LOCKDIR = os.path.join(STATE_DIR, "dashboard-deploy-watch.lock.d")
GIT = "/usr/bin/git"
LSOF = "/usr/sbin/lsof"
LOCK_STALE_SECS = 600   # git locks / self-lock older than this with no git holder = stale


def log(msg):
    os.makedirs(STATE_DIR, exist_ok=True)
    line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} — {msg}\n"
    with open(LOG_PATH, "a") as f:
        f.write(line)


def git(args, **kw):
    return subprocess.run([GIT, *args], cwd=REPO, capture_output=True, text=True, **kw)


def fail(msg, code=1):
    """Loud failure: log [DEPLOY-FAIL], echo to stderr, exit non-zero."""
    log(f"[DEPLOY-FAIL] {msg}")
    sys.stderr.write(f"[DEPLOY-FAIL] {msg}\n")
    _release_lock()
    sys.exit(code)


def stamp_version(dash):
    """Rewrite a dashboard's version.json with a fresh timestamp. Bulletproof:
    raises OSError on write failure (caller turns that into a loud [DEPLOY-FAIL]),
    never leaves a half-written file in place of a deploy."""
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    path = os.path.join(REPO, dash["dir"], "version.json") if dash["dir"] else \
        os.path.join(REPO, "version.json")
    payload = {"version": ts, "built_at": ts}
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


# --- self-mutex: never let two instances overlap ----------------------------
_have_lock = False


def _acquire_lock():
    global _have_lock
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        os.mkdir(LOCKDIR)
        _have_lock = True
        return True
    except FileExistsError:
        try:
            age = time.time() - os.path.getmtime(LOCKDIR)
        except OSError:
            age = 0
        if age > LOCK_STALE_SECS:
            log(f"[self-lock] stale ({age:.0f}s) — clearing and continuing")
            try:
                os.rmdir(LOCKDIR)
            except OSError:
                pass
            try:
                os.mkdir(LOCKDIR)
                _have_lock = True
                return True
            except OSError:
                return False
        # another instance is actively running — let it finish, retry next tick
        return False


def _release_lock():
    global _have_lock
    if _have_lock:
        try:
            os.rmdir(LOCKDIR)
        except OSError:
            pass
        _have_lock = False


# --- stale git-lock sweep + mid-flight detector ------------------------------
def git_lock_held():
    """Ports polar/summary.py::_sweep_stale_git_locks. Returns True if a git
    lock is currently HELD (fresh, or held by a live git process), after
    removing any genuinely stale lock. Incidental readers (Spotlight/mdworker
    indexing the file) do NOT count — skipping on ANY holder is the bug that
    left a 56-min-old HEAD.lock pinned by com.apple on 2026-06-05."""
    held = False
    for name in ("HEAD.lock", "index.lock"):
        path = os.path.join(REPO, ".git", name)
        if not os.path.exists(path):
            continue
        try:
            age = time.time() - os.path.getmtime(path)
        except OSError:
            continue
        if age <= LOCK_STALE_SECS:
            log(f"[stale-lock] held, skipping {name} (age={age:.0f}s, fresh)")
            held = True
            continue
        holders = []
        try:
            out = subprocess.run([LSOF, "--", path], capture_output=True,
                                 text=True, timeout=5)
            holders = [ln.split()[0] for ln in out.stdout.splitlines()[1:] if ln.split()]
        except Exception:
            holders = []
        if any("git" in h.lower() for h in holders):
            log(f"[stale-lock] held by live git process, skipping {name}")
            held = True
            continue
        try:
            os.remove(path)
            if holders:
                log(f"[stale-lock] removed {name} (age={age:.0f}s) — only "
                    f"incidental reader(s): {','.join(sorted(set(holders)))}")
            else:
                log(f"[stale-lock] removed {name} (age={age:.0f}s, no holder)")
        except OSError as e:
            log(f"[stale-lock] could not remove {name}: {e}")
            held = True
    return held


def main():
    if not _acquire_lock():
        return 0  # another instance running — silent, retry next interval

    if not os.path.isdir(os.path.join(REPO, ".git")):
        fail(f"not a git repo (no .git): {REPO}")

    # which watched files actually changed (modified OR staged-not-committed)
    changed = []
    for f in WATCHED:
        st = git(["status", "--porcelain", "--", f])
        if st.stdout.strip():
            changed.append(f)

    # Regenerate version.json for any dashboard whose CONTENT changed, BEFORE
    # staging, so the fresh stamp rides along in this same commit. Only on a real
    # content change — never on a clean tree — so re-runs can't loop.
    for dash in DASHBOARDS:
        if any(c in changed for c in dash["content"]):
            try:
                stamp_version(dash)
            except OSError as e:
                fail(f"could not write version.json for {dash['name']}: {e}")
            vf = _rel(dash, "version.json")
            if vf not in changed:
                changed.append(vf)
            log(f"[version-stamp] {dash['name']} content changed -> bumped {vf}")

    if not changed:
        _release_lock()
        return 0  # clean tree for watched files — exit silently

    # concurrency: defer if another git op is mid-flight
    if git_lock_held():
        time.sleep(5)
        if git_lock_held():
            log(f"[DEPLOY-DEFER] git lock held by another op after 5s retry; "
                f"deferring to next interval (changed: {' '.join(changed)})")
            _release_lock()
            return 0

    # stage ONLY the changed watched files (explicit list, never -A)
    add = git(["add", "--", *changed])
    if add.returncode != 0:
        fail(f"git add exited {add.returncode}: {add.stderr.strip()}")

    pre_sha = git(["rev-parse", "HEAD"]).stdout.strip()
    msg = f"chore(dashboard): deploy-watch sync {datetime.now().strftime('%Y-%m-%d_%H:%M')}"
    commit = git(["commit", "-m", msg, "--", *changed])
    if commit.returncode != 0:
        detail = (commit.stderr.strip() or commit.stdout.strip()).replace("\n", " | ")
        fail(f"git commit exited {commit.returncode}: {detail}", commit.returncode or 1)
    new_sha = git(["rev-parse", "HEAD"]).stdout.strip()

    # post-commit guard: the new commit must touch ONLY watched files
    shown = git(["show", "--name-only", "--pretty=format:", new_sha]).stdout
    committed = [c for c in shown.splitlines() if c.strip()]
    unexpected = [c for c in committed if c not in WATCHED]
    if unexpected:
        log(f"[DEPLOY-UNEXPECTED-STAGED] commit {new_sha} absorbed non-watched "
            f"file(s): {' '.join(unexpected)} — NOT pushing, undoing commit")
        git(["reset", "--soft", pre_sha])   # undo commit, keep changes staged
        _release_lock()
        sys.exit(1)

    # push + verify origin actually moved
    push = git(["push", "origin", "main"])
    if push.returncode != 0:
        detail = (push.stderr.strip() or push.stdout.strip()).replace("\n", " | ")
        fail(f"git push exited {push.returncode}: {detail}", push.returncode or 1)

    ls = git(["ls-remote", "origin", "-h", "refs/heads/main"])
    remote_sha = ls.stdout.split()[0] if ls.stdout.split() else ""
    if remote_sha != new_sha:
        fail(f"push reported success but origin/main={remote_sha} != local {new_sha}")

    log(f"[DEPLOY-OK] pushed {new_sha} (origin/main verified) — files: {' '.join(changed)}")
    _release_lock()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:  # never crash silently
        fail(f"unhandled exception: {type(e).__name__}: {e}")
