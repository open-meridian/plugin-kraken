"""Kraken's answers read into the venue's values: its assets, daily OHLC,
ticker, level-1 book, trades and v2 stream (convert.py), on the shapes Kraken
sends."""

from __future__ import annotations

import json
import zlib
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast

from meridian.edge import RawStore
from meridian.roles.data import json_decimal, number
from meridian.roles.data.pairs import Print, Top

from kraken import convert
from kraken.synthetic import Synthetic
from kraken.venue import STREAM, Kraken, RateLimiter

PAIRS = Synthetic().held["pairs"]


def test_a_documented_fiat_code_is_its_iso_4217_cash_instrument() -> None:
    usd = convert.asset("ZUSD")
    assert (usd.kind, usd.scheme, usd.value, usd.currency_code) == (
        "currency",
        "iso4217",
        "USD",
        "USD",
    )
    assert convert.asset("CHF").currency_code == "CHF"


def test_a_z_is_no_sign_of_a_currency() -> None:
    for code in ("ZAMA", "ZBCN", "ZARS"):
        assert convert.asset(code).kind == "token", code


def test_a_native_coin_carries_its_slip44_caip19() -> None:
    assert convert.asset("XXBT").value == "bip122:000000000019d6689c085ae165831e93/slip44:0"
    assert convert.asset("XETH").value == "eip155:1/slip44:60"


def test_every_other_token_is_krakens_own_instrument() -> None:
    for code in ("USDC", "USDT", "TKN"):
        token = convert.asset(code)
        assert (token.kind, token.scheme, token.currency_code) == ("token", "", ""), code


def test_pairs_by_their_keys_a_stablecoin_never_its_currency() -> None:
    listed = {p.product: p for p in convert.listing(PAIRS)}
    assert listed["XBTUSDC"].quote.code == "USDC" and not listed["XBTUSDC"].quote.currency_code
    assert listed["ZEURZUSD"].base.currency_code == "EUR"
    assert not listed["OLDUSD"].tradable and listed["OLDUSD"].status == "cancel_only"


def test_ohlc_is_read_from_its_strings_with_vwap_and_count() -> None:
    body = json_decimal(
        '[[1791417600,"62431.3","62580.9","61750.0","0.000012345678901234","62190.7",'
        '"904.71000000",31877]]'
    )
    [candle] = convert.candles("XXBTZUSD", body, "responses/x.json")
    assert candle.close == Decimal("0.000012345678901234") and str(candle.open) == "62431.3"
    assert (candle.vwap, candle.trade_count) == (Decimal("62190.7"), 31877)
    assert candle.day == date(2026, 10, 8) and candle.raw_key == "responses/x.json#1791417600"


def test_a_day_that_traded_nothing_has_no_volume_weighted_price() -> None:
    [candle] = convert.candles(
        "QDTUSD", [[1791417600, "3.20", "3.20", "3.20", "3.20", "0.00", "0.00000000", 0]], "k"
    )
    assert (candle.vwap, candle.trade_count, candle.volume) == (None, 0, Decimal("0.00000000"))


def test_a_figure_that_does_not_read_is_kept_as_sent() -> None:
    [candle] = convert.candles("XXBTZUSD", [[1791417600, "1", "2", "1", "n/a", "1", "5", 2]], "k")
    assert candle.close is None
    assert [(u.field, u.text) for u in candle.unread] == [("ohlc.close", "n/a")]


def test_an_entry_not_on_a_utc_midnight_is_refused() -> None:
    try:
        convert.candles("XXBTZUSD", [[1791417601, "1", "1", "1", "1", "1", "1", 1]], "k")
    except ValueError as refused:
        assert "00:00 UTC" in str(refused)
    else:
        raise AssertionError("an entry off midnight was read")


def test_the_ticker_states_no_time_and_the_book_its_sides_times() -> None:
    ticker = Synthetic().held["ticker"]["XXBTZUSD"]
    tick = convert.tick("XXBTZUSD", ticker, "responses/2026-10-10/Ticker/XXBTZUSD.jsonl#4", 77)
    assert (tick.price, tick.at_ns, tick.stated, tick.ident) == (
        Decimal("61988.90000"),
        77,
        False,
        "2026-10-10#4",
    )
    depth = Synthetic().held["depth"]["XXBTZUSD"]
    top = convert.top("XXBTZUSD", depth, "k", 5)
    assert (top.bid, top.ask, top.stated) == (Decimal("61988.80000"), Decimal("61989.00000"), True)
    assert top.at_ns == 1791590399 * 1_000_000_000
    empty = convert.top("XXBTZUSD", {"bids": [], "asks": []}, "k", 7)
    assert (empty.bid, empty.ask, empty.at_ns, empty.stated) == (None, None, 7, False)


