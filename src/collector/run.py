"""One collector run: save every batch Hypixel publishes, exactly once.

Called once a minute. It first saves the batch it finds, unless this instance
already saved it: normally the previous run did, but if Hypixel refreshed
late, this is the one chance to keep that batch. Then, if Hypixel hasn't
refreshed for the current minute yet, it waits for the refresh and saves that.

Timing it relies on (measured October 2026): Hypixel stamps each list about 6 s
past the minute, and it becomes visible about 12 s past, so the wait normally
ends well inside the deadline. If that ever drifts past the deadline, nothing
is lost: every run still saves the batch the previous run couldn't wait for.
Such a run counts as a success, so the failing alarm stays meaningful; only a
run that saved nothing at all is an error.
"""
from collector.feed import FeedError, fetch_with_retry, parse_batch

# The run stops starting new work 30 s in. Hypixel's list is normally visible
# by about 12 s, so this is plenty. A fetch can still take ~10 s after that and
# a save a few more, all inside the 55 s Lambda limit, so runs never overlap.
# If something hangs longer, the worst case is a Lambda timeout, which loses
# nothing: the next run saves any batch this one missed.
RUN_SECONDS = 30
POLL_SECONDS = 2


def collect_once(*, get_json, save, clock, sleep, state,
                 run_seconds=RUN_SECONDS, poll_seconds=POLL_SECONDS):
    """Return the keys written this run.

    `state` is a dict kept between runs, holding "last_saved": the
    lastUpdated of the last batch this instance wrote.

    Raises FeedError if the feed can't be read or trusted, or doesn't refresh
    before the deadline."""
    started = clock()
    deadline = started + run_seconds
    minute_start_ms = int(started // 60 * 60 * 1000)
    written = []
    while True:
        batch = parse_batch(fetch_with_retry(get_json, clock, sleep, deadline))
        if batch.last_updated != state.get("last_saved"):
            written.append(save(batch))
            state["last_saved"] = batch.last_updated
        if batch.last_updated >= minute_start_ms:
            return written
        if clock() + poll_seconds >= deadline:
            if written:
                # Too late to wait for this minute's list, but this run kept one
                # the last run missed; the next run will save this minute's.
                return written
            raise FeedError("Hypixel did not refresh before the deadline")
        sleep(poll_seconds)
