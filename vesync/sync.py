#!/usr/bin/env python3
"""
VeSync smart-scale -> vault sync (Etekcity / Cosori fat scale).

STUB / AWAITING CREDENTIALS (2026-06-01). pyvesync 2.1.18 does NOT wrap the
scale (see RECON_NOTES.md), so the flow is:
  1. log in via pyvesync (it hashes the password + manages the session),
  2. borrow manager.token / manager.account_id,
  3. POST directly to the fat-scale endpoint to pull body-comp readings.

The exact request/response field names for the fat-scale endpoint are not
pinned without a live account — the marked TODO/VERIFY spots below are where
the first real run will need a tweak. Everything else (auth, device discovery,
file writing, git push, logging) follows the proven polar/sync.py pattern.

Deps (in vesync/.venv): pyvesync==2.1.18, requests. Python 3.9.
"""
import json
import os
import subprocess
import sys
from datetime import date, datetime

import requests

# --- paths ---------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))      # .../fitness-dashboard/vesync
REPO_ROOT = os.path.dirname(HERE)                       # .../fitness-dashboard (git repo)
ENV_PATH = os.path.join(HERE, ".env")
DAILY_DIR = os.path.join(HERE, "daily")

# Deployable paths the daily sync may commit (relative to REPO_ROOT). The
# token-bearing remote URL lives in .git/config (local only) — never here.
# .env is gitignored and never `git add`-ed.
GIT_PUSH_PATHS = (
    "vesync/sync.py", "vesync/requirements.txt",
    "vesync/manifest.json", "vesync/daily",
)

# --- VeSync API (constants mirror pyvesync.helpers) -----------------------
API_BASE = "https://smartapi.vesync.com"
DEVICES_EP = "/cloud/v1/deviceManaged/devices"
FATSCALE_EP = "/cloud/v1/deviceManaged/fatScale/getWeighData"
# Substrings that flag a device as a scale in the raw device list.
SCALE_HINTS = ("scale", "esf", "fatscale", "weigh")


def log(msg):
    print(msg, flush=True)


# --- .env read -----------------------------------------------------------
def load_env():
    """Simple KEY=VALUE parse (no python-dotenv dependency)."""
    env = {}
    with open(ENV_PATH) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


# --- auth via pyvesync ---------------------------------------------------
def authenticate(email, password, tz):
    """Log in through pyvesync; return (manager, token, account_id)."""
    from pyvesync import VeSync
    manager = VeSync(email, password, time_zone=tz)
    if not manager.login():
        log("ERROR: VeSync login failed — check VESYNC_EMAIL / VESYNC_PASSWORD.")
        sys.exit(2)
    log(f"  auth: logged in (account {manager.account_id[:6]}…).")
    return manager, manager.token, manager.account_id


def _base_body(manager):
    """req_body_base + req_body_auth, the universal envelope for cloud calls."""
    return {
        "timeZone": manager.time_zone,
        "acceptLanguage": "en",
        "accountID": manager.account_id,
        "token": manager.token,
    }


def _headers(manager):
    return {
        "accept-language": "en",
        "accountId": manager.account_id,
        "appVersion": "2.8.6",
        "content-type": "application/json",
        "tk": manager.token,
        "tz": manager.time_zone,
    }


# --- device discovery (raw list — get_devices() hides the scale) ---------
def find_scale(manager, pinned_cid=""):
    """POST the raw device list, return the scale device dict (or None)."""
    body = _base_body(manager)
    body |= {"method": "devices", "pageNo": "1", "pageSize": "100"}
    r = requests.post(API_BASE + DEVICES_EP, json=body,
                      headers=_headers(manager), timeout=30)
    r.raise_for_status()
    devices = (r.json().get("result") or {}).get("list") or []
    log(f"  devices: {len(devices)} found in account.")
    if pinned_cid:
        for d in devices:
            if d.get("cid") == pinned_cid:
                return d
        log(f"  WARN: pinned VESYNC_DEVICE_ID {pinned_cid} not in account.")
    for d in devices:
        hay = f"{d.get('deviceType','')} {d.get('configModule','')} {d.get('deviceName','')}".lower()
        if any(h in hay for h in SCALE_HINTS):
            return d
    return None


# --- fat-scale reading ---------------------------------------------------
def fetch_weigh_data(manager, scale):
    """POST the fat-scale endpoint, return the latest reading parsed.

    VERIFY (first real run): the body field names and the response shape below
    are best-guesses from community captures — adjust against the logged raw
    response. See RECON_NOTES.md "Open items".
    """
    body = _base_body(manager)
    body |= {
        "method": "getWeighData",
        "page": 1,
        "pageSize": 100,
        "uuid": scale.get("uuid"),
        "configModule": scale.get("configModule"),
        "configModel": scale.get("configModule"),
        "cid": scale.get("cid"),
        # "subUserID": ...,  # TODO: some accounts require the profile/sub-user id
    }
    r = requests.post(API_BASE + FATSCALE_EP, json=body,
                      headers=_headers(manager), timeout=30)
    r.raise_for_status()
    payload = r.json()
    log(f"  fatScale: raw response code={payload.get('code')} msg={payload.get('msg')}")

    # VERIFY: result container + reading list key names.
    result = payload.get("result") or {}
    readings = (result.get("weighDataList") or result.get("list")
                or result.get("weightDataList") or [])
    if not readings:
        log("  fatScale: no readings returned (step on the scale, then re-run).")
        log(f"  fatScale: full payload for mapping → {json.dumps(payload)[:600]}")
        return None

    latest = readings[0]  # VERIFY: confirm ordering (newest first vs last)
    return parse_reading(latest)


