"""The stream: the WebSocket spoken with the standard library, and kept open.

This plugin's own transport, which the SDK leaves to it. The socket is held
to RFC 6455 over in-memory streams (a frame as a server sends one, and as a
client must); the stream's reopening, its waits, its
silence and its names wanted, over replayed connections.
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


def _stream(sessions: list[list[str]], **kw: Any) -> tuple[Any, list[str], list[float]]:
    heard: list[str] = []
    waits: list[float] = []
    opened: list[tuple[str, ...]] = []
    replays = iter(sessions)

    async def connect(_: str) -> Any:
        said = next(replays, None)
        if said is None:
            raise OSError("refused")
        return stream.Replayed(said, hold=False)

    async def hear(text: str) -> None:
        heard.append(text)

    async def opening(names: Any) -> None:
        opened.append(tuple(names))

    async def wait(seconds: float) -> None:
        waits.append(seconds)
        if len(waits) > 6:
            raise asyncio.CancelledError

    kept = stream.Stream(address="wss://venue.example/ws", connect=connect,
                         subscriptions=lambda names: [f"subscribe {','.join(names)}"],
                         heard=hear, opened=opening, sleep=wait, **kw)  # fmt: skip
    kept.opened_names = opened  # type: ignore[attr-defined]
    return kept, heard, waits


async def test_a_drop_is_opened_again_after_a_doubling_wait() -> None:
    kept, heard, waits = _stream([["a", "b"], ["c"]])
    kept.want(["BTC-USD"])
    with pytest.raises(asyncio.CancelledError):
        await kept.run()
    assert heard == ["a", "b", "c"]
    assert kept.opened_names == [("BTC-USD",), ("BTC-USD",)]
    assert waits[:4] == [1.0, 2.0, 4.0, 8.0], "doubling, through drops and refusals alike"
    assert kept.health.opened == 2 and kept.health.dropped == 2
    assert "refused" in kept.health.last_error


async def test_nothing_wanted_opens_nothing() -> None:
    kept, heard, _ = _stream([["a"]])
    await kept.run(once=True)
    assert heard == [] and kept.health.opened == 0 and kept.health.state == "off"


async def test_a_silent_stream_is_closed_as_dropped() -> None:
    async def connect(_: str) -> Any:
        return stream.Replayed([], hold=True)

    async def nothing(*_: Any) -> None:
        return None

    kept = stream.Stream(address="wss://venue.example/ws", connect=connect,
                         subscriptions=lambda names: ["subscribe"], heard=nothing,
                         opened=nothing, silent_seconds=0.05)  # fmt: skip
    kept.want(["BTC-USD"])
    await kept.run(once=True)
    assert kept.health.dropped == 1 and "silent" in kept.health.last_error


async def test_the_names_wanted_changed_open_it_again_with_them() -> None:
    sent: list[list[str]] = []

    async def connect(_: str) -> Any:
        replay = stream.Replayed([], hold=True)
        sent.append(replay.sent)
        return replay

    async def nothing(*_: Any) -> None:
        return None

    kept = stream.Stream(address="wss://venue.example/ws", connect=connect,
                         subscriptions=lambda names: [",".join(names)], heard=nothing,
                         opened=nothing, silent_seconds=0)  # fmt: skip
    kept.want(["BTC-USD"])
    running = asyncio.ensure_future(kept.run())
    for _ in range(50):
        await asyncio.sleep(0)
    kept.want(["BTC-USD", "ETH-USD"])
    for _ in range(50):
        await asyncio.sleep(0)
    kept.want([])
    for _ in range(50):
        await asyncio.sleep(0)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert sent == [["BTC-USD"], ["BTC-USD,ETH-USD"]]
    assert kept.health.state == "off" and kept.health.dropped == 0
