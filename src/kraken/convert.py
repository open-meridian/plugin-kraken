"""Kraken's answers, read into the venue's values (the SDK's
`meridian.roles.data.pairs`): the one place
Kraken's vocabulary is read.

Kraken names everything its own way: assets by legacy codes (`XXBT` for
bitcoin, whose altname is `XBT`, never `BTC`; `ZUSD` for the dollar), pairs by
keys built from them (`XXBTZUSD`) and by altnames (`XBTUSD`). A pair names a
market, not an asset: its base is a row's subject, priced in its quote.

**Assets** (the plan's "Identifiers for a pair"; the product owner's ruling of
2026-10-03 on a venue's balance in a multi-network token):

- **A currency** is a cash instrument, by its ISO 4217 code, for the fiat
  asset codes Kraken documents (FIAT, below). Kraken's `Assets` does not say
  which assets are fiat (every one is `aclass: currency`), and a `Z` is no
  sign of one (`ZAMA` and `ZBCN` are tokens), so the table is the plugin's,
  keyed by Kraken's codes; a code not in it resolves by its code until a
  person adds it.
- **A native coin** carries its CAIP-19 by SLIP-44 coin type (`XXBT`, `XETH`).
- **Every other token** is Kraken's own instrument: Kraken's public API states
  no network and no contract for any asset, so none carries a contract's
  CAIP-19; each is known by its code with source `kraken` alone. Never
  guessed from a ticker.
- **A stablecoin is a token,** never its currency (decisions/030): a pair
  quoted in `USDC` is quoted in Kraken's USDC instrument, and Kraken's own
  `USDCUSD` is the dataset's price for valuing it (the plan's Q25).

**OHLC** entries are `[time, open, high, low, close, vwap, volume, count]`,
every figure a string, `time` the day's start at 00:00 UTC; the last entry is
the day still forming. A day with no trades (`count` 0) has no
volume-weighted price, whatever Kraken writes in its place.

**The ticker's** `c` is the last trade's price; Kraken states no time and no
trade identity for it, so it is in force from when its answer arrived and is
known by that answer's place in the raw record. **The level-1 book's** best
bid and ask are `Depth`'s first `bids` and `asks`, `[price, volume, time]`, in
force from the later side's time, each volume its side's size.

**Trades** (contract v19): `Trades` states each as `[price, volume, time,
side, order type, misc, trade_id]`, its time a JSON number of seconds read
from its own text, and the stream's `trade` channel as `price`, `qty`,
`side`, `ord_type`, `trade_id` and `timestamp`. The side is **the taker's**,
the one that took liquidity (Kraken's documentation), recorded as the
aggressor as sent; the taker's order type stays in the raw record. Kraken
states no condition codes. **The stream** is Kraken's v2: pairs by their
`wsname`, with bitcoin's `XBT` as `BTC` and `XDG` as `DOGE` (its v2
documentation), its figures JSON numbers read from their own text; the
`ticker` channel, asked for each change of the best bid and offer
(`event_trigger` `bbo`), states them with their sizes (`bid`, `bid_qty`,
`ask`, `ask_qty`) at its `timestamp`. A `trade` snapshot, the pair's last 50,
comes on subscribing. Every message is kept as a raw record before it is
read, but a heartbeat, which states nothing.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from meridian.roles.data import (
    NANOS_PER_SECOND,
    SECONDS_PER_DAY,
    Endpoint,
    Limits,
    Session,
    Unread,
    day_start,
    json_decimal,
    number,
)
from meridian.roles.data.pairs import TAKER, Asset, Candle, Listed, Print, Tick, Top

from .stream import Replayed, Socket, websocket
from .venue import (
    BURST,
    MOST_CANDLES,
    MOST_TRADES,
    RATE_PER_SECOND,
    REST,
    STREAM,
    USER_AGENT,
    Kraken,
    result_for,
)

VENUE = "kraken"
#: Kraken in the venue master: no MIC, so its own code, as a symbol whose
#: source is Kraken, which the platform's curation adds to its record.
VENUE_IDENTIFIERS: tuple[tuple[str, str, str], ...] = (("symbol", "kraken", "kraken"),)
NAME = "Kraken"
#: What the venue entitles this plugin to: its public market data, no key.
ENTITLED = "Public market data: every pair it lists"

#: Native coins by SLIP-44 coin type, keyed by Kraken's asset code.
NATIVE: dict[str, str] = {
    "XXBT": "bip122:000000000019d6689c085ae165831e93/slip44:0",
    "XETH": "eip155:1/slip44:60",
}

#: Kraken's fiat asset codes, as its documentation lists them, to ISO 4217.
FIAT: dict[str, str] = {
    "ZUSD": "USD",
    "ZEUR": "EUR",
    "ZGBP": "GBP",
    "ZCAD": "CAD",
    "ZJPY": "JPY",
    "ZAUD": "AUD",
    "CHF": "CHF",
}

#: Kraken's v2 stream names these assets otherwise than its `wsname`.
V2_NAMES = {"XBT": "BTC", "XDG": "DOGE"}
#: How many pages of Kraken's trades a gap or a range is read through:
#: 10,000 trades.
TRADE_PAGES = 10
_SIDES = {"b": "buy", "s": "sell", "buy": "buy", "sell": "sell"}

LIMITS = Limits(
    allowed=(
        "Public REST limited by IP, and OHLC and Trades by pair; about one call a second "
        "stays inside (Kraken's documentation)"
    ),
    spent=f"At most {RATE_PER_SECOND:g} a second, bursts of {BURST}; a rate limit waited out",
    most_candles=MOST_CANDLES,
    history_days=MOST_CANDLES,
)


def asset(code: str) -> Asset:
    """One Kraken asset, by its code."""
    if code in FIAT:
        return Asset(code, "currency", "iso4217", FIAT[code])
    if code in NATIVE:
        return Asset(code, "token", "caip19", NATIVE[code])
    return Asset(code, "token")


def listing(pairs: Mapping[str, Any]) -> list[Listed]:
    """Every pair Kraken lists, by its key, each side read as an asset, with its
    name on the v2 stream. A pair not `online` is kept with its status: its
    history still converts."""
    listed: list[Listed] = []
    for key, item in pairs.items():
        status = str(item.get("status") or "")
        listed.append(
            Listed(
                product=str(key),
                base=asset(str(item["base"])),
                quote=asset(str(item["quote"])),
                tradable=status == "online",
                status=status,
                stream=stream_name(str(item.get("wsname") or "")),
            )
        )
    return sorted(listed, key=lambda p: p.product)


def stream_name(wsname: str) -> str:
    """A pair's name on Kraken's v2 stream, from its `wsname` (`XBT/USD` is
    `BTC/USD`); empty where Kraken gives none."""
    return "/".join(V2_NAMES.get(part, part) for part in wsname.split("/")) if wsname else ""


_RFC3339 = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})"
)


def rfc3339_ns(text: str) -> int:
    """An RFC 3339 time, to the nanosecond, as the v2 stream states one."""
    match = _RFC3339.fullmatch(text)
    if match is None:
        raise ValueError(f"{text!r} is not an RFC 3339 time")
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    offset = _dt.timedelta()
    if zone != "Z":
        sign = 1 if zone[0] == "+" else -1
        offset = sign * _dt.timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6]))
    moment = _dt.datetime(
        int(year), int(month), int(day), int(hour), int(minute), int(second),
        tzinfo=_dt.timezone(offset),
    )  # fmt: skip
    return int(moment.timestamp()) * NANOS_PER_SECOND + int((fraction or "0").ljust(9, "0"))


def seconds_ns(value: object) -> int:
    """Seconds since the epoch, as Kraken's `Trades` states them (a JSON
    number, read from its text), in nanoseconds, exactly."""
    try:
        return int(Decimal(str(value)) * NANOS_PER_SECOND)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{value!r} is not a time") from None


def candles(pair: str, entries: list[Any], raw_key: str) -> list[Candle]:
    """Daily OHLC entries, oldest first, each naming its place in the raw record."""
    read: list[Candle] = []
    for entry in sorted(entries, key=lambda e: int(e[0])):
        start = int(entry[0])
        if start % SECONDS_PER_DAY:
            raise ValueError(f"a daily entry at {start} does not start at 00:00 UTC")
        unread: list[Unread] = []

        def figure(field: str, value: object, unread: list[Unread] = unread) -> Any:
            amount = number(value)
            if amount is None:
                unread.append(Unread(f"ohlc.{field}", str(value)))
            return amount

        open_, high, low, close = (
            figure(field, entry[i]) for field, i in (("open", 1), ("high", 2), ("low", 3),
                                                      ("close", 4))
        )  # fmt: skip
        volume = figure("volume", entry[6])
        count = entry[7] if isinstance(entry[7], int) and not isinstance(entry[7], bool) else None
        if count is None:
            unread.append(Unread("ohlc.count", str(entry[7])))
        vwap = figure("vwap", entry[5]) if count else None
        read.append(
            Candle(
                product=pair,
                start_s=start,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                vwap=vwap,
                trade_count=count,
                raw_key=f"{raw_key}#{start}",
                unread=tuple(unread),
            )
        )
    return read


def tick(pair: str, body: Mapping[str, Any], raw_key: str, first_seen_ns: int) -> Tick:
    """The ticker's last trade (`c`), in force from when Kraken's answer first
    said it: Kraken's `Ticker` states no time."""
    stated = (body.get("c") or [None])[0]
    price = number(stated)
    return Tick(
        product=pair,
        price=price,
        at_ns=first_seen_ns,
        stated=False,
        ident=f"{raw_key.split('/')[1]}#{raw_key.rsplit('#', 1)[-1]}",
        raw_key=raw_key,
        unread=() if price is not None else (Unread("ticker.c", str(stated)),),
    )


