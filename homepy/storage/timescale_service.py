"""Thin async wrapper around an asyncpg pool (raw SQL, no ORM)."""

from __future__ import annotations

import re
from datetime import date, datetime

import asyncpg

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"invalid SQL identifier: {name!r}")
    return name


class TimescaleService:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("TimescaleService is not connected; call connect() first")
        return self._pool

    async def execute(self, query: str, *args) -> list[asyncpg.Record]:
        async with self._require_pool().acquire() as conn:
            return await conn.fetch(query, *args)

    async def insert_batch(self, table: str, records: list[dict]) -> int:
        """Bulk insert via COPY. ISO strings are coerced for date/timestamp columns."""
        if not records:
            return 0
        _check_ident(table)
        columns = list(records[0].keys())
        for c in columns:
            _check_ident(c)
        async with self._require_pool().acquire() as conn:
            rows = await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = $1",
                table,
            )
            types = {r["column_name"]: r["data_type"] for r in rows}
            if not types:
                raise ValueError(f"unknown table: {table!r}")

            def coerce(col: str, val):
                if isinstance(val, str):
                    t = types.get(col, "")
                    if t.startswith("timestamp"):
                        return datetime.fromisoformat(val)
                    if t == "date":
                        return date.fromisoformat(val)
                return val

            data = [tuple(coerce(c, r.get(c)) for c in columns) for r in records]
            await conn.copy_records_to_table(table, records=data, columns=columns)
        return len(data)

    async def __aenter__(self) -> "TimescaleService":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
