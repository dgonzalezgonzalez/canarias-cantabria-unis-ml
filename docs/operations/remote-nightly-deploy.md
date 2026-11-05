# Remote nightly deployment: Canarias and Cantabria

This is the deployment handoff for the Scrapling/JOB TODAY integration (2026-11-04).
Repository: https://github.com/dgonzalezgonzalez/canarias-cantabria-unis-ml
Deployment branch: `main`. Both regional scrapers, JOB TODAY and the optional public InfoJobs adapter were consolidated there on 2026-11-05. Update old checkouts explicitly; separate regional deployment branches are no longer used.

Deployment choice, 2026-11-05: use the previous direct InfoJobs adapter. The experimental Proton integration was removed because its tests did not establish sustained access and the user prefers simpler remote setup. No VPN installation, account or signed-in browser profile is needed. Remove obsolete experimental `INFOJOBS_BROWSER_PROFILE`, `INFOJOBS_PROTON_EXTENSION`, `INFOJOBS_REQUIRE_PROTON` and `INFOJOBS_REQUEST_INTERVAL_SECONDS` settings if present. Keep all regional data; the independent Windows process-lock fix is retained. InfoJobs remains opt-in and can still be limited.

## What runs

| Service | Region | Explicit sources | Output prefix |
| --- | --- | --- | --- |
| `canarias-jobs-daemon` | Canarias | `sce,jobtoday` | `data/processed/canarias_jobs` |
| `cantabria-jobs-daemon` | Cantabria | `emcan,jobtoday` | `data/processed/cantabria_jobs` |

Both templates use `--strategy scrape`, a 22:00–07:30 Europe/Madrid window, a 1440-minute cooldown, and a 10000-record per-source safety limit. JOB TODAY additionally bounds each city search to 25 pages. These are best-effort regional searches, not a complete census.

**Change from the old Canarias unit:** `scale` does not call JOB TODAY. The supplied unit now uses `scrape` and the explicit sources above. This also replaces its old five-minute repeat loop with a daily cooldown. Indeed/JobSpy and Turijobs remain available as optional `scrape` sources; they are not enabled in these templates. Do not keep an old daemon or cron job writing the same region's files at the same time.

JOB TODAY uses Scrapling **HTTP** sessions. No browser download, MCP server, Codex installation, paid proxy, API subscription, OpenAI key or CAPTCHA service is needed on the VM. The local Codex skill/MCP installation is separate from this Python service. `requirements.txt` installs the runtime; its Playwright pin was raised to match Scrapling's fetcher requirements. Chromium is needed if enabling optional Turijobs or InfoJobs.

## Update an existing machine safely

Run from its existing repository directory. Stop both services before backing up SQLite and before updating code. If service names differ, stop the actual local units/cron jobs first. Preserve any unrelated local code changes; do not reset or delete the data directory.

```bash
sudo systemctl stop canarias-jobs-daemon.service cantabria-jobs-daemon.service
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
for region in canarias cantabria; do
  for suffix in db csv; do
    file="data/processed/${region}_jobs.${suffix}"
    if [ -f "$file" ]; then cp -p "$file" "backups/${region}_jobs.${stamp}.${suffix}"; fi
  done
done

git fetch origin
git switch main
git pull --ff-only origin main
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
```

## New machine

Python 3.12 is the tested interpreter. On a host providing it, install its `venv` support using the OS package manager if absent, then:

```bash
git clone --branch main https://github.com/dgonzalezgonzalez/canarias-cantabria-unis-ml.git /opt/canarias-cantabria-unis-ml
cd /opt/canarias-cantabria-unis-ml
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
```

Create the checkout as, or grant write access to, the intended service user. The templates assume `User=ubuntu` and `/opt/canarias-cantabria-unis-ml`. If the existing checkout is `/opt/canarias-uni-ml` or another path, edit `User`, `WorkingDirectory`, `EnvironmentFile` and the Python path in `ExecStart` consistently before installing both units. `.env` is optional for these sources.

The existing regional SQLite databases are authoritative and stay on the remote machine. Local CSV snapshots, database files, raw HTML and machine-specific Codex configuration are not part of this deployment commit. If a CSV exists but its regional database is absent, the first successful `scrape` cycle imports the CSV into the new database before adding offers. A source failure preserves the old CSV. An existing database is never reseeded or replaced from Git.

## Test and preflight before enabling services

```bash
.venv/bin/python -m pytest tests/test_jobtoday_spider.py tests/test_emcan_spider.py tests/test_jobs_pipeline.py tests/test_jobs_daemon_runtime.py tests/test_jobs_daemon_schedule.py tests/test_cli_modes.py -q

# Small real requests verify connectivity and both exact daemon routes.
# Partial JOB TODAY results never deactivate historical offers.
.venv/bin/python -m src.canarias_uni_ml.cli jobs daemon --run-once \
  --region canarias --strategy scrape --sources sce,jobtoday --limit-per-source 1
.venv/bin/python -m src.canarias_uni_ml.cli jobs daemon --run-once \
  --region cantabria --strategy scrape --sources emcan,jobtoday --limit-per-source 1
```

Each region should log `[ok] jobtoday`, `[done] wrote ...`, and a successful cycle summary. A zero exit status can also mean another selected source succeeded while JOB TODAY failed: inspect individual source logs, not only the exit code. If necessary isolate the new source with `--sources jobtoday`. Do not enable the daemon until the VM can actually retrieve JOB TODAY.

