# Running Wrapped — generator (instructions for Claude Code)

This repo turns a person's **Garmin running history** into a single self-contained
`index.html` — a Spotify-Wrapped-style story of them as a runner. Nothing here is
tied to a specific person or country: home city, country and the map are
**auto-detected from the GPS data**.

When the user first opens this repo and asks for their Running Wrapped, run the
**First-run playbook** below, top to bottom. Ask the questions in steps 3, 5 and 6
**one at a time** and wait for answers.

## Ground rules (do not skip)
- **Never type the user's Garmin password yourself.** Either they have a Garmin MCP
  connected (use it), or they run `fetch_garmin.py` and type the login themselves.
- The data is personal (home-area GPS, daily routine). If you deploy to GitHub
  Pages, it becomes **public to anyone with the link** — confirm explicitly first.
- Keep everything in the user's language (default Polish; `me.json → lang`).

## First-run playbook

**1. Environment**
```
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

**2. Get their Garmin data into `./cache/`**
- If a **Garmin MCP** is connected: list the user's running activities and download
  each one's FIT file to `cache/fit/<activityId>.fit`, and write `cache/manifest.json`
  as `{ "<id>": {"fit_file":"<id>.fit","name":"<activity name>","start_time":"<gmt>"} }`.
  (Names power the place labels, so include them.) Also pull the user's **birth year**
  and **resting HR** via the MCP (`get_user_profile`/`get_userprofile_settings` and
  `get_rhr_day`/`get_user_summary`) and write them into `me.json` as `birth_year` /
  `resting_hr` — they drive the heart-rate zones.
- Otherwise: `python fetch_garmin.py` — asks the user for their Garmin login (tokens
  cached afterwards) and **auto-writes `birth_year` + `resting_hr` from their Garmin
  profile** into `me.json`. Incremental: safe to re-run.

**3. Config** — `me.json` is mostly **auto-filled from Garmin** in step 2 (birth year,
resting HR → HR zones; max HR comes from the FIT data; zones recompute every run).
Just:
- set `lang` (default `pl`), leave `home_city` as `null` (auto-detected).
- only **ask the user** for `birth_year` / `resting_hr` if step 2 couldn't fetch them
  (e.g. profile private) — otherwise don't bother them.

**4. Generate**
```
python generate.py
```
It prints the detected `home`, `country`, `countries` and `pins`. **Confirm the home
city with the user** — if the auto-detected name is wrong, set `home_city` in
`me.json` and re-run.

**5. Colors (ask, then restyle)**
Ask: *"Jakie kolory lubisz / jaki klimat? (np. ciepły zachód słońca, chłodny błękit, neon…)"*
Then recolor by editing the `:root` block at the top of `template.html`:
- `--a1`, `--a2`, `--a3` — the **accent gradient** (light → mid → deep). This is the
  signature look (numbers, bars, active tab, glows). Pick 3 harmonious stops from
  their colors.
- `--ink` / `--ink2` — page + card background (keep them dark for contrast, or go
  light but then also flip `--cream`/`--muted`/`--line` for readability).
- `--cream` (text), `--muted` (secondary), `--line` (borders).
Re-run `python generate.py`, open `index.html`, iterate with them until they like it.
Keep text contrast ≥ 4.5:1.

**6. Storytelling (analyse, then rewrite the copy)**
The template ships with placeholder Polish narrative. Read `data.json` and make the
prose **true to THIS runner**, then rewrite the chapter intros + the `.edu` callouts
+ the outro in `template.html`. Look at and reflect:
- the year trend (`years[]`): growing? comeback? steady? — rewrite chapter "wspinaczka".
- busiest/most-consistent year, `records` — the outro + records framing.
- when they run (`hours`, `weekday`): early bird / night owl / weekend warrior.
- zone split (`zones_by_year[].pct`): polarised easy, or mostly hard?
- travel (`scale.countries`, `poland.places`): a homebody or a tourist-runner?
Rules: keep their language; keep the dynamic hooks (`[data-km="YEAR"]`, the
`<span id="…">` placeholders) where live numbers appear — they auto-fill from data,
so a future refresh won't go stale. Don't invent facts; describe what the data shows.
Re-run `python generate.py` after editing.

**7. Preview** — open `index.html` in a browser (maps need internet — Leaflet CDN).
Check: hero numbers, the year bars, the “gdzie” scene tabs (home / country / Świat),
and the route-map carousel all render.

**8. Deploy (optional)** — only if they want it online and accept it's public:
- unguessable repo name (e.g. `running-wrapped-$(openssl rand -hex 3)`), public,
  push **only `index.html`** with the user's own `gh` account.
- the template already has `<meta name="robots" content="noindex, nofollow">`.
- give them `https://<their-gh-user>.github.io/<repo>/`.

## Refreshing later
`./make.sh` re-fetches new activities and regenerates. Inline numbers/dates update
themselves from the data; only year-specific *wording* you wrote by hand may need a
glance at year rollover.

## Where things live
- `template.html` — the page (theme `:root` vars + all prose). **Edit here**, not in
  `index.html` (which is generated and overwritten).
- `generate.py` — builds `data.json` from the FIT cache + `me.json`, inlines into
  `template.html` → `index.html`. `lib_fit.py` reads FIT, `geo.py` does country/outline.
- `assets/world_countries.geo.json` — borders for country detection (offline).
