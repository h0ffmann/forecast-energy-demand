"""
download_pjm.py — Download PJM hourly metered load from Data Miner 2

Fetches the `hrl_load_metered` feed from the PJM Data Miner 2 API for a
configurable date range (default: 2022-01-01 through today) and writes:

  data/raw/<REGION>_hourly.csv    Per-region legacy schema:
                                   Datetime,<REGION>_MW
                                   (compatible with the old Kaggle files,
                                    so downstream loaders need no changes)
  data/raw/pjm_hourly_raw.csv     All regions, all API columns, long format
  data/raw/header.json            Full schema: every column in the dataset
                                   plus fetch metadata

Usage:
    export PJM_API_KEY=your_subscription_key
    uv run download_pjm.py
    uv run download_pjm.py --start 2022-01-01 --end 2024-12-31
    uv run download_pjm.py --regions COMED DAYTON EKPC
    uv run download_pjm.py --list-regions

API key (free):
    1. Register at https://apiportal.pjm.com
    2. Subscribe to the "Data Miner 2" product
    3. Copy your Primary subscription key from the profile page
    4. export PJM_API_KEY=<that value>

Rate limits (PJM-enforced):
    Non-members : 6 requests / minute
    Members     : 600 requests / minute
The script throttles to the non-member limit by default and backs off on 429.

Notes:
    - hrl_load_metered is finalised data; corrections can arrive up to 90 days
      after the operating day. For the most recent weeks use hrl_load_prelim.
    - load_area allowed values are restricted to what the feed exposes today
      (10 regions). The legacy Kaggle names NI and PJM_Load are NOT available
      via this feed.
    - datetime_beginning_ept is naive local Eastern Prevailing Time and
      observes DST, so the November fall-back hour appears twice per year.
      The datetime_beginning_utc column is always unambiguous — use it as
      the primary index downstream.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_BASE = "https://api.pjm.com/api/v1"
FEED = "hrl_load_metered"
FEED_DEFINITION_URL = f"https://dataminer2.pjm.com/feed/{FEED}/definition"

# All fields the hrl_load_metered feed returns. Order matters for header.json
# and for the combined raw CSV column order.
FEED_FIELDS: list[str] = [
    "datetime_beginning_utc",
    "datetime_beginning_ept",
    "nerc_region",
    "mkt_region",
    "zone",
    "load_area",
    "mw",
    "is_verified",
]

# Mapping from friendly name (what the user types / what the output file is
# named) to the actual `zone` code the hrl_load_metered feed uses internally.
#
# The feed's `zone` values are short legacy codes (CE for ComEd, BC for BGE,
# AP for Allegheny Power, etc.) that don't match the names you'll see in PJM
# marketing material or in the old Kaggle dataset. We accept both, and also
# passthrough for any other real zone code that exists in the feed.
#
# Discovery method: sampled rowCount=5000 across 5 offsets in the ~6M-row
# dataset and collected every distinct `zone` value. 23 zones total were
# observed, listed below with their human-readable names.
REGIONS: dict[str, str] = {
    # Kaggle-compatible aliases (what downstream code / the thesis refers to)
    "AEP":     "AEP",      # American Electric Power
    "COMED":   "CE",       # Commonwealth Edison  — was NI historically
    "DAYTON":  "DAY",      # Dayton Power & Light
    "DEOK":    "DEOK",     # Duke Energy Ohio & Kentucky (integrated 2012)
    "DOM":     "DOM",      # Dominion / Virginia Electric
    "DUQ":     "DUQ",      # Duquesne Light
    "EKPC":    "EKPC",     # East Kentucky Power Cooperative (integrated 2013)
    "FE":      "ATSI",     # FirstEnergy → ATSI zone since 2011
    "PJM_LOAD":"RTO",      # RTO-wide aggregate, ≈ Kaggle PJM_Load

    # Other real zones in the feed, exposed for completeness
    "AE":      "AE",       # Atlantic City Electric
    "APS":     "AP",       # Allegheny Power Systems
    "ATSI":    "ATSI",     # American Transmission Systems, Inc.
    "BGE":     "BC",       # Baltimore Gas & Electric  (code "BC" is legacy)
    "DPL":     "DPL",      # Delmarva Power & Light
    "JCPL":    "JC",       # Jersey Central Power & Light
    "METED":   "ME",       # Met-Ed
    "PECO":    "PE",       # PECO Energy
    "PEPCO":   "PEP",      # Potomac Electric Power
    "PPL":     "PL",       # PPL Electric Utilities
    "PENELEC": "PN",       # Pennsylvania Electric
    "PSEG":    "PS",       # Public Service Electric & Gas
    "RECO":    "RECO",     # Rockland Electric
    "RTO":     "RTO",      # Same as PJM_LOAD

    # Historical aggregates/entities that still appear in the data:
    # CNCT (Conectiv, merged into AE/DPL ~2004) and GPU (General Public
    # Utilities, legacy JC+ME+PN aggregate). Not exposed by default — pass
    # them explicitly if you need them.
}

# Default region set — the 9 Kaggle-compatible names that map cleanly.
# NI, PJME, PJMW from the Kaggle dataset have no 1-to-1 equivalent in
# hrl_load_metered and are intentionally excluded.
DEFAULT_REGIONS: list[str] = [
    "AEP", "COMED", "DAYTON", "DEOK", "DOM", "DUQ", "EKPC", "FE", "PJM_LOAD",
]

# Static column documentation. Kept alongside fetched sample values in
# header.json so downstream consumers have a single source of truth.
COLUMN_DOCS: dict[str, dict[str, Any]] = {
    "datetime_beginning_utc": {
        "type": "datetime",
        "tz": "UTC",
        "description": "Hour start in UTC. Unambiguous — recommended primary index.",
    },
    "datetime_beginning_ept": {
        "type": "datetime",
        "tz": "America/New_York (naive, observes DST)",
        "description": (
            "Hour start in Eastern Prevailing Time. Naive local wall-clock. "
            "Appears duplicated on the November fall-back hour and has a "
            "one-hour gap on the March spring-forward."
        ),
    },
    "nerc_region": {
        "type": "string",
        "allowed_values": ["OTHER", "RFC", "RTO", "SERC"],
        "description": "NERC reliability region.",
    },
    "mkt_region": {
        "type": "string",
        "allowed_values": ["MIDATL", "OTHER", "RTO", "SOUTH", "WEST"],
        "description": "PJM market region.",
    },
    "zone": {
        "type": "string",
        "description": (
            "PJM transmission zone. 23 distinct values observed in the feed: "
            "AE, AEP, AP, ATSI, BC, CE, CNCT, DAY, DEOK, DOM, DPL, DUQ, EKPC, "
            "GPU, JC, ME, PE, PEP, PL, PN, PS, RECO, RTO. Use this field to "
            "filter by utility/region — NOT load_area, which is more granular."
        ),
    },
    "load_area": {
        "type": "string",
        "description": (
            "Sub-zone load area. Finer granularity than zone: AEP splits into "
            "AEPAPT/AEPIMP/AEPKPT/AEPOPT, DPL into DPL/DPLCO/EASTON, PEP into "
            "PEP/PEPCO/SMECO, etc. Zone is usually the right grain for a "
            "utility-level forecast."
        ),
    },
    "mw": {
        "type": "float",
        "unit": "MW",
        "description": "Hourly metered load in megawatts.",
    },
    "is_verified": {
        "type": "boolean",
        "description": (
            "True when the value has been verified by the electric "
            "distribution company; False when PJM has substituted an "
            "estimate."
        ),
    },
}

# Non-member rate limit is 6 req/min → 10s between calls. Members can go
# much faster; override with --request-interval 0.1 if you have a member key.
DEFAULT_REQUEST_INTERVAL_S = 10.0
MAX_ROW_COUNT = 50_000  # PJM hard cap per page


# ---------------------------------------------------------------------------
# API key handling
# ---------------------------------------------------------------------------

def _api_key() -> str | None:
    """Return the PJM Data Miner 2 subscription key or None."""
    key = os.environ.get("PJM_API_KEY") or os.environ.get(
        "PJM_SUBSCRIPTION_KEY"
    )
    if key:
        return key.strip()

    # Fall back to ~/.pjm/api_key if present (convenience for interactive use)
    key_file = Path.home() / ".pjm" / "api_key"
    if key_file.exists():
        try:
            return key_file.read_text().strip() or None
        except OSError:
            return None
    return None


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class PJMClient:
    """Thin paginated client around the Data Miner 2 REST API."""

    def __init__(
        self,
        api_key: str,
        request_interval_s: float = DEFAULT_REQUEST_INTERVAL_S,
        timeout: int = 60,
        max_retries: int = 5,
        verbose: bool = False,
    ) -> None:
        self.api_key = api_key
        self.request_interval_s = request_interval_s
        self.timeout = timeout
        self.max_retries = max_retries
        self.verbose = verbose

        self._session = requests.Session()
        self._session.headers.update({
            "Ocp-Apim-Subscription-Key": api_key,
            "Accept": "application/json",
            "User-Agent": "tcc-energy-forecast/0.2",
        })
        self._last_request_ts: float = 0.0

    # -------- low-level GET with throttle + retry ---------------------------

    def _throttle(self) -> None:
        """Sleep enough to respect request_interval_s between calls."""
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < self.request_interval_s:
            time.sleep(self.request_interval_s - elapsed)
        self._last_request_ts = time.monotonic()

    def _get(self, url: str, params: dict | None = None) -> dict:
        delay = 2.0
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            if self.verbose:
                prep = requests.Request("GET", url, params=params).prepare()
                log.info("  GET %s", prep.url)
            try:
                resp = self._session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                log.warning("  network error (attempt %d/%d): %s",
                            attempt, self.max_retries, exc)
                time.sleep(delay)
                delay *= 2
                continue

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", delay))
                log.warning("  rate-limited by PJM, sleeping %ds "
                            "(attempt %d/%d)", retry_after, attempt,
                            self.max_retries)
                time.sleep(retry_after)
                delay *= 2
                continue

            if resp.status_code >= 500:
                log.warning("  server error %s (attempt %d/%d), retrying",
                            resp.status_code, attempt, self.max_retries)
                time.sleep(delay)
                delay *= 2
                continue

            if not resp.ok:
                # 4xx other than 429 — don't retry, surface the error body
                body = resp.text[:500]
                raise RuntimeError(
                    f"PJM API error {resp.status_code} for {url}: {body}"
                )

            if self.verbose:
                snippet = resp.text[:800].replace("\n", " ")
                log.info("  ← HTTP %s  body[:800]: %s",
                         resp.status_code, snippet)

            return resp.json()

        raise RuntimeError(
            f"PJM API unreachable after {self.max_retries} retries: {url}"
        )

    # -------- paginated fetch -----------------------------------------------

    def fetch(
        self,
        zone_code: str,
        start: datetime,
        end: datetime,
    ) -> Iterator[dict]:
        """
        Yield every row of hrl_load_metered for one PJM zone in [start, end].

        PJM caps date-range filters at ~366 days, so callers should chunk
        long windows into yearly pieces.

        Pagination follows the `links[rel="next"]` link returned by the API.
        """
        params = {
            "rowCount": MAX_ROW_COUNT,
            "startRow": 1,
            "sort": "datetime_beginning_ept",
            "order": "asc",
            "fields": ",".join(FEED_FIELDS),
            "zone": zone_code,
            # Filter syntax: "<start> to <end>" on the _ept column.
            # Docs say MM/DD/YYYY HH:MM but the server also accepts ISO and
            # other clients (gridstatus, rzwink/pjm_dataminer) use ISO in
            # practice — fewer locale/escaping surprises through query strings.
            "datetime_beginning_ept": (
                f"{start.strftime('%Y-%m-%dT%H:%M:%S')}"
                f" to {end.strftime('%Y-%m-%dT%H:%M:%S')}"
            ),
        }

        url: str | None = f"{API_BASE}/{FEED}"
        page = 0
        total_expected: int | None = None
        total_seen = 0

        while url is not None:
            page += 1
            page_params = params if page == 1 else None
            payload = self._get(url, params=page_params)

            if total_expected is None:
                total_expected = int(payload.get("totalRows", 0))
                log.info("    %s: %d rows expected across %d page(s)",
                         zone_code, total_expected,
                         max(1, -(-total_expected // MAX_ROW_COUNT)))
                if total_expected == 0:
                    # Surface the full request URL so the user can paste it
                    # into a browser and eyeball what PJM is actually seeing.
                    prep = requests.Request(
                        "GET", url, params=page_params
                    ).prepare()
                    log.warning("    request returned 0 rows. URL was: %s",
                                prep.url)

            items = payload.get("items", [])
            total_seen += len(items)
            for row in items:
                yield row

            url = _next_link(payload)

        if total_expected and total_seen != total_expected:
            log.warning("    %s: expected %d rows but got %d",
                        zone_code, total_expected, total_seen)


def _next_link(payload: dict) -> str | None:
    """Extract the pagination 'next' href from a Data Miner 2 response."""
    for link in payload.get("links", []) or []:
        if link.get("rel") == "next" and link.get("href"):
            return link["href"]
    return None


# ---------------------------------------------------------------------------
# Date chunking
# ---------------------------------------------------------------------------

def year_chunks(
    start: datetime,
    end: datetime,
) -> Iterator[tuple[datetime, datetime]]:
    """
    Yield (chunk_start, chunk_end) pairs covering [start, end], each no wider
    than one calendar year — PJM's date-range filter maxes out at 366 days.
    """
    cursor = start
    while cursor < end:
        year_end = datetime(cursor.year, 12, 31, 23, 59)
        chunk_end = min(year_end, end)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(minutes=1)


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def _legacy_datetime(row: dict) -> str:
    """Return the datetime in the same format the Kaggle files used."""
    # Kaggle used "YYYY-MM-DD HH:MM:SS" from the EPT (local) column.
    ept = row.get("datetime_beginning_ept", "")
    if not ept:
        return ""
    # Incoming format is ISO-like, e.g. "2022-01-01T00:00:00" or with a "Z".
    try:
        dt = datetime.fromisoformat(ept.replace("Z", "+00:00").rstrip("Z"))
    except ValueError:
        return ept
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def write_region_csv(out_dir: Path, region: str, rows: list[dict]) -> Path:
    """
    Write per-region file in the legacy Kaggle schema:  Datetime,<REGION>_MW
    """
    path = out_dir / f"{region}_hourly.csv"
    col = f"{region}_MW"
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Datetime", col])
        for r in rows:
            writer.writerow([_legacy_datetime(r), r.get("mw", "")])
    return path


def append_raw_csv(
    out_dir: Path,
    rows: list[dict],
    first_write: bool,
) -> Path:
    """
    Append one region's rows to the combined raw long-format CSV.

    Columns: all FEED_FIELDS, in canonical order.
    """
    path = out_dir / "pjm_hourly_raw.csv"
    mode = "w" if first_write else "a"
    with path.open(mode, newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=FEED_FIELDS, extrasaction="ignore"
        )
        if first_write:
            writer.writeheader()
        writer.writerows(rows)
    return path


def write_header_json(
    out_dir: Path,
    regions_fetched: list[str],
    start: datetime,
    end: datetime,
    sample_row: dict | None,
    row_counts: dict[str, int],
) -> Path:
    """
    Write a schema descriptor for every column in the dataset plus
    run-specific metadata (fetch window, rows per region, source).
    """
    # Enrich static docs with an example value pulled from the first row we
    # actually saw, so consumers can sanity-check types without opening a CSV.
    columns: dict[str, dict[str, Any]] = {}
    for name in FEED_FIELDS:
        spec = dict(COLUMN_DOCS.get(name, {"type": "string"}))
        if sample_row is not None and name in sample_row:
            spec["example"] = sample_row[name]
        columns[name] = spec

    header = {
        "feed": FEED,
        "source": "PJM Data Miner 2 API",
        "api_url": f"{API_BASE}/{FEED}",
        "documentation": FEED_DEFINITION_URL,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date_range": {
            "start": start.strftime("%Y-%m-%d %H:%M"),
            "end": end.strftime("%Y-%m-%d %H:%M"),
            "timezone": "America/New_York (EPT, used in filter)",
        },
        "regions_available": {
            "friendly_to_zone": REGIONS,
            "default_set": DEFAULT_REGIONS,
        },
        "regions_fetched": regions_fetched,
        "row_counts": row_counts,
        "columns": columns,
        "notes": [
            "hrl_load_metered is finalised data; values can be adjusted for "
            "up to 90 days after the operating day.",
            "For recent uncorrected data, see the hrl_load_prelim feed.",
            "datetime_beginning_ept is naive local time and observes DST — "
            "deduplicate the November fall-back hour on datetime_beginning_utc.",
            "The feed's zone field uses short legacy codes (CE for ComEd, BC "
            "for BGE, AP for APS, etc.) — see regions_available.friendly_to_zone "
            "for the mapping. load_area is a finer-grained sub-zone identifier.",
            "Kaggle dataset region names NI, PJME, PJMW have no direct "
            "equivalent in this feed and are not included in the default set.",
        ],
    }

    path = out_dir / "header.json"
    path.write_text(json.dumps(header, indent=2, default=str))
    return path


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def download(
    api_key: str,
    out_dir: Path,
    regions: list[str],
    start: datetime,
    end: datetime,
    request_interval_s: float,
    verbose: bool = False,
) -> None:
    client = PJMClient(
        api_key=api_key,
        request_interval_s=request_interval_s,
        verbose=verbose,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    row_counts: dict[str, int] = defaultdict(int)
    sample_row: dict | None = None
    raw_written = False

    for i, region in enumerate(regions, 1):
        # Translate friendly name (e.g. "COMED") to the feed's real zone code
        # (e.g. "CE"). Unknown values pass through unchanged, so callers can
        # also use raw codes like "CE" or "BC" directly.
        zone_code = REGIONS.get(region, region)
        log.info("[%d/%d] Downloading %s  (zone=%s, %s → %s)",
                 i, len(regions), region, zone_code,
                 start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        region_rows: list[dict] = []

        for chunk_start, chunk_end in year_chunks(start, end):
            log.info("  chunk %s → %s",
                     chunk_start.strftime("%Y-%m-%d"),
                     chunk_end.strftime("%Y-%m-%d"))
            for row in client.fetch(zone_code, chunk_start, chunk_end):
                region_rows.append(row)
                if sample_row is None:
                    sample_row = row

        if not region_rows:
            log.warning("  no rows returned for %s (zone=%s)", region, zone_code)
            continue

        # Per-region file named after the user's friendly name, NOT the
        # internal zone code — downstream code/thesis references "COMED",
        # not "CE".
        region_path = write_region_csv(out_dir, region, region_rows)
        log.info("  saved %s  (%d rows, %s)", region_path.name,
                 len(region_rows), _human_size(region_path.stat().st_size))

        # Append to the combined raw long-format CSV
        append_raw_csv(out_dir, region_rows, first_write=not raw_written)
        raw_written = True
        row_counts[region] = len(region_rows)

    header_path = write_header_json(
        out_dir=out_dir,
        regions_fetched=list(row_counts.keys()),
        start=start,
        end=end,
        sample_row=sample_row,
        row_counts=dict(row_counts),
    )
    log.info("saved %s", header_path.name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _human_size(n: int) -> str:
    size: float = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _parse_date(s: str) -> datetime:
    """Parse YYYY-MM-DD into a midnight-local datetime."""
    return datetime.strptime(s, "%Y-%m-%d")


def print_summary(out_dir: Path, regions: list[str]) -> None:
    ok = [r for r in regions if (out_dir / f"{r}_hourly.csv").exists()]
    missing = [r for r in regions if r not in ok]

    log.info("")
    log.info("--- Download summary ---")
    log.info("Output directory : %s", out_dir.resolve())
    log.info("Available (%d/%d) : %s", len(ok), len(regions), ok or "none")
    if missing:
        log.warning("Missing          : %s", missing)

    raw = out_dir / "pjm_hourly_raw.csv"
    header = out_dir / "header.json"
    if raw.exists():
        log.info("Combined raw     : %s  (%s)", raw.name,
                 _human_size(raw.stat().st_size))
    if header.exists():
        log.info("Schema           : %s  (%s)", header.name,
                 _human_size(header.stat().st_size))

    if ok:
        log.info("")
        log.info("Next step:")
        log.info("  uv run baseline.py --data %s/%s_hourly.csv",
                 out_dir, ok[0])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download PJM hourly metered load from Data Miner 2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    parser.add_argument(
        "--out", type=Path, default=Path("data/raw"),
        help="Output directory (default: data/raw)",
    )
    parser.add_argument(
        "--regions", nargs="+", default=None, metavar="REGION",
        help=(
            "Regions to download. Default: the 9 Kaggle-compatible names "
            f"{DEFAULT_REGIONS}. Also accepts other friendly names "
            f"(BGE, JCPL, PSEG, …) or raw zone codes (CE, BC, …). "
            "Use --list-regions for the full mapping."
        ),
    )
    parser.add_argument(
        "--start", type=_parse_date, default=_parse_date("2022-01-01"),
        help="Start date, inclusive, YYYY-MM-DD (default: 2022-01-01)",
    )
    parser.add_argument(
        "--end", type=_parse_date, default=today,
        help="End date, inclusive, YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--request-interval", type=float, dest="request_interval",
        default=DEFAULT_REQUEST_INTERVAL_S,
        help=(
            "Seconds between API requests. Default 10s respects the 6/min "
            "non-member limit; set to 0.1 if you have a member key (600/min)."
        ),
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print each outgoing request URL (useful for debugging 0-row responses)",
    )
    parser.add_argument(
        "--list-regions", action="store_true",
        help="Print available region names and exit",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    if args.list_regions:
        print("Region name → feed zone code")
        print("-" * 40)
        for friendly, zone in REGIONS.items():
            marker = "  (default)" if friendly in DEFAULT_REGIONS else ""
            print(f"  {friendly:10s} → {zone}{marker}")
        print()
        print("You can also pass a raw zone code directly (e.g. --regions CE BC).")
        sys.exit(0)

    # Validate regions. Accept either friendly names from REGIONS or raw
    # zone codes (raw codes pass through unchanged to the API).
    regions: list[str] = args.regions or DEFAULT_REGIONS
    known = set(REGIONS.keys()) | set(REGIONS.values())
    unknown = set(regions) - known
    if unknown:
        log.warning(
            "Regions not in known mapping, will try as raw zone codes: %s",
            sorted(unknown),
        )

    # Validate date range
    if args.end < args.start:
        log.error("--end (%s) is before --start (%s)",
                  args.end.date(), args.start.date())
        sys.exit(1)

    # Require API key
    api_key = _api_key()
    if not api_key:
        log.error(
            "PJM API key not found. Set PJM_API_KEY environment variable:\n"
            "  export PJM_API_KEY=your_subscription_key\n"
            "Register for a free key at https://apiportal.pjm.com and "
            "subscribe to the 'Data Miner 2' product."
        )
        sys.exit(1)

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    log.info("Output directory : %s", out_dir.resolve())
    log.info("Date range       : %s → %s",
             args.start.date(), args.end.date())
    log.info("Regions          : %s", regions)
    log.info("Request interval : %.1fs", args.request_interval)

    try:
        download(
            api_key=api_key,
            out_dir=out_dir,
            regions=regions,
            start=args.start,
            end=args.end,
            request_interval_s=args.request_interval,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        log.error("Interrupted by user")
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 - surfaces to CLI
        log.error("Download failed: %s", exc)
        sys.exit(1)

    print_summary(out_dir, regions)


if __name__ == "__main__":
    main()