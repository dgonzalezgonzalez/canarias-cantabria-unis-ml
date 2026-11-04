import csv
import json
import shlex
from pathlib import Path
from types import SimpleNamespace

import pytest
from scrapling.parser import Selector

from src.canarias_uni_ml.cli import main
from src.canarias_uni_ml.jobs.regions import default_spiders
from src.canarias_uni_ml.jobs.spiders import jobtoday
from src.canarias_uni_ml.jobs.spiders.base import SpiderError
from src.canarias_uni_ml.jobs.storage import JobsRepository


def offer(region, key="one", title=None):
    canary = region == "canarias"
    return {
        "key": key, "role": title or f"Administrative assistant {key}", "description": "Manage orders and prepare customer invoices.",
        "companyName": "Fixture employer", "isActive": True, "isExternalJob": False,
        "canonicalUrl": f"/es/trabajo/assistant-{key}",
        "createDate": 1793700000000, "updateDate": 1793780000000,
        "employmentType": "FULL_TIME",
        "salary": {"isValid": True, "from": 1800, "to": 2200, "currencyCode": "EUR", "period": "MONTHLY"},
        "addressInfo": {
            "countryCode": "es",
            "coordinates": {"isValid": True, "lat": 28.46 if canary else 43.46, "lng": -16.25 if canary else -3.8},
            "display": {"stateCode": "cn" if canary else "cb", "state": "Canarias" if canary else "Cantabria",
                        "city": "Santa Cruz de Tenerife" if canary else "Santander", "fullName": "Fixture address"},
        },
    }


def html_response(props):
    selector = Selector('<script id="__NEXT_DATA__" type="application/json">' +
                        json.dumps({"props": {"pageProps": props}}) + "</script>")
    return SimpleNamespace(status=200, css=selector.css)


@pytest.fixture
def fake_site(monkeypatch):
    class Site:
        def __init__(self, region):
            self.region = region
            self.jobs = [offer(region), offer(region, "two")]
            self.calls = []
            self.robots = b"User-agent: *\nDisallow: /*_ext_*\n"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, **kwargs):
            self.calls.append(url)
            if url.endswith("robots.txt"):
                return SimpleNamespace(status=200, body=self.robots)
            if "/es/trabajo/" in url:
                return html_response({"job": next(j for j in self.jobs if url.endswith(j["canonicalUrl"]))})
            second = "page=2" in url
            jobs = self.jobs[1:] if second else [self.jobs[0], self.jobs[0]]
            if not second:
                outside = offer("cantabria" if self.region == "canarias" else "canarias", "outside")
                external = {**offer(self.region, "external"), "isExternalJob": True,
                            "canonicalUrl": "/es/trabajo/external_ext_forbidden"}
                jobs = [*jobs, outside, external]
            return html_response({"feed": {"sections": [{"items": [{"type": "job", "payload": j} for j in jobs]}]},
                                  "pagination": {"hasNext": not second}})

    def configure(region):
        site = Site(region)
        monkeypatch.setattr(jobtoday, "FetcherSession", lambda: site)
        monkeypatch.setattr(jobtoday, "SEEDS", {region: [region]})
        monkeypatch.setattr(jobtoday.time, "sleep", lambda _: None)
        return site

    return configure


@pytest.mark.parametrize("region,province", [("canarias", "Santa Cruz de Tenerife"), ("cantabria", "Cantabria")])
def test_parse_offer_and_reject_inactive_outside_external_or_unsafe(region, province):
    job = offer(region)
    record = jobtoday.parse_job(job, region)
    assert record.province == province
    assert record.salary_min == "1800" and record.salary_period == "MONTHLY"
    assert record.description == job["description"]
    assert jobtoday.parse_job({**job, "isActive": False}, region) is None
    assert jobtoday.parse_job({**job, "isActive": "false"}, region) is None
    assert jobtoday.parse_job({**job, "isExternalJob": True}, region) is None
    assert jobtoday.parse_job({**job, "canonicalUrl": "https://example.com/es/trabajo/one"}, region) is None
    assert jobtoday.parse_job({**job, "canonicalUrl": "http://jobtoday.com/es/trabajo/one"}, region) is None
    assert jobtoday.parse_job({**job, "canonicalUrl": "/es/trabajo/one_ext_blocked"}, region) is None
    assert jobtoday.parse_job(job, "cantabria" if region == "canarias" else "canarias") is None


