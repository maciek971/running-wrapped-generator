# Strava as a Second Source — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the generator build one runner's Wrapped from both their Garmin FIT cache and their Strava history (ingested via the Strava MCP), merged and deduplicated.

**Architecture:** Keep `Run` as the single normalized shape. Garmin produces `Run`s from FIT (`lib_fit`); Strava produces the same `Run`s from MCP-cached JSON (`lib_strava`); `lib_merge.merge_runs` unions and dedupes them. `generate.py` changes by a few lines. Strava ingestion itself is a Claude+MCP playbook step (documented in CLAUDE.md), writing normalized `cache/strava/<id>.json`.

**Tech Stack:** Python 3, `garmin_fit_sdk` (existing), `pytest` (new, dev).

---

## File Structure

- `lib_fit.py` — add `source` field to the shared `Run` dataclass (default `"garmin"`).
- `lib_strava.py` — **new** pure/offline loader: `cache/strava/*.json` → `Run`s.
- `lib_merge.py` — **new** `merge_runs(garmin, strava)` dedup/union.
- `generate.py` — load both sources, merge, print a source report.
- `CLAUDE.md` — Strava as an optional playbook source + one ground-rule line.
- `tests/test_strava.py`, `tests/test_merge.py` — **new** pytest.
- `requirements.txt` — add `pytest`.

---

## Task 1: Add `source` to the `Run` dataclass + pytest

**Files:**
- Modify: `lib_fit.py:20-33` (the `Run` dataclass)
- Modify: `requirements.txt`

- [ ] **Step 1: Add `source` field to `Run`**

In `lib_fit.py`, add the field at the end of the dataclass (after `hr_samples`):

```python
    hr_samples: list[int] = field(default_factory=list)  # per-record HR, for zone time
    source: str = "garmin"        # "garmin" | "strava" — for dedup preference + reporting
```

(The existing `Run(...)` construction in `_read_one` passes no `source`, so it defaults to `"garmin"` — no other change needed.)

- [ ] **Step 2: Add pytest to requirements**

Append to `requirements.txt`:

```
pytest
```

- [ ] **Step 3: Verify the package still imports**

Run: `. .venv/bin/activate && pip install -r requirements.txt && python -c "from lib_fit import Run; print(Run.__dataclass_fields__['source'].default)"`
Expected: prints `garmin`

- [ ] **Step 4: Commit**

```bash
git add lib_fit.py requirements.txt
git commit -m "feat: add source field to Run; add pytest dev dep"
```

---

## Task 2: `lib_strava.py` — load normalized Strava JSON into `Run`s

**Files:**
- Create: `lib_strava.py`
- Test: `tests/test_strava.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_strava.py`:

```python
import json

from lib_strava import load_strava

SAMPLE = {
    "id": "strava-1",
    "name": "Morning Run",
    "start_time": "2025-06-01T05:32:11Z",
    "utc_offset_h": 2,
    "distance_km": 8.42,
    "duration_s": 2715,
    "avg_hr": 154,
    "max_hr": 178,
    "ascent_m": 63,
    "latlng": [[52.40, 16.91], [52.41, 16.92], [52.42, 16.93], [52.43, 16.94]],
    "hr": [120, 121, 122],
}


def test_load_strava_parses(tmp_path):
    sdir = tmp_path / "strava"
    sdir.mkdir()
    (sdir / "1.json").write_text(json.dumps(SAMPLE))
    runs = load_strava(tmp_path, track_step=2)
    assert len(runs) == 1
    r = runs[0]
    assert r.source == "strava"
    assert r.id == "strava-1"
    assert r.distance_km == 8.42
    assert r.local_offset_h == 2
    assert r.avg_hr == 154 and r.max_hr == 178
    assert r.start == (52.4, 16.91)
    assert r.track == [(52.4, 16.91), (52.42, 16.93)]   # every 2nd point
    assert r.hr_samples == [120, 121, 122]


def test_load_strava_skips_short(tmp_path):
    sdir = tmp_path / "strava"
    sdir.mkdir()
    (sdir / "x.json").write_text(json.dumps({**SAMPLE, "distance_km": 0.5}))
    assert load_strava(tmp_path) == []


def test_load_strava_missing_dir(tmp_path):
    assert load_strava(tmp_path) == []


def test_load_strava_missing_gps_and_hr_degrades(tmp_path):
    sdir = tmp_path / "strava"
    sdir.mkdir()
    (sdir / "t.json").write_text(json.dumps({**SAMPLE, "latlng": [], "hr": []}))
    r = load_strava(tmp_path)[0]
    assert r.start is None and r.track == [] and r.hr_samples == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_strava.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib_strava'`

