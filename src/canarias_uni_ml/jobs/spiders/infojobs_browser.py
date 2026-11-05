"""Dedicated, serialized browser profile for the optional free Proton extension."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .base import SpiderError

PROTON_EXTENSION_ID = "jplgfhpmjnbigmhklmmbgecoobifkmpa"
IP_CHECK_URL = "https://api.ipify.org?format=json"


def browser_options() -> dict:
    profile = os.getenv("INFOJOBS_BROWSER_PROFILE", "").strip()
    extension = os.getenv("INFOJOBS_PROTON_EXTENSION", "").strip()
    if not profile and not extension:
        if os.getenv("INFOJOBS_REQUIRE_PROTON", "").casefold() in {"1", "true", "yes"}:
            raise SpiderError("Proton is required: configure INFOJOBS_BROWSER_PROFILE and INFOJOBS_PROTON_EXTENSION")
        return {}
    if not profile or not extension:
        raise SpiderError("Set both INFOJOBS_BROWSER_PROFILE and INFOJOBS_PROTON_EXTENSION")
    profile_path, extension_path = Path(profile).expanduser().resolve(), Path(extension).expanduser().resolve()
    personal_roots = [Path.home() / ".config/google-chrome", Path.home() / ".config/chromium"]
    if os.getenv("LOCALAPPDATA"):
        personal_roots.append(Path(os.environ["LOCALAPPDATA"]) / "Google/Chrome/User Data")
    if any(profile_path.is_relative_to(root.resolve()) for root in personal_roots):
        raise SpiderError("Use a dedicated scraper profile outside your personal Chrome user-data directory")
    try:
        manifest = json.loads((extension_path / "manifest.json").read_text(encoding="utf-8"))
        digest = hashlib.sha256(base64.b64decode(manifest["key"], validate=True)).hexdigest()[:32]
        extension_id = "".join(chr(ord("a") + int(char, 16)) for char in digest)
    except (OSError, ValueError, KeyError) as exc:
        raise SpiderError("Cannot validate the Proton extension's public manifest") from exc
    if extension_id != PROTON_EXTENSION_ID:
        raise SpiderError("The extension is not the expected official Proton VPN package")
    return {"user_data_dir": str(profile_path), "additional_args": {
        # Keep normal browser crypto/background behavior for Proton's sign-in.
        "args": [f"--disable-extensions-except={extension_path}", f"--load-extension={extension_path}"],
        "ignore_default_args": ["--disable-extensions", "--disable-background-networking", "--enable-automation"],
    }}


@contextmanager
def profile_lock(profile: str, timeout: float = 7200):
    # SQLite's OS lock is released automatically if either regional daemon dies.
    lock_path = Path(profile).with_name(Path(profile).name + ".browser-lock.sqlite3")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(lock_path, timeout=timeout, isolation_level=None)) as connection:
        try:
            connection.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as exc:
            raise SpiderError("The shared InfoJobs browser profile is busy") from exc
        try:
            yield
        finally:
            connection.rollback()


@contextmanager
def browser_session(factory, *, headless: bool = True):
    options = browser_options()

    @contextmanager
    def launch():
        with factory(headless=headless, locale="es-ES", google_search=False,
                     timeout=30000, retries=1, **options) as session:
            if options:
                workers = session.context.service_workers
                if not any(worker.url.startswith(f"chrome-extension://{PROTON_EXTENSION_ID}/") for worker in workers):
                    session.context.wait_for_event("serviceworker", predicate=lambda worker: worker.url.startswith(
                        f"chrome-extension://{PROTON_EXTENSION_ID}/"), timeout=15000)
                print("[infojobs] Proton background worker loaded", flush=True)
                connect_proton(session)
            yield session

    if options:
        print("[infojobs] waiting for dedicated browser profile", flush=True)
        with profile_lock(options["user_data_dir"]):
            with launch() as session:
                yield session
    else:
        with launch() as session:
            yield session


def connect_proton(session) -> None:
    """Use the extension's normal Connect control; never change servers mid-crawl."""
    page = session.context.new_page()
    try:
        page.goto(f"chrome-extension://{PROTON_EXTENSION_ID}/popup.html")
        connect = page.get_by_role("button", name=re.compile(r"^(Connect|Conectar)$"))
        disconnect = page.get_by_role("button", name=re.compile(r"^(Disconnect|Desconectar)$"))
        deadline = time.monotonic() + 30
        while not disconnect.is_visible():
            if connect.is_visible():
                connect.click()
                break
            if time.monotonic() >= deadline:
                raise SpiderError("Proton needs manual sign-in; run scripts.setup_infojobs_proton")
            page.wait_for_timeout(250)
        disconnect.wait_for(state="visible", timeout=45000)
        print("[infojobs] Proton connected; checking browser egress", flush=True)
    except SpiderError:
        raise
    except Exception as exc:
        raise SpiderError(f"Proton startup failed: {type(exc).__name__}: {exc}") from exc
    finally:
        page.close()


def verify_separate_egress(session, *, attempts: int = 6) -> dict:
    """Fail before requesting InfoJobs if the browser uses the normal exit IP."""
    direct = requests.get(IP_CHECK_URL, timeout=20)
    direct.raise_for_status()
    direct_ip = str(ipaddress.IPv4Address(direct.json()["ip"]))
    last_error = "scraper uses the normal IP; connect the extension in the dedicated profile"
    for attempt in range(attempts):
        # Allow the extension to restore its connection before any InfoJobs request.
        try:
            response = session.fetch(IP_CHECK_URL, extra_headers={"Cache-Control": "no-cache"})
            if response.status != 200:
                raise SpiderError(f"Public IP check returned HTTP {response.status}")
            browser_ip = str(ipaddress.IPv4Address(json.loads(BeautifulSoup(response.body, "html.parser").get_text())["ip"]))
            if browser_ip != direct_ip:
                print(f"[infojobs] separate browser egress verified: {browser_ip}", flush=True)
                return {"direct_ipv4": direct_ip, "browser_ipv4": browser_ip}
            last_error = "scraper uses the normal IP; connect the extension in the dedicated profile"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt + 1 < attempts:
            time.sleep(2)
    raise SpiderError("Proton egress check failed: " + last_error)
