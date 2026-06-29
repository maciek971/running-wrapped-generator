#!/usr/bin/env python3
"""Download your Garmin activities into ./cache (incremental).

Auth uses your own Garmin login — YOU type it (or set GARMIN_EMAIL / GARMIN_PASSWORD).
Tokens are cached in ~/.garminconnect so later runs need no password.

If you drive this from Claude Code and have a Garmin MCP connected, Claude can
instead populate ./cache/fit/<id>.fit + ./cache/manifest.json via the MCP — this
script is the no-MCP fallback.
"""
from __future__ import annotations

import getpass
import io
import json
import os
import sys
import zipfile
from pathlib import Path

from garmin_records import normalize_records

HERE = Path(__file__).resolve().parent
CACHE = Path(os.getenv("WRAPPED_CACHE") or (HERE / "cache"))
TOKENS = os.path.expanduser("~/.garminconnect")


def _login():
    try:
        from garminconnect import Garmin
    except ImportError:
        sys.exit("Missing dependency. Run:  pip install -r requirements.txt")
    try:
        g = Garmin()
        g.login(TOKENS)                       # reuse saved tokens
        return g
    except Exception:
        email = os.getenv("GARMIN_EMAIL") or input("Garmin e-mail: ").strip()
        pwd = os.getenv("GARMIN_PASSWORD") or getpass.getpass("Garmin password: ")
        g = Garmin(email, pwd)
        g.login()
        try:
            g.garth.dump(TOKENS)
        except Exception:
            pass
        return g


def _deep_find(obj, pred):
    """First value in a nested dict/list for which pred(key, value) is True (DFS)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if pred(k, v):
                return v
        for v in obj.values():
            r = _deep_find(v, pred)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _deep_find(v, pred)
            if r is not None:
                return r
    return None


def profile_defaults(g) -> dict:
    """Best-effort: pull birth_year + resting_hr from the Garmin profile so HR zones
    are fully data-driven. Anything not found is simply left for me.json / the user."""
    import datetime as _dt
    out: dict = {}
    # birth year
    for getter in ("get_userprofile_settings", "get_user_profile"):
        try:
            prof = getattr(g, getter)()
        except Exception:
            continue
        bd = _deep_find(prof, lambda k, v: k.lower() in ("birthdate", "birthday", "dateofbirth")
                        and isinstance(v, str) and v[:4].isdigit())
        if bd:
            out["birth_year"] = int(bd[:4])
            break
    # resting HR — newest of the last week
    for back in range(0, 8):
        day = (_dt.date.today() - _dt.timedelta(days=back)).isoformat()
        for getter in ("get_user_summary", "get_rhr_day"):
            try:
                r = getattr(g, getter)(day)
            except Exception:
                continue
            rhr = _deep_find(r, lambda k, v: "restingheartrate" in k.lower()
                             and isinstance(v, (int, float)) and 25 <= v <= 120)
            if rhr:
                out["resting_hr"] = int(rhr)
                break
        if "resting_hr" in out:
            break
    return out


def _merge_me_json(found: dict):
    """Write Garmin-derived defaults into me.json without clobbering user values."""
    me = HERE / "me.json"
    cfg = json.loads(me.read_text()) if me.exists() else {}
    added = {}
    for k, v in found.items():
        if cfg.get(k) in (None, "", 0):   # only fill what the user hasn't set
            cfg[k] = v
            added[k] = v
    cfg.setdefault("lang", "pl")
    me.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
    if added:
        print(f"  · from Garmin profile → {added}")
    return cfg


def _save_records(g):
    """Best-effort: pull official PRs + race predictions into cache/records.json.
    A failure here must never block the activity download."""
    try:
        prs = g.get_personal_record()
    except Exception:
        prs = None
    try:
        preds = g.get_race_predictions()
    except Exception:
        preds = None
    rec = normalize_records(prs, preds)
    if rec["personal_records"] or rec["predictions"]:
        (CACHE / "records.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        print(f"  · Garmin records → {len(rec['personal_records'])} PR, "
              f"{len(rec['predictions'])} predictions")


def main():
    from garminconnect import Garmin

    fit = CACHE / "fit"
    fit.mkdir(parents=True, exist_ok=True)
    man_path = CACHE / "manifest.json"
    manifest = json.loads(man_path.read_text()) if man_path.exists() else {}

    g = _login()
    _merge_me_json(profile_defaults(g))   # birth year + resting HR for HR zones
    _save_records(g)                      # official PRs + race predictions

    summaries, start = [], 0
    while True:
        batch = g.get_activities(start, 100)
        if not batch:
            break
        summaries += batch
        if len(batch) < 100:
            break
        start += 100

    todo = [a for a in summaries if str(a["activityId"]) not in manifest]
    print(f"{len(summaries)} activities; {len(todo)} new to download.")
    for i, a in enumerate(todo, 1):
        aid = str(a["activityId"])
        try:
            blob = g.download_activity(aid, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                fits = [n for n in z.namelist() if n.lower().endswith(".fit")]
                if not fits:
                    continue
                (fit / f"{aid}.fit").write_bytes(z.read(fits[0]))
            manifest[aid] = {"fit_file": f"{aid}.fit",
                             "name": a.get("activityName") or "",
                             "start_time": a.get("startTimeGMT", "")}
            man_path.write_text(json.dumps(manifest, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {aid}: {exc}")
        if i % 25 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}")
    print(f"✓ cache ready at {CACHE} ({len(manifest)} activities)")


if __name__ == "__main__":
    main()
