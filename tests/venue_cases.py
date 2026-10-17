"""Kraken's side of the data role's checks: this plugin's synthetic exchanges,
named for what each of the checks asks a source to present.

tests/test_data_role.py runs the SDK's checks for a pairs venue
(`meridian.roles.data.testing.PairsChecks`) -- the data suite unchanged,
the venue's work past the suite's cases, and the pages -- against this
plugin's own conversion; this module is the one place they learn which
venue they are holding. Each answer comes through the plugin's real client,
raw records and reading (synthetic.py's transport over the exchanges this
package carries, `src/kraken/synthetic/`), with invented values; real
recordings are never committed (Kraken asks its permission for non-personal
use; the plan's Q11).
"""

from __future__ import annotations

import copy
import json
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from meridian.edge import RawStore
from meridian.roles.data.pairs import TAKER, Feed, Market

from kraken import page
from kraken.convert import KrakenMarket
from kraken.stream import Replayed, Socket, Stream
from kraken.synthetic import Synthetic
from kraken.venue import Kraken, RateLimiter

__all__ = ["page"]

PACKAGE = Path(__file__).parent.parent / "src" / "kraken"
#: The plugin's own modules no float may reach.
CONVERSION = (PACKAGE / "convert.py", PACKAGE / "synthetic.py")
#: The plugin's stream: its own session over its own transport.
STREAM = Stream

SYNTHETIC = PACKAGE / "synthetic"

#: The venue's name as a symbol's source, and the plugin's.
VENUE = "kraken"
#: The suite's clock: 2026-10-10 12:00 UTC, the day still forming.
NOW_NS = 1_791_633_600 * 1_000_000_000
TODAY = date(2026, 10, 10)
#: A day whose candles are complete.
CLOSED = date(2026, 10, 8)
#: A base asset priced in both a currency and a stablecoin: Kraken's XXBT
#: (XXBTZUSD, and XBTUSDC on Kraken's own USDC instrument).
BASE = "XXBT"
STABLE_BASE = "XXBT"
#: A base whose close has more decimal places than a float holds (TKNUSD).
EXACT_BASE = "TKN"
#: A base whose day traded nothing (count 0), so states no volume-weighted
#: price (QDTUSD).
BAR_BASE = "QDT"
#: A currency priced in another: the euro in dollars (ZEURZUSD).
FX_BASE = "ZEUR"
#: An asset whose identifiers the suite answers as meeting two records.
AMBIGUOUS = "PLY"
#: The forming day's entry, as read twice while it fills.
FORMING_PRODUCT = "XXBTZUSD"
FORMING = [
    [1791590400, "61988.9", "62200.0", "61900.0", "62010.3", "62050.1", "120.50000000", 4100],
    [1791590400, "61988.9", "62300.0", "61850.0", "62155.8", "62100.4", "240.25000000", 8200],
]


def _instant(_: float) -> None:
    return None


def market(now_ns: int = NOW_NS, forming: int | None = None) -> Market:
    """Kraken's synthetic exchange through the plugin's own client, its answers
    kept in a fresh store; `forming` adds the forming day's entry, as read the
    first or second time."""
    directory = SYNTHETIC
    if forming is not None:
        held = Path(tempfile.mkdtemp(prefix="kraken-synthetic-"))
        for kept in SYNTHETIC.iterdir():
            (held / kept.name).write_text(kept.read_text())
        entries: dict[str, Any] = json.loads((SYNTHETIC / "ohlc.json").read_text())
        entries = copy.deepcopy(entries)
        entries[FORMING_PRODUCT].append(FORMING[forming])
        (held / "ohlc.json").write_text(json.dumps(entries))
        directory = held
    store = RawStore(Path(tempfile.mkdtemp(prefix="kraken-raw-")))
    client = Kraken(
        store,
        transport=Synthetic(directory),
        limiter=RateLimiter(1000.0, 1000, sleep=_instant),
        clock_ns=lambda: now_ns,
        sleep=_instant,
    )
    return KrakenMarket(client, "synthetic")


#: The last trade's price each of BASE's products states now, as its text.
LIVE_LAST = {"XXBTZUSD": "61988.90000", "XBTUSDC": "62006.75"}
#: The product quoted in a stablecoin, and that stablecoin's code.
STABLE_PRODUCT, STABLE = "XBTUSDC", "USDC"
#: A product the venue lists and no longer trades.
DELISTED = "OLDUSD"
#: The close BASE's first product states for CLOSED, as its text.
CLOSED_CLOSE = ("XXBTZUSD", "62001.40000")
#: The close EXACT_BASE states for CLOSED, as its text.
EXACT_CLOSE = "0.000012345678901234"

# ── Trades and quotes (contract v19) ─────────────────────────────────────────

