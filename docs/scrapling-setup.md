# Scrapling local installation and job collection

Installed on 2026-11-04 using existing Python 3.12 and free software only.

- Package: `scrapling[all]==0.5` in the user's `.codex/tools/scrapling-venv` virtual environment.
- Upstream checkout: `.codex/tools/Scrapling`, https://github.com/D4Vinci/Scrapling.
- Official skill: `.codex/skills/scrapling-official`, installed from `agent-skill/Scrapling-Skill` using Codex's skill installer. Available on the next turn.
- Global Codex stdio MCP registration: `scrapling`, launching that environment's `Scripts/scrapling.exe mcp`.
- Browser runtime installed with `scrapling install`.
- Checks: MCP initialization and discovery of 16 tools; HTTP and headless browser retrieval of JOB TODAY's robots file; script self-check for geography, active/native filtering, preservation, deduplication and SQLite persistence.
- No API subscriptions, paid proxies, CAPTCHA-solving services or ScrapingBee calls were used.

## InfoJobs limitation

The live `https://www.infojobs.net/robots.txt` disallows all paths for `ChatGPT-User`, `GPTBot`, and `OAI-SearchBot`. Repository instructions require respecting robots policies. InfoJobs HTML was therefore not collected.

The official endpoint `https://api.infojobs.net/api/9/offer?province=cantabria&maxResults=1` returned HTTP 401 without credentials. Neither `INFOJOBS_CLIENT_ID` nor `INFOJOBS_CLIENT_SECRET` was present in the process environment. Do not silently fall back to the legacy adapter's paid ScrapingBee option. This run added zero InfoJobs jobs and does not claim complete InfoJobs coverage.

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
