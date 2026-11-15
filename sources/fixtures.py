def initial(source):
    if source == "erp":
        yield "partner", "AURORA", {"name": "Аврора · учебный покупатель"}
        yield "partner", "MERIDIAN", {"name": "Меридиан · учебный поставщик"}
        rows = [
            (
                "INV-100",
                "AURORA",
                "REVENUE",
                "Services",
                "1000000.00",
                "RUB",
                "2026-06-05",
            ),
            (
                "INV-101",
                "AURORA",
                "REVENUE",
                "Licenses",
                "2500.00",
                "USD",
                "2026-06-10",
            ),
            (
                "INV-102",
                "AURORA",
                "REVENUE",
                "Services",
                "220000.00",
                "RUB",
                "2026-06-20",
            ),
            (
                "BILL-200",
                "MERIDIAN",
                "EXPENSE",
                "Operations",
                "500000.00",
                "RUB",
                "2026-06-07",
            ),
            (
                "BILL-201",
                "MERIDIAN",
                "EXPENSE",
                "Technology",
                "1200.00",
                "EUR",
                "2026-06-10",
            ),
            (
                "BILL-202",
                "MERIDIAN",
                "EXPENSE",
                "Operations",
                "45000.00",
                "RUB",
                "2026-06-25",
            ),
        ]
        for key, partner, side, category, amount, currency, day in rows:
            yield (
                "invoice",
                key,
                dict(
                    partner=partner,
                    side=side,
                    category=category,
                    amount=amount,
                    currency=currency,
                    date=day,
                    status="POSTED",
                    adjustment="0.00",
                ),
            )
        yield (
            "budget",
            "OPS-JUN",
            dict(
                category="Operations",
                amount="570000.00",
                currency="RUB",
                date="2026-06-01",
            ),
        )
        yield (
            "budget",
            "TECH-JUN",
            dict(
                category="Technology",
                amount="110000.00",
                currency="RUB",
                date="2026-06-01",
            ),
        )
    elif source == "bank":
        yield "account", "RUB-01", dict(currency="RUB", name="Учебный расчётный счёт")
        yield (
            "statement",
            "ST-JUN",
            dict(
                account="RUB-01",
                currency="RUB",
                date="2026-06-30",
                start="2026-06-01",
                opening="300000.00",
                closing="819500.00",
            ),
        )
        for key, amount, document, nature, day in [
            ("PAY-001", "400000.00", "INV-100", "PAYMENT", "2026-06-12"),
            ("PAY-002", "-230000.00", "BILL-200", "PAYMENT", "2026-06-13"),
            ("PAY-003", "220000.00", "INV-102", "PAYMENT", "2026-06-22"),
            ("PAY-004", "130000.00", None, "PAYMENT", "2026-06-24"),
            ("PAY-005", "-500.00", None, "FEE", "2026-06-30"),
        ]:
            yield (
                "payment",
                key,
                dict(
                    amount=amount,
                    account="RUB-01",
                    currency="RUB",
                    date=day,
                    document=document,
                    nature=nature,
                ),
            )
    else:
        yield (
            "rate",
            "USD-2026-06-10",
            dict(date="2026-06-10", currency="USD", rate="92.125"),
        )
        yield (
            "rate",
            "EUR-2026-06-10",
            dict(date="2026-06-10", currency="EUR", rate="103.20"),
        )
