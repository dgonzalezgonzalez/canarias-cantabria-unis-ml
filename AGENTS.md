# Repository Guidelines

## Project Structure & Module Organization
This repository contains a Python job-scraping pipeline for Canarias and Cantabria. Keep the layout simple and source-oriented:

- `src/canarias_uni_ml/jobs/` is the authoritative jobs pipeline, regional source selection, storage and daemon.
- `src/canarias_uni_ml/jobs/spiders/` owns source-specific scrapers, including `jobtoday.py` (Scrapling), `sce.py` and `emcan.py`.
- `src/canarias_jobs/cli.py` is a legacy CLI compatibility entrypoint; add new production sources to the canonical package above.
- `data/raw/` for temporary captures if needed during debugging. Do not commit dumps.
- `data/processed/` for generated outputs such as `canarias_jobs.csv`.
- `docs/` for source notes, API findings, and scraping constraints.

Keep normalization in shared code and source-specific extraction logic inside each spider.

## Build, Test, and Development Commands
Use a local virtual environment:

- `python3 -m venv .venv && source .venv/bin/activate` creates the environment.
- `.venv/bin/pip install -r requirements.txt` installs dependencies.
- `.venv/bin/python -m playwright install chromium` installs the browser runtime used by Playwright sources.
- `.venv/bin/python -m src.canarias_jobs.cli --limit-per-source 50` runs the scraper and writes `data/processed/canarias_jobs.csv`.
- `.venv/bin/python -m compileall src` is the current lightweight code sanity check.

Run `python -m pytest tests -q`. For JOB TODAY changes, include `tests/test_jobtoday_spider.py`, pipeline, CLI and daemon tests. These fixture tests require no live website or paid service.

## Coding Style & Naming Conventions
Use Python with 4-space indentation and follow PEP 8. Name modules and files in `snake_case`, classes in `PascalCase`, and constants in `UPPER_SNAKE_CASE`. Keep scraping selectors and extraction rules close to the site-specific module that owns them.

Avoid hardcoding secrets, cookies, or local machine paths. API credentials must come from environment variables.

## Testing Guidelines
Use sample-based tests where possible because live job sites are unstable and anti-bot protections vary. Name test files `test_<module>.py`. Prefer:

- one parsing test per supported site
- one normalization test for the common job schema
- one regression test for any selector fix

## Commit & Pull Request Guidelines
Use short imperative commit messages such as `Add SCE API scraper` or `Switch Turijobs to sitemap detail flow`.

Pull requests should include:

- a brief summary of the source or parser affected
- sample output or a short schema example
- notes on rate limits, robots rules, or anti-bot constraints
- linked issue or task, if one exists

## Security & Data Handling
Respect each site's terms, robots policy, and rate limits before scraping. Store credentials in `.env`, never in code. Do not commit large raw dumps unless they are necessary test fixtures.

## Source Notes
- `sce` works via a JWT extracted from the public Angular iframe and then a JSON API call.
- `turijobs` works best from `active-offers.xml` plus detail pages, not the paginated listing UI.
- `indeed` is currently blocked from this environment by Cloudflare even in Playwright. Treat it as best-effort unless network conditions change.
- `--sources infojobs` selects `InfoJobsPublicSpider` in `infojobs_public.py`, using public pages through Scrapling without credentials. The old API/ScrapingBee adapter is not selected by the canonical pipeline; never call its paid fallback.

## Remote-agent handoff: Scrapling/JOB TODAY (2026-11-04)

