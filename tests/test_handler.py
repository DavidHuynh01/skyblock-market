import gzip
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
