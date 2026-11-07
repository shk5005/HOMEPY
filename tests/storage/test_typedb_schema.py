import pytest
from typedb.driver import TypeDB, SessionType, TransactionType

DB_NAME = "homepy_test"


def _typedb_reachable() -> bool:
    try:
        driver = TypeDB.core_driver("localhost:1729")
        driver.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _typedb_reachable(),
    reason="TypeDB server not reachable at localhost:1729",
)


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


def test_rules_load_without_error(typedb_client):
    # schema.tql already loaded by earlier test in this module
    with open("storage/typedb/rules.tql") as f:
        rules = f.read()
    with typedb_client.session(DB_NAME, SessionType.SCHEMA) as session:
        with session.transaction(TransactionType.WRITE) as tx:
            tx.query.define(rules)
            tx.commit()


def test_undervalued_rule_fires(typedb_client):
    """Insert a complex near a subway with price below district avg;
    verify undervalued-signal is inferred."""
    with typedb_client.session(DB_NAME, SessionType.DATA) as session:
        with session.transaction(TransactionType.WRITE) as tx:
            tx.query.insert("""
                insert
                $d isa dong, has dong-code "11010", has dong-name "test-dong";
                $c isa complex, has complex-id "C001", has complex-name "test",
                    has price-per-sqm 15000000, has district-avg-price 20000000,
                    has total-units 500, has built-year 2000,
                    has floor-area-ratio 250.0, has building-coverage 60.0;
                $inf isa infrastructure, has infra-id "S001",
                    has infra-name "test-station", has infra-type "subway",
                    has infra-status "operating";
                (parent: $d, child: $c) isa spatial-hierarchy;
                (location: $c, facility: $inf) isa accessibility,
                    has distance-meter 300, has travel-time-min 5;
            """)
            tx.commit()
        with session.transaction(TransactionType.READ) as tx:
            result = tx.query.get("match (subject: $c) isa undervalued-signal; get $c;")
            answers = list(result)
            assert len(answers) >= 1
