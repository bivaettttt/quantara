# Quantara status / Состояние проекта

The release implements independent source feeds, PostgreSQL ingestion and immutable raw, staging, quality, reports and their browser evidence. Quantara Lab uses separate PostgreSQL and SQLite volumes.

## Known limits

- The model covers one synthetic organization, exact-date FX into RUB and a simplified invoice settlement convention. Statutory accounting and realized exchange gains are out of scope.
- Reconciliation uses explicit document references. Competing or missing references appear as diagnostics. A manual settlement approval workflow is pending.
- Report inputs are pinned and results remain immutable. Regeneration returns the same snapshot when current inputs and rules match. A separate endpoint to replay arbitrary historical manifests is pending.
- The mapping editor publishes category aliases. Quality rules are code-versioned. A configurable quality-rule editor and high-volume batch orchestration are pending.
- Staging records can be updated by recovery at the same mapping and raw version. Raw and report versions are durable. There is no schedule for background ETL.
- Scenario analysis applies changes in three percentage assumptions. No forecast, treasury or tax model is included.
- Some OpenAPI responses use generic object schemas. Rate and source limits are intended for small synthetic data.

## Verification record

Local verification passed ten unit cases, the PostgreSQL HTTP suite, 24 Lab scenario entries and two Chromium tests. The service contracts match the application and source schema exports. Both deployment variants were exercised. The [demonstration](demo.md) contains browser captures and two real flows. [Reproduction commands](verification.md) · [GitHub Actions](https://github.com/bivaettttt/quantara/actions)
