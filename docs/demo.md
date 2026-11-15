# Quantara demo / Демонстрация

1. Запустите `scripts/lab up` и войдите как `admin`. В финансовом обзоре откройте выручку. Выберите сумму по INV-101, затем проверьте исходный счёт, версию маппинга, загрузку и датированный USD-курс.
2. В лаборатории выполните «Исправление источника» и нажмите «Сравнить снимки». Выручка увеличится на 1 500 ₽ между двумя версиями одной записи. Старый снимок сохраняет собственную контрольную сумму.
3. Запустите «Отсутствующий курс» с флажком «Оставить ошибку для разбора». Проверьте карантин и неизвестную выручку при доступной известной части. Запустите лабораторию заново через её reset, если требуется исходный набор.
4. Для технического интервью выполните «Сбой внутри ETL» и «Конкурентный ETL». Сопоставьте даты, курсоры, журналы запуска и итоговые контрольные суммы.

| Экран | Снимок |
| --- | --- |
| Финансовый обзор | [Dashboard](../assets/screenshots/dashboard.png) |
| Начисления | [P&L](../assets/screenshots/accrual.png) |
| Денежный поток | [Cash flow](../assets/screenshots/cash.png) |
| План и факт | [Budget](../assets/screenshots/budget.png) |
| Источники | [Sources](../assets/screenshots/sources.png) |
| Конвейер | [ETL monitor](../assets/screenshots/etl.png) |
| Загрузка | [Run details](../assets/screenshots/run.png) |
| Качество | [Quality](../assets/screenshots/quality.png) |
| Карантин | [Quarantine](../assets/screenshots/quarantine.png) |
| Сверка | [Reconciliation](../assets/screenshots/reconciliation.png) |
| Происхождение записи | [Lineage](../assets/screenshots/lineage.png) |
| Детализация показателя | [KPI](../assets/screenshots/kpi.png) |
| Отчётные снимки | [Snapshots](../assets/screenshots/reports.png) |
| Сравнение снимков | [Comparison](../assets/screenshots/comparison.png) |
| Сценарный расчёт | [Scenario](../assets/screenshots/scenario.png) |
| Лаборатория | [Lab](../assets/screenshots/lab.png) |

[Видеозапись работы системы](../assets/demo/quantara.mp4). Запись сделана из браузерных проверок с реальными состояниями локальной лаборатории.
