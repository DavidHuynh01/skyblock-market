import gzip
import json
from types import SimpleNamespace

import collector.handler as handler
from tests.helpers import CUR, M, FakeS3, body, sale


def test_handler_saves_one_batch_to_the_configured_bucket(monkeypatch):
    s3 = FakeS3()
    monkeypatch.setenv("BUCKET", "the-bucket")
    monkeypatch.setattr(handler, "_s3", s3)
    monkeypatch.setattr(handler, "_STATE", {})
    monkeypatch.setattr(handler, "http_get_json", lambda: body([sale()], last_updated=CUR))
    monkeypatch.setattr(handler, "time", SimpleNamespace(time=lambda: M + 30, sleep=lambda s: None))

    result = handler.lambda_handler({}, None)

    assert result == {"saved": [s3.puts[0]["Key"]]}
    assert s3.puts[0]["Bucket"] == "the-bucket"
    assert b"buyer" not in gzip.decompress(s3.puts[0]["Body"])


def run_handler(monkeypatch, sales):
    s3 = FakeS3()
    monkeypatch.setenv("BUCKET", "the-bucket")
    monkeypatch.setattr(handler, "_s3", s3)
    monkeypatch.setattr(handler, "_STATE", {})
    monkeypatch.setattr(handler, "http_get_json", lambda: body(sales, last_updated=CUR))
    monkeypatch.setattr(handler, "time", SimpleNamespace(time=lambda: M + 30, sleep=lambda s: None))
    return handler.lambda_handler({}, None)


def test_each_save_reports_how_many_sales_it_kept(monkeypatch, capsys):
    # Logged in CloudWatch's embedded-metric format, which CloudWatch turns into
    # a metric on its own; the quiet-feed alarm watches it.
    run_handler(monkeypatch, [sale(), sale(), sale()])
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    (metric,) = [line for line in lines if "_aws" in line]
    (spec,) = metric["_aws"]["CloudWatchMetrics"]
    assert spec["Namespace"] == "skyblock-market"
    assert spec["Metrics"] == [{"Name": "SalesSaved", "Unit": "Count"}]
    assert spec["Dimensions"] == [["Service"]] and metric["Service"] == "collector"
    assert metric["SalesSaved"] == 3


def test_s3_calls_give_up_quickly_instead_of_after_a_minute():
    config = handler._s3.meta.config
    assert config.connect_timeout == 2
    assert config.read_timeout == 5
    assert config.retries == {"total_max_attempts": 2, "mode": "standard"}
