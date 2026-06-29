# Records Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the "rekordy / Tablica chwały" section (layout v3) and feed it Garmin's official personal records + race-fitness predictions instead of FIT-bucket approximations.

**Architecture:** `fetch_garmin.py` pulls official PRs + predictions (via `garminconnect`, passwordless) into `cache/records.json`. A pure `build_records_block()` in `generate.py` turns that (with graceful FIT fallbacks) into `data.json["records"]`. `template.html` renders the v3 section (hero → race PR tiles with inline prediction → sprint PRs → marathon next-goal bar → supporting trio). The pure functions are unit-tested; the template is verified via a fixture preview (no FIT cache needed because `_inline()` just swaps the `const DATA =` line).

**Tech Stack:** Python 3, `garminconnect`, `pytest`. Self-contained HTML/CSS/JS (inline SVG icons, no new CDN).

---

## File Structure

- `garmin_records.py` — **new**: pure `normalize_records(prs, preds)` → the `cache/records.json` dict. Isolated so it is testable without Garmin and reusable by an MCP-driven path.
- `fetch_garmin.py` — calls `get_personal_record()` + `get_race_predictions()`, runs them through `normalize_records`, writes `cache/records.json` (best-effort).
- `generate.py` — **new** pure `build_records_block(...)`; `main()` loads `cache/records.json` and calls it to populate `data.json["records"]`.
- `template.html` — replaces the records `<section>` (CSS + markup + JS builder), fixing the duplicate `id="records"`.
- `tests/test_garmin_records.py`, `tests/test_records_block.py` — **new** unit tests.
- `tests/fixtures/preview_data.json` — **new** fixture for visual preview of the template.
- `CLAUDE.md` — note the new fetch + section behaviour.

### Raw Garmin shapes (verified against the live `garminconnect` lib)
`get_personal_record()` → `list` of dicts: `{"typeId": 1, "value": 259.97, "activityType": "running", ...}`. Running typeIds: `1`=1K, `2`=mile, `3`=5K, `4`=10K, `5`=half, `7`=longest run. For times `value` is seconds; for longest run `value` is metres.
`get_race_predictions()` → flat `dict`: `{"time5K": 1436, "time10K": 3051, "timeHalfMarathon": 6796, "timeMarathon": 14937, ...}` (seconds).

### `data.json["records"]` schema produced by `build_records_block`
```json
{
  "longest": {"km": 22.09, "date": "2024-10-12", "name": "Półmaraton Wrocław"},
  "race": [{"key":"5k","label":"5 km","time":"25:36","pace":"5:07",
            "pred":{"time":"23:56","delta":"1:40","faster":true}}],
  "sprint": [{"key":"1k","label":"1 km","time":"4:19","pace":"4:19"}],
  "marathon": {"time":"4:08:57"},
  "totals": {"km": 3421, "runs": 612},
  "peak_week": {"km": 71.0, "week": "2024-W23"},
  "fastest_year": {"year": 2024, "pace": "5:42"}
}
```
`pred`/`sprint`/`marathon` entries are present only when their data exists.

---

## Task 1: `normalize_records` + write `cache/records.json`

**Files:**
- Create: `garmin_records.py`
- Create: `tests/test_garmin_records.py`
- Modify: `fetch_garmin.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_garmin_records.py`:

