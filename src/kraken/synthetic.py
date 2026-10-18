"""Synthetic mode: Kraken's answers from files, never from Kraken.

A developer's setting (`synthetic`, shown only on a development deployment)
turns it on. The client asks exactly as it asks Kraken, keeps each answer as a
raw record and reads it the same way; only the transport differs:

- `Synthetic`: the synthetic exchanges this package carries (`synthetic/`),
  shaped exactly as Kraken documents and sends its answers -- every figure a
  string, refusals under HTTP 200 in an `error` list -- with invented values,
  and an invented token (TKN). They are what CI and `make e2e` replay.
- `Recorded`: a developer's own recorded exchanges -- the raw records a plugin
  kept of Kraken's real answers, recorded under personal use -- replayed by
  `make e2e-recorded` from a directory that is never committed (Kraken's
  terms ask its permission for non-personal use; the plan's Q11).

Each also answers the stream (contract v19) with `stream_sessions`: the
messages of each connection in turn, which the market replays
(convert.py's `connect`, stream.py's `Replayed`). The synthetic stream is
`synthetic/stream.jsonl`, a message a line exactly as Kraken's v2 sends it,
its figures JSON numbers; a line `{"synthetic": ...}`, never sent, is where
the synthetic venue drops the connection, so the next one opens and the gap
is read from `trades.json`. A recording replays the messages it kept, in the
order they arrived, as one connection.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Mapping
from decimal import Decimal
from importlib import resources
from pathlib import Path
from typing import Any

from .venue import Response

_HEADERS = {"cache-control": "no-store"}


def _answer(result: Any = None, error: list[str] | None = None) -> Response:
    body = {"error": error or [], **({"result": result} if result is not None else {})}
    return Response(200, dict(_HEADERS), json.dumps(body, default=str).encode("utf-8"))


def _unknown() -> Response:
    return _answer(error=["EQuery:Unknown asset pair"])


def _route(url: str) -> tuple[str, dict[str, str]]:
    split = urllib.parse.urlsplit(url)
    return split.path.rstrip("/").rsplit("/", 1)[-1], dict(urllib.parse.parse_qsl(split.query))


def _trades(pair: str, entries: list[list[Any]], query: Mapping[str, str]) -> Response:
    """Kraken's `Trades`: from `since` (nanoseconds) the oldest first, else the
    latest, at most `count`; `last` the time, in nanoseconds, of the last."""
    count = int(query.get("count", "1000"))
    since = int(query.get("since", "0"))
    ordered = sorted(entries, key=lambda e: Decimal(str(e[2])))
    after = [e for e in ordered if Decimal(str(e[2])) * 1_000_000_000 >= since]
    page = after[:count] if since else ordered[-count:]
    last = int(Decimal(str(page[-1][2])) * 1_000_000_000) if page else since
    body = {"error": [], "result": {pair: page, "last": str(last)}}
    return Response(200, dict(_HEADERS), _numbers(body).encode("utf-8"))


def _numbers(body: Any) -> str:
    """JSON with each Decimal written as the number it was read from: a
    recorded trade's time is a JSON number, as Kraken sends it."""
    marked = json.dumps(body, default=lambda value: f"\0{value}\0")
    return re.sub(r'"\\u0000([^"]*)\\u0000"', r"\1", marked)


def _ohlc(pair: str, entries: list[list[Any]], since: int) -> Response:
    after = sorted((e for e in entries if int(e[0]) > since), key=lambda e: int(e[0]))
    last = int(after[-1][0]) if after else since
    return _answer({pair: after, "last": last})


