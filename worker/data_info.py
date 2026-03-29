"""Data Info Scanner -- scans historical data files and reports date ranges.

Discovers data files in HIST_DATA_PATH, extracts first/last dates from each,
and reports results back to the API so instrument records get updated with
data_from / data_to timestamps.
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from worker.config import Config

logger = logging.getLogger("irt-worker.data-info")

# File patterns in priority order (highest first)
_FILE_PATTERNS = [
    re.compile(r"^(@?)(.+)_1M_edit\.txt$", re.IGNORECASE),
    re.compile(r"^(@?)(.+)_1M\.txt$", re.IGNORECASE),
    re.compile(r"^(@?)(.+)\.csv$", re.IGNORECASE),
]

# Date formats to try when parsing (order matters — most likely first)
_DATE_FORMATS = [
    "%d/%m/%Y",   # DD/MM/YYYY  (the actual format in these files)
    "%m/%d/%Y",   # MM/DD/YYYY
    "%Y-%m-%d",   # ISO 8601
]

# Keywords that signal a header line
_HEADER_KEYWORDS = {"date", "time", "open", "high", "low", "close", "volume", "vol"}


def _is_header(line: str) -> bool:
    """Return True if the line looks like a CSV header rather than data."""
    stripped = line.strip().strip('"').lower()
    if not stripped:
        return True
    # If the first non-quote character is not a digit, likely a header
    first_char = stripped[0]
    if not first_char.isdigit():
        return True
    # Check for common header keywords
    lower = line.lower()
    if any(kw in lower for kw in _HEADER_KEYWORDS):
        return True
    return False


def _parse_date_from_line(line: str) -> Optional[datetime]:
    """Extract a date from the first field(s) of a CSV line.

    Handles two layouts:
    - Separate Date,Time columns: ``27/05/2001,17:30,...``
    - Combined datetime column: ``2001-05-27 17:30:00,...``
    """
    line = line.strip()
    if not line:
        return None

    # Strip surrounding quotes from fields
    parts = [p.strip().strip('"') for p in line.split(",")]
    if not parts:
        return None

    date_str = parts[0]

    # Try combining first two fields as Date + Time
    time_str = parts[1] if len(parts) > 1 else ""

    for fmt in _DATE_FORMATS:
        # Try date+time combined
        if time_str:
            for time_fmt in ("%H:%M", "%H:%M:%S"):
                try:
                    return datetime.strptime(f"{date_str} {time_str}", f"{fmt} {time_fmt}")
                except ValueError:
                    continue
        # Try date-only
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # Try ISO with time already in date_str  (e.g. "2001-05-27 17:30:00")
    for iso_fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str, iso_fmt)
        except ValueError:
            continue

    return None


def _read_first_data_line(filepath: Path) -> Optional[str]:
    """Read the first non-header line from a file."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if _is_header(line):
                continue
            return line.strip()
    return None


def _read_last_line(filepath: Path) -> Optional[str]:
    """Read the last non-empty line from a file using seek from the end.

    Efficient for large files — does not load the whole file.
    """
    try:
        with open(filepath, "rb") as fh:
            # Seek to end
            fh.seek(0, os.SEEK_END)
            file_size = fh.tell()
            if file_size == 0:
                return None

            # Read a chunk from the end (up to 4KB should be plenty)
            chunk_size = min(4096, file_size)
            fh.seek(file_size - chunk_size, os.SEEK_SET)
            chunk = fh.read(chunk_size).decode("utf-8", errors="replace")

            # Split into lines and find last non-empty
            lines = chunk.splitlines()
            for line in reversed(lines):
                stripped = line.strip()
                if stripped and not _is_header(stripped):
                    return stripped
    except OSError as exc:
        logger.warning("Error seeking last line of %s: %s", filepath, exc)
    return None


def scan_data_files(config: Config) -> List[dict]:
    """Scan hist_data_path for data files and extract date ranges.

    Returns a list of ``{symbol: str, data_from: str, data_to: str}``
    with ISO-format date strings.
    """
    data_dir = Path(config.hist_data_path)

    if not data_dir.is_dir():
        raise FileNotFoundError(
            f"HIST_DATA_PATH directory does not exist: {config.hist_data_path}"
        )

    # Discover files — for each symbol keep only highest-priority match
    # symbol -> (priority_index, filepath)
    symbol_files: dict[str, tuple[int, Path]] = {}

    for entry in data_dir.iterdir():
        if not entry.is_file():
            continue

        for priority, pattern in enumerate(_FILE_PATTERNS):
            m = pattern.match(entry.name)
            if m:
                symbol = m.group(2)  # group(1) is the optional '@'
                existing = symbol_files.get(symbol)
                if existing is None or priority < existing[0]:
                    symbol_files[symbol] = (priority, entry)
                break  # matched highest applicable pattern for this file

    results: List[dict] = []

    for symbol, (_priority, filepath) in sorted(symbol_files.items()):
        try:
            first_line = _read_first_data_line(filepath)
            last_line = _read_last_line(filepath)

            if not first_line or not last_line:
                logger.warning("Empty or header-only file, skipping: %s", filepath.name)
                continue

            date_from = _parse_date_from_line(first_line)
            date_to = _parse_date_from_line(last_line)

            if date_from is None:
                logger.warning("Cannot parse start date from %s: %r", filepath.name, first_line[:80])
                continue
            if date_to is None:
                logger.warning("Cannot parse end date from %s: %r", filepath.name, last_line[:80])
                continue

            results.append({
                "symbol": symbol,
                "data_from": date_from.isoformat(),
                "data_to": date_to.isoformat(),
            })
            logger.info(
                "Scanned %s -> %s: %s to %s",
                filepath.name, symbol, date_from.date(), date_to.date(),
            )

        except Exception as exc:
            logger.warning("Error scanning %s, skipping: %s", filepath.name, exc)
            continue

    logger.info("Scan complete: %d symbols found", len(results))
    return results


def execute_scan_job(job: dict, config: Config) -> None:
    """Execute a scan-data job end-to-end.

    1. Scan files using scan_data_files.
    2. POST results to the API.
    3. On error, PATCH fail endpoint.

    This function never raises — all exceptions are caught and reported
    so the orchestrator loop continues.
    """
    job_id = job["id"]
    logger.info("Starting scan job %d", job_id)

    try:
        results = scan_data_files(config)

        # POST results to API
        resp = config.session.post(
            f"{config.api_url}/api/instruments/scan-data/{job_id}/results",
            json={"results": results},
            timeout=30,
        )
        resp.raise_for_status()
        logger.info("Scan job %d completed — %d results posted", job_id, len(results))

    except FileNotFoundError as exc:
        error_msg = str(exc)
        logger.error("Scan job %d failed: %s", job_id, error_msg)
        _report_scan_failure(config, job_id, error_msg)

    except Exception as exc:
        error_msg = str(exc)
        logger.error("Scan job %d failed: %s", job_id, error_msg, exc_info=True)
        _report_scan_failure(config, job_id, error_msg)


def _report_scan_failure(config: Config, job_id: int, error_message: str) -> None:
    """Mark a scan job as failed via the API."""
    truncated = error_message[-2000:] if len(error_message) > 2000 else error_message
    try:
        resp = config.session.patch(
            f"{config.api_url}/api/instruments/scan-data/{job_id}/fail",
            json={"error_message": truncated},
            timeout=15,
        )
        resp.raise_for_status()
    except Exception:
        logger.exception("Failed to report scan failure for job %d", job_id)
