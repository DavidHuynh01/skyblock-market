"""Read one batch of finished auctions from Hypixel and reduce it to what the
collector is allowed to store.

The feed (public, no API key) is replaced once a minute, about 6 seconds past
the minute, and holds the ~60 seconds of sales before that. Batches never
overlap, so a batch that isn't saved is gone for good.
"""
import json
import re
import urllib.request
from dataclasses import dataclass

FEED_URL = "https://api.hypixel.net/v2/skyblock/auctions_ended"
FETCH_TIMEOUT_SECONDS = 10

# Fields kept, by name. Everything else is dropped: the buyer and seller ids,
# and any field Hypixel adds in future, which might be personal too.
KEEP = ("auction_id", "timestamp", "price", "bin", "item_bytes")

# Above this share of malformed sales, and at least this many, assume Hypixel
# changed its format and save nothing rather than a batch we can't trust. The
# floor stops one odd sale from sinking a small batch.
MAX_BAD_SHARE = 0.10
MIN_BAD_TO_REJECT = 3

_AUCTION_ID = re.compile(r"[0-9a-f]{32}")


class FeedError(Exception):
    """The feed couldn't be read, or what it returned can't be trusted."""


@dataclass(frozen=True)
class Batch:
    last_updated: int  # Hypixel's refresh time, ms since the epoch (UTC)
    sales: list        # allowlisted fields only
    dropped: int       # malformed sales left out


def _is_valid_sale(sale):
    if not isinstance(sale, dict):
        return False
    auction_id, item_bytes = sale.get("auction_id"), sale.get("item_bytes")
    # `type(...) is int` rather than isinstance: True and False are ints in Python.
    return (
        isinstance(auction_id, str) and _AUCTION_ID.fullmatch(auction_id) is not None
        and type(sale.get("timestamp")) is int
        and type(sale.get("price")) is int and sale["price"] >= 0
        and type(sale.get("bin")) is bool
        and isinstance(item_bytes, str) and item_bytes != ""
    )


def parse_batch(body):
    """Check a feed response and reduce it to a Batch.

    Raises FeedError if the response as a whole can't be trusted."""
    if not isinstance(body, dict) or body.get("success") is not True:
        raise FeedError("feed did not report success")
    sales, last_updated = body.get("auctions"), body.get("lastUpdated")
    if not isinstance(sales, list) or type(last_updated) is not int:
        raise FeedError("feed response is missing auctions or lastUpdated")
    kept = [{field: sale[field] for field in KEEP} for sale in sales if _is_valid_sale(sale)]
    dropped = len(sales) - len(kept)
    if dropped >= MIN_BAD_TO_REJECT and dropped / len(sales) > MAX_BAD_SHARE:
        raise FeedError(f"{dropped} of {len(sales)} sales malformed; the format may have changed")
    return Batch(last_updated, kept, dropped)


def http_get_json(url=FEED_URL, timeout=FETCH_TIMEOUT_SECONDS):
    request = urllib.request.Request(url, headers={"User-Agent": "skyblock-market-collector/1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def fetch_with_retry(get_json, clock, sleep, deadline, backoffs=(2, 4)):
    """Call get_json(), retrying after each wait in `backoffs`, but never
    starting a wait that would end past `deadline` (a clock() value).

    Raises FeedError carrying the last error if every attempt fails."""
    last_error = None
    for wait in (0, *backoffs):
        if wait:
            if clock() + wait >= deadline:
                break
            sleep(wait)
        try:
            return get_json()
        except Exception as error:  # network, timeout, HTTP status, bad JSON
            last_error = error
    raise FeedError(f"feed unavailable: {last_error!r}")
