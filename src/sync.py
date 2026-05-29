"""
fitbit-sync CLI — orchestrates fetch → map → PUT for one or more dates.

Usage:
  fitbit-sync                            # yesterday
  fitbit-sync --date 2026-05-27          # one day
  fitbit-sync --days 7                   # last N days
  fitbit-sync --from 2026-05-01 --to 2026-05-27
  fitbit-sync --dry-run                  # log payloads, skip PUT
  fitbit-sync --verbose
"""

import datetime
import json
import logging
import sys

import click

from src.fitbit_client import GoogleHealthClient
from src.intervals_client import IntervalsClient
from src.mapper import map_day


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        level=level,
        stream=sys.stderr,
    )


def _sync_date(
    fitbit: GoogleHealthClient,
    intervals: IntervalsClient,
    date: datetime.date,
    dry_run: bool,
    verbose: bool,
) -> None:
    log = logging.getLogger(__name__)
    log.info("Syncing %s", date)

    raw = fitbit.get_all(date)
    if verbose:
        log.debug("Raw API response:\n%s", json.dumps(raw, indent=2, default=str))

    payload = map_day(raw, date)
    if not payload:
        log.warning("%s — no data returned from any endpoint, skipping PUT", date)
        return

    intervals.put_wellness(date, payload, dry_run=dry_run)
    log.info("%s — done (%d fields written)", date, len(payload))


@click.command()
@click.option("--date", "single_date", default=None, help="Sync one specific date (YYYY-MM-DD).")
@click.option("--days", default=None, type=int, help="Sync the last N days.")
@click.option("--from", "from_date", default=None, help="Start of date range (YYYY-MM-DD).")
@click.option("--to", "to_date", default=None, help="End of date range (YYYY-MM-DD, inclusive).")
@click.option("--dry-run", is_flag=True, help="Log payloads but do not PUT to intervals.icu.")
@click.option("--verbose", is_flag=True, help="Enable debug logging.")
def main(
    single_date: str | None,
    days: int | None,
    from_date: str | None,
    to_date: str | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    _configure_logging(verbose)
    log = logging.getLogger(__name__)

    # Build date list
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    if single_date:
        dates = [datetime.date.fromisoformat(single_date)]
    elif days:
        dates = [today - datetime.timedelta(days=i) for i in range(1, days + 1)]
        dates.reverse()
    elif from_date and to_date:
        start = datetime.date.fromisoformat(from_date)
        end = datetime.date.fromisoformat(to_date)
        if start > end:
            raise click.BadParameter("--from must be before --to")
        delta = (end - start).days + 1
        dates = [start + datetime.timedelta(days=i) for i in range(delta)]
    else:
        dates = [yesterday]

    if dry_run:
        log.info("DRY RUN mode — no data will be written to intervals.icu")

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


if __name__ == "__main__":
    main()
