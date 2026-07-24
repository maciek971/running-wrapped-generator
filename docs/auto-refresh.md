# Advanced: auto-refresh (self-updating page)

By default this tool is **manual**: you clone, build `index.html`, optionally deploy it once,
and re-run `./make.sh` whenever you want fresh numbers. That's all most people need.

If you want a page that **updates itself daily** from Garmin — no local machine involved —
this is the pattern. It keeps your raw GPS data private while publishing only the finished
page.

## The three-repo layout

```
PUBLIC  running-wrapped-generator   the engine/tool (this repo). You never put data here.
   ▲ checked out fresh each run
   │
PRIVATE  <your>-wrapped-pipeline    personal data ONLY: me.json, your customized
   │                                template.html, cache/ (raw FIT/GPS), + the workflow.
   │ publishes only index.html
   ▼
PUBLIC  <your>-wrapped-pages        holds just index.html → served on GitHub Pages.
```

The daily job checks out the public engine, overlays your private `template.html` + `me.json`
+ `cache/` on top, fetches new activities, regenerates, commits the updated cache back to the
private repo, and pushes **only `index.html`** to the public Pages repo. Because the engine is
pulled fresh every run, any improvement to the public tool flows into your page automatically.

## Setup

**Prereqs:** you've already built your page once locally (so you have a `cache/`, a themed
`template.html`, and a `me.json`), and you have `gh` authenticated.

### 1. Create the public Pages repo (holds only index.html)
```bash
gh repo create <YOU>/<YOUR_PAGES_REPO> --public
# push your current index.html once, then enable Pages (Settings → Pages → deploy from main).
```
The template already sets `<meta name="robots" content="noindex, nofollow">`. The page is
**public to anyone with the link** — use an unguessable repo name.

### 2. Create the private pipeline repo (holds your data)
Track `me.json`, your `template.html`, `cache/`, and the workflow — but **not** the engine
code or generated artifacts. Use this `.gitignore`:
```gitignore
data.json
insights.json
index.html
__pycache__/
*.pyc
# engine is overlaid at build time — never commit it here:
.engine/
fetch_garmin.py
generate.py
geo.py
garmin_records.py
lib_*.py
requirements.txt
assets/
# cache/ and me.json ARE tracked (this repo is private)
```
Then:
```bash
gh repo create <YOU>/<YOUR_PIPELINE_REPO> --private --source=. --remote=origin --push
```
Copy [`../examples/github-actions/daily-refresh.yml`](../examples/github-actions/daily-refresh.yml)
to `.github/workflows/daily.yml` and replace `<ENGINE_OWNER>`, `<YOUR_GH_USER>`,
`<YOUR_PAGES_REPO>`.

### 3. Deploy key (lets the job push index.html to the Pages repo)
```bash
ssh-keygen -t ed25519 -f /tmp/deploy_key -N "" -C "wrapped-deploy"
gh repo deploy-key add /tmp/deploy_key.pub -R <YOU>/<YOUR_PAGES_REPO> --title wrapped-deploy --allow-write
gh secret set DEPLOY_KEY -R <YOU>/<YOUR_PIPELINE_REPO> < /tmp/deploy_key
shred -u /tmp/deploy_key /tmp/deploy_key.pub   # or rm -f
```

### 4. Garmin token secret (so the job logs in without a password)
After a local `python fetch_garmin.py`, your token lives in `~/.garminconnect`:
```bash
base64 -i ~/.garminconnect/garmin_tokens.json | gh secret set GARMIN_TOKENS -R <YOU>/<YOUR_PIPELINE_REPO>
```
Garth tokens are long-lived (~a year). If Garmin ever logs the token out, re-run the command
above to refresh it. *(Optional resilience: also set `GARMIN_EMAIL` / `GARMIN_PASSWORD`
secrets — the workflow falls back to them if the token expires.)*

### 5. Go
`gh workflow run daily.yml -R <YOU>/<YOUR_PIPELINE_REPO>` to test now, or wait for the cron.
Adjust the `cron:` time in the workflow (it's UTC).

## What stays private vs public
- **Private:** raw FIT/GPS `cache/`, `me.json`, your Garmin token, the Actions logs.
- **Public:** only the finished `index.html`. The engine code is public anyway (it's the tool).
