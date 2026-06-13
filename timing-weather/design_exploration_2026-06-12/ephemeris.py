#!/usr/bin/env python3
"""
Three-Lens dashboard — accurate ephemeris + derived intelligence (Swiss Ephemeris).

Writes ephemeris.json with REAL geocentric tropical positions, transit-to-natal
aspects, moon phase, AND the previously-hard-coded bits now COMPUTED so they never
go stale: annual profection (+ phase label), today's sky (notable applying
transits), moon void-of-course, and an upcoming-events forecast.

Does NOT touch the live engine.py / state.json. Natal: Alfredo Vargas —
1990-08-30 16:22 CDT (21:22 UTC), Chicago 41.85N 87.65W.
"""
import json, math
from datetime import datetime, date, timezone, timedelta
import swisseph as swe

BIRTH_UTC = (1990, 8, 30, 21 + 22/60)
LAT, LON = 41.85, -87.65
BODIES = [("Sun",swe.SUN),("Moon",swe.MOON),("Mercury",swe.MERCURY),("Venus",swe.VENUS),
          ("Mars",swe.MARS),("Jupiter",swe.JUPITER),("Saturn",swe.SATURN),
          ("Uranus",swe.URANUS),("Neptune",swe.NEPTUNE),("Pluto",swe.PLUTO),
          ("Node",swe.TRUE_NODE)]
SIGN = ['Ari','Tau','Gem','Can','Leo','Vir','Lib','Sco','Sag','Cap','Aqu','Pis']
SIGN_FULL = ['Aries','Taurus','Gemini','Cancer','Leo','Virgo','Libra','Scorpio',
             'Sagittarius','Capricorn','Aquarius','Pisces']
RULERS = ['Mars','Venus','Mercury','Moon','Sun','Mercury','Venus','Mars','Jupiter','Saturn','Saturn','Jupiter']
THEME  = ['Embodiment','Resources','Connection','Foundations','Creation','Refinement',
          'Partnership','Depth','Expansion','Visibility','Community','Preparation']  # house 1..12
NATAL_DOMAIN = {'Sun':'identity','Moon':'feelings','Mercury':'mind','Venus':'values & love',
    'Mars':'drive','Jupiter':'growth','Saturn':'structure','Uranus':'awakening',
    'Neptune':'imagination','Pluto':'power','Node':'direction','ASC':'presence','MC':'public path'}
TVERB = {'Sun':'lights up','Moon':'stirs','Mercury':'sparks thinking around','Venus':'sweetens',
    'Mars':'fires up','Jupiter':'expands','Saturn':'tests','Uranus':'jolts',
    'Neptune':'softens','Pluto':'intensifies','Node':'pulls'}
TONE = {'Conjunction':'a charged fusion','Square':'productive friction','Opposition':'a pull toward balance',
    'Trine':'easy flow','Sextile':'an open door'}

FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED
try:
    swe.calc_ut(swe.julday(2000,1,1,0), swe.SUN, FLAGS)
except Exception:
    FLAGS = swe.FLG_MOSEPH | swe.FLG_SPEED

def lonspeed(jd, body):
    r = swe.calc_ut(jd, body, FLAGS)[0]
    return r[0] % 360, r[3]

def fmt(lon):
    s = int(lon // 30) % 12
    return {"lon": round(lon, 3), "sign": SIGN[s], "deg": int(lon % 30)}

def positions(jd):
    out = []
    for name, body in BODIES:
        lon, sp = lonspeed(jd, body)
        d = fmt(lon); d["name"] = name; d["rx"] = sp < 0
        out.append(d)
    return out

def jd_of(dt):
    return swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute/60 + dt.second/3600)

def natal():
    jd = swe.julday(*BIRTH_UTC)
    trop = {n: round(lonspeed(jd, b)[0], 3) for n, b in BODIES}
    cusps, ascmc = swe.houses(jd, LAT, LON, b"P")
    trop["ASC"], trop["MC"] = round(ascmc[0], 3), round(ascmc[1], 3)
    return trop

ASPECTS = [("Conjunction","☌",0,5),("Opposition","☍",180,5),("Trine","△",120,4),
           ("Square","□",90,4),("Sextile","⚹",60,3)]

