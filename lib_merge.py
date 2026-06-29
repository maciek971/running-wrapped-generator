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
        match = next((g for g in garmin if _same_run(g, s)), None)   # match only against Garmin
        if match is None:
            merged.append(s)
        elif not match.track and s.track:
            merged[merged.index(match)] = s
        # else: duplicate, keep existing (Garmin) record
    merged.sort(key=lambda r: r.start_time)
    return merged
