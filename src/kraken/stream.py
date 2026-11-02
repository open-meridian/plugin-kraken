"""A venue's stream: one WebSocket, spoken with the standard library.

This plugin's own transport, which the SDK leaves to it (ruling 1027: the
WebSocket code lives in each plugin), opened by the market (`convert.py`'s
`connect`) for the SDK's feed. What is said on the stream -- the
subscription, and what each message means -- is `convert.py`'s; the socket
is here. Keeping it open -- reopening it after a drop or a silence, the
wait between, the gap read back -- is the SDK's supervisor's from 0.11.0
(`meridian.roles.data.pairs.supervised` over `helpers.sessions.Supervisor`,
open-meridian 0.35), never a loop of the plugin's own.

**The socket** (RFC 6455, client side): a TLS connection, the HTTP upgrade
with its key checked against the answer's accept, text frames masked as a
client must, a ping answered with its pong, fragments joined, and a close
answered. No extension is asked for, so no message arrives compressed. The
plugin depends on nothing but the SDK, so there is no WebSocket library.

**Kept open** (the plan's row 19), by the SDK's supervisor: a stream that
drops, or says nothing for 30 seconds, is opened again after a wait that
doubles from one second to a minute, within a fifth either way, reset once
a connection has stayed up a minute: inside Kraken's 150 reconnects in ten
minutes per IP. Each time it opens, the feed reads the gap from the venue's
REST history (the trades after the last one it recorded), and readers catch
up from the lake by the watermark they last saw.

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
import os
import ssl
import struct
import urllib.parse
from collections.abc import Sequence
from typing import Protocol

#: The WebSocket accept's suffix (RFC 6455, 1.3).
_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
#: The longest message read: a venue's snapshot is far shorter.
MOST_BYTES = 16 * 1024 * 1024


class Closed(Exception):
    """The socket closed, or broke."""


class Socket(Protocol):
    async def send(self, text: str) -> None: ...

    async def receive(self) -> str:
        """The next text message; `Closed` once the socket is."""
        ...

    async def close(self) -> None: ...


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
