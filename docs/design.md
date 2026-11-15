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
