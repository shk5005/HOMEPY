"""Bootstrap HOMEPY databases (idempotent).

Usage (from project root):  python scripts/bootstrap_db.py

- Neo4j: loads storage/neo4j/schema.cypher and rules.cypher
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

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "homepy"
NEO4J_DB = "homepy"
TIMESCALE_DSN = "postgresql://homepy:homepy@localhost:5432/homepy"

NEO4J_DIR = ROOT / "storage" / "neo4j"
TIMESCALE_DIR = ROOT / "storage" / "timescale"


def split_statements(sql: str) -> list[str]:
    """Split SQL into statements ending with ';' at end of line."""
    sql = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in re.split(r";[ \t]*\n", sql + "\n") if s.strip()]


def bootstrap_neo4j(uri: str = NEO4J_URI, user: str = NEO4J_USER,
                    password: str = NEO4J_PASSWORD, db: str = NEO4J_DB) -> dict:
    from homepy.storage.neo4j_service import Neo4jService

    try:
        svc = Neo4jService(uri, user, password)
        svc.connect()
    except Exception as exc:
        raise RuntimeError(
            f"Cannot connect to Neo4j at {uri}. Is it running? "
            f"Try: docker compose up -d  ({exc})"
        ) from exc

    try:
        svc.load_schema(db, str(NEO4J_DIR / "schema.cypher"))
        svc.load_schema(db, str(NEO4J_DIR / "rules.cypher"))

        results = svc.execute_read(db, "CALL db.labels() YIELD label RETURN count(label) AS cnt")
        label_count = results[0]["cnt"] if results else 0

        results = svc.execute_read(db, "CALL db.relationshipTypes() YIELD relationshipType RETURN count(relationshipType) AS cnt")
        rel_count = results[0]["cnt"] if results else 0
    finally:
        svc.close()

    return {
        "node_labels": label_count,
        "relationship_types": rel_count,
    }


async def bootstrap_timescale(dsn: str = TIMESCALE_DSN) -> dict:
    import asyncpg

    try:
        conn = await asyncpg.connect(dsn)
    except Exception as exc:
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
        neo = bootstrap_neo4j()
        print(
            f"Neo4j '{NEO4J_DB}': "
            f"{neo['node_labels']} node labels, {neo['relationship_types']} relationship types"
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