def test_number_refuses_what_is_not_the_contracts_decimal() -> None:
    assert number("62431.30000") == Decimal("62431.30000")
    for refused in (None, True, 1.5, "NaN", "abc", "0." + "1" * 19):
        assert number(refused) is None, refused


def test_a_pair_is_named_on_the_v2_stream_with_xbt_as_btc() -> None:
    names = {p.product: p.stream for p in convert.listing(PAIRS)}
    assert names["XXBTZUSD"] == "BTC/USD" and names["XBTUSDC"] == "BTC/USDC"
    assert names["ZEURZUSD"] == "EUR/USD"
    assert convert.stream_name("XDG/USD") == "DOGE/USD" and convert.stream_name("") == ""


def test_a_trade_names_the_takers_side_its_time_read_exactly() -> None:
    body = json_decimal(json.dumps({"r": Synthetic().held["trades"]["XXBTZUSD"]}))["r"]
    read = convert.prints("XXBTZUSD", body, "responses/Trades/XXBTZUSD.json")
    assert [p.ident for p in read][:2] == ["110938301", "110938302"]
    first = read[0]
    assert (first.side, first.side_of, first.price, first.quantity) == (
        "sell", "taker", Decimal("61990.10000"), Decimal("0.01500000"))  # fmt: skip
    assert first.at_ns == 1_791_633_590_123_400_000
    assert first.raw_key == "responses/Trades/XXBTZUSD.json#110938301"
    assert convert.seconds_ns(Decimal("1791657987.852269")) == 1_791_657_987_852_269_000


def _market(tmp_path: Path) -> convert.KrakenMarket:
    client = Kraken(RawStore(tmp_path), transport=Synthetic(),
                    limiter=RateLimiter(1000.0, 1000, sleep=lambda _: None))  # fmt: skip
    return convert.KrakenMarket(client, "synthetic")


def test_the_v2_streams_trades_and_ticker_are_read_and_kept_first(tmp_path: Path) -> None:
    market = _market(tmp_path)
    heard = market.heard(
        '{"channel":"trade","type":"update","data":[{"symbol":"BTC/USD","side":"buy",'
        '"price":62000.5,"qty":0.00010000,"ord_type":"limit","trade_id":7,'
        '"timestamp":"2026-10-10T11:00:00.500000Z"},{"symbol":"BTC/USD","side":"sell",'
        '"price":62000.4,"qty":0.2,"ord_type":"market","trade_id":8,'
        '"timestamp":"2026-10-10T11:00:00.600000Z"}]}',
        7,
    )
    prints = cast(list[Print], heard)
    assert [(p.product, p.side, p.side_of, p.ident) for p in prints] == [
        ("BTC/USD", "buy", "taker", "7"), ("BTC/USD", "sell", "taker", "8")]  # fmt: skip
    assert str(prints[0].quantity) == "0.00010000", "a JSON number read from its own text"
    kept = market.client.store.get(prints[0].raw_key)
    assert kept and kept["call"] == "stream" and kept["received_at_ns"] == 7
    heard = market.heard(
        '{"channel":"ticker","type":"update","data":[{"symbol":"BTC/USD","bid":62000.4,'
        '"bid_qty":1.25,"ask":62000.5,"ask_qty":0.5,"last":62000.5,'
        '"timestamp":"2026-10-10T11:00:00.700000Z"}]}',
        8,
    )
    [best] = cast(list[Top], heard)
    assert (best.bid, best.bid_size, best.ask, best.ask_size) == (
        Decimal("62000.4"), Decimal("1.25"), Decimal("62000.5"), Decimal("0.5"))  # fmt: skip
    assert best.at_ns == convert.rfc3339_ns("2026-10-10T11:00:00.700000Z")
    assert market.heard('{"channel":"heartbeat"}', 9) == []
    assert market.heard('{"channel":"status","type":"update","data":[]}', 9) == []
    assert sorted(p.stem for p in tmp_path.rglob("*.jsonl")) == ["status", "ticker", "trade"]


