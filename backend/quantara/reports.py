from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import HTTPException

from quantara.db import audit, digest, dumps, row, rows
from quantara.domain import BASE, MAPPING_VERSION, METHOD, money

ZERO = Decimal("0.00")


def calculate(facts, excluded, start, end, unavailable=()):
    names = (
        "revenue",
        "expenses",
        "operating_result",
        "cash_in",
        "cash_out",
        "net_cash",
        "cash_balance",
        "receivables",
        "payables",
        "budget_variance",
    )
    metrics = dict.fromkeys(names, ZERO)
    lineage = {name: [] for name in names}
    breakdown = {
        "revenue": defaultdict(lambda: ZERO),
        "expenses": defaultdict(lambda: ZERO),
    }
    checks = []
    rate = {
        (r["business_date"], r["currency"]): r for r in facts if r["entity"] == "rate"
    }
    docs = {
        r["external_id"]: r
        for r in facts
        if r["entity"] == "invoice" and r["business_date"] <= end
    }
    accounts = {r["external_id"]: r for r in facts if r["entity"] == "account"}
    payments = [
        r for r in facts if r["entity"] == "payment" and r["business_date"] <= end
    ]
    omitted = {metric: [] for metric in names}
    for issue in excluded:
        day = issue.get("date")
        entity = issue["entity"]
        fields = {
            "invoice": [
                "revenue",
                "expenses",
                "operating_result",
                "receivables",
                "payables",
                "budget_variance",
            ],
            "payment": [
                "cash_in",
                "cash_out",
                "net_cash",
                "cash_balance",
                "receivables",
                "payables",
            ],
            "budget": ["budget_variance"],
            "statement": ["cash_balance"],
        }.get(entity, [])
        if day and day > end:
            continue
        for name in fields:
            if (
                day
                and day < start
                and name
                in (
                    "revenue",
                    "expenses",
                    "operating_result",
                    "cash_in",
                    "cash_out",
                    "net_cash",
                    "budget_variance",
                )
            ):
                continue
            omitted[name].append(issue["raw"])

    def converted(value, item):
        if item["currency"] == BASE:
            return money(value), None
        fx = rate[(item["business_date"], item["currency"])]
        return money(value * Decimal(fx["attributes"]["rate"])), fx["raw"]

    def contribute(metric, item, value, fx=None):
        metrics[metric] += value
        lineage[metric].append(
            {
                "raw": item["raw"],
                "source": item["source"],
                "external_id": item["external_id"],
                "revision": item["revision"],
                "mapping": item["mapping"],
                "run": str(item["run"]),
                "fx_raw": fx,
                "amount": str(value),
            }
        )

    settled = defaultdict(list)
    for p in payments:
        attrs = p["attributes"]
        amount = p["amount"]
        rub, fx = converted(amount, p)
        if start <= p["business_date"]:
            contribute("cash_in" if rub > 0 else "cash_out", p, abs(rub), fx)
        key = attrs["document"]
        doc = docs.get(key)
        if attrs["nature"] == "FEE":
            continue
        side = doc["attributes"]["side"] if doc else None
        standard = side == "REVENUE" if side else None
        positive = amount > 0
        matches = (
            doc
            and doc["attributes"]["status"] == "POSTED"
            and (
                positive == standard
                if attrs["nature"] == "PAYMENT"
                else positive != standard
            )
        )
        if not matches:
            checks.append(
                {
                    "code": "UNMATCHED_PAYMENT",
                    "object": p["external_id"],
                    "actual": str(rub),
                    "difference": None,
                    "raw": [p["raw"]],
                }
            )
        else:
            settled[key].append(
                (p, abs(rub) if attrs["nature"] == "PAYMENT" else -abs(rub), fx)
            )

    for key, item in docs.items():
        attr = item["attributes"]
        recognition = (
            item["amount"] + Decimal(attr["adjustment"])
            if attr["status"] == "POSTED"
            else ZERO
        )
        rub, fx = converted(recognition, item)
        family = "revenue" if attr["side"] == "REVENUE" else "expenses"
        if start <= item["business_date"]:
            contribute(family, item, rub, fx)
            breakdown[family][item["category"]] += rub
        if attr["status"] != "POSTED":
            continue
        total = sum((x[1] for x in settled[key]), ZERO)
        open_amount = rub - total
        metric = "receivables" if family == "revenue" else "payables"
        contribute(metric, item, rub, fx)
        for payment, amount, fx_input in settled[key]:
            contribute(metric, payment, -amount, fx_input)
        if open_amount < 0:
            contribute(metric, item, -open_amount)
        code = (
            "OVERPAYMENT"
            if open_amount < 0
            else "SETTLED"
            if not open_amount
            else "PARTIAL_PAYMENT"
            if total
            else "OPEN_DOCUMENT"
        )
        checks.append(
            {
                "code": code,
                "object": key,
                "expected": str(rub),
                "actual": str(total),
                "difference": str(open_amount),
                "raw": [item["raw"], *[p["raw"] for p, *_ in settled[key]]],
            }
        )

    for account in accounts:
        statement = next(
            (
                s
                for s in facts
                if s["entity"] == "statement"
                and s["business_date"] == end
                and s["attributes"]["account"] == account
                and s["attributes"]["start"] <= start.isoformat()
            ),
            None,
        )
        if statement is None:
            omitted["cash_balance"].append(accounts[account]["raw"])
            checks.append(
                {
                    "code": "STATEMENT_MISSING",
                    "object": account,
                    "currency": accounts[account]["currency"],
                    "raw": [accounts[account]["raw"]],
                }
            )
            continue
        s = statement["attributes"]
        covered = [
            p
            for p in payments
            if p["attributes"]["account"] == account
            and p["business_date"] >= date.fromisoformat(s["start"])
        ]
        actual = Decimal(s["opening"]) + sum((p["amount"] for p in covered), ZERO)
        expected = Decimal(s["closing"])
        balance, fx = converted(actual, statement)
        contribute("cash_balance", statement, balance, fx)
        difference = actual - expected
        lineage["cash_balance"][-1]["related_raw"] = [p["raw"] for p in covered]
        if difference:
            omitted["cash_balance"].append(statement["raw"])
        checks.append(
            {
                "code": "BANK_MISMATCH" if difference else "BANK_MATCH",
                "object": account,
                "currency": statement["currency"],
                "expected": str(expected),
                "actual": str(actual),
                "difference": str(difference),
                "raw": [statement["raw"], *[p["raw"] for p in covered]],
            }
        )

    budget_evidence = []
    monthly_actual = defaultdict(lambda: ZERO)
    monthly_budget = defaultdict(lambda: ZERO)
    for f in facts:
        day = f["business_date"]
        if (
            day is None
            or day.strftime("%Y-%m") < start.strftime("%Y-%m")
            or day.strftime("%Y-%m") > end.strftime("%Y-%m")
        ):
            continue
        key = (day.strftime("%Y-%m"), f["category"])
        if f["entity"] == "budget":
            monthly_budget[key] += f["amount"]
            budget_evidence.append({"raw": f["raw"], "amount": str(-f["amount"])})
        if (
            f["entity"] == "invoice"
            and f["attributes"]["side"] == "EXPENSE"
            and f["attributes"]["status"] == "POSTED"
            and start <= day <= end
        ):
            amount, _ = converted(
                f["amount"] + Decimal(f["attributes"]["adjustment"]), f
            )
            monthly_actual[key] += amount
    budget = []
    for month, category in sorted(set(monthly_actual) | set(monthly_budget)):
        actual = monthly_actual[month, category]
        plan = monthly_budget.get((month, category))
        delta = actual - plan if plan is not None else None
        budget.append(
            {
                "month": month,
                "category": category,
                "actual": str(actual),
                "budget": str(plan) if plan is not None else None,
                "variance": str(delta) if delta is not None else None,
                "performance": str(money(actual / plan * 100)) if plan else None,
            }
        )
    missing_plan = not budget or any(r["variance"] is None for r in budget)
    complete_months = start.day == 1 and (
        end.toordinal() == date.max.toordinal()
        or date.fromordinal(end.toordinal() + 1).day == 1
    )
    metrics["budget_variance"] = sum(
        (Decimal(r["variance"]) for r in budget if r["variance"] is not None), ZERO
    )
    lineage["budget_variance"] = [*lineage["expenses"], *budget_evidence]
    metrics["operating_result"] = metrics["revenue"] - metrics["expenses"]
    lineage["operating_result"] = [
        *lineage["revenue"],
        *[p | {"amount": str(-Decimal(p["amount"]))} for p in lineage["expenses"]],
    ]
    metrics["net_cash"] = metrics["cash_in"] - metrics["cash_out"]
    lineage["net_cash"] = [
        *lineage["cash_in"],
        *[p | {"amount": str(-Decimal(p["amount"]))} for p in lineage["cash_out"]],
    ]
    source_block = {
        "erp": {
            "revenue",
            "expenses",
            "operating_result",
            "receivables",
            "payables",
            "budget_variance",
        },
        "bank": {
            "cash_in",
            "cash_out",
            "net_cash",
            "cash_balance",
            "receivables",
            "payables",
        },
        "fx": set(names),
    }
    blocked = set().union(*(source_block.get(s, set()) for s in unavailable))
    report_metrics = {
        k: {
            "value": None
            if omitted[k]
            or k in blocked
            or (k == "budget_variance" and (missing_plan or not complete_months))
            or (k == "cash_balance" and not accounts)
            else str(money(v)),
            "known": str(money(v)),
            "excluded": omitted[k],
            "contributions": lineage[k],
        }
        for k, v in metrics.items()
    }
    return {
        "metrics": report_metrics,
        "breakdown": breakdown,
        "reconciliation": checks,
        "budget": budget,
    }


