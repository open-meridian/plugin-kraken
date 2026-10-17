"""A venue's stream: one WebSocket, spoken with the standard library, and kept
open -- reconnected after a drop, the gap filled from the venue's history.

This plugin's own transport, which the SDK leaves to it (open-meridian
0.30.0: a plugin stays able to use an API, FIX or another protocol), handed
to the SDK's feed as its stream factory. What is said on the stream -- the
subscription, and what each message means -- is `convert.py`'s; the socket,
the reconnecting and the pacing are here.

**The socket** (RFC 6455, client side): a TLS connection, the HTTP upgrade
with its key checked against the answer's accept, text frames masked as a
client must, a ping answered with its pong, fragments joined, and a close
answered. No extension is asked for, so no message arrives compressed. The
plugin depends on nothing but the SDK, so there is no WebSocket library.

**Kept open** (the plan's row 19): a stream that drops, or says nothing for
`SILENT_SECONDS`, is opened again after a wait that doubles from one second
to a minute, reset once a connection has stayed up a minute: inside Kraken's
150 reconnects in ten minutes per IP, and Coinbase's. Each time it opens,
`opened` is called before any message is read, so the plugin can fill the gap
from the venue's REST history (the SDK's feed: the trades after the last
one it recorded), and readers catch up from the lake by the watermark they last
saw.

**Synthetic mode**: `Replayed` answers the subscription with messages shaped
exactly as the venue sends them, then falls silent, held open, or drops as a
venue's connection does; the synthetic venue's first connection drops, so
the reopening and the gap read back are proved in CI.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import logging
import os
import ssl
import struct
import time
import urllib.parse
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)

#: The WebSocket accept's suffix (RFC 6455, 1.3).
_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
#: The longest message read: a venue's snapshot is far shorter.
MOST_BYTES = 16 * 1024 * 1024
#: A stream that says nothing for this long is opened again: both venues send
#: a heartbeat or a ticker far more often.
SILENT_SECONDS = 30.0
#: The wait before opening again: doubling from the first to the most.
FIRST_WAIT, MOST_WAIT = 1.0, 60.0
#: A connection up this long resets the wait.
STEADY_SECONDS = 60.0


class Closed(Exception):
    """The socket closed, or broke."""


class Socket(Protocol):
    async def send(self, text: str) -> None: ...

    async def receive(self) -> str:
        """The next text message; `Closed` once the socket is."""
        ...

    async def close(self) -> None: ...


Connect = Callable[[str], Awaitable[Socket]]


class WebSocket:
    """One client WebSocket over asyncio's streams."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader, self.writer = reader, writer
        self.closed = False

    async def send(self, text: str) -> None:
        await self._frame(0x1, text.encode("utf-8"))

    async def _frame(self, opcode: int, payload: bytes) -> None:
        if self.closed:
            raise Closed("the socket is closed")
        mask = os.urandom(4)
        size = len(payload)
        if size < 126:
            head = struct.pack("!BB", 0x80 | opcode, 0x80 | size)
        elif size < 1 << 16:
            head = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, size)
        else:
            head = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, size)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        try:
            self.writer.write(head + mask + masked)
            await self.writer.drain()
        except (OSError, RuntimeError) as broken:
            self.closed = True
            raise Closed(str(broken)) from None

    async def _read(self, n: int) -> bytes:
        try:
            return await self.reader.readexactly(n)
        except (asyncio.IncompleteReadError, OSError) as broken:
            self.closed = True
            raise Closed(f"the stream ended: {broken}") from None

    async def receive(self) -> str:
        parts: list[bytes] = []
        while True:
            first, second = await self._read(2)
            fin, opcode = first & 0x80, first & 0x0F
            size = second & 0x7F
            if size == 126:
                (size,) = struct.unpack("!H", await self._read(2))
            elif size == 127:
                (size,) = struct.unpack("!Q", await self._read(8))
            if size > MOST_BYTES or sum(map(len, parts)) + size > MOST_BYTES:
                await self.close()
                raise Closed(f"a message longer than {MOST_BYTES} bytes")
            mask = await self._read(4) if second & 0x80 else b""
            payload = await self._read(size) if size else b""
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x9:
                await self._frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x8:
                with contextlib.suppress(Closed):
                    await self._frame(0x8, payload[:2])
                await self.close()
                code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else 1005
                raise Closed(f"closed by the venue, {code} {payload[2:].decode(errors='replace')}")
            parts.append(payload)
            if fin:
                return b"".join(parts).decode("utf-8", errors="replace")

    async def close(self) -> None:
        if not self.closed:
            self.closed = True
            with contextlib.suppress(Exception):
                self.writer.close()
                await asyncio.wait_for(self.writer.wait_closed(), 5)


