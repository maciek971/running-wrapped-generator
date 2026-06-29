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
