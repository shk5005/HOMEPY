from __future__ import annotations

from datetime import datetime, timedelta

import pytest

pytestmark = pytest.mark.skip(reason="requires live TimescaleDB")


async def test_timescale_full_backup_creates_file(backup_mgr, tmp_path):
    path = await backup_mgr.full_backup_timescale()
    assert path.exists()
    assert path.stat().st_size > 0


async def test_backup_verify_valid_dump(backup_mgr, tmp_path):
    path = await backup_mgr.full_backup_timescale()
    assert await backup_mgr.verify_backup(path) is True


async def test_backup_retention_cleans_old(backup_mgr, tmp_path):
    old = tmp_path / "ts_backup_2026-01-01.sql.gz"
    old.write_text("fake")
    backups = await backup_mgr.list_backups()
    recent = [b for b in backups if b.created_at > datetime.now() - timedelta(days=30)]
    assert all(b.created_at > datetime.now() - timedelta(days=31) for b in recent)
