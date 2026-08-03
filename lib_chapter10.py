"""Builds the data for the esoteric chapter — and the evidence that undoes it.

Design rule for the whole chapter: never ship a bare group mean. Every number the
page draws comes with a standard error, because the chapter's entire argument is
that differences this small are indistinguishable from noise, and a chart that
stretches them to full width argues the opposite.

The hypothesis register at the bottom is computed, not asserted: seven tests run
on every build, Benjamini-Hochberg decides which survive, and the copy adapts. If
one ever does survive, the page says so.
"""
from collections import defaultdict
from datetime import date, timedelta

from lib_esoteric import (biorhythm_percent, is_critical, is_mercury_retrograde,
                          next_retrograde, personal_number, retrograde_periods,
                          to_base_digit)
from lib_stats import (benjamini_hochberg, kruskal_wallis, mean, ols, pearson_r,
                       sem, welch_t)

MIN_N = 10          # below this a group gets no crown and shows its n
FDR = 0.05
WEEKDAYS = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
BIO = [("physical", "Fizyczny"), ("emotional", "Emocjonalny"), ("intellectual", "Intelektualny")]


def _fmt_pace(s):
    if not s:
        return None
    return f"{int(s) // 60}:{int(round(s)) % 60:02d}"


def _group_stats(groups, overall):
    """[{key, n, pace_s, pace, dev_s, sem_s, noise}] sorted fastest first."""
    out = []
    for key, vals in groups.items():
        if not vals:
            continue
        m = mean(vals)
        e = sem(vals)
        out.append({"key": key, "n": len(vals), "pace_s": round(m, 1),
                    "pace": _fmt_pace(m), "dev_s": round(m - overall, 1),
                    "sem_s": round(e, 1),
                    # "within noise" == the +/-2 SE band covers zero
                    "noise": abs(m - overall) <= 2 * e,
                    "small": len(vals) < MIN_N})
    return sorted(out, key=lambda r: r["pace_s"])


def _spread(rows, field="dev_s"):
    if not rows:
        return 0.0
    vals = [r[field] for r in rows]
    return round(max(vals) - min(vals), 1)


