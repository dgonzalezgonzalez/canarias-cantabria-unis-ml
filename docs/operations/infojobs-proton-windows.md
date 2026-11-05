# Optional InfoJobs daemon with free Proton on Windows

Use `main` for both regions and retain the existing regional databases. No API key, administrator installation, hotspot, paid proxy or CAPTCHA service is required. Workstation tests do not establish remote access; preflight the remote host separately.

**Current status, 2026-11-05:** headless startup and small repeated daemon cycles work. Both attempted 150-job crawls stopped early. This is not validated for complete nightly InfoJobs coverage; keep the source opt-in and retain the working sources.

## Install under the daemon's Windows user

From the repository root, with Python 3.12 installed:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\scrapling.exe install
& .\.venv\Scripts\python.exe -m pip check
```

Install the [official Proton VPN Chrome extension](https://chrome.google.com/webstore/detail/proton-vpn-a-swiss-vpn-yo/jplgfhpmjnbigmhklmmbgecoobifkmpa) using a free account. Copy **only its public extension package**, never Chrome's profile, cookies, passwords or extension storage:

```powershell
$browserRoot = Join-Path $env:LOCALAPPDATA 'InfoJobsScraper'
$installed = Join-Path $env:LOCALAPPDATA 'Google\Chrome\User Data\Default\Extensions\jplgfhpmjnbigmhklmmbgecoobifkmpa'
$package = Get-ChildItem -LiteralPath $installed -Directory |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $package) { throw 'Install the official extension first; adjust the Chrome profile path if necessary.' }
New-Item -ItemType Directory -Force $browserRoot | Out-Null
Copy-Item -LiteralPath $package.FullName -Destination (Join-Path $browserRoot 'extension') -Recurse
$env:INFOJOBS_BROWSER_PROFILE = Join-Path $browserRoot 'profile'
$env:INFOJOBS_PROTON_EXTENSION = Join-Path $browserRoot 'extension'
$env:INFOJOBS_REQUIRE_PROTON = '1'
$env:INFOJOBS_REQUEST_INTERVAL_SECONDS = '2'
& .\.venv\Scripts\python.exe -m scripts.setup_infojobs_proton
```

Use an empty extension destination for the first copy; stop both daemons before replacing an old package. The script opens a dedicated Chromium window outside automation. Sign in manually, connect a **free** server and close that window. It then checks a new headless session. Expected output includes `separate browser egress verified` and `Profile saved`. Keep ordinary Chrome's VPN disconnected while using this free connection. If sign-in expires, rerun setup under the same user.

Authentication stays in this machine's dedicated profile. Do not send credentials to an agent or copy/commit profiles to GitHub. Extension 1.3.6 was tested locally; future UI changes may require updating the Connect selector.

For future launches, add these variables to the existing **untracked** repository `.env`, preserving other settings and substituting this machine's absolute paths:

```dotenv
INFOJOBS_BROWSER_PROFILE=C:/Users/SERVICE_USER/AppData/Local/InfoJobsScraper/profile
INFOJOBS_PROTON_EXTENSION=C:/Users/SERVICE_USER/AppData/Local/InfoJobsScraper/extension
INFOJOBS_REQUIRE_PROTON=1
INFOJOBS_REQUEST_INTERVAL_SECONDS=2
```

## Preflight both actual daemon routes

```powershell
New-Item -ItemType Directory -Force data/raw/infojobs-preflight | Out-Null
foreach ($region in @('canarias', 'cantabria')) {
    & .\.venv\Scripts\python.exe -u -m src.canarias_uni_ml.cli jobs daemon --run-once `
        --region $region --strategy scrape --sources infojobs --limit-per-source 150 `
        --output "data/raw/infojobs-preflight/$region.csv" `
        --db-path "data/raw/infojobs-preflight/$region.db" `
        --lock-path "data/raw/infojobs-preflight/$region.lock"
}
```

Inspect `[infojobs-summary]`: require empty `errors`, `limit_reached=true` and different browser/host IPv4. Canarias counts should include `province_20` and `province_46`. The pipeline can exit zero after saving partial results and encountering a later block, so exit status alone does not prove success. Never replace a production database with the preflight database.

## Launch both nightly daemons

Stop old regional writers and back up SQLite/CSV files first. To add InfoJobs to existing daemon commands, retain the other sources and append `infojobs` once. Never run two writers for one region. An InfoJobs-only launch from the repo root is:

```powershell
$repo = (Get-Location).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
New-Item -ItemType Directory -Force output | Out-Null
foreach ($region in @('canarias', 'cantabria')) {
    Start-Process -FilePath $python -WorkingDirectory $repo -WindowStyle Hidden `
        -ArgumentList @('-u', '-m', 'src.canarias_uni_ml.cli', 'jobs', 'daemon',
            '--region', $region, '--strategy', 'scrape', '--sources', 'infojobs',
            '--limit-per-source', '10000', '--window-start', '22:00', '--window-end', '07:30',
            '--timezone', 'Europe/Madrid', '--cooldown-minutes', '1440') `
        -RedirectStandardOutput "output/$region-infojobs.log" `
        -RedirectStandardError "output/$region-infojobs.err.log"
}
```

Defaults use separate canonical `data/processed/{region}_jobs.db`, CSV and lock paths. A shared SQLite OS lock serializes the Proton browser sessions; one region waits while the other uses the profile. Crashes release that browser lock automatically. Windows PID checks query process status without sending `os.kill(pid, 0)`.

These processes outlive the launching terminal; this does not install a reboot/logon task. Configure the remote host's existing supervisor with the same commands, user and working directory. Manual first sign-in, and possibly renewed sign-in after expiry, is required on that host. Linux/systemd or another service account remains unvalidated by these Windows tests.

## Behavior and checks

Startup uses the extension's normal Connect control and verifies different browser/host IPv4 before requesting InfoJobs. Failed startup prevents InfoJobs requests. This preflight is not a network-wide kill switch; no mid-crawl server rotation occurs.

Public listing/detail navigations are separated by two seconds by default (configurable 0.5–60 seconds). Browser subresources are additional requests. Parse public HTML as data and verify active status, offer code and exact province. Capped Canarias runs share the allowance between Las Palmas and Tenerife. Stop on browser checks, HTTP 403/405/429, invalid pagination or other access errors. Retain partial verified results and never deactivate missing historical rows. Free VPN access does not guarantee sustained InfoJobs access.

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_infojobs_browser.py tests/test_infojobs_public.py tests/test_jobs_daemon_runtime.py tests/test_jobs_daemon_schedule.py tests/test_cli_modes.py tests/test_jobs_pipeline.py tests/test_jobs_storage.py tests/test_jobtoday_spider.py -q
```

## Local validation, 2026-11-05

The user signed into the dedicated unmanaged Chromium window, connected a free server and closed it. Subsequent headless launches automatically connected and verified a different browser/host IPv4 without further sign-in. Both regional CLI daemons were started together and serialized their browser use correctly.

| Actual `jobs daemon --run-once` test | Verified offers | Result |
| --- | ---: | --- |
| Background fetch, Cantabria, cap 150, 2-second interval | 11 | HTTP 405; partial results saved |
| Background fetch, Canarias, cap 150, 2-second interval | 0 | HTTP 405; no snapshot overwritten |
| Native navigation, Cantabria, cap 150, 2-second interval | 3 | Browser-check/unrecognized HTML; existing 11 test rows retained |
| Native navigation, Canarias, cap 150, 2-second interval | 32 Las Palmas | HTTP 405 on page 2; partial results saved |
| Restart, Canarias, cap 2, 5-second interval | 1 Las Palmas + 1 Tenerife | No errors; prior test rows retained, one new row inserted |
| Restart, Cantabria, cap 2, 5-second interval | 2 | No errors; both unchanged, no duplicates |

These are finite tests, not resistance to unlimited requests. The longer tests failed at a 2-second interval; sustained crawling at a 5-second interval was not tested. No automated server switching was added. Local test logs and the machine-readable report `output/infojobs_daemon_validation_20261105.json` are kept off GitHub, along with profiles and full-text datasets. After backup, 30 new Canarias and 10 new Cantabria offers were appended to the existing workstation databases/CSVs, now 850 and 287 rows; every prior record was verified unchanged.

Focused fixture/CLI/daemon/storage checks: **78 passed**, including both Windows process-lock tests; `pip check` passed. The unrelated degree-suite baseline failures described in the main deployment runbook were not repaired or represented as passing. No remote service, reboot startup, Linux GUI/session behavior or multi-night run was tested.
