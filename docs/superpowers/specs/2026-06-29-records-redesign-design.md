# Records section — visual redesign + official Garmin records & predictions

**Date:** 2026-06-29
**Status:** Approved design (iterated visually with the user, layout v3), ready for plan

## Goal

The "rekordy / Tablica chwały" section (chapter 9) currently renders 8 visually
identical cards — a flat grid with no hierarchy. Redesign it into a narrative,
hierarchical layout (approved mockup "v3"), and upgrade the **content** with
Garmin's **official** personal records and race-fitness predictions instead of the
current distance-bucket approximations.

## Two parts

### A. Content — official Garmin data
Today `generate.py` derives `best_5k`/`best_10k` by bucketing FIT runs into
distance windows (4.8–5.2 km, 9.5–10.5 km) — approximate, missing 1K / mile /
half, and sometimes wrong. Garmin exposes the real data via two
`garminconnect` methods (passwordless via cached tokens, same as the rest of
`fetch_garmin.py`; the MCP is an equivalent alternative):

- `get_personal_record()` → official PRs. Running ones by `type_id`:
  `1`=1K, `2`=mile, `3`=5K, `4`=10K, `5`=half marathon, `7`=longest run.
  (Cycling/swim/steps records are ignored.)
- `get_race_predictions()` → predicted times for `5K`, `10K`, `half_marathon`,
  `marathon` based on current fitness/VO₂max.

Real sample (this dev account): PRs 1K 4:19, mile 7:19, 5K 25:36, 10K 52:44,
HM 1:54:25, longest 22.09 km; predictions 5K 23:56, 10K 50:51, HM 1:53:16,
marathon 4:08:57.

`get_personal_record` returns `activity_id` but `date: null`, so PR dates are not
available from this call — the section does not show PR dates (the **hero**,
which does show a date+name, keeps using the FIT-derived `longest`).

### B. Visual — layout v3 (approved)
Top-to-bottom, all in the existing wrapped theme (Anton numerals, warm
`--a1/--a2/--a3` gradient on accents only, `--ink2` tiles, `--line` borders):

1. **Hero** — full-width tile, gradient hairline on top: "Najdłuższy bieg",
   FIT-derived (big gradient km + run name + date). Route icon.
2. **Race PRs (primary)** — 3 tiles (5K / 10K / ½): big PR time (Anton) + pace
   under it + a **secondary prediction line** below a divider showing today's
   predicted time, a **trend icon**, the delta vs PR, and an explicit
   **"prognoza"** marker so it is never mistaken for an actual result.
   The delta communicates progress: a faster prediction than the PR means current
   fitness exceeds the PR-day fitness → a new PR is "in the legs".
3. **Sprint PRs (secondary)** — 2 compact tiles (1K / mile): PR + pace only
   (no Garmin prediction exists for these).
4. **Next goal** — one slim dashed bar: "Następny cel wg Twojej formy — maraton
   <predicted>" (Garmin predicts a marathon time although there is no marathon PR;
   aspirational, deliberately understated).
5. **Supporting stats** — trio: Łącznie (km + runs), Rekordowy tydzień,
   Najszybszy rok (kept from the current data, restyled).

## Architecture / data flow

```
fetch_garmin.py ──(garminconnect: get_personal_record + get_race_predictions)──→ cache/records.json
cache/records.json ─┐
FIT-derived stats  ─┴─ generate.py: build_records_block() ──→ data.json["records"] ──→ template.html (v3 section)
```

### `cache/records.json` (normalized, written by fetch_garmin.py)
```json
{
  "personal_records": {
    "1k":   {"seconds": 259.97},
    "mile": {"seconds": 439.66},
    "5k":   {"seconds": 1536.74},
    "10k":  {"seconds": 3164.93},
    "half": {"seconds": 6865.71},
    "longest_run_km": 22.09
  },
  "predictions": {
    "5k": {"seconds": 1436}, "10k": {"seconds": 3051},
    "half": {"seconds": 6796}, "marathon": {"seconds": 14937}
  }
}
```
Only running `type_id`s are mapped; anything missing is simply omitted.

### `build_records_block(records_json, longest, fallback_5k, fallback_10k, lifetime, peak_week, fastest_year)` — pure function in generate.py
Produces the model `template.html` consumes. Responsibilities:
- Format seconds → `m:ss` / `h:mm:ss` (truncated, matching Garmin).
- Compute pace `seconds / distance_km` per PR (distances: 1, 1.609, 5, 10, 21.0975).
- Compute delta `pr.seconds - prediction.seconds` for 5K/10K/half (positive =
  prediction faster = progress); flag `faster: bool`.
- Marathon: prediction only (no PR) → the "next goal" item.
- Keep `longest` (FIT), `lifetime`, `peak_week`, `best_month`, `fastest_year`.

This function is **pure and unit-tested** (no I/O), so the formatting/pace/delta
logic is verified without Garmin.

## Fallbacks (graceful, no new hard failures)
- **No `cache/records.json`** (user never fetched PRs / MCP-less): fall back to the
  current derived `best_5k`/`best_10k`; hide 1K/mile/half tiles that have no data;
  hide all prediction lines and the marathon "next goal" bar. The section still
  renders with whatever exists.
- **PRs present, predictions absent:** show PR tiles without the prediction line;
  omit the marathon bar.
- **A given distance missing:** omit just that tile.
- Hero (`longest`) is always present (FIT-derived), so the section is never empty.

## Files
- `fetch_garmin.py` — after the activity download, call `get_personal_record()` +
  `get_race_predictions()`, normalize to `cache/records.json` (best-effort: wrap in
  try/except, a failure just skips the file — never blocks the activity fetch).
- `generate.py` — add `build_records_block(...)` (pure), read `cache/records.json`,
  feed `data.json["records"]`. Keep derived `best_5k/10k` as fallback inputs.
- `template.html` — replace the records `<section>` markup + the records JS builder
  + add CSS for the v3 layout (hero / primary race tiles with prediction line /
  sprint tiles / next-goal bar / supporting trio). Respect `prefers-reduced-motion`,
  keep contrast ≥ 4.5:1. Icons (route / trend / target) are **inline SVG** — the
  page stays self-contained, no new icon-font/CDN dependency. The mockup used the
  Tabler font only because the preview tool ships it.
- `CLAUDE.md` — note that `fetch_garmin.py` now also pulls official PRs + race
  predictions (and the MCP equivalent), and that the records section uses them.
- `tests/test_records.py` — unit tests for `build_records_block` (formatting,
  pace, delta sign/`faster`, marathon-only, and each fallback path).

## Out of scope
VO₂max trend, endurance/hill score, steps records — available but not part of this
section; can be a later chapter.
