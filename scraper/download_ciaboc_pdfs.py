#!/usr/bin/env python3
"""Download weekly CIABOC court-list PDFs through 17 July 2026."""

from __future__ import annotations

import argparse
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://ciaboc.gov.lk/images/courts"
DEFAULT_START = date(2026, 1, 12)
DEFAULT_END = date(2026, 7, 17)
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "raw"


class ServiceUnavailableError(Exception):
    """Signal that CIABOC returned HTTP 503 for the current week."""


def parse_date(value: str) -> date:
    """Parse a command-line date in YYYY-MM-DD format."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Use YYYY-MM-DD."
        ) from exc


def mondays_between(start: date, end: date) -> Iterable[date]:
    """Yield every Monday whose Friday is within the requested date range."""
    current = start + timedelta(days=(7 - start.weekday()) % 7)
    while current + timedelta(days=4) <= end:
        yield current
        current += timedelta(days=7)


def candidate_urls(monday: date, friday: date) -> Iterable[str]:
    """Generate known and fallback CIABOC URL formats without duplicates."""
    start_text = monday.strftime("%Y%m%d")
    end_text = friday.strftime("%Y%m%d")
    seen: set[str] = set()

    if monday == date(2026, 1, 12) and friday == date(2026, 1, 16):
        confirmed_url = (
            "https://ciaboc.gov.lk/images/courts/2025/"
            "20260112_-_20260116.pdf"
        )
        seen.add(confirmed_url)
        yield confirmed_url

    # CIABOC has stored some January 2026 PDFs in the 2025 directory.
    folders = (str(monday.year), str(monday.year - 1))

    # Confirmed formats include:
    # 20260112_-_20260116.pdf and 20260518-_20260522.pdf
    filenames = (
        f"{start_text}-_{end_text}.pdf",
        f"{start_text}_-_{end_text}.pdf",
        f"{start_text}_-{end_text}.pdf",
        f"{start_text}_{end_text}.pdf",
    )

    for folder in folders:
        for filename in filenames:
            url = f"{BASE_URL}/{folder}/{filename}"
            if url not in seen:
                seen.add(url)
                yield url


def fetch_pdf(url: str, timeout: int, retries: int = 3) -> bytes | None:
    """Fetch a URL and return its bytes only when it is a genuine PDF."""
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; CIABOC-PDF-Research-Downloader/1.0)"
            )
        },
    )

    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                content = response.read()
                content_type = response.headers.get("Content-Type", "").lower()
                if (
                    response.status == 200
                    and content.startswith(b"%PDF-")
                    and ("pdf" in content_type or len(content) > 100)
                ):
                    return content
                return None
        except HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code == 503:
                raise ServiceUnavailableError(url) from exc
            if exc.code not in (429, 500, 502, 504):
                return None
            if attempt == retries:
                print(f"  HTTP {exc.code} after {retries} attempts: {url}")
        except (URLError, TimeoutError) as exc:
            if attempt == retries:
                print(f"  Request failed after {retries} attempts: {url} ({exc})")

        time.sleep(0.8 * attempt)

    return None


def download_week(
    monday: date,
    output_dir: Path,
    timeout: int,
) -> tuple[Path | None, str | None]:
    """Find and download one weekly PDF."""
    friday = monday + timedelta(days=4)
    output_file = output_dir / f"{monday:%Y%m%d}_-_{friday:%Y%m%d}.pdf"

    if output_file.exists() and output_file.read_bytes()[:5] == b"%PDF-":
        print(f"[SKIP] {monday} to {friday}: already downloaded")
        return output_file, "existing file"

    for url in candidate_urls(monday, friday):
        try:
            content = fetch_pdf(url, timeout=timeout)
        except ServiceUnavailableError:
            print(
                f"[SKIP] {monday} to {friday}: "
                "server returned HTTP 503; moving to next week"
            )
            return None, None
        if content is not None:
            output_file.write_bytes(content)
            print(
                f"[OK]   {monday} to {friday}: "
                f"{output_file.name} ({len(content):,} bytes)"
            )
            print(f"       Source: {url}")
            return output_file, url

    print(f"[MISS] {monday} to {friday}: no valid PDF found")
    return None, None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Download available weekly CIABOC court-list PDFs. "
            "The defaults cover 12 January to 17 July 2026."
        )
    )
    parser.add_argument(
        "--start",
        type=parse_date,
        default=DEFAULT_START,
        help="Start date in YYYY-MM-DD format (default: 2026-01-12)",
    )
    parser.add_argument(
        "--end",
        type=parse_date,
        default=DEFAULT_END,
        help="End date in YYYY-MM-DD format (default: 2026-07-17)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Download directory (default: project data/raw folder)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=25,
        help="Timeout for each request in seconds (default: 25)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="Delay between weeks in seconds (default: 0.25)",
    )
    args = parser.parse_args()

    if args.start > args.end:
        parser.error("--start must be on or before --end")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.delay < 0:
        parser.error("--delay cannot be negative")

    args.output.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    missing: list[str] = []

    weeks = list(mondays_between(args.start, args.end))
    print(
        f"Checking {len(weeks)} weekly periods from "
        f"{args.start} through {args.end}..."
    )

    for index, monday in enumerate(weeks):
        file_path, _ = download_week(
            monday=monday,
            output_dir=args.output,
            timeout=args.timeout,
        )
        if file_path is not None:
            downloaded.append(file_path)
        else:
            friday = monday + timedelta(days=4)
            period = f"{monday.isoformat()} to {friday.isoformat()}"
            missing.append(period)

        if index < len(weeks) - 1 and args.delay:
            time.sleep(args.delay)

    missing_file = args.output / "missing_weeks.txt"
    if missing:
        missing_file.write_text("\n".join(missing) + "\n", encoding="utf-8")
    elif missing_file.exists():
        missing_file.unlink()

    print("\nDownload summary")
    print(f"  Available PDFs: {len(downloaded)}")
    print(f"  Missing weeks:  {len(missing)}")
    print(f"  Output folder:  {args.output.resolve()}")
    if missing:
        print(f"  Missing list:   {missing_file.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
