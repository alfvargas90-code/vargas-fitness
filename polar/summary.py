#!/usr/bin/env python3
"""Generate an AI health read for the fitness dashboard.

Reads the latest Polar recharge/sleep data + body-comp seed and writes
polar/summary.json with a `simple` block the dashboard Currents card renders, then
pushes so the live URL updates. The headline product is the TACTICAL BRIEF in
`simple.reading`: a multiline read that briefs, in order — what's the state, what
does it mean, training, nutrition, and recovery.

The brief has two layers. The STATE block (3 lines: Recovery / Strain / Sleep) is
computed deterministically in Python and mirrors the dashboard's Recovery/Strain/Sleep
rings exactly — real numbers, no LLM. The READ line plus the declarative briefing
conclusions (workout / eat / rest) are the only `claude -p` (Alfie's Claude Max plan
— no API key, no marginal cost) authored parts. The Read never quotes biometric
numbers; the Eat conclusion may use gram amounts and clock times. No astrology, no
natal/lunar texture.

Run by the com.alfredo.polar-summary LaunchAgent 7x/day (CDT), one fire per slot:
  04:00 sleep · 07:00 recovery · 11:30 fuel-1 · 15:00 fuel-2 · 17:30 train-1 ·
  20:00 train-2 · 21:45 day-review.
NOTE: several of these fire times land ON the :00/:30 boundary the 30-min polar-sync
timer also hits. The old 9:05 fire used a :05 offset specifically to dodge that
same-minute sync race (which once left "Today's Read" stale). The 7-fire schedule
above is locked by Alfie; if a stale-read race resurfaces, nudge the offending fire
a few minutes off the boundary rather than reverting the schedule.
The 21:45 fire is the nightly Day-in-Review slot: it freezes the day's stats + verdict + prose into day_review.json INSTEAD OF the regular summary.json.
"""
import json, os, re, shutil, subprocess, sys
from datetime import datetime, date
from statistics import mean

HERE = os.path.dirname(os.path.abspath(__file__))        # .../fitness-dashboard/polar
ROOT = os.path.dirname(HERE)                              # .../fitness-dashboard

# Load bands: import the ONE Python definition from lunar_stress.py (which mirrors the
# dashboard's app.js LOAD_BANDS) so the AI prompt's "load so far" framing reads the
# exact same thresholds as the Recovery tile, Activity card, and LSI. Resilient fallback
# keeps summary generation working even if that import ever fails.
try:
    from lunar_stress import load_band_for
except Exception:
    _LOAD_BANDS = [("—", 0, 49), ("Light", 50, 399), ("Moderate", 400, 799), ("Heavy", 800, 10 ** 9)]
    def load_band_for(active_cal):
        c = active_cal if isinstance(active_cal, (int, float)) else 0
        for name, lo, hi in _LOAD_BANDS:
            if lo <= c <= hi:
                return name
        return "—"

# Daily transit snapshot folder (scheduled task) — files named <date>-transit-snapshot.md
TRANSIT_DIR = os.path.expanduser(
    "~/Documents/Claude/Scheduled/daily-transit-snapshot")

# ---- Section 12: Astrology-aware fitness intelligence (spec Section 12, Layer 2) ----
# NOTE (2026-06-03 direct-data reframe): the structures below stay DEFINED for other
# code (load_today_transits still uses BODY_MAPPING), but they are NO LONGER injected
# into the prose prompt. The Reading is pure physiology + action now — Layer 1.

# Static natal architecture. Lifted tight from spec Section 12, Layer 2.
NATAL_ARCHITECTURE = (
    "Alfie's natal fitness architecture (static): Capricorn Ascendant, Saturn chart ruler, "
    "Moon in Capricorn, Saturn in Capricorn, Mars in Taurus, Uranus in Capricorn, Neptune in Capricorn.\n"
    "- Saturn/Capricorn dominance -> knees, joints, bones, connective tissue, structural alignment, "
    "long-term recovery, endurance. Watch knee soreness, joint stress, tendon recovery, overuse "
    "accumulation, recovery debt.\n"
    "- Moon in Capricorn -> recovery quality, sleep quality, stress load, adaptation capacity. "
    "Watch sleep scores, HRV, fatigue markers, recovery consistency.\n"
    "- Mars in Taurus -> neck, upper traps, shoulders, strength output, mechanical force production. "
    "Watch pulling/pressing performance, neck tension, strength progression.\n"
    "- Uranus-Moon signature -> nervous system, recovery variability, sleep disruption, sudden energy "
    "swings. Watch HRV volatility, sleep inconsistency.\n"
    "- Tendencies: strong at endurance, consistency, discipline, progressive overload; weak at "
    "overworking through fatigue, ignoring recovery signals, joint accumulation stress, delayed burnout recognition."
)

# Universal zodiac body mapping (spec Section 12).
BODY_MAPPING = {
    "Aries": "Head",
    "Taurus": "Neck / Throat",
    "Gemini": "Lungs / Nervous System",
    "Cancer": "Stomach / Digestion",
    "Leo": "Heart / Vitality",
    "Virgo": "Gut / Nutrition",
    "Libra": "Balance / Mobility",
    "Scorpio": "Deep Recovery / Regeneration",
    "Sagittarius": "Hips / Mobility",
    "Capricorn": "Knees / Bones / Joints",
    "Aquarius": "Circulation / Nervous System",
    "Pisces": "Feet / Restoration",
}

# Transiting planets we care about -> tier (per spec Layer 3).
_TRANSIT_TIER = {"Moon": 1, "Saturn": 2, "Mars": 3, "Jupiter": 4}
# Natal points a relevant transit must hit (Ascendant aliased as ASC).
_NATAL_TARGETS = {"Moon", "Saturn", "Mars", "Ascendant", "ASC"}
_ASPECTS = ("conjunct", "opposite", "opposition", "square", "trine",
            "sextile", "quincunx", "semisextile", "sesquiquadrate")
_SIGNS = "|".join(BODY_MAPPING)

OUTPUT_SECTIONS = [
    "Recovery",
    "Reading",
    "Performance",
    "Transit",
]

# Section label -> key in the plain-English `simple` block the dashboard card reads.
LABEL_TO_KEY = {
    "Recovery": "recovery",
    "Reading": "reading",
    "Performance": "performance",
    "Transit": "transit",
}
RECOVERY_WORDS = ["Excellent", "Good", "Average", "Poor"]
SIMPLE_KEYS = ["recovery", "reading", "performance", "transit"]

# Per-slot framing for the tactical brief. Each entry sets WHERE Alfie is in his day
# (`when` — sets the tone), what the AI Read line should focus on (`read`), and which
# decision blocks fire (`blocks`). The STATE block is deterministic Python; the Read +
# declarative decision conclusions are the only LLM-authored parts, each written as a
# concise Mission-Control briefing section. The clock matters: the 4 AM sleep slot has no workout/eat call (he's
# asleep) — it answers "Setup for today?" instead; the 8 PM train-2 slot answers the
# workout question RETROSPECTIVELY and weights the rest/sleep-prep call. The day's stat
# recap stays owned by the 9:45 PM Day-in-Review card (untouched).
SLOT_FRAMING = {
    "sleep": {
        "when": "SLOT — SLEEP (~4 AM, Alfie is asleep). The State block shows last night's sleep and the recovery he's waking into.",
        "read": "what last night's recovery means for the day ahead — the reserve he's working with",
        "blocks": ["Read", "Setup"],
    },
    "recovery": {
        "when": "SLOT — WAKE-UP (~7 AM, the day is open ahead of him).",
        "read": "the recovery state he woke up on and what kind of day that capacity sets up",
        "blocks": ["Read", "Workout", "Eat", "Rest"],
    },
    "fuel-1": {
        "when": "SLOT — FUEL #1 (~11:30 AM, first fueling/energy check). The eating call carries the most weight.",
        "read": "where fueling and energy stand heading into the afternoon",
        "blocks": ["Read", "Workout", "Eat", "Rest"],
    },
    "fuel-2": {
        "when": "SLOT — FUEL #2 (~3 PM, second fueling/energy check). The eating call carries the most weight — is he fueled for the evening window or running a deficit into it?",
        "read": "the fuel/energy state heading into the evening and the workout window",
        "blocks": ["Read", "Workout", "Eat", "Rest"],
    },
    "train-1": {
        "when": "SLOT — TRAIN OPEN (~5:30 PM, the workout window is opening). The workout call carries the most weight.",
        "read": "his recovery against how much he's already spent today",
        "blocks": ["Read", "Workout", "Eat", "Rest"],
    },
    "train-2": {
        "when": "SLOT — TRAIN CLOSE (~8 PM, the workout window is closing). The rest/sleep-prep call carries the most weight; the workout question is RETROSPECTIVE.",
        "read": "how the session landed (or that the window passed) and what the night needs",
        "blocks": ["Read", "Workout", "Eat", "Rest"],
    },
}


