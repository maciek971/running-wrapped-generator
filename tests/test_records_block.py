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
    assert keys == ["5k", "10k"]
    assert all(r["pred"] is None for r in b["race"])
    assert b["sprint"] == []
    assert b["marathon"] is None
    assert b["longest"] == LONGEST


def test_predictions_present_but_no_pr_for_distance():
    rec = {"personal_records": {"5k": {"seconds": 1536.74}},
           "predictions": {"10k": {"seconds": 3051}}}
    b = build_records_block(rec_json=rec, longest=LONGEST, totals=TOTALS,
                            peak_week=PEAK, fastest_year=FASTEST,
                            fallback_5k=None, fallback_10k=None)
    five = next(r for r in b["race"] if r["key"] == "5k")
    assert five["pred"] is None
    assert all(r["key"] != "10k" for r in b["race"])
