#!/usr/bin/env python3
"""Fetch air temperature for every run into <cache>/weather.json (optional).

generate.py reads this file for the folklore chapter (temperature as a control
variable); without it that chapter just runs without weather. The build itself
never calls the network -- only this script does (Open-Meteo archive, no key).

Why not use the temperature Garmin already records: that sensor sits against warm
skin and reads 8-13 C above air temperature (measured on 8 runs, median +10.7 C).
Mixing it with a real weather source would put an ~11 C step change into the data
exactly where the device changed, and any model would read that artefact as weather.

So: one consistent source for all runs. Runs are grouped by 0.1-degree cell
(~11 km) so a home city is one request per date span, not one per run, and the
stored coordinates stay coarse enough not to point at a front door.

Re-runnable: keeps whatever is already in weather.json and only fetches what is
missing, so an interrupted run costs nothing.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import timedelta, timezone
from pathlib import Path

from lib_fit import load_runs
from lib_merge import merge_runs
from lib_strava import load_strava

HERE = Path(__file__).resolve().parent
API = "https://archive-api.open-meteo.com/v1/archive"
GRID = 1          # decimal places for the location cell -> ~11 km
RETRIES = 4
PAUSE_S = 1.0     # be a polite guest on a free service


def fetch(lat, lon, start, end, attempt=1):
    url = (f"{API}?latitude={lat}&longitude={lon}&start_date={start}&end_date={end}"
           f"&hourly=temperature_2m&timezone=UTC")
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.load(r)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        if attempt >= RETRIES:
            raise
        wait = 2 ** attempt
        print(f"    ! {type(e).__name__} — retrying in {wait}s ({attempt}/{RETRIES - 1})")
        time.sleep(wait)
        return fetch(lat, lon, start, end, attempt + 1)


def cells_to_fetch(runs, have):
    """Runs still missing a temperature, grouped by coarse location cell."""
    cells = defaultdict(list)
    for r in runs:
        if r.id not in have and r.start:
            cells[(round(r.start[0], GRID), round(r.start[1], GRID))].append(r)
    return cells


def match_hours(rs, hourly, lat, lon):
    """{run id: {temp_c, lat, lon}} for runs whose start hour (UTC) the archive covers."""
    out = {}
    for r in rs:
        key = r.start_time.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:00")
        if hourly.get(key) is not None:
            out[r.id] = {"temp_c": hourly[key], "lat": lat, "lon": lon}
    return out


def main():
    cfg = json.loads((HERE / "me.json").read_text()) if (HERE / "me.json").exists() else {}
    cache = Path(os.getenv("WRAPPED_CACHE") or cfg.get("cache_dir") or (HERE / "cache"))
    out_path = cache / "weather.json"
    runs = merge_runs(load_runs(cache), load_strava(cache))
    have = json.loads(out_path.read_text()) if out_path.exists() else {}
    cells = cells_to_fetch(runs, have)
    todo = sum(len(rs) for rs in cells.values())
    no_gps = sum(1 for r in runs if not r.start)
    print(f"{len(runs)} runs · {len(have)} already cached · {todo} to fetch"
          + (f" · {no_gps} without GPS (skipped)" if no_gps else ""))
    if not todo:
        print("Nothing to do.")
        return

    print(f"{len(cells)} location cells → that many requests\n")
    for i, ((lat, lon), rs) in enumerate(sorted(cells.items(), key=lambda kv: -len(kv[1])), 1):
        days = sorted({r.start_time.date() for r in rs})
        start, end = days[0].isoformat(), days[-1].isoformat()
        print(f"[{i}/{len(cells)}] {lat},{lon} · {len(rs)} runs · {start}..{end}")
        data = fetch(lat, lon, start, end)
        got = match_hours(rs, dict(zip(data["hourly"]["time"], data["hourly"]["temperature_2m"])),
                          lat, lon)
        have.update(got)
        if len(got) < len(rs):
            print(f"    · {len(rs) - len(got)} with no reading for that hour")
        out_path.write_text(json.dumps(have, ensure_ascii=False, indent=1))  # save as we go
        time.sleep(PAUSE_S)

    temps = [v["temp_c"] for v in have.values()]
    print(f"\n✓ {out_path} — {len(have)} runs with temperature, "
          f"range {min(temps):.1f}..{max(temps):.1f} °C")
    by_month = defaultdict(list)
    for r in runs:
        if r.id in have:
            by_month[(r.start_time + timedelta(hours=r.local_offset_h)).month].append(
                have[r.id]["temp_c"])
    print("  median by month:",
          " ".join(f"{m}:{sorted(v)[len(v) // 2]:.0f}°" for m, v in sorted(by_month.items())))


if __name__ == "__main__":
    sys.exit(main())
