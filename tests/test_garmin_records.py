from garmin_records import normalize_records

PRS = [
    {"typeId": 1, "value": 259.97, "activityType": "running"},
    {"typeId": 3, "value": 1536.74, "activityType": "running"},
    {"typeId": 7, "value": 22085.94, "activityType": "running"},
    {"typeId": 8, "value": 28671.0, "activityType": "cycling"},
    {"typeId": 18, "value": 130.0, "activityType": "swimming"},
]
PREDS = {"time5K": 1436, "time10K": 3051, "timeHalfMarathon": 6796, "timeMarathon": 14937}


def test_maps_running_prs_by_typeid():
    out = normalize_records(PRS, PREDS)
    assert out["personal_records"]["1k"] == {"seconds": 259.97}
    assert out["personal_records"]["5k"] == {"seconds": 1536.74}
    assert out["personal_records"]["longest_run_km"] == 22.09


def test_ignores_non_running_prs():
    out = normalize_records(PRS, PREDS)
    pr = out["personal_records"]
    assert "mile" not in pr            # typeId 2 not in input
    assert all(k not in pr for k in ("ride", "swim"))
    assert set(pr) <= {"1k", "mile", "5k", "10k", "half", "longest_run_km"}


def test_maps_predictions():
    out = normalize_records(PRS, PREDS)
    assert out["predictions"] == {
        "5k": {"seconds": 1436}, "10k": {"seconds": 3051},
        "half": {"seconds": 6796}, "marathon": {"seconds": 14937},
    }


def test_handles_empty_inputs():
    assert normalize_records(None, None) == {"personal_records": {}, "predictions": {}}
    assert normalize_records([], {}) == {"personal_records": {}, "predictions": {}}