def inputs(conn, period):
    facts = rows(
        conn,
        """SELECT f.* FROM facts f WHERE f.business_date IS NULL OR f.business_date<=:end
       ORDER BY f.source,f.entity,f.external_id""",
        end=period.end,
    )
    mapping = row(conn, "SELECT version FROM mapping ORDER BY version DESC LIMIT 1")[
        "version"
    ]
    excluded = rows(
        conn,
        """SELECT r.id AS raw,r.source,r.entity,r.external_id,r.revision,r.payload->>'date' AS date,s.reason
       FROM (SELECT DISTINCT ON(source,entity,external_id) * FROM raw WHERE disposition='CANONICAL'
             ORDER BY source,entity,external_id,revision DESC,id) r
       JOIN stage s ON s.raw=r.id AND s.mapping=:mapping WHERE s.status='QUARANTINED'
       ORDER BY r.source,r.entity,r.external_id""",
        mapping=mapping,
    )
    for issue in excluded:
        try:
            issue["date"] = date.fromisoformat(issue["date"]) if issue["date"] else None
        except ValueError:
            issue["date"] = None
    excluded = [e for e in excluded if not e["date"] or e["date"] <= period.end]
    unhealthy = [
        c["source"]
        for c in rows(
            conn,
            """SELECT source FROM checkpoints WHERE source<>'csv' AND
      (last_error IS NOT NULL OR last_success IS NULL OR last_success<now()-interval '24 hours') ORDER BY source""",
        )
    ]
    return facts, excluded, unhealthy, mapping