@pytest.mark.parametrize("region", ["canarias", "cantabria"])
def test_fetch_paginates_and_skips_external_and_outside_before_detail(region, fake_site):
    site = fake_site(region)
    result = jobtoday.JobTodaySpider(region).fetch(10)
    assert [r.external_id for r in result.records] == ["one", "two"]
    assert not result.complete
    assert any("page=2" in url for url in site.calls)
    assert not any("outside" in url or "_ext_" in url for url in site.calls)


def test_fetch_limit_is_partial_and_does_not_request_next_page(fake_site):
    site = fake_site("canarias")
    result = jobtoday.JobTodaySpider().fetch(1)
    assert len(result.records) == 1 and not result.complete
    assert not any("page=2" in url for url in site.calls)


def test_robots_exclusion_stops_before_listings(fake_site):
    site = fake_site("cantabria")
    site.robots = b"User-agent: ChatGPT-User\nDisallow: /\n"
    with pytest.raises(SpiderError, match="robots excludes"):
        jobtoday.JobTodaySpider("cantabria").fetch(10)
    assert len(site.calls) == 1


@pytest.mark.parametrize("region", ["canarias", "cantabria"])
def test_actual_daemon_route_preserves_csv_seed_updates_and_keeps_partial_history(region, fake_site, tmp_path):
    site = fake_site(region)
    output, database = tmp_path / f"{region}.csv", tmp_path / f"{region}.db"
    historic = jobtoday.parse_job(offer(region, "historic"), region).to_row()
    historic["source"] = "existing_source"
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(historic))
        writer.writeheader()
        writer.writerow(historic)
    args = ["jobs", "daemon", "--run-once", "--region", region, "--sources", "jobtoday",
            "--output", str(output), "--db-path", str(database), "--lock-path", str(tmp_path / "daemon.lock")]
    assert main(args) == 0
    assert len(JobsRepository(database).read_all()) == 3
    site.jobs[0]["role"] = "Updated assistant"
    # A capped follow-up must keep job two and the CSV seed in canonical storage.
    assert main([*args, "--limit-per-source", "1"]) == 0
    records = JobsRepository(database).read_all(active_only=True)
    assert len(records) == 3
    assert next(r for r in records if r.external_id == "one").title == "Updated assistant"
    with output.open(encoding="utf-8", newline="") as f:
        assert len(list(csv.DictReader(f))) == 3


def test_failed_source_keeps_existing_csv_and_does_not_create_database(fake_site, tmp_path):
    site = fake_site("cantabria")
    site.robots = b"User-agent: ChatGPT-User\nDisallow: /\n"
    output, database = tmp_path / "jobs.csv", tmp_path / "jobs.db"
    output.write_text("previous snapshot", encoding="utf-8")
    assert main(["jobs", "scrape", "--region", "cantabria", "--sources", "jobtoday",
                 "--output", str(output), "--db-path", str(database)]) == 1
    assert output.read_text(encoding="utf-8") == "previous snapshot"
    assert not database.exists()


def test_scale_cannot_silently_ignore_jobtoday_selection():
    with pytest.raises(SystemExit) as exc:
        main(["jobs", "daemon", "--strategy", "scale", "--sources", "jobtoday", "--run-once"])
    assert exc.value.code == 2


@pytest.mark.parametrize("region", ["canarias", "cantabria"])
def test_service_template_selects_jobtoday_for_correct_region(region):
    service = (Path(__file__).resolve().parents[1] / f"deploy/systemd/{region}-jobs-daemon.service").read_text()
    command = next(line.removeprefix("ExecStart=") for line in service.splitlines() if line.startswith("ExecStart="))
    tokens = shlex.split(command)
    from src.canarias_uni_ml.cli import build_parser
    args = build_parser().parse_args(tokens[tokens.index("jobs"):])
    assert args.region == region and args.strategy == "scrape"
    assert "jobtoday" in args.sources.split(",")
    assert any(isinstance(s, jobtoday.JobTodaySpider) for s in default_spiders(region, args.sources.split(",")))
