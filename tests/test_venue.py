"""The client: every answer kept before it is read, an error under HTTP 200
said, a rate limit waited out, and synthetic mode's two transports answering
as Kraken does."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from meridian.edge import RawStore

from kraken.synthetic import Recorded, Synthetic
from kraken.venue import Kraken, RateLimiter, Response, VenueError, result_for


def _client(tmp_path: Path, transport: object) -> Kraken:
    clock = iter(range(1_791_633_600_000_000_000, 1_791_633_700_000_000_000, 1_000))
    return Kraken(
        RawStore(tmp_path),
        transport=transport,  # type: ignore[arg-type]
        limiter=RateLimiter(1000.0, 1000, sleep=lambda _: None),
        clock_ns=lambda: next(clock),
        sleep=lambda _: None,
    )


class Scripted:
    def __init__(self, *answers: Response) -> None:
        self.answers = list(answers)
        self.asked: list[str] = []

    def __call__(self, url: str, headers: Mapping[str, str]) -> Response:
        self.asked.append(url)
        assert "User-Agent" in headers
        return self.answers.pop(0)


def test_every_answer_is_kept_before_it_is_read(tmp_path: Path) -> None:
    client = _client(tmp_path, Scripted(Response(200, {"age": "2"}, b'{"error":[],"result":{}}')))
    fetched = client.assets()
    kept = client.store.get(fetched.raw_key)
    assert kept is not None and kept["body"] == '{"error":[],"result":{}}'
    assert fetched.raw_key.startswith("responses/2026-10-10/Assets/")


def test_an_error_under_http_200_is_said_and_kept(tmp_path: Path) -> None:
    body = b'{"error":["EQuery:Unknown asset pair"]}'
    client = _client(tmp_path, Scripted(Response(200, {}, body)))
    with pytest.raises(VenueError) as refused:
        client.ticker("NOPEUSD")
    assert "Unknown asset pair" in str(refused.value) and client.store.get(refused.value.raw_key)
    assert client.health.failures == 1


def test_a_rate_limit_under_http_200_is_waited_out_and_counted(tmp_path: Path) -> None:
    limited = Response(200, {}, b'{"error":["EGeneral:Too many requests"]}')
    client = _client(tmp_path, Scripted(limited, Response(200, {}, b'{"error":[],"result":{}}')))
    assert client.asset_pairs().value == {}
    assert (client.health.rate_limited, client.health.calls) == (1, 2)


def test_no_answer_is_said(tmp_path: Path) -> None:
    def down(url: str, headers: Mapping[str, str]) -> Response:
        raise OSError("connection refused")

    with pytest.raises(VenueError):
        _client(tmp_path, down).assets()


def test_ohlc_is_asked_daily_since_a_time(tmp_path: Path) -> None:
    transport = Scripted(Response(200, {}, b'{"error":[],"result":{"XXBTZUSD":[],"last":0}}'))
    client = _client(tmp_path, transport)
    client.ohlc("XXBTZUSD", 1791417599)
    assert "interval=1440" in transport.asked[0] and "since=1791417599" in transport.asked[0]


def test_a_result_is_found_by_the_pairs_key() -> None:
    assert result_for({"XXBTZUSD": [1], "last": 5}, "XBTUSD") == [1]
    with pytest.raises(KeyError):
        result_for({"A": 1, "B": 2}, "C")


def test_a_live_answer_unchanged_is_not_kept_again(tmp_path: Path) -> None:
    client = _client(tmp_path, Synthetic())
    first, second = client.depth("XXBTZUSD"), client.depth("XXBTZUSD")
    assert first.raw_key == second.raw_key and first.raw_key.endswith(".jsonl#0")


def test_synthetic_answers_krakens_shapes(tmp_path: Path) -> None:
    client = _client(tmp_path, Synthetic())
    assert {"XXBTZUSD", "XBTUSDC", "USDCUSD", "ZEURZUSD"} <= set(client.asset_pairs().value)
    entries = client.ohlc("XXBTZUSD", 1791331200).value["XXBTZUSD"]
    assert [e[0] for e in entries] == [1791417600, 1791504000], "after since, oldest first"
    with pytest.raises(VenueError):
        client.depth("NOPEUSD")


def test_recorded_exchanges_are_replayed_from_a_plugins_raw_records(tmp_path: Path) -> None:
    recording = _client(tmp_path / "kept", Synthetic())
    recording.asset_pairs()
    recording.ohlc("XXBTZUSD", 0)
    recording.ticker("XXBTZUSD")
    replay = _client(tmp_path / "replayed", Recorded(tmp_path / "kept" / "responses"))
    assert set(replay.asset_pairs().value) == set(recording.asset_pairs().value)
    entries = replay.ohlc("XXBTZUSD", 1791417599).value["XXBTZUSD"]
    assert [e[0] for e in entries] == [1791417600, 1791504000]
    assert entries[0][4] == "62001.40000"
    assert replay.ticker("XXBTZUSD").value["XXBTZUSD"]["c"][0] == "61988.90000"


def test_trades_are_asked_a_thousand_at_a_time_since_a_time(tmp_path: Path) -> None:
    empty = b'{"error":[],"result":{"XXBTZUSD":[],"last":"0"}}'
    scripted = Scripted(Response(200, {}, empty), Response(200, {}, empty))
    client = _client(tmp_path, scripted)
    client.trades("XXBTZUSD")
    client.trades("XXBTZUSD", 1_791_633_590_000_000_000)
    assert scripted.asked[0].endswith("/Trades?pair=XXBTZUSD&count=1000")
    assert scripted.asked[1].endswith("/Trades?pair=XXBTZUSD&count=1000&since=1791633590000000000")


def test_a_recording_replays_its_stream_and_its_trades(tmp_path: Path) -> None:
    from kraken.convert import KrakenMarket

    kept = KrakenMarket(_client(tmp_path / "kept", Synthetic()), "synthetic")
    kept.client.trades("XXBTZUSD")
    said = ['{"channel":"status","type":"update","data":[]}',
            '{"channel":"trade","type":"update","data":[{"symbol":"BTC/USD","side":"buy",'
            '"price":1.5,"qty":0.1,"ord_type":"limit","trade_id":9,'
            '"timestamp":"2026-10-10T11:00:00Z"}]}']  # fmt: skip
    for at, text in enumerate(said):
        kept.heard(text, 1_791_633_600_000_000_000 + at)
    replay = Recorded(tmp_path / "kept" / "responses")
    assert replay.stream_sessions() == [said]
    trades = result_for(_client(tmp_path / "replayed", replay).trades("XXBTZUSD").value,
                        "XXBTZUSD")  # fmt: skip
    assert [str(t[6]) for t in trades][-1] == "110938306"


def test_a_stream_line_as_the_first_recorder_kept_it_is_replayed(tmp_path: Path) -> None:
    # The recordings of 2026-10-03 keep each stream message as its text and
    # when it arrived, before the stream's raw records named their call.
    trade = '{"channel":"trade","type":"update","data":[]}'
    lines = [{"received_at_ns": 2, "text": trade}, {"received_at_ns": 1, "text": "first"}]
    (tmp_path / "stream").mkdir()
    (tmp_path / "stream" / "1.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
    assert Recorded(tmp_path).stream_sessions() == [["first", trade]]
