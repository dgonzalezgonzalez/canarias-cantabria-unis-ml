# Scrapling local installation and job collection

Installed on 2026-11-04 using existing Python 3.12 and free software only.

- Package: `scrapling[all]==0.5` in the user's `.codex/tools/scrapling-venv` virtual environment.
- Upstream checkout: `.codex/tools/Scrapling`, https://github.com/D4Vinci/Scrapling.
- Official skill: `.codex/skills/scrapling-official`, installed from `agent-skill/Scrapling-Skill` using Codex's skill installer. Available on the next turn.
- Global Codex stdio MCP registration: `scrapling`, launching that environment's `Scripts/scrapling.exe mcp`.
- Browser runtime installed with `scrapling install`.
- Checks: MCP initialization and discovery of 16 tools; HTTP and headless browser retrieval of JOB TODAY's robots file; script self-check for geography, active/native filtering, preservation, deduplication and SQLite persistence.
- No API subscriptions, paid proxies, CAPTCHA-solving services or ScrapingBee calls were used.

## Original InfoJobs limitation (2026-11-04)

The live `https://www.infojobs.net/robots.txt` disallows all paths for `ChatGPT-User`, `GPTBot`, and `OAI-SearchBot`. Repository instructions require respecting robots policies. InfoJobs HTML was therefore not collected.

The official endpoint `https://api.infojobs.net/api/9/offer?province=cantabria&maxResults=1` returned HTTP 401 without credentials. Neither `INFOJOBS_CLIENT_ID` nor `INFOJOBS_CLIENT_SECRET` was present in the process environment. Do not silently fall back to the legacy adapter's paid ScrapingBee option. This run added zero InfoJobs jobs and does not claim complete InfoJobs coverage.

## Public InfoJobs follow-up (2026-11-05)

The user subsequently explicitly requested an attempt against public pages despite the earlier robots exclusion, without API access. This records the instruction, not a legal determination about AIReF's powers. Plain Scrapling HTTP requests returned a browser-check document with HTTP 200. Scrapling's JavaScript-capable browser exposed public search and offer state without API keys or a CAPTCHA solver.

`InfoJobsPublicSpider` in `src/canarias_uni_ml/jobs/spiders/infojobs_public.py` now supports explicit `--sources infojobs` for both regional CLI/daemon routes. It is excluded from default source selection. Use the existing venv and run:

```bash
python -m src.canarias_uni_ml.cli jobs scrape --region cantabria --sources infojobs --limit-per-source 10000
python -m src.canarias_uni_ml.cli jobs scrape --region canarias --sources infojobs --limit-per-source 10000
```

Province filters must be explicit on every page (`13`, `20`, `46`). Adding `?page=2` to a regional slug silently yields nationwide results; returned filters and page numbers are validated. Each accepted record is checked on its public native detail page for province ID, offer identity and `canApply=true`. Descriptions include available minimum/desired requirements and minimum studies. Tracking queries are removed from stable URLs.

Requests use ordinary same-origin browser fetches, with at most two starts per second. HTTP access failures and browser checks stop the attempt, preserving nonempty partial data. The source always reports `complete=False`; absence never deactivates historical jobs. No API credentials, paid services, proxy rotation or challenge solvers are used. The local attempt retrieved 98 Cantabria offers before HTTP 405. Local audit results are in `output/infojobs_public_run_20261105.json` and the matching log; datasets, backups and logs are not code-deployment files. See the runbook's optional InfoJobs section for remote browser installation and both regional preflights.

The Canarias attempt retrieved 43 verified Las Palmas offers before another HTTP 405, before reaching the Santa Cruz de Tenerife search. Total verified additions: 141 (98 Cantabria, 43 Canarias). Neither crawl completed. The regional pipeline exports canonical lifecycle columns from SQLite that were absent in the earlier manual CSV; preservation checks compare every originally present field, allowing those additional columns. Focused public-scraper/pipeline/storage/CLI/daemon/compatibility tests: 59 passed, two Windows process-lock tests excluded. No remote InfoJobs run was performed.

## Additional free source: JOB TODAY

Run from the repository root in PowerShell:

```powershell
& "$env:USERPROFILE\.codex\tools\scrapling-venv\Scripts\python.exe" -m scripts.scrape_scrapling_jobs --self-check
& "$env:USERPROFILE\.codex\tools\scrapling-venv\Scripts\python.exe" -u -m scripts.scrape_scrapling_jobs
```

The collector is now `src/canarias_uni_ml/jobs/spiders/jobtoday.py` and uses the standard regional pipeline for storage, normalization and degree-target annotation. The manual helper delegates to that same pipeline. It accepts native offers whose detail page reports `isActive=true`, country Spain and region code Canarias (`cn`) or Cantabria (`cb`). It excludes external aggregator jobs and their robots-disallowed `*_ext_*` pages. Full available job descriptions, company, salary, dates, location and source URL are retained.

Review the source's current [robots policy](https://jobtoday.com/robots.txt) and [terms](https://jobtoday.com/es/legal/tos) before reuse. The terms restrict commercial copying and scraping; this collection is for internal research and is not authorization to publish or commercially redistribute it.

The canonical SQLite databases keep regional state and export `data/processed/canarias_jobs.csv` and `data/processed/cantabria_jobs.csv`. Existing databases are upserted, not replaced. If the database is absent, a successful scrape first imports the existing regional CSV. JOB TODAY always reports a partial result so missing historical jobs are not deactivated. All-source failures preserve the previous CSV.

Coverage remains partial: city searches overlap or omit jobs, pages may return HTTP 404/410, and each seed has a 25-page bound. Historical offers are not fully revalidated. The 2026-11-04 run report and original backup are local audit artifacts, not deployment files or public datasets.

For the daemon on another machine, follow [the deployment runbook](operations/remote-nightly-deploy.md) and `AGENTS.md`. Both systemd templates now include JOB TODAY through `--strategy scrape`; no MCP server, Codex installation, browser download, paid subscription or API key is needed there. Only the interactive workstation uses the global skill/MCP installation described above.

## Verified outcome, 2026-11-04

- Canarias: 443 JOB TODAY offers added (222 Las Palmas, 221 Santa Cruz de Tenerife); CSV increased from 334 to 777 rows.
- Cantabria: 179 JOB TODAY offers; a new regional CSV was created because none existed locally.
- Total additions: 622. InfoJobs additions: zero.
- The original 334 CSV rows were preserved exactly as parsed and an exact pre-change file backup was retained. Both regional SQLite databases contain the same number of rows as their CSVs. All new source IDs and URLs are unique within each region.
- Script self-check and eight existing storage/date tests passed; `pip check` reported no broken requirements.
- Source coverage remains partial. Listing end/error responses were HTTP 404 or 410 and are recorded in the report. Existing historical offers were not revalidated.