If a unit fails to acquire its regional lock, find the existing process first. The daemon reclaims stale locks; do not delete a lock belonging to a live process. The two regions use separate CSVs, databases and lock files. `--sources` is rejected with `--strategy scale` so the new source cannot be silently ignored.

## Install, start and monitor both services

After adjusting the templates for this machine:

```bash
sudo cp deploy/systemd/canarias-jobs-daemon.service /etc/systemd/system/
sudo cp deploy/systemd/cantabria-jobs-daemon.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now canarias-jobs-daemon.service cantabria-jobs-daemon.service
sudo systemctl status canarias-jobs-daemon.service cantabria-jobs-daemon.service
sudo journalctl -u canarias-jobs-daemon.service -u cantabria-jobs-daemon.service -f
```

Outside the configured window they wait. `--run-once` bypasses that window for preflight. A daily cooldown follows each completed cycle; both processes remain running. No-change successful cycles are healthy. Templates restart on failure, not after every successful scrape. Their health threshold follows existing pipeline behavior: one working source keeps a mixed-source cycle healthy, so monitor `[skip] jobtoday` and `[jobtoday]` warnings too.

## Source behavior and limits

- The same `JobTodaySpider` backs the CLI, manual helper and both daemons. `--sources jobtoday` is supported for either region.
- Listings and each accepted native detail page are checked. Jobs require Spain plus the exact `cn`/`cb` region code and `isActive=true`; known out-of-region listings are excluded before detail requests.
- Every crawl retrieves and enforces the live robots policy. External aggregator jobs and disallowed `*_ext_*` pages are excluded. Requests are sequential within a source and delayed by 0.5 seconds. Check the current source terms before changing this internal-research use to commercial reuse or redistribution.
- Stable source URLs drive SQLite upserts and repeat-night deduplication. Partial/capped/blocked results always have `complete=False`, so JOB TODAY never deactivates offers merely missing from one crawl. Historical JOB TODAY offers can therefore remain active; this is not a fully maintained census of current vacancies.
- HTTP 404/410, malformed pages and failed seed searches are logged. Nonempty partial results are retained; if no verified offers are available the source fails and the pipeline keeps the previous snapshot when no other source succeeds.
- InfoJobs public pages are now available as an explicit opt-in after the user's 2026-11-05 instruction. The shipped units still select the sources in the table above. See the section below; never enable the legacy paid ScrapingBee adapter.

## Optional InfoJobs without API credentials (2026-11-05)

The user explicitly requested a public-page research attempt despite the previously recorded robots exclusion. This documents that instruction; it does not establish an institutional legal exemption. The canonical `--sources infojobs` selects `InfoJobsPublicSpider`, not the old API/ScrapingBee adapter. It requires no keys, paid proxy or CAPTCHA service.

Install the Scrapling browser runtime using the same account and environment as the service; a browser installed in root's cache may be invisible to `User=ubuntu`. Install any required Linux shared libraries reported by the installer.

```bash
.venv/bin/scrapling install
.venv/bin/python -m pytest tests/test_infojobs_public.py -q
.venv/bin/python -m src.canarias_uni_ml.cli jobs daemon --run-once \
  --region canarias --strategy scrape --sources infojobs --limit-per-source 1
.venv/bin/python -m src.canarias_uni_ml.cli jobs daemon --run-once \
  --region cantabria --strategy scrape --sources infojobs --limit-per-source 1
```

If both preflights work, add `infojobs` to the existing `ExecStart` source lists (`sce,jobtoday,infojobs` and `emcan,jobtoday,infojobs`), then reload/restart both units. Keep the regional databases, daily cooldown and separate locks. InfoJobs is not included when `--sources` is omitted.

The adapter follows explicit province filters on every page and checks each detail's province and `canApply` status. It retains full available detail descriptions, minimum/desired requirements and education fields in the description. Public search descriptions alone may be truncated and are not treated as full detail. It makes ordinary same-origin browser requests, caps each province at 250 pages, and stops on access failures instead of solving challenges or rotating identities. Missing/partial results never deactivate historical rows. Monitor `[infojobs]` lines: a source can return some records successfully and still stop early on HTTP 405/429. Local collection reached 98 verified Cantabria offers before HTTP 405; remote access and sustained coverage remain unverified.

The manual equivalent, from the repository root, is:

```bash
.venv/bin/python -m scripts.scrape_scrapling_jobs --region both --limit-per-source 10000
```

Remote startup and network policy must be verified by the agent on that VM. Local tests and a local live preflight cannot establish remote deployment success.

## Local validation and known baseline failures

On 2026-11-04 the focused scraper/pipeline/CLI/daemon/storage/Turijobs/compatibility checks passed (51 tests). Both actual daemon CLI routes also retrieved one live JOB TODAY offer into isolated temporary files. Dependency installation and `pip check` passed. Two process-lock tests were excluded on Windows; run them on the Linux VM.

An earlier wider-suite run had 130 passing tests and three failures in untouched degree code/fixtures: `test_degree_storage.py` hits a missing `DegreeCatalogRecord.description_status` attribute, and two `test_program_page_resolver.py` tests require untracked/missing `tests/fixtures/program_page_samples` HTML files. These are outside the JOB TODAY deployment change; do not interpret them as a successful full-suite run or silently fabricate the fixtures.