def transit_aspects(jd, natal_pos):
    trans = positions(jd)
    nxt = {n: lonspeed(jd + 0.5, b)[0] for n, b in BODIES}
    hits = []
    for tp in trans:
        for nk, nl in natal_pos.items():
            d = abs(tp["lon"] - nl) % 360
            if d > 180: d = 360 - d
            for name, sym, deg, orb in ASPECTS:
                o = abs(d - deg)
                if o <= orb:
                    d2 = abs(nxt[tp["name"]] - nl) % 360
                    if d2 > 180: d2 = 360 - d2
                    hits.append({"t": tp["name"], "rx": tp["rx"], "sym": sym, "aspect": name,
                                 "n": nk, "orb": round(o, 1), "applying": abs(d2 - deg) < o})
                    break
    hits.sort(key=lambda h: h["orb"])
    return hits

# ── derived intelligence ────────────────────────────────────────────────────
def profection(today):
    b = date(1990, 8, 30)
    age = today.year - b.year - ((today.month, today.day) < (b.month, b.day))
    house = age % 12 + 1
    asc_sign = 9  # natal ASC = Capricorn (whole-sign 1st)
    si = (asc_sign + house - 1) % 12
    nxt = date(today.year + (0 if (today.month, today.day) < (8, 30) else 1), 8, 30)
    nh = house % 12 + 1; nsi = (asc_sign + nh - 1) % 12
    def ordn(h): return f"{h}{'th' if 10<=h%100<=20 else {1:'st',2:'nd',3:'rd'}.get(h%10,'th')}"
    return {"age": age, "house": house, "houseOrd": ordn(house), "sign": SIGN_FULL[si],
            "lord": RULERS[si], "theme": THEME[house-1], "daysToTurn": (nxt-today).days,
            "nextSign": SIGN_FULL[nsi], "nextLord": RULERS[nsi], "nextHouseOrd": ordn(nh)}

def phase_block(prof):
    return {"label": prof["theme"].upper(),
            "subtitle": f"{prof['houseOrd']}-house {prof['sign']} year · lord {prof['lord']} · "
                        f"{prof['daysToTurn']} days to the {prof['nextSign']} turn"}

