#!/usr/bin/env python3
"""
Calories Club (recordo.app) MCP -> vault sync.

OAuth 2.1 public client with PKCE. First run (empty NUTRITION_ACCESS_TOKEN):
runs the OAuth dance — opens the browser to recordo's consent screen with a
PKCE challenge, captures the callback on http://localhost:5001, exchanges the
code (+ verifier) for access + refresh tokens, writes them back to .env.

Every run after that: refreshes the access token if expired (refresh_token
grant), opens an MCP streamable-HTTP session (initialize -> tools/list ->
tools/call), pulls today's macros, and writes nutrition/daily/<YYYY-MM-DD>.json.
Idempotent on a per-run basis — today's file is always rewritten with the
latest numbers (macros change through the day), older days are never touched.

Deps (in polar/.venv): requests, python-dotenv. Reuses the polar venv.
"""
import base64
import hashlib
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

# --- paths ---------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))          # .../fitness-dashboard/nutrition
REPO_ROOT = os.path.dirname(HERE)                          # .../fitness-dashboard
ENV_PATH = os.path.join(HERE, ".env")
DAILY_DIR = os.path.join(HERE, "daily")

MCP_PROTOCOL_VERSION = "2025-03-26"


def log(msg):
    print(msg, flush=True)


# --- .env read/write -----------------------------------------------------
def load_env():
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
    return {k: (v or "") for k, v in env.items()}


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


# --- PKCE ----------------------------------------------------------------
def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def make_pkce():
    verifier = _b64url(secrets.token_bytes(64))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


# --- OAuth dance ---------------------------------------------------------
class _CallbackHandler(BaseHTTPRequestHandler):
    code = None
    state = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        _CallbackHandler.code = params.get("code", [None])[0]
        _CallbackHandler.state = params.get("state", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        body = (
            "<h2>Calories Club authorization received.</h2>"
            "<p>You can close this window and return to the terminal.</p>"
            if _CallbackHandler.code
            else "<h2>No authorization code received.</h2>"
        )
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass


def oauth_dance(env):
    client_id = env["NUTRITION_CLIENT_ID"]
    redirect_uri = env["NUTRITION_REDIRECT_URI"]
    scope = env.get("NUTRITION_SCOPE", "")
    auth_endpoint = env["NUTRITION_AUTH_ENDPOINT"]
    token_endpoint = env["NUTRITION_TOKEN_ENDPOINT"]

    parsed = urllib.parse.urlparse(redirect_uri)
    host, port = parsed.hostname or "localhost", parsed.port or 5001

    verifier, challenge = make_pkce()
    state = secrets.token_urlsafe(16)

    # auth_endpoint already carries ?app=calories — append with & via urlencode
    sep = "&" if "?" in auth_endpoint else "?"
    auth_link = auth_endpoint + sep + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })

    server = HTTPServer((host, port), _CallbackHandler)
    threading.Thread(target=server.handle_request, daemon=True).start()

    log("")
    log("=== READY FOR ALFIE: browser tab opening in 3 seconds. Click Allow on Calories Club consent screen. ===")
    log(f"If it doesn't open, visit:\n  {auth_link}")
    log("")
    time.sleep(3)
    try:
        webbrowser.open(auth_link)
    except Exception:
        pass

    log(f"Waiting for the callback on {redirect_uri} ...")
    deadline = 300
    waited = 0.0
    while _CallbackHandler.code is None and waited < deadline:
        time.sleep(0.5)
        waited += 0.5
    server.server_close()

    code = _CallbackHandler.code
    if not code:
        log("ERROR: no authorization code captured (timed out). Re-run to retry.")
        sys.exit(1)
    if _CallbackHandler.state != state:
        log("ERROR: state mismatch — possible CSRF. Aborting.")
        sys.exit(1)

    resp = requests.post(
        token_endpoint,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        log(f"ERROR: token exchange failed {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)
    _store_tokens(resp.json())
    log("OAuth complete. Tokens saved to .env.")
    return load_env()


def refresh_access_token(env):
    refresh_token = env.get("NUTRITION_REFRESH_TOKEN", "")
    if not refresh_token:
        return None
    resp = requests.post(
        env["NUTRITION_TOKEN_ENDPOINT"],
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": env["NUTRITION_CLIENT_ID"],
        },
        timeout=30,
    )
    if resp.status_code != 200:
        log(f"WARN: refresh failed {resp.status_code}: {resp.text[:200]} — re-running OAuth dance.")
        return None
    _store_tokens(resp.json())
    log("Access token refreshed.")
    return load_env()


def _store_tokens(tok):
    write_env_value("NUTRITION_ACCESS_TOKEN", tok["access_token"])
    if tok.get("refresh_token"):
        write_env_value("NUTRITION_REFRESH_TOKEN", tok["refresh_token"])
    expires_in = tok.get("expires_in")
    if expires_in:
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))).isoformat()
        write_env_value("NUTRITION_TOKEN_EXPIRES_AT", expires_at)


