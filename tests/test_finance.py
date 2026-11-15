from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from quantara.domain import Invalid, decimal, money, normalize
from quantara.etl import parse_csv
from quantara.reports import calculate

START, END = date(2026, 6, 1), date(2026, 6, 30)


@pytest.mark.parametrize("value", [0.1, "1e8", "NaN", "1.234", True])
def test_money_rejects_unsafe_number(value):
    with pytest.raises(Invalid):
        decimal(value)


def test_round_halves():
    assert money(Decimal("10.005")) == Decimal("10.01")
    assert money(Decimal("-10.005")) == Decimal("-10.01")


def test_transaction_clock_is_canonical():
    with pytest.raises(Invalid, match="INVALID_DATE"):
        normalize("rate", {"currency": "USD", "date": "20260610", "rate": "10.21"}, {})


def fact(entity, external_id, raw, amount=None, **attrs):
    return dict(
        source="bank" if entity in {"payment", "account", "statement"} else "erp",
        entity=entity,
        external_id=external_id,
        raw=raw,
        revision=1,
        mapping=1,
        run="demo",
        business_date=date.fromisoformat(attrs["date"]) if attrs.get("date") else None,
        amount=Decimal(amount) if amount is not None else None,
        currency=attrs.get("currency", "RUB"),
        category=attrs.get("category"),
        attributes=attrs,
    )


def test_accrual_cash_and_open_items_are_separate():
    result = calculate(
        [
            fact(
                "invoice",
                "I1",
                1,
                "1000000",
                side="REVENUE",
                status="POSTED",
                date="2026-06-01",
                category="Sales",
                adjustment="0",
            ),
            fact(
                "payment",
                "P1",
                2,
                "400000",
                document="I1",
                nature="PAYMENT",
                date="2026-06-10",
                account="A1",
            ),
            fact(
                "payment",
                "P2",
                3,
                "-10000",
                document="I1",
                nature="REFUND",
                date="2026-06-20",
                account="A1",
            ),
        ],
        [],
        START,
        END,
    )
    assert result["metrics"]["revenue"]["value"] == "1000000.00"
    assert result["metrics"]["cash_in"]["value"] == "400000.00"
    assert result["metrics"]["net_cash"]["value"] == "390000.00"
    assert result["metrics"]["receivables"]["value"] == "610000.00"


def test_missing_fact_is_unknown_and_has_trace():
    result = calculate(
        [], [{"raw": 12, "entity": "invoice", "date": START}], START, END
    )
    assert result["metrics"]["revenue"] == {
        "value": None,
        "known": "0.00",
        "excluded": [12],
        "contributions": [],
    }


def test_csv_schema_and_nonfinancial_columns():
    with pytest.raises(HTTPException, match="INVALID_CSV"):
        parse_csv("source,id\nerp,1")
    entry = parse_csv(
        "external_id,account,currency,date,amount,document,nature\np1,RUB-01,RUB,2026-06-02,10.00,,PAYMENT"
    )
    assert entry[0][0] == "p1" and entry[0][1]["document"] is None
