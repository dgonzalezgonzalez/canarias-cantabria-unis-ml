"""Public native JOB TODAY offers, fetched through Scrapling HTTP sessions."""
from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from ..models import JobRecord
from ..utils import clean_text
from .base import SpiderError, SpiderResult

try:
    from scrapling.fetchers import FetcherSession
except ImportError:  # optional until the source is selected
    FetcherSession = None

BASE = "https://jobtoday.com"
SEEDS = {
    "canarias": ["las-palmas-de-gran-canaria", "santa-cruz-de-tenerife", "san-cristobal-de-la-laguna",
                 "adeje", "arona", "san-bartolome-de-tirajana", "telde", "arrecife",
                 "puerto-del-rosario", "santa-cruz-de-la-palma", "san-sebastian-de-la-gomera", "valverde"],
    "cantabria": ["cantabria", "santander", "torrelavega", "camargo", "castro-urdiales", "laredo"],
}


def date_ms(value):
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat() if value else None


def outside_region(job: dict, region: str) -> bool:
    address = job.get("addressInfo") or {}
    display = address.get("display") or {}
    state = str(display.get("stateCode") or job.get("stateCode") or "").casefold()
    country = str(address.get("countryCode") or job.get("countryCode") or "").casefold()
    return bool((country and country != "es") or (state and state != {"canarias": "cn", "cantabria": "cb"}[region]))


def parse_job(job: dict, region: str) -> JobRecord | None:
    address = job.get("addressInfo") or {}
    display = address.get("display") or {}
    state = str(display.get("stateCode") or job.get("stateCode") or "").casefold()
    country = str(address.get("countryCode") or job.get("countryCode") or "").casefold()
    path = job.get("canonicalUrl", "")
    url = urljoin(BASE, path)
    if (job.get("isExternalJob") or job.get("isActive") is not True or country != "es"
            or state != {"canarias": "cn", "cantabria": "cb"}[region]
            or urlsplit(url).scheme != "https" or urlsplit(url).netloc != "jobtoday.com"
            or not urlsplit(url).path.startswith("/es/trabajo/") or "_ext_" in urlsplit(url).path):
        return None
    title, description = clean_text(job.get("role")), clean_text(job.get("description"))
    if not title or not description or not job.get("key"):
        return None
    coords = address.get("coordinates") or {}
    province = "Cantabria" if region == "cantabria" else None
    if region == "canarias" and coords.get("isValid"):
        province = "Santa Cruz de Tenerife" if coords["lng"] < -16 else "Las Palmas"
    salary = job.get("salary") or {}
    if not salary.get("isValid"):
        salary = {}
    low, high = salary.get("from"), salary.get("to")
    return JobRecord(
        source="jobtoday", external_id=str(job["key"]), title=title,
        company=clean_text(job.get("companyName")), description=description,
        salary_text=clean_text(" ".join(str(v) for v in [low, high, salary.get("currencyCode"), salary.get("period")] if v is not None)),
        salary_min=str(low) if low is not None else None,
        salary_max=str(high) if high is not None else None,
        salary_currency=salary.get("currencyCode"), salary_period=salary.get("period"),
        publication_date=date_ms(job.get("createDate")), update_date=date_ms(job.get("updateDate")),
        closing_date=date_ms(job.get("expireDate")), province=province, province_raw=display.get("state"),
        municipality=clean_text(display.get("city") or job.get("city")),
        raw_location=clean_text(display.get("fullName") or job.get("location")),
        workday=job.get("employmentType"), schedule=clean_text(job.get("shifts")),
        source_url=url, scraped_at=JobRecord.now(),
    )


class JobTodaySpider:
    source = "jobtoday"

    def __init__(self, region: str = "canarias") -> None:
        if region not in SEEDS:
            raise ValueError(f"Unsupported JOB TODAY region: {region}")
        self.region = region

    def fetch(self, limit: int) -> SpiderResult:
        if limit <= 0:
            return SpiderResult(source=self.source, records=[], complete=False)
        if FetcherSession is None:
            raise SpiderError("JOB TODAY requires pip install -r requirements.txt (Scrapling fetchers)")
        records: list[JobRecord] = []
        seen: set[str] = set()
        failures: list[str] = []
        counts = Counter()
        with FetcherSession() as session:
            response = session.get(BASE + "/robots.txt", timeout=30, retries=1)
            if response.status != 200:
                raise SpiderError("Cannot verify JOB TODAY robots policy")
            robots = RobotFileParser()
            robots.parse(response.body.decode("utf-8").splitlines())
            if not robots.can_fetch("ChatGPT-User", BASE + "/es/trabajos/" + SEEDS[self.region][0]):
                raise SpiderError("JOB TODAY robots excludes this crawler")

            def fetch(url):
                parsed = urlsplit(url)
                if parsed.scheme != "https" or parsed.netloc != "jobtoday.com":
                    raise ValueError("Unexpected source URL")
                if not robots.can_fetch("ChatGPT-User", url):
                    raise ValueError("Robots excludes " + url)
                time.sleep(0.5)
                return session.get(url, timeout=30, retries=1)

            for seed in SEEDS[self.region]:
                for page in range(1, 26):
                    url = f"{BASE}/es/trabajos/{seed}" + (f"?page={page}" if page > 1 else "")
                    try:
                        response = fetch(url)
                        counts["listing_requests"] += 1
                        if response.status != 200:
                            failures.append(f"{url}: HTTP {response.status}")
                            break
                        props = json.loads(response.css("#__NEXT_DATA__::text").get())["props"]["pageProps"]
                        items = [i["payload"] for s in props["feed"]["sections"] for i in s.get("items", []) if i.get("type") == "job"]
                        unseen = [j for j in items if j.get("key") and j["key"] not in seen]
                        for job in unseen:
                            if job["key"] in seen:
                                continue
                            seen.add(job["key"])
                            if job.get("isExternalJob"):
                                counts["external_skipped"] += 1
                                continue
                            if outside_region(job, self.region):
                                counts["outside_region_listing_skipped"] += 1
                                continue
                            detail_url = urljoin(BASE, job.get("canonicalUrl", ""))
                            if not urlsplit(detail_url).path.startswith("/es/trabajo/"):
                                continue
                            detail = fetch(detail_url)
                            counts["detail_requests"] += 1
                            if detail.status != 200:
                                failures.append(f"{detail_url}: HTTP {detail.status}")
                                continue
                            full = json.loads(detail.css("#__NEXT_DATA__::text").get())["props"]["pageProps"]["job"]
                            record = parse_job(full, self.region)
                            if record:
                                records.append(record)
                                if len(records) >= limit:
                                    self._log(counts, failures)
                                    return SpiderResult(source=self.source, records=records, complete=False)
                            else:
                                counts["inactive_or_outside_region_skipped"] += 1
                        if not props["pagination"]["hasNext"] or not unseen:
                            break
                    except Exception as exc:
                        failures.append(f"{url}: {type(exc).__name__}: {exc}")
                        break
                else:
                    failures.append(f"{seed}: 25-page limit reached")
        self._log(counts, failures)
        if not records:
            raise SpiderError("JOB TODAY returned no verified regional offers; " + "; ".join(failures[:2]))
        # City searches and blocked/external pages never establish a full census.
        return SpiderResult(source=self.source, records=records, complete=False)

    def _log(self, counts, failures) -> None:
        print(f"[jobtoday] region={self.region} counts={dict(counts)} partial=True")
        for failure in failures:
            print(f"[jobtoday] {failure}")
