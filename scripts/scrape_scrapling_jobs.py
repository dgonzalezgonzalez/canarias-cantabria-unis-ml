"""Manual JOB TODAY collection using the same pipeline as the nightly daemon."""
from __future__ import annotations

import argparse
import subprocess
import sys

from src.canarias_uni_ml.cli import main as pipeline_main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=["canarias", "cantabria", "both"], default="both")
    parser.add_argument("--limit-per-source", type=int, default=10000)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        return subprocess.call([sys.executable, "-m", "pytest", "tests/test_jobtoday_spider.py", "-q"])
    regions = ["canarias", "cantabria"] if args.region == "both" else [args.region]
    codes = [pipeline_main(["jobs", "scrape", "--region", region, "--sources", "jobtoday",
                            "--limit-per-source", str(args.limit_per_source)]) for region in regions]
    return int(any(codes))


if __name__ == "__main__":
    raise SystemExit(main())
