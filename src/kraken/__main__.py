"""Kraken's public market data as an Open Meridian data plugin.

It connects to the sidecar it is launched beside, declaring its catalogue,
its storage and its settings (declaration.py) and its pages (page.py), and
serves them. Then the SDK's work for a pairs venue
(`meridian.roles.data.pairs.Feed`, over Kraken's conversion in convert.py)
maps Kraken's products to the deployment's instruments, hears what the
lake wants of it and records it, and keeps each standing want current --
from contract v19 its trades and best bid and offer from the venue's stream,
kept open while a standing want puts anything on it (stream.py, this
plugin's transport) -- until stopped. Everything goes through the
sidecar; nothing but Kraken's public REST and its stream are called, and with sample data
not even that (synthetic.py).

It holds nothing it cannot lose: Kraken's raw responses and the product map
are kept in the storage the deployment grants it (decisions/028), and a
restart reads the map back and hears again what the lake wants.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Mapping
from datetime import UTC, datetime

import meridian
from meridian.edge import RawStore, storage_root
from meridian.roles import Latency
from meridian.roles.data import cancelled
from meridian.roles.data.pairs import Feed, ProductMap

from .convert import KrakenMarket
from .declaration import DECLARATION, PORT
from .declared import KIND, SAMPLE_DATA, WINDOW_DAYS
from .page import figures_now, hold, pages
from .stream import Stream
from .synthetic import Recorded, Synthetic
from .venue import Kraken

log = logging.getLogger("kraken")

#: Where a developer's recorded exchanges are replayed from, under the
#: plugin's storage, when `make e2e-recorded` mounts them there.
RECORDED = "recorded"


def market(store: RawStore, synthetic: bool) -> KrakenMarket:
    """Kraken itself, or with sample data its answers from files: a
    developer's recorded exchanges where storage holds them, else this
    package's synthetic ones."""
    if not synthetic:
        return KrakenMarket(Kraken(store), "live")
    recorded = store.root / RECORDED
    if recorded.is_dir():
        return KrakenMarket(Kraken(store, transport=Recorded(recorded)), "recorded")
    return KrakenMarket(Kraken(store, transport=Synthetic()), "synthetic")


def product_map(store: RawStore, mode: str) -> ProductMap:
    held = ProductMap(store.root / f"products-{mode}.json")
    held.load()
    return held


async def watch_settings(
    plugin: meridian.Plugin, feed: Feed, store: RawStore, configured: asyncio.Event
) -> None:
    """Each delivery of the settings: the source switched where synthetic
    mode changed, its own product map read back from storage, and each day's
    raw responses past their window moved. Answering from Kraken, the map is
    made on the first want, never before: nothing is asked of Kraken, and
    nothing resolved, until the lake wants something of it. With sample data
    it is made at once, so a developer has the instruments it resolved to
    read before anything is wanted."""
    while True:
        try:
            await _apply_settings(plugin, feed, store, configured)
        except Exception as failed:  # noqa: BLE001 - the stream broke: said, and watched again
            log.warning("the settings' stream broke, watching again: %s", failed)
        await asyncio.sleep(2)


async def _apply_settings(
    plugin: meridian.Plugin, feed: Feed, store: RawStore, configured: asyncio.Event
) -> None:
    async for delivered in plugin.settings():
        values = delivered.values
        log.info("settings delivered: sample data %s", values.get(SAMPLE_DATA))
        synthetic = values.get(SAMPLE_DATA) is True
        mode = feed.market.session.mode
        if synthetic != (mode != "live"):
            chosen = market(store, synthetic)
            feed.use(chosen, product_map(store, chosen.session.mode))
            log.info("answering from %s", chosen.session.mode)
        if synthetic and not feed.products.read_at_ns:
            try:
                await feed.map_products()
            except Exception as failed:  # noqa: BLE001 - said on its pages, tried on a want
                log.warning("the synthetic product map was not made: %s", failed)
        configured.set()
        await tend_now(plugin, store, values)


async def tend_now(plugin: meridian.Plugin, store: RawStore, values: Mapping[str, object]) -> None:
    window = values.get(f"{KIND}_window_days")
    past = values.get(f"{KIND}_past_window")
    await store.tend(
        plugin,
        window if isinstance(window, int) else WINDOW_DAYS,
        past if isinstance(past, str) else "kept",
        datetime.now(UTC).date(),
    )


async def hear_wants(plugin: meridian.Plugin, feed: Feed, configured: asyncio.Event) -> None:
    """What the lake wants, once the settings have said where to answer from."""
    await configured.wait()
    await plugin.receive(observations_wanted=feed.on_want, want_withdrawn=feed.on_withdrawn)


async def report_health(plugin: meridian.Plugin, feed: Feed) -> None:
    """Each minute: its datasets' licences read again (contract v20), and
    on the heartbeat whether Kraken answers, with the data role's figures."""
    while True:
        try:
            await feed.read_licences()
        except meridian.MeridianError as failed:
            log.warning("licences not read: %s", failed)
        health = feed.market.session.health
        healthy = health.last_ok_ns >= health.last_failed_ns
        detail = f"{feed.market.name} answers" if healthy else health.last_error
        try:
            await plugin.report(healthy=healthy, detail=detail[:200], figures=figures_now())
        except (meridian.MeridianError, ValueError) as failed:
            log.warning("health not reported: %s", failed)
        await asyncio.sleep(60)


def _said(task: asyncio.Task[None]) -> None:
    """A task that stopped, said with why, and the plugin stopped with it: a
    restart starts it again."""
    if not task.cancelled() and task.exception() is not None:
        log.error("stopped: %r", task.exception(), exc_info=task.exception())
        os._exit(1)


async def run() -> None:
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for stop in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(stop, stopped.set)

    port = PORT
    # The version's whole declaration (declaration.py): its settings, its
    # pages with the levels each serves and their tools, and its documentation.
    # A version registers exactly what it was uploaded with (contract v25).
    async with await meridian.connect(declaration=DECLARATION) as plugin:
        log.info("registered as %s, roles %s", plugin.identity.instance_id, plugin.identity.roles)
        store = RawStore(storage_root(), KIND)
        chosen = market(store, synthetic=False)
        feed = Feed(plugin, chosen, product_map(store, chosen.session.mode), stream_factory=Stream)
        # Contract v28 (ruling 518): each row streamed or kept current has
        # its age at the edge recorded, its feed delay, reported every 10
        # seconds (ReportLatency).
        latency = Latency(plugin)
        feed.wants.latency = latency
        hold(feed)
        served = pages.serve(plugin, port)
        configured = asyncio.Event()
        tasks = [
            asyncio.create_task(watch_settings(plugin, feed, store, configured)),
            asyncio.create_task(hear_wants(plugin, feed, configured)),
            asyncio.create_task(feed.keep_current()),
            asyncio.create_task(feed.keep_streaming()),
            asyncio.create_task(report_health(plugin, feed)),
            asyncio.create_task(latency.run()),
        ]
        for task in tasks:
            task.add_done_callback(_said)
        await stopped.wait()
        log.info("stopping")
        for task in tasks:
            await cancelled(task)
        served.shutdown()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
