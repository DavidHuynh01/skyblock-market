import gzip
import json
from datetime import datetime, timezone

from collector.feed import Batch
from collector.store import encode, object_key, save_batch
from tests.helpers import FakeS3, sale


def ms(*args):
    return int(datetime(*args, tzinfo=timezone.utc).timestamp() * 1000)


def test_key_is_the_utc_second_of_the_refresh():
    assert object_key(ms(2026, 10, 12, 4, 34, 6, 275000)) == (
        "raw/date=2026-10-12/hour=04/20261012T043406Z.jsonl.gz"
    )


def test_two_lists_stamped_in_the_same_minute_get_different_keys():
    # Hypixel refreshes once a minute, but if it ever refreshed twice within
    # one, a minute-only name would let the second list overwrite the first.
    assert object_key(ms(2026, 10, 12, 4, 34, 6)) != object_key(ms(2026, 10, 12, 4, 34, 50))


def test_the_same_batch_always_gets_the_same_key_and_bytes():
    sales = [sale(), sale(price=5)]
    assert object_key(ms(2026, 10, 12, 23, 59, 6)) == object_key(ms(2026, 10, 12, 23, 59, 6))
    assert encode(sales) == encode(sales)  # identical re-saves, never a new file


def test_file_is_gzipped_json_lines():
    sales = [{"auction_id": "a" * 32, "price": 1}, {"auction_id": "b" * 32, "price": 2}]
    lines = gzip.decompress(encode(sales)).decode("utf-8").splitlines()
    assert [json.loads(line) for line in lines] == sales


def test_an_empty_batch_is_an_empty_file():
    assert gzip.decompress(encode([])) == b""


def test_save_batch_writes_the_file_with_its_metadata():
    s3 = FakeS3()
    batch = Batch(ms(2026, 10, 12, 4, 34, 6), [{"auction_id": "a" * 32}], dropped=2)
    key = save_batch(s3, "the-bucket", batch, "1")
    (put,) = s3.puts
    assert key == put["Key"] == "raw/date=2026-10-12/hour=04/20261012T043406Z.jsonl.gz"
    assert put["Bucket"] == "the-bucket"
    assert put["ContentType"] == "application/gzip"
    assert gzip.decompress(put["Body"]).count(b"\n") == 1
    assert put["Metadata"] == {
        "last-updated": str(batch.last_updated),
        "sale-count": "1",
        "dropped-count": "2",
        "collector-version": "1",
    }
