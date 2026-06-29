#!/usr/bin/env python3
"""Build a personal "Running Wrapped" page from a Garmin FIT cache — for anyone.

No hardcoded city/country: home and country are auto-detected from the GPS data.
Reads ./me.json (birth_year, optional name/home_city/resting_hr), the FIT cache,
and template.html; writes data.json and a self-contained index.html.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from statistics import median

from geo import World, haversine_km
from lib_fit import load_runs
from lib_merge import merge_runs
from lib_strava import load_strava

HERE = Path(__file__).resolve().parent
ZONES = ["Z1", "Z2", "Z3", "Z4", "Z5"]
HOME_R = 18.0          # km — runs starting within this of the home centre are "home"
AWAY_LINK = 12.0       # km — away runs within this of a cluster seed merge into one pin

_PLACE_PREFIX = {"nowa", "nowy", "nowe", "stara", "stary", "stare", "biała", "biały",
                 "wielka", "wielki", "mała", "mały", "dolna", "dolny", "górna", "górny"}
_STOP = {"tempo", "interwały", "interwaly", "bieg", "trening", "rozbieganie", "long",
         "easy", "recovery", "rozgrzewka", "spacer", "marszobieg", "run", "morning", "evening"}


def fmt_pace(sec_per_km):
    if not sec_per_km:
        return None
    return f"{int(sec_per_km // 60)}:{int(round(sec_per_km % 60)):02d}"


def iso_week(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def place_token(name):
    toks = (name or "").split()
    if not toks or not toks[0][:1].isalpha():
        return None
    if toks[0].lower() in _PLACE_PREFIX and len(toks) > 1 and toks[1][:1].isupper():
        return f"{toks[0]} {toks[1]}"
    return toks[0]


def flag_emoji(iso2: str) -> str:
    iso2 = (iso2 or "").upper()
    if len(iso2) != 2 or not iso2.isalpha():
        return "🌍"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2)


# ---------- HR zones (Karvonen from age + resting HR) ----------
def zone_bounds(max_hr: float, rest_hr: float):
    hrr = max(1.0, max_hr - rest_hr)
    return [rest_hr + p * hrr for p in (0.60, 0.70, 0.80, 0.90)]  # 4 thresholds -> 5 zones


def zone_seconds(run, bounds):
    out = {z: 0.0 for z in ZONES}
    hrs = run.hr_samples
    if not hrs or not run.duration_s:
        return out
    counts = [0] * 5
    for hr in hrs:
        k = 4
        for i, b in enumerate(bounds):
            if hr < b:
                k = i
                break
        counts[k] += 1
    per = run.duration_s / len(hrs)
    return {ZONES[i]: counts[i] * per for i in range(5)}


# ---------- home detection ----------
def detect_home(runs):
    """Densest cluster of start points -> (lat, lon, count, member_runs)."""
    pts = [(r, r.start) for r in runs if r.start]
    if not pts:
        return None
    best = None
    for r0, s0 in pts:
        members = [r for r, s in pts if haversine_km(s0, s) < HOME_R]
        if best is None or len(members) > best[1]:
            best = (s0, len(members), members)
    seed, _, members = best
    lat = median(r.start[0] for r in members)
    lon = median(r.start[1] for r in members)
    return lat, lon, members


# ---------- country-map (home country outline + away pins) ----------
def build_country_map(runs, world, home, home_country):
    lat0, lon0 = home["lat"], home["lon"]
    ring = world.outline(home_country) or []
    if not ring:
        return None
    k = cos(radians(sum(p[1] for p in ring) / len(ring)))
    xs = [p[0] * k for p in ring]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(p[1] for p in ring), max(p[1] for p in ring)
    W, PAD = 1000, 56
    s = (W - 2 * PAD) / (maxx - minx)
    H = round((maxy - miny) * s + 2 * PAD)

    def proj(lon, lat):
        return round(PAD + (lon * k - minx) * s, 1), round(PAD + (maxy - lat) * s, 1)

    outline = "M" + " L".join(f"{x},{y}" for x, y in (proj(lo, la) for lo, la in ring)) + "Z"
    hx, hy = proj(lon0, lat0)

    # away places inside the home country, by name, clustered by location
    by_name = defaultdict(list)
    for r in runs:
        if not r.start:
            continue
        if haversine_km(r.start, (lat0, lon0)) < HOME_R:
            continue
        loc = world.locate(*r.start)
        if not loc or loc[0] != home_country:
            continue
        tok = place_token(r.name)
        if tok and len(tok) >= 3 and tok[0].isalpha() and not any(c.isdigit() for c in tok) \
                and tok.lower() not in _STOP:
            by_name[tok].append(r.start)
    cand = [{"name": n, "count": len(v),
             "lat": median(p[0] for p in v), "lon": median(p[1] for p in v)}
            for n, v in by_name.items()]
    cand.sort(key=lambda c: -c["count"])
    clusters = []
    for c in cand:
        for cl in clusters:
            if haversine_km((c["lat"], c["lon"]), (cl["lat"], cl["lon"])) < AWAY_LINK:
                cl["count"] += c["count"]
                cl["names"].append(c["name"])
                break
        else:
            clusters.append({"lat": c["lat"], "lon": c["lon"], "count": c["count"], "names": [c["name"]]})
    places = []
    for cl in clusters:
        x, y = proj(cl["lon"], cl["lat"])
        places.append({"name": cl["names"][0], "names": cl["names"], "count": cl["count"], "x": x, "y": y})
    places.sort(key=lambda p: -p["count"])
    return {"w": W, "h": H, "outline": outline,
            "home": {"count": home["count"], "x": hx, "y": hy},
            "places": places, "other_runs": sum(p["count"] for p in places)}


def latlon_tracks(rs, step):
    out = []
    for r in rs:
        t = r.track[::step] if r.track else []
        if len(t) >= 2:
            out.append([[round(a, 5), round(b, 5)] for a, b in t])
    return out


def build_maps(runs, home, home_city):
    lat0, lon0 = home["lat"], home["lon"]
    near = [r for r in runs if r.start and haversine_km(r.start, (lat0, lon0)) < HOME_R]
    longest = max(runs, key=lambda r: r.distance_km or 0)
    maps = []
    recent = sorted(near, key=lambda r: r.start_time, reverse=True)[:120]
    if longest in near and longest not in recent:
        recent.append(longest)
    tr = latlon_tracks(recent, 7)
    if tr:
        maps.append({"id": "home", "title": f"{home_city} — Twój teren",
                     "subtitle": f"{len(near)} biegów w sercu miasta", "tracks": tr})
    tr = latlon_tracks([longest], 3)
    if tr:
        maps.append({"id": "longest", "title": "Najdłuższy bieg",
                     "subtitle": f"{round(longest.distance_km, 1)} km · {longest.start_time:%Y-%m-%d}",
                     "tracks": tr})
    away = [r for r in runs if r.start and haversine_km(r.start, (lat0, lon0)) >= HOME_R]
    clusters = []
    for r in sorted(away, key=lambda r: -(r.distance_km or 0)):
        for cl in clusters:
            if haversine_km(r.start, (cl["lat"], cl["lon"])) < AWAY_LINK:
                cl["runs"].append(r)
                tok = place_token(r.name)
                if tok:
                    cl["names"][tok] = cl["names"].get(tok, 0) + 1
                break
        else:
            tok = place_token(r.name)
            clusters.append({"lat": r.start[0], "lon": r.start[1], "runs": [r],
                             "names": {tok: 1} if tok else {}})
    clusters.sort(key=lambda c: -len(c["runs"]))
    for cl in clusters:
        if len(cl["runs"]) < 2:
            continue
        names = [n for n, _ in sorted(cl["names"].items(), key=lambda kv: -kv[1])][:2]
        pre = "🌴 " if cl["lon"] < 0 else ("🌊 " if cl["lat"] > 53.9 else "📍 ")
        rs = sorted(cl["runs"], key=lambda r: r.distance_km or 0, reverse=True)[:14]
        tr = latlon_tracks(rs, 9)
        if tr:
            maps.append({"id": names[0] if names else "away",
                         "title": pre + (" · ".join(names) if names else "Wyjazd"),
                         "subtitle": f"{len(cl['runs'])} biegów na wyjeździe", "tracks": tr})
        if len(maps) >= 9:
            break
    return maps


def gc(a, b):
    la1, lo1, la2, lo2 = map(radians, [a[0], a[1], b[0], b[1]])
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(h))


def main():
    cfg = json.loads((HERE / "me.json").read_text()) if (HERE / "me.json").exists() else {}
    cache = Path(cfg.get("cache_dir") or (HERE / "cache"))
    birth_year = int(cfg.get("birth_year") or 1990)
    rest_hr = float(cfg.get("resting_hr") or 48)

    garmin_runs = load_runs(cache)
    strava_runs = load_strava(cache)
    runs = merge_runs(garmin_runs, strava_runs)
    if not runs:
        sys.exit("No running activities found. Run fetch_garmin.py and/or ingest "
                 "Strava via the MCP (see CLAUDE.md).")
    dups = len(garmin_runs) + len(strava_runs) - len(runs)
    print(f"  · sources: {len(garmin_runs)} Garmin + {len(strava_runs)} Strava, "
          f"{dups} dups → {len(runs)} runs")
    world = World(lang=cfg.get("lang", "pl"))

    # home + country
    lat0, lon0, members = detect_home(runs)
    home_country, home_iso = (world.locate(lat0, lon0) or ("?", ""))
    tokens = Counter(t for r in members if (t := place_token(r.name)) and len(t) >= 3
                     and t.lower() not in _STOP and not any(c.isdigit() for c in t))
    home_city = cfg.get("home_city") or (tokens.most_common(1)[0][0] if tokens else home_country)
    home = {"lat": lat0, "lon": lon0, "count": len(members)}

    # HR zone bounds from observed max (p99) + resting
    all_hr = sorted(h for r in runs for h in r.hr_samples)
    obs_max = all_hr[int(len(all_hr) * 0.99)] if all_hr else 0
    max_hr = max(obs_max, 220 - (date.today().year - birth_year))
    bounds = zone_bounds(max_hr, rest_hr)

    by_year = defaultdict(lambda: {"runs": 0, "km": 0.0, "sec": 0.0, "hr_sec": 0.0,
                                   "hr_wsum": 0.0, "longest": 0.0, "days": set()})
    by_month = defaultdict(lambda: {"km": 0.0, "runs": 0})
    by_week = defaultdict(float)
    zby = defaultdict(lambda: {z: 0.0 for z in ZONES})
    weekday = [{"d": d, "runs": 0, "km": 0.0} for d in ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Nie"]]
    hours = [{"h": h, "runs": 0} for h in range(24)]
    countries_c = Counter()
    total_km = total_sec = ascent = 0.0

    for r in runs:
        y = r.start_time.year
        km = r.distance_km or 0.0
        sec = r.duration_s or 0.0
        total_km += km
        total_sec += sec
        ascent += r.ascent_m
        d = by_year[y]
        d["runs"] += 1; d["km"] += km; d["sec"] += sec
        d["longest"] = max(d["longest"], km); d["days"].add(r.start_time.date())
        if r.avg_hr:
            d["hr_sec"] += sec; d["hr_wsum"] += r.avg_hr * sec
        ym = r.start_time.strftime("%Y-%m")
        by_month[ym]["km"] += km; by_month[ym]["runs"] += 1
        by_week[iso_week(r.start_time.date())] += km
        zs = zone_seconds(r, bounds)
        for z in ZONES:
            zby[y][z] += zs[z]
        local = r.start_time + timedelta(hours=r.local_offset_h)
        weekday[local.weekday()]["runs"] += 1
        weekday[local.weekday()]["km"] += km
        hours[local.hour]["runs"] += 1
        if r.start:
            loc = world.locate(*r.start)
            if loc:
                countries_c[loc] += 1

    years = []
    for y in sorted(by_year):
        d = by_year[y]
        pace = d["sec"] / d["km"] if d["km"] else None
        avg_hr = d["hr_wsum"] / d["hr_sec"] if d["hr_sec"] else None
        years.append({"year": y, "runs": d["runs"], "km": round(d["km"], 1),
                      "hours": round(d["sec"] / 3600, 1), "pace_s": round(pace, 1) if pace else None,
                      "pace": fmt_pace(pace), "avg_hr": round(avg_hr) if avg_hr else None,
                      "longest": round(d["longest"], 1), "active_days": len(d["days"])})
    months = [{"ym": k, "km": round(v["km"], 1), "runs": v["runs"]} for k, v in sorted(by_month.items())]
    zones_by_year = []
    for y in sorted(zby):
        z = zby[y]; tot = sum(z.values()) or 1
        zones_by_year.append({"year": y, **{k: round(z[k] / 3600, 1) for k in ZONES},
                              "pct": {k: round(100 * z[k] / tot) for k in ZONES}})
    for w in weekday:
        w["km"] = round(w["km"])

    # distance histogram
    buckets = [(0, 3, "<3"), (3, 5, "3–5"), (5, 7, "5–7"), (7, 10, "7–10"), (10, 15, "10–15"), (15, 99, "15+")]
    dist_hist = [{"label": lbl, "runs": 0} for *_, lbl in buckets]
    for r in runs:
        for i, (lo, hi, _) in enumerate(buckets):
            if lo <= r.distance_km < hi:
                dist_hist[i]["runs"] += 1
                break

    def best_at(lo, hi):
        cand = [r for r in runs if lo <= r.distance_km <= hi and r.duration_s]
        if not cand:
            return None
        b = min(cand, key=lambda r: r.duration_s)
        return {"time": f"{int(b.duration_s // 60)}:{int(b.duration_s % 60):02d}",
                "pace": fmt_pace(b.duration_s / b.distance_km), "date": b.start_time.strftime("%Y-%m-%d")}

    # moon + zodiac (date only)
    SYN = 29.530588853
    REF = date(2000, 1, 6).toordinal()
    MOON = ["🌑 Nów", "🌓 Przybywający", "🌕 Pełnia", "🌗 Ubywający"]
    moon = {m: {"runs": 0, "psum": 0.0, "pn": 0} for m in MOON}
    ZS = [(120, "♑ Koziorożec"), (218, "♒ Wodnik"), (320, "♓ Ryby"), (419, "♈ Baran"),
          (520, "♉ Byk"), (620, "♊ Bliźnięta"), (722, "♋ Rak"), (822, "♌ Lew"),
          (922, "♍ Panna"), (1022, "♎ Waga"), (1121, "♏ Skorpion"), (1221, "♐ Strzelec")]
    zodiac = {s: {"runs": 0, "km": 0.0, "psum": 0.0, "pn": 0} for _, s in ZS}

    def moon_phase(d):
        f = ((d.toordinal() - REF) % SYN) / SYN
        return MOON[min(range(4), key=lambda i: min(abs(f - i * .25), 1 - abs(f - i * .25)))]

    def zsign(d):
        key = d.month * 100 + d.day
        for c, n in ZS:
            if key <= c:
                return n
        return ZS[0][1]

    for r in runs:
        dd = r.start_time.date()
        pace = (r.duration_s / r.distance_km) if (r.duration_s and r.distance_km) else None
        mp = moon[moon_phase(dd)]; mp["runs"] += 1
        if pace:
            mp["psum"] += pace; mp["pn"] += 1
        zz = zodiac[zsign(dd)]; zz["runs"] += 1; zz["km"] += r.distance_km
        if pace:
            zz["psum"] += pace; zz["pn"] += 1
    moon_list = [{"phase": m, "runs": v["runs"], "pace": fmt_pace(v["psum"] / v["pn"]) if v["pn"] else None,
                  "pace_s": (v["psum"] / v["pn"]) if v["pn"] else None} for m, v in moon.items()]
    zodiac_list = [{"sign": s, "runs": v["runs"], "km": round(v["km"]),
                    "pace": fmt_pace(v["psum"] / v["pn"]) if v["pn"] else None,
                    "pace_s": (v["psum"] / v["pn"]) if v["pn"] else None}
                   for s, v in zodiac.items() if v["runs"] > 0]
    srt = [z for z in zodiac_list if z["pace_s"] and z["runs"] >= 5]
    strongest = min(srt, key=lambda z: z["pace_s"])["sign"] if srt else None
    fav_moon = max(moon_list, key=lambda m: m["runs"])["phase"]

    longest = max(runs, key=lambda r: r.distance_km)
    best_month = max(by_month, key=lambda k: by_month[k]["km"])
    peak_week = max(by_week, key=lambda k: by_week[k])
    biggest_year = max(years, key=lambda y: y["km"])
    fastest_year = min((y for y in years if y["pace_s"]), key=lambda y: y["pace_s"])

    region_counter = Counter(t for r in runs if (t := place_token(r.name)))
    regions = [{"name": n, "runs": c} for n, c in region_counter.most_common(8)]

    # scale: ascent vs peaks, distance vs a journey from home
    peaks = [("Śnieżka", 1603), ("Rysy", 2499), ("Mont Blanc", 4809), ("Mount Everest", 8849)]
    cities = {"Paryż": (48.85, 2.35), "Lizbona": (38.72, -9.14), "Rzym": (41.90, 12.50),
              "Reykjavik": (64.13, -21.90), "Stambuł": (41.01, 28.98), "Madryt": (40.42, -3.70),
              "Ateny": (37.98, 23.73), "Londyn": (51.51, -0.13), "Berlin": (52.52, 13.40)}
    dists = sorted(({"city": c, "km": round(gc((lat0, lon0), xy))} for c, xy in cities.items()),
                   key=lambda d: d["km"])
    closest = min(dists, key=lambda d: abs(d["km"] - total_km))
    scale = {"ascent_m": round(ascent),
             "peaks": [{"name": n, "h": h, "x": round(ascent / h, 1)} for n, h in peaks],
             "distance": {"closest": closest, "cities": dists},
             "countries": [], "weekday": weekday, "hours": hours}

    countries = sorted(({"name": n, "flag": flag_emoji(i), "runs": c}
                        for (n, i), c in countries_c.items()), key=lambda x: -x["runs"])
    scale["countries"] = countries
    cmap = build_country_map(runs, world, home, home_country)

    data = {
        "lifetime": {"runs": len(runs), "km": round(total_km), "hours": round(total_sec / 3600),
                     "years": years[-1]["year"] - years[0]["year"] + 1 if years else 0,
                     "first": runs[0].start_time.strftime("%Y-%m-%d"),
                     "last": runs[-1].start_time.strftime("%Y-%m-%d"),
                     "cities": len(regions), "earth_pct": round(100 * total_km / 40075, 1)},
        "geo": {"home_city": home_city, "country": home_country, "country_flag": flag_emoji(home_iso)},
        "years": years, "months": months, "zones_by_year": zones_by_year,
        "zone_bounds": [round(b) for b in bounds],
        "records": {"longest": {"km": round(longest.distance_km, 2),
                                "date": longest.start_time.strftime("%Y-%m-%d"), "name": longest.name or "—"},
                    "best_month": {"ym": best_month, "km": round(by_month[best_month]["km"])},
                    "peak_week": {"week": peak_week, "km": round(by_week[peak_week], 1)},
                    "biggest_year": {"year": biggest_year["year"], "km": biggest_year["km"]},
                    "fastest_year": {"year": fastest_year["year"], "pace": fastest_year["pace"]},
                    "best_5k": best_at(4.8, 5.2), "best_10k": best_at(9.5, 10.5)},
        "regions": regions, "poland": cmap, "weekday": weekday, "hours": hours,
        "dist_hist": dist_hist, "moon": moon_list, "fav_moon": fav_moon,
        "zodiac": sorted(zodiac_list, key=lambda z: -z["runs"]), "strongest_sign": strongest,
        "maps": build_maps(runs, home, home_city), "scale": scale,
    }

    (HERE / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    _inline(data)
    print(f"✓ {data['lifetime']['runs']} runs · {data['lifetime']['km']} km · "
          f"home={home_city} ({home_country}) · countries={[c['name'] for c in countries]}")
    print(f"  pins={[ (p['name'],p['count']) for p in (cmap['places'] if cmap else []) ]}")


def _inline(data):
    compact = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    tpl = (HERE / "template.html").read_text(encoding="utf-8")
    lines = tpl.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("const DATA =")]
    assert len(idx) == 1, f"template needs exactly one `const DATA =` line ({len(idx)} found)"
    i = idx[0]
    indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
    lines[i] = f"{indent}const DATA = {compact};"
    (HERE / "index.html").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
