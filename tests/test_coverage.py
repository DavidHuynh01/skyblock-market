from datetime import datetime, timedelta, timezone

from tools.coverage import coverage, minute_of

UTC = timezone.utc


def key(dt):
    return f"raw/date={dt:%Y-%m-%d}/hour={dt:%H}/{dt:%Y%m%dT%H%MZ}.jsonl.gz"


def test_minute_is_read_from_the_file_name():
    assert minute_of(key(datetime(2026, 10, 12, 4, 34, tzinfo=UTC))) == datetime(2026, 10, 12, 4, 34, tzinfo=UTC)


def test_first_day_counts_from_the_first_file_and_today_counts_up_to_now():
    first = datetime(2026, 10, 12, 23, 58, tzinfo=UTC)
    keys = [key(first), key(first + timedelta(minutes=1))]
    keys += [key(datetime(2026, 10, 13, 0, m, tzinfo=UTC)) for m in range(10) if m != 5]
    keys += [key(datetime(2026, 10, 13, 0, 10, tzinfo=UTC))]  # the current minute isn't over yet
    now = datetime(2026, 10, 13, 0, 10, 30, tzinfo=UTC)
    assert coverage(keys, now) == [("2026-10-12", 2, 2), ("2026-10-13", 9, 10)]


def test_no_files_means_no_rows():
    assert coverage([], datetime(2026, 10, 13, tzinfo=UTC)) == []
