# Running Wrapped — generator (instructions for Claude Code)

Turns a person's **Garmin running history** into one self-contained `index.html` — a
Spotify-Wrapped-style story of them as a runner. Home city, country and map are
**auto-detected from GPS**, so it works for anyone, anywhere.

When the user asks for their Running Wrapped, run the **First-run playbook** top to bottom.
Ask the question steps (4 colours, 5 story) **one at a time** — wait for answers.

## Ground rules (do not skip)
- **Never type the user's Garmin/Strava password yourself.** Garmin: they use a connected
  MCP or type their login into `fetch_garmin.py`. Strava: **read-only Strava MCP only**.
- **The data is personal** (home-area GPS, daily routine). Deploying to GitHub Pages makes it
  **public to anyone with the link** — confirm explicitly first.
- Keep everything in the user's language (default Polish; `me.json → lang`).

## First-run playbook
One-stop-shop: do the preflight yourself, only stop for a real choice or their own login.

> **`template.html` ships as a neutral scaffold** (generic colours/prose, `INITIALIZE`
> comment atop `<main>`). Steps **4 (colours)** and **5 (story)** are therefore **required** —
> the page isn't done until it's themed and authored for this specific runner.

**0. Preflight**
- **Python 3** (`python3 --version`) — if missing, tell them how to install it and stop.
- **Deps**: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`
  (surface + fix any pip error before continuing).
- **`gh`** — only for the optional deploy (step 7); if absent, note it and carry on.
- **Garmin access** = OAuth tokens in `~/.garminconnect`; once they exist everything is
  passwordless and `fetch_garmin.py` reuses them however they got there:
  - **Garmin MCP connected** (e.g. `Taxuspt/garmin_mcp`) → tokens already saved, step 1 just works.
  - **No MCP / no tokens** → step 1 asks their login once and saves them. Zero-setup default.
  - **Wants the Garmin MCP too** (optional) → needs [`uv`](https://docs.astral.sh/uv/); confirm, then:
    ```
    uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth   # login once
    claude mcp add garmin -- uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp
    ```
    (the auth step alone makes step 1 passwordless, even without registering the MCP.)

**1. Fetch Garmin data → `./cache/`** — `python fetch_garmin.py`. Reuses tokens, downloads new
activities incrementally, and auto-writes `birth_year` + `resting_hr` into `me.json` (they
drive HR zones). Also pulls official **personal records** + **race predictions** into
`cache/records.json` for the "Tablica chwały" section (best-effort; falls back to FIT-derived
records). Safe to re-run.
- *Garmin MCP alternative:* save each FIT to `cache/fit/<id>.fit` + a `cache/manifest.json` of
  `{id:{fit_file,name,start_time}}`, plus birth year/resting HR and `records.json` via
  `get_personal_record` + `get_race_predictions`. But `fetch_garmin.py` is faster — prefer it.

**1b. Strava (optional — only with a Strava MCP).** Use when the runner has more history in
Strava than Garmin, or no Garmin. Via the read-only Strava MCP: list activities (paginate,
keep `Run`); for each not in `cache/strava/manifest.json`, fetch summary + streams and write
`cache/strava/<id>.json`:
```json
{"id":"strava-<id>","name":"...","start_time":"<UTC ISO8601>",
 "utc_offset_h":2,"distance_km":8.42,"duration_s":2715,
 "avg_hr":154,"max_hr":178,"ascent_m":63,
 "latlng":[[lat,lon],...],"hr":[bpm,...]}
