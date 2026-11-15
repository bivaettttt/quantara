import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  api,
  read,
  useCommand,
  type Comparison,
  type Report,
  type ReportMeta,
  type User,
} from "./data";
import {
  Badge,
  ErrorView,
  form,
  Heading,
  Json,
  label,
  Load,
  Panel,
  rub,
  stamp,
  Table,
} from "./ui";

const groups: Record<string, { title: string; sub: string; codes: string[] }> =
  {
    overview: {
      title: "Финансовый обзор",
      sub: "Начисления, денежные потоки и качество выбранного снимка",
      codes: [
        "revenue",
        "expenses",
        "operating_result",
        "net_cash",
        "cash_balance",
        "receivables",
        "payables",
      ],
    },
    accrual: {
      title: "Начисления · P&L",
      sub: "Признанные счета покупателей и поставщиков",
      codes: ["revenue", "expenses", "operating_result"],
    },
    cash: {
      title: "Движение денежных средств",
      sub: "Поступления и выплаты по банковским датам",
      codes: ["cash_in", "cash_out", "net_cash", "cash_balance"],
    },
    balances: {
      title: "Дебиторская и кредиторская задолженность",
      sub: "Открытые суммы за вычетом сопоставленных платежей",
      codes: ["receivables", "payables"],
    },
    budget: {
      title: "План / факт",
      sub: "Расходы по начислению и месячные бюджеты в рублях",
      codes: ["budget_variance"],
    },
    reconciliation: {
      title: "Сверка",
      sub: "Расхождения банковских остатков и расчётов по документам",
      codes: [],
    },
    scenarios: {
      title: "Сценарный анализ",
      sub: "Гипотетическое изменение относительно сохранённого снимка",
      codes: [],
    },
  };

