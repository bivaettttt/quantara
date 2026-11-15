import os
from decimal import Decimal
from uuid import uuid4

import httpx
from quantara.db import engine, sql
from quantara.lab import PERIOD, SCENARIOS
from sqlalchemy.exc import IntegrityError

client = httpx.Client(base_url="http://127.0.0.1:8000/api", timeout=60, trust_env=False)
users = {}


def call(user, method, path, data=None, want=200):
    headers = {"Authorization": "Bearer " + users[user]} if user else {}
    r = client.request(method, path, json=data, headers=headers)
    assert r.status_code == want, (method, path, r.status_code, r.text[:800])
    assert r.headers["X-Request-ID"]
    return r.json() if "json" in r.headers.get("Content-Type", "") else r.text


for login in ("admin", "finance", "engineer", "analyst", "steward"):
    users[login] = call(
        None,
        "POST",
        "/auth/login",
        {"login": login, "password": os.environ["DEMO_PASSWORD"]},
    )["token"]
call(None, "GET", "/reports", want=401)
call("finance", "POST", "/runs", want=403)
call("engineer", "POST", "/reports", PERIOD, 403)
call("analyst", "POST", "/lab/reproduce", want=403)
call("finance", "GET", "/quarantine", want=403)
report = call("finance", "POST", "/reports", PERIOD, 201)
m = report["result"]["metrics"]
assert m["revenue"]["value"] == "1450312.50"
assert m["cash_in"]["value"] == "750000.00"
assert m["operating_result"]["value"] == "781472.50"
assert m["receivables"]["value"] == "830312.50"
assert m["payables"]["value"] == "438840.00"
assert m["cash_balance"]["value"] == "819500.00"
assert m["budget_variance"]["value"] == "-11160.00"
assert report["quality"] == "COMPLETE"
assert "revenue,1450312.50,COMPLETE" in call(
    "finance", "GET", f"/reports/{report['id']}/export"
)
for table, column, value in [
    ("reports", "id", report["id"]),
    ("raw", "id", m["revenue"]["contributions"][0]["raw"]),
]:
    try:
        with engine.begin() as conn:
            sql(conn, f"DELETE FROM {table} WHERE {column}=:id", id=value)
    except IntegrityError as error:
        assert error.orig.sqlstate == "23514"
    else:
        raise AssertionError("History changed")

for name in SCENARIOS:
    result = call("admin", "POST", "/lab/" + name)
    assert result["passed"], (name, result["checks"])
    print(name, result["checks"], flush=True)

tag = "CSV-" + uuid4().hex[:8]
csv = (
    "external_id,account,currency,date,amount,document,nature\n"
    + tag
    + ",RUB-01,RUB,2026-06-02,120.00,,PAYMENT"
)
first = call("engineer", "POST", "/import", {"text": csv}, 201)
again = call("engineer", "POST", "/import", {"text": csv}, 201)
assert first["summary"]["sources"]["csv"]["accepted"] == 1
assert again["summary"]["sources"]["csv"]["duplicates"] == 1
facts = call("analyst", "GET", "/warehouse?entity=payment")
assert any(f["external_id"] == tag and Decimal(str(f["amount"])) == 120 for f in facts)
print(
    "24 laboratory experiments and PostgreSQL financial, security, immutability and CSV checks passed."
)
