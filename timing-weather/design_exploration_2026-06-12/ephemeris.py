#!/usr/bin/env python3
"""
Three-Lens dashboard — accurate ephemeris generator (Swiss Ephemeris).

Writes ephemeris.json next to three-lens-dashboard.html with REAL current
geocentric tropical positions for all planets + transit-to-natal aspects +
moon phase. The page fetches this and renders it; if the fetch fails it falls
back to the in-page Schlyter approximation (Sun/Moon only).

This does NOT touch the live engine.py / index.html / state.json. Run it on a
schedule (e.g. the existing deploy-watch / a launchd job) to keep it current.

Natal: Alfredo Vargas — 1990-08-30 16:22 CDT (21:22 UTC), Chicago 41.85N 87.65W.
"""
import json, sys
from datetime import datetime, timezone
import swisseph as swe

BIRTH_UTC = (1990, 8, 30, 21 + 22/60)          # 16:22 CDT = 21:22 UTC
LAT, LON = 41.85, -87.65
BODIES = [("Sun",swe.SUN),("Moon",swe.MOON),("Mercury",swe.MERCURY),("Venus",swe.VENUS),
          ("Mars",swe.MARS),("Jupiter",swe.JUPITER),("Saturn",swe.SATURN),
          ("Uranus",swe.URANUS),("Neptune",swe.NEPTUNE),("Pluto",swe.PLUTO),
          ("Node",swe.TRUE_NODE)]
SIGN = ['Ari','Tau','Gem','Can','Leo','Vir','Lib','Sco','Sag','Cap','Aqu','Pis']
FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED
try:                                            # fall back to built-in Moshier if no data files
    swe.calc_ut(swe.julday(2000,1,1,0), swe.SUN, FLAGS)
except Exception:
    FLAGS = swe.FLG_MOSEPH | swe.FLG_SPEED

def lonspeed(jd, body):
    res = swe.calc_ut(jd, body, FLAGS)[0]
    return res[0] % 360, res[3]                 # longitude, lon-speed (deg/day)

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
    nxt = {n: lonspeed(jd + 0.5, b)[0] for n, b in BODIES}   # for applying/separating
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
                    applying = abs(d2 - deg) < o
                    hits.append({"t": tp["name"], "rx": tp["rx"], "sym": sym, "aspect": name,
                                 "n": nk, "orb": round(o, 1), "applying": applying})
                    break
    hits.sort(key=lambda h: h["orb"])
    return hits

def main():
    now = datetime.now(timezone.utc)
    jd = swe.julday(now.year, now.month, now.day, now.hour + now.minute/60 + now.second/3600)
    trans = positions(jd)
    sun = next(p for p in trans if p["name"] == "Sun")
    moon = next(p for p in trans if p["name"] == "Moon")
    elong = (moon["lon"] - sun["lon"]) % 360
    import math
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
    data = {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "transits": trans,
        "moon": {"phase": phase, "illum": illum, "sign": moon["sign"], "waxing": elong < 180},
        "transitAspects": transit_aspects(jd, nat),
        "natalTropical": nat,
        "engine": f"Swiss Ephemeris {swe.version}",
    }
    with open("ephemeris.json", "w") as f:
        json.dump(data, f, indent=1)
    print("wrote ephemeris.json —", data["generated"])
    print("Sun", sun["deg"], sun["sign"], "| Moon", moon["deg"], moon["sign"],
          phase, f"{illum}%", "| Pluto",
          next(p for p in trans if p["name"]=="Pluto")["deg"],
          next(p for p in trans if p["name"]=="Pluto")["sign"])

if __name__ == "__main__":
    main()