def moon_void(jd):
    """Geometric VOC: does the Moon make another major aspect (to the 7 classical bodies)
    before it leaves its current sign?"""
    mlon, mspd = lonspeed(jd, swe.MOON)
    classical = [swe.SUN, swe.MERCURY, swe.VENUS, swe.MARS, swe.JUPITER, swe.SATURN]
    sign_end = (math.floor(mlon/30)+1)*30
    dist_end = sign_end - mlon
    angles = [0,60,90,120,180,240,270,300]
    best, best_p = dist_end, None
    for body in classical:
        plon = lonspeed(jd, body)[0]
        for a in angles:
            fd = ((plon + a) - mlon) % 360
            if 0 < fd < best:
                best, best_p = fd, body
    void = best_p is None
    hours = (dist_end if void else best) / (mspd/24) if mspd else 0
    enter = jd + dist_end/(mspd/24) if mspd else jd
    y,m,d,h = swe.revjul(enter)
    return {"void": void, "sign": SIGN_FULL[int(mlon//30)%12],
            "entersNextHours": round(dist_end/(mspd/24),1) if mspd else None,
            "nextSign": SIGN_FULL[int(sign_end//30)%12]}

def next_lunation(jd, target):  # target 0=new, 180=full
    j = jd
    for _ in range(800):  # up to ~33 days in 1h steps
        s = lonspeed(j, swe.SUN)[0]; m = lonspeed(j, swe.MOON)[0]
        e = (m - s) % 360
        diff = (e - target) % 360
        if diff > 180: diff -= 360
        if -0.4 < diff < 0.4:
            y,mo,d,h = swe.revjul(j); return j
        j += 1/24
    return None

def jupiter_return(jd, natal_jup):
    j = jd
    prev = lonspeed(j, swe.JUPITER)[0]
    for _ in range(500):  # up to 500 days
        j += 1
        cur = lonspeed(j, swe.JUPITER)[0]
        # crossing of natal_jup (handle wrap)
        a = (prev - natal_jup) % 360; b = (cur - natal_jup) % 360
        if (a > 350 or a < 10) and (b > 350 or b < 10) and ((prev <= natal_jup <= cur) or (a > 180) != (b > 180)):
            # refine by sign change of (cur-natal) around 0
            pass
        if (prev - natal_jup) % 360 > 180 and (cur - natal_jup) % 360 < 180 and abs(((cur-natal_jup+180)%360)-180) < 5:
            return j
        prev = cur
    return None

def daily_sky(aspects):
    """Notable CURRENT transits for the Traditional 'Today's Sky' — applying ones to
    personal points, top 3, with generated prose."""
    personal = {'Sun','Moon','ASC','MC','Mercury','Venus','Mars'}
    rows = []
    for a in aspects:
        if a['n'] in personal or a['t'] in ('Moon','Sun','Mercury','Venus','Mars'):
            verb = TVERB.get(a['t'], 'touches'); dom = NATAL_DOMAIN.get(a['n'], a['n'])
            rows.append({"t": a['t'], "sym": a['sym'], "n": a['n'], "rx": a['rx'],
                         "aspect": a['aspect'], "orb": a['orb'], "applying": a['applying'],
                         "text": f"{verb} your {dom} — {TONE.get(a['aspect'],'an active contact')}."})
        if len(rows) >= 3: break
    return rows

def main():
    now = datetime.now(timezone.utc); today = now.date()
    jd = jd_of(now)
    trans = positions(jd)
    sun = next(p for p in trans if p["name"] == "Sun")
    moon = next(p for p in trans if p["name"] == "Moon")
    elong = (moon["lon"] - sun["lon"]) % 360
    illum = round((1 - math.cos(math.radians(elong))) / 2 * 100)
    if illum < 2: phase = "New Moon"
    elif elong < 90: phase = "Waxing crescent"
    elif elong < 100: phase = "First quarter"
    elif elong < 170: phase = "Waxing gibbous"
    elif elong < 190: phase = "Full Moon"
    elif elong < 260: phase = "Waning gibbous"
    elif elong < 280: phase = "Last quarter"
    else: phase = "Waning crescent"
    nat = natal()
    aspects = transit_aspects(jd, nat)
    prof = profection(today)

    # upcoming forecast
    fc = []
    nn = next_lunation(jd, 0); ff = next_lunation(jd, 180)
    if nn and ff:
        if nn < ff:
            y,m,d,h = swe.revjul(nn); fc.append({"label":"New Moon","days":round(nn-jd),"note":"fresh cycle"})
            y,m,d,h = swe.revjul(ff); fc.append({"label":"Full Moon","days":round(ff-jd),"note":"culmination"})
        else:
            y,m,d,h = swe.revjul(ff); fc.append({"label":"Full Moon","days":round(ff-jd),"note":"culmination"})
            y,m,d,h = swe.revjul(nn); fc.append({"label":"New Moon","days":round(nn-jd),"note":"fresh cycle"})
    jr = jupiter_return(jd, nat["Jupiter"])
    if jr: fc.append({"label":"Jupiter Return","days":round(jr-jd),"note":"12-yr renewal of the year-lord"})
    fc.append({"label": f"Profection → {prof['nextSign']}", "days": prof["daysToTurn"],
               "note": f"lord becomes {prof['nextLord']}"})
    fc.sort(key=lambda x: x["days"])

    # one-sentence cross-system synthesis for the hero (pinned across all lenses).
    # The interpretive frame keys off the profection theme; the markers are computed.
    jr_days = next((x["days"] for x in fc if x["label"] == "Jupiter Return"), None)
    jr_txt = f"the Jupiter return ({jr_days}d)" if jr_days is not None else "the Jupiter return"
    FRAME = {
        "Preparation": "build quietly and refine now, don't perform",
        "Embodiment":  "step into the new identity and own it",
        "Resources":   "consolidate what you have and grow it",
        "Connection":  "learn, network, and put ideas into words",
        "Foundations": "tend home, roots, and emotional ground",
        "Creation":    "make, play, and let yourself be seen",
        "Refinement":  "sharpen the craft and the daily systems",
        "Partnership": "meet others halfway and commit",
        "Depth":       "go deep, transform, and share resources",
        "Expansion":   "widen the world — travel, study, believe",
        "Visibility":  "step into view and lead",
        "Community":   "build with the group and aim past yourself",
    }
    frame = FRAME.get(prof["theme"], "move with the season")
    synthesis = frame[0].upper() + frame[1:] + "."

    data = {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "transits": trans,
        "moon": {"phase": phase, "illum": illum, "sign": moon["sign"], "waxing": elong < 180},
        "moonVoid": moon_void(jd),
        "transitAspects": aspects,
        "dailySky": daily_sky(aspects),
        "profection": prof,
        "phase": phase_block(prof),
        "synthesis": synthesis,
        "forecast": fc,
        "natalTropical": nat,
        "engine": f"Swiss Ephemeris {swe.version}",
    }
    with open("ephemeris.json", "w") as f:
        json.dump(data, f, indent=1)
    print("wrote ephemeris.json —", data["generated"])
    print("phase:", data["phase"]["label"], "| moon:", phase, f"{illum}%",
          "| void:", data["moonVoid"]["void"],
          "| forecast:", [(x["label"], x["days"]) for x in fc])

if __name__ == "__main__":
    main()
