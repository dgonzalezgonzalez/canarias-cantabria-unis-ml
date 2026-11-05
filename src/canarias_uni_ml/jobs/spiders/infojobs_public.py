"""Opt-in public InfoJobs pages through Scrapling; no API or paid fallback."""
from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from urllib.parse import urljoin, urlsplit, urlunsplit

from ..models import JobRecord
from ..utils import clean_text, parse_date
from .base import SpiderError, SpiderResult
from .infojobs_browser import browser_options, browser_session, verify_separate_egress

try:
    from scrapling.fetchers import StealthySession
except ImportError:
    StealthySession = None

BASE = "https://www.infojobs.net"
PROVINCES = {"13": "Cantabria", "20": "Las Palmas", "46": "Santa Cruz de Tenerife"}
REGIONS = {"cantabria": ("13",), "canarias": ("20", "46")}
INITIAL_PROPS = re.compile(r'window\.__INITIAL_PROPS__\s*=\s*JSON\.parse\(("(?:[^"\\]|\\.)*")\)')


def page_props(html: str) -> dict:
    match = INITIAL_PROPS.search(html)
    if not match:
        raise SpiderError("InfoJobs returned a browser check or an unrecognized page; stopping")
    props = json.loads(json.loads(match[1]))
    if not isinstance(props, dict):
        raise SpiderError("Invalid InfoJobs page state")
    return props


def offer_url(value: str, code: str) -> str:
    parts = urlsplit(urljoin(BASE, value))
    if (parts.scheme != "https" or parts.netloc != "www.infojobs.net"
            or not re.fullmatch(r"[a-zA-Z0-9]+", code)
            or not parts.path.endswith("/of-i" + code)):
        raise SpiderError("Unexpected InfoJobs offer URL")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def parse_offer(offer: dict, listing: dict, region: str, url: str) -> JobRecord | None:
    location = offer.get("location") or {}
    province_id = str((location.get("province") or {}).get("id", ""))
    code = str(offer.get("offerCode") or "")
    title = clean_text(offer.get("title"))
    if (province_id not in REGIONS[region] or offer.get("canApply") is not True
            or code != listing.get("code") or not title or not clean_text(offer.get("description"))):
        return None
    url = offer_url(url, code)
    sections = [offer["description"]]
    for key, label in [("minimumRequirements", "Requisitos mínimos"), ("desiredRequirements", "Requisitos deseados")]:
        if clean_text(offer.get(key)):
            sections.append(label + ": " + offer[key])
    studies = (offer.get("minimumStudies") or {}).get("level")
    if studies:
        sections.append("Estudios mínimos: " + studies)
    salary = listing.get("salary") or {}
    pay_range = salary.get("range") or {}
    salary_text = clean_text(offer.get("salary"))
    if salary_text == "Salario no disponible":
        salary_text = None
    contract = offer.get("contract") or {}
    province = PROVINCES[province_id]
    city = clean_text(location.get("city"))
    return JobRecord(
        source="infojobs", external_id=code, title=title,
        company=clean_text(offer.get("companyName")), description=clean_text("\n\n".join(sections)),
        salary_text=salary_text,
        salary_min=str(pay_range["min"]) if pay_range.get("min") is not None else None,
        salary_max=str(pay_range["max"]) if pay_range.get("max") is not None else None,
        salary_currency=salary.get("currency"), salary_period=salary.get("period"),
        publication_date=parse_date(offer.get("publishedAt")), update_date=None,
        province=province, province_raw=clean_text((location.get("province") or {}).get("label")),
        municipality=city, raw_location=" / ".join(filter(None, [city, province])),
        contract_type=clean_text(contract.get("type")), workday=clean_text(contract.get("workday")),
        schedule=clean_text(offer.get("workingHours")),
        vacancies=str(offer["numberOfVacancies"]) if offer.get("numberOfVacancies") is not None else None,
        source_url=url, scraped_at=JobRecord.now(),
    )


