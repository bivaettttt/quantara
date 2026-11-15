import csv
import os
from io import StringIO
from secrets import token_urlsafe
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from quantara import contracts as c
from quantara import reports
from quantara.auth import (
    DATA,
    ENGINEERING,
    FIN,
    Actor,
    allow,
    passwords,
    signin,
    token_hash,
)
from quantara.db import audit, engine, row, rows, sql
from quantara.domain import METRICS
from quantara.etl import guard, parse_csv, pipeline
from quantara.lab import SCENARIOS, exercise

app = FastAPI(
    title="Quantara",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
A = "/api"
Offset = Annotated[int, Query(ge=0)]


@app.middleware("http")
async def tracking(request: Request, call_next):
    request.state.id = uuid4()
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(request.state.id)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def error(request: Request, exception: HTTPException):
    return JSONResponse(
        {"detail": exception.detail, "request_id": str(request.state.id)},
        status_code=exception.status_code,
    )


@app.exception_handler(RequestValidationError)
async def invalid(request: Request, exception: RequestValidationError):
    return JSONResponse(
        {
            "detail": "INVALID_REQUEST",
            "request_id": str(request.state.id),
            "fields": [
                {"path": list(e["loc"]), "type": e["type"]} for e in exception.errors()
            ],
        },
        status_code=422,
    )


@app.get("/health")
def health():
    with engine.connect() as conn:
        sql(conn, "SELECT sequence FROM checkpoints")
    return {"status": "ok"}


@app.post(A + "/auth/login")
def login(payload: c.Login, request: Request):
    return signin(payload, request.state.id)


@app.post(A + "/auth/logout", status_code=204)
def logout(actor: Actor):
    with engine.begin() as conn:
        sql(conn, "DELETE FROM sessions WHERE token_digest=:s", s=actor["session"])


@app.get(A + "/users")
def users(actor: Actor):
    allow(actor, "ADMIN")
    with engine.connect() as conn:
        return rows(conn, "SELECT login,name,role FROM users ORDER BY login")


@app.post(A + "/users", status_code=201)
def new_user(payload: c.User, actor: Actor, request: Request):
    allow(actor, "ADMIN")
    with engine.begin() as conn:
        item = row(
            conn,
            """INSERT INTO users(login,name,role,password) VALUES (:login,:name,:role,:password)
                    ON CONFLICT DO NOTHING RETURNING login,name,role""",
            **(payload.model_dump() | {"password": passwords.hash(payload.password)}),
        )
        if not item:
            raise HTTPException(409, "LOGIN_EXISTS")
        audit(
            conn,
            actor["login"],
            request.state.id,
            "USER_CREATED",
            item["login"],
            role=item["role"],
        )
        return item


@app.get(A + "/sources")
def sources(actor: Actor):
    with engine.connect() as conn:
        return rows(
            conn,
            """SELECT *, CASE WHEN last_error IS NOT NULL THEN 'UNAVAILABLE'
                  WHEN last_success IS NULL OR last_success<now()-interval '24 hours' THEN 'STALE'
                  ELSE 'READY' END AS status FROM checkpoints ORDER BY source""",
        )


@app.get(A + "/runs")
def runs(actor: Actor, offset: Offset = 0):
    with engine.connect() as conn:
        return rows(
            conn,
            "SELECT * FROM runs ORDER BY started DESC,id LIMIT 50 OFFSET :o",
            o=offset,
        )


@app.get(A + "/runs/{id}")
def run_detail(id: UUID, actor: Actor):
    with engine.connect() as conn:
        item = row(conn, "SELECT * FROM runs WHERE id=:id", id=id)
        if not item:
            raise HTTPException(404, "RUN_NOT_FOUND")
        return item | {
            "issues": rows(
                conn, "SELECT * FROM quality WHERE run=:id ORDER BY id LIMIT 100", id=id
            )
        }


@app.post(A + "/runs", status_code=201)
def run_etl(
    actor: Actor,
    request: Request,
    mode: Literal["incremental", "full", "reprocess"] = "incremental",
):
    allow(actor, *ENGINEERING)
    return pipeline(actor["login"], request.state.id, mode)


@app.post(A + "/import", status_code=201)
def import_csv(payload: c.Csv, actor: Actor, request: Request):
    allow(actor, "DATA_ENGINEER", "ADMIN")
    return pipeline(
        actor["login"], request.state.id, "csv", csv_data=parse_csv(payload.text)
    )


@app.get(A + "/quality")
def issues(actor: Actor, offset: Offset = 0):
    allow(actor, *DATA)
    with engine.connect() as conn:
        return rows(
            conn, "SELECT * FROM quality ORDER BY id DESC LIMIT 50 OFFSET :o", o=offset
        )


@app.get(A + "/quarantine")
def quarantine(actor: Actor, offset: Offset = 0):
    allow(actor, *DATA)
    with engine.connect() as conn:
        return rows(
            conn,
            """SELECT r.id,r.source,r.entity,r.external_id,r.revision,r.run,s.reason,s.mapping,s.normalized
           FROM (SELECT DISTINCT ON(source,entity,external_id) * FROM raw WHERE disposition='CANONICAL'
                 ORDER BY source,entity,external_id,revision DESC,id) r
           JOIN stage s ON s.raw=r.id AND s.mapping=(SELECT max(version) FROM mapping)
           WHERE s.status='QUARANTINED' ORDER BY r.id DESC LIMIT 50 OFFSET :o""",
            o=offset,
        )


@app.get(A + "/raw")
def raw_records(
    actor: Actor, offset: Offset = 0, q: Annotated[str, Query(max_length=80)] = ""
):
    allow(actor, *DATA)
    with engine.connect() as conn:
        return rows(
            conn,
            """SELECT id,source,entity,external_id,revision,received,disposition,run FROM raw
           WHERE external_id ILIKE :q ORDER BY id DESC LIMIT 50 OFFSET :o""",
            o=offset,
            q=f"%{q}%",
        )


@app.get(A + "/raw/{id}")
def raw(id: int, actor: Actor):
    allow(actor, *DATA, *FIN)
    with engine.connect() as conn:
        item = row(conn, "SELECT * FROM raw WHERE id=:id", id=id)
        if not item:
            raise HTTPException(404, "RAW_NOT_FOUND")
        return item | {
            "stage": rows(
                conn, "SELECT * FROM stage WHERE raw=:id ORDER BY mapping DESC", id=id
            ),
            "issues": rows(
                conn, "SELECT * FROM quality WHERE raw=:id ORDER BY id DESC", id=id
            ),
        }


@app.get(A + "/warehouse")
def warehouse(
    actor: Actor,
    offset: Offset = 0,
    entity: Literal[
        "invoice", "payment", "budget", "statement", "partner", "account", "rate"
    ]
    | None = None,
):
    allow(actor, *DATA, *FIN)
    with engine.connect() as conn:
        return rows(
            conn,
            """SELECT * FROM facts WHERE (CAST(:e AS text) IS NULL OR entity=:e)
                       ORDER BY business_date DESC NULLS LAST,source,external_id LIMIT 50 OFFSET :o""",
            e=entity,
            o=offset,
        )


@app.get(A + "/mapping")
def mappings(actor: Actor):
    allow(actor, *DATA)
    with engine.connect() as conn:
        return rows(conn, "SELECT * FROM mapping ORDER BY version DESC")


@app.post(A + "/mapping", status_code=201)
def mapping(payload: c.Mapping, actor: Actor, request: Request):
    allow(actor, "ADMIN", "DATA_STEWARD")
    return pipeline(
        actor["login"], request.state.id, "mapping", aliases=payload.aliases
    )


@app.get(A + "/kpis")
def registry(actor: Actor):
    allow(actor, *FIN)
    return [
        {
            "code": k,
            "name": n,
            "formula": f,
            "currency": "RUB",
            "version": "quantara-accrual-cash/1",
        }
        for k, (n, f) in METRICS.items()
    ]


@app.get(A + "/reports")
def list_reports(actor: Actor, offset: Offset = 0):
    allow(actor, *FIN)
    with engine.connect() as conn:
        return rows(
            conn,
            """SELECT id,start_date,end_date,quality,checksum,method,created FROM reports
                          ORDER BY created DESC,id LIMIT 50 OFFSET :o""",
            o=offset,
        )


@app.post(A + "/reports", status_code=201)
def build_report(payload: c.Period, actor: Actor, request: Request):
    allow(actor, "FINANCIAL_ANALYST", "ADMIN")
    with engine.begin() as conn:
        guard(conn)
        return reports.build(conn, payload, actor["login"], request.state.id)


@app.get(A + "/reports/{id}")
def get_report(id: UUID, actor: Actor):
    allow(actor, *FIN)
    with engine.connect() as conn:
        return reports.get(conn, id)


@app.get(A + "/reports/{id}/compare/{other}")
def compare(id: UUID, other: UUID, actor: Actor):
    allow(actor, *FIN)
    with engine.connect() as conn:
        return reports.compare(reports.get(conn, id), reports.get(conn, other))


@app.get(A + "/reports/{id}/export", response_class=Response)
def export_report(id: UUID, actor: Actor):
    allow(actor, *FIN)
    with engine.connect() as conn:
        report = reports.get(conn, id)
    target = StringIO()
    writer = csv.writer(target)
    writer.writerow(["metric", "rub", "quality"])
    for key, value in report["result"]["metrics"].items():
        # Only fixed metric codes and precision-controlled Decimal outputs enter export.
        writer.writerow([key, value["value"], report["quality"]])
    return Response(
        target.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=quantara-report.csv"},
    )


@app.post(A + "/reports/{id}/scenarios", status_code=201)
def scenario(id: UUID, payload: c.Scenario, actor: Actor, request: Request):
    allow(actor, "FINANCIAL_ANALYST", "ADMIN")
    with engine.begin() as conn:
        return reports.scenario(
            conn, reports.get(conn, id), payload, actor["login"], request.state.id
        )


@app.get(A + "/reports/{id}/scenarios")
def scenarios(id: UUID, actor: Actor):
    allow(actor, *FIN)
    with engine.connect() as conn:
        reports.get(conn, id)
        return rows(
            conn,
            "SELECT * FROM scenarios WHERE report=:id ORDER BY created DESC LIMIT 50",
            id=id,
        )


@app.get(A + "/audit")
def audit_log(actor: Actor, offset: Offset = 0):
    allow(actor, "ADMIN")
    with engine.connect() as conn:
        return rows(
            conn, "SELECT * FROM audit ORDER BY id DESC LIMIT 50 OFFSET :o", o=offset
        )


@app.get(A + "/lab")
def lab_config(actor: Actor):
    allow(actor, "ADMIN")
    return {
        "enabled": os.getenv("LAB_MODE") == "1",
        "scenarios": SCENARIOS if os.getenv("LAB_MODE") == "1" else {},
    }


@app.post(A + "/lab/{name}")
def lab(name: str, actor: Actor, request: Request):
    allow(actor, "ADMIN")
    if os.getenv("LAB_MODE") != "1" or name not in SCENARIOS:
        raise HTTPException(404, "SCENARIO_NOT_FOUND")
    token = token_urlsafe(32)
    token_digest = token_hash(token)
    with engine.begin() as conn:
        if not sql(conn, "SELECT pg_try_advisory_xact_lock(765043)").scalar_one():
            raise HTTPException(409, "LAB_BUSY")
        with engine.begin() as sessions:
            sql(
                sessions,
                "INSERT INTO sessions VALUES (:d,:u,now()+interval '5 minutes')",
                d=token_digest,
                u=actor["login"],
            )
        try:
            result = exercise(
                name,
                token,
                lambda: pipeline(actor["login"], request.state.id, fail=True),
            )
            audit(
                conn,
                actor["login"],
                request.state.id,
                "LAB_RUN",
                name,
                passed=result["passed"],
            )
            return result
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        finally:
            with engine.begin() as sessions:
                sql(
                    sessions,
                    "DELETE FROM sessions WHERE token_digest=:d",
                    d=token_digest,
                )
