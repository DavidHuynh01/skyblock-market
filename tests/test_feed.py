import pytest

from collector.feed import KEEP, FeedError, parse_batch
from tests.helpers import CUR, body, sale


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
    sales = [sale() for _ in range(8)] + [sale(price=-1), sale(bin="yes")]
    with pytest.raises(FeedError, match="format may have changed"):
        parse_batch(body(sales))


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
