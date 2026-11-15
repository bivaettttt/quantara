# Verification / Проверки

| Need | Rule and implementation | Evidence |
| --- | --- | --- |
| FR-01 | [ETL](../backend/quantara/etl.py) and immutable [raw schema](../backend/migrations/versions/001_initial.py) | TC-01. Full, incremental, duplicate, CSV, correction, cursor rollback and concurrent ETL |
| FR-02 | [Validation and mapping](../backend/quantara/domain.py) | TC-02. Missing counterparties, invalid amount, FX absence and dependency repair |
| FR-03 | BR-01–BR-05 in [reporting](../backend/quantara/reports.py) | TC-03. Exact accrual, cash, receivables, payables, FX and rounding |
| FR-04 | [Manifest and contributions](../backend/quantara/reports.py) | TC-04. Report revenue links to immutable invoice, mapping, run and FX records |
| FR-05 | BR-08, [snapshot code and constraints](../backend/quantara/reports.py) | TC-05. Stable checksum, PostgreSQL rejection of deletes, explainable historical correction |
| FR-06 | BR-05–BR-06 in [reporting](../backend/quantara/reports.py) | TC-06. Partial settlement, refund, unknown link and bank difference |
| FR-07 | BR-07 and BR-09 in [reporting](../backend/quantara/reports.py) | TC-07. Budget variance, hypothetical result, unchanged actuals |
| FR-08 | [Permissions](../backend/quantara/auth.py), [lab](../backend/quantara/lab.py) | TC-08. Real HTTP in separate Compose volume, role denial and source outages |

```sh
python -m pip install -r requirements.txt pytest ruff
ruff check backend sources scripts tests
ruff format --check backend sources scripts tests
pytest -q
PYTHONPATH=backend python scripts/contracts.py
scripts/lab up
docker compose -p quantara-lab exec -T api python -u - < scripts/verify.py
cd frontend
npm ci
npx playwright install chromium
npm run e2e
```

Use a clean lab and run sequentially. Tests intentionally append corrections, document versions, scenario results and evidence. The browser may retain a missing FX issue for inspection. [Unit suite](../tests/test_finance.py) · [Integration suite](../scripts/verify.py) · [Playwright suite](../frontend/e2e/workspace.spec.ts)
