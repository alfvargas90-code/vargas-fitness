#!/usr/bin/env python3
"""
macros_trigger.py — event-driven Currents refresh on a meaningful nutrition change.

The dashboard's Currents prose is normally regenerated on a 7-slot daily clock by
com.alfredo.polar-summary (summary.py). Calorie data, though, updates live every
30 min via nutrition/sync.py — so between scheduled slots the prose can feel stale
even while the macro numbers move. This script closes that gap: nutrition/sync.py
calls it right after each macro write, and it fires summary.py --slot macros-update
ONLY when the day's intake has shifted enough to be worth re-reading.

It is a GATE, not a writer. Decision flow (all thresholds are constants below and
are meant to be tuned):

  1. Read today's nutrition/daily/<date>.json -> macro signature (cal/protein/carbs/
     fat/meal_count) -> stable hash.
  2. New day or first-ever run -> set the baseline silently, reset the daily counter,
     do NOT fire (avoids a spurious midnight fire off yesterday's totals).
  3. Identical hash to the last FIRED state -> no-op (a re-sync with no real change).
  4. Daily cap reached (DAILY_CAP fires) -> no-op.
  5. Burst guard: last fire < BURST_GAP_MIN ago -> no-op (coalesce; the next 30-min
     sync picks up the accumulated delta).
  6. Meaningful-change gate (vs the last fired baseline) — fire if ANY of:
       - |Δcalories|  >= THRESH_CAL
       - |Δprotein|   >= THRESH_PROTEIN
       -  Δmeal_count >= THRESH_MEALS         (a new meal landed)
       - time since last fire >= STALE_MIN AND |Δcalories| >= STALE_FLOOR_CAL
         (slow drip that never crosses a threshold but is worth a freshness refresh)
     Otherwise -> no-op.
  7. Fire summary.py --slot macros-update --macro-note "<plain-language delta>",
     then persist the new baseline + bump the daily counter (only on success).

Every decision is logged to stdout (captured by the nutrition-sync launchd log).
Never raises into the caller — a bad macro file or a summary.py failure must not
crash the 30-min nutrition sync.

State: polar/state/last_macros_fire.json (auto-committed by the polar-sync job).
"""
import json
import os
import subprocess
import sys
from datetime import datetime

# --- paths ---------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))          # .../fitness-dashboard/polar
REPO_ROOT = os.path.dirname(HERE)                          # .../fitness-dashboard
STATE_DIR = os.path.join(HERE, "state")
STATE_PATH = os.path.join(STATE_DIR, "last_macros_fire.json")
SUMMARY_PY = os.path.join(HERE, "summary.py")
NUTRITION_DAILY = os.path.join(REPO_ROOT, "nutrition", "daily")

# --- tunables (Alfie: weigh in) -----------------------------------------
THRESH_CAL = 200          # kcal — a meaningful intake jump
THRESH_PROTEIN = 20       # g protein — a meaningful protein jump
THRESH_MEALS = 1          # +N meals logged since last fire
STALE_MIN = 90            # min — freshness refresh window
STALE_FLOOR_CAL = 50      # kcal — minimum change for a stale-refresh to count (kills noise)
BURST_GAP_MIN = 20        # min — minimum gap between fires (anti-burst; < 30-min sync cadence so normal cycles never blocked)
DAILY_CAP = 6             # max macro-triggered fires per local day
SUMMARY_TIMEOUT = 240     # s — summary.py wall-clock budget (it allows the LLM 180s)

# PATH for the summary.py subprocess. The nutrition-sync plist sets NO PATH, but
# summary.py shells out to ~/bin/llm -> codex (lives in the nvm bin dir). Mirror the
# polar-summary plist's PATH so codex/llm resolve regardless of the launchd context.
_HOME = os.path.expanduser("~")
SUMMARY_PATH = ":".join([
    os.path.join(_HOME, "bin"),
    os.path.join(_HOME, ".nvm", "versions", "node", "v24.15.0", "bin"),
    os.path.join(_HOME, ".local", "bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin",
])


def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] macros_trigger: {msg}", flush=True)


