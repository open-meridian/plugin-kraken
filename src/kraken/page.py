"""The plugin's pages, under Manage: the data role's Connection and Datasets
(spec/plugin-pages-follow-their-role), as the SDK draws them for a pairs
venue (`meridian.roles.data.pairs`), Kraken's names read from convert.py.

A data plugin shows no market data (ruled 2026-10-03): no price, bar or
candle is on either page; viewing prices is for the reading roles.

- **Connection** (`/`, `read_connection`): "Key" -- Live, or Sample data;
  "No key needed"; what Kraken entitles it to; the venue master's ID it
  resolved -- "Limits and use" and "Stream", the venue's session.
- **Datasets** (`/datasets`, `read_datasets`): "Served", "Wants" (searched
  and paged), "Subjects", then a section under Kraken's name: the product
  map and the rows restated, unchanged and not read.

Each page declares the record it renders (`answers=`), so each is also a
read tool on the deployment's MCP surface answering the same record.
"""

from __future__ import annotations

import meridian
from meridian import Figure
from meridian.roles.data import pairs

from .convert import ENTITLED as ENTITLED
from .convert import NAME, VENUE
from .declared import CATALOGUE

TITLE = NAME
#: The kit the pages are built against: 0.12.0's next step (`data-om-opens`).
KIT = "0.12.0"

pages = meridian.Pages(TITLE, kit=KIT)


class _Held:
    feed: pairs.Feed | None = None


HELD = _Held()


def hold(feed: pairs.Feed) -> None:
    """The work the pages show."""
    HELD.feed = feed


def connection_now() -> pairs.Connection:
    return pairs.connection_read(HELD.feed, NAME, ENTITLED)


def datasets_now() -> pairs.Datasets:
    return pairs.datasets_read(HELD.feed, CATALOGUE, VENUE, ENTITLED)


@pages.page("/", "Connection", levels="admin", answers=pairs.Connection, name="read_connection")
def connection(request: meridian.Request) -> meridian.Response:
    """How the plugin reaches Kraken: the mode, no key needed, what Kraken
    entitles it to, the venue master's ID it resolved and the endpoints; its
    limits and what the plugin spends of them, its calls, the last call and
    the last error; and the stream's session."""
    return pages.answer("meridian/roles/data/pairs/connection.html", connection_now())


@pages.page("/datasets", "Datasets", levels="admin", answers=pairs.Datasets, name="read_datasets")
def datasets(request: meridian.Request) -> meridian.Response:
    """What the plugin serves the lake: each dataset of its catalogue and
    whether it is licensed, what Kraken entitles it to, what it recorded
    and declined; the wants it heard and the standing wants it keeps
    current; whether it may read an instrument's record; and the product
    map."""
    return pages.answer("meridian/roles/data/pairs/datasets.html", datasets_now(), venue=NAME)


def figures_now() -> list[Figure]:
    """The data role's figures on the Summary, in its order: Connection,
    Entitled at the vendor, Stream and Last recorded. Kraken states no
    running rate to measure against, so Rate use is left out."""
    return pairs.figures_read(HELD.feed, CATALOGUE)
