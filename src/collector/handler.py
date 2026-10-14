"""Lambda entry point: connects the run to the real feed, S3 and clock."""
import json
import os
import time

import boto3
from botocore.config import Config

from collector.feed import http_get_json
from collector.run import collect_once
from collector.store import save_batch

VERSION = "1"

# Kept between runs while Lambda keeps this instance warm, which it usually
# does at one run a minute. After a cold start it's empty, which costs at most
# one re-write of an identical file.
_STATE = {}
# S3 saves give up after seconds, not boto3's default minute, so a slow save
# can't hold the run anywhere near the next one.
_s3 = boto3.client(
    "s3",
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
    config=Config(
        connect_timeout=2,
        read_timeout=5,
        retries={"total_max_attempts": 2, "mode": "standard"},
    ),
)


def _metric_line(key, batch):
    """One log line that CloudWatch also reads as the SalesSaved metric
    (embedded metric format), so a feed that goes quiet can be alarmed on."""
    return {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": "skyblock-market",
                "Dimensions": [["Service"]],
                "Metrics": [{"Name": "SalesSaved", "Unit": "Count"}],
            }],
        },
        "Service": "collector",
        "SalesSaved": len(batch.sales),
        "saved": key,
        "dropped": batch.dropped,
    }


def lambda_handler(event, context):
    bucket = os.environ["BUCKET"]

    def save(batch):
        key = save_batch(_s3, bucket, batch, VERSION)
        print(json.dumps(_metric_line(key, batch)))
        return key

    keys = collect_once(
        get_json=http_get_json, save=save, clock=time.time, sleep=time.sleep, state=_STATE
    )
    return {"saved": keys}