# --- Tactical-brief instruction builders -----------------------------------------
# Each returns the one-line instruction that tells claude -p how to write that block.
# Decision blocks now deliver declarative briefing conclusions: no question framing,
# no leading verdict words, and 1 to 2 tight sentences. The Read line remains the
# only free interpretation, capped at 30 words and barred from quoting numbers (the
# State block already shows them).

def read_instruction():
    return (
        "Read: 1 to 2 sentences, 30 words MAX, plain language. Interpret the State holistically — "
        "what does the COMBINATION mean? Do NOT repeat raw numbers; the State block already showed "
        "them. No jargon, no astrology. "
        "Example shape (do not copy): \"Body's on a thinner reserve than usual and you've already "
        "spent a typical day's load.\""
    )


def workout_instruction(slot, rest_today):
    if slot == "train-2":
        return (
            "Workout: RETROSPECTIVE — the window has closed. In 1 to 2 declarative sentences, "
            "30 words MAX, state what logged training accomplished and whether more work tonight "
            "adds value. If no training logged, state the window has closed and tomorrow is the platform. "
            "No question framing; do NOT lead with a verdict word or phrase."
        )
    if rest_today:
        return (
            "Workout: 1 to 2 declarative sentences, 30 words MAX. State that today is deliberate "
            "recovery, not training output. No question framing; do NOT lead with a verdict word or phrase."
        )
    return (
        "Workout: 1 to 2 declarative sentences, 30 words MAX. State whether training is warranted "
        "and at what intensity/duration, or why to hold. No question framing; do NOT lead with a verdict word or phrase."
    )


def eat_instruction():
    return (
        "Eat: 1 to 2 declarative sentences, 30 words MAX. State the nutrition priority and by when, "
        "anchored to the clock. Gram amounts and time windows ARE allowed. Lean on calories left, "
        "protein gap, and time since the last meal. No question framing; do NOT lead with a verdict word or phrase."
    )


def rest_instruction():
    return (
        "Rest: 1 to 2 declarative sentences, 30 words MAX. State the highest-leverage recovery move "
        "and why: banking sleep, protecting capacity, maintaining output, or room to push. No question framing; "
        "do NOT lead with a verdict word or phrase."
    )


def setup_instruction():
    return (
        "Setup: ONE directional line, 20 words MAX — what kind of day this recovery sets up "
        "(capacity, ceiling, where to spend or protect). He's asleep, so NO imperative."
    )


BLOCK_INSTR = {
    "Read": lambda slot, rest: read_instruction(),
    "Workout": lambda slot, rest: workout_instruction(slot, rest),
    "Eat": lambda slot, rest: eat_instruction(),
    "Rest": lambda slot, rest: rest_instruction(),
    "Setup": lambda slot, rest: setup_instruction(),
}


def block_header(label, slot):
    """Human-facing declarative section header for each block in the rendered brief."""
    if label == "Workout":
        return "TRAINING"
    return {
        "Read": "Read",
        "Eat": "NUTRITION",
        "Rest": "RECOVERY",
        "Setup": "Setup for today?",
    }.get(label, label)


def parse_brief_blocks(text, labels):
    """Pull the labeled lines (Read:/Workout:/Eat:/Rest:/Setup:) out of claude -p's
    output. Tolerant of markdown bullets/emphasis. Returns {label: text}; first hit
    per label wins."""
    out = {}
    alt = "|".join(re.escape(l) for l in labels)
    pat = re.compile(
        rf"(?im)^[\s#*_>-]*({alt})\s*[:\-–—]+\s*(.*?)(?=^[\s#*_>-]*(?:{alt})\s*[:\-–—]|\Z)",
        re.S)
    for m in pat.finditer(text):
        label = m.group(1).strip()
        label = next((l for l in labels if l.lower() == label.lower()), label)
        body = re.sub(r"[*_`#>]", "", m.group(2))
        body = re.sub(r"\s+", " ", body).strip()
        if body and label not in out:
            out[label] = body
    return out
# Slots whose prompt gets today's accumulated activity + nutrition fed in. The 4 AM sleep
# slot is too early to have any. The fuel slots are literally fueling/energy checks and
# the train slots need today's load to judge the session, so all four get the data — and
# train-2 (unlike the old hardcoded evening wind-down) needs it to read whether he trained.
TODAY_DATA_SLOTS = {"recovery", "fuel-1", "fuel-2", "train-1", "train-2"}


def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def slot_for(now):
    """sleep / recovery / fuel-1 / fuel-2 / train-1 / train-2 / day-review from
    minutes-of-day. Boundaries are cut so each scheduled fire lands cleanly inside
    its own slot's window with margin on either side (7-fire schedule, CDT):
      04:00 sleep · 07:00 recovery · 11:30 fuel-1 · 15:00 fuel-2 ·
      17:30 train-1 · 20:00 train-2 · 21:45 day-review.
    The 21:45 day-review fire is actually dispatched by is_night_review() upstream,
    so the trailing "day-review" return is a late-evening fallback, not the live path."""
    t = now.hour * 60 + now.minute
    if 3 * 60 <= t < 6 * 60:            return "sleep"      # covers 04:00 fire
    if 6 * 60 <= t < 9 * 60:            return "recovery"   # covers 07:00 fire
    if 9 * 60 <= t < 13 * 60 + 15:      return "fuel-1"     # covers 11:30 fire
    if 13 * 60 + 15 <= t < 16 * 60 + 15: return "fuel-2"    # covers 15:00 fire
    if 16 * 60 + 15 <= t < 18 * 60 + 45: return "train-1"   # covers 17:30 fire
    if 18 * 60 + 45 <= t < 21 * 60 + 15: return "train-2"   # covers 20:00 fire
    return "day-review"                                     # covers 21:45 fire + late fallback


def load_json(path):
    with open(path) as f:
        return json.load(f)


def goal_framing():
    """Read polar/goal_config.json and build the active-goal framing block injected
    into every prose prompt. This is the source of truth for the goal lens — the AI
    layer assesses the day through it (protein hits/misses matter, modest deficits
    preserve muscle, resistance work > steps). Never raises; returns "" if no config
    so the prompts degrade to goal-agnostic prose."""
    try:
        cfg = load_json(os.path.join(HERE, "goal_config.json"))
        framing = cfg.get("framing", "").strip()
        if not framing:
            return ""
        return (
            "=== ACTIVE GOAL: body recomp (frame everything through this lens) ===\n"
            f"{framing}\n"
            "Assess his day through this lens: protein hits and misses matter, a "
            "deficit over ~800 calories is a muscle-loss risk worth flagging, and "
            "resistance work is valued more than step count. Weave this into the prose "
            "naturally — a protein nag, deficit context, muscle protection — never as a "
            "checklist or bullet list, and never name it as a \"goal\" or \"recomp\" label.\n\n"
        )
    except Exception as e:
        log(f"goal_config parse failed (non-fatal): {e}")
        return ""


def is_rest_day(date_iso):
    """True if `date_iso` (YYYY-MM-DD) is in polar/rest_days.json. Penny writes
    that file when Alfie declares a rest day in chat. Never raises; returns False
    if the file is missing or unparseable so the prompts degrade to normal."""
    try:
        cfg = load_json(os.path.join(HERE, "rest_days.json"))
        return date_iso in (cfg.get("rest_days") or [])
    except Exception as e:
        log(f"rest_days parse failed (non-fatal): {e}")
        return False


