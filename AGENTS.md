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
- `infojobs` is implemented against the official API and requires `INFOJOBS_CLIENT_ID` and `INFOJOBS_CLIENT_SECRET`.

## Remote-agent handoff: Scrapling/JOB TODAY (2026-11-04)

- Deployment branch is `cantabria-scraper` in `dgonzalezgonzalez/canarias-cantabria-unis-ml`. Fetch/pull that branch explicitly. Follow [the two-region deployment runbook](docs/operations/remote-nightly-deploy.md) before editing services.
- Use the existing remote checkout and preserve its databases. Stop both regional daemons/cron jobs, back up their SQLite/CSV files, update code, and install `requirements.txt` in that machine's venv. Python 3.12 is tested. Do not copy Windows `.codex` paths or this workstation's venv to Linux.
- `JobTodaySpider(region=...)` uses Scrapling HTTP sessions and implements the standard `fetch(limit) -> SpiderResult` contract. It is available through `--sources jobtoday` for both regions. The manual script delegates to the same pipeline; there is no second scraper implementation.
- Use `jobs daemon --strategy scrape`, never `scale`, for JOB TODAY. `scale` has fixed legacy sources; explicit `--sources` with it is rejected. The shipped Canarias unit now selects `sce,jobtoday`; Cantabria selects `emcan,jobtoday`. Both have a 10000-record cap and 1440-minute cooldown. This intentionally replaces the old Canarias scale/five-minute template. Other sources remain explicit opt-ins.
- Adjust `User`, checkout paths, optional environment-file path and interpreter path in BOTH systemd templates before installing them. Each region must keep separate CSV, database and lock paths. Never run two writers for the same region.
- The daemon needs no Codex, MCP, browser download or API keys for JOB TODAY. The workstation's official Scrapling skill and 16-tool MCP server are for interactive use only. Chromium is only needed for optional Turijobs. No paid API, proxy or CAPTCHA service may be added.
- Run fixture tests and a small `--run-once` preflight for BOTH regions on the VM. Inspect `[ok] jobtoday` specifically: another successful source can mask a JOB TODAY failure in the overall exit status. Only then enable both services. Do not claim the remote daemon is running until checked on the remote host.
- SQLite is canonical. A first successful scrape seeds a missing database from the existing regional CSV before upserting new offers. Existing databases are never replaced from CSV/Git. JOB TODAY always returns `complete=False`; partial searches must never deactivate missing historical rows.
- Validate Spain plus exact regional codes (`cn` Canarias, `cb` Cantabria), active native offers, trusted source URLs and current robots rules. Skip external/`*_ext_*` aggregator offers. Keep the 0.5-second request delay and bounded pagination. Coverage is partial; absent offers are not proof of closure.
- Preserve the existing InfoJobs limitation: no API access, no website scraping against its robots rules, and no paid ScrapingBee fallback. Source terms restrict commercial reuse; do not publish scraped full-text datasets as part of a code deployment.
- The workstation's previous collection verified 443 JOB TODAY records for Canarias and 179 for Cantabria. These CSV snapshots/databases/raw captures and local logs are not deployment files; the remote agent must retain/recollect its own state. See [Scrapling notes](docs/scrapling-setup.md).
- The deployment runbook records local validation and three known failures in untouched degree-catalog code/missing fixtures. Do not claim the full suite passed. Run the two process-lock tests on Linux; they were excluded on Windows.
