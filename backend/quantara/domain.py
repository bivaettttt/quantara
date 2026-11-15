import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

MONEY = Decimal("0.01")
MAPPING_VERSION = "normalize/1"
METHOD = "quantara-accrual-cash/1"
BASE = "RUB"
CURRENCIES = {"RUB", "USD", "EUR"}

METRICS = {
    "revenue": ("Выручка по начислению", "Сумма признанных счетов покупателей"),
    "expenses": ("Расходы по начислению", "Сумма признанных счетов поставщиков"),
    "operating_result": ("Операционный результат", "Выручка минус расходы"),
    "cash_in": ("Денежные поступления", "Сумма положительных платежей"),
    "cash_out": ("Денежные выплаты", "Модуль суммы отрицательных платежей"),
    "net_cash": ("Чистый денежный поток", "Поступления минус выплаты"),
    "cash_balance": ("Конечный остаток", "Начальный остаток и подтверждённое движение"),
    "receivables": ("Дебиторская задолженность", "Остаток активных счетов покупателей"),
    "payables": ("Кредиторская задолженность", "Остаток активных счетов поставщиков"),
    "budget_variance": ("Отклонение от бюджета", "Расходы минус сопоставленный бюджет"),
}


class Invalid(ValueError):
    def __init__(self, code, dimension="VALIDITY"):
        super().__init__(code)
        self.dimension = dimension


def decimal(value, scale=2, nonnegative=False):
    if not isinstance(value, str) or not re.fullmatch(
        r"-?\d{1,16}(?:\.\d{1," + str(scale) + r"})?", value
    ):
        raise Invalid("INVALID_AMOUNT")
    result = Decimal(value)
    if nonnegative and result < 0:
        raise Invalid("NEGATIVE_AMOUNT")
    return result


def money(value):
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def normalize(kind, p, aliases):
    def get(key):
        if key not in p or p[key] is None or p[key] == "":
            raise Invalid("MISSING_" + key.upper(), "COMPLETENESS")
        return p[key]

    def string(key):
        value = get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 120:
            raise Invalid("INVALID_" + key.upper())
        return value.strip()

    def options(key, allowed):
        value = string(key)
        if value not in allowed:
            raise Invalid("INVALID_" + key.upper())
        return value

    def day(key):
        try:
            value = string(key)
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError
            return value
        except ValueError as exc:
            if isinstance(exc, Invalid):
                raise
            raise Invalid("INVALID_DATE") from exc

    if kind == "partner":
        return {"name": string("name")}
    currency = options("currency", CURRENCIES)
    if kind == "account":
        return {"currency": currency, "name": string("name")}
    result = {"currency": currency, "date": day("date")}
    if kind == "rate":
        rate = decimal(get("rate"), 6, True)
        if rate <= 0 or rate > 100000 or currency == BASE:
            raise Invalid("INVALID_FX")
        return result | {"rate": str(rate)}
    if kind == "statement":
        start = day("start")
        if start > result["date"]:
            raise Invalid("INVALID_INTERVAL", "CONSISTENCY")
        return result | {
            "account": string("account"),
            "start": start,
            "opening": str(decimal(get("opening"))),
            "closing": str(decimal(get("closing"))),
        }
    amount = decimal(get("amount"), nonnegative=kind != "payment")
    if kind == "payment":
        nature = options("nature", {"PAYMENT", "FEE", "REFUND"})
        if amount == 0 or (nature == "FEE" and amount > 0):
            raise Invalid("INVALID_DIRECTION", "CONSISTENCY")
        return result | {
            "amount": str(amount),
            "account": string("account"),
            "nature": nature,
            "document": string("document") if p.get("document") else None,
        }
    category = string("category")
    result.update(amount=str(amount), category=aliases.get(category, category))
    if kind == "budget":
        if currency != BASE or not result["date"].endswith("-01"):
            raise Invalid("INVALID_BUDGET_BASIS", "CONSISTENCY")
        return result
    if kind != "invoice":
        raise Invalid("UNSUPPORTED_ENTITY")
    adjustment = decimal(p.get("adjustment", "0"))
    if amount + adjustment < 0:
        raise Invalid("INVALID_ADJUSTMENT", "CONSISTENCY")
    return result | {
        "partner": string("partner"),
        "side": options("side", {"REVENUE", "EXPENSE"}),
        "status": options("status", {"POSTED", "DRAFT", "VOID"}),
        "adjustment": str(adjustment),
    }
