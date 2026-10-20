from datetime import datetime

import backfill_weather
from lib_fit import Run


def run(rid, start, when):
    return Run(id=rid, name=None, start_time=when, local_offset_h=2, distance_km=5,
               duration_s=1800, avg_hr=None, max_hr=None, ascent_m=0, start=start)


def test_only_missing_runs_with_gps_are_fetched_grouped_by_coarse_cell():
    runs = [run('a', (51.1081, 17.0385), datetime(2026, 6, 1, 6, 10)),
            run('b', (51.1349, 17.0412), datetime(2026, 6, 2, 6, 10)),   # same ~11 km cell
            run('c', (50.7713, 16.2843), datetime(2026, 6, 3, 6, 10)),
            run('d', None, datetime(2026, 6, 4, 6, 10)),                 # no GPS
            run('e', (50.7713, 16.2843), datetime(2026, 6, 5, 6, 10))]   # already cached
    cells = backfill_weather.cells_to_fetch(runs, {'e': {'temp_c': 20}})
    assert {cell: [r.id for r in rs] for cell, rs in cells.items()} == {
        (51.1, 17.0): ['a', 'b'], (50.8, 16.3): ['c']}


def test_runs_take_the_reading_of_their_utc_start_hour():
    rs = [run('a', (51.1, 17.0), datetime(2026, 6, 1, 6, 59)),
          run('b', (51.1, 17.0), datetime(2026, 6, 1, 9, 0))]
    got = backfill_weather.match_hours(rs, {'2026-06-01T06:00': 14.5, '2026-06-01T09:00': None},
                                       51.1, 17.0)
    assert got == {'a': {'temp_c': 14.5, 'lat': 51.1, 'lon': 17.0}}