def parse_reading(r):
    """Map a raw reading to the dashboard's body-comp fields.

    VERIFY: key names + units (VeSync is metric: kg). Returns None-safe floats.
    """
    def g(*keys):
        for k in keys:
            if k in r and r[k] is not None:
                return r[k]
        return None

    ts = g("weighTimestamp", "timestamp", "weightTime", "createTime")
    day = None
    if ts:
        try:
            # epoch seconds or ms
            sec = int(ts) / (1000 if int(ts) > 10**12 else 1)
            day = datetime.utcfromtimestamp(sec).date().isoformat()
        except (ValueError, TypeError):
            day = str(ts)[:10]
    return {
        "date": day or date.today().isoformat(),
        "raw_timestamp": ts,
        "weight_kg": g("weight", "weightG", "bodyWeight"),
        "body_fat_pct": g("bodyFat", "bodyFatRate", "fat"),
        "bmi": g("bmi", "BMI"),
        "muscle_mass_kg": g("muscleMass", "muscle"),
        "body_water_pct": g("waterRate", "bodyWater", "water"),
        "bmr": g("bmr", "BMR", "basalMetabolism"),
        "visceral_fat": g("visceralFat", "visceralFatLevel", "visceral"),
        "_raw": r,  # keep raw so we can refine the mapping later
    }


def save_reading(reading):
    """Write daily/<YYYY-MM-DD>.json. Overwrite same-day (latest wins)."""
    os.makedirs(DAILY_DIR, exist_ok=True)
    path = os.path.join(DAILY_DIR, f"{reading['date']}.json")
    with open(path, "w") as fh:
        json.dump(reading, fh, indent=2)
    log(f"  saved: daily/{reading['date']}.json "
        f"({reading.get('weight_kg')}kg, {reading.get('body_fat_pct')}% fat)")
    return path


def rebuild_manifest():
    """Index available reading dates so the dashboard can load them."""
    dates = []
    if os.path.isdir(DAILY_DIR):
        dates = sorted(f[:-5] for f in os.listdir(DAILY_DIR) if f.endswith(".json"))
    with open(os.path.join(HERE, "manifest.json"), "w") as fh:
        json.dump({"generated": date.today().isoformat(), "dates": dates}, fh, indent=2)


# --- git push (deploy to GitHub Pages) -----------------------------------
def git_push():
    """Commit the deployable subset and push. Best-effort — never fatal."""
    def git(*args):
        return subprocess.run(["git", "-C", REPO_ROOT, *args],
                              capture_output=True, text=True, timeout=120)
    if not os.path.isdir(os.path.join(REPO_ROOT, ".git")):
        log("  git: no repo — skipping push")
        return
    try:
        present = [p for p in GIT_PUSH_PATHS
                   if os.path.exists(os.path.join(REPO_ROOT, p))]
        git("add", "--", *present)
        if git("diff", "--cached", "--quiet").returncode == 0:
            log("  git: no changes to push")
            return
        msg = f"chore(vesync): sync {date.today().isoformat()} weigh-in"
        c = git("commit", "-m", msg)
        if c.returncode != 0:
            log(f"  git: commit failed — {(c.stderr or c.stdout).strip()[:160]}")
            return
        p = git("push", "origin", "HEAD:main")
        if p.returncode != 0:
            log(f"  git: push failed (non-fatal) — {(p.stderr or p.stdout).strip()[:160]}")
            return
        log(f"  git: pushed — {msg}")
    except Exception as e:
        log(f"  git: error (non-fatal) — {str(e)[:160]}")


# --- main ----------------------------------------------------------------
def main():
    if not os.path.exists(ENV_PATH):
        log("create .env from .env.example with your VeSync credentials")
        sys.exit(1)

    env = load_env()
    email = env.get("VESYNC_EMAIL")
    password = env.get("VESYNC_PASSWORD")
    tz = env.get("VESYNC_TIMEZONE") or "America/Chicago"
    pinned = env.get("VESYNC_DEVICE_ID") or ""
    if not email or not password or "example.com" in email:
        log("create .env from .env.example with your VeSync credentials")
        sys.exit(1)

    log(f"Syncing VeSync scale ({date.today().isoformat()}) …")
    manager, _, _ = authenticate(email, password, tz)

    scale = find_scale(manager, pinned)
    if not scale:
        log("  ERROR: no scale found in account. Devices may use an unexpected "
            "type string — re-run with the device list logged and update "
            "SCALE_HINTS, or pin VESYNC_DEVICE_ID.")
        sys.exit(3)
    log(f"  scale: {scale.get('deviceName')} "
        f"(cid={scale.get('cid')}, type={scale.get('deviceType')})")

    reading = fetch_weigh_data(manager, scale)
    if reading:
        save_reading(reading)
    rebuild_manifest()
    git_push()  # best-effort deploy; never fatal
    sys.exit(0)


if __name__ == "__main__":
    main()
