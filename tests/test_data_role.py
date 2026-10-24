"""The SDK's checks for a data plugin of a pairs venue, run unchanged against
this plugin's own conversion (`meridian.roles.data.testing.PairsChecks`):
the data suite, the venue's work past the suite's cases, and the pages.
tests/venue_cases.py names Kraken's synthetic exchange for each."""

from __future__ import annotations

from typing import Any

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles.data import pairs
from meridian.roles.data.testing import (
    PAIRS_NOT_PRESENTED,
    Instruments,
    PairsChecks,
    hear,
    held,
    pairs_producers,
)
from meridian.suites import Recorder, run

import venue_cases

QUOTE = "meridian.v1.Quote"


class TestPairs(PairsChecks):
    venue = venue_cases


async def heartbeat_only(recorder: Recorder) -> int:
    """records-a-datasets-liveness as its case states it (contract v27): a
    standing want of the live dataset for BASE, then the venue's stream
    stating its heartbeat and no price change, replayed through the plugin's
    own stream. The heartbeat is the stream's sign of life (`Wants.liveness`
    through the SDK's `pairs.Feed`), never a row. How many calls the want's
    own answer made before the stream opened."""
    v = venue_cases
    store = Instruments().answering(recorder)
    feed = pairs.Feed(recorder, v.market(v.NOW_NS), pairs.ProductMap(),
                      clock_ns=lambda: v.NOW_NS, stream_factory=v.STREAM)  # fmt: skip
    subject = await held(store, feed, v.BASE)
    await hear(recorder, feed, ops.ObservationsWantedEvent(
        want_id="WNT-L", dataset=feed.dataset(pairs.LIVE), data_type=QUOTE,
        subjects=[ops.SubjectRef(entity_id=subject)], standing=True,
    ))  # fmt: skip

    async def said(_: str) -> Any:
        return v.replayed([v.HEARTBEAT])

    before = len(recorder.sent)
    feed.stream.retarget(feed.market.stream_address, said, feed.market.subscriptions)
    await feed.stream.run(once=True)
    await feed.flush()
    return before


def producers() -> dict[str, Any]:
    """The SDK's producers for a pairs venue, the liveness case's on a
    heartbeat alone (the SDK's states a ticker, which changes a price)."""

    async def liveness(recorder: Recorder) -> None:
        await heartbeat_only(recorder)

    return {**pairs_producers(venue_cases), "records-a-datasets-liveness": liveness}


def test_the_data_suite_passes_unchanged() -> None:
    """The SDK's data suite, each case on this plugin's own exchange
    (`meridian.suites.run`), as `meridian plugin check` asks to see."""
    v = venue_cases
    # What no pairs venue presents (contract v27: rates; the feed delay, about
    # latency until v28, ruling 518), then what this venue does not.
    not_presented = {**PAIRS_NOT_PRESENTED, **v.NOT_PRESENTED}
    report = run("data", producers(), not_presented=not_presented, instance_id=v.VENUE)
    assert report.passed, report.failures


async def test_a_heartbeat_alone_records_the_live_datasets_liveness() -> None:
    """The heartbeat confirms every quote in force: once the want is
    answered, the stream's heartbeat records the live dataset's liveness,
    once, at the moment it was heard, and no row."""
    v = venue_cases
    recorder = Recorder(v.VENUE)
    streamed = recorder.sent[await heartbeat_only(recorder) :]
    assert [sent.row for sent in streamed] == ["RecordLiveness"]
    (liveness,) = streamed[0].params.liveness
    assert (liveness.dataset, liveness.alive_at_ns) == (f"{v.VENUE}:live", v.NOW_NS)
