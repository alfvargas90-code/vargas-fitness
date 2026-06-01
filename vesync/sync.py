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
USERINFO_EP = "/cloud/v1/user/getUserInfo"
# The fatScale/getWeighData (v1) + getWeighingDataV2 (v2) history endpoints
# DO work now (RECON_NOTES 2026-06-01 cracked the shape: appVersion 3.0.20 +
# lowercase app headers; -11000079 just meant "illegal argument"). But this
# ESF-551 is Bluetooth-only (cid=null) — its readings live in the phone app,
# not the cloud, so weightDatas comes back empty. VeSync keeps only a profile
# snapshot (weightG + initialBfr) via getUserInfo, which is what we read.
# Substrings that flag a body-fat scale. "esf"/"fatscale" are body-comp; we
# must NOT match the food/NutritionScale (deviceType ESN…, also named "scale").
SCALE_HINTS = ("esf", "fatscale")
SCALE_EXCLUDE = ("nutrition", "esn")


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
    """Universal envelope for cloud calls: base + auth + details.

    The device-list and getUserInfo endpoints reject a body missing the
    "details" keys (appVersion/phoneBrand/phoneOS/traceId) with
    "illegal argument" — pyvesync's own Helpers build the exact set, so we
    borrow them rather than hardcode constants that drift across versions.
    """
    from pyvesync.helpers import Helpers
    body = Helpers.req_body_base(manager)
    body |= Helpers.req_body_auth(manager)
    body |= Helpers.req_body_details()
    return body


# --- device discovery (raw list — get_devices() hides the scale) ---------
def find_scale(manager, pinned_id=""):
    """POST the raw device list, return the body-fat scale dict (or None).

    ESF-551 BLE scales report cid=None, so VESYNC_DEVICE_ID pins by uuid.
    The account may also hold a NutritionScale (food scale, also named
    "…scale") — SCALE_EXCLUDE keeps us off it.
    """
    body = _base_body(manager)
    body |= {"method": "devices", "pageNo": "1", "pageSize": "100"}
    r = requests.post(API_BASE + DEVICES_EP, json=body, timeout=30)
    r.raise_for_status()
    devices = (r.json().get("result") or {}).get("list") or []
    log(f"  devices: {len(devices)} found in account.")
    if pinned_id:
        for d in devices:
            if pinned_id in (d.get("uuid"), d.get("cid")):
                return d
        log(f"  WARN: pinned VESYNC_DEVICE_ID {pinned_id} not in account.")
    for d in devices:
        hay = f"{d.get('deviceType','')} {d.get('configModule','')} {d.get('deviceName','')}".lower()
        if any(x in hay for x in SCALE_EXCLUDE):
            continue
        if any(h in hay for h in SCALE_HINTS):
            return d
    return None


# --- body-comp reading (from the user profile) ---------------------------
def fetch_reading(manager):
    """Pull the body-comp snapshot from getUserInfo.

    The ESF-551 syncs over Bluetooth and VeSync stamps the latest weigh-in
    onto the user profile (weightG + initialBfr). The per-reading history
    endpoint (fatScale/getWeighData) rejected every body we tried on this
    account, so getUserInfo is the working source. It carries weight + body
    fat only — BMI is derived from height; muscle/water/BMR/visceral are not
    exposed here and stay null until/unless the history endpoint is cracked.
    """
    body = _base_body(manager)
    body |= {"method": "getUserInfo"}
    r = requests.post(API_BASE + USERINFO_EP, json=body, timeout=30)
    r.raise_for_status()
    payload = r.json()
    log(f"  userInfo: code={payload.get('code')} msg={payload.get('msg')}")
    res = payload.get("result") or {}
    if payload.get("code") not in (0, None) or not res:
        log(f"  userInfo: unexpected payload → {json.dumps(payload)[:400]}")
        return None
    return parse_reading(res)


def parse_reading(res):
    """Map a getUserInfo result to the dashboard's body-comp fields.

    Weight is metric grams (weightG); body fat is a rate %. real_weight_* is
    the live BLE value (0 until a fresh step-on); weightG holds the last
    stored weigh-in, so we prefer real_weight when present and fall back to
    weightG. Returns None-safe floats.
    """
    def num(*keys):
        for k in keys:
            v = res.get(k)
            if v not in (None, "", 0, 0.0):
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
        return None

    weight_kg = num("real_weight_kg") or (
        (num("weightG") / 1000.0) if num("weightG") else None)
    body_fat = num("currentBfr", "bfr", "initialBfr")
    height_cm = num("heightCm")
    bmi = round(weight_kg / (height_cm / 100.0) ** 2, 1) if (weight_kg and height_cm) else None

    ts = res.get("statusUpdateTimestamp") or res.get("initialTimestamp")
    day = date.today().isoformat()
    if ts:
        try:
            sec = int(ts) / (1000 if int(ts) > 10 ** 12 else 1)
            day = datetime.utcfromtimestamp(sec).date().isoformat()
        except (ValueError, TypeError):
            pass

    return {
        "date": day,
        "raw_timestamp": ts,
        "weight_kg": round(weight_kg, 3) if weight_kg else None,
        "weight_lb": round(weight_kg * 2.2046226, 1) if weight_kg else None,
        "body_fat_pct": body_fat,
        "bmi": bmi,
        "height_cm": height_cm,
        # Not exposed by getUserInfo for this scale — need the history endpoint.
        "muscle_mass_kg": None,
        "body_water_pct": None,
        "bmr": None,
        "visceral_fat": None,
        "source": "vesync:getUserInfo",
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
    if scale:
        log(f"  scale: {scale.get('deviceName')} "
            f"(type={scale.get('deviceType')}, uuid={scale.get('uuid')})")
    else:
        log("  WARN: no body-fat scale matched in the device list — reading "
            "from the user profile anyway (it is account-level, not per-device).")

    reading = fetch_reading(manager)
    if reading and (reading.get("weight_kg") or reading.get("body_fat_pct")):
        save_reading(reading)
    else:
        log("  ERROR: no usable weight/body-fat in the profile snapshot.")
        sys.exit(3)
    rebuild_manifest()
    git_push()  # best-effort deploy; never fatal
    sys.exit(0)


if __name__ == "__main__":
    main()
