"""Thin synchronous wrapper around the TypeDB 2.x Python driver."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from typedb.driver import SessionType, TransactionType, TypeDB, TypeDBOptions


def _concept_value(concept: Any) -> Any:
    """Convert a TypeDB concept into a plain Python value."""
    if concept.is_attribute():
        return concept.get_value()
    if concept.is_entity() or concept.is_relation():
        return {
            "iid": concept.get_iid(),
            "type": concept.get_type().get_label().name,
        }
    if concept.is_type():
        return concept.get_label().name
    return str(concept)


class TypeDBService:
    def __init__(self, address: str) -> None:
        self.address = address
        self._driver = None

    def connect(self) -> None:
        if self._driver is None:
            self._driver = TypeDB.core_driver(self.address)

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def _require_driver(self):
        if self._driver is None:
            raise RuntimeError("TypeDBService is not connected; call connect() first")
        return self._driver

    def execute_read(self, db: str, query: str, infer: bool = False) -> list[dict]:
        driver = self._require_driver()
        with driver.session(db, SessionType.DATA) as session:
            options = TypeDBOptions(infer=True) if infer else None
            with session.transaction(TransactionType.READ, options) as tx:
                return [
                    {var: _concept_value(c) for var, c in cmap.map.items()}
                    for cmap in tx.query.get(query)
                ]

    def execute_write(self, db: str, query: str) -> None:
        driver = self._require_driver()
        with driver.session(db, SessionType.DATA) as session:
            with session.transaction(TransactionType.WRITE) as tx:
                # insert/delete/update return lazy iterators; drain them.
                for _ in tx.query.insert(query):
                    pass
                tx.commit()

    def execute_write_many(self, db: str, statements: list[tuple[str, str]]) -> None:
        """Run ``("insert"|"delete", query)`` statements in ONE write transaction.

        Callers are responsible for keeping batches small (sync layer uses 500).
        """
        if not statements:
            return
        driver = self._require_driver()
        with driver.session(db, SessionType.DATA) as session:
            with session.transaction(TransactionType.WRITE) as tx:
                for kind, query in statements:
                    if kind == "insert":
                        for _ in tx.query.insert(query):
                            pass
                    elif kind == "delete":
                        tx.query.delete(query).resolve()
                    else:
                        raise ValueError(f"unknown statement kind: {kind!r}")
                tx.commit()

    def load_schema(self, db: str, tql_path: str) -> None:
        driver = self._require_driver()
        tql = Path(tql_path).read_text(encoding="utf-8")
        with driver.session(db, SessionType.SCHEMA) as session:
            with session.transaction(TransactionType.WRITE) as tx:
                tx.query.define(tql)
                tx.commit()

    def __enter__(self) -> "TypeDBService":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
