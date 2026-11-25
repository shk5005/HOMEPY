import fnmatch
import json

import pytest


class MockPubSub:
    def __init__(self, redis):
        self.redis = redis
        self.patterns = []
        self.queue = []

    async def psubscribe(self, *patterns):
        self.patterns.extend(patterns)
        self.redis.pubsubs.append(self)

    async def get_message(self, ignore_subscribe_messages=False, timeout=0.0):
        return self.queue.pop(0) if self.queue else None

    async def punsubscribe(self, *a):
        self.patterns.clear()

    async def close(self):
        pass


class MockRedis:
    def __init__(self):
        self.published_messages = {}
        self.pubsubs = []

    async def publish(self, channel, message):
        self.published_messages.setdefault(channel, []).append(
            json.loads(message) if isinstance(message, (str, bytes)) else message)
        for ps in self.pubsubs:
            if any(fnmatch.fnmatch(channel, p) for p in ps.patterns):
                ps.queue.append({"type": "pmessage", "channel": channel, "data": message})
        return len(self.pubsubs)

    def pubsub(self):
        return MockPubSub(self)


class MockTimescale:
    def __init__(self):
        self.calls = []

    async def execute(self, query, *args):
        self.calls.append((query, args))
        return []

    def inserted_count(self, table):
        return sum(1 for q, _ in self.calls if q.lstrip().upper().startswith("INSERT INTO " + table.upper()))


class MockTypeDB:
    def __init__(self):
        self.updates = []

    def update_snapshot(self, district_code, event_type, data):
        self.updates.append((district_code, event_type, data))


@pytest.fixture
def mock_redis():
    return MockRedis()


@pytest.fixture
def mock_timescale():
    return MockTimescale()


@pytest.fixture
def mock_typedb():
    return MockTypeDB()
