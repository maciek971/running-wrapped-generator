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
    activity_id = str(data.get("id") or "")
    dist_km = float(data.get("distance_km") or 0)
    st = data.get("start_time")
    if not activity_id or dist_km < 1.0 or not st:
        return None
    start_time = datetime.fromisoformat(st.replace("Z", "+00:00")).astimezone(timezone.utc)

    latlng = data.get("latlng") or []
    track = [(round(float(la), 5), round(float(lo), 5))
             for i, (la, lo) in enumerate(latlng) if i % track_step == 0]
    start = (round(float(latlng[0][0]), 5), round(float(latlng[0][1]), 5)) if latlng else None
    hr_samples = [int(h) for h in (data.get("hr") or []) if h]

    return Run(
        id=activity_id,
        name=(data.get("name") or None),
        start_time=start_time,
        local_offset_h=int(data["utc_offset_h"]) if data.get("utc_offset_h") is not None else 1,
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
            r = _read_one(data, track_step=track_step)
        except Exception:
            continue
        if r and r.start_time:
            runs.append(r)
    runs.sort(key=lambda r: r.start_time)
    return runs
