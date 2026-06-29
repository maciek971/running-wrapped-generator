#!/usr/bin/env python3
"""Turn a runner's data into a ranked briefing of *distinctive* hooks + their own
run titles — so the author-LLM writes a personal story, not a templated report.

`build_briefing(runs, data, home)` returns a JSON-able dict:
  { "angle_guess": str, "insights": [ {id, score, note, **numbers} ... ],
    "events": [...], "notable_runs": [...] }
Everything is factual (computed from the data); the LLM phrases it.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta

from geo import haversine_km

# run-title patterns that usually mean a RACE / event — pure gold for the story.
# Deliberately narrow: generic words like "bieg"/"run"/"10k" are training, not races.
_EVENT_RE = re.compile(
    r"(maraton|marathon|p[oó][łl]maraton|half\s*marathon|parkrun|ultra|zawody|"
    r"wy[śs]cig|\brace\b|21[.,]1\s*km|42[.,]2\s*km|\bDOZ\b|\bPKO\b)", re.I)
_NOISE = {"bieg", "run", "running", "trening", "tempo", "easy", "long", "z2", "z3",
          "interwały", "rozbieganie", "recovery", "morning", "evening"}


def _clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def build_briefing(runs, data, home) -> dict:
    years = data.get("years", [])
    ins: list[dict] = []

    def add(id, score, note, **nums):
        ins.append({"id": id, "score": round(_clip(score), 2), "note": note, **nums})

    # --- year-trend shape ---------------------------------------------------
    if len(years) >= 2:
        first, last = years[0], years[-1]
        peak = max(years, key=lambda y: y["km"])
        kms = [y["km"] for y in years]
        rising = last["km"] >= 0.9 * peak["km"] and last["km"] > 1.4 * (kms[0] or 1)
        shape = ("rosnący" if rising else
                 "powrót" if (peak is not last and last["km"] > 1.3 * min(kms[-3:] or kms)) else
                 "stabilny" if max(kms) < 1.6 * (min(kms) or 1) else "zmienny")
        add("trend", 0.6 + 0.1 * rising,
            f"Kształt lat: {shape}. Start {first['year']}={first['km']} km, "
            f"szczyt {peak['year']}={peak['km']} km, ostatni {last['year']}={last['km']} km.",
            shape=shape, first_year=first["year"], first_km=first["km"],
            peak_year=peak["year"], peak_km=peak["km"], last_year=last["year"], last_km=last["km"])
        # biggest year-over-year jump
        jumps = [(years[i]["year"], years[i - 1]["km"], years[i]["km"],
                  (years[i]["km"] - years[i - 1]["km"]) / (years[i - 1]["km"] or 1))
                 for i in range(1, len(years))]
        yj = max(jumps, key=lambda t: t[3])
        if yj[3] > 0.4:
            add("jump", _clip(yj[3]), f"Największy skok roku: {yj[0]} +{round(yj[3]*100)}% "
                f"({round(yj[1])}→{round(yj[2])} km).", year=yj[0], pct=round(yj[3]*100),
                from_km=round(yj[1]), to_km=round(yj[2]))

    # --- streaks & comeback gaps (calendar days with a run) -----------------
    days = sorted({r.start_time.date() for r in runs})
    if days:
        # longest streak of consecutive days
        best = run_len = 1
        bstart = bend = days[0]
        cs = days[0]
        for i in range(1, len(days)):
            if (days[i] - days[i - 1]).days == 1:
                run_len += 1
            else:
                run_len = 1; cs = days[i]
            if run_len > best:
                best, bstart, bend = run_len, cs, days[i]
        if best >= 5:
            add("streak", _clip(best / 30), f"Najdłuższa seria: {best} dni z rzędu "
                f"({bstart}→{bend}).", days=best, start=str(bstart), end=str(bend))
        # longest break, and whether they came back bigger
        gaps = [((days[i] - days[i - 1]).days, days[i - 1], days[i]) for i in range(1, len(days))]
        gmax = max(gaps, key=lambda g: g[0])
        if gmax[0] >= 30:
            before = sum(r.distance_km for r in runs if gmax[1] - timedelta(90) <= r.start_time.date() <= gmax[1])
            after = sum(r.distance_km for r in runs if gmax[2] <= r.start_time.date() <= gmax[2] + timedelta(90))
            add("comeback", _clip(gmax[0] / 120 + (0.3 if after > before else 0)),
                f"Najdłuższa przerwa: {gmax[0]} dni ({gmax[1]}→{gmax[2]}); "
                f"90 dni przed={round(before)} km, po={round(after)} km"
                f"{' — wrócił(a) mocniej' if after > before else ''}.",
                gap_days=gmax[0], ended=str(gmax[2]), km_before=round(before), km_after=round(after))

    # --- when do they run ---------------------------------------------------
    hours = data.get("hours", [])
    tot_h = sum(h["runs"] for h in hours) or 1
    early = sum(h["runs"] for h in hours if 4 <= h["h"] <= 8) / tot_h
    evening = sum(h["runs"] for h in hours if 17 <= h["h"] <= 22) / tot_h
    if early >= 0.5:
        peak_h = max(hours, key=lambda h: h["runs"])["h"]
        add("early_bird", _clip(early), f"Ranny ptaszek: {round(early*100)}% biegów 4–8 rano "
            f"(szczyt {peak_h}:00).", share=round(early*100), peak_hour=peak_h)
    elif evening >= 0.5:
        add("night_owl", _clip(evening), f"Wieczorny biegacz: {round(evening*100)}% biegów 17–22.",
            share=round(evening*100))
    wd = data.get("weekday", [])
    we = sum(d["runs"] for d in wd[5:]); wk = sum(d["runs"] for d in wd[:5])
    if we and wk and we / (we + wk) > 0.45:
        add("weekend", 0.5, f"Weekendowiec: {round(100*we/(we+wk))}% biegów w sob/nd.",
            share=round(100*we/(we+wk)))

    # --- training intensity (latest year) -----------------------------------
    zby = data.get("zones_by_year", [])
    if zby:
        z = zby[-1].get("pct", {})
        easy = (z.get("Z1", 0) + z.get("Z2", 0)); hard = (z.get("Z4", 0) + z.get("Z5", 0))
        if easy >= 55:
            add("polarised", _clip(easy / 100 + 0.2), f"Trening spokojny: {easy}% czasu w Z1+Z2 "
                f"(tylko {hard}% w Z4+Z5) w {zby[-1]['year']}.", easy_pct=easy, hard_pct=hard)
        elif hard >= 35:
            add("hard", _clip(hard / 100 + 0.2), f"Trening mocny: aż {hard}% w Z4+Z5 w {zby[-1]['year']}.",
                hard_pct=hard, easy_pct=easy)

    # --- travel / geography -------------------------------------------------
    countries = data.get("scale", {}).get("countries", [])
    foreign = [c for c in countries if c["name"] != data.get("geo", {}).get("country")]
    places = (data.get("poland") or {}).get("places", [])
    if home:
        far = max((r for r in runs if r.start), key=lambda r: haversine_km(r.start, (home["lat"], home["lon"])), default=None)
        if far:
            d = round(haversine_km(far.start, (home["lat"], home["lon"])))
            add("farthest", _clip(d / 1500), f"Najdalszy bieg od domu: {d} km — „{(far.name or '?').strip()}” "
                f"({far.start_time:%Y-%m-%d}).", km=d, name=(far.name or "").strip(), date=str(far.start_time.date()))
    if foreign:
        add("abroad", _clip(0.4 + 0.15 * len(foreign)), f"Biegał(a) w {len(foreign)} krajach poza domem: "
            f"{', '.join(c['name'] for c in foreign)}.", countries=[c["name"] for c in foreign])
    if len(places) >= 4:
        add("explorer", 0.5, f"{len(places)} różnych okolic w kraju poza domem.", places=len(places))

    # --- records ------------------------------------------------------------
    rec = data.get("records", {})
    lg = rec.get("longest") or {}
    if lg:
        add("longest", 0.7, f"Najdłuższy bieg: {lg.get('km')} km — „{(lg.get('name') or '').strip()}” "
            f"({lg.get('date')}).", km=lg.get("km"), name=(lg.get("name") or "").strip(), date=lg.get("date"))
    for d in rec.get("race", []):
        msg = f"Rekord {d['label']}: {d['time']} ({d['pace']}/km)."
        pred = d.get("pred")
        if pred:
            how = "szybciej" if pred.get("faster") else "wolniej"
            msg += f" Garmin szacuje dziś {pred['time']} ({pred['delta']} {how} niż rekord)."
        add("pr_" + d["key"], 0.45, msg, label=d["label"], time=d["time"], pace=d["pace"], pred=pred)
    mar = rec.get("marathon")
    if mar:
        add("marathon_pred", 0.4,
            f"Garmin przewiduje, że na maraton stać Cię dziś na ~{mar['time']} — a nie masz jeszcze rekordu na tym dystansie.",
            time=mar["time"])

    # --- events from run titles (very personal) -----------------------------
    events = []
    for r in runs:
        nm = (r.name or "").strip()
        if nm and _EVENT_RE.search(nm) and nm.lower() not in _NOISE:
            events.append({"date": str(r.start_time.date()), "name": nm, "km": round(r.distance_km, 1)})
    events.sort(key=lambda e: e["date"])
    if events:
        add("events", _clip(0.5 + 0.1 * len(events)), f"{len(events)} biegów wyglądających na zawody/wydarzenia "
            f"(z nazw) — np. „{events[-1]['name']}”.", count=len(events))

    # --- notable runs (real titles for the LLM to quote) --------------------
    notable = {}

    def note_run(r, why):
        if not r:
            return
        notable[id(r)] = {"date": str(r.start_time.date()), "name": (r.name or "").strip(),
                          "km": round(r.distance_km, 1), "why": why}
    note_run(max(runs, key=lambda r: r.distance_km or 0), "longest")
    note_run(min(runs, key=lambda r: r.start_time), "first ever")
    note_run(max(runs, key=lambda r: r.start_time), "most recent")
    # a few longest, most-descriptive titles (have words beyond a place/noise token),
    # deduped by title text so repeated plan labels don't crowd it out
    seen_titles, worded = set(), []
    for r in sorted((r for r in runs if r.name and len(r.name.split()) >= 3
                     and r.name.split()[0].lower() not in _NOISE),
                    key=lambda r: len(r.name), reverse=True):
        key = " ".join(r.name.lower().split())
        if key in seen_titles:
            continue
        seen_titles.add(key)
        worded.append(r)
        if len(worded) >= 6:
            break
    for r in worded:
        note_run(r, "descriptive title")

    ins.sort(key=lambda x: -x["score"])
    angle = ins[0]["note"] if ins else "Steady runner."
    return {"angle_guess": angle, "insights": ins, "events": events,
            "notable_runs": list(notable.values())}
