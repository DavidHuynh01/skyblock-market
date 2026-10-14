"""One collector run: save every batch Hypixel publishes, exactly once.

Called once a minute. It first saves the batch it finds, unless this instance
already saved it: normally the previous run did, but if Hypixel refreshed
late, this is the one chance to keep that batch. Then, if Hypixel hasn't
refreshed for the current minute yet, it waits for the refresh and saves that.
"""
from collector.feed import FeedError, fetch_with_retry, parse_batch

# The run gives up 38 s after starting. A fetch can take up to 10 s, so even
# one started just before the deadline ends inside the 50 s Lambda timeout,
# and runs never overlap.
RUN_SECONDS = 38
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
            raise FeedError("Hypixel did not refresh before the deadline")
        sleep(poll_seconds)
