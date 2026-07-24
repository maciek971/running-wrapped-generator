# 🏃 Running Wrapped — generator

Turn your **Garmin running history** into a personal, Spotify-Wrapped-style web page —
a 12-chapter story of you as a runner (volume over the years, where you run on a real
map, your hours, heart-rate zones, records, and some fun stuff). Home city, country
and the map are detected automatically from your GPS — it works for anyone, anywhere.

It's built to be driven by **Claude Code**: clone, open in Claude Code, ask for your
Wrapped, and it walks you through login, your colors, and a story tailored to your data.

## Quick start (with Claude Code)
1. `git clone <this repo>` and open the folder in Claude Code.
2. Say: **„Zrób mój Running Wrapped"** (or "build my Running Wrapped").
3. Claude follows [`CLAUDE.md`](CLAUDE.md): sets up, gets your Garmin data (you type your
   own login), asks your **favourite colours** and restyles, **rewrites the story** to
   fit your data, and produces `index.html`. Optionally publishes it to your GitHub Pages.

## Manual use (without Claude)
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python fetch_garmin.py              # type your Garmin login (once); auto-writes
                                    # birth year + resting HR into me.json
python generate.py                  # -> index.html
open index.html
```
Or just `./make.sh` (fetch + generate). Re-run anytime to refresh.

## Auto-refresh (advanced, optional)
Want a page that **updates itself daily** from Garmin, with no local machine involved? See
[`docs/auto-refresh.md`](docs/auto-refresh.md) for the self-hosting pattern: a private repo
holds your data + a GitHub Actions workflow, pulls this engine fresh each day, and publishes
only `index.html` to a public Pages repo (raw GPS stays private). A ready-to-copy workflow is
in [`examples/github-actions/daily-refresh.yml`](examples/github-actions/daily-refresh.yml).

## Config (`me.json`)
Copy `me.example.json` → `me.json`. `birth_year` + `resting_hr` are auto-filled from your
Garmin profile on the first fetch, so the minimal config is just `lang` / `source`.

**Heart-rate zones** default to a **Karvonen estimate** (from your max + resting HR) — this
works out of the box, nothing to set. If you *know* your real numbers (e.g. a chest-strap
max, or the zones you set in Garmin), add the optional fields below for accurate zones;
otherwise leave them out and you'll get the auto-estimate (`generate.py` prints which mode
it used on every run, so you always know):

```jsonc
{
  "lang": "pl",            // page language
  "home_city": null,       // null = auto-detected from GPS
  "source": "both",        // "garmin" | "strava" | "both"
  "birth_year": 1986,      // auto-filled from Garmin if omitted
  "resting_hr": 51,        // auto-filled from Garmin if omitted

  // --- optional: your OWN heart-rate zones (omit both for the auto estimate) ---
  "hr_max": 188,               // your true max HR, overrides the observed/age estimate
  "hr_zones": [133, 148, 161, 172]  // lower bpm bounds for Z2,Z3,Z4,Z5 (Z1 is below the first)
}
```
> `me.json` is JSON — the `//` comments above are just for illustration, remove them in your file.

## What it never does
- It never asks Claude to type your Garmin password — **you** authenticate.
- Your data stays local. Publishing to GitHub Pages is optional and makes the page
  **public** (it exposes home-area routes), so it's opt-in and uses an unguessable URL.

## Files
| file | role |
|------|------|
| `template.html` | the page — theme colours (`:root`) + all the prose. Edit here. |
| `generate.py` | FIT cache + `me.json` → `data.json` → inlined `index.html` |
| `lib_fit.py` | minimal self-contained FIT reader |
| `geo.py` + `assets/world_countries.geo.json` | offline country detection + outlines |
| `fetch_garmin.py` | download your activities into `./cache/` (garminconnect) |
| `me.json` | your config (birth year, language, optional home-city override) |

Credit: data via [garminconnect](https://github.com/cyberjunky/python-garminconnect) +
[garmin-fit-sdk](https://github.com/garmin/fit-python-sdk); borders from
[Natural Earth](https://www.naturalearthdata.com/); maps © OpenStreetMap / CARTO.
