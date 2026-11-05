from __future__ import annotations

from .spiders import EmcanSpider, InfoJobsPublicSpider, JobspySpider, JobTodaySpider, SCESpider, TrabajoCantabriaSpider, TurijobsSpider


SUPPORTED_REGIONS = ("canarias", "cantabria")

SOURCE_NAMES = ("sce", "emcan", "trabajocantabria", "turijobs", "jobspy", "jobtoday", "infojobs")


def default_spiders(region: str, sources: list[str] | tuple[str, ...] | None = None) -> list[object]:
    normalized = region.strip().lower()
    if normalized not in SUPPORTED_REGIONS:
        raise ValueError(f"Unsupported jobs region: {region}")
    selected = tuple(item.strip().lower() for item in sources or ())
    if selected:
        unknown = sorted(set(selected) - set(SOURCE_NAMES))
        if unknown:
            raise ValueError(f"Unsupported job sources: {', '.join(unknown)}")
        allowed = {"canarias": {"sce", "turijobs", "jobspy", "jobtoday", "infojobs"}, "cantabria": {"emcan", "trabajocantabria", "turijobs", "jobspy", "jobtoday", "infojobs"}}[normalized]
        invalid = sorted(set(selected) - allowed)
        if invalid:
            raise ValueError(f"Sources not available for {normalized}: {', '.join(invalid)}")

    def wanted(name: str) -> bool:
        return not selected or name in selected

    if normalized == "canarias":
        spiders: list[object] = []
        if wanted("sce"):
            spiders.append(SCESpider())
        if wanted("turijobs"):
            spiders.append(TurijobsSpider(region=normalized))
        if wanted("jobspy"):
            spiders.append(JobspySpider(region=normalized))
        if wanted("jobtoday"):
            spiders.append(JobTodaySpider(region=normalized))
        if "infojobs" in selected:
            spiders.append(InfoJobsPublicSpider(region=normalized))
        return spiders
    if normalized == "cantabria":
        spiders = []
        if wanted("emcan"):
            spiders.append(EmcanSpider())
        if wanted("trabajocantabria"):
            spiders.append(TrabajoCantabriaSpider())
        if wanted("turijobs"):
            spiders.append(TurijobsSpider(region=normalized))
        if wanted("jobspy"):
            spiders.append(JobspySpider(region=normalized))
        if wanted("jobtoday"):
            spiders.append(JobTodaySpider(region=normalized))
        if "infojobs" in selected:
            spiders.append(InfoJobsPublicSpider(region=normalized))
        return spiders
    raise AssertionError("unreachable")
