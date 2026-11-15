from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx

from quantara.etl import origin

SCENARIOS = {
    "initial": "Полная загрузка",
    "replay": "Повтор ETL",
    "new": "Новые данные",
    "correction": "Исправление источника",
    "duplicate": "Дубликат транзакции",
    "partner": "Отсутствующий контрагент",
    "amount": "Некорректная сумма",
    "missing_fx": "Отсутствующий курс",
    "stale": "Устаревший источник",
    "partial": "Частичная оплата",
    "refund": "Возврат платежа",
    "unmatched": "Несопоставленный платёж",
    "bank": "Нарушение сверки",
    "mapping": "Изменение маппинга",
    "lineage": "Цепочка происхождения",
    "reproduce": "Повтор расчёта",
    "historical": "Историческое исправление",
    "compare": "Сравнение снимков",
    "concurrent": "Конкурентный ETL",
    "rollback": "Сбой внутри ETL",
    "erp_outage": "Недоступность ERP",
    "fx_outage": "Недоступность курсов",
    "budget": "План и факт",
    "scenario": "Гипотетический сценарий",
}
PERIOD = {"start": "2026-06-01", "end": "2026-06-30"}


def exercise(name, token, fault, keep_issue=False):
    trace = []
    checks = {}
    tag = uuid4().hex[:8]
    with httpx.Client(
        base_url="http://127.0.0.1:8000/api",
        timeout=25,
        trust_env=False,
        headers={"Authorization": "Bearer " + token},
    ) as client:

        def reply(method, path, body=None):
            r = client.request(method, path, json=body)
            result = r.json()
            trace.append(
                {
                    "method": method,
                    "path": path,
                    "input": body,
                    "status": r.status_code,
                    "request_id": r.headers.get("X-Request-ID"),
                    "response": result,
                }
            )
            return r.status_code, result

        def call(method, path, body=None, expected=200):
            status, result = reply(method, path, body)
            if status != expected:
                raise RuntimeError(f"{method} {path} returned {status}")
            return result

        def upstream(source, method, path, data):
            result = origin(source, method, path, json=data)
            trace.append(
                {
                    "source": source,
                    "method": method,
                    "path": path,
                    "input": data,
                    "response": result,
                }
            )
            return result

        def load(mode="incremental"):
            return call("POST", "/runs?mode=" + mode, expected=201)

        def report():
            return call("POST", "/reports", PERIOD, 201)

        def change(source, kind, key, payload, revision=None):
            return upstream(
                source,
                "POST",
                "/control/change",
                {
                    "kind": kind,
                    "external_id": key,
                    "payload": payload,
                    "revision": revision,
                },
            )

        def value(snap, code):
            return snap["result"]["metrics"][code]["value"]

        def raw(key):
            return call("GET", "/raw?q=" + key)

        def invoice(
            amount="1000.00", partner="AURORA", currency="RUB", date="2026-06-15"
        ):
            return {
                "partner": partner,
                "side": "REVENUE",
                "category": "Services",
                "amount": amount,
                "currency": currency,
                "date": date,
                "status": "POSTED",
                "adjustment": "0",
            }

        def bank(amount="-50.00", document=None, nature="PAYMENT"):
            return {
                "account": "RUB-01",
                "currency": "RUB",
                "amount": amount,
                "document": document,
                "nature": nature,
                "date": "2026-06-26",
            }

        before = report()
        key = "LAB-" + tag
        if name in {
            "initial",
            "replay",
            "reproduce",
            "lineage",
            "partial",
            "budget",
            "scenario",
        }:
            run = load("full" if name in {"initial", "replay"} else "incremental")
            current = report()
            if name in {"initial", "replay"}:
                checks["three_sources"] = set(run["summary"]["sources"]) == {
                    "erp",
                    "bank",
                    "fx",
                }
                checks["same_snapshot"] = before["checksum"] == current["checksum"]
                checks["published"] = run["status"] in {"SUCCESS", "PARTIAL"}
            elif name == "reproduce":
                checks["same_checksum"] = (
                    before["checksum"] == current["checksum"]
                    and before["id"] == current["id"]
                )
            elif name == "lineage":
                contributors = before["result"]["metrics"]["revenue"]["contributions"]
                first = next(x for x in contributors if x["fx_raw"] is not None)
                checks["raw_and_rate"] = all(
                    call("GET", f"/raw/{k}")["payload"]
                    for k in (first["raw"], first["fx_raw"])
                )
            elif name == "partial":
                checks["partial_payment"] = any(
                    x["code"] == "PARTIAL_PAYMENT"
                    for x in before["result"]["reconciliation"]
                )
            elif name == "budget":
                checks["consistent_variance"] = all(
                    Decimal(x["variance"])
                    == Decimal(x["actual"]) - Decimal(x["budget"])
                    for x in before["result"]["budget"]
                    if x["budget"] is not None
                )
            else:
                result = call(
                    "POST",
                    f"/reports/{before['id']}/scenarios",
                    {"revenue_percent": 10},
                    201,
                )
                baseline = value(before, "revenue")
                checks["hypothetical_adjustment"] = baseline is not None and abs(
                    Decimal(result["result"]["revenue"])
                    - Decimal(baseline) * Decimal("1.1")
                ) <= Decimal("0.005")
                checks["actual_unchanged"] = report()["checksum"] == before["checksum"]
        elif name in {
            "new",
            "correction",
            "historical",
            "compare",
            "duplicate",
            "rollback",
        }:
            first = change("erp", "invoice", key, invoice())
            if name == "rollback":
                failed = fault()
                trace.append({"action": "ETL fault after staging", "response": failed})
                checks["rolled_back"] = failed["status"] == "FAILED" and not raw(key)
            load()
            initial = report()
            checks["first_version"] = len(raw(key)) == 1
            if name == "duplicate":
                change("erp", "invoice", key, invoice(), first["revision"])
                run = load()
                checks["deduplicated"] = (
                    run["summary"]["sources"]["erp"]["duplicates"] >= 1
                    and report()["id"] == initial["id"]
                )
            elif name in {"correction", "historical", "compare"}:
                before = initial
                change("erp", "invoice", key, invoice("2500.00"))
                load()
                updated = report()
                comparison = call(
                    "GET", f"/reports/{initial['id']}/compare/{updated['id']}"
                )
                checks["delta_explained"] = any(
                    x["external_id"] == key for x in comparison["changed"]
                )
                checks["1500_increment"] = (
                    Decimal(value(updated, "revenue"))
                    - Decimal(value(initial, "revenue"))
                    == 1500
                )
                checks["old_snapshot_pinned"] = (
                    call("GET", f"/reports/{initial['id']}")["checksum"]
                    == initial["checksum"]
                )
        elif name in {"partner", "amount", "missing_fx"}:
            p = invoice(
                "invalid" if name == "amount" else "1000.00",
                "UNKNOWN" if name == "partner" else "AURORA",
                "USD" if name == "missing_fx" else "RUB",
            )
            change("erp", "invoice", key, p)
            load()
            reason = {
                "partner": "UNKNOWN_PARTNER",
                "amount": "INVALID_AMOUNT",
                "missing_fx": "FX_MISSING",
            }[name]
            checks["quarantined"] = any(
                x["external_id"] == key and x["reason"] == reason
                for x in call("GET", "/quarantine")
            )
            checks["incomplete_metric"] = value(report(), "revenue") is None
            if not keep_issue:
                change("erp", "invoice", key, invoice())
                load()
                checks["repaired"] = all(
                    x["external_id"] != key for x in call("GET", "/quarantine")
                )
        elif name in {"refund", "unmatched", "bank"}:
            p = (
                bank(document="INV-100", nature="REFUND")
                if name == "refund"
                else bank("1000.00")
            )
            change("bank", "payment", key, p)
            load()
            current = report()
            if name == "refund":
                checks["refund_increases_ar"] = (
                    Decimal(value(current, "receivables"))
                    - Decimal(value(before, "receivables"))
                    == 50
                )
            else:
                target = "BANK_MISMATCH" if name == "bank" else "UNMATCHED_PAYMENT"
                checks["difference_visible"] = any(
                    x["code"] == target for x in current["result"]["reconciliation"]
                )
        elif name in {"erp_outage", "fx_outage", "stale"}:
            source = "fx" if name == "fx_outage" else "erp"
            upstream(source, "PUT", "/control/mode", {"available": False})
            try:
                run = load()
                counts = run["summary"]["sources"][source]
                checks["checkpoint_preserved"] = (
                    counts["start_cursor"] == counts["end_cursor"]
                )
                checks["health_visible"] = any(
                    x["source"] == source and x["status"] == "UNAVAILABLE"
                    for x in call("GET", "/sources")
                )
                checks["partial_report"] = report()["quality"] == "PARTIAL"
            finally:
                upstream(source, "PUT", "/control/mode", {"available": True})
                load()
        elif name == "mapping":
            current = call("GET", "/mapping")[0]
            call(
                "POST",
                "/mapping",
                {"aliases": current["aliases"] | {"Services": "Consulting"}},
                201,
            )
            try:
                updated = report()
                checks["new_mapping"] = (
                    updated["manifest"]["mapping"] > before["manifest"]["mapping"]
                )
                checks["breakdown_changes"] = (
                    updated["result"]["breakdown"]["revenue"].get("Consulting")
                    is not None
                )
            finally:
                call("POST", "/mapping", {"aliases": current["aliases"]}, 201)
        elif name == "concurrent":
            with ThreadPoolExecutor(2) as pool:
                outcomes = list(
                    pool.map(lambda _: reply("POST", "/runs?mode=full"), range(2))
                )
            checks["serialized_or_rejected"] = all(
                s in {201, 409} for s, _ in outcomes
            ) and any(s == 201 for s, _ in outcomes)
            checks["same_checksum"] = report()["checksum"] == before["checksum"]
        final = report()
        return {
            "passed": bool(checks) and all(checks.values()),
            "checks": checks,
            "trace": trace,
            "before": {"id": before["id"], "checksum": before["checksum"]},
            "after": {"id": final["id"], "checksum": final["checksum"]},
            "completed": datetime.now(UTC).isoformat(),
        }
