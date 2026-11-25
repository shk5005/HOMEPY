"""Thin synchronous wrapper around the Neo4j 6.x Python driver."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neo4j import GraphDatabase


class Neo4jService:
    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        auth: tuple[str, str] = ("neo4j", "neo4j"),
    ) -> None:
        self.uri = uri
        self.auth = auth
        self._driver = None

    def connect(self) -> None:
        if self._driver is None:
            self._driver = GraphDatabase.driver(self.uri, auth=self.auth)

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def _require_driver(self):
        if self._driver is None:
            raise RuntimeError("Neo4jService is not connected; call connect() first")
        return self._driver

    def execute_read(
        self, db: str, query: str, infer: bool = False, **params: Any
    ) -> list[dict]:
        driver = self._require_driver()
        if infer:
            self.run_inference(db)
        with driver.session(database=db) as session:
            result = session.run(query, **params)
            return [record.data() for record in result]

    def execute_write(self, db: str, query: str, **params: Any) -> None:
        driver = self._require_driver()
        with driver.session(database=db) as session:
            session.run(query, **params)

    def execute_write_many(
        self, db: str, statements: list[tuple[str, str]]
    ) -> None:
        """Run ``("create"|"delete", cypher)`` statements in ONE transaction."""
        if not statements:
            return
        driver = self._require_driver()
        with driver.session(database=db) as session:
            with session.begin_transaction() as tx:
                for _kind, query in statements:
                    tx.run(query)
                tx.commit()

    def load_schema(self, db: str, cypher_path: str) -> None:
        driver = self._require_driver()
        text = Path(cypher_path).read_text(encoding="utf-8")
        stmts = [s.strip() for s in text.split(";") if s.strip() and not s.strip().startswith("//")]
        with driver.session(database=db) as session:
            for stmt in stmts:
                if stmt:
                    session.run(stmt)

    def run_inference(self, db: str) -> None:
        rules_path = Path(__file__).resolve().parents[2] / "storage" / "neo4j" / "rules.cypher"
        if not rules_path.exists():
            return
        text = rules_path.read_text(encoding="utf-8")
        stmts = [s.strip() for s in text.split(";") if s.strip() and not s.strip().startswith("//")]
        driver = self._require_driver()
        with driver.session(database=db) as session:
            for stmt in stmts:
                if stmt:
                    session.run(stmt)

    def __enter__(self) -> "Neo4jService":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
