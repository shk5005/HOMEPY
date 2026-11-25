from __future__ import annotations

from datetime import datetime

import pytest

from homepy.ha.neo4j_standby import Neo4jStandbyManager

pytestmark = pytest.mark.skip(reason="requires live Neo4j")


async def test_neo4j_export_creates_file(neo4j_primary, tmp_path):
    mgr = Neo4jStandbyManager(neo4j_primary.addr, "localhost:7688", str(tmp_path))
    snapshot = await mgr.export_snapshot()
    assert snapshot.exists()
    assert snapshot.suffix == ".dump"


async def test_neo4j_export_timestamp_recorded(neo4j_primary, tmp_path):
    mgr = Neo4jStandbyManager(neo4j_primary.addr, "localhost:7688", str(tmp_path))
    before = datetime.now()
    await mgr.export_snapshot()
    ts = await mgr.last_export_timestamp()
    assert ts is not None
    assert ts >= before