```python
from garmin_records import normalize_records

PRS = [
    {"typeId": 1, "value": 259.97, "activityType": "running"},
    {"typeId": 3, "value": 1536.74, "activityType": "running"},
    {"typeId": 7, "value": 22085.94, "activityType": "running"},
    {"typeId": 8, "value": 28671.0, "activityType": "cycling"},
    {"typeId": 18, "value": 130.0, "activityType": "swimming"},
]
PREDS = {"time5K": 1436, "time10K": 3051, "timeHalfMarathon": 6796, "timeMarathon": 14937}


def test_maps_running_prs_by_typeid():
    out = normalize_records(PRS, PREDS)
    assert out["personal_records"]["1k"] == {"seconds": 259.97}
    assert out["personal_records"]["5k"] == {"seconds": 1536.74}
    assert out["personal_records"]["longest_run_km"] == 22.09


def test_ignores_non_running_prs():
    out = normalize_records(PRS, PREDS)
    pr = out["personal_records"]
    assert "mile" not in pr            # typeId 2 not in input
    assert all(k not in pr for k in ("ride", "swim"))
    assert set(pr) <= {"1k", "mile", "5k", "10k", "half", "longest_run_km"}


def test_maps_predictions():
    out = normalize_records(PRS, PREDS)
    assert out["predictions"] == {
        "5k": {"seconds": 1436}, "10k": {"seconds": 3051},
        "half": {"seconds": 6796}, "marathon": {"seconds": 14937},
    }


def test_handles_empty_inputs():
    assert normalize_records(None, None) == {"personal_records": {}, "predictions": {}}
    assert normalize_records([], {}) == {"personal_records": {}, "predictions": {}}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `. .venv/bin/activate && pytest tests/test_garmin_records.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'garmin_records'`

- [ ] **Step 3: Write `garmin_records.py`**

```python
#!/usr/bin/env python3
"""Normalize Garmin official personal records + race predictions into the
`cache/records.json` shape the generator reads. Pure — no network, no I/O —
so it is testable without Garmin and reusable from an MCP-driven path.

Raw inputs come from `garminconnect`:
- get_personal_record() -> list of {"typeId", "value", ...}; running typeIds:
  1=1K, 2=mile, 3=5K, 4=10K, 5=half, 7=longest run. `value` is seconds for
  times, metres for the longest-run distance.
- get_race_predictions() -> {"time5K", "time10K", "timeHalfMarathon",
  "timeMarathon"} in seconds.
"""
from __future__ import annotations

_PR_KEYS = {1: "1k", 2: "mile", 3: "5k", 4: "10k", 5: "half", 7: "longest"}
_PRED_KEYS = {"5k": "time5K", "10k": "time10K", "half": "timeHalfMarathon",
              "marathon": "timeMarathon"}


def normalize_records(prs, preds) -> dict:
    out: dict = {"personal_records": {}, "predictions": {}}
    for p in (prs or []):
        key = _PR_KEYS.get(p.get("typeId"))
        val = p.get("value")
        if not key or val is None:
            continue
        if key == "longest":
            out["personal_records"]["longest_run_km"] = round(val / 1000, 2)
        else:
            out["personal_records"][key] = {"seconds": round(val, 2)}
    for key, src in _PRED_KEYS.items():
        v = (preds or {}).get(src)
        if v:
            out["predictions"][key] = {"seconds": int(v)}
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `. .venv/bin/activate && pytest tests/test_garmin_records.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Wire into `fetch_garmin.py`**

In `fetch_garmin.py`, add the import near the top (after the existing imports):

```python
from garmin_records import normalize_records
```

Add this helper above `main()`:

```python
def _save_records(g):
    """Best-effort: pull official PRs + race predictions into cache/records.json.
    A failure here must never block the activity download."""
    try:
        prs = g.get_personal_record()
    except Exception:
        prs = None
    try:
        preds = g.get_race_predictions()
    except Exception:
        preds = None
    rec = normalize_records(prs, preds)
    if rec["personal_records"] or rec["predictions"]:
        (CACHE / "records.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        print(f"  · Garmin records → {len(rec['personal_records'])} PR, "
              f"{len(rec['predictions'])} predictions")
```

In `main()`, call it right after `_merge_me_json(profile_defaults(g))`:

```python
    _merge_me_json(profile_defaults(g))   # birth year + resting HR for HR zones
    _save_records(g)                      # official PRs + race predictions
```

- [ ] **Step 6: Verify the import graph is intact**

Run: `. .venv/bin/activate && python -c "import fetch_garmin, garmin_records; print('ok')"`
Expected: prints `ok`

- [ ] **Step 7: Commit**

```bash
git add garmin_records.py tests/test_garmin_records.py fetch_garmin.py
git commit -m "feat: pull official Garmin PRs + race predictions into cache/records.json"
```

---

## Task 2: `build_records_block` pure function

**Files:**
- Modify: `generate.py`
- Create: `tests/test_records_block.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_records_block.py`:

```python
from generate import build_records_block

