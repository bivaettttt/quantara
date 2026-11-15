import os
from uuid import uuid4

from quantara.auth import passwords
from quantara.contracts import Period
from quantara.db import engine, row, sql
from quantara.etl import pipeline
from quantara.reports import build


def seed():
    with engine.begin() as conn:
        sql(conn, "SELECT pg_advisory_xact_lock(761901)")
        if row(conn, "SELECT login FROM users WHERE login='admin'"):
            return
        password = os.environ["DEMO_PASSWORD"]
        if len(password) < 12:
            raise ValueError("DEMO_PASSWORD requires at least 12 characters")
        for login, name, role in [
            ("finance", "Анна Соколова", "FINANCIAL_ANALYST"),
            ("analyst", "Вера Орлова", "DATA_ANALYST"),
            ("engineer", "Илья Волков", "DATA_ENGINEER"),
            ("steward", "Мария Лебедева", "DATA_STEWARD"),
            ("admin", "Алексей Котов", "ADMIN"),
        ]:
            sql(
                conn,
                "INSERT INTO users VALUES (:l,:n,:r,:p)",
                l=login,
                n=name,
                r=role,
                p=passwords.hash(password),
            )
    result = pipeline("admin", uuid4())
    if result["status"] == "SUCCESS":
        with engine.begin() as conn:
            build(conn, Period(start="2026-06-01", end="2026-06-30"), "admin", uuid4())


if __name__ == "__main__":
    seed()