def top(pair: str, body: Mapping[str, Any], raw_key: str, received_ns: int) -> Top:
    """`Depth`'s best bid and ask with their volumes, in force from the later
    side's time; a side with no order is None."""
    bids, asks = body.get("bids") or [], body.get("asks") or []
    unread: list[Unread] = []
    bid = number(bids[0][0]) if bids else None
    ask = number(asks[0][0]) if asks else None
    if bids and bid is None:
        unread.append(Unread("depth.bids.price", str(bids[0][0])))
    if asks and ask is None:
        unread.append(Unread("depth.asks.price", str(asks[0][0])))
    times = [int(side[0][2]) for side in (bids, asks) if side]
    at = max(times) * NANOS_PER_SECOND if times else received_ns
    return Top(
        product=pair,
        bid=bid,
        ask=ask,
        at_ns=at,
        stated=bool(times),
        ident=str(max(times)) if times else str(received_ns),
        raw_key=raw_key,
        unread=tuple(unread),
        bid_size=number(bids[0][1]) if bids else None,
        ask_size=number(asks[0][1]) if asks else None,
    )


def prints(pair: str, entries: list[Any], raw_key: str) -> list[Print]:
    """`Trades`' entries, oldest first, each its side the taker's."""
    read: list[Print] = []
    for entry in entries:
        price, volume = number(entry[0]), number(entry[1])
        side = _SIDES.get(str(entry[3]), "")
        ident = str(entry[6]) if len(entry) > 6 else ""
        unread = [Unread(f"trades.{f}", str(v)) for f, v, read_as in (("price", entry[0], price),
                  ("volume", entry[1], volume)) if read_as is None]  # fmt: skip
        read.append(
            Print(
                product=pair,
                price=price,
                quantity=volume,
                at_ns=seconds_ns(entry[2]),
                ident=ident,
                side=side,
                side_of=TAKER if side else "",
                raw_key=f"{raw_key}#{ident}",
                unread=tuple(unread),
            )
        )
    return sorted(read, key=lambda p: (p.at_ns, p.sequence))


