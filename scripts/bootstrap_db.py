"""Bootstrap HOMEPY databases (idempotent).

Usage (from project root):  python scripts/bootstrap_db.py

- TypeDB: creates database if missing, loads storage/typedb/schema.tql and rules.tql
- TimescaleDB: runs storage/timescale/schema.sql and hypertables.sql statement by
  statement (continuous aggregates cannot run inside a transaction block).
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TYPEDB_ADDRESS = "localhost:1729"
TYPEDB_DB = "homepy"
TIMESCALE_DSN = "postgresql://homepy:homepy@localhost:5432/homepy"

TYPEDB_DIR = ROOT / "storage" / "typedb"
TIMESCALE_DIR = ROOT / "storage" / "timescale"


def split_statements(sql: str) -> list[str]:
    """Split SQL into statements ending with ';' at end of line."""
    sql = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in re.split(r";[ \t]*\n", sql + "\n") if s.strip()]


def bootstrap_typedb(address: str = TYPEDB_ADDRESS, db: str = TYPEDB_DB) -> dict:
    from typedb.driver import SessionType, TransactionType, TypeDB

    from homepy.storage.typedb_service import TypeDBService

    try:
        driver = TypeDB.core_driver(address)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Cannot connect to TypeDB at {address}. Is it running? "
            f"Try: docker compose up -d  ({exc})"
        ) from exc
    try:
        created = not driver.databases.contains(db)
        if created:
            driver.databases.create(db)
    finally:
        driver.close()

    with TypeDBService(address) as svc:
        svc.load_schema(db, str(TYPEDB_DIR / "schema.tql"))
        svc.load_schema(db, str(TYPEDB_DIR / "rules.tql"))

    driver = TypeDB.core_driver(address)
    try:
        with driver.session(db, SessionType.SCHEMA) as session:
            with session.transaction(TransactionType.READ) as tx:
                entities = [
                    c.get("x").get_label().name
                    for c in tx.query.get("match $x sub entity; get $x;")
                ]
                relations = [
                    c.get("x").get_label().name
                    for c in tx.query.get("match $x sub relation; get $x;")
                ]
    finally:
        driver.close()
    return {
        "created": created,
        "entity_types": len([e for e in entities if e != "entity"]),
        "relation_types": len([r for r in relations if r != "relation"]),
    }


async def bootstrap_timescale(dsn: str = TIMESCALE_DSN) -> dict:
    import asyncpg

    try:
        conn = await asyncpg.connect(dsn)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Cannot connect to TimescaleDB ({dsn}). Is it running? "
            f"Try: docker compose up -d  ({exc})"
        ) from exc
    try:
        for name in ("schema.sql", "hypertables.sql"):
            for stmt in split_statements((TIMESCALE_DIR / name).read_text(encoding="utf-8")):
                await conn.execute(stmt)
        tables = await conn.fetchval(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name LIKE 'ts\\_%'"
        )
        hypertables = await conn.fetchval(
            "SELECT count(*) FROM timescaledb_information.hypertables"
        )
    finally:
        await conn.close()
    return {"tables": tables, "hypertables": hypertables}


def main() -> int:
    try:
        tdb = bootstrap_typedb()
        print(
            f"TypeDB '{TYPEDB_DB}': {'created' if tdb['created'] else 'already existed'}; "
            f"{tdb['entity_types']} entity types, {tdb['relation_types']} relation types"
        )
        ts = asyncio.run(bootstrap_timescale())
        print(f"TimescaleDB: {ts['tables']} ts_* tables, {ts['hypertables']} hypertables")
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Bootstrap complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
