import csv
import logging
from datetime import UTC, datetime, timedelta
from io import StringIO
from uuid import uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from quantara.contracts import Delivery, Page
from quantara.db import audit, digest, dumps, engine, row, rows, sql
from quantara.domain import BASE, Invalid, normalize

LOG = logging.getLogger(__name__)
SOURCES = ("erp", "bank", "fx")
ENTITIES = {
    "erp": {"partner", "invoice", "budget"},
    "bank": {"account", "payment", "statement"},
    "fx": {"rate"},
    "csv": {"payment"},
}
GUARD = 76432011


def guard(conn):
    if not sql(conn, "SELECT pg_try_advisory_xact_lock(:key)", key=GUARD).scalar_one():
        raise HTTPException(409, "ETL_BUSY")


def origin(source, method, path, **kwargs):
    if source not in SOURCES:
        raise ValueError("Unregistered source")
    with httpx.Client(
        base_url=f"http://{source}:8100",
        timeout=3,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()


def fetch(source, cursor):
    result = []
    for _ in range(20):
        page = Page.model_validate(
            origin(source, "GET", "/changes", params={"after": cursor, "limit": 50})
        )
        if page.source != source:
            raise ValueError("SOURCE_MISMATCH")
        for record in page.records:
            if record.sequence != cursor + 1:
                raise ValueError("DELIVERY_GAP")
            result.append(record)
            cursor = record.sequence
        if len(page.records) < 50:
            return result
    raise ValueError("PAGINATION_LIMIT")


def problem(conn, run, source, raw, dimension, code, **detail):
    sql(
        conn,
        """INSERT INTO quality(run,raw,source,dimension,code,detail)
        VALUES (:r,:id,:s,:d,:c,CAST(:p AS jsonb))""",
        r=run,
        id=raw,
        s=source,
        d=dimension,
        c=code,
        p=dumps(detail),
    )


def summary_row(conn, id):
    return row(conn, "SELECT * FROM runs WHERE id=:id", id=id)


def create_run(conn, id, actor, request, start, mode, status="RUNNING"):
    sql(
        conn,
        """INSERT INTO runs(id,request,actor,started,mode,status,summary)
           VALUES (:id,:r,:a,:t,:m,:s,'{}')""",
        id=id,
        r=request,
        a=actor,
        t=start,
        m=mode,
        s=status,
    )


def store(conn, id, source, deliveries, counts):
    for event in deliveries:
        counts["received"] += 1
        known = row(
            conn,
            "SELECT id FROM raw WHERE source=:s AND sequence=:n",
            s=source,
            n=event.sequence,
        )
        if known:
            counts["duplicates"] += 1
            continue
        name, key, version = event.kind, event.external_id, event.revision
        hash = digest(event.payload)
        canonical = row(
            conn,
            """SELECT hash FROM raw WHERE source=:s AND entity=:e AND external_id=:k
                   AND revision=:v AND disposition='CANONICAL'""",
            s=source,
            e=name,
            k=key,
            v=version,
        )
        disposition = (
            ("DUPLICATE" if canonical["hash"] == hash else "REVISION_CONFLICT")
            if canonical
            else "CANONICAL"
        )
        if name not in ENTITIES[source]:
            disposition = "WRONG_ENTITY"
        item = row(
            conn,
            """INSERT INTO raw(source,sequence,entity,external_id,revision,event_time,hash,payload,run,disposition)
              VALUES (:s,:n,:e,:k,:v,:t,:h,CAST(:p AS jsonb),:r,:d) RETURNING id""",
            s=source,
            n=event.sequence,
            e=name,
            k=key,
            v=version,
            t=event.event_time,
            h=hash,
            p=dumps(event.payload),
            r=id,
            d=disposition,
        )
        if disposition == "DUPLICATE":
            counts["duplicates"] += 1
        elif disposition != "CANONICAL":
            counts["rejected"] += 1
            problem(
                conn,
                id,
                source,
                item["id"],
                "UNIQUENESS" if canonical else "VALIDITY",
                disposition,
            )
        else:
            counts["accepted"] += 1


def rebuild(conn, id):
    mapping = row(conn, "SELECT * FROM mapping ORDER BY version DESC LIMIT 1")
    latest = rows(
        conn,
        """SELECT DISTINCT ON(source,entity,external_id) * FROM raw WHERE disposition='CANONICAL'
        ORDER BY source,entity,external_id,revision DESC,id""",
    )
    normalized = {}
    errors = {}
    for r in latest:
        try:
            normalized[r["id"]] = normalize(
                r["entity"], r["payload"], mapping["aliases"]
            )
        except Invalid as exc:
            errors[r["id"]] = exc
    dimensions = {k: {} for k in ("partner", "account", "rate")}
    duplicate_payments = {
        r["external_id"]
        for r in latest
        if r["source"] == "bank" and r["entity"] == "payment"
    }
    for r in latest:
        entry = normalized.get(r["id"])
        if entry is not None and r["entity"] in dimensions:
            key = (
                (entry["date"], entry["currency"])
                if r["entity"] == "rate"
                else r["external_id"]
            )
            dimensions[r["entity"]][key] = entry
    for r in latest:
        key = r["id"]
        entry = normalized.get(key)
        kind = r["entity"]
        if entry is not None:
            if kind == "invoice" and entry["partner"] not in dimensions["partner"]:
                errors[key] = Invalid("UNKNOWN_PARTNER", "REFERENTIAL_INTEGRITY")
            elif kind in {"payment", "statement"}:
                account = dimensions["account"].get(entry["account"])
                if not account:
                    errors[key] = Invalid("UNKNOWN_ACCOUNT", "REFERENTIAL_INTEGRITY")
                elif account["currency"] != entry["currency"]:
                    errors[key] = Invalid("ACCOUNT_CURRENCY_MISMATCH", "CONSISTENCY")
                elif r["source"] == "csv" and r["external_id"] in duplicate_payments:
                    errors[key] = Invalid("DUPLICATE_BANK_ID", "UNIQUENESS")
            if (
                kind in {"invoice", "payment", "statement"}
                and key not in errors
                and entry["currency"] != BASE
                and (entry["date"], entry["currency"]) not in dimensions["rate"]
            ):
                errors[key] = Invalid("FX_MISSING", "REFERENTIAL_INTEGRITY")
        exc = errors.get(key)
        status = "QUARANTINED" if exc else "READY"
        previous = row(
            conn,
            "SELECT * FROM stage WHERE raw=:id AND mapping=:v",
            id=key,
            v=mapping["version"],
        )
        reason = str(exc) if exc else None
        if not previous or previous["reason"] != reason:
            sql(
                conn,
                """INSERT INTO stage(raw,mapping,normalized,status,reason,run)
                VALUES (:id,:v,CAST(:p AS jsonb),:s,:reason,:r)
                ON CONFLICT(raw,mapping) DO UPDATE SET normalized=excluded.normalized,status=excluded.status,
                reason=excluded.reason,run=excluded.run""",
                id=key,
                v=mapping["version"],
                p=dumps(entry),
                s=status,
                reason=reason,
                r=id,
            )
            if exc:
                problem(
                    conn,
                    id,
                    r["source"],
                    key,
                    exc.dimension,
                    reason,
                    entity=kind,
                    external_id=r["external_id"],
                )
        fields = dict(s=r["source"], e=kind, k=r["external_id"])
        if exc:
            sql(
                conn,
                "DELETE FROM facts WHERE source=:s AND entity=:e AND external_id=:k",
                **fields,
            )
        else:
            sql(
                conn,
                """INSERT INTO facts(source,entity,external_id,revision,raw,mapping,run,business_date,amount,currency,category,attributes)
              VALUES (:s,:e,:k,:v,:id,:m,:r,:date,:amount,:currency,:category,CAST(:a AS jsonb))
              ON CONFLICT(source,entity,external_id) DO UPDATE SET revision=excluded.revision,raw=excluded.raw,
              mapping=excluded.mapping,run=excluded.run,business_date=excluded.business_date,amount=excluded.amount,
              currency=excluded.currency,category=excluded.category,attributes=excluded.attributes
              WHERE facts.raw<>excluded.raw OR facts.mapping<>excluded.mapping""",
                **fields,
                v=r["revision"],
                id=key,
                m=mapping["version"],
                r=id,
                date=entry.get("date"),
                amount=entry.get("amount"),
                currency=entry.get("currency"),
                category=entry.get("category"),
                a=dumps(entry),
            )
    return len(errors)


def pipeline(
    actor=None,
    request=None,
    mode="incremental",
    csv_data=None,
    aliases=None,
    fail=False,
):
    id, request, start = uuid4(), request or uuid4(), datetime.now(UTC)
    try:
        with engine.begin() as conn:
            guard(conn)
            create_run(conn, id, actor, request, start, mode)
            summary = {}
            for source in SOURCES if mode in {"incremental", "full"} else ():
                previous = row(
                    conn, "SELECT * FROM checkpoints WHERE source=:s", s=source
                )
                start_cursor = 0 if mode == "full" else previous["sequence"]
                counts = {
                    "start_cursor": start_cursor,
                    "end_cursor": previous["sequence"],
                    "received": 0,
                    "accepted": 0,
                    "duplicates": 0,
                    "rejected": 0,
                    "error": None,
                }
                summary[source] = counts
                try:
                    items = fetch(source, start_cursor)
                except (httpx.HTTPError, ValueError) as exc:
                    code = (
                        "SOURCE_UNAVAILABLE"
                        if isinstance(exc, httpx.HTTPError)
                        else "INVALID_FEED"
                    )
                    counts["error"] = code
                    sql(
                        conn,
                        "UPDATE checkpoints SET last_error=:err WHERE source=:s",
                        err=code,
                        s=source,
                    )
                    problem(conn, id, source, None, "FRESHNESS", code)
                    continue
                store(conn, id, source, items, counts)
                counts["end_cursor"] = max(
                    previous["sequence"], items[-1].sequence if items else 0
                )
                sql(
                    conn,
                    """UPDATE checkpoints SET sequence=:n,last_success=clock_timestamp(),last_error=NULL
                    WHERE source=:s""",
                    n=counts["end_cursor"],
                    s=source,
                )
                if any(start - event.event_time > timedelta(days=7) for event in items):
                    problem(conn, id, source, None, "FRESHNESS", "LATE_DELIVERY")
            if csv_data is not None:
                current = row(
                    conn, "SELECT sequence FROM checkpoints WHERE source='csv'"
                )["sequence"]
                counts = {
                    "start_cursor": current,
                    "end_cursor": current,
                    "received": 0,
                    "accepted": 0,
                    "duplicates": 0,
                    "rejected": 0,
                    "error": None,
                }
                items = [
                    Delivery(
                        sequence=current + i,
                        kind="payment",
                        external_id=key,
                        revision=1,
                        event_time=start,
                        payload=payload,
                    )
                    for i, (key, payload) in enumerate(csv_data, 1)
                ]
                store(conn, id, "csv", items, counts)
                counts["end_cursor"] = items[-1].sequence
                sql(
                    conn,
                    "UPDATE checkpoints SET sequence=:n,last_success=clock_timestamp() WHERE source='csv'",
                    n=counts["end_cursor"],
                )
                summary["csv"] = counts
            if aliases is not None:
                sql(
                    conn,
                    """INSERT INTO mapping(version,aliases,actor)
                  SELECT max(version)+1,CAST(:p AS jsonb),:a FROM mapping""",
                    p=dumps(aliases),
                    a=actor,
                )
            quarantined = rebuild(conn, id)
            if fail:
                raise RuntimeError("INJECTED_ETL_FAILURE")
            status = (
                "PARTIAL"
                if quarantined
                or any(s["error"] or s["rejected"] for s in summary.values())
                else "SUCCESS"
            )
            sql(
                conn,
                "UPDATE runs SET status=:s,summary=CAST(:p AS jsonb),finished=clock_timestamp() WHERE id=:id",
                s=status,
                p=dumps({"sources": summary, "quarantined": quarantined}),
                id=id,
            )
            audit(conn, actor, request, "ETL_PUBLISHED", id, status=status, mode=mode)
            return summary_row(conn, id)
    except (SQLAlchemyError, RuntimeError):
        if not fail:
            LOG.exception(
                "ETL publication rolled back", extra={"request_id": str(request)}
            )
        with engine.begin() as conn:
            create_run(conn, id, actor, request, start, mode, "FAILED")
            sql(
                conn,
                "UPDATE runs SET summary=CAST(:p AS jsonb) WHERE id=:id",
                id=id,
                p=dumps(
                    {"error": "INJECTED_ETL_FAILURE" if fail else "ETL_STORAGE_FAILURE"}
                ),
            )
            audit(conn, actor, request, "ETL_FAILED", id)
            return summary_row(conn, id)


def parse_csv(data):
    columns = {
        "external_id",
        "amount",
        "currency",
        "date",
        "account",
        "document",
        "nature",
    }
    reader = csv.DictReader(StringIO(data), strict=True)
    parsed = []
    try:
        if (
            not reader.fieldnames
            or set(reader.fieldnames) != columns
            or len(reader.fieldnames) != len(columns)
        ):
            raise ValueError
        for n, line in enumerate(reader, 1):
            if n > 100 or None in line or any(v is None for v in line.values()):
                raise ValueError
            key = line.pop("external_id")
            Delivery(
                sequence=n,
                kind="payment",
                external_id=key,
                revision=1,
                event_time=datetime.now(UTC),
                payload=line,
            )
            line["document"] = line["document"] or None
            parsed.append((key, line))
    except (ValueError, csv.Error) as exc:
        raise HTTPException(422, "INVALID_CSV") from exc
    if not parsed:
        raise HTTPException(422, "EMPTY_CSV")
    return parsed