def rest_day_framing(date_iso):
    """Injection block for an explicit rest day. Empty string on a normal day, so
    current (training-aware) behavior is unchanged unless the date is flagged."""
    if not is_rest_day(date_iso):
        return ""
    return (
        "=== REST DAY (overrides training framing) ===\n"
        "Today is an explicit rest day declared by the user. Frame the day's prose "
        "around recovery, protein, hydration, and sleep prep — NOT around training "
        "intensity or pushing output. The Performance verdict should NOT be 'Push hard' "
        "or 'Train normally' — instead use 'Rest day' / 'Recover' / 'Protein focus' "
        "framing. If activity-calorie data looks 'high,' interpret that as accumulated "
        "daily movement, not training.\n\n"
    )


def recharge_score(rec):   # Nightly Recharge status, 1-6
    return rec.get("ans_charge_status")


def recovery_word(rec_score, hrv_today=None, hrv_7d=None):
    """Deterministic Recovery word from overnight data. Computed in Python (not left
    to the LLM) so the word is identical across every slot the same day — the overnight
    recovery doesn't change as the day goes on, so the word shouldn't flicker between
    fires. Maps the Polar Nightly Recharge status (1-6), then lets a clearly
    above-average HRV bump a strong night up to Excellent."""
    if rec_score is None:
        return None
    word = ("Excellent" if rec_score >= 6 else
            "Good" if rec_score >= 4 else
            "Average" if rec_score >= 3 else "Poor")
    if (word == "Good" and rec_score >= 5 and hrv_today and hrv_7d
            and hrv_today >= hrv_7d * 1.08):
        word = "Excellent"
    return word


# ---- Tactical-brief State block (deterministic; mirrors the dashboard rings) ----
# The 3 State lines are computed in Python, never by the LLM — they must read the SAME
# numbers the Recovery / Strain / Sleep rings show. recovery_score_100 is a verbatim
# port of app.js computeRecoveryScore; strain mirrors the 800-cal reserve depletion;
# the sleep word is sleepLabel collapsed to the spec's 4-word vocabulary.
RESERVE_DEPLETION_CAL = 800   # mirrors app.js RESERVE_DEPLETION_CAL


def recovery_score_100(rec, slp, hrv_all_mean):
    """0–100 composite recovery score — verbatim port of app.js computeRecoveryScore
    so the State line's number equals the Recovery ring's number."""
    rs = rec.get("ans_charge_status") if rec else None
    recharge_part = (rs / 6) * 50 if rs is not None else 25
    ss = slp.get("sleep_score") if slp else None
    sleep_part = (ss / 100) * 30 if ss is not None else 15
    hv = rec.get("heart_rate_variability_avg") if rec else None
    hrv_part = min(hv / hrv_all_mean, 1) * 20 if (hv is not None and hrv_all_mean) else 10
    return round(min(recharge_part + sleep_part + hrv_part, 100))


def strain_pct_label(active_cal):
    """(pct, word) from today's active-calories vs the 800-cal reserve. Word vocab is
    the spec's Minimal/Light/Moderate/Heavy/Max on the dashboard's strainLabel cuts."""
    if active_cal is None:
        return None, None
    pct = min(100, round(active_cal / RESERVE_DEPLETION_CAL * 100))
    word = ("Max" if pct >= 95 else "Heavy" if pct >= 80 else
            "Moderate" if pct >= 50 else "Light" if pct >= 15 else "Minimal")
    return pct, word


def sleep_word_4(score):
    """Sleep word collapsed to the spec's 4-word set (Excellent/Good/Fair/Poor)."""
    if score is None:
        return None
    return ("Excellent" if score >= 85 else "Good" if score >= 70 else
            "Fair" if score >= 55 else "Poor")


def sleep_span_hm(slp):
    """Last night's sleep as 'Xh Ym' from the start→end span (matches the Polar app
    and the Sleep ring), falling back to summed stages."""
    try:
        s = datetime.fromisoformat(slp["sleep_start_time"])
        e = datetime.fromisoformat(slp["sleep_end_time"])
        secs = (e - s).total_seconds()
        if secs > 0:
            return min_to_hm(round(secs / 60))
    except Exception:
        pass
    secs = sum(slp.get(k, 0) or 0 for k in ("light_sleep", "deep_sleep", "rem_sleep"))
    return min_to_hm(round(secs / 60)) if secs else None


def hrv_delta_pct(hrv_today, hrv_7d):
    """HRV today vs the 7-day mean, as a signed %. None when either is missing."""
    if hrv_today is None or not hrv_7d:
        return None
    return round((hrv_today / hrv_7d - 1) * 100)


