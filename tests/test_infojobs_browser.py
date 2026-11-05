import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.canarias_uni_ml.jobs.spiders import infojobs_browser as browser
from src.canarias_uni_ml.jobs.spiders import infojobs_public as ij
from src.canarias_uni_ml.jobs.spiders.base import SpiderError


@pytest.fixture(autouse=True)
def no_browser_environment(monkeypatch):
    monkeypatch.delenv("INFOJOBS_BROWSER_PROFILE", raising=False)
    monkeypatch.delenv("INFOJOBS_PROTON_EXTENSION", raising=False)
    monkeypatch.delenv("INFOJOBS_REQUIRE_PROTON", raising=False)


@pytest.fixture
def configured_profile(monkeypatch, tmp_path):
    extension = tmp_path / "extension"
    extension.mkdir()
    fixture = Path(__file__).parent / "fixtures/proton_extension_manifest.json"
    (extension / "manifest.json").write_bytes(fixture.read_bytes())
    profile = tmp_path / "scraper-profile"
    monkeypatch.setenv("INFOJOBS_BROWSER_PROFILE", str(profile))
    monkeypatch.setenv("INFOJOBS_PROTON_EXTENSION", str(extension))
    return profile, extension


def test_default_browser_does_not_load_proton():
    assert browser.browser_options() == {}


def test_required_proton_cannot_silently_use_direct_connection(monkeypatch):
    monkeypatch.setenv("INFOJOBS_REQUIRE_PROTON", "1")
    with pytest.raises(SpiderError, match="Proton is required"):
        browser.browser_options()


def test_dedicated_profile_loads_official_public_extension(configured_profile):
    profile, extension = configured_profile
    options = browser.browser_options()
    assert options["user_data_dir"] == str(profile)
    assert f"--load-extension={extension}" in options["additional_args"]["args"]
    assert "--disable-background-networking" in options["additional_args"]["ignore_default_args"]


def test_rejects_incomplete_configuration_and_non_proton_extension(configured_profile, monkeypatch):
    _, extension = configured_profile
    (extension / "manifest.json").write_text(json.dumps({"key": "ZmFrZQ=="}), encoding="utf-8")
    with pytest.raises(SpiderError, match="not the expected"):
        browser.browser_options()
    monkeypatch.delenv("INFOJOBS_PROTON_EXTENSION")
    with pytest.raises(SpiderError, match="both"):
        browser.browser_options()


def test_personal_chrome_profile_is_rejected(configured_profile, monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("INFOJOBS_BROWSER_PROFILE", str(tmp_path / "Google/Chrome/User Data"))
    with pytest.raises(SpiderError, match="personal Chrome"):
        browser.browser_options()


def test_profile_lock_excludes_other_region_and_recovers_after_exception(tmp_path):
    profile = str(tmp_path / "shared-profile")
    with pytest.raises(ValueError):
        with browser.profile_lock(profile, timeout=0.01):
            with pytest.raises(SpiderError, match="busy"):
                with browser.profile_lock(profile, timeout=0.01):
                    pytest.fail("Concurrent profile use was allowed")
            raise ValueError("Simulated browser failure")
    with browser.profile_lock(profile, timeout=0.01):
        pass


@pytest.mark.parametrize("browser_ip,allowed", [("169.150.218.56", True), ("192.148.209.196", False)])
def test_egress_check_rejects_direct_fallback(monkeypatch, browser_ip, allowed):
    direct = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"ip": "192.148.209.196"})
    monkeypatch.setattr(browser.requests, "get", lambda *args, **kwargs: direct)
    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status=200, body=('<html><body><pre>' + json.dumps({"ip": browser_ip}) + '</pre></body></html>').encode())

    session = SimpleNamespace(fetch=fetch)
    if allowed:
        assert browser.verify_separate_egress(session, attempts=1)["browser_ipv4"] == browser_ip
    else:
        with pytest.raises(SpiderError, match="normal IP"):
            browser.verify_separate_egress(session, attempts=1)
    assert calls == [browser.IP_CHECK_URL]


def test_egress_check_allows_extension_startup_then_requires_different_ip(monkeypatch):
    monkeypatch.setattr(browser.time, "sleep", lambda _: None)
    monkeypatch.setattr(browser.requests, "get", lambda *args, **kwargs: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"ip": "192.148.209.196"}))
    count = 0

    def fetch(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            raise RuntimeError("ERR_PROXY_CONNECTION_FAILED during startup")
        return SimpleNamespace(status=200, body=b'{"ip":"169.150.218.56"}')

    assert browser.verify_separate_egress(SimpleNamespace(fetch=fetch), attempts=2)["browser_ipv4"] == "169.150.218.56"
    assert count == 2


def test_daemon_spider_never_requests_infojobs_after_failed_egress_check(monkeypatch):
    calls = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def fetch(self, url, **kwargs):
            calls.append(url)
            pytest.fail("InfoJobs was requested after VPN failure")

    monkeypatch.setattr(ij, "StealthySession", lambda **kwargs: Session())
    monkeypatch.setattr(ij, "browser_options", lambda: {"user_data_dir": "dedicated"})

    def reject(_):
        raise SpiderError("Proton egress check failed")

    monkeypatch.setattr(ij, "verify_separate_egress", reject)
    with pytest.raises(SpiderError, match="egress check failed"):
        ij.InfoJobsPublicSpider("cantabria").fetch(150)
    assert calls == []


@pytest.mark.parametrize("state", ["connected", "disconnected", "signed-out", "failed"])
def test_proton_startup_uses_normal_connect_control_and_closes_popup(monkeypatch, state):
    calls = []
    connected = state == "connected"

    class Button:
        def __init__(self, disconnect):
            self.disconnect = disconnect

        def is_visible(self):
            return connected if self.disconnect else state != "signed-out" and not connected

        def click(self):
            nonlocal connected
            calls.append("connect")
            if state == "failed":
                raise TimeoutError("Connection failed")
            connected = True

        def wait_for(self, **kwargs):
            assert connected and kwargs["state"] == "visible"

    page = SimpleNamespace(
        goto=lambda url: calls.append(url),
        get_by_role=lambda role, name: Button("Disconnect" in name.pattern),
        close=lambda: calls.append("closed"),
    )
    session = SimpleNamespace(context=SimpleNamespace(new_page=lambda: page))
    ticks = iter([0, 31])
    monkeypatch.setattr(browser.time, "monotonic", lambda: next(ticks))
    if state in {"signed-out", "failed"}:
        with pytest.raises(SpiderError, match="manual sign-in|startup failed"):
            browser.connect_proton(session)
    else:
        browser.connect_proton(session)
    assert calls[-1] == "closed"
    assert calls.count("connect") == (state in {"disconnected", "failed"})
