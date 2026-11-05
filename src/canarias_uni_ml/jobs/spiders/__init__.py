from .base import SpiderError
from .emcan import EmcanSpider
from .indeed import IndeedSpider
from .indeed_api import IndeedApiSpider
from .infojobs_public import InfoJobsPublicSpider
from .jobspy_spider import JobspySpider
from .jobtoday import JobTodaySpider
from .sce import SCESpider
from .trabajocantabria import TrabajoCantabriaSpider
from .turijobs import TurijobsSpider

__all__ = [
    "IndeedApiSpider",
    "IndeedSpider",
    "InfoJobsPublicSpider",
    "JobspySpider",
    "JobTodaySpider",
    "EmcanSpider",
    "SCESpider",
    "SpiderError",
    "TrabajoCantabriaSpider",
    "TurijobsSpider",
]