def build(conn, period, actor, request):
    facts, excluded, unhealthy, mapping = inputs(conn, period)
    manifest = {
        "period": period.model_dump(mode="json"),
        "method": METHOD,
        "transform": MAPPING_VERSION,
        "mapping": mapping,
        "quality_rules": "quality/1",
        "unavailable": unhealthy,
        "excluded": excluded,
        "records": [
            {
                k: f[k]
                for k in (
                    "source",
                    "entity",
                    "external_id",
                    "raw",
                    "revision",
                    "mapping",
                    "run",
                )
            }
            for f in facts
        ],
    }
    result = calculate(facts, excluded, period.start, period.end, unhealthy)
    checksum = digest({"manifest": manifest, "result": result})
    quality = (
        "PARTIAL"
        if excluded
        or unhealthy
        or any(m["value"] is None for m in result["metrics"].values())
        else "COMPLETE"
    )
    item = row(
        conn,
        """INSERT INTO reports(start_date,end_date,actor,method,manifest,result,checksum,quality)
      VALUES (:start,:end,:actor,:method,CAST(:manifest AS jsonb),CAST(:result AS jsonb),:checksum,:quality)
      ON CONFLICT(checksum) DO NOTHING RETURNING *""",
        start=period.start,
        end=period.end,
        actor=actor,
        method=METHOD,
        manifest=dumps(manifest),
        result=dumps(result),
        checksum=checksum,
        quality=quality,
    )
    if item:
        audit(conn, actor, request, "REPORT_CREATED", item["id"], checksum=checksum)
    return item or row(conn, "SELECT * FROM reports WHERE checksum=:c", c=checksum)


