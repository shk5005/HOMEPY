// ============================================================
// HOMEPY Neo4j Schema — Constraints & Indexes
// Converted from TypeDB schema.tql
// ============================================================
//
// TypeDB → Neo4j mapping conventions:
//   Entity types   → Node labels (PascalCase)
//   Attributes     → Node properties (camelCase)
//   Relations      → Relationships (UPPER_SNAKE_CASE)
//   Sub-entity     → Multiple labels (e.g., InterestRate:MacroIndicator)
//   Relation attrs → Relationship properties (camelCase)
//
// TypeDB abstract entities:
//   macro-indicator → MacroIndicator label (InterestRate, ExchangeRate, Liquidity, PriceIndex)
//   tax-regime      → TaxRegime label (AcquisitionTax, CapitalGainsTax, etc.)
//
// Relationship direction convention:
//   spatial-hierarchy  → (parent)-[:SPATIAL_HIERARCHY]->(child)
//   accessibility      → (location)-[:ACCESSIBILITY]->(facility)
//   macro-drives-cycle → (macroFactor)-[:MACRO_DRIVES_CYCLE]->(cycleState)
//   zone-applied-to    → (designation)-[:ZONE_APPLIED_TO]->(targetDistrict)
//   development-influence → (project)-[:DEVELOPMENT_INFLUENCE]->(beneficiary)
// ============================================================

// ---------- Domain 1: 공간 계층 ----------

CREATE CONSTRAINT IF NOT EXISTS FOR (n:Region) REQUIRE n.regionCode IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:District) REQUIRE n.districtCode IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:Dong) REQUIRE n.dongCode IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:Complex) REQUIRE n.complexId IS UNIQUE;

// ---------- Domain 2: 거시경제 ----------

CREATE INDEX IF NOT EXISTS FOR (n:InterestRate) ON (n.indicatorDate);

CREATE INDEX IF NOT EXISTS FOR (n:ExchangeRate) ON (n.indicatorDate);

CREATE INDEX IF NOT EXISTS FOR (n:Liquidity) ON (n.indicatorDate);

CREATE INDEX IF NOT EXISTS FOR (n:PriceIndex) ON (n.indicatorDate);

// ---------- Domain 3: 부동산 사이클 ----------

CREATE INDEX IF NOT EXISTS FOR (n:RealEstateCycle) ON (n.cycleDate);

CREATE INDEX IF NOT EXISTS FOR (n:CycleObservation) ON (n.observationDate);

// ---------- Domain 4: 금융/대출 ----------

CREATE CONSTRAINT IF NOT EXISTS FOR (n:LoanProduct) REQUIRE n.loanId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:LoanRegulation) REQUIRE n.regulationId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:LoanRegulationRule) REQUIRE n.ruleId IS UNIQUE;

// ---------- Domain 5: 세제 ----------

CREATE CONSTRAINT IF NOT EXISTS FOR (n:AcquisitionTax) REQUIRE n.taxId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:CapitalGainsTax) REQUIRE n.taxId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:ComprehensiveReTax) REQUIRE n.taxId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:InheritanceTax) REQUIRE n.taxId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:GiftTax) REQUIRE n.taxId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:PropertyTax) REQUIRE n.taxId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:AcquisitionTaxRate) REQUIRE n.rateId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:CgtRateRule) REQUIRE n.ruleId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:CrtRateRule) REQUIRE n.ruleId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:GiftTaxRate) REQUIRE n.rateId IS UNIQUE;

// ---------- Domain 6: 규제/정책 ----------

CREATE CONSTRAINT IF NOT EXISTS FOR (n:Policy) REQUIRE n.policyId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:ZoneDesignation) REQUIRE n.designationId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:PriceControl) REQUIRE n.controlId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:SubscriptionRegulation) REQUIRE n.subscriptionId IS UNIQUE;

// ---------- Domain 7: 수요/공급 ----------

CREATE INDEX IF NOT EXISTS FOR (n:PopulationData) ON (n.dataDate);

CREATE INDEX IF NOT EXISTS FOR (n:MigrationData) ON (n.dataDate);

CREATE INDEX IF NOT EXISTS FOR (n:IncomeData) ON (n.dataDate);

CREATE INDEX IF NOT EXISTS FOR (n:SupplyData) ON (n.dataDate);

CREATE INDEX IF NOT EXISTS FOR (n:UnsoldInventory) ON (n.dataDate);

CREATE INDEX IF NOT EXISTS FOR (n:ReconstructionSupply) ON (n.dataDate);

// ---------- 인프라 + 개발호재 + 시장심리 ----------

CREATE CONSTRAINT IF NOT EXISTS FOR (n:Infrastructure) REQUIRE n.infraId IS UNIQUE;

CREATE CONSTRAINT IF NOT EXISTS FOR (n:DevelopmentProject) REQUIRE n.projectId IS UNIQUE;

CREATE INDEX IF NOT EXISTS FOR (n:MarketSentiment) ON (n.sentimentDate);

// ---------- Frequently queried property indexes ----------

CREATE INDEX IF NOT EXISTS FOR (n:District) ON (n.districtName);

CREATE INDEX IF NOT EXISTS FOR (n:District) ON (n.regulationZoneType);

CREATE INDEX IF NOT EXISTS FOR (n:Complex) ON (n.complexName);

CREATE INDEX IF NOT EXISTS FOR (n:Complex) ON (n.pricePerSqm);

CREATE INDEX IF NOT EXISTS FOR (n:Complex) ON (n.builtYear);

CREATE INDEX IF NOT EXISTS FOR (n:Infrastructure) ON (n.infraType);

CREATE INDEX IF NOT EXISTS FOR (n:ZoneDesignation) ON (n.zoneType);

CREATE INDEX IF NOT EXISTS FOR (n:ZoneDesignation) ON (n.isActive);

CREATE INDEX IF NOT EXISTS FOR (n:InterestRate) ON (n.rateDirection);

CREATE INDEX IF NOT EXISTS FOR (n:RealEstateCycle) ON (n.cyclePhase);

CREATE INDEX IF NOT EXISTS FOR (n:LoanRegulationRule) ON (n.targetAreaType);

CREATE INDEX IF NOT EXISTS FOR (n:Policy) ON (n.policyCategory);

CREATE INDEX IF NOT EXISTS FOR (n:DevelopmentProject) ON (n.projectType);

// ---------- Relationship indexes ----------

CREATE INDEX IF NOT EXISTS FOR ()-[r:SPATIAL_HIERARCHY]-() ON (r.level);

CREATE INDEX IF NOT EXISTS FOR ()-[r:ACCESSIBILITY]-() ON (r.distanceMeter);

CREATE INDEX IF NOT EXISTS FOR ()-[r:DEVELOPMENT_INFLUENCE]-() ON (r.influenceRadiusKm)