```
then record `{id:{name,start_time}}` in the manifest. `generate.py` merges + dedups Garmin/
Strava (start time ±5 min + distance, preferring Garmin) unless `source` pins one (step 2b).

**2. Config (`me.json`)** — mostly auto-filled in step 1. Set `lang` (default `pl`), leave
`home_city` `null` (auto-detected). Only ask for `birth_year`/`resting_hr` if step 1 couldn't
fetch them.
- **HR zones — ask once.** Zones default to a **Karvonen estimate** (works, no input). If the
  runner knows their real numbers, ask once: *"Znasz swoje realne tętno maksymalne / progi
  stref (np. z pasa albo ustawione w Garminie)? Jeśli tak — podaj; jeśli nie — policzę
  automatycznie."*
  - Given → set `"hr_max"` and/or `"hr_zones": [z2,z3,z4,z5]` (the four lower bpm thresholds).
  - Skipped → do nothing, and **say plainly**: *"Strefy policzę automatycznie (Karvonen);
    możesz je później podać w `me.json` przez `hr_max`/`hr_zones`."* (`generate.py` prints the
    mode each run, so the fallback is never silent.)

**2b. Data source** (`me.json → "source"`: `garmin`/`strava`/`both`, default `both` = merge +
dedup). Decide **before generating**: only Garmin → `garmin`; only Strava → `strava`; **both
available → ask** which to use. Re-runnable (switch value + re-`generate.py`, no refetch).

**3. Generate** — `python generate.py`. Prints detected `home`/`country`/`countries`/`pins`.
**Confirm the home city**; if wrong, set `home_city` in `me.json` and re-run.

**4. Colours — ask, then restyle.** Ask: *"Jakie kolory lubisz / jaki klimat? (np. ciepły
zachód słońca, chłodny błękit, neon…)"* Then edit the `:root` block in `template.html`:
- `--a1`/`--a2`/`--a3` — accent gradient (light→mid→deep); the signature look. Pick 3 harmonious stops.
- `--ink`/`--ink2` — page/card background (keep dark, or go light and also flip `--cream`/`--muted`/`--line`).
- `--cream` text · `--muted` secondary · `--line` borders.
Re-`generate.py`, open `index.html`, iterate. Keep text contrast ≥ 4.5:1.

**5. Story — author mode (this makes it personal; don't skip).** Default output is correct but
generic. Be the **author**, not a slot-filler. Inputs: `data.json` (numbers), `insights.json`
(ranked briefing of what's distinctive — hooks, events, their run titles), a short interview.
- **A. Interview** — ask 3–5, one at a time, in their language (skippable): *Dlaczego biegasz?
  Najmocniejsze wspomnienie? Cel na teraz? Jak się czuł ten rok (kontuzja/powrót/życiówka)?
  Jednym słowem — Twoje bieganie?* Their words carry the emotion the data can't.
- **B. Find the spine** — from top `insights` + answers, pick ONE through-line (not always
  "more km" — maybe the comeback, the 5 a.m. habit, the first race, the year abroad). Decide
  the **title/hero line**, **hero number**, **tone** (liryczny/zadziorny/rzeczowy/żartobliwy). Weave in their name.
- **C. Compose `template.html`** (restructure, don't just rewrite): **reorder** chapters
  (`style="order:N"`), **cut** irrelevant ones (`style="display:none"` — keep the inner `id`
  divs the JS fills), **retitle** kickers/headers, **rewrite** every `.lead`/`.edu`/outro
  around their hooks, **quote real run titles** from `insights`. Optional: a small bespoke section.
- **D. Rules** — keep their language; keep dynamic hooks (`[data-km="YEAR"]`, `<span id="…">`)
  so numbers stay live (place new ones if you move numbers); **don't invent facts** (only
  `data.json`/`insights.json` or what they told you); keep every chart's container `id`.
- **E.** Re-`generate.py`, read it back as if you were them, iterate until it's *their* story.

**6. Preview** — open `index.html` (maps need internet — Leaflet CDN). Check hero numbers,
year bars, the "gdzie" scene tabs (home/country/Świat), and the route-map carousel.

**7. Deploy (optional)** — only if they want it online and accept it's public: unguessable
public repo (e.g. `running-wrapped-$(openssl rand -hex 3)`), push **only `index.html`** with
their own `gh`. The template already has `<meta name="robots" content="noindex, nofollow">`.
Give them `https://<user>.github.io/<repo>/`.

## Refreshing later
`./make.sh` re-fetches + regenerates. Inline numbers/dates update themselves; only hand-written
year-specific *wording* may need a glance at year rollover.

## Where things live
- `template.html` — the page (theme `:root` vars + all prose). **Edit here**, not `index.html` (generated/overwritten).
- `generate.py` — FIT cache + `me.json` → `data.json` + `insights.json`, inlined into
  `template.html` → `index.html`. Helpers: `lib_fit.py` (FIT reader), `lib_strava.py`/
  `lib_merge.py` (Strava add + dedup), `geo.py` (country/outline), `lib_insights.py` (ranks hooks).
- `insights.json` — author briefing for step 5. · `assets/world_countries.geo.json` — offline borders.
