#!/usr/bin/env python3
"""
Polar AccessLink -> vault sync for Polar Loop Gen 2 (activity tracker).

First run (empty POLAR_ACCESS_TOKEN): runs the OAuth dance — opens the browser
to Polar's auth page, captures the callback on http://localhost:5000, exchanges
the code for a token, registers the user, and writes the token + user id back to
.env. You only do this once.

Every run after that: pulls recent daily activity, sleep, and nightly recharge
and writes one JSON file per day per category. Idempotent — a date that already
has a file is skipped, never overwritten. A manifest.json index is rebuilt each
run so the dashboard knows which dates exist.

Deps (in polar/.venv): requests, python-dotenv. OAuth callback uses the stdlib
http.server — no Flask needed.
"""
import base64
import json
import os
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

# --- paths ---------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))         # .../fitness-dashboard/polar
REPO_ROOT = os.path.dirname(HERE)                          # .../fitness-dashboard (the git repo)
ENV_PATH = os.path.join(HERE, ".env")
CATEGORIES = ("daily_activity", "sleep", "recharge")

# Deployable paths the daily sync is allowed to commit (relative to REPO_ROOT).
# The token-bearing remote URL lives in .git/config (local only) — never here,
# since this file is public. .env is gitignored; we also never `git add` it.
GIT_PUSH_PATHS = (
    "index.html", "fitness_dashboard.html", "app.js", "data.js", "serve.py",
    "manifest.json", "apple-touch-icon.png", "icon-192.png", "icon-512.png",
    "polar/sync.py", "polar/requirements.txt",
    "polar/manifest.json", "polar/daily_activity", "polar/sleep", "polar/recharge",
)

# --- Polar endpoints -----------------------------------------------------
AUTH_URL = "https://flow.polar.com/oauth2/authorization"
TOKEN_URL = "https://polarremote.com/v2/oauth2/token"
API = "https://www.polaraccesslink.com"
SCOPE = "accesslink.read_all"


def log(msg):
    print(msg, flush=True)


# --- .env read/write -----------------------------------------------------
def load_env():
    """Use python-dotenv if present, else a simple KEY=VALUE parse."""
    env = {}
    try:
        from dotenv import dotenv_values
        env = dict(dotenv_values(ENV_PATH))
    except Exception:
        with open(ENV_PATH) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return {k: v for k, v in env.items() if v is not None}


def write_env_value(key, value):
    """Rewrite a single KEY=value line in .env, preserving everything else."""
    with open(ENV_PATH) as fh:
        lines = fh.readlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}\n")
    with open(ENV_PATH, "w") as fh:
        fh.writelines(lines)


# --- OAuth dance ---------------------------------------------------------
class _CallbackHandler(BaseHTTPRequestHandler):
    code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        _CallbackHandler.code = params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        body = (
            "<h2>Polar authorization received.</h2>"
            "<p>You can close this window and return to the terminal.</p>"
            if _CallbackHandler.code
            else "<h2>No authorization code received.</h2>"
        )
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass  # silence default request logging