def token_expired(env):
    exp = env.get("NUTRITION_TOKEN_EXPIRES_AT", "")
    if not exp:
        return False
    try:
        return datetime.now(timezone.utc) >= datetime.fromisoformat(exp) - timedelta(seconds=60)
    except Exception:
        return False


def ensure_token(env):
    """Return env with a usable access token, refreshing or re-authing as needed."""
    if not env.get("NUTRITION_ACCESS_TOKEN"):
        return oauth_dance(env)
    if token_expired(env):
        refreshed = refresh_access_token(env)
        if refreshed:
            return refreshed
        return oauth_dance(env)
    return env


# --- MCP streamable-HTTP client -----------------------------------------
class MCPClient:
    def __init__(self, url, token):
        self.url = url
        self.token = token
        self.session_id = None
        self._id = 0

    def _headers(self):
        h = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _next_id(self):
        self._id += 1
        return self._id

    @staticmethod
    def _parse(resp):
        """Return the JSON-RPC payload from a JSON or SSE response.

        recordo's SSE frames embed raw (non-data:-prefixed) newlines inside the
        JSON, so naive per-line parsing truncates the payload. We instead take
        everything after the first `data:` marker and parse the JSON span.
        """
        ctype = resp.headers.get("Content-Type", "")
        text = resp.text
        if "text/event-stream" in ctype:
            idx = text.find("data:")
            if idx == -1:
                return None
            blob = text[idx + len("data:"):].strip()
            if not blob or blob == "[DONE]":
                return None
            try:
                return json.loads(blob)
            except json.JSONDecodeError:
                start, end = blob.find("{"), blob.rfind("}")
                if start != -1 and end != -1:
                    return json.loads(blob[start:end + 1])
                return None
        if not text.strip():
            return None
        return resp.json()

    def _rpc(self, method, params=None, notify=False):
        body = {"jsonrpc": "2.0", "method": method}
        if not notify:
            body["id"] = self._next_id()
        if params is not None:
            body["params"] = params
        resp = requests.post(self.url, headers=self._headers(),
                             data=json.dumps(body), timeout=60)
        # capture session id offered by the server on initialize
        sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        if resp.status_code >= 400:
            raise RuntimeError(f"{method} -> HTTP {resp.status_code}: {resp.text[:300]}")
        if notify:
            return None
        payload = self._parse(resp)
        if payload is None:
            raise RuntimeError(f"{method} -> empty/unparseable response: {resp.text[:300]}")
        if "error" in payload:
            raise RuntimeError(f"{method} -> JSON-RPC error: {payload['error']}")
        return payload.get("result")

    def initialize(self):
        result = self._rpc("initialize", {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "vargas-fitness-dashboard", "version": "1.0"},
        })
        self._rpc("notifications/initialized", notify=True)
        return result

    def list_tools(self):
        return (self.list_tools_raw() or {}).get("tools", [])

    def list_tools_raw(self):
        return self._rpc("tools/list")

    def call_tool(self, name, arguments=None):
        return self._rpc("tools/call", {"name": name, "arguments": arguments or {}})


# --- tool selection + extraction ----------------------------------------
def pick_macros_tool(tools):
    """Heuristic: prefer a tool whose name mentions today/daily/summary/macros."""
    names = {t["name"]: t for t in tools}
    priority = ("today", "daily", "summary", "macro", "nutrition", "diary", "log", "entries")
    for kw in priority:
        for n in names:
            if kw in n.lower():
                return names[n]
    return tools[0] if tools else None


def tool_result_to_obj(result):
    """MCP tools/call result -> python object. Prefer structuredContent, else parse text."""
    if not isinstance(result, dict):
        return result
    if result.get("structuredContent"):
        return result["structuredContent"]
    content = result.get("content", [])
    for block in content:
        if block.get("type") == "text":
            txt = block.get("text", "")
            try:
                return json.loads(txt)
            except json.JSONDecodeError:
                return {"text": txt}
    return result


