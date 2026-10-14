# skyblock-market

Predicting what **Hypixel SkyBlock** items sell for on the Auction House,
from real sales. Companion to
[SkyblockZordle](https://github.com/DavidHuynh01/SkyblockZordle), where the
estimates will appear.

**Status: collecting data.** The model comes once there are a few weeks of sales.

## Why not just average the price?

For items where every copy is identical, the average is the right answer. For
upgraded items it's badly wrong. The 98 Hyperions listed one afternoon ranged
from **454M** coins (no upgrades) to **3,499M** (Fabled, 5 stars, 5 master
stars), with an average of 1,047M. That's more than double the price of a plain
one, and under a third of the price of a maxed one.

Pricing each exact combination doesn't work either: with stars, reforges,
dozens of enchantments and potato books, most items sold are one of a kind.
The model's job is to learn what each upgrade is worth, so it can price
combinations nobody has sold before. It's judged against the plain average on
sales it has never seen, and the results will be reported either way.

## The collector (live)

Hypixel publishes every finished auction, but only the last minute's worth,
and keeps no history. So a Lambda runs every minute and saves each batch
before it disappears:

```
EventBridge Scheduler ─ every minute ─▶ Lambda (Python) ─▶ S3: one gzipped JSON Lines file per minute
                                            └─ fails or stops ─▶ CloudWatch alarm ─▶ email
```

- **Privacy by allowlist.** Each sale keeps five fields: id, time, price,
  Buy-It-Now or bid, and the item itself. Buyer and seller ids are never
  stored, and neither is any field Hypixel adds later.
- **No duplicates, no gaps.** Files are named after Hypixel's own refresh
  time, so a batch fetched twice overwrites itself. A run saves any batch the
  previous run missed before waiting for its own.
- **Untrustworthy data is rejected.** If more than 10% of a batch, and at
  least 3 sales, are malformed, nothing is saved. Repeated failures, a
  stopped collector, or a feed that goes quiet each set off an email alarm.
- **Least privilege.** The function can only add files; it can't read, list
  or delete them. The bucket is private, encrypted and TLS-only, and the data
  survives even if the stack is deleted.

## Roadmap

1. **Collector**: live
2. **Model**: learn prices from the collected sales, compared against the plain average
3. **Price service**: serve the model in a Docker container
4. **SkyblockZordle integration**: market value in Collections and on the win screen

## Built with

Python 3.13 · AWS Lambda · EventBridge Scheduler · S3 · CloudWatch + SNS ·
AWS SAM (infrastructure as code) · GitHub Actions with keyless OIDC deploys ·
pytest

---

Data from Hypixel's public API. A fan project, not affiliated with or
endorsed by Hypixel or Mojang.
