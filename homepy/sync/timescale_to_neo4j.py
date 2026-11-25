"""TimescaleDB -> Neo4j: push aggregate attributes onto Neo4j nodes (spec 4.5)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

NEO4J_BATCH_SIZE = 500
DEFAULT_DB = "homepy"


@dataclass(frozen=True)
class AggregateMapping:
    name: str
    sql: str  # must return columns: key, value
    node_label: str
    key_prop: str
    attr_prop: str
    value_type: str = "double"  # double | string


MAPPINGS: tuple[AggregateMapping, ...] = (
    AggregateMapping(
        "complex_price_per_sqm",
        "SELECT complex_id AS key, AVG(price_krw / area_m2)::float8 AS value "
        "FROM ts_real_trade WHERE NOT is_cancelled AND area_m2 > 0 "
        "AND ts >= now() - interval '12 months' GROUP BY complex_id",
        "Complex", "complexId", "pricePerSqm"),
    AggregateMapping(
        "complex_district_avg_price",
        "SELECT complex_id AS key, AVG(d.avg_price)::float8 AS value FROM ("
        "  SELECT DISTINCT complex_id, district_code FROM ts_real_trade) c "
        "JOIN (SELECT district_code, AVG(price_krw / NULLIF(area_m2, 0)) AS avg_price FROM ts_real_trade "
        "      WHERE NOT is_cancelled AND ts >= now() - interval '12 months' "
        "      GROUP BY district_code) d USING (district_code) GROUP BY complex_id",
        "Complex", "complexId", "districtAvgPrice"),
)


@dataclass
class SyncReport:
    mappings: dict[str, int] = field(default_factory=dict)  # name -> nodes updated
    batches: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.mappings.values())


def build_cypher(m: AggregateMapping, key, value) -> tuple[str, dict]:
    """MERGE upsert: set the aggregate property on the matching node."""
    query = (
        f"MATCH (n:{m.node_label} {{{m.key_prop}: $key}}) "
        f"SET n.{m.attr_prop} = $value"
    )
    params = {"key": str(key), "value": float(value) if m.value_type == "double" else str(value)}
    return query, params


async def sync_aggregates_to_neo4j(timescale_svc, neo4j_svc, db: str = DEFAULT_DB,
                                   mappings: tuple[AggregateMapping, ...] = MAPPINGS,
                                   batch_size: int = NEO4J_BATCH_SIZE) -> SyncReport:
    batch_size = min(batch_size, NEO4J_BATCH_SIZE)
    report = SyncReport()
    for m in mappings:
        try:
            rows = await timescale_svc.execute(m.sql)
        except Exception as exc:
            logger.exception("aggregate query failed: %s", m.name)
            report.errors.append(f"{m.name}: {exc}")
            continue
        rows = [r for r in rows if r["key"] is not None and r["value"] is not None]
        done = 0
        for i in range(0, len(rows), batch_size):
            chunk = rows[i:i + batch_size]
            stmts = [build_cypher(m, r["key"], r["value"]) for r in chunk]
            try:
                for query, params in stmts:
                    neo4j_svc.execute_write(db, query, **params)
            except Exception as exc:
                logger.exception("neo4j batch failed: %s", m.name)
                report.errors.append(f"{m.name}: {exc}")
                continue
            report.batches += 1
            done += len(chunk)
        report.mappings[m.name] = done
    return report
