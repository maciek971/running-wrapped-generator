# Strava as a second data source (merge + dedup via MCP)

**Date:** 2026-06-29
**Status:** Approved design, ready for implementation plan

## Goal

Let the Running Wrapped generator build one person's page from **both** their
Garmin history and their **Strava** history, merged and deduplicated. Motivating
case: a runner whose Strava holds *more* activities than her Garmin (phone-tracked
runs, older history). Strava is read via the official **Strava MCP connector**
(per-second HR/pace streams + GPS coordinates, read-only, account-scoped).

The generation runs in the runner's **own** Claude Code, with her Strava MCP
connected and her own Garmin FIT cache present. No cross-account data movement.

## Non-goals

- No standalone `fetch_strava.py` hitting the Strava REST API — ingestion goes
  through the MCP (explicit requirement).
- No change to the Garmin FIT path, the theming, or the narrative flow.
- No merging of *different people* into one page.

## Architecture

The `Run` dataclass stays the single normalized shape. Garmin produces `Run`s
from FIT (`lib_fit.py`); Strava produces the same `Run`s from MCP stream data
(`lib_strava.py`); a merge step unions and dedupes them. `generate.py` changes by
one line.

```
Garmin FIT cache ─ lib_fit.load_runs ─┐
                                       ├─ lib_merge.merge_runs ─→ [Run] ─→ generate.py
cache/strava/*.json ─ lib_strava.load_strava ─┘
        ▲
   Claude + Strava MCP (ingestion, incremental)
```

### Components

**1. `Run.source` field** — add `source: str` (`"garmin"` | `"strava"`) to the
dataclass in `lib_fit.py`. Drives dedup preference and a one-line report. Nothing
downstream reads it, so it is additive and safe.

**2. Strava ingestion — Claude-driven via the MCP.** Mirrors the existing
"drive via a connected Garmin MCP" fallback already documented in CLAUDE.md. The
MCP only runs inside Claude, so this is a documented playbook procedure, not a
script. Claude:
- enumerates the athlete's activities (paginate, keep type `Run`);
- for each activity **not already cached**, pulls the summary (id, name, UTC
  start + `utc_offset`/timezone, distance, moving/elapsed time, total elevation
  gain, average + max heart rate) and streams (`latlng`, `heartrate`, `time`,
  `altitude`);
- writes a normalized `cache/strava/<id>.json` and updates
  `cache/strava/manifest.json` so re-runs only fetch new activities (incremental,
  like Garmin).

Normalized per-activity JSON schema (mirrors `Run` so the loader is trivial):
```json
{
  "id": "strava-<activity_id>",
  "name": "Morning Run",
  "start_time": "2025-06-01T05:32:11Z",
  "utc_offset_h": 2,
  "distance_km": 8.42,
  "duration_s": 2715,
  "avg_hr": 154,
  "max_hr": 178,
  "ascent_m": 63,
  "latlng": [[52.40, 16.91], ...],
  "hr": [120, 121, ...]
}
```

**3. `lib_strava.py` — loader.** Pure and offline: reads `cache/strava/*.json`
→ `Run` objects. Symmetric with `lib_fit.load_runs`:
- same filters: running, distance ≥ 1 km;
- same track subsampling (`track_step`, default 3);
- `local_offset_h` from `utc_offset_h`;
- `start` = first `latlng` point; `track` = subsampled `latlng`;
  `hr_samples` = `hr` stream;
- `source="strava"`.
Missing streams degrade gracefully (no GPS → `start=None`, no track; no HR →
`avg/max_hr=None`, empty `hr_samples`).

**4. `lib_merge.py` — `merge_runs(garmin, strava) -> list[Run]`.**
- **Match rule:** two runs are the same activity if start times are within
  **±5 minutes** AND distance within **5% (or ≤ 0.3 km absolute)**. Garmin
  auto-syncs to Strava with a near-identical start time, so this is safe and
  avoids false merges of genuinely distinct runs.
- **Preference on a match:** prefer **Garmin** (the device's original FIT
  recording) when its `Run` has a GPS track; otherwise keep whichever side has the
  track / HR. Strava-only runs (the extra history) pass straight through.
- Returns the deduplicated union, sorted by `start_time`.

**5. `generate.py`** — replace `runs = load_runs(cache)` with:
```python
runs = merge_runs(load_runs(cache), load_strava(cache))
```
plus a one-line report, e.g. `"42 Garmin + 88 Strava, 30 dups → 100 runs"`.
Broaden the "no activities" exit message to mention both sources.

**6. CLAUDE.md** — add Strava as an **optional** source in the first-run
playbook: if the Strava MCP is connected, ingest to `cache/strava/`; dedup is
automatic. Add one ground-rule line: Strava data is equally personal and becomes
public on deploy.

## Error handling

All graceful — no new hard-failure modes:
- Strava MCP not connected → `cache/strava/` empty → Garmin-only, silently.
- No Garmin cache → Strava-only works.
- Missing HR stream → zones path already tolerates `None`/empty.
- Treadmill / no GPS → excluded from the map (FIT path already handles `start=None`).

## Testing

This is the first branching logic in the repo, so introduce `pytest`:
- `merge_runs`: dedup window edges (just inside/outside ±5 min and the distance
  tolerance), Garmin-preferred-on-match, Strava-only passthrough, both-empty.
- `lib_strava`: parse a small fixture JSON → expected `Run` (track subsampling,
  local offset, missing-stream degradation).

The Garmin FIT path stays untouched.

## Files

- `lib_fit.py` — add `source` field to `Run` (set `source="garmin"`).
- `lib_strava.py` — **new** loader.
- `lib_merge.py` — **new** merge/dedup.
- `generate.py` — one-line integration + report + broadened error message.
- `CLAUDE.md` — Strava playbook step + ground rule.
- `tests/` — **new** pytest for merge + strava loader.
- `requirements.txt` — add `pytest` (dev).
