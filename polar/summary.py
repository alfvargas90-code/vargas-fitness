#!/usr/bin/env python3
"""Generate an AI health read for the fitness dashboard.

Reads the latest Polar recharge/sleep data + body-comp seed, asks `claude -p`
(rides Alfie's Claude Max plan — no API key, no marginal cost) for a 3-5 sentence
plain-English read, writes polar/summary.json, and pushes so the live URL updates.

Run by the com.alfredo.polar-summary LaunchAgent 4x/day (8:30, 12:30, 16:45, 20:00 CST).
"""
import json, os, re, shutil, subprocess, sys
from datetime import datetime
from statistics import mean

HERE = os.path.dirname(os.path.abspath(__file__))        # .../fitness-dashboard/polar
ROOT = os.path.dirname(HERE)                              # .../fitness-dashboard


def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def slot_for(now):
    """morning / midday / afternoon / evening from minutes-of-day."""
    m = now.hour * 60 + now.minute
    if m <= 10 * 60 + 30:   return "morning"      # …–10:30
    if m <= 14 * 60 + 30:   return "midday"       # 10:31–14:30
    if m <= 18 * 60:        return "afternoon"    # 14:31–18:00
    return "evening"                              # 18:01–…


def load_json(path):
    with open(path) as f:
        return json.load(f)


def recharge_score(rec):   # Nightly Recharge status, 1-6
    return rec.get("ans_charge_status")


def hrv_of(rec):
    return rec.get("heart_rate_variability_avg")


def sleep_hours(slp):
    """Prefer start/end span; fall back to summed stages."""
    try:
        s = datetime.fromisoformat(slp["sleep_start_time"])
        e = datetime.fromisoformat(slp["sleep_end_time"])
        h = (e - s).total_seconds() / 3600
        if h > 0:
            return round(h, 1)
    except Exception:
        pass
    secs = sum(slp.get(k, 0) or 0 for k in ("light_sleep", "deep_sleep", "rem_sleep"))
    return round(secs / 3600, 1) if secs else None


def rolling_mean(dates, folder, fn, n=7):
    vals = []
    for d in reversed(dates):                 # newest first
        try:
            v = fn(load_json(os.path.join(HERE, folder, f"{d}.json")))
        except Exception:
            v = None
        if v is not None:
            vals.append(v)
        if len(vals) >= n:
            break
    return round(mean(vals), 1) if vals else None


def body_comp_line():
    """Tolerantly pull latest weight + scale body-fat from data.js. Never raises."""
    try:
        with open(os.path.join(ROOT, "data.js")) as f:
            js = f.read()
        bits = []
        # latest weight from SEED_WEIGHT
        w = re.findall(r'date:\s*"(\d{4}-\d{2}-\d{2})"[^}]*?weight_lbs:\s*([\d.]+)', js)
        if w:
            d, lbs = max(w, key=lambda x: x[0])
            bits.append(f"weight {lbs} lbs (as of {d})")
        # latest scale body-fat
        bf = re.findall(r'date:\s*"(\d{4}-\d{2}-\d{2})"[^}]*?body_fat_pct:\s*([\d.]+)', js)
        if bf:
            d, pct = max(bf, key=lambda x: x[0])
            bits.append(f"body fat {pct}% (as of {d})")
        return "; ".join(bits) if bits else "no body-comp update"
    except Exception as e:
        log(f"body-comp parse failed (non-fatal): {e}")
        return "no body-comp update"


def call_claude(prompt):
    claude = shutil.which("claude") or "/Users/alfredovargas/.local/bin/claude"
    out = subprocess.run(
        [claude, "-p", prompt],
        capture_output=True, text=True, timeout=180, cwd=ROOT,
    )
    if out.returncode != 0:
        raise RuntimeError(f"claude exited {out.returncode}: {out.stderr.strip()[:300]}")
    return out.stdout


def clean(text):
    text = re.sub(r"[*_`#>]", "", text)                 # strip markdown emphasis/headers
    text = re.sub(r"\s+", " ", text).strip()
    return text


def git_push(slot, date):
    try:
        subprocess.run(["git", "add", "polar/summary.json"], cwd=ROOT, check=True)
        subprocess.run(["git", "commit", "-m", f"chore: {slot} summary {date}"],
                       cwd=ROOT, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, check=True,
                       capture_output=True, text=True)
        log("pushed summary.json")
    except subprocess.CalledProcessError as e:
        log(f"git push failed (non-fatal): {e}")        # likely no change or offline


def main():
    now = datetime.now().astimezone()
    slot = slot_for(now)

    manifest = load_json(os.path.join(HERE, "manifest.json"))
    cats = manifest.get("categories", {})
    rec_dates = sorted(cats.get("recharge", []))
    slp_dates = sorted(cats.get("sleep", []))
    if not rec_dates and not slp_dates:
        log("no polar data yet — nothing to summarize")
        return 0

    rec = load_json(os.path.join(HERE, "recharge", f"{rec_dates[-1]}.json")) if rec_dates else {}
    slp = load_json(os.path.join(HERE, "sleep", f"{slp_dates[-1]}.json")) if slp_dates else {}

    rec_today = recharge_score(rec)
    hrv_today = hrv_of(rec)
    slp_hours = sleep_hours(slp) if slp else None

    rec_7d = rolling_mean(rec_dates, "recharge", recharge_score)
    hrv_7d = rolling_mean(rec_dates, "recharge", hrv_of)
    slp_7d = rolling_mean(slp_dates, "sleep", sleep_hours)
    body = body_comp_line()

    prompt = (
        "You are a recovery coach reading wearable data for an athlete. "
        "Here are the current numbers (Polar Nightly Recharge is a 1-6 scale, 6 best):\n"
        f"- Nightly Recharge today: {rec_today}/6 (7-day avg {rec_7d})\n"
        f"- HRV today: {hrv_today} ms (7-day avg {hrv_7d})\n"
        f"- Sleep last night: {slp_hours} hours (7-day avg {slp_7d})\n"
        f"- Body composition: {body}\n\n"
        "Write 3 to 5 sentences, plain English, no preamble, no markdown, no bullet points. "
        "First say what the data SAYS (1-2 sentences of fact). "
        "Then say what it SUGGESTS for today (1-2 sentences of action: train hard, "
        "train moderate, rest, or a specific recovery move). Be direct and concrete."
    )

    log(f"slot={slot} recharge={rec_today} hrv={hrv_today} sleep={slp_hours}")
    summary = clean(call_claude(prompt))
    if not summary:
        raise RuntimeError("claude returned empty output")

    payload = {
        "generated_at": now.replace(microsecond=0).isoformat(),
        "slot": slot,
        "summary": summary,
        "data_basis": {
            "recharge_today": rec_today,
            "sleep_hours": slp_hours,
            "hrv_today": hrv_today,
            "hrv_7d_avg": hrv_7d,
        },
    }
    with open(os.path.join(HERE, "summary.json"), "w") as f:
        json.dump(payload, f, indent=2)
    log("wrote summary.json")

    git_push(slot, now.date().isoformat())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(0)   # never let launchd mark a hard failure / spin
