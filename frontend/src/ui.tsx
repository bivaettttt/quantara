import type { FormEvent, ReactNode } from "react";
import { ChartNoAxesCombined } from "lucide-react";
export const labels: Record<string, string> = {
  revenue: "Выручка по начислению",
  expenses: "Расходы по начислению",
  operating_result: "Операционный результат",
  cash_in: "Денежные поступления",
  cash_out: "Денежные выплаты",
  net_cash: "Чистый денежный поток",
  cash_balance: "Конечный остаток",
  receivables: "Дебиторская задолженность",
  payables: "Кредиторская задолженность",
  budget_variance: "Отклонение от бюджета",
  FINANCIAL_ANALYST: "Финансовый аналитик",
  DATA_ANALYST: "Аналитик данных",
  DATA_ENGINEER: "Инженер данных",
  DATA_STEWARD: "Куратор данных",
  ADMIN: "Администратор",
  COMPLETE: "Полный",
  PARTIAL: "Частичный",
  SUCCESS: "Успешно",
  FAILED: "Ошибка",
  READY: "Актуален",
  UNAVAILABLE: "Недоступен",
  STALE: "Устарел",
  BANK_MATCH: "Остаток сходится",
  BANK_MISMATCH: "Расхождение остатка",
  UNMATCHED_PAYMENT: "Платёж без соответствия",
  PARTIAL_PAYMENT: "Частичная оплата",
  OPEN_DOCUMENT: "Открытый документ",
  SETTLED: "Сопоставлено",
  invoice: "Счета",
  payment: "Платежи",
  budget: "Бюджет",
  statement: "Выписка",
  partner: "Контрагенты",
  account: "Счета банка",
  rate: "Курсы",
};
export const label = (value: string) => labels[value] ?? value;
export const rub = (value: string | null | undefined) => {
  if (value == null) return "—";
  const [whole, fraction = "00"] = String(value).split(".");
  return (
    whole.replace(/\B(?=(\d{3})+(?!\d))/g, "\u202f") +
    "," +
    fraction.padEnd(2, "0") +
    " ₽"
  );
};
export const stamp = (s: string | null | undefined) =>
  s
    ? new Intl.DateTimeFormat("ru", {
        dateStyle: "short",
        timeStyle: "short",
        timeZone: "UTC",
      }).format(new Date(s))
    : "—";
export const form = (e: FormEvent<HTMLFormElement>) => {
  e.preventDefault();
  return Object.fromEntries(new FormData(e.currentTarget));
};
export function Badge({ value }: { value: string }) {
  return <span className={"badge " + value.toLowerCase()}>{label(value)}</span>;
}
export function ErrorView({ error }: { error?: Error | null }) {
  return error ? (
    <p className="error" role="alert">
      {error.message}
    </p>
  ) : null;
}
export function Load({ error }: { error?: Error | null }) {
  return error ? (
    <ErrorView error={error} />
  ) : (
    <p className="pad muted" role="status">
      Загрузка…
    </p>
  );
}
export function Heading({
  title,
  sub,
  children,
}: {
  title: string;
  sub?: string;
  children?: ReactNode;
}) {
  return (
    <header className="headline">
      <div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {children}
    </header>
  );
}
export function Panel({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}
export function Table({
  columns,
  rows,
  empty = "Записей пока нет.",
}: {
  columns: string[];
  rows: ReactNode[][];
  empty?: string;
}) {
  return rows.length ? (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((v, j) => (
                <td key={j}>{v}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="pad muted">{empty}</p>
  );
}
export function Pager({
  offset,
  count,
  onChange,
}: {
  offset: number;
  count: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="pad toolbar">
      <button disabled={!offset} onClick={() => onChange(offset - 50)}>
        Назад
      </button>
      <span className="muted">Страница {offset / 50 + 1}</span>
      <button disabled={count < 50} onClick={() => onChange(offset + 50)}>
        Далее
      </button>
    </div>
  );
}
export function Json({ data }: { data: unknown }) {
  return <pre>{JSON.stringify(data, null, 2)}</pre>;
}
export function Brand() {
  return (
    <div className="brand">
      <span>
        <ChartNoAxesCombined size={23} />
      </span>
      Quantara
    </div>
  );
}
