import hashlib
import json
import os

from sqlalchemy import create_engine, text

engine = create_engine(
    os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://quantara:quantara-local@localhost/quantara",
    ),
    pool_pre_ping=True,
)


def dumps(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
    )


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def sql(conn, statement, **params):
    return conn.execute(text(statement), params)


def rows(conn, statement, **params):
    return [dict(row) for row in sql(conn, statement, **params).mappings()]


def row(conn, statement, **params):
    result = sql(conn, statement, **params).mappings().first()
    return dict(result) if result is not None else None


def audit(conn, actor, request, action, subject, **detail):
    sql(
        conn,
        "INSERT INTO audit(actor,request,action,subject,detail) VALUES (:a,:r,:k,:s,CAST(:d AS jsonb))",
        a=actor,
        r=request,
        k=action,
        s=str(subject),
        d=dumps(detail),
    )
