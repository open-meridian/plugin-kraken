"""The stream: the WebSocket spoken with the standard library.

This plugin's own transport, which the SDK leaves to it (ruling 1027). The
socket is held to RFC 6455 over in-memory streams (a frame as a server sends
one, and as a client must). Keeping it open -- its reopening, its waits, its
silence and its names wanted -- is the SDK's supervisor's from 0.11.0
(`pairs.supervised`), proved by the SDK's own cases and, over this plugin's
synthetic venue, by the data role's checks (tests/test_data_role.py).
"""

from __future__ import annotations

import asyncio
import struct
from typing import Any

import pytest

from kraken import stream


class _Writer:
    """What a client wrote, as asyncio's StreamWriter takes it."""

    def __init__(self) -> None:
        self.written = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.written += data

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


def _frame(opcode: int, payload: bytes, fin: bool = True) -> bytes:
    """A frame as a server sends it: unmasked."""
    head = (0x80 if fin else 0) | opcode
    if len(payload) < 126:
        return struct.pack("!BB", head, len(payload)) + payload
    return struct.pack("!BBH", head, 126, len(payload)) + payload


def _socket(*frames: bytes) -> tuple[Any, _Writer]:
    reader = asyncio.StreamReader()
    for frame in frames:
        reader.feed_data(frame)
    reader.feed_eof()
    writer = _Writer()
    return stream.WebSocket(reader, writer), writer  # type: ignore[arg-type]


def _unmask(written: bytes) -> tuple[int, bytes]:
    """A client's frame read back: its opcode and payload, unmasked."""
    opcode, second = written[0] & 0x0F, written[1]
    assert second & 0x80, "a client masks every frame"
    size, at = second & 0x7F, 2
    if size == 126:
        (size,), at = struct.unpack("!H", written[2:4]), 4
    mask = written[at : at + 4]
    payload = bytes(b ^ mask[i % 4] for i, b in enumerate(written[at + 4 : at + 4 + size]))
    return opcode, payload


async def test_a_text_frame_is_sent_masked() -> None:
    socket, writer = _socket()
    await socket.send('{"type":"subscribe"}')
    assert _unmask(bytes(writer.written)) == (0x1, b'{"type":"subscribe"}')


async def test_a_long_message_and_fragments_are_read_whole() -> None:
    long = b"x" * 300
    socket, _ = _socket(_frame(0x1, long), _frame(0x1, b"one ", fin=False),
                        _frame(0x0, b"message"))  # fmt: skip
    assert await socket.receive() == "x" * 300
    assert await socket.receive() == "one message"


async def test_a_ping_is_answered_with_its_pong() -> None:
    socket, writer = _socket(_frame(0x9, b"alive?"), _frame(0x1, b"after"))
    assert await socket.receive() == "after"
    assert _unmask(bytes(writer.written)) == (0xA, b"alive?")


async def test_a_close_is_answered_and_said() -> None:
    socket, writer = _socket(_frame(0x8, struct.pack("!H", 1001) + b"going away"))
    with pytest.raises(stream.Closed, match="1001 going away"):
        await socket.receive()
    assert _unmask(bytes(writer.written))[0] == 0x8 and writer.closed


async def test_the_end_of_the_connection_is_closed() -> None:
    socket, _ = _socket()
    with pytest.raises(stream.Closed):
        await socket.receive()