function snapshotList() {
  return read<ReportMeta[]>("/reports");
}
function SnapshotPicker({
  list,
  id,
  change,
}: {
  list: ReportMeta[];
  id: string;
  change: (s: string) => void;
}) {
  return (
    <label>
      Отчётный снимок
      <select value={id} onChange={(e) => change(e.target.value)}>
        {list.map((r) => (
          <option key={r.id} value={r.id}>
            {r.start_date} — {r.end_date} · {r.checksum.slice(0, 7)}
          </option>
        ))}
      </select>
    </label>
  );
}
function Amounts({ report, codes }: { report: Report; codes: string[] }) {
  return (
    <div className="metrics">
      {codes.map((k) => (
        <section key={k}>
          <span>{label(k)}</span>
          <strong>{rub(report.result.metrics[k].value)}</strong>
          <Link to={"/reports/" + report.id + "/metric/" + k}>
            Состав показателя
          </Link>
        </section>
      ))}
    </div>
  );
}
function Breakdown({ report }: { report: Report }) {
  return (
    <div className="split">
      {["revenue", "expenses"].map((key) => (
        <Panel
          key={key}
          title={key === "revenue" ? "Структура доходов" : "Структура расходов"}
        >
          <Table
            columns={["Категория", "Известная сумма"]}
            rows={Object.entries(report.result.breakdown[key]).map(([k, v]) => [
              k,
              rub(v),
            ])}
          />
        </Panel>
      ))}
    </div>
  );
}
export function Finance({ section, user }: { section: string; user: User }) {
  const snapshots = snapshotList(),
    [selected, set] = useState("");
  const latest = snapshots.isFetching ? undefined : snapshots.data?.[0]?.id;
  useEffect(() => {
    if (latest) set((current) => current || latest);
  }, [latest]);
  const id = selected || latest || "";
  const q = read<Report>("/reports/" + id, Boolean(id));
  const config = groups[section];
  return (
    <>
      <Heading title={config.title} sub={config.sub}>
        {snapshots.data?.length ? (
          <SnapshotPicker list={snapshots.data} id={id} change={set} />
        ) : null}
      </Heading>
      <ErrorView error={snapshots.error ?? q.error} />
      {q.data ? (
        <>
          <div className="report-strip">
            <span>
              {q.data.start_date} — {q.data.end_date}
            </span>
            <Badge value={q.data.quality} />
            <code>{q.data.checksum.slice(0, 12)}</code>
            <Link to={"/reports/" + q.data.id}>Открыть снимок</Link>
          </div>
          {config.codes.length > 0 && (
            <Amounts report={q.data} codes={config.codes} />
          )}
          {["overview", "accrual"].includes(section) && (
            <Breakdown report={q.data} />
          )}
          {section === "overview" && (
            <Panel title="Покрытие снимка">
              <Table
                columns={[
                  "Входные версии",
                  "Версия маппинга",
                  "Исключения",
                  "Недоступные источники",
                ]}
                rows={[
                  [
                    q.data.manifest.records.length,
                    q.data.manifest.mapping,
                    q.data.manifest.excluded.length,
                    q.data.manifest.unavailable.join(", ") || "—",
                  ],
                ]}
              />
            </Panel>
          )}
          {section === "cash" && <Reconcile report={q.data} bank />}
          {section === "balances" && <Reconcile report={q.data} open />}
          {section === "reconciliation" && <Reconcile report={q.data} />}
          {section === "budget" && (
            <Panel title="Бюджет по категориям">
              <Table
                columns={[
                  "Период",
                  "Категория",
                  "Факт",
                  "Бюджет",
                  "Отклонение",
                  "Выполнение",
                ]}
                rows={q.data.result.budget.map((r) => [
                  r.month,
                  r.category,
                  rub(r.actual),
                  rub(r.budget),
                  rub(r.variance),
                  r.performance === null ? "—" : r.performance + " %",
                ])}
              />
            </Panel>
          )}
          {section === "scenarios" && (
            <Scenario
              key={id}
              report={q.data}
              editable={user.role !== "DATA_ANALYST"}
            />
          )}
        </>
      ) : (
        !q.error &&
        (!snapshots.data || snapshots.isFetching || id ? (
          <Load />
        ) : (
          <Panel title="Снимки">
            <p className="pad muted">Сформируйте отчёт за нужный период.</p>
            <Link className="pad" to="/reports">
              Открыть отчёты
            </Link>
          </Panel>
        ))
      )}
    </>
  );
}
function Reconcile({
  report,
  bank = false,
  open = false,
}: {
  report: Report;
  bank?: boolean;
  open?: boolean;
}) {
  return (
    <Panel
      title={
        bank
          ? "Сверка банковского остатка"
          : open
            ? "Расчёты по документам"
            : "Результаты сверки"
      }
    >
      <Table
        columns={[
          "Объект",
          "Результат",
          "Ожидаемо",
          "Фактически",
          "Разница",
          "Источники",
        ]}
        rows={report.result.reconciliation
          .filter((x) =>
            bank
              ? x.code.startsWith("BANK") || x.code === "STATEMENT_MISSING"
              : open
                ? [
                    "PARTIAL_PAYMENT",
                    "OPEN_DOCUMENT",
                    "OVERPAYMENT",
                    "SETTLED",
                  ].includes(x.code)
                : true,
          )
          .map((r) => [
            r.object,
            label(r.code),
            rub(r.expected),
            rub(r.actual),
            rub(r.difference),
            r.raw.map((id) => (
              <Link key={id} className="inline" to={"/raw/" + id}>
                #{id}
              </Link>
            )),
          ])}
      />
    </Panel>
  );
}
function Scenario({ report, editable }: { report: Report; editable: boolean }) {
  const path = "/reports/" + report.id + "/scenarios";
  const act = useCommand<{
    id: string;
    result: Record<string, string | null>;
  }>();
  const history =
    read<
      { id: string; created: string; assumptions: unknown; result: unknown }[]
    >(path);
  return (
    <>
      <Panel title="Гипотетические допущения">
        {editable ? (
          <form
            className="pad toolbar"
            onSubmit={(e) =>
              act.mutate({
                path,
                data: Object.fromEntries(
                  Object.entries(form(e)).map(([k, v]) => [k, Number(v)]),
                ),
              })
            }
          >
            {[
              ["revenue_percent", "Выручка, %"],
              ["expense_percent", "Расходы, %"],
              ["cash_in_percent", "Поступления, %"],
            ].map(([k, n]) => (
              <label key={k}>
                {n}
                <input
                  name={k}
                  type="number"
                  min={-100}
                  max={200}
                  defaultValue={0}
                  required
                />
              </label>
            ))}
            <button className="primary" disabled={act.isPending}>
              Рассчитать сценарий
            </button>
          </form>
        ) : null}
        <ErrorView error={act.error} />
      </Panel>
      {act.data && (
        <Panel title="Результат сценария">
          <Table
            columns={["Показатель", "Факт", "Гипотеза"]}
            rows={Object.entries(act.data.result).map(([k, v]) => [
              label(k),
              rub(report.result.metrics[k].value),
              rub(v),
            ])}
          />
        </Panel>
      )}
      <Panel title="Сохранённые сценарии">
        <Table
          columns={["Создан UTC", "Допущения и результат"]}
          rows={(history.data ?? []).map((s) => [
            stamp(s.created),
            <details>
              <summary>{s.id.slice(0, 8)}</summary>
              <Json data={{ assumptions: s.assumptions, result: s.result }} />
            </details>,
          ])}
        />
      </Panel>
    </>
  );
}
export function Reports({ user }: { user: User }) {
  const rows = read<ReportMeta[]>("/reports");
  const act = useCommand<Report>();
  const navigate = useNavigate();
  const [left, L] = useState(""),
    [right, R] = useState("");
  const pair = left && right && left !== right;
  return (
    <>
      <Heading
        title="Отчётные снимки"
        sub="Фиксированные входные версии, расчёты и контрольные суммы"
      />
      {user.role !== "DATA_ANALYST" && (
        <Panel title="Новый отчёт">
          <form
            className="pad toolbar"
            onSubmit={(e) =>
              act.mutate(
                { path: "/reports", data: form(e) },
                { onSuccess: (r) => navigate("/reports/" + r.id) },
              )
            }
          >
            <label>
              Начало
              <input
                name="start"
                type="date"
                defaultValue="2026-06-01"
                required
              />
            </label>
            <label>
              Конец
              <input
                name="end"
                type="date"
                defaultValue="2026-06-30"
                required
              />
            </label>
            <button className="primary" disabled={act.isPending}>
              Сформировать
            </button>
          </form>
          <ErrorView error={act.error} />
        </Panel>
      )}
      <Panel title="Сравнить версии">
        <div className="pad toolbar">
          {[
            ["Старый снимок", left, L],
            ["Новый снимок", right, R],
          ].map(([title, value, fn]) => (
            <label key={String(title)}>
              {String(title)}
              <select
                value={String(value)}
                onChange={(e) => (fn as (s: string) => void)(e.target.value)}
              >
                <option value="">Выберите снимок</option>
                {rows.data?.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.checksum.slice(0, 8)} · {r.start_date} — {r.end_date}
                  </option>
                ))}
              </select>
            </label>
          ))}
          {pair && (
            <Link
              className="button"
              to={"/reports/" + left + "/compare/" + right}
            >
              Сравнить
            </Link>
          )}
        </div>
      </Panel>
      <Panel title="История снимков">
        {rows.data ? (
          <Table
            columns={[
              "Контрольная сумма",
              "Период",
              "Качество",
              "Методика",
              "Создан UTC",
            ]}
            rows={rows.data.map((r) => [
              <Link to={"/reports/" + r.id}>{r.checksum.slice(0, 12)}</Link>,
              r.start_date + " — " + r.end_date,
              <Badge value={r.quality} />,
              r.method,
              stamp(r.created),
            ])}
          />
        ) : (
          <Load error={rows.error} />
        )}
      </Panel>
    </>
  );
}
export function Snapshot() {
  const { id } = useParams();
  const q = read<Report>("/reports/" + id);
  const [error, set] = useState<Error>();
  if (!q.data) return <Load error={q.error} />;
  const r = q.data;
  async function download() {
    try {
      const csv = await api<string>("/reports/" + id + "/export");
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "quantara-report.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      set(e instanceof Error ? e : Error(String(e)));
    }
  }
  return (
    <>
      <Link to="/reports">← Отчётные снимки</Link>
      <Heading
        title="Финансовый снимок"
        sub={r.start_date + " — " + r.end_date + " · " + r.method}
      >
        <button onClick={() => void download()}>Скачать CSV</button>
      </Heading>
      <ErrorView error={error} />
      <div className="report-strip">
        <Badge value={r.quality} />
        <code>{r.checksum}</code>
      </div>
      <Panel title="Сохранённые показатели">
        <Table
          columns={["Показатель", "Значение", "Известная часть", "Исключения"]}
          rows={Object.entries(r.result.metrics).map(([k, m]) => [
            <Link to={"/reports/" + r.id + "/metric/" + k}>{label(k)}</Link>,
            rub(m.value),
            rub(m.known),
            m.excluded.length,
          ])}
        />
      </Panel>
      <Panel title="Манифест">
        <details>
          <summary>Входные версии и правила</summary>
          <Json data={r.manifest} />
        </details>
      </Panel>
    </>
  );
}
export function Metric() {
  const { id, code } = useParams();
  const q = read<Report>("/reports/" + id);
  const registry = read<{ code: string; formula: string }[]>("/kpis");
  if (!q.data) return <Load error={q.error} />;
  const m = q.data.result.metrics[code ?? ""];
  if (!m) return <Heading title="Показатель отсутствует" />;
  return (
    <>
      <Link to={"/reports/" + id}>← Отчётный снимок</Link>
      <Heading
        title={label(code ?? "")}
        sub={registry.data?.find((r) => r.code === code)?.formula}
      >
        <Badge value={q.data.quality} />
      </Heading>
      <div className="report-strip">
        <strong>{rub(m.value)}</strong>
        <span>Известная часть {rub(m.known)}</span>
        <span>Методика {q.data.method}</span>
      </div>
      <Panel title="Происхождение показателя">
        <Table
          columns={[
            "Запись",
            "Источник",
            "Ревизия",
            "Маппинг",
            "Загрузка",
            "FX",
            "Вклад",
          ]}
          rows={m.contributions.map((e) => [
            <div>
              <Link to={"/raw/" + e.raw}>{e.external_id ?? "#" + e.raw}</Link>
              {e.related_raw?.length ? (
                <div>
                  Платежи{" "}
                  {e.related_raw.map((id) => (
                    <Link className="inline" key={id} to={"/raw/" + id}>
                      #{id}
                    </Link>
                  ))}
                </div>
              ) : null}
            </div>,
            e.source ?? "ERP",
            e.revision ?? "—",
            e.mapping ?? "—",
            e.run ? (
              <Link to={"/runs/" + e.run}>{e.run.slice(0, 8)}</Link>
            ) : (
              "—"
            ),
            e.fx_raw ? <Link to={"/raw/" + e.fx_raw}>#{e.fx_raw}</Link> : "—",
            rub(e.amount),
          ])}
        />
      </Panel>
      {m.excluded.length > 0 && (
        <Panel title="Исключённые записи">
          <div className="pad toolbar">
            {m.excluded.map((id) => (
              <Link key={id} to={"/raw/" + id}>
                #{id}
              </Link>
            ))}
          </div>
        </Panel>
      )}
    </>
  );
}
export function Compare() {
  const { id, other } = useParams();
  const c = read<Comparison>("/reports/" + id + "/compare/" + other);
  const rawLink = (r: Comparison["changed"][number]["before"]): ReactNode =>
    r ? (
      <Link to={"/raw/" + r.raw}>
        #{r.raw} · v{r.revision}
      </Link>
    ) : (
      "—"
    );
  return (
    <>
      <Link to="/reports">← Отчётные снимки</Link>
      <Heading
        title="Сравнение снимков"
        sub="Значения, изменения входных записей и качество"
      />
      {c.data ? (
        <>
          <Panel title="Влияние на показатели">
            <Table
              columns={["Показатель", "Было", "Стало", "Разница", "Отклонение"]}
              rows={c.data.metrics.map((x) => [
                label(x.code),
                rub(x.before),
                rub(x.after),
                rub(x.delta),
                x.percent === null ? "—" : x.percent + " %",
              ])}
            />
          </Panel>
          <Panel title="Изменившиеся записи">
            <Table
              columns={["Источник", "Сущность", "Ключ", "Было", "Стало"]}
              rows={c.data.changed.map((x) => [
                x.source,
                label(x.entity),
                x.external_id,
                rawLink(x.before),
                rawLink(x.after),
              ])}
            />
          </Panel>
          <Panel title="Изменения качества">
            <details>
              <summary>Источники и исключения</summary>
              <Json data={c.data.quality_changes} />
            </details>
          </Panel>
        </>
      ) : (
        <Load error={c.error} />
      )}
    </>
  );
}