class InfoJobsPublicSpider:
    source = "infojobs"

    def __init__(self, region: str = "canarias") -> None:
        if region not in REGIONS:
            raise ValueError(f"Unsupported InfoJobs region: {region}")
        self.region = region

    def fetch(self, limit: int) -> SpiderResult:
        if limit <= 0:
            return SpiderResult(self.source, [], complete=False)
        if StealthySession is None:
            raise SpiderError("InfoJobs requires Scrapling fetchers and `scrapling install`")
        records: list[JobRecord] = []
        seen: set[str] = set()
        counts = Counter()
        errors: list[str] = []
        interval = float(os.getenv("INFOJOBS_REQUEST_INTERVAL_SECONDS", "2"))
        if not 0.5 <= interval <= 60:
            raise SpiderError("INFOJOBS_REQUEST_INTERVAL_SECONDS must be between 0.5 and 60")
        self.last_run = {"region": self.region, "counts": counts, "errors": errors, "interval_seconds": interval}

        def collect(page):
            last_request = time.monotonic()

            def request(url, missing_ok=False):
                nonlocal last_request
                if urlsplit(url).netloc != "www.infojobs.net" or urlsplit(url).scheme != "https":
                    raise SpiderError("Unexpected InfoJobs host")
                time.sleep(max(0, interval - (time.monotonic() - last_request)))
                last_request = time.monotonic()
                # Native navigation works where background fetch receives HTTP 405.
                response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                counts["requests"] += 1
                if response is None:
                    raise SpiderError("Missing InfoJobs navigation response; stopping")
                destination = urlsplit(response.url)
                if destination.scheme != "https" or destination.netloc != "www.infojobs.net":
                    raise SpiderError("Unexpected InfoJobs navigation; stopping")
                if missing_ok and response.status in {404, 410}:
                    counts["gone_detail_pages"] += 1
                    return {}
                if response.status != 200:
                    raise SpiderError(f"InfoJobs HTTP {response.status} at {url}; stopping")
                try:
                    return page_props(response.text())
                except SpiderError as exc:
                    raise SpiderError(f"{exc} at {response.url}") from exc

            try:
                provinces = REGIONS[self.region]
                for index, province_id in enumerate(provinces):
                    # Share a capped run across both Canary provinces.
                    remaining = limit - len(records)
                    provinces_left = len(provinces) - index
                    target = len(records) + (remaining + provinces_left - 1) // provinces_left
                    page_number = 1
                    while page_number <= 250:
                        url = f"{BASE}/ofertas-trabajo/?provinceIds={province_id}&page={page_number}"
                        props = request(url)
                        navigation = props.get("navigation") or {}
                        if (props.get("search", {}).get("provinceIds") != [province_id]
                                or navigation.get("self") != page_number):
                            raise SpiderError("InfoJobs lost its province/page filter; stopping")
                        listings = props.get("offers")
                        if not isinstance(listings, list):
                            raise SpiderError("Missing InfoJobs listings")
                        counts["listing_pages"] += 1
                        unseen = 0
                        for listing in listings:
                            code = str(listing.get("code") or "")
                            if not code or code in seen:
                                continue
                            seen.add(code)
                            unseen += 1
                            detail_url = offer_url(listing.get("link", ""), code)
                            detail_props = request(detail_url, missing_ok=True)
                            if not detail_props:
                                continue
                            detail = detail_props.get("offer")
                            if not isinstance(detail, dict):
                                raise SpiderError("Missing InfoJobs offer detail; stopping")
                            counts["detail_pages"] += 1
                            record = parse_offer(detail, listing, self.region, detail_url)
                            if record:
                                records.append(record)
                                counts[f"province_{province_id}"] += 1
                            else:
                                counts["inactive_or_outside_region"] += 1
                            if len(records) >= limit:
                                return
                            if len(records) >= target:
                                break
                        print(f"[infojobs] region={self.region} province={province_id} page={page_number}/{navigation.get('totalPages')} accepted={len(records)} counts={dict(counts)}", flush=True)
                        if len(records) >= target:
                            break
                        next_page = navigation.get("next")
                        if not next_page:
                            break
                        if next_page != page_number + 1 or not unseen:
                            raise SpiderError("InfoJobs repeated or invalid pagination; stopping")
                        page_number = next_page
                    else:
                        errors.append(f"Province {province_id}: 250-page cap")
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")

        try:
            with browser_session(StealthySession) as session:
                if browser_options():
                    self.last_run["egress"] = verify_separate_egress(session)
                seed = f"{BASE}/ofertas-trabajo/?provinceIds={REGIONS[self.region][0]}&page=1"
                response = session.fetch(seed, wait=1500)
                if response.status != 200:
                    raise SpiderError(f"InfoJobs initial HTTP {response.status}")
                page_props(response.body.decode("utf-8"))
                session.fetch(seed, page_action=collect)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        for error in errors:
            print(f"[infojobs] {error}", flush=True)
        print(f"[infojobs] region={self.region} accepted={len(records)} counts={dict(counts)} partial=True", flush=True)
        self.last_run.update(accepted=len(records), complete=False, limit_reached=len(records) >= limit)
        print("[infojobs-summary] " + json.dumps(self.last_run, ensure_ascii=False), flush=True)
        if not records:
            raise SpiderError("InfoJobs returned no verified offers; " + "; ".join(errors[:2]))
        # A moving search index, caps and blocked pages never establish a full census.
        return SpiderResult(self.source, records, complete=False)
