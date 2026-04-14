"""
download_pjm.py — Download PJM Hourly Energy Consumption data

Strategies (tried in order):
  1. Kaggle Python API — uses KAGGLE_USERNAME + KAGGLE_KEY env vars,
                         OR ~/.kaggle/kaggle.json
  2. GitHub mirror    — panambY/Hourly_Energy_Consumption (no auth)

Usage:
    uv run download_pjm.py
    uv run download_pjm.py --out data/raw --regions COMED DAYTON EKPC
    uv run download_pjm.py --strategy direct
    uv run download_pjm.py --list-regions

Kaggle setup (optional, enables strategy 1):
    export KAGGLE_USERNAME=your_username
    export KAGGLE_KEY=your_api_key        # from kaggle.com/settings → API
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import zipfile
from io import BytesIO
from pathlib import Path

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

KAGGLE_DATASET = "robikscube/hourly-energy-consumption"

# Correct mirror: panambY repo, files live under data/
GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com"
    "/panambY/Hourly_Energy_Consumption/master/data"
)

ALL_REGIONS = [
    "AEP",
    "COMED",
    "DAYTON",
    "DEOK",
    "DOM",
    "DUQ",
    "EKPC",
    "FE",
    "NI",
    "PJME",
    "PJMW",
    "PJM_Load",
]

# ---------------------------------------------------------------------------
# Kaggle credentials
# ---------------------------------------------------------------------------

def _kaggle_creds() -> tuple[str, str] | None:
    """
    Return (username, key) from environment variables or ~/.kaggle/kaggle.json.
    Returns None if neither source is available.
    """
    # 1. Environment variables (set by user or CI)
    username = os.environ.get("KAGGLE_USERNAME")
    key = os.environ.get("KAGGLE_KEY")
    if username and key:
        return username, key

    # 2. Credentials file
    creds_file = Path.home() / ".kaggle" / "kaggle.json"
    if creds_file.exists():
        import json
        try:
            data = json.loads(creds_file.read_text())
            u, k = data.get("username"), data.get("key")
            if u and k:
                return u, k
        except (json.JSONDecodeError, OSError):
            pass

    return None


# ---------------------------------------------------------------------------
# Strategy 1 — Kaggle API (requests-based, no CLI needed)
# ---------------------------------------------------------------------------

def download_via_kaggle(out_dir: Path) -> bool:
    """
    Download the dataset zip via the Kaggle REST API using HTTP Basic Auth.

    Returns True on success, False if credentials are missing or request fails.
    Does NOT require the kaggle CLI — uses the API directly with requests.
    """
    creds = _kaggle_creds()
    if creds is None:
        log.warning(
            "Kaggle credentials not found.\n"
            "  Option A — environment variables (recommended):\n"
            "    export KAGGLE_USERNAME=your_username\n"
            "    export KAGGLE_KEY=your_api_key\n"
            "  Option B — credentials file:\n"
            "    1. Go to https://www.kaggle.com/settings → API → Create New Token\n"
            "    2. Save the file to ~/.kaggle/kaggle.json\n"
            "    3. chmod 600 ~/.kaggle/kaggle.json\n"
            "  Falling back to direct download."
        )
        return False

    username, key = creds
    url = f"https://www.kaggle.com/api/v1/datasets/download/{KAGGLE_DATASET}"
    log.info("Downloading via Kaggle API: %s", KAGGLE_DATASET)

    try:
        resp = requests.get(url, auth=(username, key), timeout=120, stream=True)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        log.error("Kaggle API error: HTTP %s — check credentials", exc.response.status_code)
        return False
    except requests.RequestException as exc:
        log.error("Kaggle API network error: %s", exc)
        return False

    # Stream zip into memory then extract
    log.info("Extracting zip archive...")
    content = BytesIO(resp.content)
    try:
        with zipfile.ZipFile(content) as zf:
            for name in zf.namelist():
                if name.endswith(".csv"):
                    dest = out_dir / Path(name).name
                    dest.write_bytes(zf.read(name))
                    log.info("  Saved: %s  (%s)", dest.name, _human_size(dest.stat().st_size))
    except zipfile.BadZipFile:
        log.error("Downloaded file is not a valid zip — Kaggle may have returned an error page.")
        return False

    return True


# ---------------------------------------------------------------------------
# Strategy 2 — Direct GitHub mirror
# ---------------------------------------------------------------------------

def download_direct(
    out_dir: Path,
    regions: list[str],
    timeout: int = 30,
) -> None:
    """
    Download individual region CSVs from the panambY GitHub mirror.

    No authentication required.
    URL pattern: GITHUB_RAW_BASE/{REGION}_hourly.csv
    """
    log.info("Downloading %d region(s) from GitHub mirror...", len(regions))

    session = requests.Session()
    session.headers["User-Agent"] = "tcc-energy-forecast/0.1"

    failed: list[str] = []

    for region in regions:
        filename = f"{region}_hourly.csv"
        url = f"{GITHUB_RAW_BASE}/{filename}"
        dest = out_dir / filename

        if dest.exists() and dest.stat().st_size > 0:
            log.info("  Already exists, skipping: %s", filename)
            continue

        log.info("  Downloading: %s", filename)
        try:
            resp = session.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()

            with dest.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=65_536):
                    fh.write(chunk)

            log.info("  Saved: %s  (%s)", dest.name, _human_size(dest.stat().st_size))

        except requests.HTTPError as exc:
            log.error("  HTTP %s for %s", exc.response.status_code, filename)
            failed.append(region)
        except requests.RequestException as exc:
            log.error("  Network error for %s: %s", filename, exc)
            failed.append(region)

    if failed:
        log.warning("Could not download: %s", failed)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n //= 1024
    return f"{n:.1f} TB"


def print_summary(out_dir: Path, regions: list[str]) -> None:
    ok = [r for r in regions if (out_dir / f"{r}_hourly.csv").exists()]
    missing = [r for r in regions if r not in ok]

    log.info("\n--- Download summary ---")
    log.info("Output directory : %s", out_dir.resolve())
    log.info("Available (%d/%d) : %s", len(ok), len(regions), ok or "none")
    if missing:
        log.warning("Missing          : %s", missing)
    if ok:
        example = ok[0]
        log.info(
            "\nNext step:\n"
            "  uv run baseline.py --data %s/%s_hourly.csv",
            out_dir, example,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download PJM Hourly Energy Consumption CSVs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--out", type=Path, default=Path("data/raw"),
        help="Output directory (default: data/raw)",
    )
    parser.add_argument(
        "--regions", nargs="+", default=None, metavar="REGION",
        help=f"Regions to download (default: all). Available: {', '.join(ALL_REGIONS)}",
    )
    parser.add_argument(
        "--strategy", choices=["auto", "kaggle", "direct"], default="auto",
        help=(
            "auto: try Kaggle first, fall back to direct | "
            "kaggle: requires credentials | "
            "direct: GitHub mirror, no auth needed"
        ),
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
        print("Available regions:")
        for r in ALL_REGIONS:
            print(f"  {r}")
        sys.exit(0)

    # Validate regions
    regions: list[str] = args.regions or ALL_REGIONS
    unknown = set(regions) - set(ALL_REGIONS)
    if unknown:
        log.error("Unknown regions: %s. Use --list-regions to see valid names.", unknown)
        sys.exit(1)

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    log.info("Output directory: %s", out_dir.resolve())

    strategy: str = args.strategy

    if strategy in ("auto", "kaggle"):
        success = download_via_kaggle(out_dir)
        if success:
            print_summary(out_dir, regions)
            return
        if strategy == "kaggle":
            log.error("Kaggle strategy failed. Exiting.")
            sys.exit(1)
        log.info("Trying direct download...")

    download_direct(out_dir, regions)
    print_summary(out_dir, regions)


if __name__ == "__main__":
    main()