async def websocket(url: str, user_agent: str = "meridian-data", timeout: float = 15.0) -> Socket:
    """A WebSocket opened to `url` (`wss://`), its upgrade checked."""
    split = urllib.parse.urlsplit(url)
    if split.scheme != "wss" or not split.hostname:
        raise ValueError(f"{url!r} is not a wss:// address")
    host, port = split.hostname, split.port or 443
    path = (split.path or "/") + (f"?{split.query}" if split.query else "")
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port, ssl=ssl.create_default_context(),
                                server_hostname=host),
        timeout,
    )  # fmt: skip
    key = base64.b64encode(os.urandom(16)).decode()
    writer.write(
        (
            f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\nUser-Agent: {user_agent}\r\n\r\n"
        ).encode()
    )
    await writer.drain()
    head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout)
    lines = head.decode("latin-1").split("\r\n")
    pairs = (h.partition(":") for h in lines[1:])
    headers = {k.strip().lower(): v.strip() for k, _, v in pairs if k}
    expected = base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()
    if " 101 " not in lines[0] + " " or headers.get("sec-websocket-accept") != expected:
        writer.close()
        raise Closed(f"the upgrade was refused: {lines[0]}")
    return WebSocket(reader, writer)


class Replayed:
    """A stream answered from messages shaped as the venue sends them: every
    message once the first subscription is sent, then silence, held open --
    or, not `hold`, `Closed`, as a dropped connection is."""

    def __init__(self, messages: Sequence[str], hold: bool = True) -> None:
        self.messages = list(messages)
        self.hold = hold
        self.sent: list[str] = []
        self._given = 0
        self._subscribed = asyncio.Event()
        self.closed = False

    async def send(self, text: str) -> None:
        self.sent.append(text)
        self._subscribed.set()

    async def receive(self) -> str:
        await self._subscribed.wait()
        if self._given < len(self.messages) and not self.closed:
            self._given += 1
            return self.messages[self._given - 1]
        if self.hold and not self.closed:
            await asyncio.Event().wait()  # silent, as a quiet market is, until cancelled
        self.closed = True
        raise Closed("the replay dropped the connection")

    async def close(self) -> None:
        self.closed = True


@dataclass
class StreamHealth:
    """How the stream has gone since the plugin started."""

    #: "off" (nothing to stream), "connecting", "open", or "waiting" to open
    #: again.
    state: str = "off"
    opened: int = 0
    dropped: int = 0
    messages: int = 0
    last_message_ns: int = 0
    opened_at_ns: int = 0
    last_error: str = ""
    #: The venue's names the stream is subscribed to now.
    subscribed: tuple[str, ...] = ()