- [ ] **Step 3: Write `lib_strava.py`**

Create `lib_strava.py`:

```python
#!/usr/bin/env python3
"""Load Strava activities (cached as normalized JSON) into Run objects.

Claude writes `cache/strava/<id>.json` via the Strava MCP (see CLAUDE.md). This
module is pure/offline — it only reads those files. Symmetric with
`lib_fit.load_runs`: same Run shape, same >=1 km running filter, same subsampling.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from lib_fit import Run


def _read_one(data: dict, *, track_step: int) -> Run | None:
    dist_km = float(data.get("distance_km") or 0)
    st = data.get("start_time")
    if dist_km < 1.0 or not st:
        return None
    start_time = datetime.fromisoformat(st.replace("Z", "+00:00")).astimezone(timezone.utc)

    latlng = data.get("latlng") or []
    track = [(round(float(la), 5), round(float(lo), 5))
             for i, (la, lo) in enumerate(latlng) if i % track_step == 0]
    start = (round(float(latlng[0][0]), 5), round(float(latlng[0][1]), 5)) if latlng else None
    hr_samples = [int(h) for h in (data.get("hr") or []) if h]

    return Run(
        id=str(data.get("id")),
        name=(data.get("name") or None),
        start_time=start_time,
        local_offset_h=int(data.get("utc_offset_h") or 1),
        distance_km=dist_km,
        duration_s=float(data.get("duration_s") or 0),
        avg_hr=int(data["avg_hr"]) if data.get("avg_hr") else None,
        max_hr=int(data["max_hr"]) if data.get("max_hr") else None,
        ascent_m=float(data.get("ascent_m") or 0),
        start=start,
        track=track,
        hr_samples=hr_samples,
        source="strava",
    )


def load_strava(cache_dir: Path, *, track_step: int = 3) -> list[Run]:
    """Load Strava running activities (>=1 km) from `<cache>/strava/*.json`."""
    cache_dir = Path(cache_dir)
    sdir = cache_dir / "strava"
    if not sdir.exists():
        return []
    runs: list[Run] = []
    for fp in sorted(sdir.glob("*.json")):
        if fp.name == "manifest.json":
            continue
        try:
            data = json.loads(fp.read_text())
        except Exception:
            continue
        r = _read_one(data, track_step=track_step)
        if r and r.start_time:
            runs.append(r)
    runs.sort(key=lambda r: r.start_time)
    return runs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_strava.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add lib_strava.py tests/test_strava.py
git commit -m "feat: lib_strava — load normalized Strava JSON into Run objects"
```

---

## Task 3: `lib_merge.py` — dedup/union of Garmin + Strava

**Files:**
- Create: `lib_merge.py`
- Test: `tests/test_merge.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_merge.py`:

```python
from datetime import datetime, timedelta, timezone

from lib_fit import Run
from lib_merge import merge_runs

BASE = datetime(2025, 6, 1, 5, 0, tzinfo=timezone.utc)


def mk(rid, source, *, mins=0, dist=8.0, track=False):
    pts = [(1.0, 2.0), (1.1, 2.1)] if track else []
    return Run(
        id=rid, name=None, start_time=BASE + timedelta(minutes=mins),
        local_offset_h=2, distance_km=dist, duration_s=1800,
        avg_hr=150, max_hr=170, ascent_m=10,
        start=(pts[0] if pts else None), track=pts, hr_samples=[],
        source=source,
    )


def test_dedup_within_window_prefers_garmin():
    g = mk("g1", "garmin", mins=0, dist=8.0, track=True)
    s = mk("s1", "strava", mins=3, dist=8.1, track=True)
    out = merge_runs([g], [s])
    assert len(out) == 1
    assert out[0].source == "garmin"


def test_time_outside_window_keeps_both():
    g = mk("g1", "garmin", mins=0, dist=8.0)
    s = mk("s1", "strava", mins=6, dist=8.0)   # 6 min > 5 min tolerance
    assert len(merge_runs([g], [s])) == 2


def test_distance_outside_tolerance_keeps_both():
    g = mk("g1", "garmin", mins=0, dist=8.0)
    s = mk("s1", "strava", mins=1, dist=9.0)   # 1.0 km diff > max(0.3, 5%)
    assert len(merge_runs([g], [s])) == 2


def test_strava_only_passthrough():
    g = mk("g1", "garmin", mins=0, dist=8.0)
    s = mk("s1", "strava", mins=120, dist=5.0)
    out = merge_runs([g], [s])
    assert {r.source for r in out} == {"garmin", "strava"}
    assert len(out) == 2


def test_garmin_without_track_yields_to_strava_with_track():
    g = mk("g1", "garmin", mins=0, dist=8.0, track=False)
    s = mk("s1", "strava", mins=2, dist=8.0, track=True)
    out = merge_runs([g], [s])
    assert len(out) == 1
    assert out[0].source == "strava"


def test_both_empty():
    assert merge_runs([], []) == []


def test_result_sorted_by_time():
    g = mk("g1", "garmin", mins=120, dist=8.0)
    s = mk("s1", "strava", mins=0, dist=5.0)
    out = merge_runs([g], [s])
    assert [r.id for r in out] == ["s1", "g1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_merge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib_merge'`

- [ ] **Step 3: Write `lib_merge.py`**

Create `lib_merge.py`:

```python
#!/usr/bin/env python3
"""Merge Garmin + Strava runs into one deduplicated list.

A run that exists in both sources (Garmin auto-syncs to Strava) is matched by
start time + distance and kept once, preferring the Garmin original when it has a
GPS track. Strava-only runs pass straight through.
"""
from __future__ import annotations

from lib_fit import Run

_TIME_TOL_S = 5 * 60       # +/- 5 minutes
_DIST_TOL_FRAC = 0.05      # 5%
_DIST_TOL_KM = 0.3         # or 0.3 km absolute, whichever is larger


def _same_run(a: Run, b: Run) -> bool:
    if abs((a.start_time - b.start_time).total_seconds()) > _TIME_TOL_S:
        return False
    dd = abs(a.distance_km - b.distance_km)
    tol = max(_DIST_TOL_KM, _DIST_TOL_FRAC * max(a.distance_km, b.distance_km))
    return dd <= tol


def merge_runs(garmin: list[Run], strava: list[Run]) -> list[Run]:
    """Union of both sources, de-duplicated. On a match prefer Garmin when it has
    a GPS track; if Garmin lacks a track but Strava has one, keep Strava."""
    merged = list(garmin)
    for s in strava:
        match = next((g for g in merged if _same_run(g, s)), None)
        if match is None:
            merged.append(s)
        elif not match.track and s.track:
            merged[merged.index(match)] = s
        # else: duplicate, keep existing (Garmin) record
    merged.sort(key=lambda r: r.start_time)
    return merged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_merge.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add lib_merge.py tests/test_merge.py
git commit -m "feat: lib_merge — dedup/union of Garmin and Strava runs"
```

---

## Task 4: Wire both sources into `generate.py`

**Files:**
- Modify: `generate.py:19` (imports), `generate.py:225-227` (run loading)

- [ ] **Step 1: Add imports**

In `generate.py`, replace line 19 (`from lib_fit import load_runs`) with:

```python
from lib_fit import load_runs
from lib_merge import merge_runs
from lib_strava import load_strava
```

- [ ] **Step 2: Load + merge both sources**

Replace lines 225-227:

```python
    runs = load_runs(cache)
    if not runs:
        sys.exit("No running activities found in the cache. Run fetch_garmin.py first.")
```

with:

```python
    garmin_runs = load_runs(cache)
    strava_runs = load_strava(cache)
    runs = merge_runs(garmin_runs, strava_runs)
    if not runs:
        sys.exit("No running activities found. Run fetch_garmin.py and/or ingest "
                 "Strava via the MCP (see CLAUDE.md).")
    dups = len(garmin_runs) + len(strava_runs) - len(runs)
    print(f"  · sources: {len(garmin_runs)} Garmin + {len(strava_runs)} Strava, "
          f"{dups} dups → {len(runs)} runs")
```

- [ ] **Step 3: Verify generate still runs on the existing cache**

Run: `. .venv/bin/activate && python generate.py`
Expected: prints the new `· sources: N Garmin + 0 Strava, 0 dups → N runs` line (0 Strava when no `cache/strava/` exists), then the usual home/country/pins output; `index.html` regenerates without error.

- [ ] **Step 4: Run the full test suite**

Run: `pytest -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add generate.py
git commit -m "feat: merge Garmin + Strava sources in generate.py"
```

---

## Task 5: Document Strava ingestion in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (Ground rules section ~line 12; First-run playbook step 1 ~line 51)

- [ ] **Step 1: Add a Strava ground-rule line**

In the "Ground rules" list, after the GitHub Pages privacy bullet (~line 16), add:

```markdown
- **Strava data is just as personal as Garmin's** (GPS, routine). The same
  public-on-deploy warning applies. Strava is read **only via the Strava MCP**
  (read-only, account-scoped) — never ask for a Strava password.
```

- [ ] **Step 2: Add an optional Strava ingestion step**

After step 1 (the Garmin fetch block, ~line 59), insert a new sub-step:

```markdown
**1b. (optional) Strava — only if a Strava MCP is connected.** Use it when the
runner has more history in Strava than Garmin, or no Garmin at all. Drive it
through the connected Strava MCP (read-only):
- list the athlete's activities (paginate); keep type `Run`;
- for each activity **not already in `cache/strava/manifest.json`**, fetch its
  summary + streams (`latlng`, `heartrate`, `time`, `altitude`) and write a
  normalized `cache/strava/<id>.json`:
  ```json
  {"id":"strava-<id>","name":"...","start_time":"<UTC ISO8601>",
   "utc_offset_h":2,"distance_km":8.42,"duration_s":2715,
   "avg_hr":154,"max_hr":178,"ascent_m":63,
   "latlng":[[lat,lon],...],"hr":[bpm,...]}
  ```
  then record `{id:{name,start_time}}` in `cache/strava/manifest.json` so re-runs
  only fetch new activities.
- `generate.py` merges Garmin + Strava automatically and **deduplicates** runs
  that appear in both (matched by start time ±5 min + distance), preferring the
  Garmin original. Nothing else to do — just run `python generate.py`.
- If no Strava MCP is connected, skip this; everything stays Garmin-only.
```

- [ ] **Step 3: Verify the doc reads correctly**

Run: `grep -n "Strava" CLAUDE.md`
Expected: the new ground-rule line and the `1b.` block appear.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document optional Strava ingestion via MCP in the playbook"
```

---

## Self-Review (completed by plan author)

- **Spec coverage:** `source` field (T1), Strava ingestion doc (T5), `lib_strava` loader (T2), `lib_merge` dedup with ±5 min/5% + Garmin preference (T3), one-line `generate.py` integration + report (T4), graceful error handling (T2/T3/T4 — empty dir, missing streams, no-cache exit), pytest for merge + loader (T2/T3). All spec sections map to a task.
- **Placeholder scan:** none — every code/doc step shows full content.
- **Type consistency:** `Run` field `source` (T1) used by `load_strava` (T2) and `merge_runs` (T3/T4); `load_strava`/`merge_runs` signatures match their `generate.py` call (T4). `cache/strava/` schema in T2 test, T5 doc, and `lib_strava._read_one` agree (id, start_time, utc_offset_h, distance_km, duration_s, avg_hr, max_hr, ascent_m, latlng, hr).
