import pytest

from collector.feed import FeedError
from collector.run import collect_once
from tests.helpers import CUR, M, PREV, Clock, body, sale


def feed(clock, refresh_at=M + 6):
    """Hypixel stand-in: serves last minute's batch until `refresh_at`, then this minute's."""
    def get_json():
        last_updated = CUR if clock() >= refresh_at else PREV
        return body([sale(auction_id=f"{last_updated:032x}")], last_updated=last_updated)
    return get_json


def run(clock, state, get_json=None):
    saved = []
    keys = collect_once(
        get_json=get_json or feed(clock),
        save=lambda batch: saved.append(batch.last_updated) or f"key-{batch.last_updated}",
        clock=clock, sleep=clock.sleep, state=state,
    )
    return saved, keys


def test_on_time_run_waits_for_the_refresh_and_saves_it_once():
    clock = Clock(M + 0.5)
    saved, keys = run(clock, {"last_saved": PREV})  # the previous run saved PREV
    assert saved == [CUR]
    assert keys == [f"key-{CUR}"]
    assert clock.sleeps == [2, 2, 2]  # refresh lands at :06, seen at :06.5


def test_a_run_after_the_refresh_saves_without_waiting():
    clock = Clock(M + 30)
    saved, _ = run(clock, {"last_saved": PREV})
    assert saved == [CUR]
    assert clock.sleeps == []


def test_a_late_refresh_missed_last_minute_is_still_saved():
    clock = Clock(M + 0.5)
    saved, _ = run(clock, {"last_saved": PREV - 60_000})  # PREV was never saved
    assert saved == [PREV, CUR]


def test_a_second_run_in_the_same_minute_writes_nothing():  # Review Focus 5
    clock = Clock(M + 30)
    state = {"last_saved": CUR}
    saved, keys = run(clock, state)
    assert saved == [] and keys == []


def test_after_a_cold_start_last_minute_is_rewritten_once_at_most():
    clock = Clock(M + 0.5)
    saved, _ = run(clock, {})
    assert saved == [PREV, CUR]  # PREV's file is re-written with identical bytes


def test_state_remembers_the_last_batch_saved():
    clock = Clock(M + 30)
    state = {}
    run(clock, state)
    assert state == {"last_saved": CUR}


def test_last_updated_going_backwards_does_not_break_the_run():  # Review Focus 4
    clock = Clock(M + 30)
    replies = iter([body([sale()], last_updated=PREV), body([sale()], last_updated=CUR)])
    saved, _ = run(clock, {"last_saved": CUR}, get_json=lambda: next(replies))
    assert saved == [PREV, CUR]  # both re-written identically; nothing duplicated or lost
    assert clock.sleeps == [2]


def test_it_gives_up_at_the_deadline_if_hypixel_never_refreshes():
    clock = Clock(M + 0.5)
    with pytest.raises(FeedError, match="did not refresh"):
        collect_once(get_json=feed(clock, refresh_at=M + 999), save=lambda b: "k",
                     clock=clock, sleep=clock.sleep, state={"last_saved": PREV})
    assert clock.t <= M + 0.5 + 38


def test_a_broken_feed_saves_nothing():
    clock = Clock(M + 0.5)
    saved = []

    def broken():
        raise OSError("down")

    with pytest.raises(FeedError):
        collect_once(get_json=broken, save=saved.append, clock=clock, sleep=clock.sleep, state={})
    assert saved == []


def test_an_untrustworthy_batch_saves_nothing():
    clock = Clock(M + 30)
    saved = []
    with pytest.raises(FeedError):
        collect_once(get_json=lambda: body([sale(price=-1)] * 5, last_updated=CUR),
                     save=saved.append, clock=clock, sleep=clock.sleep, state={})
    assert saved == []