# --- main ----------------------------------------------------------------
def main():
    env = load_env()
    if not env.get("NUTRITION_CLIENT_ID"):
        log("ERROR: NUTRITION_CLIENT_ID missing from .env — run client registration first.")
        return 1

    env = ensure_token(env)
    token = env["NUTRITION_ACCESS_TOKEN"]

    client = MCPClient(env["NUTRITION_MCP_URL"], token)
    log("Initializing MCP session ...")
    info = client.initialize()
    server_name = (info or {}).get("serverInfo", {}).get("name", "?")
    log(f"MCP session ready (server: {server_name}, session_id={client.session_id}).")

    tools = client.list_tools()
    log(f"tools/list returned {len(tools)} tool(s): {[t['name'] for t in tools]}")
    if not tools:
        log("Saturn-shell: tools/list empty. Raw response:")
        log(json.dumps(client.list_tools_raw(), indent=2)[:1000])
        return 1

    today = date.today().isoformat()
    tool = pick_macros_tool(tools)
    log(f"Selected tool for macros: {tool['name']}")
    if tool.get("description"):
        log(f"  desc: {tool['description'][:160]}")
    schema = tool.get("inputSchema", {})
    props = list((schema.get("properties") or {}).keys())
    log(f"  input properties: {props}")

    # Build arguments conservatively from the tool's own schema.
    args = {}
    for key in props:
        kl = key.lower()
        if "date" in kl or kl in ("day", "on"):
            args[key] = today
        elif kl in ("timezone", "tz", "time_zone"):
            args[key] = env.get("NUTRITION_TIMEZONE") or "America/Chicago"
        elif kl == "locale":
            args[key] = env.get("NUTRITION_LOCALE") or "en-US"
    log(f"Calling {tool['name']} with args={args}")
    raw = client.call_tool(tool["name"], args)
    obj = tool_result_to_obj(raw)

    # Prefer the app's live daily targets; fall back to the .env goals.
    targets = obj.get("targets") if isinstance(obj, dict) else None
    if isinstance(targets, dict):
        goals = {
            "calories": _num(targets.get("calories")),
            "protein_g": _num(targets.get("protein")),
            "carbs_g": _num(targets.get("carbs")),
            "fat_g": _num(targets.get("fat")),
        }
    else:
        goals = {
            "calories": _num(env.get("NUTRITION_CALORIE_GOAL")),
            "protein_g": _num(env.get("NUTRITION_PROTEIN_GOAL_G")),
            "carbs_g": _num(env.get("NUTRITION_CARBS_GOAL_G")),
            "fat_g": _num(env.get("NUTRITION_FAT_GOAL_G")),
        }

    payload = {
        "date": today,
        "synced_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_tool": tool["name"],
        "goals": goals,
        "totals": _extract_macros(obj),
        "meal_count": obj.get("meal_count") if isinstance(obj, dict) else None,
        "raw": obj,
    }

    os.makedirs(DAILY_DIR, exist_ok=True)
    out_path = os.path.join(DAILY_DIR, f"{today}.json")
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    log(f"Wrote {out_path}")
    log(f"Totals: {payload['totals']}")

    git_push(today)

    # Event-driven Currents refresh: let the macro-delta gate decide whether today's
    # intake moved enough to regenerate the dashboard prose between scheduled slots.
    # Pure no-op unless the gate's thresholds are crossed; never fatal to the sync.
    fire_macros_trigger()
    return 0


def fire_macros_trigger():
    """Run polar/macros_trigger.py after the macro write. The trigger is a gate — it
    fires summary.py --slot macros-update only on a meaningful nutrition change, else
    no-ops. Failures here must never crash the 30-min nutrition sync (best-effort)."""
    import subprocess
    trigger = os.path.join(REPO_ROOT, "polar", "macros_trigger.py")
    if not os.path.exists(trigger):
        log("macros_trigger.py not found — skipping Currents refresh hook")
        return
    try:
        out = subprocess.run(
            [sys.executable, trigger],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
        )
        for line in (out.stdout or "").strip().splitlines():
            log(line)
        if out.returncode != 0:
            log(f"macros_trigger exited {out.returncode} (non-fatal): {(out.stderr or '').strip()[:200]}")
    except Exception as e:
        log(f"macros_trigger invocation failed (non-fatal): {e}")


def git_push(day):
    """Commit + push today's nutrition file so the live dashboard updates.

    Only stages nutrition/daily — never .env (gitignored anyway). Non-fatal:
    a no-op commit or offline state must not crash the 30-min job.
    """
    import subprocess
    try:
        subprocess.run(["git", "add", "nutrition/daily"], cwd=REPO_ROOT, check=True)
        subprocess.run(["git", "commit", "-m", f"chore: nutrition macros {day}"],
                       cwd=REPO_ROOT, check=True, capture_output=True, text=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=REPO_ROOT, check=True,
                       capture_output=True, text=True)
        log("pushed nutrition daily file")
    except subprocess.CalledProcessError as e:
        log(f"git push skipped/failed (non-fatal): {e}")


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _extract_macros(obj):
    """Best-effort pull of calories/protein/carbs/fat from an arbitrary nutrition object."""
    if not isinstance(obj, dict):
        return {"calories": None, "protein_g": None, "carbs_g": None, "fat_g": None}
    # flatten one common nesting level (e.g. {"totals": {...}} or {"summary": {...}})
    src = obj
    for nest in ("totals", "summary", "today", "macros", "data"):
        if isinstance(obj.get(nest), dict):
            src = obj[nest]
            break

    def find(*keys):
        for k in keys:
            for actual in src:
                if actual.lower().replace("_", "").replace(" ", "") == k:
                    return _num(src[actual])
        return None

    return {
        "calories": find("calories", "kcal", "energy", "caloriestotal"),
        "protein_g": find("protein", "proteing", "proteingrams"),
        "carbs_g": find("carbs", "carbohydrates", "carbsg", "carbgrams"),
        "fat_g": find("fat", "fatg", "fatgrams"),
    }


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(1)
