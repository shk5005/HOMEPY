"""TypeDB warm-standby manager (snapshot export/import)."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DATABASE = "homepy"


class TypeDBStandbyManager:
    def __init__(self, primary_addr: str, standby_addr: str, export_dir: str) -> None:
        self.primary_addr = primary_addr
        self.standby_addr = standby_addr
        self.export_dir = Path(export_dir)

    @property
    def _meta_path(self) -> Path:
        return self.export_dir / "last_export.json"

    async def _run(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"{args[0]} failed ({proc.returncode}): {err.decode(errors='replace')}"
            )
        return out.decode(errors="replace")

    async def export_snapshot(self) -> Path:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        started = datetime.now()
        stamp = started.strftime("%Y%m%dT%H%M%S")
        schema = self.export_dir / f"{DATABASE}_{stamp}.schema.tql"
        snapshot = self.export_dir / f"{DATABASE}_{stamp}.typedb"
        await self._run(
            "typedb", "console", f"--address={self.primary_addr}",
            "--command", f"database export {DATABASE} {schema} {snapshot}",
        )
        self._meta_path.write_text(
            json.dumps({"timestamp": started.isoformat(), "snapshot": str(snapshot)})
        )
        return snapshot

    async def import_to_standby(self, snapshot: Path) -> None:
        schema = snapshot.with_name(snapshot.name.replace(".typedb", ".schema.tql"))
        await self._run(
            "typedb", "console", f"--address={self.standby_addr}",
            "--command", f"database import {DATABASE} {schema} {snapshot}",
        )

    async def promote_standby(self) -> None:
        meta = self._read_meta()
        if meta is None:
            raise RuntimeError("no snapshot available to promote standby")
        snapshot = Path(meta["snapshot"])
        await self.import_to_standby(snapshot)
        logger.warning(
            "Standby promoted from snapshot %s; data after %s may be lost (RPO gap)",
            snapshot, meta["timestamp"],
        )

    async def last_export_timestamp(self) -> datetime | None:
        meta = self._read_meta()
        if meta is None:
            return None
        return datetime.fromisoformat(meta["timestamp"])

    def _read_meta(self) -> dict | None:
        try:
            return json.loads(self._meta_path.read_text())
        except (FileNotFoundError, ValueError):
            return None