class Synthetic:
    """Answers from a directory of synthetic exchanges: `pairs.json` and
    `assets.json` as Kraken's results, `ohlc.json`, `ticker.json`,
    `depth.json` and `trades.json` each a result per pair (trades oldest
    first, each time a JSON number), and `stream.jsonl` the stream's
    messages."""

    def __init__(self, directory: Path | None = None) -> None:
        root = directory or Path(str(resources.files("kraken") / "synthetic"))
        self.held = {
            name: json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
            for name in ("pairs", "assets", "ohlc", "ticker", "depth", "trades")
        }
        lines = (root / "stream.jsonl").read_text(encoding="utf-8").splitlines()
        self.sessions: list[list[str]] = [[]]
        for line in lines:
            if line.startswith('{"synthetic"'):
                self.sessions.append([])
            elif line.strip():
                self.sessions[-1].append(line)

    def stream_sessions(self) -> list[list[str]]:
        return self.sessions

    def __call__(self, url: str, headers: Mapping[str, str]) -> Response:
        call, query = _route(url)
        pair = query.get("pair", "")
        if call == "AssetPairs":
            return _answer(self.held["pairs"])
        if call == "Assets":
            return _answer(self.held["assets"])
        if call == "OHLC":
            entries = self.held["ohlc"].get(pair)
            return _unknown() if entries is None else _ohlc(pair, entries, int(query["since"]))
        if call in ("Ticker", "Depth"):
            held = self.held[call.lower()].get(pair)
            return _unknown() if held is None else _answer({pair: held})
        if call == "Trades":
            entries = self.held["trades"].get(pair)
            return _unknown() if entries is None else _trades(pair, entries, query)
        return _answer(error=[f"EGeneral:Unknown method {call}"])


class Recorded:
    """Answers from a developer's recorded raw records (`meridian.edge.RawStore`'s files under a
    `responses/` directory): the latest good answer kept for each call and
    pair, and for OHLC every entry kept for the pair, after the `since`
    asked."""

    def __init__(self, directory: Path) -> None:
        self.latest: dict[tuple[str, str], Any] = {}
        self.entries: dict[str, dict[int, list[Any]]] = {}
        self.trades: dict[str, dict[str, list[Any]]] = {}
        heard: list[tuple[int, str]] = []
        for path in sorted(directory.rglob("*")):
            if path.suffix == ".json":
                records = [json.loads(path.read_text(encoding="utf-8"))]
            elif path.suffix == ".jsonl":
                lines = path.read_text(encoding="utf-8").splitlines()
                records = [json.loads(line) for line in lines]
            else:
                continue
            for record in records:
                if record.get("call") == "stream":
                    heard.append((int(record["received_at_ns"]), str(record["body"])))
                    continue
                if "call" not in record and "text" in record and "received_at_ns" in record:
                    # A stream message as the recorder of 2026-10-03 kept it,
                    # before the stream's raw records: its text and arrival.
                    heard.append((int(record["received_at_ns"]), str(record["text"])))
                    continue
                try:
                    body = json.loads(str(record["body"]), parse_float=Decimal)
                except (KeyError, ValueError):
                    continue
                if record.get("status") != 200 or body.get("error"):
                    continue
                call, query = _route(str(record["request"]["url"]))
                pair = query.get("pair", "")
                result = body.get("result") or {}
                if call == "OHLC":
                    for key, entries in result.items():
                        if key != "last":
                            for entry in entries:
                                self.entries.setdefault(pair, {})[int(entry[0])] = entry
                elif call in ("Ticker", "Depth"):
                    for value in (v for k, v in result.items() if k != "last"):
                        self.latest[(call, pair)] = value
                elif call == "Trades":
                    for key, entries in result.items():
                        if key != "last":
                            for entry in entries:
                                self.trades.setdefault(pair, {})[str(entry[6])] = entry
                else:
                    self.latest[(call, "")] = result
        self.heard = [body for _, body in sorted(heard, key=lambda h: h[0])]

    def stream_sessions(self) -> list[list[str]]:
        return [self.heard]

    def __call__(self, url: str, headers: Mapping[str, str]) -> Response:
        call, query = _route(url)
        pair = query.get("pair", "")
        if call == "OHLC":
            held = self.entries.get(pair)
            return _unknown() if held is None else _ohlc(pair, list(held.values()),
                                                         int(query["since"]))  # fmt: skip
        if call in ("Ticker", "Depth"):
            value = self.latest.get((call, pair))
            return _unknown() if value is None else _answer({pair: value})
        if call == "Trades":
            kept = self.trades.get(pair)
            return _unknown() if kept is None else _trades(pair, list(kept.values()), query)
        value = self.latest.get((call, ""))
        return _answer(value) if value is not None else _answer(error=["EGeneral:Not recorded"])