- Both regions now share the single deployment branch `main` in `dgonzalezgonzalez/canarias-cantabria-unis-ml` (consolidated 2026-11-05). Fetch/pull `main`; do not recreate separate Canarias/Cantabria branches for deployment. Follow [the two-region deployment runbook](docs/operations/remote-nightly-deploy.md) before editing services.
- Use the existing remote checkout and preserve its databases. Stop both regional daemons/cron jobs, back up their SQLite/CSV files, update code, and install `requirements.txt` in that machine's venv. Python 3.12 is tested. Do not copy Windows `.codex` paths or this workstation's venv to Linux.
- `JobTodaySpider(region=...)` uses Scrapling HTTP sessions and implements the standard `fetch(limit) -> SpiderResult` contract. It is available through `--sources jobtoday` for both regions. The manual script delegates to the same pipeline; there is no second scraper implementation.
- Use `jobs daemon --strategy scrape`, never `scale`, for JOB TODAY. `scale` has fixed legacy sources; explicit `--sources` with it is rejected. The shipped Canarias unit now selects `sce,jobtoday`; Cantabria selects `emcan,jobtoday`. Both have a 10000-record cap and 1440-minute cooldown. This intentionally replaces the old Canarias scale/five-minute template. Other sources remain explicit opt-ins.
- Adjust `User`, checkout paths, optional environment-file path and interpreter path in BOTH systemd templates before installing them. Each region must keep separate CSV, database and lock paths. Never run two writers for the same region.
- The daemon needs no Codex, MCP, browser download or API keys for JOB TODAY. The workstation's official Scrapling skill and 16-tool MCP server are for interactive use only. Chromium is only needed for optional Turijobs. No paid API, proxy or CAPTCHA service may be added.
- Run fixture tests and a small `--run-once` preflight for BOTH regions on the VM. Inspect `[ok] jobtoday` specifically: another successful source can mask a JOB TODAY failure in the overall exit status. Only then enable both services. Do not claim the remote daemon is running until checked on the remote host.
- SQLite is canonical. A first successful scrape seeds a missing database from the existing regional CSV before upserting new offers. Existing databases are never replaced from CSV/Git. JOB TODAY always returns `complete=False`; partial searches must never deactivate missing historical rows.
- Validate Spain plus exact regional codes (`cn` Canarias, `cb` Cantabria), active native offers, trusted source URLs and current robots rules. Skip external/`*_ext_*` aggregator offers. Keep the 0.5-second request delay and bounded pagination. Coverage is partial; absent offers are not proof of closure.
- InfoJobs follow-up (2026-11-05): the user explicitly requested this public-page research attempt despite the earlier robots restriction. This records the user's instruction, not a legal finding about institutional powers. InfoJobs remains an explicit opt-in (`--sources infojobs`); no API credentials, paid services, proxy rotation or CAPTCHA solvers are used. See the updated deployment runbook before enabling it remotely. Source terms restrict commercial reuse; do not publish scraped full-text datasets as part of a code deployment.
- The workstation's previous collection verified 443 JOB TODAY records for Canarias and 179 for Cantabria. These CSV snapshots/databases/raw captures and local logs are not deployment files; the remote agent must retain/recollect its own state. See [Scrapling notes](docs/scrapling-setup.md).
- The deployment runbook records local validation and three known failures in untouched degree-catalog code/missing fixtures. Do not claim the full suite passed. Run the two process-lock tests on Linux; they were excluded on Windows.

## Public InfoJobs adapter

- Install browser binaries on the target machine with its venv's `scrapling install` under the actual service user (including required Linux OS libraries). JOB TODAY alone still needs no browser. Do not copy workstation browser cookies or browser profiles.
- Public search URLs must explicitly include `provinceIds=13` (Cantabria), `20` (Las Palmas), or `46` (Santa Cruz de Tenerife) on EVERY page. Appending `?page=2` to a regional slug loses the province filter and produces nationwide results. Validate the returned search filter and page number before accepting candidates.
- Read the public HTML's `window.__INITIAL_PROPS__` JSON string using JSON decoding, never execute downloaded scripts. Verify each native detail's matching offer code, exact province ID and `canApply=true`; retain descriptions and requirements. Strip tracking queries for stable URL upserts. Do not assume that a search result's city proves its province.
- Requests use the initialized browser's ordinary same-origin `fetch` for public HTML, at most two starts per second. Stop on a browser check, 403/405/429, unexpected pagination or other access failure; retain any verified partial data. There is no automated challenge solver or paid retry path. Both complete and capped traversals report `complete=False` to protect historical records.
- The local broad attempt received HTTP 405 after 98 verified Cantabria offers. Connectivity depends on host/network; preflight each region with a small `--limit-per-source` before scheduling. Inspect `[infojobs]` warnings even when the pipeline exit status is zero. No remote InfoJobs run has been verified.
