"""Fakes shared by the tests: sales, feed responses, a controllable clock and S3."""

M = 1_791_600_000            # a minute boundary, in seconds since the epoch
PREV = (M - 54) * 1000       # previous minute's refresh (:06), in ms
CUR = (M + 6) * 1000         # this minute's refresh (:06), in ms


def sale(**overrides):
    s = {
        "auction_id": "e6fd22cd45af47e29acf7e0221514240",
        "seller": "a" * 32,
        "seller_profile": "b" * 32,
        "buyer": "c" * 32,
        "buyer_profile": "d" * 32,
        "timestamp": 1_791_600_001_234,
        "price": 1_000_000,
        "bin": True,
        "item_bytes": "H4sIAAAAAAAA",
    }
    s.update(overrides)
    return s


def body(sales, last_updated=CUR, success=True):
    return {"success": success, "lastUpdated": last_updated, "auctions": sales}


class Clock:
    """time.time stand-in; sleep() advances it instantly and records the wait."""

    def __init__(self, t):
        self.t = t
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


class FakeS3:
    def __init__(self):
        self.puts = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        return {}