REC = {
    "personal_records": {
        "1k": {"seconds": 259.97}, "mile": {"seconds": 439.66},
        "5k": {"seconds": 1536.74}, "10k": {"seconds": 3164.93},
        "half": {"seconds": 6865.71}, "longest_run_km": 22.09,
    },
    "predictions": {
        "5k": {"seconds": 1436}, "10k": {"seconds": 3051},
        "half": {"seconds": 6796}, "marathon": {"seconds": 14937},
    },
}
LONGEST = {"km": 22.09, "date": "2024-10-12", "name": "Półmaraton Wrocław"}
TOTALS = {"km": 3421, "runs": 612}
PEAK = {"km": 71.0, "week": "2024-W23"}
FASTEST = {"year": 2024, "pace": "5:42"}


def _block(**kw):
    base = dict(rec_json=REC, longest=LONGEST, totals=TOTALS, peak_week=PEAK,
                fastest_year=FASTEST, fallback_5k=None, fallback_10k=None)
    base.update(kw)
    return build_records_block(**base)


def test_race_tiles_have_time_pace_and_prediction():
    b = _block()
    five = next(r for r in b["race"] if r["key"] == "5k")
    assert five["time"] == "25:36"
    assert five["pace"] == "5:07"
    assert five["pred"] == {"time": "23:56", "delta": "1:40", "faster": True}


def test_half_marathon_time_uses_hms():
    b = _block()
    half = next(r for r in b["race"] if r["key"] == "half")
    assert half["time"] == "1:54:25"
    assert half["pred"]["time"] == "1:53:16"


def test_sprint_tiles_have_no_prediction():
    b = _block()
    keys = [s["key"] for s in b["sprint"]]
    assert keys == ["1k", "mile"]
    assert b["sprint"][0]["time"] == "4:19"


def test_marathon_is_prediction_only():
    assert _block()["marathon"] == {"time": "4:08:57"}


def test_longest_and_supporting_passthrough():
    b = _block()
    assert b["longest"] == LONGEST
    assert b["totals"] == TOTALS
    assert b["peak_week"] == PEAK
    assert b["fastest_year"] == FASTEST


def test_no_records_json_falls_back_to_derived():
    fb5 = {"time": "26:10", "pace": "5:14", "date": "2023-05-01"}
    fb10 = {"time": "54:00", "pace": "5:24", "date": "2023-06-01"}
    b = build_records_block(rec_json=None, longest=LONGEST, totals=TOTALS,
                            peak_week=PEAK, fastest_year=FASTEST,
                            fallback_5k=fb5, fallback_10k=fb10)
    keys = [r["key"] for r in b["race"]]
    assert keys == ["5k", "10k"]            # half has no fallback
    assert all(r["pred"] is None for r in b["race"])
    assert b["sprint"] == []
    assert b["marathon"] is None
    assert b["longest"] == LONGEST          # hero always present


def test_predictions_present_but_no_pr_for_distance():
    rec = {"personal_records": {"5k": {"seconds": 1536.74}},
           "predictions": {"10k": {"seconds": 3051}}}
    b = build_records_block(rec_json=rec, longest=LONGEST, totals=TOTALS,
                            peak_week=PEAK, fastest_year=FASTEST,
                            fallback_5k=None, fallback_10k=None)
    five = next(r for r in b["race"] if r["key"] == "5k")
    assert five["pred"] is None             # no 5k prediction -> no pred line
    assert all(r["key"] != "10k" for r in b["race"])  # 10k has prediction but no PR -> no tile
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `. .venv/bin/activate && pytest tests/test_records_block.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_records_block'`

- [ ] **Step 3: Implement `build_records_block` in `generate.py`**

Add near the other module-level helpers (e.g. just after `fmt_pace`, around line 39). It reuses the existing `fmt_pace`:

