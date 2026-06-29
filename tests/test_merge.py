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