#: Whose side Kraken names on a trade: the one that took liquidity.
SIDE_OF = TAKER
#: BASE's pairs on the v2 stream, by their names on it (XBT is BTC there).
STREAM_NAMES = ["BTC/USD", "BTC/USDC"]
#: Every trade the synthetic stream and history state for BASE's pairs, by
#: pair, in order: the first connection drops after 110938302, so on reopening
#: 110938303 to 110938306 are read back from `Trades`, and the second
#: connection's snapshot of 110938304 to 110938306 is heard again and not
#: sent again.
STREAMED = {
    "XXBTZUSD": ["110938301", "110938302", "110938303", "110938304", "110938305",
                 "110938306", "110938307"],
    "XBTUSDC": ["5502", "5503"],
}  # fmt: skip
GAP = {"110938303", "110938304", "110938305", "110938306"}
#: The side that took liquidity, by trade: Kraken's taker side as sent.
AGGRESSORS = {"110938301": "AGGRESSOR_SELL", "110938302": "AGGRESSOR_BUY",
              "110938303": "AGGRESSOR_BUY", "110938304": "AGGRESSOR_SELL",
              "110938305": "AGGRESSOR_BUY", "110938306": "AGGRESSOR_SELL",
              "110938307": "AGGRESSOR_BUY", "5502": "AGGRESSOR_SELL",
              "5503": "AGGRESSOR_SELL"}  # fmt: skip
#: 110938302 as the stream states it, its JSON numbers read from their text.
TRADE_PRICE, TRADE_QUANTITY = ("XXBTZUSD", "110938302"), ("61990.20000", "0.01250000")
#: The last best bid and offer each pair's stream states: bid, its size, ask,
#: its size.
LAST_QUOTES = {"XXBTZUSD": ("61991.7", "0.92000000", "61991.8", "0.33000000"),
               "XBTUSDC": ("62007.10", "0.10000000", "62007.40", "0.25000000")}  # fmt: skip
#: A base whose level-1 book has bids and no offer: TKNUSD's.
ONE_SIDED_BASE = "TKN"
#: A trade on BASE's dollar pair taken by a buy, as the v2 stream states it.
TAKER_BUY = (
    '{"channel":"trade","type":"update","data":[{"symbol":"BTC/USD","side":"buy",'
    '"price":62510.01,"qty":0.0125,"ord_type":"market","trade_id":110939001,'
    '"timestamp":"2026-10-10T11:59:58.123456Z"}]}'
)
#: The v2 stream's ticker for BASE's dollar pair: both sides, with sizes.
TICKER = (
    '{"channel":"ticker","type":"update","data":[{"symbol":"BTC/USD","bid":62510.0,'
    '"bid_qty":0.84000000,"ask":62510.1,"ask_qty":0.50000000,"last":62510.01,'
    '"volume":100.5,"vwap":62400.0,"low":61900.0,"high":62600.0,"change":40.1,'
    '"change_pct":0.06,"trades":1234,"timestamp":"2026-10-10T11:59:58.500000Z"}]}'
)
#: Each case of the suite about trades or quotes, the stream's message that
#: presents it.
STREAM_CASES = {"a-trade-recorded": TAKER_BUY, "the-takers-side-stated": TAKER_BUY,
                "a-standing-want-streamed": TAKER_BUY, "a-quote-recorded": TICKER}  # fmt: skip
#: Why each case Kraken never presents is not (meridian.suites: a case about a
#: kind of data, `about`, the plugin never publishes).
NOT_PRESENTED = {
    "the-makers-side-inverted": "Kraken names the side that took liquidity, never the resting "
    "order's",
    "a-condition-converted": "Kraken states no condition codes: a crypto trade is regular",
    "a-condition-not-converted": "Kraken states no condition codes: none to leave unconverted",
    "a-trade-withdrawn": "Kraken's feed never withdraws a trade it has stated",
    "reads-a-calendar": "a crypto venue trading 24/7: it reads no settlement calendar",
    "asks-for-a-settlement-date": (
        "records prices, bars and trades as Kraken publishes them; never computes a settlement date"
    ),
    "records-an-outcome": "Kraken lists no event contract: no outcome to record",
    "restates-a-disputed-outcome": "Kraken lists no event contract: no outcome disputed",
    "records-a-partial-payout": "Kraken lists no event contract: no payout to settle",
}
#: A restart's gap (contract v20): the last trade the lake holds of BASE's
#: dollar pair, by its pair, trade ID and time; and the trades the venue's
#: history states after it, in order.
RESTARTED = ("XXBTZUSD", "110938304", 1_791_633_593_500_000_000)
BACKFILLED = ["110938305", "110938306"]


def replayed(messages: list[str]) -> Socket:
    """A connection saying `messages` and dropping, as a venue's does."""
    return Replayed(messages, hold=False)


def stream_sessions(feed: Feed) -> list[list[str]]:
    """The messages of each of the synthetic venue's connections, in turn."""
    sessions: list[list[str]] = feed.market.client.transport.stream_sessions()  # type: ignore[attr-defined]
    return sessions


def raw_store(feed: Feed) -> RawStore:
    """The raw records the plugin's client keeps."""
    store: RawStore = feed.market.client.store  # type: ignore[attr-defined]
    return store