```python
_RACE = [("5k", "5 km", 5.0), ("10k", "10 km", 10.0), ("half", "½ maraton", 21.0975)]
_SPRINT = [("1k", "1 km", 1.0), ("mile", "Mila", 1.609344)]


def _fmt_time(sec):
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def build_records_block(*, rec_json, longest, totals, peak_week, fastest_year,
                        fallback_5k, fallback_10k):
    """Pure: assemble data.json['records'] from Garmin records (rec_json) with
    FIT-derived fallbacks. See docs/superpowers/specs for the schema."""
    prs = (rec_json or {}).get("personal_records", {})
    preds = (rec_json or {}).get("predictions", {})

    race = []
    for key, label, dist in _RACE:
        pr = prs.get(key)
        if pr:
            sec = pr["seconds"]
            time, pace = _fmt_time(sec), fmt_pace(sec / dist)
            pred = None
            p = preds.get(key)
            if p:
                delta = sec - p["seconds"]
                pred = {"time": _fmt_time(p["seconds"]),
                        "delta": _fmt_time(abs(delta)), "faster": delta > 0}
            race.append({"key": key, "label": label, "time": time, "pace": pace, "pred": pred})
        else:
            fb = {"5k": fallback_5k, "10k": fallback_10k}.get(key)
            if fb:
                race.append({"key": key, "label": label, "time": fb["time"],
                             "pace": fb["pace"], "pred": None})

    sprint = []
    for key, label, dist in _SPRINT:
        pr = prs.get(key)
        if pr:
            sprint.append({"key": key, "label": label, "time": _fmt_time(pr["seconds"]),
                           "pace": fmt_pace(pr["seconds"] / dist)})

    marathon = None
    if preds.get("marathon"):
        marathon = {"time": _fmt_time(preds["marathon"]["seconds"])}

    return {"longest": longest, "race": race, "sprint": sprint, "marathon": marathon,
            "totals": totals, "peak_week": peak_week, "fastest_year": fastest_year}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `. .venv/bin/activate && pytest tests/test_records_block.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add generate.py tests/test_records_block.py
git commit -m "feat: build_records_block — official PRs + predictions model with fallbacks"
```

---

## Task 3: Wire `build_records_block` into `generate.py` main

**Files:**
- Modify: `generate.py` (records dict in the `data = {...}` block, ~line 405-411; add cache read in `main()`)

- [ ] **Step 1: Load `cache/records.json` in `main()`**

In `main()`, right after `runs = merge_runs(...)` and its guard (just before `world = World(...)`, ~line 228), add:

```python
    rec_path = cache / "records.json"
    rec_json = json.loads(rec_path.read_text()) if rec_path.exists() else None
```

- [ ] **Step 2: Replace the inline `records` dict**

In the `data = {...}` literal, replace the entire `"records": { ... "best_5k": ..., "best_10k": ...}` entry (the block currently spanning ~lines 405-411) with:

```python
        "records": build_records_block(
            rec_json=rec_json,
            longest={"km": round(longest.distance_km, 2),
                     "date": longest.start_time.strftime("%Y-%m-%d"), "name": longest.name or "—"},
            totals={"km": round(total_km), "runs": len(runs)},
            peak_week={"week": peak_week, "km": round(by_week[peak_week], 1)},
            fastest_year={"year": fastest_year["year"], "pace": fastest_year["pace"]},
            fallback_5k=best_at(4.8, 5.2), fallback_10k=best_at(9.5, 10.5)),
