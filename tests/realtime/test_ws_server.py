import asyncio

import pytest

from homepy.realtime.ws_server import ConnectionManager


class MockWebSocket:
    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.sent = []
        self.closed = False
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.sent.append(data)

    async def close(self, code=1000):
        self.closed = True


@pytest.fixture
def connection_manager():
    return ConnectionManager(send_timeout=0.2)


async def test_connection_manager_tracks_count(connection_manager):
    ws = MockWebSocket()
    await connection_manager.connect(ws, "11680")
    assert ws.accepted
    assert connection_manager.get_connection_count("11680") == 1
    await connection_manager.disconnect(ws, "11680")
    assert connection_manager.get_connection_count("11680") == 0


async def test_broadcast_reaches_only_district_clients(connection_manager):
    a, b = MockWebSocket(), MockWebSocket()
    await connection_manager.connect(a, "11680")
    await connection_manager.connect(b, "11650")
    await connection_manager.broadcast("11680", {"price": 1})
    assert a.sent == [{"price": 1}]
    assert b.sent == []


async def test_slow_consumer_disconnected(connection_manager):
    slow, fast = MockWebSocket(delay=5), MockWebSocket()
    await connection_manager.connect(slow, "11680")
    await connection_manager.connect(fast, "11680")
    await connection_manager.broadcast("11680", {"test": True})
    assert connection_manager.get_connection_count("11680") == 1
    assert slow.closed and fast.sent == [{"test": True}]


async def test_message_dropped_while_send_in_flight():
    mgr = ConnectionManager(send_timeout=2)
    ws = MockWebSocket(delay=0.1)
    await mgr.connect(ws, "11680")
    await asyncio.gather(mgr.broadcast("11680", {"n": 1}), mgr.broadcast("11680", {"n": 2}))
    assert ws.sent == [{"n": 1}] and mgr.dropped == 1


@pytest.mark.skip(reason="requires live Redis + HTTP WebSocket server")
async def test_ws_connect_and_receive():
    ...


@pytest.mark.skip(reason="requires live app/WebSocket client")
async def test_ws_rejects_no_token():
    ...


@pytest.mark.skip(reason="requires live app/WebSocket client")
async def test_ws_rejects_expired_token():
    ...
