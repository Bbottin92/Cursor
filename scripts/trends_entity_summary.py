#!/usr/bin/env python3
"""
Fetch a lightweight Google Trends summary for a named entity.

Notes:
  - Google Trends does not provide absolute search counts. The values returned are
    a normalized interest index (0-100) for the requested timeframe/geography.
  - For long timeframes (e.g. 2004→today), interest-over-time is typically weekly.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Callable, Optional


def _require_pytrends() -> None:
    try:
        import pytrends  # noqa: F401
    except ImportError:
        print(
            "Missing dependency: pytrends\n"
            "Install with:\n"
            "  pip3 install -r requirements.txt\n",
            file=sys.stderr,
        )
        raise


def _retry(
    fn: Callable[[], Any],
    *,
    what: str,
    attempts: int = 6,
    base_delay_s: float = 2.0,
) -> Any:
    last_exc: Optional[BaseException] = None
    for i in range(attempts):
        try:
            return fn()
        except BaseException as exc:  # intentionally broad: pytrends wraps various request errors
            last_exc = exc
            # Exponential backoff with a small cap; keeps the script usable in CI.
            delay = min(base_delay_s * (2**i), 30.0)
            print(f"[warn] {what} failed (attempt {i+1}/{attempts}); retrying in {delay:.1f}s", file=sys.stderr)
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def _iso(d: Optional[date]) -> Optional[str]:
    return None if d is None else d.isoformat()


@dataclass(frozen=True)
class InterestOverTimeSummary:
    points_total: int
    points_nonzero: int
    percent_nonzero: float
    mean: float
    median: float
    max: int
    max_dates: list[str]
    first_nonzero_date: Optional[str]


@dataclass(frozen=True)
class RegionValue:
    region: str
    value: int


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Summarize Google Trends interest for a query.")
    parser.add_argument("--term", required=True, help="Search term (e.g. a person name).")
    parser.add_argument("--start", default="2004-01-01", help="Start date (YYYY-MM-DD). Default: 2004-01-01.")
    parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date (YYYY-MM-DD). Default: today.",
    )
    parser.add_argument(
        "--geo",
        default="",
        help="Geography code (e.g. 'US'). Empty means worldwide. Default: worldwide.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Top N countries to return (non-zero only). Default: 10.",
    )
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    args = parser.parse_args(argv)

    _require_pytrends()
    from pytrends.request import TrendReq

    try:
        start_d = date.fromisoformat(args.start)
        end_d = date.fromisoformat(args.end)
    except ValueError as exc:
        print(f"Invalid date format: {exc}", file=sys.stderr)
        return 2

    if end_d < start_d:
        print("--end must be >= --start", file=sys.stderr)
        return 2

    term = args.term.strip()
    if not term:
        print("--term must be non-empty", file=sys.stderr)
        return 2

    timeframe = f"{start_d.isoformat()} {end_d.isoformat()}"

    pytrends = TrendReq(
        hl="en-US",
        tz=0,
        timeout=(10, 30),
        retries=2,
        backoff_factor=0.3,
    )

    def build_payload() -> None:
        pytrends.build_payload(
            kw_list=[term],
            cat=0,
            timeframe=timeframe,
            geo=args.geo,
            gprop="",
        )

    _retry(build_payload, what="build_payload")

    def fetch_iot():
        return pytrends.interest_over_time()

    iot = _retry(fetch_iot, what="interest_over_time")

    iot_summary: Optional[InterestOverTimeSummary] = None
    if iot is not None and not iot.empty and term in iot.columns:
        # Drop partial last row if present.
        if "isPartial" in iot.columns:
            iot = iot[~iot["isPartial"]]

        series = iot[term]
        points_total = int(series.shape[0])
        points_nonzero = int((series > 0).sum())
        percent_nonzero = (points_nonzero / points_total * 100.0) if points_total else 0.0
        mean = float(series.mean()) if points_total else 0.0
        median = float(series.median()) if points_total else 0.0
        max_val = int(series.max()) if points_total else 0

        max_dates: list[str] = []
        if points_total and max_val > 0:
            max_dates = [d.date().isoformat() for d in series[series == max_val].index.to_pydatetime()]

        first_nonzero_date: Optional[str] = None
        if points_total and points_nonzero:
            first_idx = series[series > 0].index[0]
            first_nonzero_date = first_idx.date().isoformat()

        iot_summary = InterestOverTimeSummary(
            points_total=points_total,
            points_nonzero=points_nonzero,
            percent_nonzero=percent_nonzero,
            mean=mean,
            median=median,
            max=max_val,
            max_dates=max_dates,
            first_nonzero_date=first_nonzero_date,
        )

    def fetch_countries():
        return pytrends.interest_by_region(resolution="COUNTRY", inc_low_vol=True, inc_geo_code=False)

    countries_df = _retry(fetch_countries, what="interest_by_region(COUNTRY)")

    top_countries: list[RegionValue] = []
    if countries_df is not None and not countries_df.empty and term in countries_df.columns:
        countries_series = countries_df[term].dropna()
        countries_series = countries_series[countries_series > 0].sort_values(ascending=False)
        for region, value in countries_series.head(max(args.top_n, 0)).items():
            top_countries.append(RegionValue(region=str(region), value=int(value)))

    result = {
        "term": term,
        "timeframe": {"start": start_d.isoformat(), "end": end_d.isoformat(), "google_trends_timeframe": timeframe},
        "geo": args.geo,
        "interest_over_time": None if iot_summary is None else asdict(iot_summary),
        "top_countries": [asdict(x) for x in top_countries],
    }

    out = json.dumps(result, indent=2, sort_keys=True)
    print(out)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
            f.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

