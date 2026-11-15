import csv
import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from io import StringIO
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fixtures import initial
from pydantic import BaseModel, Field

SOURCE = os.environ.get("SOURCE", "erp")
DB = os.getenv("SOURCE_DB", "/state/feed.sqlite")
KINDS = {
    "erp": {"partner", "invoice", "budget"},
    "bank": {"account", "payment", "statement"},
    "fx": {"rate"},
}[SOURCE]
app = FastAPI(title=f"Quantara {SOURCE.upper()} source", version="1.0.0")


def connect():
    conn = sqlite3.connect(DB, timeout=8)
    conn.row_factory = sqlite3.Row
    return conn


def append(conn, kind, key, payload, revision=None):
    if kind not in KINDS:
        raise HTTPException(422, "WRONG_ENTITY")
    previous = conn.execute(
        "SELECT max(revision) FROM changes WHERE kind=? AND external_id=?", (kind, key)
    ).fetchone()[0]
    revision = revision or ((previous or 0) + 1)
    timestamp = datetime.now(UTC).isoformat()
    seq = conn.execute(
        "INSERT INTO changes(kind,external_id,revision,payload,event_time) VALUES (?,?,?,?,?)",
        (kind, key, revision, json.dumps(payload, sort_keys=True), timestamp),
    ).lastrowid
    return {
        "sequence": seq,
        "kind": kind,
        "external_id": key,
        "revision": revision,
        "event_time": timestamp,
        "payload": payload,
    }


with closing(connect()) as conn, conn:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS changes(sequence integer PRIMARY KEY AUTOINCREMENT,kind text,external_id text,revision integer,payload text,event_time text);
    CREATE TABLE IF NOT EXISTS settings(id integer PRIMARY KEY, available integer NOT NULL);
    INSERT OR IGNORE INTO settings VALUES(1,1);
    """)
    if not conn.execute("SELECT sequence FROM changes LIMIT 1").fetchone():
        for kind, key, payload in initial(SOURCE):
            append(conn, kind, key, payload)


class Change(BaseModel):
    kind: str
    external_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,100}$")]
    revision: Annotated[int, Field(gt=0, le=1000000)] | None = None
    payload: dict


class Csv(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=100000)]


class Mode(BaseModel):
    available: bool


def control():
    if os.getenv("LAB_MODE") != "1":
        raise HTTPException(404, "CONTROL_DISABLED")


@app.get("/health")
def health():
    return {"status": "ok", "source": SOURCE}


@app.get("/changes")
def changes(
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    start: date | None = None,
    end: date | None = None,
):
    with closing(connect()) as conn:
        if not conn.execute("SELECT available FROM settings").fetchone()[0]:
            raise HTTPException(503, "SOURCE_UNAVAILABLE")
        rows = conn.execute(
            """SELECT * FROM changes WHERE sequence>? AND ((? IS NULL AND ? IS NULL) OR
             (json_extract(payload,'$.date') IS NOT NULL AND (? IS NULL OR json_extract(payload,'$.date')>=?)
             AND (? IS NULL OR json_extract(payload,'$.date')<=?))) ORDER BY sequence LIMIT ?""",
            (after, start, end, start, start, end, end, limit),
        )
        return {
            "source": SOURCE,
            "contract": "source/1",
            "records": [
                dict(row) | {"payload": json.loads(row["payload"])} for row in rows
            ],
        }


@app.post("/control/change", status_code=201)
def change(item: Change):
    control()
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        return append(conn, item.kind, item.external_id, item.payload, item.revision)


@app.put("/control/mode")
def mode(item: Mode):
    control()
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE settings SET available=?", (item.available,))
    return item


@app.post("/import", status_code=201)
def csv_import(item: Csv):
    control()
    if SOURCE != "bank":
        raise HTTPException(404, "BANK_ONLY")
    reader = csv.DictReader(StringIO(item.text), strict=True)
    expected = {
        "external_id",
        "account",
        "currency",
        "date",
        "amount",
        "document",
        "nature",
    }
    try:
        if (
            not reader.fieldnames
            or len(reader.fieldnames) != len(expected)
            or set(reader.fieldnames) != expected
        ):
            raise HTTPException(422, "CSV_HEADER")
        rows = []
        for number, row in enumerate(reader, 1):
            if (
                number > 100
                or None in row
                or any(value is None for value in row.values())
            ):
                raise HTTPException(422, "CSV_ROWS")
            key = row.pop("external_id")
            row["document"] = row["document"] or None
            rows.append(Change(kind="payment", external_id=key, payload=row))
    except (csv.Error, ValueError) as exc:
        raise HTTPException(422, "CSV_ROWS") from exc
    if not rows:
        raise HTTPException(422, "CSV_EMPTY")
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        return [
            append(conn, item.kind, item.external_id, item.payload, item.revision)
            for item in rows
        ]