```

- [ ] **Step 3: Verify generate.py imports and the suite is green**

Run: `. .venv/bin/activate && python -c "import ast; ast.parse(open('generate.py').read()); print('parses')" && pytest -q`
Expected: `parses`, then all tests pass (includes Task 1 + Task 2 + the pre-existing Strava tests).

- [ ] **Step 4: Commit**

```bash
git add generate.py
git commit -m "feat: feed build_records_block into data.json records"
```

---

## Task 4: Redesign the records section in `template.html`

**Files:**
- Modify: `template.html` (CSS ~lines 101-107; section ~lines 460-465; JS builder ~lines 682-699)
- Create: `tests/fixtures/preview_data.json`

This task is verified visually (no FIT cache on this machine) by injecting a fixture into the template via `generate._inline`.

- [ ] **Step 1: Create the preview fixture**

Create `tests/fixtures/preview_data.json` — a minimal but complete `data.json` so the page renders. It must contain every top-level key the template reads. Start from the real schema; the records block uses the Task 3 output:

```json
{
  "lifetime": {"runs": 612, "km": 3421, "hours": 342, "years": 6, "first": "2019-03-01", "last": "2024-12-20", "cities": 8, "earth_pct": 8.5},
  "geo": {"home_city": "Wrocław", "country": "Polska", "country_flag": "🇵🇱"},
  "years": [{"year": 2023, "km": 520, "pace": "5:50", "pace_s": 350, "runs": 90}, {"year": 2024, "km": 700, "pace": "5:42", "pace_s": 342, "runs": 120}],
  "months": [], "zones_by_year": [], "zone_bounds": [120, 140, 155, 170, 185],
  "records": {
    "longest": {"km": 22.09, "date": "2024-10-12", "name": "Półmaraton Wrocław"},
    "race": [
      {"key": "5k", "label": "5 km", "time": "25:36", "pace": "5:07", "pred": {"time": "23:56", "delta": "1:40", "faster": true}},
      {"key": "10k", "label": "10 km", "time": "52:44", "pace": "5:16", "pred": {"time": "50:51", "delta": "1:53", "faster": true}},
      {"key": "half", "label": "½ maraton", "time": "1:54:25", "pace": "5:25", "pred": {"time": "1:53:16", "delta": "1:09", "faster": true}}
    ],
    "sprint": [
      {"key": "1k", "label": "1 km", "time": "4:19", "pace": "4:19"},
      {"key": "mile", "label": "Mila", "time": "7:19", "pace": "4:33"}
    ],
    "marathon": {"time": "4:08:57"},
    "totals": {"km": 3421, "runs": 612},
    "peak_week": {"km": 71.0, "week": "2024-W23"},
    "fastest_year": {"year": 2024, "pace": "5:42"}
  },
  "regions": [], "poland": null, "weekday": [0,0,0,0,0,0,0], "hours": [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
  "dist_hist": [], "moon": [], "fav_moon": "", "zodiac": [], "strongest_sign": null,
  "maps": [], "scale": {"ascent_m": 0, "peaks": [], "distance": {"closest": null, "cities": []}, "countries": [], "weekday": [0,0,0,0,0,0,0], "hours": [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]}
}
```

- [ ] **Step 2: Replace the records CSS**

In `template.html`, replace the `/* records */` block (currently lines 101-107: `.grid`, `.card`, `.card::after`, `.card .big/.lbl/.sub`) with the v3 styles. Keep using the theme vars:

```css
  /* records — v3 */
  .rec-hero{background:var(--ink2);border:1px solid var(--line);border-radius:18px;padding:22px 24px;
    position:relative;overflow:hidden;display:flex;justify-content:space-between;align-items:flex-end;gap:16px}
  .rec-hero::before{content:"";position:absolute;inset:0 0 auto 0;height:4px;background:var(--grad)}
  .rec-hero .num{font-family:'Anton';font-size:clamp(40px,7vw,62px);line-height:.9;
    color:transparent;background:var(--grad);-webkit-background-clip:text;background-clip:text}
  .rec-hero .num .u{font-size:.45em}
  .rec-lbl{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.13em;font-weight:600;
    display:inline-flex;align-items:center;gap:6px}
  .rec-lbl svg{width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:2}
  .rec-cap{color:var(--muted);font-size:10.5px;text-transform:uppercase;letter-spacing:.12em;font-weight:600;margin:18px 0 9px}
  .rec-cap.grad{color:transparent;background:var(--grad);-webkit-background-clip:text;background-clip:text}
  .rec-race{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
  .rtile{background:var(--ink2);border:1px solid var(--line);border-radius:16px;padding:16px}
  .rtile .t{font-family:'Anton';font-size:clamp(22px,3.4vw,28px);line-height:.9;margin-top:8px}
  .rtile .pace{color:var(--muted);font-size:11px;margin-top:4px}
  .rtile .pred{display:flex;align-items:center;gap:6px;margin-top:11px;padding-top:10px;border-top:1px solid var(--line)}
  .rtile .pred .pv{color:var(--cream);opacity:.55;font-size:12px}
  .rtile .pred .d{margin-left:auto;font-size:11px;font-weight:700;
    color:transparent;background:var(--grad);-webkit-background-clip:text;background-clip:text}
  .rtile .pred svg{width:13px;height:13px;stroke:var(--a2);fill:none;stroke-width:2}
  .rec-sprint{display:flex;gap:8px;margin-top:8px}
  .rec-sprint .rtile{flex:1;display:flex;align-items:baseline;gap:10px;padding:12px 16px}
  .rec-sprint .t{margin:0;font-size:21px}
  .rec-sprint .pace{margin:0 0 0 auto}
  .rec-goal{display:flex;align-items:center;gap:8px;margin-top:12px;padding:11px 16px;
    border:1px dashed var(--line);border-radius:13px;color:var(--muted);font-size:12.5px}
  .rec-goal svg{width:15px;height:15px;stroke:var(--a1);fill:none;stroke-width:2}
  .rec-goal .m{font-family:'Anton';font-size:20px;margin-left:auto;
    color:transparent;background:var(--grad);-webkit-background-clip:text;background-clip:text}
  .rec-sup{display:grid;grid-template-columns:1.3fr 1fr 1fr;gap:8px;margin-top:16px}
  .rec-sup .t{font-family:'Anton';font-size:clamp(22px,3.4vw,27px);line-height:.9;margin-top:7px}
  .rec-sup .t .u{font-size:.5em;opacity:.6}
  .rec-sup .sub{font-size:12.5px;color:var(--cream);opacity:.6;margin-top:5px}
```

- [ ] **Step 3: Replace the section markup (fix the duplicate id)**

Replace lines 461-465 (the `<section id="records">...</section>`) with — note the body container gets a unique id, the section keeps `id="records"`:

```html
  <section id="records" style="order:9">
    <div class="kicker rv">Rozdział 9 — rekordy</div>
    <h2 class="rv">Tablica chwały</h2>
    <div id="rec-body" class="rv"></div>
  </section>
```

- [ ] **Step 4: Replace the JS builder**

Replace the records IIFE (currently lines 682-699, `/* ---------- records ---------- */ (function(){...})();`) with the v3 builder. It reads the new `DATA.records` schema and writes into `#rec-body`:

```javascript
/* ---------- records (v3) ---------- */
(function(){
  const r=DATA.records;
  const ICON={route:'<svg viewBox="0 0 24 24"><path d="M9 19a3 3 0 0 1-3-3V8a3 3 0 0 0-3-3"/><path d="M15 5a3 3 0 0 1 3 3v8a3 3 0 0 0 3 3"/><circle cx="6" cy="5" r="1.6"/><circle cx="18" cy="19" r="1.6"/></svg>',
    flame:'<svg viewBox="0 0 24 24"><path d="M12 3c1 4 5 5 5 9a5 5 0 0 1-10 0c0-2 1-3 2-4 0 1 1 2 2 2 0-3-1-5 1-7z"/></svg>',
    goal:'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 1v3M12 20v3M1 12h3M20 12h3"/></svg>'};
  const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  let h='';
  const lk=r.longest.km, lw=(lk%1?lk.toFixed(1):lk);
  h+=`<div class="rec-hero">
    <div><div class="rec-lbl">${ICON.route} Najdłuższy bieg</div>
      <div class="sub" style="color:var(--cream);opacity:.6;font-size:12.5px;margin-top:9px">${esc(r.longest.name)} · ${esc(r.longest.date)}</div></div>
    <div class="num">${String(lw).split('.')[0]}<span class="u">${lw%1?'.'+String(lw).split('.')[1]:''} km</span></div></div>`;

  if(r.race.length){
    h+='<div class="rec-cap">Rekordy wyścigowe · rekord vs forma dziś (Garmin)</div><div class="rec-race">';
    h+=r.race.map(d=>`<div class="rtile"><div class="rec-lbl">${esc(d.label)}</div>
      <div class="t">${d.time}</div><div class="pace">${d.pace} / km</div>`+
      (d.pred?`<div class="pred">${ICON.flame}<span class="pv">prognoza ${d.pred.time}</span><span class="d">${d.pred.faster?'−':'+'}${d.pred.delta}</span></div>`:'')+
      `</div>`).join('');
    h+='</div>';
  }
  if(r.sprint.length){
    h+='<div class="rec-sprint">'+r.sprint.map(d=>`<div class="rtile"><div class="rec-lbl">${esc(d.label)}</div><div class="t">${d.time}</div><div class="pace">${d.pace}/km</div></div>`).join('')+'</div>';
  }
  if(r.marathon){
    h+=`<div class="rec-goal">${ICON.goal}<span>Następny cel wg Twojej formy — <span style="color:var(--cream)">maraton</span> (prognoza)</span><span class="m">${r.marathon.time}</span></div>`;
  }
  const km=n=>n.toLocaleString('pl').replace(/,/g,' ');
  h+=`<div class="rec-sup">
    <div class="rtile"><div class="rec-lbl">Łącznie</div><div class="t">${km(r.totals.km)}<span class="u"> km</span></div><div class="sub">${km(r.totals.runs)} biegów</div></div>
    <div class="rtile"><div class="rec-lbl">Rekord. tydzień</div><div class="t">${r.peak_week.km}<span class="u"> km</span></div></div>
    <div class="rtile"><div class="rec-lbl">Najszybszy rok</div><div class="t">${r.fastest_year.pace}</div><div class="sub">${r.fastest_year.year}</div></div></div>`;
  $('#rec-body').innerHTML=h;
})();
```

- [ ] **Step 5: Generate a preview and screenshot it**

Run:
```bash
. .venv/bin/activate && python -c "import json,generate; generate._inline(json.load(open('tests/fixtures/preview_data.json')))" && echo "index.html written"
```
Expected: `index.html written`. Then open `index.html` in a browser, scroll to "Tablica chwały", and confirm against the approved v3 mockup: hero with gradient km, 3 race tiles each showing PR + pace + a "prognoza" line with flame icon + gradient `−delta`, the 1K/mile sprint row, the dashed marathon goal bar, and the supporting trio. Verify the heading "Tablica chwały" is still present (the duplicate-id bug is fixed). Take a screenshot for the reviewer.

- [ ] **Step 6: Confirm the structure rendered (non-visual gate)**

Run: `grep -c "rec-hero\|rec-race\|rec-goal\|rec-sup" index.html`
Expected: `4` (all four blocks present in the generated output).

- [ ] **Step 7: Commit**

```bash
git add template.html tests/fixtures/preview_data.json
git commit -m "feat: redesign records section (v3) — hero, race PRs w/ predictions, goal bar"
```

---

## Task 5: Document in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (step 1 fetch description, ~lines 51-59)

- [ ] **Step 1: Add a records note to the fetch step**

In `CLAUDE.md`, at the end of step **1** (after the parenthetical about driving via the Garmin MCP, ~line 62), add:

```markdown
- `fetch_garmin.py` also pulls **official personal records** (1K, mila, 5K, 10K,
  półmaraton, najdłuższy bieg) and **race predictions** (5K/10K/½/maraton) into
  `cache/records.json` — these drive the redesigned "Tablica chwały" section.
  Best-effort: if the profile/endpoint is unavailable the section falls back to
  records derived from the FIT data. (Via a Garmin MCP: call `get_personal_record`
  + `get_race_predictions` and write the same `cache/records.json`.)
```

- [ ] **Step 2: Verify**

Run: `grep -n "records.json\|personal records" CLAUDE.md`
Expected: the new lines appear under step 1.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: note official PR + prediction fetch and the records section"
```

---

## Self-Review (completed by plan author)

- **Spec coverage:** official PR + prediction fetch via garminconnect → T1 (`normalize_records` + `fetch_garmin._save_records`, verified raw shapes `typeId`/`value` and `time5K`-style preds); `cache/records.json` schema → T1; `build_records_block` pure (pace, delta sign+`faster`, h:mm:ss, marathon-only, all fallbacks) → T2; main wiring + keep derived fallbacks → T3; v3 layout (hero/race+prediction/sprint/goal/trio), inline SVG icons, duplicate-id fix → T4; fixture-preview verification path → T4; CLAUDE.md → T5; unit tests → T1/T2. All spec sections mapped.
- **Placeholder scan:** none — every step has full code/commands.
- **Type consistency:** `normalize_records` output keys (`personal_records`/`predictions`, `1k/mile/5k/10k/half/longest_run_km`, `marathon`) match `build_records_block`'s reads (T2) and the fixture (T4). `build_records_block` output (`longest/race/sprint/marathon/totals/peak_week/fastest_year`, each race tile `key/label/time/pace/pred{time,delta,faster}`) matches the template JS reads in T4 exactly. `_fmt_time`/`fmt_pace` reused consistently. The section keeps `id="records"` (outro `o-longest` at template ~line 944 still reads `DATA.records.longest`, preserved by T3/T2).
