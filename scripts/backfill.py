"""
Idempotent backfill for the last N days (default: 30).

Usage:
  uv run python scripts/backfill.py --days 30
  uv run python scripts/backfill.py --days 30 --dry-run
"""

import datetime
import logging
import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.fitbit_client import GoogleHealthClient
from src.intervals_client import IntervalsClient
from src.mapper import map_day
from src.sync import _configure_logging, _sync_date


@click.command()
@click.option("--days", default=30, show_default=True, help="Number of days to backfill.")
@click.option("--dry-run", is_flag=True, help="Log payloads, skip PUT.")
@click.option("--verbose", is_flag=True)
def main(days: int, dry_run: bool, verbose: bool) -> None:
    _configure_logging(verbose)
    log = logging.getLogger(__name__)

    today = datetime.date.today()
    dates = [today - datetime.timedelta(days=i) for i in range(1, days + 1)]
    dates.reverse()

    log.info("Backfilling %d days: %s → %s", days, dates[0], dates[-1])
    if dry_run:
        log.info("DRY RUN mode")

    fitbit = GoogleHealthClient()
    intervals = IntervalsClient()

    errors = []
    for d in dates:
        try:
            _sync_date(fitbit, intervals, d, dry_run=dry_run, verbose=verbose)
        except Exception as e:
            log.error("%s failed: %s", d, e)
            errors.append((d, e))

    if errors:
        log.error("%d date(s) failed", len(errors))
        sys.exit(1)
    else:
        log.info("Backfill complete.")


if __name__ == "__main__":
    main()