def _append_metric_snapshot(now, slot, rec, slp, hrv_all_mean, hrv_today, hrv_7d, slp_hours, active_cal):
    try:
        recovery = recovery_score_100(rec, slp, hrv_all_mean)
        delta = hrv_delta_pct(hrv_today, hrv_7d)
        rhr = round(rec.get("heart_rate_avg")) if rec and rec.get("heart_rate_avg") is not None else None
        sleep_min = round(slp_hours * 60) if slp_hours is not None else None
        sleep_quality = sleep_word_4(slp.get("sleep_score")) if slp else None
        strain_pct = strain_pct_label(active_cal)[0]
        active_cal_out = round(active_cal) if active_cal is not None else None
        snapshot = {
            "ts": now.replace(microsecond=0).isoformat(),
            "slot": slot,
            "recovery": recovery,
            "hrv_delta_pct": delta,
            "rhr": rhr,
            "sleep_min": sleep_min,
            "sleep_quality": sleep_quality,
            "strain_pct": strain_pct,
            "active_cal": active_cal_out,
        }
        path = os.path.join(HERE, "metrics_history.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(snapshot) + "\n")
    except Exception as e:
        log(f"metrics snapshot append failed (non-fatal): {e}")


def lunar_hrv_pct():
    """The HRV-vs-baseline % the Recovery ring corner shows (lunar_stress.json
    physiology.hrv_pct_baseline), so the State line matches it. None if unavailable."""
    try:
        d = load_json(os.path.join(HERE, "lunar_stress.json"))
        v = (d.get("physiology") or {}).get("hrv_pct_baseline")
        return round(v) if v is not None else None
    except Exception:
        return None


def build_state_block(slot, rec, slp, rec_word, hrv_all_mean, hrv_today, hrv_7d,
                      slp_hours, slp_7d, active_cal):
    """The deterministic 3-line State block. All real values; no LLM involvement.
      Recovery {N} · {word} · HRV {±X%}
      Strain {N}% · {word} · {N} cal spent
      Sleep {Xh Ym} · {word} · {On|Above|Below} baseline"""
    # Recovery line — N mirrors the ring; word is the constant overnight recovery word;
    # the HRV % prefers the same baseline the ring corner uses.
    n = recovery_score_100(rec, slp, hrv_all_mean)
    hd = lunar_hrv_pct()
    if hd is None:
        hd = hrv_delta_pct(hrv_today, hrv_7d)
    hrv_str = f"HRV {'+' if hd >= 0 else ''}{hd}%" if hd is not None else "HRV —"
    rec_line = f"Recovery {n} · {rec_word or '—'} · {hrv_str}"

    # Strain line — % of the 800-cal reserve spent, with the cal figure as the detail.
    pct, word = strain_pct_label(active_cal)
    if pct is not None:
        strain_line = f"Strain {pct}% · {word} · {round(active_cal)} cal spent"
    elif slot == "sleep":
        strain_line = "Strain — · Resting · nothing logged overnight"
    else:
        strain_line = "Strain — · Minimal · no load logged yet"

    # Sleep line — start→end span, 4-word quality, baseline comparison (±0.3h band).
    span = sleep_span_hm(slp) if slp else None
    sword = sleep_word_4(slp.get("sleep_score") if slp else None)
    if slp_hours is not None and slp_7d is not None:
        delta = slp_hours - slp_7d
        base = ("On baseline" if abs(delta) <= 0.3 else
                "Above baseline" if delta > 0.3 else "Below baseline")
    else:
        base = "—"
    sleep_line = f"Sleep {span or '—'} · {sword or '—'} · {base}"

    return f"{rec_line}\n{strain_line}\n{sleep_line}"


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


def nutrition_line():
    """Today's macros from nutrition/sync.py, if present. Never raises."""
    try:
        from datetime import date as _date
        path = os.path.join(ROOT, "nutrition", "daily", f"{_date.today().isoformat()}.json")
        if not os.path.exists(path):
            return None
        n = load_json(path)
        t = n.get("totals", {}) or {}
        g = n.get("goals", {}) or {}

        def fmt(val, goal, unit):
            if val is None:
                return None
            s = f"{round(val)}{unit}"
            if goal:
                s += f" of {round(goal)}{unit} goal"
            return s
        bits = [
            ("calories", fmt(t.get("calories"), g.get("calories"), "")),
            ("protein", fmt(t.get("protein_g"), g.get("protein_g"), "g")),
            ("carbs", fmt(t.get("carbs_g"), g.get("carbs_g"), "g")),
            ("fat", fmt(t.get("fat_g"), g.get("fat_g"), "g")),
        ]
        parts = [f"{label} {v}" for label, v in bits if v]
        return ", ".join(parts) if parts else None
    except Exception as e:
        log(f"nutrition parse failed (non-fatal): {e}")
        return None


def _today_active_cal(today):
    """Today's accumulated active-calories (or None) — fed to load_band_for() for the
    shared load-band framing. Never raises."""
    try:
        path = os.path.join(HERE, "daily_activity", f"{today}.json")
        if not os.path.exists(path):
            return None
        return load_json(path).get("active-calories")
    except Exception:
        return None


def activity_today_line(today):
    """Today's accumulated activity (steps / active time / calories burned / active
    calories) from daily_activity/<today>.json, if present. Used to make the daytime
    read evolve as the day fills in. Never raises; returns None if no file yet."""
    try:
        path = os.path.join(HERE, "daily_activity", f"{today}.json")
        if not os.path.exists(path):
            return None
        act = load_json(path)
        steps = act.get("active-steps") or act.get("step_count")
        active_min = iso_duration_to_min(act.get("duration") or act.get("active-time"))
        cal = act.get("calories")
        active_cal = act.get("active-calories")
        bits = []
        if steps is not None:
            bits.append(f"{int(steps):,} steps so far")
        if active_min is not None:
            bits.append(f"{min_to_hm(active_min)} active")
        if cal is not None:
            bits.append(f"{round(cal):,} calories burned")
        # Express today's exertion as the shared load BAND, not a raw active-calorie
        # number — same thresholds the Recovery tile / Activity card / LSI use.
        if active_cal is not None:
            bits.append(f"{load_band_for(active_cal)} training load")
        return ", ".join(bits) if bits else None
    except Exception as e:
        log(f"activity parse failed (non-fatal): {e}")
        return None


def nutrition_gap_line():
    """Today's macros WITH the delta vs target spelled out (e.g.
    'protein 126g of 372g goal -> 246g gap'). Richer than nutrition_line(); used in
    the prompt so the model can frame how far ahead/behind the day is. Never raises."""
    try:
        from datetime import date as _date
        path = os.path.join(ROOT, "nutrition", "daily", f"{_date.today().isoformat()}.json")
        if not os.path.exists(path):
            return None
        n = load_json(path)
        t = n.get("totals", {}) or {}
        g = n.get("goals", {}) or {}
        bits = []
        cal, cal_goal = t.get("calories"), g.get("calories")
        if cal is not None and cal_goal:
            gap = round(cal_goal - cal)
            tail = f"{gap} left" if gap > 0 else (f"{abs(gap)} over" if gap < 0 else "right on target")
            bits.append(f"calories {round(cal)} of {round(cal_goal)} goal -> {tail}")
        prot, prot_goal = t.get("protein_g"), g.get("protein_g")
        if prot is not None and prot_goal:
            gap = round(prot_goal - prot)
            tail = f"{gap}g gap" if gap > 0 else ("target hit" if gap == 0 else f"{abs(gap)}g over")
            bits.append(f"protein {round(prot)}g of {round(prot_goal)}g goal -> {tail}")
        for label, vk, gk in (("carbs", "carbs_g", "carbs_g"), ("fat", "fat_g", "fat_g")):
            v, gl = t.get(vk), g.get(gk)
            if v is not None and gl:
                bits.append(f"{label} {round(v)}g of {round(gl)}g goal")
        return "; ".join(bits) if bits else None
    except Exception as e:
        log(f"nutrition-gap parse failed (non-fatal): {e}")
        return None


def meals_in_window(now, hours=4):
    """Layer 4 (fuel slots): today's meals logged within the last `hours`, oldest
    first, as a compact timeline string carrying macros + clock time — e.g.
    "Burger and Fruit Cup at 11:44am (35g protein, 750 cal); Cheetos at 7:44pm
    (6g protein, 470 cal)". Reads nutrition/daily/<today>.json raw.meals (each meal
    has title/time/calories/protein/...). Returns (timeline_str, first_clock_str) or
    (None, None) when nothing's in the window. Never raises."""
    try:
        today = now.date().isoformat()
        path = os.path.join(ROOT, "nutrition", "daily", f"{today}.json")
        if not os.path.exists(path):
            return None, None
        meals = ((load_json(path).get("raw") or {}).get("meals")) or []
        cutoff = now.hour * 60 + now.minute - hours * 60
        picked = []
        for m in meals:
            t = m.get("time")
            if not t or ":" not in t:
                continue
            try:
                hh, mm = t.split(":")[:2]
                tod = int(hh) * 60 + int(mm)
            except Exception:
                continue
            if tod >= cutoff:
                picked.append((tod, m))
        if not picked:
            return None, None
        picked.sort(key=lambda x: x[0])

        def clock(tod):
            h, mn = divmod(tod, 60)
            ap = "am" if h < 12 else "pm"
            return f"{h % 12 or 12}:{mn:02d}{ap}"

        parts = []
        for tod, m in picked:
            title = (m.get("title") or "meal").strip()
            macros = []
            if m.get("protein") is not None:
                macros.append(f"{round(m['protein'])}g protein")
            if m.get("calories") is not None:
                macros.append(f"{round(m['calories'])} cal")
            mac = f" ({', '.join(macros)})" if macros else ""
            parts.append(f"{title} at {clock(tod)}{mac}")
        return "; ".join(parts), clock(picked[0][0])
    except Exception as e:
        log(f"meals-window parse failed (non-fatal): {e}")
        return None, None


# ============================================================================
# Nutrition nudge — single-line, time-aware "what to eat next" call.
# Generated each fire alongside the prose, written to summary.json.nutrition_nudge.
# Deterministic priority rules pick WHICH issue fires (so it can't drift or alarm
# off-clock); claude -p only phrases the chosen call in Alfie's voice.
# ============================================================================

# Expected fraction of the daily macro target eaten by each hour (CDT clock).
# Linearly interpolated between points. A nudge only fires when actual is
# meaningfully off this pace (the priority rules below bake the thresholds in).
NUDGE_CURVE = [(6, 0.0), (10, 0.25), (13, 0.50), (18, 0.80), (21, 1.0)]

# The stale-data message (point 5 of the spec): nutrition syncs every 30 min, so
# if the file hasn't refreshed in 4+ waking hours the nudge can't be trusted.
NUDGE_STALE_MSG = "Log a meal to refresh the nudge."

# rule key -> the situation handed to claude. The model phrases ONE action line.
NUDGE_RULES = {
    "protein_critical": "Protein is critically behind for this point in the day. Tell him to front-load protein into the very next meal to catch the gap.",
    "calories_low":     "Calories are dangerously low for the evening — on a recomp that risks burning muscle. Tell him to eat a real, protein-anchored meal now.",
    "calories_over":    "Calories are already past the day's target and it isn't evening yet — he'll overshoot. Tell him to keep the remaining meals light.",
    "fat_over":         "Fat is over budget for the day. Tell him to pull back oils and fats at the remaining meals.",
    "carbs_low":        "Carbs are critically low for midday — energy crash risk. Tell him to add carbs at the next meal.",
    "on_pace":          "Everything is tracking on pace. Give a short, calm on-pace confirmation — keep meal pacing steady.",
}


def expected_fraction(now):
    """Interpolate NUDGE_CURVE -> expected % (0-1) of daily target by this hour."""
    h = now.hour + now.minute / 60.0
    pts = NUDGE_CURVE
    if h <= pts[0][0]:
        return 0.0
    if h >= pts[-1][0]:
        return 1.0
    for (h0, f0), (h1, f1) in zip(pts, pts[1:]):
        if h0 <= h <= h1:
            return f0 + (f1 - f0) * (h - h0) / (h1 - h0)
    return 1.0


def nutrition_decision(totals, goals, now):
    """Pick the single highest-priority nudge rule (or 'on_pace') from intake vs
    target and the time of day. Pure/deterministic so it's unit-testable and never
    alarms off-clock (e.g. low intake at 11 AM doesn't fire — expected pace is low).
    Returns a NUDGE_RULES key."""
    h = now.hour + now.minute / 60.0

    def frac(v, g):
        return (v / g) if (v not in (None, "") and g) else None

    cal = frac(totals.get("calories"), goals.get("calories"))
    pro = frac(totals.get("protein_g"), goals.get("protein_g"))
    carb = frac(totals.get("carbs_g"), goals.get("carbs_g"))
    fat = frac(totals.get("fat_g"), goals.get("fat_g"))

    # 1 — protein gap critical: <30% by midday, OR <70% by 8 PM
    if pro is not None and ((h >= 12 and pro < 0.30) or (h >= 20 and pro < 0.70)):
        return "protein_critical"
    # 2 — calories dangerously low by 6 PM (muscle-loss risk on a recomp)
    if cal is not None and h >= 18 and cal < 0.40:
        return "calories_low"
    # 3 — calories already over before 6 PM (will overshoot the day)
    if cal is not None and h < 18 and cal > 1.0:
        return "calories_over"
    # 4 — fat over budget (any time of day)
    if fat is not None and fat > 1.0:
        return "fat_over"
    # 5 — carbs critically low by midday
    if carb is not None and h >= 12 and carb < 0.30:
        return "carbs_low"
    # 6 — everything on pace
    return "on_pace"


def _nutrition_synced_age_hours(n, now):
    """Hours since the nutrition file last synced, or None if unknown."""
    ts = n.get("synced_at")
    if not ts:
        return None
    try:
        synced = datetime.fromisoformat(ts)
        if synced.tzinfo is None:
            synced = synced.astimezone()
        return (now - synced).total_seconds() / 3600.0
    except Exception:
        return None


def _clean_nudge(text):
    """Single clean line: strip markdown, leading arrows/bullets, stray percentages."""
    t = clean(text)                          # markdown strip + whitespace collapse
    t = t.lstrip("→-•* ").strip()
    t = re.sub(r"\s*\d+\s*%", "", t)          # belt-and-suspenders: kill any percentage
    # keep only the first sentence if the model rambled into a second
    parts = re.split(r"(?<=[.!])\s+", t)
    return parts[0].strip() if parts else t


def build_nutrition_nudge(now):
    """One-line, time-aware nutrition nudge for the dashboard card. Reads today's
    intake + targets, applies the deterministic priority rules, and has claude -p
    phrase the chosen action in Alfie's voice. Returns "" (card hides) when there's
    no data or it's pre-waking; the stale message when the sync has gone quiet."""
    try:
        today = now.date().isoformat()
        path = os.path.join(ROOT, "nutrition", "daily", f"{today}.json")
        if not os.path.exists(path):
            return ""
        n = load_json(path)
        totals = n.get("totals", {}) or {}
        goals = n.get("goals", {}) or {}
        if not goals:
            return ""

        h = now.hour + now.minute / 60.0
        waking = 7 <= h <= 22
        if not waking:
            return ""   # pre-dawn / overnight: nothing to nudge yet

        # Stale-data guard: syncs run every 30 min, so 4+ waking hours quiet = trust lost.
        age = _nutrition_synced_age_hours(n, now)
        if age is not None and age >= 4:
            return NUDGE_STALE_MSG

        rule = nutrition_decision(totals, goals, now)
        facts = nutrition_gap_line() or "no meals logged yet"
        prompt = (
            "You write ONE short nutrition nudge line for Alfie's fitness dashboard. "
            "It tells him the single most important food action to take right now.\n\n"
            "HARD RULES (absolute):\n"
            "- EXACTLY one sentence, 20 words or fewer.\n"
            "- Actionable — say WHAT to do, not just that he's short.\n"
            "- Calibration, not alarm. Confident, plain, direct.\n"
            "- Gram amounts are fine (e.g. \"50g\"). NO percentages, NO decimals, NO "
            "biometric jargon (no HRV, ms, BPM), NO \"macros\" label.\n"
            "- Do NOT use the words \"should\" or \"please\". No soft hedging.\n"
            "- No preamble, no quotes, no arrow, no label — output ONLY the sentence.\n\n"
            f"{goal_framing()}"
            f"Time now: {now.strftime('%I:%M %p').lstrip('0')}.\n"
            f"Today so far: {facts}\n\n"
            f"THE SITUATION: {NUDGE_RULES[rule]}\n\n"
            "Examples of the voice (do not copy):\n"
            "- Front-load protein at lunch — make it carry 50g.\n"
            "- Calories on pace, but protein's trailing — load dinner.\n"
            "- Fat budget gone — pull back oils at dinner.\n"
            "- On pace across all macros — keep meal pacing steady.\n\n"
            "Write the one-line nudge now — nothing else."
        )
        raw = call_claude(prompt)
        nudge = _clean_nudge(raw)
        log(f"nutrition nudge: rule={rule} -> {nudge!r}")
        return nudge
    except Exception as e:
        log(f"nutrition nudge failed (non-fatal): {e}")
        return ""


def _transit_path(d):
    """Today's snapshot path. Filename pattern: <date>-transit-snapshot.md."""
    return os.path.join(TRANSIT_DIR, f"{d.isoformat()}-transit-snapshot.md")


def load_today_transits():
    """Read today's transit snapshot and return a compact list of tier 1-4
    health-relevant strings. Filters to transiting Moon/Saturn/Mars/Jupiter
    hitting natal Moon/Saturn/Mars/Ascendant; drops everything else
    (relationships, Vertex, asteroids, non-health). Never raises."""
    path = _transit_path(date.today())
    if not os.path.exists(path):
        log(f"no transit snapshot for today ({path}) — proceeding without transits")
        return []
    try:
        with open(path) as f:
            text = f.read()
    except Exception as e:
        log(f"transit read failed (non-fatal): {e}")
        return []

    out = []

    # Tier 1 also covers Moon SIGN (ingress), if the snapshot states it.
    msign = re.search(rf"Moon\s+(?:transiting|in|enters?|ingress(?:es)?(?:\s+into)?)\s+({_SIGNS})", text)
    if msign:
        sign = msign.group(1)
        out.append(f"Tier 1 — Moon transiting {sign} (body focus: {BODY_MAPPING[sign]})")

    # Aspect lines: "Transit <Planet> <aspect> natal <Target>".
    pat = re.compile(
        rf"Transit\s+(\w+)(?:\s+Rx)?\s+({'|'.join(_ASPECTS)})\s+natal\s+([A-Za-z]+)",
        re.IGNORECASE)
    seen = set()
    for m in pat.finditer(text):
        planet, aspect, target = m.group(1), m.group(2).lower(), m.group(3)
        planet = planet.capitalize()
        # Normalize natal target token (ASC -> Ascendant).
        tnorm = "Ascendant" if target.upper() == "ASC" else target.capitalize()
        if planet not in _TRANSIT_TIER:
            continue
        if tnorm not in {"Moon", "Saturn", "Mars", "Ascendant"}:
            continue
        if aspect == "opposition":
            aspect = "opposite"
        tier = _TRANSIT_TIER[planet]
        key = (planet, aspect, tnorm)
        if key in seen:
            continue
        seen.add(key)
        out.append(f"Tier {tier} — transiting {planet} {aspect} natal {tnorm}")

    out.sort(key=lambda s: s[5] if len(s) > 5 else "9")  # rough tier order
    log(f"transits: {len(out)} relevant aspect(s) after filtering")
    return out


# ============================================================================
# Day in Review — nightly freeze (fires 21:45 CST via the polar-summary plist)
# At the night slot we generate day_review.json INSTEAD OF the regular summary:
# it freezes the day's activity + nutrition + an AI verdict + plain-English prose.
# The dashboard reads it next morning until the next night's fire overwrites it.
# ============================================================================

def is_night_review(now):
    """True if the fire time is in the 21:30–22:00 nightly-review window."""
    m = now.hour * 60 + now.minute
    return 21 * 60 + 30 <= m <= 22 * 60


def iso_duration_to_min(iso):
    """'PT4H47M' -> 287 (minutes). Tolerant; returns None on junk."""
    if not iso or not isinstance(iso, str):
        return None
    m = re.match(r"^P(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$", iso)
    if not m:
        return None
    h, mn, s = int(m.group(1) or 0), int(m.group(2) or 0), int(m.group(3) or 0)
    return h * 60 + mn + round(s / 60)


def min_to_hm(total_min):
    """287 -> '4h 47m', 45 -> '45m', 120 -> '2h'."""
    if total_min is None:
        return "—"
    h, mn = divmod(int(total_min), 60)
    if h and mn:
        return f"{h}h {mn}m"
    if h:
        return f"{h}h"
    return f"{mn}m"


def compute_verdict(steps, active_min, deficit, protein_gap):
    """Single label from simple thresholds, tuned for Alfie (avg 3–7k steps/day).
    Order matters: Big (high output) → Great (targets hit) → Easy (restful) → Solid.
      Big:   10,000+ steps OR 5h+ active OR deficit > 700
      Great: 8,000+ steps AND protein within 50g AND deficit 200–500
      Easy:  < 5,000 steps AND < 1h active AND no real deficit (< 200)
      Solid: everything in between (the default day)
    """
    steps = steps or 0
    active_min = active_min or 0
    deficit = deficit or 0
    if steps >= 10000 or active_min >= 300 or deficit > 700:
        return "Big"
    if (steps >= 8000 and protein_gap is not None and protein_gap <= 50
            and 200 <= deficit <= 500):
        return "Great"
    if steps < 5000 and active_min < 60 and deficit < 200:
        return "Easy"
    return "Solid"


VERDICT_FLAVOR = {
    "Easy":  "an easy, restful day — low movement",
    "Solid": "a solid, balanced day",
    "Great": "a great day — steps and protein on target with a clean deficit",
    "Big":   "a big day — high output, real burn",
}


def build_day_review_prose(stats, verdict, date_iso=None):
    """Ask claude -p for a 2–3 sentence plain-English wrap-up of the day, same
    voice as the Today's Read prose. Mixes activity + nutrition, ends with a
    forward-looking nudge for tomorrow. No jargon, no percentages, no biometrics.
    On an explicit rest day the wrap-up reframes around recovery, not output."""
    s = stats
    rest = is_rest_day(date_iso) if date_iso else False
    # On a rest day, don't narrate "a big day — high output" off accumulated movement.
    flavor = ("a deliberate rest day — recovery, not output" if rest
              else VERDICT_FLAVOR.get(verdict, "a normal day"))
    deficit = s["net_deficit"]
    eat_line = (f"ran a calorie deficit of about {deficit}" if deficit and deficit > 0
                else (f"ate about {abs(deficit)} over what he burned" if deficit and deficit < 0
                      else "ate right around what he burned"))
    protein_line = (f"hit his protein target" if s["protein_gap_g"] is not None and s["protein_gap_g"] <= 0
                    else f"came up about {s['protein_gap_g']}g short on protein"
                    if s["protein_gap_g"] is not None else "logged some protein")
    prompt = (
        "You are a sharp, plain-spoken fitness coach writing a one-paragraph wrap-up of "
        "Alfie's day for his dashboard. He reads it the next morning. Talk like a human "
        "coach, not a report.\n\n"
        "HARD RULES (absolute):\n"
        "- 2 to 3 sentences. One short paragraph. No headings, no bullets, no preamble.\n"
        "- NO percentages, NO decimals, NO units-with-jargon. Round, everyday numbers only "
        "(you may say things like \"about 6,500 steps\" or \"a 265-calorie deficit\").\n"
        "- NO biometric jargon: no HRV, no Recharge, no BPM, no \"net deficit\" as a label, "
        "no \"macros\". Plain English.\n"
        "- NO astrology, no chart talk.\n"
        "- End with ONE forward-looking nudge for tomorrow (e.g. \"Push protein hard "
        "tomorrow\" or \"Take it easier — you're due a lighter day\").\n\n"
        f"{goal_framing()}"
        f"{rest_day_framing(date_iso) if date_iso else ''}"
        f"Today was {flavor}. The facts:\n"
        f"- Took about {s['steps']:,} steps\n"
        f"- Was active for {s['active_time_display']}\n"
        f"- Burned about {s['calories_burned']:,} calories\n"
        f"- Ate about {s['calories_eaten']:,} calories, so he {eat_line}\n"
        f"- On protein he {protein_line} (ate {s['protein_g']}g)\n\n"
        "Write the paragraph now — nothing else."
    )
    raw = call_claude(prompt)
    return clean(raw)


def generate_day_review(now):
    """Freeze today's stats + verdict + prose into polar/day_review.json, then push."""
    today = now.date().isoformat()

    # --- activity (steps / active time / calories burned) ---
    act_path = os.path.join(HERE, "daily_activity", f"{today}.json")
    act = load_json(act_path) if os.path.exists(act_path) else {}
    steps = act.get("active-steps") or act.get("step_count")
    active_min = iso_duration_to_min(act.get("duration") or act.get("active-time"))
    calories_burned = act.get("calories")
    active_calories = act.get("active-calories")

    # --- nutrition (calories eaten / protein) ---
    nut_path = os.path.join(ROOT, "nutrition", "daily", f"{today}.json")
    nut = load_json(nut_path) if os.path.exists(nut_path) else {}
    totals = nut.get("totals", {}) or {}
    goals = nut.get("goals", {}) or {}
    calories_eaten = totals.get("calories")
    calorie_target = goals.get("calories")
    protein_g = totals.get("protein_g")
    protein_target_g = goals.get("protein_g")

    # --- derived ---
    net_deficit = (round(calories_burned - calories_eaten)
                   if calories_burned is not None and calories_eaten is not None else None)
    protein_gap_g = (round(protein_target_g - protein_g)
                     if protein_target_g is not None and protein_g is not None else None)

    stats = {
        "steps": int(steps) if steps is not None else None,
        "active_minutes": active_min,
        "active_time_display": min_to_hm(active_min),
        "calories_burned": round(calories_burned) if calories_burned is not None else None,
        "active_calories": round(active_calories) if active_calories is not None else None,
        "calories_eaten": round(calories_eaten) if calories_eaten is not None else None,
        "net_deficit": net_deficit,
        "calorie_target": round(calorie_target) if calorie_target is not None else None,
        "protein_g": round(protein_g) if protein_g is not None else None,
        "protein_target_g": round(protein_target_g) if protein_target_g is not None else None,
        "protein_gap_g": protein_gap_g,
    }

    verdict = compute_verdict(stats["steps"], stats["active_minutes"],
                              stats["net_deficit"], stats["protein_gap_g"])
    log(f"day-review {today}: verdict={verdict} steps={stats['steps']} "
        f"active={stats['active_time_display']} deficit={stats['net_deficit']} "
        f"protein_gap={stats['protein_gap_g']}")

    try:
        prose = build_day_review_prose(stats, verdict, today)
    except Exception as e:
        log(f"day-review prose failed (non-fatal): {e}")
        prose = ""

    payload = {
        "date": today,
        "generated_at": now.replace(microsecond=0).isoformat(),
        "verdict": verdict,
        "stats": stats,
        "prose": prose,
    }
    with open(os.path.join(HERE, "day_review.json"), "w") as f:
        json.dump(payload, f, indent=2)
    log("wrote day_review.json")

    try:
        _sweep_stale_git_locks()
        subprocess.run(["git", "add", "polar/day_review.json"], cwd=ROOT, check=True)
        subprocess.run(["git", "commit", "-m", f"chore: day review {today}"],
                       cwd=ROOT, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, check=True,
                       capture_output=True, text=True)
        log("pushed day_review.json")
    except subprocess.CalledProcessError as e:
        log(f"git push failed (non-fatal): {e}")
    return 0


def parse_sections(text):
    """Split Claude output into the five labeled sections. Returns a list of
    {label, text}. Tolerant of markdown (**Label:**, ## Label, Label —/-/:)."""
    # Strip leading markdown markers per line so labels are easy to match.
    label_alt = "|".join(re.escape(l) for l in OUTPUT_SECTIONS)
    # Find each label and capture text up to the next label (or end).
    pat = re.compile(
        rf"(?im)^[\s#*_>-]*({label_alt})\s*[:\-–—]*\s*(.*?)(?=^[\s#*_>-]*(?:{label_alt})\s*[:\-–—]|\Z)",
        re.S)
    sections = []
    for m in pat.finditer(text):
        label = m.group(1).strip()
        body = re.sub(r"[*_`#>]", "", m.group(2))
        body = re.sub(r"\s+", " ", body).strip()
        if body:
            sections.append({"label": label, "text": body})
    return sections


def call_claude(prompt):
    # v0.1 role-router shim (09_Reference/agent_workflow/role_router_spec.md):
    # reasoning-lane calls go through ~/bin/llm so backend choice, billing, and
    # usage logging live in one auditable place. The shim dispatches the
    # reasoning lane to `claude -p`, so behavior is unchanged — but a failure
    # there still surfaces here as a "claude exited <n>" RuntimeError, which the
    # silent-401 notifier (_notify_dark_fire) parses. Keep that wording.
    # Original direct `claude -p` body is preserved commented out below for one
    # rollback cycle (role_router_spec acceptance criterion #5).
    llm = shutil.which("llm") or os.path.expanduser("~/bin/llm")
    env = {**os.environ, "LLM_CALLER": "polar/summary.py"}
    out = subprocess.run(
        [llm, "--lane", "reasoning", prompt],
        capture_output=True, text=True, timeout=180, cwd=ROOT, env=env,
    )
    if out.returncode != 0:
        # The shim folds the backend's stderr/stdout into its own diagnostics;
        # stderr first (real errors + [AUTH]/[ERROR] tag), else stdout body.
        detail = (out.stderr.strip() or out.stdout.strip())[:300]
        raise RuntimeError(f"claude exited {out.returncode}: {detail}")
    return out.stdout

# --- ORIGINAL pre-router body (role_router_spec #5: keep one cycle) ----------
# def call_claude(prompt):
#     claude = shutil.which("claude") or "/Users/alfredovargas/.local/bin/claude"
#     out = subprocess.run(
#         [claude, "-p", prompt],
#         capture_output=True, text=True, timeout=180, cwd=ROOT,
#     )
#     if out.returncode != 0:
#         # `claude -p` writes auth/401 failures to STDOUT, not stderr — fold both
#         # in so the silent-401 notifier (_notify_dark_fire) can tell auth from
#         # rate from other. stderr first (real errors), else the stdout body.
#         detail = (out.stderr.strip() or out.stdout.strip())[:300]
#         raise RuntimeError(f"claude exited {out.returncode}: {detail}")
#     return out.stdout
# -----------------------------------------------------------------------------


def clean(text):
    text = re.sub(r"[*_`#>]", "", text)                 # strip markdown emphasis/headers
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _sweep_stale_git_locks():
    try:
        lock_paths = (
            os.path.join(ROOT, ".git", "HEAD.lock"),
            os.path.join(ROOT, ".git", "index.lock"),
        )
        now_ts = datetime.now().timestamp()

        for path in lock_paths:
            try:
                if not os.path.exists(path):
                    continue

                name = os.path.basename(path)
                mtime = os.path.getmtime(path)
                age = now_ts - mtime
                mtime_iso = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")

                if age <= 600:
                    log(f"[stale-lock] held, skipping {name}")
                    continue

                try:
                    proc = subprocess.run(
                        ["lsof", "--", path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=5,
                    )
                except Exception:
                    log(f"[stale-lock] held, skipping {name}")
                    continue

                if proc.returncode == 0 and proc.stdout.strip():
                    log(f"[stale-lock] held, skipping {name}")
                    continue

                age_min = age / 60.0
                os.remove(path)
                log(f"[stale-lock] removed {name} (age={age_min:.1f}m, mtime={mtime_iso})")
            except Exception:
                continue
    except Exception:
        pass


def git_push(slot, date):
    try:
        _sweep_stale_git_locks()
        subprocess.run(["git", "add", "polar/summary.json"], cwd=ROOT, check=True)
        subprocess.run(["git", "commit", "-m", f"chore: {slot} summary {date}"],
                       cwd=ROOT, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, check=True,
                       capture_output=True, text=True)
        log("pushed summary.json")
    except subprocess.CalledProcessError as e:
        log(f"git push failed (non-fatal): {e}")        # likely no change or offline


def _arg_value(flag):
    """Return the value following `flag` in argv, or None."""
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def _notify_dark_fire(exc):
    """Silent-401 notifier (WHEN_HOME.md #9). When an AI-prose fire dies — most
    often an expired/revoked Anthropic OAuth token (`claude -p` exits 1, 401 to
    stdout) — the outer handler used to sys.exit(0) with NO trace: no summary, no
    log alert, dashboard pinned to the last good slot until someone noticed by
    accident. This leaves a breadcrumb so the dashboard never goes dark silently.
    Appends one line to WHEN_HOME.md (timestamp · slot · claude exit · theory ·
    excerpt) and fires a best-effort osascript banner (no-op without a GUI login,
    e.g. under launchd). Never raises into the caller — failures are swallowed."""
    now = datetime.now().astimezone()
    slot = _arg_value("--slot") or slot_for(now)
    msg = re.sub(r"\s+", " ", str(exc)).strip()
    low = msg.lower()
    if any(k in low for k in ("401", "oauth", "unauthor", "expired", "invalid api", "auth")):
        theory = "auth — re-auth: run `claude`, then backfill the slot"
    elif any(k in low for k in ("429", "rate", "overloaded", "quota", "credit")):
        theory = "rate/quota/credit"
    elif "exited" in low or "timeout" in low or "timed out" in low:
        theory = "other (claude nonzero exit / timeout)"
    else:
        theory = "other"
    m = re.search(r"claude exited (-?\d+)", msg)
    code = m.group(1) if m else "?"
    stamp = now.strftime("%Y-%m-%d %H:%M %Z")
    line = (f"- ⚠️ **{stamp}** — AI-prose fire went DARK · slot=`{slot}` · "
            f"claude_exit=`{code}` · theory: {theory} · excerpt: `{msg[:200]}`\n")
    path = os.environ.get("WHEN_HOME_PATH") or os.path.join(ROOT, "WHEN_HOME.md")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
        log(f"silent-fire alert appended to {os.path.basename(path)} "
            f"(slot={slot}, claude_exit={code}, theory={theory.split(' —')[0]})")
    except Exception as e:
        log(f"silent-fire alert write failed (non-fatal): {e}")
    # Best-effort graphical banner — harmless no-op when no aqua session is
    # attached (launchd). Swallow everything; the on-disk breadcrumb is the
    # real channel, the banner is a bonus when Alfie is logged in.
    try:
        subprocess.run(
            ["osascript", "-e",
             ('display notification "AI-prose fire failed (slot ' + slot + ', '
              + theory.split(" —")[0] + '). Dashboard may be stale — re-auth claude." '
              'with title "Fitness dashboard went dark"')],
            capture_output=True, timeout=10)
    except Exception:
        pass


def main():
    now = datetime.now().astimezone()
    # Manual-test overrides: `--slot NAME` forces a slot (and bypasses the nightly
    # day-review branch so you can regenerate any slot at any time); `--out PATH`
    # writes to an alternate file and skips the git push.
    slot_override = _arg_value("--slot")
    out_path = _arg_value("--out")
    slot = slot_override or slot_for(now)

    # Nightly Day-in-Review slot (21:45 fire) — or forced via `--day-review`.
    # Generates day_review.json INSTEAD OF the regular summary.json. A `--slot`
    # override skips this so a forced slot always produces a regular summary.
    if not slot_override and ("--day-review" in sys.argv or is_night_review(now)):
        return generate_day_review(now)

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
    nutrition = nutrition_line()              # plain "X of Y goal" — kept for data_basis
    today_iso = now.date().isoformat()
    activity = activity_today_line(today_iso)  # today's accumulated steps / active / burn
    nutrition_detail = nutrition_gap_line()    # macros + delta vs target, for the prompt

    # Feed today's accumulated activity + nutrition into the data-bearing slots (recovery,
    # both fuel checks, both train windows). The 4 AM sleep slot is too early to have any.
    # The day's stat recap stays owned by the 9:45 PM Day-in-Review card.
    show_today_data = slot in TODAY_DATA_SLOTS
    today_block = ""
    if show_today_data:
        if activity:
            today_block += f"- Today's activity so far: {activity}\n"
        # Frame today's exertion as how much of the morning recovery reserve he's
        # spent, using the shared load band (—/Light/Moderate/Heavy) — never a raw
        # active-calorie figure. Mirrors the Recovery tile's "Spent so far" line.
        load_band = load_band_for(_today_active_cal(today_iso))
        if load_band != "—":
            today_block += (f"- Today's load so far: he's spent {load_band} of his recovery reserve "
                            f"(frame as Light/Moderate/Heavy effort, never as a calorie number).\n")
        if nutrition_detail:
            today_block += f"- Today's nutrition so far: {nutrition_detail}\n"
        elif nutrition:
            today_block += f"- Today's nutrition so far: {nutrition}\n"

    # Direct-data reframe (Layer 1): astrology context (natal architecture + transits)
    # is no longer injected into the prose. load_today_transits stays defined for any
    # other consumer, but the prompt and the rendered Reading are pure physiology now.
    transits = []

    # Layer 4 — fuel slots read the recent meal log + the energy response since the
    # first meal in the window, and comment on whether fueling matches output.
    fuel_block = ""
    if slot in ("fuel-1", "fuel-2"):
        timeline, first_t = meals_in_window(now, hours=4)
        if timeline:
            fuel_block = (
                f"- Meals logged in the last ~4 hours (oldest first): {timeline}\n"
                f"- First meal in that window was at {first_t}; read today's activity/load curve "
                f"since then as the energy response, and judge whether what he ate is matching the "
                f"output.\n"
            )
        else:
            fuel_block = ("- No meals logged in the last ~4 hours — name the gap and say what to "
                          "eat next.\n")

    slot_cfg = SLOT_FRAMING.get(slot, SLOT_FRAMING["recovery"])
    blocks = slot_cfg["blocks"]
    rest_today = is_rest_day(today_iso)

    # Per-block instructions (Read + the decision verdicts the slot calls for) and the
    # bare output skeleton claude -p fills in line by line.
    block_instrs = "\n".join(BLOCK_INSTR[b](slot, rest_today) for b in blocks)
    output_skeleton = "\n".join(f"{b}: ..." for b in blocks)

    prompt = (
        "You are a recovery and performance coach writing a tactical daily brief for an athlete "
        "(Alfie). He knows his own body and does NOT want jargon. In plain English, answer: what does "
        "his state MEAN, and — should he work out, eat, rest?\n\n"
        "HARD OUTPUT RULES (these are absolute):\n"
        "- NEVER quote recovery, heart-rate-variability, or sleep figures, and NEVER write "
        "percentages, decimals, or biometric units in the Read line. No \"72ms\", \"5/6\", \"6.1h\", "
        "\"%\". (The Eat line MAY use gram amounts and clock times — that is the one exception.)\n"
        "- NEVER write biometric jargon: HRV, Recharge, Nightly Recharge, BPM, ANS, Sleep Score.\n"
        "- NO ASTROLOGY, AT ALL. Never mention the moon, planets, signs, houses, aspects, transits, a "
        "chart, anything natal/lunar/cosmic — not named, not as subtle 'texture'. If a thought only "
        "makes sense through astrology, drop it.\n"
        "- The data below INFORMS you but must NOT be quoted back. Translate it into plain language; "
        "the data sets the conclusion, the conclusion is what you write.\n"
        "- Every decision line MUST start with one of its allowed verdict words, then ONE tight "
        "qualifier (15 words max). No preamble, no markdown, no closing remarks.\n\n"
        "=== WHERE ALFIE IS IN HIS DAY (sets the tone) ===\n"
        f"{slot_cfg['when']}\n"
        f"The Read line should focus on: {slot_cfg['read']}.\n\n"
        "=== RECOVERY & FITNESS DATA (informs you — never quote it) ===\n"
        "(Polar Nightly Recharge is a 1-6 scale, 6 best.)\n"
        f"- Recovery status today: {rec_today}/6 (7-day avg {rec_7d})\n"
        f"- Heart-rate variability today: {hrv_today} ms (7-day avg {hrv_7d})\n"
        f"- Sleep last night: {slp_hours} hours (7-day avg {slp_7d})\n"
        f"- Body composition: {body}\n"
        f"{today_block}"
        f"{fuel_block}"
        f"\n{goal_framing()}"
        f"{rest_day_framing(today_iso)}"
        "=== WRITE THESE LABELED LINES, IN THIS ORDER, AND NOTHING ELSE ===\n"
        "Each line starts with its label and a colon. No extra lines, no headers, no markdown.\n\n"
        f"{block_instrs}\n\n"
        "Output skeleton (replace each ... with your line):\n"
        f"{output_skeleton}\n"
    )

    log(f"slot={slot} recharge={rec_today} hrv={hrv_today} sleep={slp_hours} "
        f"activity={'y' if (show_today_data and activity) else 'n'} blocks={','.join(blocks)}")
    raw = call_claude(prompt)
    parsed = parse_brief_blocks(raw, blocks)

    # Deterministic Recovery word (overnight-derived; constant across the day's fires).
    rec_word = recovery_word(rec_today, hrv_today, hrv_7d)

    # Deterministic State block — mirrors the Recovery / Strain / Sleep rings exactly.
    # hrv_all_mean is the mean of every recharge HRV (the same baseline app.js feeds
    # computeRecoveryScore) so the State Recovery number equals the ring number.
    hrv_vals = []
    for d in rec_dates:
        try:
            v = load_json(os.path.join(HERE, "recharge", f"{d}.json")).get("heart_rate_variability_avg")
            if v is not None:
                hrv_vals.append(v)
        except Exception:
            pass
    hrv_all_mean = mean(hrv_vals) if hrv_vals else None
    active_cal = _today_active_cal(today_iso)
    state_block = build_state_block(slot, rec, slp, rec_word, hrv_all_mean,
                                    hrv_today, hrv_7d, slp_hours, slp_7d, active_cal)

    # Assemble the multiline tactical brief: deterministic State, then the LLM Read +
    # decision verdicts under their human-facing question headers. Newlines are load-
    # bearing — the render layer splits on blank lines and preserves them.
    parts = [f"State\n{state_block}"]
    for b in blocks:
        txt = parsed.get(b) or "—"
        parts.append(f"{block_header(b, slot)}\n{txt}")
    reading = "\n\n".join(parts)
    if not reading.strip():
        raise RuntimeError("empty tactical brief")

    # Keep the stored schema shape stable (summary + sections + simple) so nothing
    # downstream breaks; the card reads simple.reading. `performance` keeps the workout
    # (or sleep-slot setup) verdict as a backward-compat fallback for the renderer.
    perf_text = parsed.get("Workout") or parsed.get("Setup") or ""
    sections = [
        {"label": "Recovery", "text": rec_word or ""},
        {"label": "Reading", "text": reading},
        {"label": "Performance", "text": perf_text},
        {"label": "Transit", "text": "none"},
    ]
    summary = "\n\n".join(f"{s['label']}: {s['text']}" for s in sections if s["text"])
    simple = {
        "recovery": rec_word,
        "reading": reading,
        "performance": perf_text or None,
        "transit": None,
    }

    nutrition_nudge = build_nutrition_nudge(now)

    payload = {
        "generated_at": now.replace(microsecond=0).isoformat(),
        "slot": slot,
        "summary": summary,
        "sections": sections,
        "simple": simple,
        "nutrition_nudge": nutrition_nudge,
        "transits": transits,
        "data_basis": {
            "recharge_today": rec_today,
            "sleep_hours": slp_hours,
            "hrv_today": hrv_today,
            "hrv_7d_avg": hrv_7d,
            "nutrition": nutrition,
            "nutrition_detail": nutrition_detail,
            "activity_today": activity if show_today_data else None,
        },
    }
    _append_metric_snapshot(now, slot, rec, slp, hrv_all_mean, hrv_today, hrv_7d, slp_hours, active_cal)
    target = out_path or os.path.join(HERE, "summary.json")
    with open(target, "w") as f:
        json.dump(payload, f, indent=2)
    log(f"wrote {target}")

    # Manual test runs (`--out`) don't touch git; only the real summary.json is pushed.
    if not out_path:
        git_push(slot, now.date().isoformat())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"FATAL: {e}")
        _notify_dark_fire(e)   # WHEN_HOME.md #9 — leave a breadcrumb, don't go dark silent
        sys.exit(0)   # never let launchd mark a hard failure / spin