def _num(v):
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def read_signature(today_iso):
    """Return (sig_dict, hash_str) for today's macro file, or (None, None) if absent."""
    path = os.path.join(NUTRITION_DAILY, f"{today_iso}.json")
    if not os.path.exists(path):
        return None, None
    with open(path) as fh:
        n = json.load(fh)
    totals = n.get("totals", {}) or {}
    sig = {
        "calories": round(_num(totals.get("calories"))),
        "protein_g": round(_num(totals.get("protein_g"))),
        "carbs_g": round(_num(totals.get("carbs_g"))),
        "fat_g": round(_num(totals.get("fat_g"))),
        "meal_count": int(_num(n.get("meal_count"))),
        "cal_goal": round(_num((n.get("goals", {}) or {}).get("calories"))),
        "protein_goal": round(_num((n.get("goals", {}) or {}).get("protein_g"))),
    }
    # Hash only the parts that represent "what was logged", not the goals.
    import hashlib
    fingerprint = json.dumps(
        {k: sig[k] for k in ("calories", "protein_g", "carbs_g", "fat_g", "meal_count")},
        sort_keys=True,
    )
    return sig, hashlib.sha1(fingerprint.encode()).hexdigest()[:16]


def load_state():
    try:
        with open(STATE_PATH) as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh, indent=2)
    os.replace(tmp, STATE_PATH)


def set_baseline(state, sig, sig_hash, now, today_iso, reason):
    """Adopt the current signature as the new baseline WITHOUT firing."""
    new_count = state.get("fire_count", 0) if state.get("fire_date") == today_iso else 0
    save_state({
        "fired_hash": sig_hash,
        "fired_calories": sig["calories"],
        "fired_protein_g": sig["protein_g"],
        "fired_meal_count": sig["meal_count"],
        "fired_at": state.get("fired_at"),          # preserve last real fire time for burst guard
        "fire_date": today_iso,
        "fire_count": new_count,
    })
    log(f"baseline set ({reason}); no fire. cal={sig['calories']} prot={sig['protein_g']} meals={sig['meal_count']}")


def mins_since(iso_ts, now):
    if not iso_ts:
        return None
    try:
        return (now - datetime.fromisoformat(iso_ts)).total_seconds() / 60.0
    except Exception:
        return None


def build_note(sig, d_cal, d_prot, d_meals):
    """Plain-language description of the delta for summary.py's --macro-note."""
    bits = []
    if d_meals >= 1:
        bits.append(f"{d_meals} new meal{'s' if d_meals > 1 else ''} just logged")
    if abs(d_cal) >= 1:
        direction = "rose" if d_cal > 0 else "dropped"
        left = sig["cal_goal"] - sig["calories"] if sig["cal_goal"] else None
        tail = f", about {round(left)} left in the day's window" if left is not None and left > 0 else (
            ", now over the day's target" if left is not None and left < 0 else "")
        bits.append(f"calories {direction} about {abs(round(d_cal))} "
                    f"(now {sig['calories']} of {sig['cal_goal']} target{tail})")
    if abs(d_prot) >= 1:
        direction = "climbed" if d_prot > 0 else "fell"
        bits.append(f"protein {direction} about {abs(round(d_prot))}g "
                    f"(now {sig['protein_g']}g of {sig['protein_goal']}g target)")
    return "; ".join(bits) or "intake updated"


