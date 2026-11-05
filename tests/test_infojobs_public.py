import json
from types import SimpleNamespace

import pytest

from src.canarias_uni_ml.cli import main
from src.canarias_uni_ml.jobs.regions import default_spiders
from src.canarias_uni_ml.jobs.spiders import infojobs_public as ij
from src.canarias_uni_ml.jobs.spiders.base import SpiderError
from src.canarias_uni_ml.jobs.storage import JobsRepository


def html(props):
    return "<script>window.__INITIAL_PROPS__ = JSON.parse(" + json.dumps(json.dumps(props)) + ");</script>"


def offer(code="abc", province=13):
    return {"offerCode": code, "title": "Técnico contable", "companyName": "Fixture",
            "description": "Contabilidad y facturas.", "minimumRequirements": "Grado en ADE.",
            "minimumStudies": {"level": "Grado"}, "canApply": True,
            "location": {"city": "Santander" if province == 13 else "Telde", "province": {"id": province}},
            "salary": "1800 EUR/mes", "publishedAt": "2026-11-05T08:00:00Z",
            "contract": {"type": "Indefinido", "workday": "Completa"}, "numberOfVacancies": 2}


def listing(code="abc"):
    return {"code": code, "link": f"//www.infojobs.net/city/role/of-i{code}?page=1",
            "salary": {"range": {"min": 1800, "max": 2200}, "currency": "EUR", "period": "MONTH"}}


@pytest.mark.parametrize("region,province", [("cantabria", 13), ("canarias", 20), ("canarias", 46)])
def test_parse_full_regional_detail(region, province):
    row = listing()
    url = ij.offer_url(row["link"], row["code"])
    job = ij.parse_offer(offer(province=province), row, region, url)
    assert job.province == ij.PROVINCES[str(province)]
    assert job.salary_min == "1800" and job.salary_period == "MONTH"
    assert "Requisitos mínimos: Grado en ADE." in job.description
    assert job.source_url == "https://www.infojobs.net/city/role/of-iabc"
    for change in [{"canApply": False}, {"canApply": "true"}, {"offerCode": "other"},
                   {"location": {"province": {"id": 33}}}]:
        assert ij.parse_offer({**offer(province=province), **change}, row, region, url) is None


@pytest.mark.parametrize("value", ["https://example.com/role/of-iabc", "http://www.infojobs.net/role/of-iabc",
                                  "//www.infojobs.net/city/role/of-iother", "javascript:alert(1)"])
def test_reject_untrusted_urls(value):
    with pytest.raises(SpiderError):
        ij.offer_url(value, "abc")


def test_browser_check_is_failure_even_with_http_200():
    with pytest.raises(SpiderError, match="browser check"):
        ij.page_props("<h1>No podemos identificar tu navegador</h1>")
    assert ij.page_props(html({"offers": []})) == {"offers": []}


@pytest.fixture
def site(monkeypatch):
    class Site:
        def __init__(self):
            self.calls = []
            self.lost_filter = False
            self.block_detail = False
            self.province = 13
            self.gone_detail = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def fetch(self, url, **kwargs):
            if kwargs.get("page_action"):
                kwargs["page_action"](self)
            return SimpleNamespace(status=200, body=html({"offers": []}).encode())

        def evaluate(self, script, url):
            self.calls.append(url)
            if "/of-i" in url:
                code = url.rsplit("of-i", 1)[1]
                if code == "blocked" or self.block_detail:
                    return {"status": 429, "html": "rate limit"}
                if code == "two" and self.gone_detail:
                    return {"status": 410, "html": "gone"}
                payload = {"offer": offer(code, 33 if code == "outside" else self.province)}
            else:
                second = "page=2" in url
                payload = {"search": {"provinceIds": [] if second and self.lost_filter else [str(self.province)]},
                           "navigation": {"self": 2 if second else 1, "next": None if second else 2, "totalPages": 2},
                           "offers": [listing("two"), listing("blocked")] if second else
                                     [listing(), listing(), listing("outside")]}
            return {"status": 200, "html": html(payload)}

    instance = Site()
    monkeypatch.setattr(ij, "StealthySession", lambda **kwargs: instance)
    monkeypatch.setattr(ij.time, "sleep", lambda _: None)
    return instance


def test_fetch_deduplicates_checks_details_and_retains_partial_on_rate_limit(site):
    result = ij.InfoJobsPublicSpider("cantabria").fetch(100)
    assert [r.external_id for r in result.records] == ["abc", "two"]
    assert result.complete is False
    assert sum("of-iabc" in u for u in site.calls) == 1
    assert all("provinceIds=13" in u for u in site.calls if "ofertas-trabajo" in u)


def test_fetch_stops_if_pagination_loses_province_filter(site):
    site.lost_filter = True
    result = ij.InfoJobsPublicSpider("cantabria").fetch(100)
    assert [r.external_id for r in result.records] == ["abc"]
    assert not any("of-itwo" in u for u in site.calls)


def test_limit_and_explicit_region_source_selection(site):
    assert len(ij.InfoJobsPublicSpider("cantabria").fetch(1).records) == 1
    assert not any("page=2" in u for u in site.calls)
    for region in ij.REGIONS:
        spiders = default_spiders(region, ["infojobs"])
        assert len(spiders) == 1 and spiders[0].region == region
        assert not any(s.source == "infojobs" for s in default_spiders(region))


def test_cli_failure_preserves_existing_csv(site, tmp_path):
    site.block_detail = True
    csv = tmp_path / "jobs.csv"
    csv.write_text("previous valid snapshot\n", encoding="utf-8")
    code = main(["jobs", "scrape", "--region", "cantabria", "--sources", "infojobs",
                 "--limit-per-source", "1", "--output", str(csv), "--db-path", str(tmp_path / "jobs.db")])
    assert code == 1
    assert csv.read_text() == "previous valid snapshot\n"
    assert not (tmp_path / "jobs.db").exists()


def test_gone_detail_is_skipped_without_discarding_previous_records(site):
    site.gone_detail = True
    result = ij.InfoJobsPublicSpider("cantabria").fetch(100)
    assert [r.external_id for r in result.records] == ["abc"]
    assert any("of-iblocked" in u for u in site.calls)


@pytest.mark.parametrize("region,province", [("cantabria", 13), ("canarias", 20)])
def test_daemon_routes_to_public_scraper_and_upserts_without_duplicates(site, tmp_path, region, province):
    site.province = province
    database = tmp_path / "jobs.db"
    args = ["jobs", "daemon", "--run-once", "--region", region, "--strategy", "scrape",
            "--sources", "infojobs", "--limit-per-source", "1", "--output", str(tmp_path / "jobs.csv"),
            "--db-path", str(database), "--lock-path", str(tmp_path / "jobs.lock")]
    assert main(args) == 0
    assert main(args) == 0
    records = JobsRepository(database).read_all()
    assert len(records) == 1 and records[0].province == ij.PROVINCES[str(province)]
