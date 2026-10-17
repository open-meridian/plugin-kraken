"""Kraken's public market data: the one module that speaks to it.

REST at api.kraken.com/0/public/: `AssetPairs`, `Assets`, `OHLC` (daily, the
720 most recent entries at most), `Ticker`, `Depth` (the level-1 book) and
`Trades`; and from contract v19 the stream at ws.kraken.com/v2 (`STREAM`; the
socket is stream.py's, what is said on it convert.py's). No key: nothing
here holds a credential, and nothing is sent but the request.
The standard library's HTTP client; the plugin depends on nothing but the
SDK.

**Rate limits, honoured.** Kraken limits public REST by IP, and `OHLC` and
`Trades` by pair besides; about one call a second stays inside, so this
client spends at most that from a token bucket. A rate limit -- HTTP 429, or
Kraken's `EGeneral:Too many requests` under HTTP 200 -- is waited out, 2, 4,
8 seconds, and asked again at most three times, each one counted.

**Errors under HTTP 200.** Kraken answers most refusals with status 200 and a
non-empty `error` list: an answer is good only with an empty one.

**Every response is a raw record first** (`meridian.edge.RawStore`), kept exactly as its bytes
arrived, with its status and freshness headers, before anything is read from
it. A body is parsed with `json_decimal`: Kraken sends its figures as
strings, read as Decimals, and a JSON number, where one appears, from its
own text.

**Where it answers from.** Kraken itself; or, in synthetic mode, the synthetic
exchanges this package carries, or a developer's recorded ones, through the
same requests (synthetic.py).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from meridian.edge import RawStore
from meridian.roles.data import Health, json_decimal

REST = "https://api.kraken.com/0/public"
STREAM = "wss://ws.kraken.com/v2"
USER_AGENT = "meridian-kraken (+https://open-meridian.dev)"

#: About one call a second stays inside Kraken's public allowance.
RATE_PER_SECOND = 1.0
BURST = 1
#: Kraken's most daily OHLC entries: the 720 most recent.
MOST_CANDLES = 720
#: Kraken's most trades in one request, oldest first from `since`.
MOST_TRADES = 1000
RATE_LIMITED = ("EGeneral:Too many requests", "EAPI:Rate limit exceeded")
#: The headers kept with a record: freshness and rate limits.
KEPT_HEADERS = ("date", "cache-control", "age", "cf-cache-status", "retry-after")


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[str, Mapping[str, str]], Response]


def urllib_transport(url: str, headers: Mapping[str, str]) -> Response:
    """One GET over HTTPS, with the standard library."""
    request = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=15) as answer:
            return Response(
                answer.status, {k.lower(): v for k, v in answer.headers.items()}, answer.read()
            )
    except urllib.error.HTTPError as answer:
        return Response(
            answer.code, {k.lower(): v for k, v in answer.headers.items()}, answer.read()
        )


class RateLimiter:
    """A token bucket: `rate` calls a second, `burst` at once."""

    def __init__(
        self,
        rate: float,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.rate, self.burst = rate, burst
        self._clock, self._sleep = clock, sleep
        self._tokens = float(burst)
        self._at = clock()
        self.waited = 0.0

    def acquire(self) -> None:
        now = self._clock()
        self._tokens = min(self.burst, self._tokens + (now - self._at) * self.rate)
        self._at = now
        if self._tokens < 1:
            wait = (1 - self._tokens) / self.rate
            self._sleep(wait)
            self.waited += wait
            self._at = self._clock()
            self._tokens = 1.0
        self._tokens -= 1


class VenueError(Exception):
    """Kraken answered with an error, or something other than what was asked
    for, or did not answer."""

    def __init__(self, call: str, status: int, detail: str, raw_key: str = "") -> None:
        kept = f" (raw record {raw_key})" if raw_key else ""
        super().__init__(f"Kraken's {call}: {status or 'no answer'} {detail}{kept}")
        self.call, self.status, self.detail, self.raw_key = call, status, detail, raw_key


@dataclass(frozen=True)
class Fetched:
    """A response's `result`, the key of the raw record it was kept as, and
    when it arrived."""

    value: Any
    raw_key: str
    received_at_ns: int


class Kraken:
    """Kraken's public REST, every response kept."""

    def __init__(
        self,
        store: RawStore,
        transport: Transport = urllib_transport,
        limiter: RateLimiter | None = None,
        clock_ns: Callable[[], int] = time.time_ns,
        sleep: Callable[[float], None] = time.sleep,
        retries: int = 3,
    ) -> None:
        self.store, self.transport = store, transport
        self.limiter = limiter or RateLimiter(RATE_PER_SECOND, BURST)
        self.clock_ns, self.sleep, self.retries = clock_ns, sleep, retries
        self.health = Health()

    def _get(
        self, call: str, name: str, params: Mapping[str, str] | None = None, live: bool = False
    ) -> Fetched:
        url = f"{REST}/{call}" + (("?" + urllib.parse.urlencode(params)) if params else "")
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        for attempt in range(self.retries + 1):
            self.limiter.acquire()
            self.health.waited_seconds = self.limiter.waited
            self.health.calls += 1
            try:
                answer = self.transport(url, headers)
            except OSError as failed:
                self._failed(f"{call}: {failed}")
                raise VenueError(call, 0, str(failed)) from None
            received = self.clock_ns()
            text = answer.body.decode("utf-8", errors="replace")
            try:
                parsed = json_decimal(text)
            except json.JSONDecodeError:
                parsed = None
            errors = [str(e) for e in parsed.get("error") or []] if isinstance(parsed, dict) else []
            good = answer.status == 200 and not errors and isinstance(parsed, dict)
            record = {
                "venue": "kraken",
                "call": call,
                "request": {"method": "GET", "url": url},
                "received_at_ns": received,
                "status": answer.status,
                "headers": {h: answer.headers[h] for h in KEPT_HEADERS if h in answer.headers},
                "body": text,
            }
            raw_key = (
                self.store.keep_line(call, name, record)
                if live and good
                else self.store.keep(call, name, record)
            )
            limited = answer.status == 429 or any(e.startswith(RATE_LIMITED) for e in errors)
            if limited and attempt < self.retries:
                self.health.rate_limited += 1
                self.sleep(2.0 ** (attempt + 1))
                continue
            if not good:
                detail = "; ".join(errors) or text[:200]
                self._failed(f"{call}: {answer.status} {detail}")
                raise VenueError(call, answer.status, detail, raw_key)
            assert isinstance(parsed, dict)
            self.health.last_ok_ns = received
            return Fetched(parsed.get("result"), raw_key, received)
        raise AssertionError("unreachable")

    def _failed(self, why: str) -> None:
        self.health.failures += 1
        self.health.last_failed_ns = self.clock_ns()
        self.health.last_error = why

    def assets(self) -> Fetched:
        return self._get("Assets", "assets")

    def asset_pairs(self) -> Fetched:
        return self._get("AssetPairs", "pairs")

    def ohlc(self, pair: str, since_s: int) -> Fetched:
        """Daily OHLC entries after `since_s`: the 720 most recent at most, the
        last one the day still forming."""
        return self._get("OHLC", pair, {"pair": pair, "interval": "1440", "since": str(since_s)})

    def ticker(self, pair: str) -> Fetched:
        return self._get("Ticker", pair, {"pair": pair}, live=True)

    def trades(self, pair: str, since_ns: int = 0) -> Fetched:
        """The pair's trades from `since_ns` (UTC nanoseconds), oldest first, at
        most 1,000; the latest 1,000 where it is 0. `last` says where the next
        page starts."""
        params = {"pair": pair, "count": str(MOST_TRADES)}
        if since_ns:
            params["since"] = str(since_ns)
        return self._get("Trades", pair, params)

    def depth(self, pair: str) -> Fetched:
        """The best bid and ask, each with its volume and time (level 1)."""
        return self._get("Depth", pair, {"pair": pair, "count": "1"}, live=True)


def result_for(result: Mapping[str, Any], pair: str) -> Any:
    """The one pair's entry in a `result`: Kraken keys it by the pair's own key
    (`XXBTZUSD`) even when asked by its altname, beside `last`."""
    entries = {k: v for k, v in result.items() if k != "last"}
    if pair in entries:
        return entries[pair]
    if len(entries) == 1:
        return next(iter(entries.values()))
    raise KeyError(f"Kraken's result names {sorted(entries)}, not {pair!r}")
