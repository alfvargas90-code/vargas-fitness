#!/usr/bin/env python3
"""Generate an AI health read for the fitness dashboard.

Reads the latest Polar recharge/sleep data + body-comp seed, asks `claude -p`
(rides Alfie's Claude Max plan — no API key, no marginal cost) for a plain-English
read in four sections (Recovery / Reading / Performance / Transit), writes
polar/summary.json with a `simple` block the dashboard card renders, and pushes so
the live URL updates. The `Reading` section fuses physical body-area notes with the
natal recovery trait into ONE flowing paragraph — astrology is texture, never named.
The biometrics inform the read but never appear in it — no raw numbers, units, or jargon.

Run by the com.alfredo.polar-summary LaunchAgent 6x/day (4:15, 9:05, 12:30, 16:45, 20:00, 21:45 CST).
(9:05, not 9:00, so it fires off the :00/:30 boundary the 30-min polar-sync timer hits — avoids the same-minute sync race that left "Today's Read" stale.)
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

# Per-slot framing for the Reading prose. The Recovery WORD is always from overnight
# data (it doesn't change through the day), but the prose around it should move with
# the clock — fresh capacity in the morning, progress-checks midday/afternoon, and a
# present-moment wind-down in the evening that leaves the day's stat recap to the
# 9:45 PM Day-in-Review card.
SLOT_FRAMING = {
    "overnight": (
        "SLOT — OVERNIGHT (~4 AM, Alfie just woke up). The Reading is a first read of what the "
        "night's recovery left him with — the body's report card from sleep.\n"
        "LEAD WITH: the sleep / recharge state — what the body PRODUCED overnight. The very first "
        "sentence must be about the night's recovery, not body areas.\n"
        "Opener examples (do not copy verbatim): \"You came back clean from last night…\" / "
        "\"Last night gave you steady sleep but…\" / \"Recovery landed strong overnight…\"\n"
        "No day-ahead planning yet, no activity or food talk — just where he's starting from."
    ),
    "morning": (
        "SLOT — MORNING (~9 AM, the day is open in front of him). The Reading frames fresh capacity "
        "and the day ahead.\n"
        "LEAD WITH: the day-ahead frame — his capacity to SPEND today. The first sentence looks "
        "forward, not back.\n"
        "Opener examples (do not copy verbatim): \"Day's wide open in front of you…\" / "
        "\"You're walking into today with…\" / \"The morning's clear and the tank's full…\"\n"
        "If a little activity or food is already logged, touch it lightly as a starting point, but "
        "keep the focus forward — on what the day can hold, not what's behind him."
    ),
    "midday": (
        "SLOT — MIDDAY (~12:30 PM, half the day done). The Reading is about how the day is tracking "
        "so far.\n"
        "LEAD WITH: what's ALREADY ACCUMULATED today — a current pace check. The first sentence "
        "names where the day stands right now (steps put down, food/protein pace).\n"
        "Opener examples (do not copy verbatim): \"You've already put down 3,000 steps and…\" / "
        "\"Half the day's logged…\" / \"Morning's behind you with…\"\n"
        "Weave the numbers in as lived context, never a stat list."
    ),
    "afternoon": (
        "SLOT — AFTERNOON (~4:45 PM, day mostly behind him, evening to go). The Reading is a "
        "progress check plus what's left.\n"
        "LEAD WITH: what's LEFT in the day — what to do with the remaining hours. The first "
        "sentence is about the hours still in front of him, not a recap.\n"
        "Opener examples (do not copy verbatim): \"Plenty of day still in you…\" / \"The session "
        "you've been holding off is right there…\" / \"Afternoon's the turn point — you've moved a "
        "little, you've got…\"\n"
        "Reference the accumulated activity and food naturally as part of the read."
    ),
    "evening": (
        "SLOT — EVENING (~8 PM, winding toward night). This is a PRESENT-MOMENT read, NOT a recap. "
        "Do NOT mention steps, calories, protein, active time, or any of the day's accumulated "
        "stats — a separate nightly card owns the day's wrap-up.\n"
        "LEAD WITH: present-moment / sleep-prep state — how the system feels heading into night. "
        "The first sentence is about right now and winding down.\n"
        "Opener examples (do not copy verbatim): \"Day's settled now…\" / \"Heading into night…\" / "
        "\"The work's done; the system feels…\"\n"
        "Focus only on right-now state: how the system feels heading into the night, sleep prep, "
        "and tomorrow as the next platform."
    ),
}
# Slots whose prompt gets today's accumulated activity + nutrition fed in. Overnight is
# too early to have any; evening deliberately omits it (present-moment, no recap).
TODAY_DATA_SLOTS = {"morning", "midday", "afternoon"}


def log(msg):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def slot_for(now):
    """overnight / morning / midday / afternoon / evening from minutes-of-day."""
    m = now.hour * 60 + now.minute
    if 2 * 60 <= m <= 5 * 60 + 59:   return "overnight"  # 02:00–05:59 (4:15 fire)
    if m <= 10 * 60 + 30:   return "morning"      # …–10:30
    if m <= 14 * 60 + 30:   return "midday"       # 10:31–14:30
    if m <= 18 * 60:        return "afternoon"    # 14:31–18:00
    return "evening"                              # 18:01–…


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


def _arg_value(flag):
    """Return the value following `flag` in argv, or None."""
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


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

    # Feed today's accumulated activity + nutrition only into the daytime slots. Overnight
    # is too early to have any; evening is a present-moment read that deliberately leaves
    # the day's stat recap to the 9:45 PM Day-in-Review card.
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

    transits = load_today_transits()
    transit_block = ("\n".join(f"- {t}" for t in transits)
                     if transits else "- No relevant transit data available today.")

    framing = SLOT_FRAMING.get(slot, SLOT_FRAMING["morning"])

    rest_today = is_rest_day(today_iso)

    # Performance verdict set is slot-aware: evening gets the wind-down call, every
    # other slot gets the four daytime training verdicts. An explicit rest day swaps
    # the daytime training verdicts for recovery framing (evening's wind-down already
    # reads as recovery, so it's left alone).
    if slot == "evening":
        perf_instr = (
            "Performance: start with EXACTLY this verdict — Wind down — then one short sentence of "
            "wind-down / sleep-prep reasoning (the day's work is logged; tomorrow is the next "
            "platform). Do NOT use Push hard / Train normally / Moderate effort / Prioritize "
            "recovery at this slot. "
            "Example: \"Wind down. The day's logged — sleep prep is the move now, and tomorrow gives "
            "you a fresh platform to build on.\"\n"
        )
    elif rest_today:
        perf_instr = (
            "Performance: start with EXACTLY one of these verdicts — Rest day / Recover / Protein focus "
            "— then one short sentence framing today as deliberate recovery (protein, hydration, sleep, "
            "easy mobility), NOT training output. Do NOT use Push hard / Train normally / Moderate effort. "
            "Example: \"Rest day. You called it, so today's about protein, water, and an early night — "
            "let the work you've banked settle in.\"\n"
        )
    else:
        perf_instr = (
            "Performance: start with EXACTLY one of these verdicts — Push hard / Train normally / "
            "Moderate effort / Prioritize recovery — then one short sentence of why. "
            "Example: \"Push hard. You came in well above your normal recovery, so today's a green "
            "light to go after it — just keep technique honest if you go heavy.\"\n"
        )

    # Whether the Reading may reference today's rounded activity/food numbers.
    if slot == "evening":
        numbers_rule = (
            "- This is the EVENING slot: write NO numbers at all — no steps, no calories, no protein, "
            "no times. The nightly card recaps the day's stats; your job is the present moment.\n"
        )
    elif show_today_data:
        numbers_rule = (
            "- You MAY reference today's activity and food as rounded, everyday numbers in natural "
            "speech (e.g. \"about 3,000 steps down already\", \"protein's barely halfway\") — but only "
            "woven into the read as lived context, never as a stat list, and never with units/decimals.\n"
        )
    else:
        numbers_rule = "- Do not write numbers; there's no accumulated activity to reference yet.\n"

    prompt = (
        "You are a recovery and performance coach writing a short daily read for an athlete (Alfie). "
        "He knows his own body and his own birth chart well. He does NOT want technical jargon — not "
        "biometric labels, not astrology terminology. Write like a sharp human coach talking to him "
        "in plain English.\n\n"
        "HARD OUTPUT RULES (these are absolute):\n"
        "- NEVER quote the recovery, heart-rate-variability, or sleep figures, and NEVER write "
        "percentages, decimals, or units. No \"72ms\", no \"5/6\", no \"6.1h\", no \"%\".\n"
        "- NEVER write biometric jargon: HRV, Recharge, Nightly Recharge, BPM, ANS, Sleep Score.\n"
        f"{numbers_rule}"
        "- NEVER write astrology jargon: no \"Moon-in-Capricorn\", no \"Uranus-Moon\", no \"Saturn square\", "
        "no aspect names (square / trine / conjunct / opposition / sextile) unless translated into plain "
        "words, no \"natal\", \"Placidus\", or \"transit chart\". The everyday words chart, transit, moon, "
        "and mars are fine when used conversationally and lowercase.\n"
        "- The recovery/sleep data below INFORMS your assessment but must NOT appear in the output. "
        "Translate everything into plain language. The data sets the conclusion; the conclusion is what you write.\n\n"
        "HIERARCHY — measured recovery/fitness data is the source of truth. Natal context and transits are "
        "background for body-area awareness and pattern recognition only; they NEVER override the data. "
        "If a chart theme conflicts with the data, the data wins.\n\n"
        "=== WHERE ALFIE IS IN HIS DAY (sets the tone of the Reading) ===\n"
        f"{framing}\n"
        "The Recovery WORD comes only from the overnight recovery data and stays constant through the "
        "day; it is the PROSE that must move with the slot above.\n\n"
        "=== RECOVERY & FITNESS DATA (informs you — never quote it) ===\n"
        "(Polar Nightly Recharge is a 1-6 scale, 6 best.)\n"
        f"- Recovery status today: {rec_today}/6 (7-day avg {rec_7d})\n"
        f"- Heart-rate variability today: {hrv_today} ms (7-day avg {hrv_7d})\n"
        f"- Sleep last night: {slp_hours} hours (7-day avg {slp_7d})\n"
        f"- Body composition: {body}\n"
        f"{today_block}"
        f"\n{goal_framing()}"
        f"{rest_day_framing(today_iso)}"
        "=== NATAL CONTEXT (static, body-area awareness only) ===\n"
        f"{NATAL_ARCHITECTURE}\n"
        "\n=== TODAY'S RELEVANT TRANSITS (context only) ===\n"
        f"{transit_block}\n\n"
        "Produce EXACTLY these four sections, each starting on its own line with the exact label shown "
        "followed by a colon. No markdown, no bullets, no preamble, no closing remarks.\n\n"
        "Recovery: ONE word only — Poor, Average, Good, or Excellent. Nothing else on this line. "
        "Base it ONLY on the overnight recovery/sleep data, never on the time of day.\n"
        "Reading: ONE paragraph, two or three sentences, flowing prose, written in the tone of the slot "
        "framing above. The FIRST sentence MUST open with the slot's LEAD framing (see the slot block "
        "above) — overnight leads with the night's recovery, morning with the day ahead, midday with "
        "what's accumulated, afternoon with what's left, evening with the present wind-down. Then, in the "
        "MIDDLE of the paragraph, you may blend in: (1) any body areas that actually deserve attention "
        "today (joints, tendons, shoulders, neck, lower body) — mention ONLY when there's a real signal "
        "worth noting; if nothing's flagged, you may skip body areas entirely rather than opening with "
        "them; and (2) how he tends to recover and perform, woven in as character rather than a separate "
        "topic, e.g. \"you're built to recover through steadiness rather than big swings.\" "
        "NEVER label, name, or hint that this is astrology — no \"your chart\", no \"the stars\", no "
        "\"astrologically\", no planet or sign names. No sub-headings inside the paragraph; one smooth read.\n"
        "HARD VARIATION RULES (absolute):\n"
        "- Each slot must OPEN with the slot-specific LEAD framing above. Do NOT start the prose with "
        "\"Nothing's flagging\" or any line about watch areas / body areas — those can appear mid-prose "
        "or be skipped entirely. Never lead with them.\n"
        "- Do not reuse the same opening sentence STRUCTURE across slots; vary the sentence type.\n"
        "- Body areas (knees, joints, shoulders, neck) are optional context — mention only when there's "
        "an actual signal worth noting, not as a recurring opener.\n"
        "- The \"you recover by stacking steady days\" type character framing may appear AT MOST ONCE, in "
        "the middle of the paragraph — never as a verbatim repeat.\n"
        "- Crutch phrases — \"stacking steady days\", \"the tank's full\", \"Nothing's flagging\", \"your "
        "usual watch areas\" — are overused. Use AT MOST ONE of these per prose; find fresh wording for "
        "everything else.\n"
        "Example (afternoon, note it leads with what's LEFT, body areas only mid-prose): \"Plenty of day "
        "still in you, and that walk you've been putting off is right there for the taking. Knees and "
        "shoulders are quiet, nothing pulling for attention — you recover best by stacking steady days, "
        "and a light evening push keeps that streak honest.\"\n"
        f"{perf_instr}"
        "Transit: only if a meaningful planetary transit is actually affecting today; plain "
        "English, one short sentence (e.g. \"Mars is amplifying your drive — channel it into work, not "
        "friction.\"). If nothing meaningful is hitting today, write exactly: none\n"
    )

    log(f"slot={slot} recharge={rec_today} hrv={hrv_today} sleep={slp_hours} "
        f"activity={'y' if (show_today_data and activity) else 'n'} transits={len(transits)}")
    raw = call_claude(prompt)
    sections = parse_sections(raw)

    # Force the Recovery word to the deterministic overnight-derived value so it can't
    # drift between slots on the same day's data (the LLM otherwise re-judges 5/6 → it
    # flickered Good/Excellent across fires). Overwrite the parsed Recovery section so
    # summary + sections + simple all agree.
    rec_word = recovery_word(rec_today, hrv_today, hrv_7d)
    if rec_word:
        rec_sec = next((s for s in sections if s["label"] == "Recovery"), None)
        if rec_sec:
            rec_sec["text"] = rec_word
        else:
            sections.insert(0, {"label": "Recovery", "text": rec_word})

    if sections:
        summary = "\n\n".join(f"{s['label']}: {s['text']}" for s in sections)
    else:
        # Parser found no labeled sections — fall back to a flat cleaned read.
        log("section parse found nothing — falling back to flat summary")
        summary = clean(raw)
    if not summary:
        raise RuntimeError("claude returned empty output")

    # Plain-English block the dashboard card reads. Maps each labeled section to
    # its key; normalizes Recovery to a single word; nulls Transit Impact when no
    # real transit is hitting (so the card skips that section entirely).
    simple = {k: None for k in SIMPLE_KEYS}
    for s in sections:
        key = LABEL_TO_KEY.get(s["label"])
        if key:
            simple[key] = s["text"]
    if simple["recovery"]:
        word = next((w for w in RECOVERY_WORDS
                     if re.search(rf"\b{w}\b", simple["recovery"], re.I)), None)
        if word:
            simple["recovery"] = word
    ti = simple.get("transit")
    if not transits or not ti or ti.strip().lower() == "none" \
            or re.search(r"\bno (significant|relevant|meaningful)\b", ti, re.I):
        simple["transit"] = None

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
        sys.exit(0)   # never let launchd mark a hard failure / spin
