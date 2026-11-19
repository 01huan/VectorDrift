"""Check a run of daily-challenge maps (not a test; run it by hand).

    python tools/check_daily.py                       # 365 days from today
    python tools/check_daily.py --start 2027-01-01 --days 30

Prints how often the fallback map was needed, the average number of
generation attempts, the slowest day and how the templates are spread.
Generation only: no window, no save files.
"""

import argparse
import os
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")      # config.py must not open SDL video
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vector_drift.daily_level import daily_today, generate_daily  # noqa: E402


def check(start, days, out=print):
    fallbacks, attempts, templates = [], [], Counter()
    slowest_day, slowest = None, -1.0
    began = time.perf_counter()
    for offset in range(days):
        day = start + timedelta(days=offset)
        t0 = time.perf_counter()
        daily = generate_daily(day)
        spent = time.perf_counter() - t0
        if spent > slowest:
            slowest_day, slowest = day, spent
        if daily.is_fallback:
            fallbacks.append(day)
        else:
            attempts.append(daily.attempts)
            templates[daily.template] += 1
    total = time.perf_counter() - began

    out(f"Days checked:      {days} ({start} .. {start + timedelta(days=days - 1)})")
    out(f"Fallback maps:     {len(fallbacks)}"
        + (f"  ({', '.join(str(d) for d in fallbacks)})" if fallbacks else ""))
    if attempts:
        out(f"Average attempts:  {sum(attempts) / len(attempts):.2f}"
            f"  (max {max(attempts)}, generated maps only)")
    out(f"Slowest day:       {slowest_day}  {slowest:.2f} s")
    out(f"Total time:        {total:.1f} s  ({total / days:.2f} s per day)")
    out("Templates:         " + ", ".join(
        f"{name} {count} ({count / days:.1%})" for name, count in templates.most_common()))
    return len(fallbacks)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", type=date.fromisoformat, default=None,
                        help="first day, YYYY-MM-DD (default: today in UTC+8)")
    parser.add_argument("--days", type=int, default=365, help="number of days (default 365)")
    args = parser.parse_args(argv)
    if args.days < 1:
        parser.error("--days must be at least 1")
    check(args.start or daily_today(), args.days)
    return 0


if __name__ == "__main__":
    sys.exit(main())
