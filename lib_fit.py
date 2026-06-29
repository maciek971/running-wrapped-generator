#!/usr/bin/env python3
"""Minimal, self-contained FIT reader — no external toolkit needed.

Reads a Garmin FIT cache (`<cache>/fit/<id>.fit` + optional `<cache>/manifest.json`
for names) into plain Run objects. Only the fields the Wrapped needs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from garmin_fit_sdk import Decoder, Stream

_SC = 180.0 / 2 ** 31          # FIT semicircles -> degrees
_FIT_EPOCH = 631065600         # 1989-12-31 in unix seconds


@dataclass
class Run:
    id: str
    name: str | None
    start_time: datetime          # UTC
    local_offset_h: int           # wall-clock offset (e.g. +2)
    distance_km: float
    duration_s: float
    avg_hr: int | None
    max_hr: int | None
    ascent_m: float
    start: tuple[float, float] | None   # (lat, lon) of first GPS fix
    track: list[tuple[float, float]] = field(default_factory=list)
    hr_samples: list[int] = field(default_factory=list)  # per-record HR, for zone time


def _local_offset(msgs) -> int:
    act = (msgs.get("activity_mesgs") or [{}])[0]
    ts, lts = act.get("timestamp"), act.get("local_timestamp")
    if ts is None or lts is None:
        return 1
    ts_fit = ts.replace(tzinfo=timezone.utc).timestamp() - _FIT_EPOCH
    return round((lts - ts_fit) / 3600)


def _read_one(path: Path, name: str | None, *, track_step: int) -> Run | None:
    try:
        msgs, _ = Decoder(Stream.from_file(str(path))).read()
    except Exception:
        return None
    sess = (msgs.get("session_mesgs") or [{}])[0]
    if (sess.get("sport") or "").lower() != "running":
        return None
    dist_km = (sess.get("total_distance") or 0) / 1000.0
    dur_s = sess.get("total_timer_time") or sess.get("total_elapsed_time") or 0
    st = sess.get("start_time")
    if not st or dist_km < 1.0:
        return None
    start_time = st.replace(tzinfo=timezone.utc) if st.tzinfo is None else st.astimezone(timezone.utc)

    start = None
    track: list[tuple[float, float]] = []
    hr_samples: list[int] = []
    recs = msgs.get("record_mesgs", [])
    for i, rec in enumerate(recs):
        hr = rec.get("heart_rate")
        if hr:
            hr_samples.append(int(hr))
        la, lo = rec.get("position_lat"), rec.get("position_long")
        if la is None or lo is None:
            continue
        pt = (round(la * _SC, 5), round(lo * _SC, 5))
        if start is None:
            start = pt
        if i % track_step == 0:
            track.append(pt)

    return Run(
        id=path.stem,
        name=(name or None),
        start_time=start_time,
        local_offset_h=_local_offset(msgs),
        distance_km=dist_km,
        duration_s=float(dur_s),
        avg_hr=int(sess["avg_heart_rate"]) if sess.get("avg_heart_rate") else None,
        max_hr=int(sess["max_heart_rate"]) if sess.get("max_heart_rate") else None,
        ascent_m=float(sess.get("total_ascent") or 0),
        start=start,
        track=track,
        hr_samples=hr_samples,
    )


def load_runs(cache_dir: Path, *, track_step: int = 3) -> list[Run]:
    """Load all running activities (>=1 km) from a FIT cache, newest names from manifest."""
    cache_dir = Path(cache_dir)
    fit_dir = cache_dir / "fit"
    names: dict[str, str] = {}
    manifest = cache_dir / "manifest.json"
    if manifest.exists():
        man = json.loads(manifest.read_text())
        names = {aid: (m.get("name") or "") for aid, m in man.items()}
    runs: list[Run] = []
    for fp in sorted(fit_dir.glob("*.fit")):
        r = _read_one(fp, names.get(fp.stem), track_step=track_step)
        if r and r.start_time:
            runs.append(r)
    runs.sort(key=lambda r: r.start_time)
    return runs