def traded(item: Mapping[str, Any], raw_key: str) -> Print:
    """One trade of the stream's `trade` channel, its side the taker's."""
    price, qty = number(item.get("price")), number(item.get("qty"))
    side = _SIDES.get(str(item.get("side") or ""), "")
    unread = [Unread(f"trade.{f}", str(item.get(f))) for f, v in (("price", price), ("qty", qty))
              if v is None]  # fmt: skip
    return Print(
        product=str(item.get("symbol") or ""),
        price=price,
        quantity=qty,
        at_ns=rfc3339_ns(str(item["timestamp"])),
        ident=str(item.get("trade_id") or ""),
        side=side,
        side_of=TAKER if side else "",
        raw_key=raw_key,
        unread=tuple(unread),
    )


def ticked(item: Mapping[str, Any], raw_key: str, received_ns: int) -> Top:
    """The stream's `ticker`: the best bid and offer with their sizes."""
    unread: list[Unread] = []
    sides = []
    for side in ("bid", "ask"):
        stated = item.get(side)
        price = number(stated) if stated is not None else None
        if stated is not None and price is None:
            unread.append(Unread(f"ticker.{side}", str(stated)))
        qty = item.get(f"{side}_qty")
        sides.append((price, number(qty) if price is not None and qty is not None else None))
    stamp = item.get("timestamp")
    return Top(
        product=str(item.get("symbol") or ""),
        bid=sides[0][0],
        ask=sides[1][0],
        at_ns=rfc3339_ns(str(stamp)) if stamp else received_ns,
        stated=bool(stamp),
        ident=str(stamp or received_ns),
        raw_key=raw_key,
        unread=tuple(unread),
        bid_size=sides[0][1],
        ask_size=sides[1][1],
    )


