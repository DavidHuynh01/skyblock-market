"""Lambda entry point: connects the run to the real feed, S3 and clock."""
import json
import os
import time

import boto3

from collector.feed import http_get_json
from collector.run import collect_once
from collector.store import save_batch

VERSION = "1"

# Kept between runs while Lambda keeps this instance warm, which it usually
# does at one run a minute. After a cold start it's empty, which costs at most
# one re-write of an identical file.
_STATE = {}
_s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def lambda_handler(event, context):
    bucket = os.environ["BUCKET"]

    def save(batch):
        key = save_batch(_s3, bucket, batch, VERSION)
        print(json.dumps({"saved": key, "sales": len(batch.sales), "dropped": batch.dropped}))
        return key

    keys = collect_once(
        get_json=http_get_json, save=save, clock=time.time, sleep=time.sleep, state=_STATE
    )
    return {"saved": keys}
