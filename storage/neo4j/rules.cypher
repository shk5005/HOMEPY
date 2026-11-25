// ============================================================
// HOMEPY Neo4j Rules — Materialized Inference
// Converted from TypeDB rules.tql (17 rules)
//
// TypeDB uses automatic inference (infer=True at query time).
// Neo4j materializes inferred relationships explicitly via
// MERGE statements. Call these after data updates.
// ============================================================

// ---------- Rule 1: monetary-easing-signal ----------
MATCH (ir:InterestRate {rateDirection: 'falling'})
MATCH (lq:Liquidity)
WHERE ir.indicatorDate = lq.indicatorDate AND lq.m2GrowthRate > 5.0
MERGE (ir)-[:RECOVERY_SIGNAL]->(lq);

// ---------- Rule 2: rate-hike-pressure ----------
MATCH (ir:InterestRate {rateDirection: 'rising'})
WHERE ir.baseRate > 3.0
MATCH (lq:Liquidity)
WHERE lq.householdCreditGrowth > 6.0
MERGE (ir)-[:DOWNWARD_PRESSURE]->(lq);

// ---------- Rule 3: multi-owner-loan-block ----------
MATCH (zd:ZoneDesignation {zoneType: 'adjusted-target', isActive: true})
MATCH (dist:District)
MATCH (zd)-[:ZONE_APPLIED_TO]->(dist)
MATCH (lr:LoanRegulationRule {targetAreaType: 'adjusted-target', buyerType: 'multi-owner'})
WHERE lr.ltvLimit <= 0
MERGE (dist)-[:LOAN_BLOCKED_SIGNAL]->(lr);

// ---------- Rule 4: dsr-purchasing-power ----------
MATCH (lr:LoanRegulationRule)
WHERE lr.dsrLimit IS NOT NULL AND lr.dsrStressRate > 1.5
MATCH (ir:InterestRate)
WHERE ir.mortgageRateAvg > 3.5
MATCH (lr)-[:LOAN_CONSTRAINT]->(dist:District)
MERGE (dist)-[:PURCHASING_POWER_SQUEEZE]->(lr);

// ---------- Rule 5: cgt-lockin-effect ----------
MATCH (cgt:CgtRateRule {areaType: 'adjusted-target'})
WHERE cgt.ownerCount >= 2 AND cgt.surchargePct >= 20
MATCH (cgt)-[:CGT_APPLIES_TO]->(dist:District)
MATCH (zd:ZoneDesignation {zoneType: 'adjusted-target', isActive: true})
MATCH (zd)-[:ZONE_APPLIED_TO]->(dist)
MERGE (dist)-[:TAX_LOCKIN_SIGNAL]->(cgt);

// ---------- Rule 6: crt-selling-pressure ----------
MATCH (crt:CrtRateRule)
WHERE crt.ownerCount >= 2 AND crt.taxRatePct >= 1.2
MATCH (crt)-[:CRT_APPLIES_TO]->(c:Complex)
MERGE (c)-[:HOLDING_COST_PRESSURE]->(crt);

// ---------- Rule 7: acquisition-tax-relief ----------
MATCH (at1:AcquisitionTaxRate {buyerType: 'multi-owner', areaType: 'adjusted-target'})
MATCH (at2:AcquisitionTaxRate {buyerType: 'multi-owner', areaType: 'non-regulated'})
WHERE at1.taxRatePct > at2.taxRatePct
MATCH (zd:ZoneDesignation {zoneType: 'adjusted-target', isActive: false})
MATCH (zd)-[:ZONE_APPLIED_TO]->(dist:District)
MERGE (dist)-[:TAX_RELIEF_OPPORTUNITY {rateGap: at1.taxRatePct - at2.taxRatePct}]->(dist);

// ---------- Rule 8: supply-shortage-pressure ----------
MATCH (sd:SupplyData)
WHERE sd.completions < 3000
MATCH (md:MigrationData)
WHERE md.netMigration > 1000
MATCH (sd)-[:SUPPLY_IN_AREA]->(dist:District)
MATCH (md)-[:DEMAND_IN_AREA]->(dist)
MERGE (dist)-[:SUPPLY_DEMAND_GAP_UP {completions: sd.completions, netMigration: md.netMigration}]->(dist);

