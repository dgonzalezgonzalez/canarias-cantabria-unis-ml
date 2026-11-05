"""One-time manual Proton sign-in in the daemon's dedicated Chromium profile."""
from __future__ import annotations

import json
import subprocess

from patchright.sync_api import sync_playwright
from scrapling.fetchers import StealthySession
from dotenv import load_dotenv

from src.canarias_uni_ml.jobs.spiders.infojobs_browser import (
    PROTON_EXTENSION_ID, browser_options, browser_session, profile_lock, verify_separate_egress,
)


def main() -> int:
    load_dotenv()
    options = browser_options()
    if not options:
        raise SystemExit("Set INFOJOBS_BROWSER_PROFILE and INFOJOBS_PROTON_EXTENSION first")
    with sync_playwright() as playwright:
        executable = playwright.chromium.executable_path
    print("Sign into Proton and connect a free server in the dedicated browser.", flush=True)
    print("Then close that browser window to save the profile and start the background check.", flush=True)
    print("Do not enter credentials in this terminal or chat.", flush=True)
    # Keep the manual authentication browser outside the automation event loop.
    with profile_lock(options["user_data_dir"]):
        result = subprocess.run([executable, f"--user-data-dir={options['user_data_dir']}",
                                 *options["additional_args"]["args"],
                                 f"chrome-extension://{PROTON_EXTENSION_ID}/onboarding.html"])
        if result.returncode:
            raise SystemExit(f"Manual setup browser exited with status {result.returncode}")
    with browser_session(StealthySession) as session:
        print(json.dumps(verify_separate_egress(session)), flush=True)
    print("Profile saved. Close this setup before running either regional daemon.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
