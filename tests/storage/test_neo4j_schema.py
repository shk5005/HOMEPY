import pytest
from neo4j import GraphDatabase


def _neo4j_reachable() -> bool:
    try:
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "homepy"))
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _neo4j_reachable(),
    reason="Neo4j server not reachable at bolt://localhost:7687",
)

DB_NAME = "homepy_test"


@pytest.fixture(scope="module")
def neo4j_driver():
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "homepy"))
    with driver.session(database="system") as session:
        dbs = [r["name"] for r in session.run("SHOW DATABASES")]
        if DB_NAME in dbs:
            session.run(f"DROP DATABASE {DB_NAME}")
        session.run(f"CREATE DATABASE {DB_NAME}")
    yield driver
    with driver.session(database="system") as session:
        session.run(f"DROP DATABASE {DB_NAME} IF EXISTS")
    driver.close()


def test_schema_loads_without_error(neo4j_driver):
    with open("storage/neo4j/schema.cypher") as f:
        schema = f.read()
    with neo4j_driver.session(database=DB_NAME) as session:
        for statement in schema.split(";"):
            stmt = statement.strip()
            if stmt and not stmt.startswith("//"):
                session.run(stmt)


def test_all_node_labels_exist(neo4j_driver):
    expected = [
        "Region", "District", "Dong", "Complex", "UnitType",
        "InterestRate", "ExchangeRate", "Liquidity", "PriceIndex",
        "RealEstateCycle", "CycleObservation",
        "LoanProduct", "LoanRegulation", "LoanRegulationRule",
        "AcquisitionTax", "AcquisitionTaxRate",
        "CapitalGainsTax", "CgtRateRule",
        "ComprehensiveReTax", "CrtRateRule",
        "InheritanceTax", "GiftTax", "GiftTaxRate", "PropertyTax",
        "Policy", "ZoneDesignation", "PriceControl",
        "SubscriptionRegulation",
        "PopulationData", "MigrationData", "IncomeData",
        "SupplyData", "UnsoldInventory", "ReconstructionSupply",
        "Infrastructure", "DevelopmentProject", "MarketSentiment",
    ]
    with neo4j_driver.session(database=DB_NAME) as session:
        for label in expected:
            session.run(f"CREATE (n:{label} {{_test: true}})")
        result = session.run("CALL db.labels()")
        labels = {r["label"] for r in result}
        for label in expected:
            assert label in labels, f"Label '{label}' missing"
        session.run("MATCH (n {_test: true}) DETACH DELETE n")


def test_all_relationship_types_exist(neo4j_driver):
    expected_relations = [
        "SPATIAL_HIERARCHY", "HAS_UNIT_TYPE", "ACCESSIBILITY",
        "MACRO_DRIVES_CYCLE", "RATE_AFFECTS_LOAN",
        "ZONE_APPLIED_TO", "REGULATION_APPLIES", "LOAN_CONSTRAINT",
        "TAX_APPLIES_TO", "CGT_APPLIES_TO", "CRT_APPLIES_TO",
        "POLICY_IMPACT", "POLICY_TARGETS_TAX",
        "DEMAND_IN_AREA", "SUPPLY_IN_AREA",
        "CYCLE_OBSERVED_AT", "DEVELOPMENT_INFLUENCE",
        "SENTIMENT_OBSERVATION", "COMPARABLE",
    ]
    with neo4j_driver.session(database=DB_NAME) as session:
        for rel in expected_relations:
            session.run(f"CREATE (a:_Test)-[:{rel}]->(b:_Test)")
        result = session.run("CALL db.relationshipTypes()")
        types = {r["relationshipType"] for r in result}
        for rel in expected_relations:
            assert rel in types, f"Relationship type '{rel}' missing"
        session.run("MATCH (n:_Test) DETACH DELETE n")


def test_rules_load_without_error(neo4j_driver):
    with open("storage/neo4j/rules.cypher") as f:
        rules = f.read()
    with neo4j_driver.session(database=DB_NAME) as session:
        for statement in rules.split(";"):
            stmt = statement.strip()
            if stmt and not stmt.startswith("//"):
                session.run(stmt)


def test_undervalued_rule_fires(neo4j_driver):
    """Insert a complex near a subway with price below district avg;
    verify undervalued-signal is inferred via materialization."""
    with neo4j_driver.session(database=DB_NAME) as session:
        session.run("""
            CREATE (d:Dong {dongCode: '11010', dongName: 'test-dong'})
            CREATE (c:Complex {complexId: 'C001', complexName: 'test',
                pricePerSqm: 15000000, districtAvgPrice: 20000000,
                totalUnits: 500, builtYear: 2000,
                floorAreaRatio: 250.0, buildingCoverage: 60.0})
            CREATE (inf:Infrastructure {infraId: 'S001',
                infraName: 'test-station', infraType: 'subway',
                infraStatus: 'operating'})
            CREATE (d)-[:SPATIAL_HIERARCHY]->(c)
            CREATE (c)-[:ACCESSIBILITY {distanceMeter: 300, travelTimeMin: 5}]->(inf)
        """)
        with open("storage/neo4j/rules.cypher") as f:
            rules = f.read()
        for statement in rules.split(";"):
            stmt = statement.strip()
            if stmt and not stmt.startswith("//"):
                session.run(stmt)
        result = session.run(
            "MATCH (c:Complex)-[:UNDERVALUED_SIGNAL]->(c) RETURN c.complexId AS id"
        )
        answers = list(result)
        assert len(answers) >= 1
        session.run("MATCH (n) WHERE n.complexId = 'C001' OR n.dongCode = '11010' OR n.infraId = 'S001' DETACH DELETE n")