class KrakenMarket:
    """Kraken's market data, as the shared data plugin's work asks for it."""

    venue = VENUE
    venue_identifiers = VENUE_IDENTIFIERS
    name = NAME

    def __init__(self, client: Kraken, mode: str = "live") -> None:
        self.client = client
        address = REST if mode == "live" else f"{mode}: no call leaves the deployment"
        stream = STREAM if mode == "live" else f"{mode}: no stream leaves the deployment"
        self.session = Session(
            mode=mode,
            endpoints=(
                Endpoint("REST", address, "asset pairs, daily OHLC, ticker, depth, trades"),
                Endpoint("WebSocket", stream, "trades, and the best bid and offer"),
            ),
            limits=LIMITS,
            health=client.health,
        )
        self._replays = 0

    @property
    def stream_address(self) -> str:
        return STREAM

    async def connect(self, address: str) -> Socket:
        """Kraken's v2 stream; in synthetic mode its sessions replayed in turn
        from files, the last one held open."""
        if self.session.mode == "live":
            return await websocket(address, USER_AGENT)
        sessions: list[list[str]] = getattr(self.client.transport, "stream_sessions", list)()
        held = sessions[min(self._replays, len(sessions) - 1)] if sessions else []
        self._replays += 1
        # Every connection but the last drops once it has said its messages,
        # as the venue's do; the last is held open.
        return Replayed(held, hold=self._replays >= len(sessions))

    def subscriptions(self, names: Sequence[str]) -> list[str]:
        trade = {"channel": "trade", "symbol": list(names), "snapshot": True}
        ticker = {"channel": "ticker", "symbol": list(names), "event_trigger": "bbo",
                  "snapshot": True}  # fmt: skip
        return [json.dumps({"method": "subscribe", "params": p}) for p in (trade, ticker)]

    def heard(self, text: str, received_ns: int) -> list[Print | Top]:
        """One message of the stream, kept first; its trades or its tickers
        read. A heartbeat is neither kept nor read; the status, a
        subscription's answer or an error is kept, and states neither."""
        try:
            body = json_decimal(text)
        except ValueError:
            body = {}
        channel = str(body.get("channel") or body.get("method") or "unread") if isinstance(
            body, dict) else "unread"  # fmt: skip
        if channel == "heartbeat":
            return []
        raw_key = self.client.store.keep_line("stream", channel, {
            "venue": VENUE, "call": "stream", "request": {"method": "GET", "url": STREAM},
            "received_at_ns": received_ns, "status": 101, "headers": {}, "body": text,
        })  # fmt: skip
        if isinstance(body, dict) and body.get("success") is False:  # a pair refused
            self.client.health.last_error = f"stream: {body.get('error')}"[:200]
        read: list[Print | Top] = []
        try:
            for item in body.get("data") or [] if channel in ("trade", "ticker") else []:
                if channel == "trade":
                    read.append(traded(item, raw_key))
                else:
                    read.append(ticked(item, raw_key, received_ns))
        except (KeyError, ValueError) as unread:
            self.client.health.last_error = f"stream: a {channel} that did not read: {unread}"[:200]
        return read

    def listing(self) -> list[Listed]:
        return listing(self.client.asset_pairs().value)

    def candles(self, product: str, first: date, last: date) -> list[Candle]:
        start, end = day_start(first), day_start(last)
        fetched = self.client.ohlc(product, start - 1)
        entries = result_for(fetched.value, product)
        return [c for c in candles(product, entries, fetched.raw_key) if start <= c.start_s <= end]

    def last(self, product: str) -> Tick:
        fetched = self.client.ticker(product)
        kept = self.client.store.get(fetched.raw_key) or {}
        first_seen = int(kept.get("received_at_ns", fetched.received_at_ns))
        return tick(product, result_for(fetched.value, product), fetched.raw_key, first_seen)

    def top(self, product: str) -> Top:
        fetched = self.client.depth(product)
        return top(product, result_for(fetched.value, product), fetched.raw_key,
                   fetched.received_at_ns)  # fmt: skip

    def trades(self, product: str, since_ns: int = 0) -> list[Print]:
        """The pair's trades from `since_ns` to now, oldest first, a page at a
        time through at most TRADE_PAGES; the latest page where it is 0."""
        read: list[Print] = []
        seen: set[str] = set()
        since = since_ns
        for _ in range(TRADE_PAGES):
            fetched = self.client.trades(product, since)
            entries = result_for(fetched.value, product)
            for trade in prints(product, entries, fetched.raw_key):
                if not trade.ident or trade.ident not in seen:
                    seen.add(trade.ident)
                    read.append(trade)
            last = int(str(fetched.value.get("last") or 0))
            if not since_ns or len(entries) < MOST_TRADES or last <= since:
                break
            since = last
        return read
