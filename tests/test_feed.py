import json
import urllib.error

import pytest

from collector.feed import KEEP, FeedError, fetch_with_retry, parse_batch
from tests.helpers import CUR, Clock, body, sale


def test_only_allowlisted_fields_are_kept():
    batch = parse_batch(body([sale(someNewField="x")]))
    assert list(batch.sales[0]) == list(KEEP)
    for private in ("seller", "seller_profile", "buyer", "buyer_profile", "someNewField"):
        assert private not in batch.sales[0]


def test_batch_carries_hypixels_refresh_time():
    assert parse_batch(body([sale()], last_updated=CUR)).last_updated == CUR


def test_failure_flag_rejects_the_batch():
    with pytest.raises(FeedError):
        parse_batch(body([sale()], success=False))


def test_missing_auctions_rejects_the_batch():
    with pytest.raises(FeedError):
        parse_batch({"success": True, "lastUpdated": CUR})


def test_missing_last_updated_rejects_the_batch():
    with pytest.raises(FeedError):
        parse_batch({"success": True, "auctions": [sale()]})


def test_a_few_malformed_sales_are_dropped_and_counted():
    sales = [sale() for _ in range(19)] + [sale(price=-1)]
    batch = parse_batch(body(sales))
    assert len(batch.sales) == 19
    assert batch.dropped == 1


def test_too_many_malformed_sales_reject_the_batch():
    sales = [sale() for _ in range(10)] + [sale(price=-1), sale(bin="yes"), sale(item_bytes="")]
    with pytest.raises(FeedError, match="format may have changed"):
        parse_batch(body(sales))


def test_one_bad_sale_does_not_sink_a_small_batch():
    # 1 of 9 is over 10%, but a single odd sale isn't a format change; it takes
    # at least 3 bad sales as well as more than 10% to reject a batch.
    batch = parse_batch(body([sale() for _ in range(8)] + [sale(price=-1)]))
    assert len(batch.sales) == 8 and batch.dropped == 1


def test_two_bad_sales_are_dropped_even_at_twenty_percent():
    batch = parse_batch(body([sale() for _ in range(8)] + [sale(price=-1), sale(bin="yes")]))
    assert len(batch.sales) == 8 and batch.dropped == 2


@pytest.mark.parametrize("bad", [
    {"auction_id": "NOT-HEX"},
    {"auction_id": "E6FD22CD45AF47E29ACF7E0221514240"},  # uppercase isn't Hypixel's format
    {"timestamp": "1791600001234"},
    {"price": True},          # bool is an int in Python; it must not count as a price
    {"price": 1000.0},        # Review Focus 3: a type change is caught, not stored
    {"bin": 1},
    {"item_bytes": ""},
])
def test_each_kind_of_malformed_sale_is_dropped(bad):
    batch = parse_batch(body([sale() for _ in range(19)] + [sale(**bad)]))
    assert batch.dropped == 1


def test_an_empty_list_is_a_valid_batch():
    batch = parse_batch(body([]))
    assert batch.sales == [] and batch.dropped == 0


def failing_then(results):
    """A get_json that raises or returns each item of `results` in turn."""
    calls = iter(results)

    def get_json():
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return item
    return get_json


def test_a_failed_fetch_is_retried_after_two_seconds():
    clock = Clock(0)
    got = fetch_with_retry(failing_then([OSError("reset"), {"ok": 1}]), clock, clock.sleep, deadline=38)
    assert got == {"ok": 1}
    assert clock.sleeps == [2]


def test_it_gives_up_after_three_tries():
    clock = Clock(0)
    with pytest.raises(FeedError, match="feed unavailable"):
        fetch_with_retry(failing_then([OSError("x")] * 3), clock, clock.sleep, deadline=38)
    assert clock.sleeps == [2, 4]


def test_it_never_waits_past_the_deadline():
    clock = Clock(0)
    with pytest.raises(FeedError):
        fetch_with_retry(failing_then([OSError("x")] * 3), clock, clock.sleep, deadline=3)
    assert clock.sleeps == [2]  # a 4 s wait would end past the deadline, so it stops


def test_an_html_error_page_is_retried_then_fails():  # Review Focus 1
    not_json = json.JSONDecodeError("Expecting value", "<html>502</html>", 0)
    clock = Clock(0)
    with pytest.raises(FeedError):
        fetch_with_retry(failing_then([not_json] * 3), clock, clock.sleep, deadline=38)


@pytest.mark.parametrize("status", [429, 503])
def test_rate_limits_and_maintenance_are_retried_then_fail(status):  # Review Focus 2
    error = urllib.error.HTTPError("https://api.hypixel.net", status, "busy", {}, None)
    clock = Clock(0)
    with pytest.raises(FeedError):
        fetch_with_retry(failing_then([error] * 3), clock, clock.sleep, deadline=38)
    assert clock.sleeps == [2, 4]