def oauth_dance(client_id, client_secret, redirect_uri):
    parsed = urllib.parse.urlparse(redirect_uri)
    host, port = parsed.hostname or "localhost", parsed.port or 5000

    auth_link = AUTH_URL + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "scope": SCOPE,
        "redirect_uri": redirect_uri,
    })
    log("Opening Polar authorization in your browser. Click 'Allow'.")
    log(f"If it doesn't open, visit:\n  {auth_link}")

    server = HTTPServer((host, port), _CallbackHandler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    try:
        webbrowser.open(auth_link)
    except Exception:
        pass

    log("Waiting for the callback on " + redirect_uri + " ...")
    # handle_request serves exactly one request, then the thread ends.
    server_thread_done = threading.Event()

    def wait():
        while _CallbackHandler.code is None and not server_thread_done.is_set():
            server_thread_done.wait(0.5)

    import time
    deadline = 300  # 5 min
    waited = 0
    while _CallbackHandler.code is None and waited < deadline:
        time.sleep(0.5)
        waited += 0.5
    server.server_close()

    code = _CallbackHandler.code
    if not code:
        log("ERROR: no authorization code captured (timed out). Re-run to retry.")
        sys.exit(1)

    # exchange code -> token (HTTP Basic auth with client id/secret)
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    resp.raise_for_status()
    tok = resp.json()
    access_token = tok["access_token"]
    user_id = str(tok.get("x_user_id", ""))

    # register the user with this application (idempotent: 409 = already linked)
    reg = requests.post(
        f"{API}/v3/users",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps({"member-id": f"alfie-{user_id or 'loop'}"}),
        timeout=30,
    )
    if reg.status_code not in (200, 201, 409):
        log(f"WARN: user registration returned {reg.status_code}: {reg.text[:200]}")
    if not user_id and reg.status_code in (200, 201):
        try:
            user_id = str(reg.json().get("polar-user-id", ""))
        except Exception:
            pass

    write_env_value("POLAR_ACCESS_TOKEN", access_token)
    write_env_value("POLAR_USER_ID", user_id)
    log(f"OAuth complete. Token + user id ({user_id}) saved to .env.")
    return access_token, user_id


# --- data pull -----------------------------------------------------------
def _headers(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _save_day(category, day, payload):
    """Write polar/<category>/<day>.json. Skip if it already exists."""
    folder = os.path.join(HERE, category)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{day}.json")
    if os.path.exists(path):
        return False
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=2)
    return True


def pull_recharge(token):
    """GET /v3/users/nightly-recharge — returns up to the last 28 nights."""
    r = requests.get(f"{API}/v3/users/nightly-recharge", headers=_headers(token), timeout=30)
    if r.status_code == 204:
        return 0
    r.raise_for_status()
    items = r.json().get("recharges", [])
    n = sum(1 for it in items if it.get("date") and _save_day("recharge", it["date"], it))
    log(f"  recharge: {len(items)} nights returned, {n} new")
    return n


def pull_sleep(token):
    """GET /v3/users/sleep — last nights of sleep with stage breakdown."""
    r = requests.get(f"{API}/v3/users/sleep", headers=_headers(token), timeout=30)
    if r.status_code == 204:
        return 0
    r.raise_for_status()
    items = r.json().get("nights", [])
    n = sum(1 for it in items if it.get("date") and _save_day("sleep", it["date"], it))
    log(f"  sleep: {len(items)} nights returned, {n} new")
    return n


def pull_daily_activity(token, user_id):
    """Daily activity uses the transaction model: open -> list -> fetch -> commit."""
    tx = requests.post(
        f"{API}/v3/users/{user_id}/activity-transactions",
        headers=_headers(token), timeout=30,
    )
    if tx.status_code == 204:
        log("  daily_activity: no new data")
        return 0
    tx.raise_for_status()
    tx_id = tx.json().get("transaction-id")
    tx_base = f"{API}/v3/users/{user_id}/activity-transactions/{tx_id}"
    listing = requests.get(tx_base, headers=_headers(token), timeout=30)
    listing.raise_for_status()
    urls = listing.json().get("activity-log", [])
    n = 0
    for url in urls:
        detail = requests.get(url, headers=_headers(token), timeout=30)
        if detail.status_code != 200:
            continue
        data = detail.json()
        day = (data.get("date") or "")[:10]
        if day and _save_day("daily_activity", day, data):
            n += 1
    # commit the transaction so Polar advances the cursor
    requests.put(tx_base, headers=_headers(token), timeout=30)
    log(f"  daily_activity: {len(urls)} summaries, {n} new")
    return n


def rebuild_manifest():
    """Index available dates per category so the dashboard can load them."""
    manifest = {"generated": date.today().isoformat(), "categories": {}}
    for cat in CATEGORIES:
        folder = os.path.join(HERE, cat)
        dates = []
        if os.path.isdir(folder):
            dates = sorted(
                f[:-5] for f in os.listdir(folder) if f.endswith(".json")
            )
        manifest["categories"][cat] = dates
    with open(os.path.join(HERE, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)


# --- git push (deploy to GitHub Pages) -----------------------------------
def git_push():
    """Commit the deployable subset and push to origin/main.

    Best-effort: any git failure logs a warning and returns without raising,
    so a transient network/auth hiccup never blocks the cron or causes retries.
    The token lives in the remote URL (.git/config, local only) — never .env,
    never this file. .env is gitignored and never added here.
    """
    def git(*args):
        return subprocess.run(
            ["git", "-C", REPO_ROOT, *args],
            capture_output=True, text=True, timeout=120,
        )
    if not os.path.isdir(os.path.join(REPO_ROOT, ".git")):
        log("  git: no repo at " + REPO_ROOT + " — skipping push")
        return
    try:
        # Stage only the allowlisted deployable paths that actually exist.
        present = [p for p in GIT_PUSH_PATHS if os.path.exists(os.path.join(REPO_ROOT, p))]
        git("add", "--", *present)
        # Nothing staged? (no new data) — skip the commit/push quietly.
        if git("diff", "--cached", "--quiet").returncode == 0:
            log("  git: no changes to push")
            return
        msg = f"chore: sync {date.today().isoformat()} data"
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
    env = load_env()
    client_id = env.get("POLAR_CLIENT_ID")
    client_secret = env.get("POLAR_CLIENT_SECRET")
    redirect_uri = env.get("POLAR_REDIRECT_URI", "http://localhost:5000/oauth2_callback")
    token = env.get("POLAR_ACCESS_TOKEN") or ""
    user_id = env.get("POLAR_USER_ID") or ""

    if not client_id or not client_secret:
        log("ERROR: POLAR_CLIENT_ID / POLAR_CLIENT_SECRET missing from .env")
        sys.exit(1)

    if not token:
        log("No access token yet — starting one-time OAuth dance.")
        token, user_id = oauth_dance(client_id, client_secret, redirect_uri)

    log(f"Syncing Polar data ({date.today().isoformat()}) ...")
    new_total = 0
    for name, fn in (
        ("recharge", lambda: pull_recharge(token)),
        ("sleep", lambda: pull_sleep(token)),
        ("daily_activity", lambda: pull_daily_activity(token, user_id)),
    ):
        try:
            new_total += fn() or 0
        except requests.HTTPError as e:
            sc = e.response.status_code if e.response is not None else "?"
            if sc == 401:
                log("ERROR: token rejected (401). Clear POLAR_ACCESS_TOKEN in .env to re-auth.")
                sys.exit(2)
            log(f"  {name}: HTTP {sc} — skipped ({str(e)[:120]})")
        except Exception as e:
            log(f"  {name}: error — skipped ({str(e)[:120]})")

    rebuild_manifest()
    log(f"Done. {new_total} new day-files written.")
    git_push()  # best-effort deploy to GitHub Pages; never fatal
    sys.exit(0)


if __name__ == "__main__":
    main()