def get(conn, id):
    found = row(conn, "SELECT * FROM reports WHERE id=:id", id=id)
    if not found:
        raise HTTPException(404, "REPORT_NOT_FOUND")
    return found


def compare(left, right):
    if (left["start_date"], left["end_date"]) != (
        right["start_date"],
        right["end_date"],
    ):
        raise HTTPException(422, "PERIOD_MISMATCH")

    def key(record):
        return record["source"], record["entity"], record["external_id"]

    previous = {key(r): r for r in left["manifest"]["records"]}
    current = {key(r): r for r in right["manifest"]["records"]}
    changed = [
        {
            "source": k[0],
            "entity": k[1],
            "external_id": k[2],
            "before": previous.get(k),
            "after": current.get(k),
        }
        for k in sorted(previous.keys() | current.keys())
        if previous.get(k) != current.get(k)
    ]
    metrics = []
    for code, lvalue in left["result"]["metrics"].items():
        a, b = lvalue["value"], right["result"]["metrics"][code]["value"]
        delta = Decimal(b) - Decimal(a) if a is not None and b is not None else None
        metrics.append(
            {
                "code": code,
                "before": a,
                "after": b,
                "delta": str(delta) if delta is not None else None,
                "percent": str(money(delta / abs(Decimal(a)) * 100))
                if delta is not None and Decimal(a)
                else None,
            }
        )
    return {
        "metrics": metrics,
        "changed": changed,
        "previous_quality": left["quality"],
        "quality": right["quality"],
        "quality_changes": {
            "before": left["manifest"]["excluded"],
            "after": right["manifest"]["excluded"],
            "unavailable_before": left["manifest"]["unavailable"],
            "unavailable_after": right["manifest"]["unavailable"],
        },
    }


def scenario(conn, report, payload, actor, request):
    assumptions = payload.model_dump()
    results = {}
    for k, factor in (
        ("revenue", "revenue_percent"),
        ("expenses", "expense_percent"),
        ("cash_in", "cash_in_percent"),
    ):
        value = report["result"]["metrics"][k]["value"]
        results[k] = (
            None
            if value is None
            else str(money(Decimal(value) * (100 + assumptions[factor]) / 100))
        )
    results["operating_result"] = (
        str(money(Decimal(results["revenue"]) - Decimal(results["expenses"])))
        if all(results[k] is not None for k in ("revenue", "expenses"))
        else None
    )
    item = row(
        conn,
        """INSERT INTO scenarios(report,actor,assumptions,result)
       VALUES (:r,:a,CAST(:p AS jsonb),CAST(:o AS jsonb)) RETURNING *""",
        r=report["id"],
        a=actor,
        p=dumps(assumptions),
        o=dumps(results),
    )
    audit(conn, actor, request, "SCENARIO_CREATED", item["id"], report=report["id"])
    return item
