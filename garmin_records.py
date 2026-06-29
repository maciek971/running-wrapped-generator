#!/usr/bin/env python3
"""Normalize Garmin official personal records + race predictions into the
`cache/records.json` shape the generator reads. Pure — no network, no I/O —
so it is testable without Garmin and reusable from an MCP-driven path.

Raw inputs come from `garminconnect`:
- get_personal_record() -> list of {"typeId", "value", ...}; running typeIds:
  1=1K, 2=mile, 3=5K, 4=10K, 5=half, 7=longest run. `value` is seconds for
  times, metres for the longest-run distance.
- get_race_predictions() -> {"time5K", "time10K", "timeHalfMarathon",
  "timeMarathon"} in seconds.
"""
from __future__ import annotations

_PR_KEYS = {1: "1k", 2: "mile", 3: "5k", 4: "10k", 5: "half", 7: "longest"}
_PRED_KEYS = {"5k": "time5K", "10k": "time10K", "half": "timeHalfMarathon",
              "marathon": "timeMarathon"}


def normalize_records(prs, preds) -> dict:
    out: dict = {"personal_records": {}, "predictions": {}}
    for p in (prs or []):
        key = _PR_KEYS.get(p.get("typeId"))
        val = p.get("value")
        if not key or val is None:
            continue
        if key == "longest":
            out["personal_records"]["longest_run_km"] = round(val / 1000, 2)
        else:
            out["personal_records"][key] = {"seconds": round(val, 2)}
    for key, src in _PRED_KEYS.items():
        v = (preds or {}).get(src)
        if v:
            out["predictions"][key] = {"seconds": int(v)}
    return out