// ---------- Rule 9: oversupply-risk ----------
MATCH (sd:SupplyData)
WHERE sd.completions > 10000
MATCH (ui:UnsoldInventory)
WHERE ui.unsoldTotal > 500
MATCH (md:MigrationData)
WHERE md.netMigration < 0
MATCH (sd)-[:SUPPLY_IN_AREA]->(dist:District)
MATCH (ui)-[:SUPPLY_IN_AREA]->(dist)
MATCH (md)-[:DEMAND_IN_AREA]->(dist)
MERGE (dist)-[:SUPPLY_DEMAND_GAP_DOWN {completions: sd.completions, unsold: ui.unsoldTotal}]->(dist);

// ---------- Rule 10: undervalued-complex ----------
MATCH (c:Complex)
WHERE c.pricePerSqm < c.districtAvgPrice
MATCH (d:Dong)-[:SPATIAL_HIERARCHY]->(c)
MATCH (c)-[acc:ACCESSIBILITY]->(inf:Infrastructure {infraType: 'subway'})
WHERE acc.distanceMeter < 500
MERGE (c)-[:UNDERVALUED_SIGNAL]->(c);

// ---------- Rule 11: strong-buy-candidate ----------
MATCH (c:Complex)-[:UNDERVALUED_SIGNAL]->(c)
MATCH (dong:Dong)-[:SPATIAL_HIERARCHY]->(c)
MATCH (dist:District)-[:SPATIAL_HIERARCHY]->(dong)
MATCH (ir:InterestRate)-[:RECOVERY_SIGNAL]->(lq:Liquidity)
MATCH (dist)-[:TAX_RELIEF_OPPORTUNITY]->(dist)
MERGE (c)-[:STRONG_BUY_SIGNAL {macroSupport: ir.indicatorDate, taxSupport: dist.districtCode}]->(c);

// ---------- Rule 12: cycle-peak-warning ----------
MATCH (rc:RealEstateCycle {cyclePhase: 'peak'})
MATCH (ir:InterestRate {rateDirection: 'rising'})
MATCH (co:CycleObservation)
WHERE co.priceChangeYoy > 15.0
MATCH (co)-[:CYCLE_OBSERVED_AT]->(dist:District)
MERGE (dist)-[:CYCLE_PEAK_DANGER]->(rc);

// ---------- Rule 13: reverse-jeonse-risk ----------
MATCH (ms:MarketSentiment)
WHERE ms.jeonseRatio > 0.75
MATCH (ir:InterestRate {rateDirection: 'rising'})
MATCH (sd:SupplyData)
WHERE sd.completions > 5000
MATCH (ms)-[:SENTIMENT_OBSERVATION]->(dist:District)
MATCH (sd)-[:SUPPLY_IN_AREA]->(dist)
MERGE (dist)-[:REVERSE_JEONSE_DANGER {jeonseRatio: ms.jeonseRatio}]->(dist);

// ---------- Rule 14: gap-investment-risk ----------
MATCH (ms:MarketSentiment)
WHERE ms.jeonseRatio > 0.70 AND ms.buyerSentiment < 40
MATCH (ms)-[:SENTIMENT_OBSERVATION]->(dist:District)
MERGE (dist)-[:GAP_RISK_SIGNAL {jeonseRatio: ms.jeonseRatio, buyerSentiment: ms.buyerSentiment}]->(dist);

// ---------- Rule 15: development-spillover ----------
MATCH (dp:DevelopmentProject {projectType: 'GTX'})
MATCH (dp)-[di:DEVELOPMENT_INFLUENCE]->(c:Complex)
WHERE di.influenceRadiusKm <= 2.0
MERGE (c)-[:TRANSPORT_PREMIUM]->(dp);

// ---------- Rule 16: land-permit-reconstruction-play ----------
MATCH (dong:Dong {landTransactionPermit: true})
MATCH (dong)-[:SPATIAL_HIERARCHY]->(c:Complex)
WHERE c.reconstructionEligible = true AND c.builtYear < 1990
MERGE (c)-[:RECONSTRUCTION_DEEP_VALUE]->(dong);

// ---------- Rule 17 (early warning): excessive-leverage-warning ----------
MATCH (lq:Liquidity)
WHERE lq.householdCreditGrowth > 8.0
MATCH (ir:InterestRate {rateDirection: 'rising'})
WHERE ir.indicatorDate = lq.indicatorDate
MERGE (lq)-[:EXCESSIVE_LEVERAGE_WARNING]->(ir)
