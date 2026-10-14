"""Write one batch to S3 as a gzipped JSON Lines file (one sale per line).

The object key comes from the batch's own refresh time, so the same batch
always lands on the same key and saving it twice can't create a duplicate.
"""
import gzip
import json
from datetime import datetime, timezone


def object_key(last_updated_ms):
    t = datetime.fromtimestamp(last_updated_ms / 1000, tz=timezone.utc)
    return f"raw/date={t:%Y-%m-%d}/hour={t:%H}/{t:%Y%m%dT%H%MZ}.jsonl.gz"


def encode(sales):
    lines = "".join(json.dumps(sale, separators=(",", ":")) + "\n" for sale in sales)
    # mtime=0 makes the bytes depend only on the sales, so a re-save is identical.
    return gzip.compress(lines.encode("utf-8"), mtime=0)


def save_batch(s3, bucket, batch, version):
    key = object_key(batch.last_updated)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=encode(batch.sales),
        ContentType="application/gzip",
        Metadata={
            "last-updated": str(batch.last_updated),
            "sale-count": str(len(batch.sales)),
            "dropped-count": str(batch.dropped),
            "collector-version": version,
        },
    )
    return key
