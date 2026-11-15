# Quantara · Финансовая семантика и архитектура / Financial semantics and architecture

Quantara helps a financial analyst explain differences between invoices and settlements, and a data engineer trace errors through independent source deliveries. The system uses synthetic observations in a single synthetic organization.

| ID | Actor and outcome | Acceptance |
| --- | --- | --- |
| FR-01 | Engineer ingests source records | Each source has its own monotonic delivery cursor. A staged revision is reconstructible from an immutable delivery |
| FR-02 | Steward investigates quality | Rejections remain visible with a diagnostic. Missing references and rates can be repaired by source correction or reprocessing |
| FR-03 | Financial analyst compares accrual and cash | Decimal values and dated FX produce distinct revenue, cash and open-item metrics |
| FR-04 | Analyst explains a reported value | Snapshot resolves to record contributions, transformation versions, raw versions and FX inputs |
| FR-05 | Analyst reproduces and compares reports | Historical values remain unchanged. Matching inputs give an identical digest. Comparison identifies changed source records |
| FR-06 | Steward validates reconciliation | A bank balance and linked invoices expose unknown references, partial payments and monetary differences |
| FR-07 | Financial analyst tests assumptions | Budget and scenario outputs retain actuals separately |
| FR-08 | Administrator exercises the pipeline | The isolated lab runs real HTTP and PostgreSQL workflows |

## Rules and assumptions

- BR-01. Dates are business calendar dates. Invoices are recognized on the document date. Payments are recognized on the bank value date. The period includes both endpoints.
- BR-02. Posted revenue and expense invoice versions replace prior versions for new reports. Positive values add to their category. Signed adjustments reduce or increase the current amount. A draft or void is an explicit zero recognition state for that document.
- BR-03. Positive bank amounts are inflows. Negative amounts are outflows, including refunds and fees. Revenue and expense metrics use only ERP facts. Operating result equals revenue less expense and is an educational operating measure.
- BR-04. Convert each USD/EUR fact at the exact business date using the date's active rate. RUB is the base currency. Quantize each converted fact to two decimals using ROUND_HALF_UP. Report values serialize as strings.
- BR-05. Open items subtract linked net settled amount from originally recognized document value using transaction-date conversion on both sides. The demo uses documented currency settlement conventions; negative open amounts are shown as reconciliation overpayments with a zero open balance.
- BR-06. Payments link by explicit document ID. Missing or wrong-direction links remain unmatched. Refunds reverse settlement. Balance statement closes against opening amount plus movements in the same account currency.
- BR-07. Category/month budgets use the accrual expense basis and RUB. Variance is actual minus budget. Division by an absent or zero budget returns null.
- BR-08. A quarantine retains the original payload. Affected reports expose partial metrics for material exclusions; no implicit FX fallback or zero substitution is used.
- BR-09. Scenario changes are calculated against a stored report and never write actual ledger facts.

## ADRs

1. Three HTTP processes use separate SQLite volumes for source feeds. PostgreSQL is the warehouse. Source updates append revisions under a single monotonic sequence per source.
2. A database advisory lock serializes ETL publication. Pages are validated before a single publication transaction writes raw facts, staging results, warehouse projections and checkpoints. Failed commits preserve the cursor for retry.
3. Record-level lineage includes source, external key, revision, delivery batch, mapping version, warehouse record and dated FX version. Reports store deterministic input manifests, evidence and result hashes.
4. Reproducibility uses immutable report payloads. Source changes trigger a new snapshot when requested. Interactive comparisons use the original manifests.
5. PostgreSQL and a modular FastAPI backend support a local educational workflow without a broker. Server-side role checks gate transformation, stewardship and administration.

## Scope

Synthetic ERP, bank statements and FX. No bank connection, statutory financial statement, tax treatment, accounting certification, official FX rates or externally published financial guidance.

## Roles, use cases and nonfunctional requirements