@dataclass
class Stream:
    """One venue stream, kept open while there is something to stream.

    `subscriptions(names)` gives the texts to send for the venue's names;
    `heard(text)` is handed each message; `opened(names)` is called each time
    the stream opens, before any message is read."""

    address: str
    connect: Connect
    subscriptions: Callable[[Sequence[str]], list[str]]
    heard: Callable[[str], Awaitable[None]]
    opened: Callable[[Sequence[str]], Awaitable[None]]
    clock_ns: Callable[[], int] = time.time_ns
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    silent_seconds: float = SILENT_SECONDS
    health: StreamHealth = field(default_factory=StreamHealth)
    _wanted: tuple[str, ...] = ()
    _changed: asyncio.Event = field(default_factory=asyncio.Event)

    def retarget(
        self, address: str, connect: Connect, subscriptions: Callable[[Sequence[str]], list[str]]
    ) -> None:
        """Stream from another source (synthetic mode switched): reopened."""
        self.address, self.connect, self.subscriptions = address, connect, subscriptions
        self._changed.set()

    def want(self, names: Sequence[str]) -> None:
        """Stream these of the venue's names; nothing, to close it."""
        wanted = tuple(sorted(set(names)))
        if wanted != self._wanted:
            self._wanted = wanted
            self._changed.set()

    async def run(self, once: bool = False) -> None:
        """Keep the stream open while anything is wanted, until cancelled; with
        `once`, open it once and return when it closes."""
        wait = FIRST_WAIT
        while True:
            if not self._wanted:
                self.health.state, self.health.subscribed = "off", ()
                if once:
                    return
                self._changed.clear()
                await self._changed.wait()
                continue
            started = time.monotonic()
            changed = await self._session()
            if once:
                return
            if changed:
                wait = FIRST_WAIT
                continue
            wait = FIRST_WAIT if time.monotonic() - started >= STEADY_SECONDS else wait
            self.health.state = "waiting"
            await self.sleep(wait)
            wait = min(wait * 2, MOST_WAIT)

    async def _session(self) -> bool:
        """One connection, until it closes; whether the names wanted changed."""
        names = self._wanted
        self._changed.clear()
        self.health.state = "connecting"
        try:
            socket = await self.connect(self.address)
        except (OSError, Closed, ValueError, TimeoutError) as failed:
            self.health.last_error = f"not opened: {failed}"[:200]
            log.warning("the stream at %s did not open: %s", self.address, failed)
            return False
        self.health.opened += 1
        self.health.opened_at_ns = self.clock_ns()
        self.health.state, self.health.subscribed = "open", names
        try:
            for subscription in self.subscriptions(names):
                await socket.send(subscription)
            await self._said(self.opened, names)
            while not self._changed.is_set():
                text = await self._next(socket)
                if text is None:
                    break
                self.health.messages += 1
                self.health.last_message_ns = self.clock_ns()
                await self._said(self.heard, text)
        except Closed as dropped:
            self.health.dropped += 1
            self.health.last_error = str(dropped)[:200]
            log.warning("the stream at %s dropped: %s", self.address, dropped)
        finally:
            await socket.close()
            self.health.state = "waiting"
        return self._changed.is_set()

    async def _said(self, handler: Callable[[Any], Awaitable[None]], given: Any) -> None:
        """A handler's failure said, never the stream's end: the next message
        is read all the same."""
        try:
            await handler(given)
        except Exception as failed:  # noqa: BLE001 - said; the stream goes on
            self.health.last_error = f"not handled: {failed}"[:200]
            log.warning("a message of the stream at %s not handled: %s", self.address, failed)

    async def _next(self, socket: Socket) -> str | None:
        """The next message; None where the wanted names changed (opened again
        with the new ones); `Closed` after `silent_seconds` of nothing, where
        it is not 0 (a replay, which is silent once it has said everything)."""
        receiving = asyncio.ensure_future(socket.receive())
        changed = asyncio.ensure_future(self._changed.wait())
        try:
            done, _ = await asyncio.wait(
                {receiving, changed}, timeout=self.silent_seconds or None,
                return_when=asyncio.FIRST_COMPLETED,
            )  # fmt: skip
        finally:
            changed.cancel()
        if receiving in done:
            return receiving.result()
        receiving.cancel()
        with contextlib.suppress(asyncio.CancelledError, Closed):
            await receiving
        if changed in done or self._changed.is_set():
            return None
        raise Closed(f"silent for {self.silent_seconds:g} seconds")