def fire_summary(note):
    """Invoke summary.py --slot macros-update. Returns True on success."""
    py = os.path.join(HERE, ".venv", "bin", "python3")
    if not os.path.exists(py):
        py = sys.executable
    env = {**os.environ, "PATH": SUMMARY_PATH, "LLM_CALLER": "polar/macros_trigger.py"}
    log(f"firing summary.py --slot macros-update --macro-note {note!r}")
    try:
        out = subprocess.run(
            [py, SUMMARY_PY, "--slot", "macros-update", "--macro-note", note],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=SUMMARY_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        log("summary.py timed out — not advancing baseline (will retry next cycle)")
        return False
    # Surface summary.py's own log tail for traceability.
    tail = (out.stdout or "").strip().splitlines()[-4:]
    for line in tail:
        log(f"  summary> {line}")
    if out.returncode != 0:
        err = (out.stderr or out.stdout or "").strip()[:300]
        log(f"summary.py exited {out.returncode} — not advancing baseline. {err}")
        return False
    return True


def main():
    now = datetime.now().astimezone()
    today_iso = now.date().isoformat()

    sig, sig_hash = read_signature(today_iso)
    if sig is None:
        log(f"no macro file for {today_iso} yet — nothing to do")
        return 0

    state = load_state()

    # New day / first run / day rollover -> reset cap counter, adopt baseline, no fire.
    if state.get("fire_date") != today_iso or not state.get("fired_hash"):
        reason = "new day" if state.get("fire_date") and state.get("fire_date") != today_iso else "first run"
        set_baseline(state, sig, sig_hash, now, today_iso, reason)
        return 0

    # Identical to last fired state — a re-sync with no real change.
    if sig_hash == state.get("fired_hash"):
        log("no macro change since last fire — no-op")
        return 0

    # Daily cap.
    fire_count = state.get("fire_count", 0)
    if fire_count >= DAILY_CAP:
        log(f"daily cap reached ({fire_count}/{DAILY_CAP}) — no-op until midnight CDT")
        return 0

    # Burst guard.
    gap = mins_since(state.get("fired_at"), now)
    if gap is not None and gap < BURST_GAP_MIN:
        log(f"burst-suppressed (last fire {gap:.0f}m ago < {BURST_GAP_MIN}m) — will coalesce next cycle")
        return 0

    # Meaningful-change gate (vs last fired baseline).
    d_cal = sig["calories"] - _num(state.get("fired_calories"))
    d_prot = sig["protein_g"] - _num(state.get("fired_protein_g"))
    d_meals = sig["meal_count"] - int(_num(state.get("fired_meal_count")))

    reasons = []
    if abs(d_cal) >= THRESH_CAL:
        reasons.append(f"Δcal={d_cal:+.0f}>={THRESH_CAL}")
    if abs(d_prot) >= THRESH_PROTEIN:
        reasons.append(f"Δprot={d_prot:+.0f}>={THRESH_PROTEIN}")
    if d_meals >= THRESH_MEALS:
        reasons.append(f"Δmeals={d_meals:+d}")
    if gap is not None and gap >= STALE_MIN and abs(d_cal) >= STALE_FLOOR_CAL:
        reasons.append(f"stale-refresh({gap:.0f}m, Δcal={d_cal:+.0f})")

    if not reasons:
        log(f"below threshold (Δcal={d_cal:+.0f} Δprot={d_prot:+.0f} Δmeals={d_meals:+d}, "
            f"gap={gap if gap is None else round(gap)}m) — no-op")
        return 0

    log(f"meaningful change: {', '.join(reasons)} — firing")
    note = build_note(sig, d_cal, d_prot, d_meals)
    if not fire_summary(note):
        return 0   # failure already logged; baseline not advanced so it retries

    # Advance baseline + bump the daily counter (only on a successful fire).
    save_state({
        "fired_hash": sig_hash,
        "fired_calories": sig["calories"],
        "fired_protein_g": sig["protein_g"],
        "fired_meal_count": sig["meal_count"],
        "fired_at": now.replace(microsecond=0).isoformat(),
        "fire_date": today_iso,
        "fire_count": fire_count + 1,
    })
    log(f"fired ({fire_count + 1}/{DAILY_CAP} today)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"FATAL (non-fatal to caller): {e}")
        sys.exit(0)   # never crash the nutrition sync
