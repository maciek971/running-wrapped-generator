from lib_insights import _record_insights

REC = {
    "longest": {"km": 22.09, "date": "2024-10-12", "name": "Półmaraton Wrocław"},
    "race": [
        {"key": "5k", "label": "5 km", "time": "25:36", "pace": "5:07",
         "pred": {"time": "23:56", "delta": "1:40", "faster": True}},
        {"key": "10k", "label": "10 km", "time": "52:44", "pace": "5:16",
         "pred": {"time": "50:51", "delta": "1:53", "faster": True}},
        {"key": "half", "label": "½ maraton", "time": "1:54:25", "pace": "5:25", "pred": None},
    ],
    "marathon": {"time": "4:08:57"},
}


def _by_id(rec):
    return {row[0]: row for row in _record_insights(rec)}


def test_race_insight_with_faster_prediction():
    note = _by_id(REC)["pr_5k"][2]
    assert note == "Rekord 5 km: 25:36 (5:07/km) · prognoza 23:56 (−1:40)."


def test_race_insight_without_prediction_omits_prognoza():
    note = _by_id(REC)["pr_half"][2]
    assert note == "Rekord ½ maraton: 1:54:25 (5:25/km)."
    assert "prognoza" not in note


def test_all_race_distances_emit_a_hook():
    ids = _by_id(REC)
    assert {"pr_5k", "pr_10k", "pr_half"} <= set(ids)


def test_slower_prediction_uses_plus_sign():
    rec = {"race": [{"key": "5k", "label": "5 km", "time": "25:00", "pace": "5:00",
                     "pred": {"time": "26:00", "delta": "1:00", "faster": False}}]}
    assert _by_id(rec)["pr_5k"][2] == "Rekord 5 km: 25:00 (5:00/km) · prognoza 26:00 (+1:00)."


def test_marathon_prediction_hook_present():
    assert "marathon_pred" in _by_id(REC)


def test_race_notes_never_leak_a_none_date():
    for _id, _score, note, _nums in _record_insights(REC):
        if _id.startswith("pr_"):
            assert "None" not in note


def test_empty_records_yields_nothing():
    assert _record_insights({}) == []