def build(runs, cfg, weather, moon_phase, zsign, records, today):
    """runs: qualified Run objects with .wdate (Warsaw date) and .pace_s attached."""
    paces = [r.pace_s for r in runs]
    overall = mean(paces)
    birth = cfg.get("birth_date")
    birth = date.fromisoformat(birth) if birth else None

    # ---------------------------------------------------------------- moon
    by_moon = defaultdict(list)
    for r in runs:
        by_moon[moon_phase(r.wdate)].append(r.pace_s)
    moon_rows = _group_stats(by_moon, overall)

    longest = max(runs, key=lambda r: r.distance_km)
    by_wd = defaultdict(list)
    for r in runs:
        by_wd[r.wdate.weekday()].append(r.pace_s)
    busiest = max(by_wd, key=lambda k: len(by_wd[k]))
    wd_spread = round(max(by_wd[busiest]) - min(by_wd[busiest]))
    phase_spread = round(_spread(moon_rows))

    # third line only lands if the within-group scatter dwarfs the between-group one
    if wd_spread > phase_spread:
        contrast = {"kind": "weekday", "label": WEEKDAYS[busiest], "spread_s": wd_spread}
    else:
        biggest = max(moon_rows, key=lambda r: r["n"])
        vals = by_moon[biggest["key"]]
        contrast = {"kind": "phase", "label": biggest["key"],
                    "spread_s": round(max(vals) - min(vals))}

    pb = None
    pr = (records or {}).get("personal_records") or {}
    shortest = next((k for k in ("1k", "mile", "5k", "10k", "half") if k in pr), None)
    if shortest:
        target = pr[shortest]["seconds"]
        cand = [r for r in runs if r.duration_s and abs(r.duration_s - target) < 60]
        if cand:
            best = min(cand, key=lambda r: abs(r.duration_s - target))
            pb = {"phase": moon_phase(best.wdate), "label": shortest.replace("k", " km")}

    moon_block = {
        "rows": moon_rows,
        "longest": {"phase": moon_phase(longest.wdate), "km": round(longest.distance_km, 1)},
        "pb": pb,
        "phase_spread_s": phase_spread,
        "contrast": contrast,
    }

    # ------------------------------------------------------------- mercury
    retro_days = set()
    for a, b in retrograde_periods(runs[0].wdate, max(today, runs[-1].wdate)):
        d = a
        while d <= b:
            retro_days.add(d)
            d += timedelta(days=1)
    in_retro = [r for r in runs if r.wdate in retro_days]
    out_retro = [r for r in runs if r.wdate not in retro_days]
    span_days = (runs[-1].wdate - runs[0].wdate).days + 1
    retro_share = round(100 * len({d for d in retro_days
                                   if runs[0].wdate <= d <= runs[-1].wdate}) / span_days)
    km_retro = sum(r.distance_km for r in in_retro)
    p_retro = mean([r.pace_s for r in in_retro]) if in_retro else 0
    p_norm = mean([r.pace_s for r in out_retro]) if out_retro else 0
    diff = round(p_retro - p_norm, 1)
    # Significance comes from the test, not from the size of the gap. 4.5 s/km looks
    # like something until Welch puts p at 0.21 on this much within-run scatter.
    _, _, retro_p = welch_t([r.pace_s for r in in_retro], [r.pace_s for r in out_retro])
    active = is_mercury_retrograde(today)
    nxt = next_retrograde(today)
    mercury = {
        "km": round(km_retro), "km_pct": round(100 * km_retro / sum(r.distance_km for r in runs)),
        "days_pct": retro_share, "runs": len(in_retro),
        "pace_retro": _fmt_pace(p_retro), "pace_normal": _fmt_pace(p_norm),
        "diff_s": diff, "faster": diff < 0, "p": round(retro_p, 4),
        "noise": retro_p >= FDR,
        "active": active,
        "next_start": nxt[0].isoformat() if nxt else None,
        "days_to_next": (nxt[0] - today).days if nxt else None,
    }
    if active:
        cur = next((b for a, b in retrograde_periods(today - timedelta(days=30),
                                                     today + timedelta(days=30))
                    if a <= today <= b), None)
        mercury["days_left"] = (cur - today).days if cur else None

    # ----------------------------------------------------------- biorhythm
    bio = None
    if birth:
        pool = [r for r in runs if r.distance_km > 10]
        target_run = min(pool, key=lambda r: r.pace_s) if pool else min(runs, key=lambda r: r.pace_s)
        pct = biorhythm_percent(birth, target_run.wdate)
        vals = [{"key": k, "label": lbl, "pct": pct[k],
                 "critical": is_critical(birth, target_run.wdate, k)} for k, lbl in BIO]
        total = sum(pct.values())
        bio = {
            "date": target_run.wdate.isoformat(),
            "name": target_run.name, "km": round(target_run.distance_km, 1),
            "pace": _fmt_pace(target_run.pace_s),
            "values": vals, "sum": total,
            "tone": "bad" if total < -50 else ("good" if total > 50 else "flat"),
            "fastest_long": len(pool),
        }

    # ---------------------------------------------------------- numerology
    numerology = None
    if birth:
        num = {}
        for base in (10, 16):
            g = defaultdict(list)
            for r in runs:
                g[personal_number(birth, r.wdate, base)].append(r.pace_s)
            rows = _group_stats(g, overall)
            for row in rows:
                row["label"] = to_base_digit(row["key"], base)
            best = next((r for r in rows if not r["small"]), None)
            num[f"base{base}"] = {"rows": rows,
                                  "lucky": best["label"] if best else None,
                                  "lucky_noise": best["noise"] if best else True}
        numerology = num

    # -------------------------------------------------------------- zodiac
    by_sign = defaultdict(list)
    for r in runs:
        by_sign[zsign(r.wdate)].append(r.pace_s)
    zodiac_raw = _group_stats(by_sign, overall)

    with_w = [r for r in runs if r.temp_c is not None]
    coverage = round(100 * len(with_w) / len(runs))
    resid_rows, model_kind, spread_resid = [], None, None
    if coverage >= 30:
        y = [r.pace_s for r in with_w]
        coeffs, resid = ols(y, [[r.temp_c for r in with_w], [r.vol7 for r in with_w]])
        model_kind = "temp+vol"
        if coeffs is None:
            coeffs, resid = ols(y, [[r.vol7 for r in with_w]])
            model_kind = "vol"
        if resid:
            g = defaultdict(list)
            for r, e in zip(with_w, resid):
                g[zsign(r.wdate)].append(e)
            base = mean(resid)
            resid_rows = _group_stats(g, base)
            spread_resid = _spread(resid_rows)

    spread_raw = _spread(zodiac_raw)
    months_by_sign, temp_by_sign = defaultdict(list), defaultdict(list)
    for r in runs:
        s = zsign(r.wdate)
        months_by_sign[s].append(r.wdate.month)
        if r.temp_c is not None:
            temp_by_sign[s].append(r.temp_c)

    def _med(v):
        return round(sorted(v)[len(v) // 2]) if v else None

    zodiac = {
        "raw": zodiac_raw, "resid": resid_rows,
        "spread_raw_s": spread_raw, "spread_resid_s": spread_resid,
        "drop_pct": round(100 * (1 - spread_resid / spread_raw)) if spread_resid and spread_raw else None,
        "coverage_pct": coverage, "model": model_kind,
        "top": [r["key"] for r in zodiac_raw[:3]],
        "bottom": [r["key"] for r in zodiac_raw[-3:]],
        "top_temp": _med([t for r in zodiac_raw[:3] for t in temp_by_sign[r["key"]]]),
        "bottom_temp": _med([t for r in zodiac_raw[-3:] for t in temp_by_sign[r["key"]]]),
    }
    # Which way the reveal actually went. It is allowed to fail: adjusting for
    # weather and load can leave the gap untouched, or widen it, and if so the page
    # has to say that instead of pretending the confounder was found.
    drop = zodiac["drop_pct"]
    zodiac["verdict"] = (None if drop is None else
                         "explained" if drop >= 40 else
                         "partial" if drop > 0 else "unexplained")

    # ----------------------------------------------------- hypothesis register
    tests = []

    def add(tid, label, method, p):
        tests.append({"id": tid, "label": label, "method": method,
                      "p": None if p is None else round(p, 4)})

    add("moon", "faza Księżyca", "Kruskal-Wallis", kruskal_wallis(list(by_moon.values()))[2])
    add("weekday", "dzień tygodnia", "Kruskal-Wallis", kruskal_wallis(list(by_wd.values()))[2])
    add("mercury", "retrograd Merkurego", "Welch",
        welch_t([r.pace_s for r in in_retro], [r.pace_s for r in out_retro])[2])
    if birth:
        phys = [biorhythm_percent(birth, r.wdate)["physical"] for r in runs]
        add("biorhythm", "biorytm fizyczny", "Pearson", pearson_r(phys, paces)[2])
        crit = [r.pace_s for r in runs if is_critical(birth, r.wdate, "physical")]
        non = [r.pace_s for r in runs if not is_critical(birth, r.wdate, "physical")]
        add("critical", "dzień krytyczny", "Welch", welch_t(crit, non)[2])
        g10 = defaultdict(list)
        for r in runs:
            g10[personal_number(birth, r.wdate, 10)].append(r.pace_s)
        add("numerology", "dzień osobisty", "Kruskal-Wallis", kruskal_wallis(list(g10.values()))[2])
    add("zodiac", "znak zodiaku", "Kruskal-Wallis", kruskal_wallis(list(by_sign.values()))[2])

    ps = [t["p"] for t in tests if t["p"] is not None]
    keep = benjamini_hochberg(ps, FDR)
    i = 0
    for t in tests:
        if t["p"] is None:
            t["significant"] = False
            continue
        t["significant"] = keep[i]
        t["raw_significant"] = t["p"] < FDR
        i += 1
    survivors = [t["label"] for t in tests if t.get("significant")]

    return {
        "mean_pace_s": round(overall, 1), "mean_pace": _fmt_pace(overall),
        "runs": len(runs),
        "moon": moon_block, "mercury": mercury, "biorhythm": bio,
        "numerology": numerology, "zodiac": zodiac,
        "tests": tests,
        "register": {"n": len(ps), "expected": round(FDR * len(ps), 2),
                     "survived": len(survivors), "names": survivors,
                     "raw_hits": sum(1 for t in tests if t.get("raw_significant")),
                     # picks the closing sentence; "one_open" is the awkward case
                     # where something survived and the adjustment did not kill it
                     "verdict": ("none" if not survivors else
                                 "many" if len(survivors) > 1 else
                                 "one_explained" if survivors == ["znak zodiaku"]
                                 and zodiac["verdict"] == "explained"
                                 else "one_open")},
    }
