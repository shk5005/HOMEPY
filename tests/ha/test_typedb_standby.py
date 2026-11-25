from __future__ import annotations

from datetime import datetime

import pytest

from homepy.ha.typedb_standby import TypeDBStandbyManager

pytestmark = pytest.mark.skip(reason="requires live TypeDB")


async def test_typedb_export_creates_file(typedb_primary, tmp_path):
    mgr = TypeDBStandbyManager(typedb_primary.addr, "localhost:11730", str(tmp_path))
    snapshot = await mgr.export_snapshot()
    assert snapshot.exists()
    assert snapshot.suffix == ".typedb"


async def test_typedb_export_timestamp_recorded(typedb_primary, tmp_path):
    mgr = TypeDBStandbyManager(typedb_primary.addr, "localhost:11730", str(tmp_path))
    before = datetime.now()
    await mgr.export_snapshot()
    ts = await mgr.last_export_timestamp()
    assert ts is not None
    assert ts >= before
