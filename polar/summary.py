#!/usr/bin/env python3
"""Generate an AI health read for the fitness dashboard.

Reads the latest Polar recharge/sleep data + body-comp seed, asks `claude -p`
(rides Alfie's Claude Max plan — no API key, no marginal cost) for a plain-English
read in five sections (Recovery / Physical Themes / Astrology Correlation /
Performance Outlook / Transit Impact), writes polar/summary.json with a `simple`
block the dashboard card renders, and pushes so the live URL updates. The biometrics
inform the read but never appear in it — no raw numbers, units, or jargon.

Run by the com.alfredo.polar-summary LaunchAgent 5x/day (4:15, 9:05, 12:30, 16:45, 20:00 CST).
(9:05, not 9:00, so it fires off the :00/:30 boundary the 30-min polar-sync timer hits — avoids the same-minute sync race that left "Today's Read" stale.)
"""
import json, os, re, shutil, subprocess, sys
from datetime import datetime, date
from statistics import mean

HERE = os.path.dirname(os.path.abspath(__file__))        # .../fitness-dashboard/polar
ROOT = os.path.dirname(HERE)                              # .../fitness-dashboard

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
    "Physical Themes",
    "Astrology Correlation",
    "Performance Outlook",
    "Transit Impact",
]

# Section label -> key in the plain-English `simple` block the dashboard card reads.
LABEL_TO_KEY = {
    "Recovery": "recovery",
    "Physical Themes": "physical_themes",
    "Astrology Correlation": "astrology_correlation",
    "Performance Outlook": "performance_outlook",
    "Transit Impact": "transit_impact",
}
RECOVERY_WORDS = ["Excellent", "Good", "Average", "Poor"]
SIMPLE_KEYS = ["recovery", "physical_themes", "astrology_correlation",
               "performance_outlook", "transit_impact"]


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
    nutrition = nutrition_line()

    nutrition_bullet = f"- Today's nutrition so far: {nutrition}\n" if nutrition else ""
    transits = load_today_transits()
    transit_block = ("\n".join(f"- {t}" for t in transits)
                     if transits else "- No relevant transit data available today.")

    # Temporal lens per slot (spec Section 12: Morning Outlook / Midday Status / Evening Review).
    lens = {
        "overnight": "EVENING REVIEW lens: assess how the day's recovery actually resolved overnight.",
        "morning": "MORNING OUTLOOK lens: identify likely stress/recovery themes before training.",
        "midday": "MIDDAY STATUS lens: compare the morning's expected themes against observed metrics.",
        "afternoon": "MIDDAY STATUS lens: compare expected themes against observed metrics.",
        "evening": "EVENING REVIEW lens: assess what the actual correlations turned out to be.",
    }.get(slot, "MORNING OUTLOOK lens.")

    prompt = (
        "You are a recovery and performance coach writing a short daily read for an athlete (Alfie). "
        "He knows his own body and his own birth chart well. He does NOT want technical jargon — not "
        "biometric labels, not astrology terminology. Write like a sharp human coach talking to him "
        "in plain English.\n\n"
        "HARD OUTPUT RULES (these are absolute):\n"
        "- NEVER write raw numbers, percentages, or units. No \"72ms\", no \"5/6\", no \"6.1h\", no \"%\".\n"
        "- NEVER write biometric jargon: HRV, Recharge, Nightly Recharge, BPM, ANS, Sleep Score.\n"
        "- NEVER write astrology jargon: no \"Moon-in-Capricorn\", no \"Uranus-Moon\", no \"Saturn square\", "
        "no aspect names (square / trine / conjunct / opposition / sextile) unless translated into plain "
        "words, no \"natal\", \"Placidus\", or \"transit chart\". The everyday words chart, transit, moon, "
        "and mars are fine when used conversationally and lowercase.\n"
        "- The data below INFORMS your assessment. It must NOT appear in the output. Translate everything "
        "into plain language. The data sets the conclusion; the conclusion is what you write.\n\n"
        "HIERARCHY — measured recovery/fitness data is the source of truth. Natal context and transits are "
        "background for body-area awareness and pattern recognition only; they NEVER override the data. "
        "If a chart theme conflicts with the data, the data wins.\n\n"
        f"{lens}\n\n"
        "=== RECOVERY & FITNESS DATA (informs you — never quote it) ===\n"
        "(Polar Nightly Recharge is a 1-6 scale, 6 best.)\n"
        f"- Recovery status today: {rec_today}/6 (7-day avg {rec_7d})\n"
        f"- Heart-rate variability today: {hrv_today} ms (7-day avg {hrv_7d})\n"
        f"- Sleep last night: {slp_hours} hours (7-day avg {slp_7d})\n"
        f"- Body composition: {body}\n"
        f"{nutrition_bullet}"
        "\n=== NATAL CONTEXT (static, body-area awareness only) ===\n"
        f"{NATAL_ARCHITECTURE}\n"
        "\n=== TODAY'S RELEVANT TRANSITS (context only) ===\n"
        f"{transit_block}\n\n"
        "Produce EXACTLY these five sections, each starting on its own line with the exact label shown "
        "followed by a colon. No markdown, no bullets, no preamble, no closing remarks.\n\n"
        "Recovery: ONE word only — Poor, Average, Good, or Excellent. Nothing else on this line.\n"
        "Physical Themes: one or two short sentences about any body areas that deserve attention today "
        "(joints, tendons, shoulders, neck, lower body). If nothing is flagged, say so plainly. "
        "Example: \"Nothing currently suggests increased stress on joints, tendons, shoulders, or neck.\"\n"
        "Astrology Correlation: translate today's chart themes into plain English about how he tends to "
        "recover and perform, and whether today's data fits that pattern. "
        "Example: \"You generally recover best through consistency, structure, and routine, and today's "
        "data supports that pattern.\"\n"
        "Performance Outlook: start with EXACTLY one of these verdicts — Push hard / Train normally / "
        "Moderate effort / Prioritize recovery — then one short sentence of why. "
        "Example: \"Push hard. Recovery is excellent and training should be above average — push if "
        "technique stays solid.\"\n"
        "Transit Impact: only if a meaningful planetary transit is actually affecting today; plain "
        "English, one short sentence (e.g. \"Mars is amplifying your drive — channel it into work, not "
        "friction.\"). If nothing meaningful is hitting today, write exactly: none\n"
    )

    log(f"slot={slot} recharge={rec_today} hrv={hrv_today} sleep={slp_hours} transits={len(transits)}")
    raw = call_claude(prompt)
    sections = parse_sections(raw)
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
    ti = simple.get("transit_impact")
    if not transits or not ti or ti.strip().lower() == "none" \
            or re.search(r"\bno (significant|relevant|meaningful)\b", ti, re.I):
        simple["transit_impact"] = None

    payload = {
        "generated_at": now.replace(microsecond=0).isoformat(),
        "slot": slot,
        "summary": summary,
        "sections": sections,
        "simple": simple,
        "transits": transits,
        "data_basis": {
            "recharge_today": rec_today,
            "sleep_hours": slp_hours,
            "hrv_today": hrv_today,
            "hrv_7d_avg": hrv_7d,
            "nutrition": nutrition,
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
