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

This is a **one-stop-shop**: do the preflight yourself, decide the path, and only
stop to ask the user for a real choice or their own login. Don't make them figure
out setup.

**0. Preflight — check the environment, fix what you can**
1. **Python 3**: `python3 --version`. If missing, tell the user how to install it for
   their OS and stop until it's there.
2. **Dependencies**: create a venv and install — `python3 -m venv .venv` then
   `. .venv/bin/activate && pip install -r requirements.txt`. (If pip fails, surface
   the error and fix it before continuing.)
3. **`gh` (only needed for the optional deploy in step 7)** — check `gh auth status`;
   if absent, just note it and carry on (not needed to build the page).
4. **Garmin access.** All the work needs is Garmin OAuth tokens in `~/.garminconnect`
   — once they exist, everything is passwordless. `fetch_garmin.py` (step 1) does the
   bulk download efficiently and **reuses those tokens no matter how they got there**.
   So:
   - If a **Garmin MCP is already connected** (e.g. the user runs `Taxuspt/garmin_mcp`),
     the tokens are already saved → step 1 just works, no password. Nothing to install.
   - **No MCP, no tokens?** Don't block: step 1's `fetch_garmin.py` will ask the user's
     Garmin login once and save the tokens itself. This is the zero-setup default.
   - **If the user also wants the Garmin MCP** in Claude Code generally (optional — not
     needed for this page), set up `Taxuspt/garmin_mcp` for them (it shares the same
     `~/.garminconnect` tokens). Needs [`uv`](https://docs.astral.sh/uv/) (`brew install uv`).
     Confirm before changing their config, then:
     ```
     uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth   # user types login once
     claude mcp add garmin -- uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp
     ```
     (the auth step alone is enough to make step 1 passwordless, even without registering the MCP.)

**1. Get their Garmin data into `./cache/`** — run `python fetch_garmin.py`.
It reuses `~/.garminconnect` tokens (passwordless if the user has the MCP or has logged
in before; otherwise it asks for their Garmin login once), downloads new activities
incrementally, and **auto-writes `birth_year` + `resting_hr` from their Garmin profile**
into `me.json` (these drive the HR zones). Safe to re-run.
- *(If you prefer to drive it via a connected Garmin MCP instead, you can — list running
  activities, save each FIT to `cache/fit/<id>.fit` and a `cache/manifest.json` of
  `{id:{fit_file,name,start_time}}`, plus birth year + resting HR — but `fetch_garmin.py`
  is faster for the bulk download, so prefer it.)*

**2. Config** — `me.json` is mostly **auto-filled from Garmin** in step 1 (birth year,
resting HR → HR zones; max HR comes from the FIT data; zones recompute every run).
Just:
- set `lang` (default `pl`), leave `home_city` as `null` (auto-detected).
- only **ask the user** for `birth_year` / `resting_hr` if step 1 couldn't fetch them
  (e.g. profile private) — otherwise don't bother them.

**3. Generate**
```
python generate.py
```
It prints the detected `home`, `country`, `countries` and `pins`. **Confirm the home
city with the user** — if the auto-detected name is wrong, set `home_city` in
`me.json` and re-run.

**4. Colors (ask, then restyle)**
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

**5. Storytelling (analyse, then rewrite the copy)**
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

**6. Preview** — open `index.html` in a browser (maps need internet — Leaflet CDN).
Check: hero numbers, the year bars, the “gdzie” scene tabs (home / country / Świat),
and the route-map carousel all render.

**7. Deploy (optional)** — only if they want it online and accept it's public:
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