| Role | Main operation | Scope |
| --- | --- | --- |
| FINANCIAL_ANALYST | UC-01 Build and compare reports | Read immutable report, access its raw evidence, run scenarios |
| DATA_ANALYST | UC-02 Investigate input quality | Inspect raw history, staging, mappings and read financial reports |
| DATA_ENGINEER | UC-03 Operate ETL | Incremental and full import, CSV, reprocessing and diagnostic queries |
| DATA_STEWARD | UC-04 Repair a data classification | Publish a new mapping, reprocess raw and inspect issues |
| ADMIN | UC-05 Operate demo | Create users, audit commands and run Lab where enabled |

NFR-01 requires atomic checkpoint and warehouse publication. NFR-02 requires exact arithmetic and stable digests for equal inputs. NFR-03 requires scoped APIs, bounded CSV and paging, fixed source addresses, and no secrets in audit. NFR-04 requires resetting Lab without removing demo volumes.

## Mapping and quality decisions

| Origin | Field or identity | Target | Validation |
| --- | --- | --- | --- |
| All streams | sequence, kind, external ID, revision | raw delivery and version identity | Monotonic sequence, typed envelope |
| ERP | date, amount, adjustment, currency | invoice business date and numeric amount | ISO date, decimal string, supported currency, nonnegative adjusted amount |
| ERP | buyer or supplier, category | normalized attributes and category | Existing partner. Apply versioned category aliases |
| ERP | budget category, date, amount | monthly accrual plan | RUB, month start, nonnegative |
| Bank | account, date, amount, nature | payment fact and account reference | Existing account, matching currency, signed decimal and valid nature |
| Bank | account, start, date, opening, closing | statement and reconciliation inputs | Existing account, ordered interval, exact values |
| FX | business date, currency, rate | dated conversion dimension | Positive rate, non-RUB currency, unique day and currency |

A malformed feed leaves the source cursor untouched. Duplicate deliveries are retained when the delivery sequence is new, with a duplicate disposition. Same-revision differences are visible in quality history. The latest erroneous canonical version is quarantined, so an older valid record cannot appear silently as current. A repaired dependency can be reprocessed without editing raw data. Missing month budgets, zero baselines and incomplete financial totals are displayed explicitly. The known subtotal remains visible. Cash balance is unavailable when the statement does not reconcile. Its known subtotal and evidence remain available.

Bank matching uses an explicit document reference and validates the direction of payment or refund. A payment whose ID and normalized content match across CSV and bank delivery contributes once. Conflicts are investigated through quality history. Reconciliation exposes partial, open, settled and overpaid documents and bank differences. It does not infer a missing reference.

## Errors and evidence

401 identifies a missing or invalid session. 403 marks a role denial. 404 marks an unavailable entity. 409 reports a competing ETL publication or a conflicting command. 422 marks an invalid request or incompatible report period. Responses and audit retain a request identifier. Warehouse publication handles source outages as partial runs and persistence failures as rolled-back failed runs.

[Context](diagrams/context.mmd) · [Containers](diagrams/containers.mmd) · [Warehouse ERD](diagrams/warehouse.mmd) · [ETL](diagrams/etl.mmd) · [Lineage](diagrams/lineage.mmd) · [Quality states](diagrams/quality.mmd) · [Verification](verification.md)

The warehouse uses a consolidated facts table with a grain of source, entity and external key, plus typed views for document, payment and budget facts and counterparty and FX dimensions. It is a compact dimensional projection. Account, category, calendar and settlement context remain in columns or normalized attributes. Report queries use an inclusive business date and explicit accumulation horizons. A snapshot manifests both its inputs and its material exclusions. It computes known subtotals even when a metric is unavailable, applies a checksum to canonical serialization, and permits version comparison only for matching periods.

[Report sequence](diagrams/report.mmd) · [Source correction sequence](diagrams/correction.mmd) · [ETL run states](diagrams/run.mmd)
