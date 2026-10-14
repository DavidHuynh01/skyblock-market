"""How many minutes the collector captured, per UTC day.

    python tools/coverage.py <bucket>

Runs with your own AWS credentials (it lists the bucket, which the collector
itself is not allowed to do). The first day counts from the first file, and
today counts only the minutes that have finished.
"""
import re
import sys
from datetime import datetime, time, timedelta, timezone

_STAMP = re.compile(r"(\d{8}T\d{4}Z)\.jsonl\.gz$")


def minute_of(key):
    stamp = _STAMP.search(key).group(1)
    return datetime.strptime(stamp, "%Y%m%dT%H%MZ").replace(tzinfo=timezone.utc)


def coverage(keys, now):
    """[(date, minutes_captured, minutes_expected)], from the first file's day to now's."""
    minutes = sorted({minute_of(k) for k in keys})
    if not minutes:
        return []
    first, now_minute = minutes[0], now.replace(second=0, microsecond=0)
    rows, day = [], first.date()
    while day <= now.date():
        day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        start, end = max(day_start, first), min(day_start + timedelta(days=1), now_minute)
        expected = max(0, int((end - start).total_seconds() // 60))
        captured = sum(1 for m in minutes if start <= m < end)
        rows.append((day.isoformat(), captured, expected))
        day += timedelta(days=1)
    return rows


def main(bucket):
    import boto3  # only the live report needs AWS; the tests don't

    pages = boto3.client("s3").get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="raw/")
    keys = [obj["Key"] for page in pages for obj in page.get("Contents", [])]
    rows = coverage(keys, datetime.now(timezone.utc))
    for day, captured, expected in rows:
        pct = 100 * captured / expected if expected else 100.0
        print(f"{day}  {captured:>5} / {expected:<5} {pct:6.2f}%")
    total_captured, total_expected = sum(r[1] for r in rows), sum(r[2] for r in rows)
    if total_expected:
        print(f"overall     {total_captured} / {total_expected}  {100 * total_captured / total_expected:.2f}%")


if __name__ == "__main__":
    main(sys.argv[1])
