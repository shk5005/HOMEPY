"""TimescaleDB -> TypeDB: push aggregate attributes onto TypeDB entities (spec 4.5)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

TYPEDB_BATCH_SIZE = 500  # >1000 entities per transaction can time out; stay well under.
DEFAULT_DB = "homepy"


@dataclass(frozen=True)
class AggregateMapping:
    name: str
    sql: str  # must return columns: key, value
    entity_type: str
    key_attr: str
    attr: str
    value_type: str = "double"  # double | string


MAPPINGS: tuple[AggregateMapping, ...] = (
    AggregateMapping(
        "complex_price_per_sqm",
        "SELECT complex_id AS key, AVG(price_krw / area_m2)::float8 AS value "
        "FROM ts_real_trade WHERE NOT is_cancelled AND area_m2 > 0 "
        "AND ts >= now() - interval '12 months' GROUP BY complex_id",
        "complex", "complex-id", "price-per-sqm"),
    AggregateMapping(
        "complex_district_avg_price",
        "SELECT complex_id AS key, AVG(d.avg_price)::float8 AS value FROM ("
        "  SELECT DISTINCT complex_id, district_code FROM ts_real_trade) c "
        "JOIN (SELECT district_code, AVG(price_krw / NULLIF(area_m2, 0)) AS avg_price FROM ts_real_trade "
        "      WHERE NOT is_cancelled AND ts >= now() - interval '12 months' "
        "      GROUP BY district_code) d USING (district_code) GROUP BY complex_id",
        "complex", "complex-id", "district-avg-price"),
)


@dataclass
class SyncReport:
    mappings: dict[str, int] = field(default_factory=dict)  # name -> entities updated
    batches: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.mappings.values())


def _lit(value, value_type: str) -> str:
    if value_type == "string":
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'
    return repr(float(value))


def build_statements(m: AggregateMapping, key, value) -> list[tuple[str, str]]:
    """Upsert = delete the old attribute value, then insert the new one."""
    k = _lit(key, "string")
    match = f"match $e isa {m.entity_type}, has {m.key_attr} {k}"
    return [
        ("delete", f"{match}, has {m.attr} $old; delete $e has $old;"),
        ("insert", f"{match}; insert $e has {m.attr} {_lit(value, m.value_type)};"),
    ]


async def sync_aggregates_to_typedb(timescale_svc, typedb_svc, db: str = DEFAULT_DB,
                                    mappings: tuple[AggregateMapping, ...] = MAPPINGS,
                                    batch_size: int = TYPEDB_BATCH_SIZE) -> SyncReport:
    batch_size = min(batch_size, TYPEDB_BATCH_SIZE)
    report = SyncReport()
    for m in mappings:
        try:
            rows = await timescale_svc.execute(m.sql)
        except Exception as exc:  # keep syncing other mappings
            logger.exception("aggregate query failed: %s", m.name)
            report.errors.append(f"{m.name}: {exc}")
            continue
        rows = [r for r in rows if r["key"] is not None and r["value"] is not None]
        done = 0
        for i in range(0, len(rows), batch_size):
            chunk = rows[i:i + batch_size]
            stmts = [s for r in chunk for s in build_statements(m, r["key"], r["value"])]
            try:
                typedb_svc.execute_write_many(db, stmts)
            except Exception as exc:
                logger.exception("typedb batch failed: %s", m.name)
                report.errors.append(f"{m.name}: {exc}")
                continue
            report.batches += 1
            done += len(chunk)
        report.mappings[m.name] = done
    return report
