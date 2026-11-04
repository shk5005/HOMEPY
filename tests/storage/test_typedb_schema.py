import pytest
from typedb.driver import TypeDB, SessionType, TransactionType

DB_NAME = "homepy_test"

@pytest.fixture(scope="module")
def typedb_client():
    with TypeDB.core_driver("localhost:1729") as driver:
        if driver.databases.contains(DB_NAME):
            driver.databases.get(DB_NAME).delete()
        driver.databases.create(DB_NAME)
        yield driver
        driver.databases.get(DB_NAME).delete()

def test_schema_loads_without_error(typedb_client):
    with open("storage/typedb/schema.tql") as f:
        schema = f.read()
    with typedb_client.session(DB_NAME, SessionType.SCHEMA) as session:
        with session.transaction(TransactionType.WRITE) as tx:
            tx.query.define(schema)
            tx.commit()

def test_all_entity_types_exist(typedb_client):
    with typedb_client.session(DB_NAME, SessionType.SCHEMA) as session:
        with session.transaction(TransactionType.READ) as tx:
            expected = [
                "region", "district", "dong", "complex", "unit-type",
                "interest-rate", "exchange-rate", "liquidity", "price-index",
                "real-estate-cycle", "cycle-observation",
                "loan-product", "loan-regulation", "loan-regulation-rule",
                "acquisition-tax", "acquisition-tax-rate",
                "capital-gains-tax", "cgt-rate-rule",
                "comprehensive-re-tax", "crt-rate-rule",
                "inheritance-tax", "gift-tax", "gift-tax-rate", "property-tax",
                "policy", "zone-designation", "price-control",
                "subscription-regulation",
                "population-data", "migration-data", "income-data",
                "supply-data", "unsold-inventory", "reconstruction-supply",
                "infrastructure", "development-project", "market-sentiment",
            ]
            for name in expected:
                concept = tx.concepts.get_entity_type(name).resolve()
                assert concept is not None, f"Entity type '{name}' missing"


def test_all_relation_types_exist(typedb_client):
    with typedb_client.session(DB_NAME, SessionType.SCHEMA) as session:
        with session.transaction(TransactionType.READ) as tx:
            expected_relations = [
                "spatial-hierarchy", "has-unit-type", "accessibility",
                "macro-drives-cycle", "rate-affects-loan",
                "zone-applied-to", "regulation-applies", "loan-constraint",
                "tax-applies-to", "cgt-applies-to", "crt-applies-to",
                "policy-impact", "policy-targets-tax",
                "demand-in-area", "supply-in-area",
                "cycle-observed-at", "development-influence",
                "sentiment-observation", "comparable",
            ]
            for name in expected_relations:
                concept = tx.concepts.get_relation_type(name).resolve()
                assert concept is not None, f"Relation type '{name}' missing"
