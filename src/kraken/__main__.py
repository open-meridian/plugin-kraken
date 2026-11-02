"""Kraken's public market data as an Open Meridian data plugin.

It runs its data role class, `Lake` -- the SDK's work for a pairs venue
(`meridian.roles.data.pairs.Feed`, over Kraken's conversion in convert.py)
-- on the sidecar it is launched beside, declaring its catalogue, its
storage and its settings (declaration.py) and its pages (page.py), which
`meridian.run` serves. It maps Kraken's products to the deployment's
instruments, hears what the lake wants of it and records it, and keeps
each standing want current -- from contract v19 its trades and best bid and
offer from the venue's stream, kept open while a standing want puts
anything on it -- until stopped. Everything goes through the sidecar;
nothing but Kraken's public REST and its stream are called, and with
sample data not even that (synthetic.py).

From 0.11.0 (open-meridian 0.35, each role one class: rulings 1004, 1005,
1009 to 1023) the role's work is `Lake`, registered with `meridian.run`,
which delivers the settings, serves the pages, sets the figures on each
heartbeat and starts `Lake.run` again after a backoff should it fail -- the
work the plugin wired by hand before. The stream is kept open by the SDK's
supervisor (`pairs.supervised`, `helpers.sessions.Supervisor`: ruling 1027)
over the plugin's own socket (stream.py).

It holds nothing it cannot lose: Kraken's raw responses and the product map
are kept in the storage the deployment grants it (decisions/028), and a
restart reads the map back and hears again what the lake wants.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import meridian
from meridian.edge import RawStore, storage_root
from meridian.roles import Latency
from meridian.roles.data.pairs import Feed, ProductMap, supervised

from .convert import KrakenMarket
from .declaration import DECLARATION, PORT
from .declared import KIND, SAMPLE_DATA, WINDOW_DAYS
from .page import figures_now, hold, pages
from .synthetic import Recorded, Synthetic
from .venue import Kraken

log = logging.getLogger("kraken")

#: Where a developer's recorded exchanges are replayed from, under the
#: plugin's storage, when `make e2e-recorded` mounts them there.
RECORDED = "recorded"
#: How often its datasets' licences are read again and whether Kraken
#: answers is said on its health.
HEALTH_EVERY_SECONDS = 60


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


@dataclass(eq=False)
class Lake(Feed):
    """The data role's class: the SDK's pairs feed over Kraken's conversion,
    which hears what the lake wants, keeps its standing wants current and
    its stream open, and records each row's age at the edge."""

    store: RawStore | None = None
    #: Contract v28 (ruling 518): each row streamed or kept current has its
    #: age at the edge recorded, its feed delay, reported every 10 seconds
    #: (ReportLatency) through this class.
    latency: Latency = field(default_factory=Latency)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.latency.role = self
        self.wants.latency = self.latency

    async def on_settings(self, delivered: Any) -> None:
        """Each delivery of the settings: the source switched where synthetic
        mode changed, its own product map read back from storage, and each
        day's raw responses past their window moved. Answering from Kraken,
        the map is made on the first want, never before: nothing is asked of
        Kraken, and nothing resolved, until the lake wants something of it.
        With sample data it is made at once, so a developer has the
        instruments it resolved to read before anything is wanted."""
        values = delivered.values
        log.info("settings delivered: sample data %s", values.get(SAMPLE_DATA))
        synthetic = values.get(SAMPLE_DATA) is True
        if self.store is None:
            return
        if synthetic != (self.market.session.mode != "live"):
            chosen = market(self.store, synthetic)
            self.use(chosen, product_map(self.store, chosen.session.mode))
            log.info("answering from %s", chosen.session.mode)
        if synthetic and not self.products.read_at_ns:
            try:
                await self.map_products()
            except Exception as failed:  # noqa: BLE001 - said on its pages, tried on a want
                log.warning("the synthetic product map was not made: %s", failed)
        window = values.get(f"{KIND}_window_days")
        past = values.get(f"{KIND}_past_window")
        await self.store.tend(
            self.plugin,
            window if isinstance(window, int) else WINDOW_DAYS,
            past if isinstance(past, str) else "kept",
            datetime.now(UTC).date(),
        )

    async def run(self) -> None:
        """The SDK's feed's work -- each standing want kept current and the
        stream kept open while anything stands on it -- the rows' ages
        reported every 10 seconds, and its health said each minute."""
        await asyncio.gather(super().run(), self.latency.run(), self._health())

    async def _health(self) -> None:
        """Each minute: its datasets' licences read again (contract v20), and
        on its health whether Kraken answers."""
        while True:
            try:
                await self.read_licences()
            except meridian.MeridianError as failed:
                log.warning("licences not read: %s", failed)
            health = self.market.session.health
            healthy = health.last_ok_ns >= health.last_failed_ns
            detail = f"{self.market.name} answers" if healthy else health.last_error
            try:
                await self.plugin.report(healthy=healthy, detail=detail[:200])
            except (meridian.MeridianError, ValueError) as failed:
                log.warning("health not reported: %s", failed)
            await asyncio.sleep(HEALTH_EVERY_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    store = RawStore(storage_root(), KIND)
    chosen = market(store, synthetic=False)
    lake = Lake(
        chosen,
        product_map(store, chosen.session.mode),
        stream_factory=supervised,
        store=store,
    )
    hold(lake)
    # The version's whole declaration (declaration.py): its settings, its
    # pages with the levels each serves and their tools, and its
    # documentation. A version registers exactly what it was uploaded with
    # (contract v25).
    meridian.run(
        declaration=DECLARATION,
        roles=[lake],
        pages=pages,
        port=PORT,
        on_settings=lake.on_settings,
        figures=figures_now,
    )


if __name__ == "__main__":
    main()
