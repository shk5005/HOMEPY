"""Backup manager for TimescaleDB, Neo4j and raw data archives."""
from __future__ import annotations

import asyncio
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from homepy.ha.neo4j_standby import Neo4jStandbyManager


@dataclass
class BackupConfig:
    timescale_retain_days: int = 30
    neo4j_retain_days: int = 7
    raw_retain_days: int = 365
    backup_dir: str = "/backups"
    timescale_dsn: str = "postgresql://homepy:homepy@localhost:5432/homepy"
    neo4j_primary_addr: str = "bolt://localhost:7687"
    neo4j_standby_addr: str = "bolt://localhost:7688"


@dataclass
class BackupInfo:
    path: Path
    component: str
    created_at: datetime
    size_bytes: int
    verified: bool = False


class BackupManager:
    def __init__(self, config: BackupConfig) -> None:
        self.config = config
        self.backup_dir = Path(config.backup_dir)
        self._neo4j = Neo4jStandbyManager(
            config.neo4j_primary_addr,
            config.neo4j_standby_addr,
            str(self.backup_dir / "neo4j"),
        )

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

    async def full_backup_timescale(self) -> Path:
        d = self.backup_dir / "timescale"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"ts_backup_{datetime.now().strftime('%Y-%m-%dT%H%M%S')}.dump"
        await self._run("pg_dump", "-Fc", "-Z", "6", "-f", str(path),
                        self.config.timescale_dsn)
        self._rotate(d, self.config.timescale_retain_days)
        return path

    async def export_neo4j(self) -> Path:
        path = await self._neo4j.export_snapshot()
        self._rotate(self.backup_dir / "neo4j", self.config.neo4j_retain_days)
        return path

    async def archive_raw_data(self, source_dir: str, dest_dir: str) -> int:
        src, dst = Path(source_dir), Path(dest_dir)
        dst.mkdir(parents=True, exist_ok=True)
        count = 0
        for f in src.rglob("*.parquet"):
            target = dst / f.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.stat().st_mtime < f.stat().st_mtime:
                shutil.copy2(f, target)
                count += 1
        self._rotate(dst, self.config.raw_retain_days)
        return count

    async def verify_backup(self, backup_path: Path) -> bool:
        if not backup_path.exists() or backup_path.stat().st_size == 0:
            return False
        try:
            await self._run("pg_restore", "--list", str(backup_path))
        except (RuntimeError, FileNotFoundError):
            return False
        return True

    async def list_backups(self) -> list[BackupInfo]:
        result: list[BackupInfo] = []
        for component in ("timescale", "neo4j"):
            d = self.backup_dir / component
            if not d.exists():
                continue
            for f in sorted(d.iterdir()):
                if not f.is_file() or f.name == "last_export.json":
                    continue
                st = f.stat()
                result.append(BackupInfo(
                    path=f, component=component,
                    created_at=datetime.fromtimestamp(st.st_mtime),
                    size_bytes=st.st_size, verified=False,
                ))
        return result

    @staticmethod
    def _rotate(directory: Path, retain_days: int) -> None:
        if not directory.exists():
            return
        cutoff = time.time() - retain_days * 86400
        for f in directory.rglob("*"):
            if f.is_file() and f.name != "last_export.json" \
                    and f.stat().st_mtime < cutoff:
                f.unlink()