def test_the_subscription_asks_for_trades_each_change_of_the_best_and_depth(
    tmp_path: Path,
) -> None:
    trade, ticker, book = (json.loads(s) for s in _market(tmp_path).subscriptions(["BTC/USD"]))
    assert trade == {"method": "subscribe", "params": {"channel": "trade",
                     "symbol": ["BTC/USD"], "snapshot": True}}  # fmt: skip
    assert ticker["params"] == {"channel": "ticker", "symbol": ["BTC/USD"],
                                "event_trigger": "bbo", "snapshot": True}  # fmt: skip
    assert book["params"] == {"channel": "book", "symbol": ["BTC/USD"], "depth": 10,
                              "snapshot": True}  # fmt: skip


def test_depth_is_kept_raw_whole_and_read_into_no_row(tmp_path: Path) -> None:
    """Open question 232: the book's snapshot and each update kept exactly as
    sent, a line each, and nothing recorded from them."""
    market = _market(tmp_path)
    snapshot = ('{"channel":"book","type":"snapshot","data":[{"symbol":"BTC/USD",'
                '"bids":[{"price":61990.10,"qty":0.84}],"asks":[{"price":61990.20,"qty":0.5}],'
                '"checksum":1}]}')  # fmt: skip
    update = ('{"channel":"book","type":"update","data":[{"symbol":"BTC/USD",'
              '"bids":[{"price":61990.10,"qty":0.00000000}],"asks":[],"checksum":2,'
              '"timestamp":"2026-10-10T11:59:51.300000Z"}]}')  # fmt: skip
    assert market.heard(snapshot, 10) == [] and market.heard(update, 11) == []
    [kept] = tmp_path.rglob("*.jsonl")
    assert kept.name == "book.jsonl" and kept.parent.name == "stream"
    key = kept.relative_to(tmp_path).as_posix()
    for line, text, at in ((0, snapshot, 10), (1, update, 11)):
        record = market.client.store.get(f"{key}#{line}")
        assert record is not None
        assert (record["body"], record["call"], record["received_at_ns"]) == (text, "stream", at)
        assert record["venue"] == "kraken" and record["request"]["url"] == STREAM


def test_the_synthetic_books_checksums_hold() -> None:
    """Kraken's checksum (its v2 documentation): the top ten asks, lowest
    first, then the top ten bids, highest first, each price and quantity at
    the pair's decimals with the point and leading zeros dropped, as a CRC32;
    each synthetic update's over the book it leaves. So a depth converter
    proved on the synthetic stream later proves its rebuilt book too."""
    decimals = PAIRS["XXBTZUSD"]["pair_decimals"], PAIRS["XXBTZUSD"]["lot_decimals"]

    def text(figure: Decimal, places: int) -> str:
        return f"{figure:.{places}f}".replace(".", "").lstrip("0")

    sessions = Synthetic().stream_sessions()
    books = [json_decimal(m) for s in sessions for m in s if '"channel":"book","type"' in m]
    assert [b["type"] for b in books] == ["snapshot", "update", "snapshot"]
    book: dict[str, dict[Decimal, Decimal]] = {}
    for message in books:
        [item] = message["data"]
        if message["type"] == "snapshot":
            book = {"bids": {}, "asks": {}}
        for side in ("bids", "asks"):
            for level in item[side]:
                if level["qty"]:
                    book[side][level["price"]] = level["qty"]
                else:
                    book[side].pop(level["price"], None)
        asks = sorted(book["asks"].items())[:10]
        bids = sorted(book["bids"].items(), reverse=True)[:10]
        said = "".join(text(p, decimals[0]) + text(q, decimals[1]) for p, q in asks + bids)
        assert zlib.crc32(said.encode()) == item["checksum"]


def test_trades_are_read_from_the_time_asked_each_once(tmp_path: Path) -> None:
    read = _market(tmp_path).trades("XXBTZUSD", 1_791_633_592_000_100_000)
    assert [p.ident for p in read] == ["110938303", "110938304", "110938305", "110938306"]


async def test_a_synthetic_connection_drops_but_the_last_is_held_open(tmp_path: Path) -> None:
    market = _market(tmp_path)
    first, last = await market.connect(""), await market.connect("")
    assert (first.hold, last.hold) == (False, True)  # type: ignore[attr-defined]


def test_the_venue_is_known_by_its_own_code_having_no_mic() -> None:
    assert convert.VENUE_IDENTIFIERS == (("symbol", "kraken", "kraken"),)
