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


def test_load_strava_skips_corrupt_json(tmp_path):
    sdir = tmp_path / "strava"
    sdir.mkdir()
    (sdir / "bad.json").write_text("{truncated")
    assert load_strava(tmp_path) == []


def test_load_strava_skips_non_dict_content(tmp_path):
    sdir = tmp_path / "strava"
    sdir.mkdir()
    (sdir / "arr.json").write_text(json.dumps([1, 2, 3]))
    assert load_strava(tmp_path) == []


def test_load_strava_preserves_utc_zero(tmp_path):
    sdir = tmp_path / "strava"
    sdir.mkdir()
    (sdir / "u.json").write_text(json.dumps({**SAMPLE, "utc_offset_h": 0}))
    assert load_strava(tmp_path)[0].local_offset_h == 0
