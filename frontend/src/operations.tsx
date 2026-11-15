import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import {
  read,
  useCommand,
  type Fact,
  type Issue,
  type Raw,
  type Run,
  type Source,
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
  Pager,
  Panel,
  rub,
  stamp,
  Table,
} from "./ui";

export function Sources() {
  const q = read<Source[]>("/sources");
  return (
    <>
      <Heading
        title="Источники данных"
        sub="Независимые REST-потоки и состояние контрольных точек"
      />
      <Panel title="Реестр источников">
        {q.data ? (
          <Table
            columns={[
              "Источник",
              "Статус",
              "Курсор",
              "Последняя загрузка UTC",
              "Ошибка",
            ]}
            rows={q.data.map((s) => [
              <Link to={"/sources/" + s.source}>{s.source.toUpperCase()}</Link>,
              <Badge value={s.status} />,
              s.sequence,
              stamp(s.last_success),
              s.last_error ?? "—",
            ])}
          />
        ) : (
          <Load error={q.error} />
        )}
      </Panel>
    </>
  );
}
export function SourcePage() {
  const { source } = useParams();
  const q = read<Source[]>("/sources"),
    history = read<Run[]>("/runs");
  const item = q.data?.find((s) => s.source === source);
  return (
    <>
      <Link to="/sources">← Источники</Link>
      <Heading
        title={"Источник " + source?.toUpperCase()}
        sub="Контрольная точка и история доставки"
      />
      {item ? (
        <div className="report-strip">
          <Badge value={item.status} />
          <span>Курсор {item.sequence}</span>
          <span>{stamp(item.last_success)} UTC</span>
        </div>
      ) : (
        <Load error={q.error} />
      )}
      <Panel title="Запуски источника">
        <Table
          columns={["Запуск", "Получено", "До курсора", "Состояние"]}
          rows={(history.data ?? [])
            .filter((x) => x.summary.sources?.[source ?? ""])
            .map((x) => {
              const count = x.summary.sources![source!];
              return [
                <Link to={"/runs/" + x.id}>{x.id.slice(0, 8)}</Link>,
                count.received,
                count.end_cursor,
                count.error ?? label(x.status),
              ];
            })}
        />
      </Panel>
    </>
  );
}
export function Runs({ user }: { user: User }) {
  const [offset, setOffset] = useState(0);
  const q = read<Run[]>("/runs?offset=" + offset);
  const act = useCommand<Run>();
  const [upload, U] = useState(false);
  const canRun = ["ADMIN", "DATA_ENGINEER", "DATA_STEWARD"].includes(user.role);
  return (
    <>
      <Heading
        title="Мониторинг ETL"
        sub="Версии доставки, курсоры и результаты обработки"
      >
        {["ADMIN", "DATA_ENGINEER"].includes(user.role) && (
          <button onClick={() => U(!upload)}>Импорт CSV</button>
        )}
      </Heading>
      {canRun && (
        <Panel title="Запуск конвейера">
          <form
            className="pad toolbar"
            onSubmit={(e) => act.mutate({ path: "/runs?mode=" + form(e).mode })}
          >
            <label>
              Режим
              <select name="mode">
                <option value="incremental">Инкрементальный</option>
                <option value="full">Повтор всех страниц</option>
                <option value="reprocess">Пересобрать из raw</option>
              </select>
            </label>
            <button className="primary" disabled={act.isPending}>
              Запустить ETL
            </button>
          </form>
          <ErrorView error={act.error} />
          {act.data && (
            <p className="pad" role="status">
              <Badge value={act.data.status} />{" "}
              <Link to={"/runs/" + act.data.id}>Открыть запуск</Link>
            </p>
          )}
        </Panel>
      )}
      {upload && (
        <Panel title="Импорт банковских событий">
          <form
            className="pad toolbar"
            onSubmit={async (e) => {
              const f = form(e).file;
              if (f instanceof File)
                act.mutate({ path: "/import", data: { text: await f.text() } });
            }}
          >
            <label>
              Файл CSV
              <input type="file" name="file" accept=".csv,text/csv" required />
            </label>
            <button disabled={act.isPending}>Загрузить</button>
          </form>
        </Panel>
      )}
      <Panel title="Журнал загрузок">
        {q.data ? (
          <>
            <Table
              columns={[
                "Запуск",
                "Режим",
                "Статус",
                "Получено",
                "Карантин",
                "Начало UTC",
              ]}
              rows={q.data.map((r) => [
                <Link to={"/runs/" + r.id}>{r.id.slice(0, 8)}</Link>,
                r.mode,
                <Badge value={r.status} />,
                Object.values(r.summary.sources ?? {}).reduce(
                  (total, s) => total + s.received,
                  0,
                ),
                r.summary.quarantined ?? "—",
                stamp(r.started),
              ])}
            />
            <Pager offset={offset} count={q.data.length} onChange={setOffset} />
          </>
        ) : (
          <Load error={q.error} />
        )}
      </Panel>
    </>
  );
}
function Issues({ items }: { items: Issue[] }) {
  return (
    <Table
      columns={[
        "Источник",
        "Измерение",
        "Диагностика",
        "Raw",
        "Запуск",
        "Время UTC",
      ]}
      rows={items.map((i) => [
        i.source,
        i.dimension,
        i.code,
        i.raw ? <Link to={"/raw/" + i.raw}>#{i.raw}</Link> : "—",
        <Link to={"/runs/" + i.run}>{i.run.slice(0, 8)}</Link>,
        stamp(i.created),
      ])}
    />
  );
}
export function RunPage() {
  const { id } = useParams();
  const q = read<Run>("/runs/" + id);
  if (!q.data) return <Load error={q.error} />;
  const r = q.data;
  return (
    <>
      <Link to="/runs">← Мониторинг ETL</Link>
      <Heading
        title={"Запуск " + r.id.slice(0, 8)}
        sub={r.mode + " · " + stamp(r.started) + " UTC"}
      >
        <Badge value={r.status} />
      </Heading>
      <div className="report-strip">
        <span>Correlation ID</span>
        <code>{r.request}</code>
      </div>
      <Panel title="Результаты по источникам">
        <Table
          columns={[
            "Источник",
            "Получено",
            "Принято в raw",
            "Повторы",
            "Отклонено",
            "Курсор",
            "Ошибка",
          ]}
          rows={Object.entries(r.summary.sources ?? {}).map(([k, s]) => [
            k,
            s.received,
            s.accepted,
            s.duplicates,
            s.rejected,
            s.start_cursor + " → " + s.end_cursor,
            s.error ?? "—",
          ])}
        />
        {r.summary.error && <p className="pad error">{r.summary.error}</p>}
      </Panel>
      <Panel title="Диагностика качества">
        <Issues items={r.issues ?? []} />
      </Panel>
    </>
  );
}
export function Quality({ quarantine = false }: { quarantine?: boolean }) {
  const [offset, set] = useState(0);
  const q = read<Issue[]>(
    quarantine ? "" : "/quality?offset=" + offset,
    !quarantine,
  );
  const rows = read<
    {
      id: number;
      source: string;
      entity: string;
      external_id: string;
      revision: number;
      reason: string;
      mapping: number;
    }[]
  >(quarantine ? "/quarantine?offset=" + offset : "", quarantine);
  return (
    <>
      <Heading
        title={quarantine ? "Карантин" : "Качество данных"}
        sub={
          quarantine
            ? "Последние непригодные версии и причины исключения"
            : "Диагностика измерений качества по запускам"
        }
      />
      {quarantine ? (
        <Panel title="Отклонённые записи">
          {rows.data ? (
            <>
              <Table
                columns={[
                  "Источник",
                  "Сущность",
                  "Запись",
                  "Версия",
                  "Маппинг",
                  "Причина",
                ]}
                rows={rows.data.map((x) => [
                  x.source,
                  label(x.entity),
                  <Link to={"/raw/" + x.id}>{x.external_id}</Link>,
                  x.revision,
                  x.mapping,
                  x.reason,
                ])}
              />
              <Pager offset={offset} count={rows.data.length} onChange={set} />
            </>
          ) : (
            <Load error={rows.error} />
          )}
        </Panel>
      ) : (
        <Panel title="Журнал проверок">
          {q.data ? (
            <>
              <Issues items={q.data} />
              <Pager offset={offset} count={q.data.length} onChange={set} />
            </>
          ) : (
            <Load error={q.error} />
          )}
        </Panel>
      )}
    </>
  );
}
export function Warehouse() {
  const [offset, set] = useState(0),
    [entity, E] = useState("");
  const q = read<Fact[]>(
    "/warehouse?offset=" + offset + (entity ? "&entity=" + entity : ""),
  );
  return (
    <>
      <Heading
        title="Хранилище"
        sub="Типизированная проекция последних пригодных версий"
      />
      <Panel title="Факты и измерения">
        <div className="pad toolbar">
          <label>
            Сущность
            <select
              value={entity}
              onChange={(e) => {
                E(e.target.value);
                set(0);
              }}
            >
              <option value="">Все записи</option>
              {[
                "invoice",
                "payment",
                "budget",
                "statement",
                "account",
                "partner",
                "rate",
              ].map((e) => (
                <option key={e} value={e}>
                  {label(e)}
                </option>
              ))}
            </select>
          </label>
        </div>
        {q.data ? (
          <>
            <Table
              columns={[
                "Запись",
                "Сущность",
                "Бизнес-дата",
                "Категория",
                "Сумма",
                "Валюта",
                "Ревизия",
              ]}
              rows={q.data.map((x) => [
                <Link to={"/raw/" + x.raw}>{x.external_id}</Link>,
                label(x.entity),
                x.business_date ?? "—",
                x.category ?? "—",
                x.currency === "RUB" ? rub(x.amount) : (x.amount ?? "—"),
                x.currency ?? "—",
                x.revision,
              ])}
            />
            <Pager offset={offset} count={q.data.length} onChange={set} />
          </>
        ) : (
          <Load error={q.error} />
        )}
      </Panel>
    </>
  );
}
export function RawIndex() {
  const [params, set] = useSearchParams(),
    [offset, O] = useState(0);
  const q = read<Raw[]>(
    "/raw?offset=" + offset + "&q=" + encodeURIComponent(params.get("q") ?? ""),
  );
  return (
    <>
      <Heading
        title="Происхождение данных"
        sub="Исходные версии, загрузка и статус исходной записи"
      />
      <Panel title="Неизменяемый слой raw">
        <form
          className="pad toolbar"
          onSubmit={(e) => {
            set({ q: String(form(e).q) });
            O(0);
          }}
        >
          <label>
            Внешний ключ
            <input name="q" defaultValue={params.get("q") ?? ""} />
          </label>
          <button>Найти</button>
        </form>
        {q.data ? (
          <>
            <Table
              columns={[
                "Ключ",
                "Источник",
                "Сущность",
                "Ревизия",
                "Статус",
                "Получено UTC",
              ]}
              rows={q.data.map((x) => [
                <Link to={"/raw/" + x.id}>{x.external_id}</Link>,
                x.source,
                label(x.entity),
                x.revision,
                x.disposition,
                stamp(x.received),
              ])}
            />
            <Pager offset={offset} count={q.data.length} onChange={O} />
          </>
        ) : (
          <Load error={q.error} />
        )}
      </Panel>
    </>
  );
}
export function RawPage() {
  const { id } = useParams();
  const q = read<Raw>("/raw/" + id);
  if (!q.data) return <Load error={q.error} />;
  const x = q.data;
  return (
    <>
      <Heading
        title={x.external_id}
        sub={
          x.source.toUpperCase() +
          " · " +
          label(x.entity) +
          " · версия " +
          x.revision
        }
      />
      <div className="report-strip">
        <Link to={"/runs/" + x.run}>Загрузка {x.run.slice(0, 8)}</Link>
        <span>Raw #{x.id}</span>
        <Badge value={x.disposition} />
        <code>{x.hash.slice(0, 16)}</code>
      </div>
      <div className="split">
        <Panel title="Исходная запись">
          <Json data={x.payload} />
        </Panel>
        <Panel title="Нормализация">
          <Json data={x.stage} />
        </Panel>
      </div>
      <Panel title="Проверки записи">
        <Issues items={x.issues} />
      </Panel>
    </>
  );
}
export function Mapping({ user }: { user: User }) {
  const q = read<
    {
      version: number;
      aliases: Record<string, string>;
      actor: string;
      created: string;
    }[]
  >("/mapping");
  const act = useCommand<Run>();
  return (
    <>
      <Heading
        title="Версии маппинга"
        sub="Управляемое сопоставление категорий ERP"
      />
      {["ADMIN", "DATA_STEWARD"].includes(user.role) && (
        <Panel title="Опубликовать переименование">
          <form
            className="pad toolbar"
            onSubmit={(e) => {
              const f = form(e);
              act.mutate({
                path: "/mapping",
                data: {
                  aliases: {
                    ...(q.data?.[0]?.aliases ?? {}),
                    [String(f.source)]: f.target,
                  },
                },
              });
            }}
          >
            <label>
              Исходная категория
              <input name="source" required maxLength={120} />
            </label>
            <label>
              Целевая категория
              <input name="target" required maxLength={120} />
            </label>
            <button className="primary" disabled={act.isPending}>
              Опубликовать
            </button>
          </form>
          <ErrorView error={act.error} />
        </Panel>
      )}
      <Panel title="История">
        {q.data ? (
          <Table
            columns={["Версия", "Автор", "Правила", "Дата UTC"]}
            rows={q.data.map((x) => [
              x.version,
              x.actor ?? "—",
              <Json data={x.aliases} />,
              stamp(x.created),
            ])}
          />
        ) : (
          <Load error={q.error} />
        )}
      </Panel>
    </>
  );
}
export function Audit() {
  const q = read<
    {
      id: number;
      actor: string;
      action: string;
      request: string;
      subject: string;
      created: string;
      detail: unknown;
    }[]
  >("/audit");
  return (
    <>
      <Heading title="Аудит" />
      <Panel title="Журнал действий">
        {q.data ? (
          <Table
            columns={["Действие", "Автор", "Объект", "Дата UTC", "Детали"]}
            rows={q.data.map((x) => [
              x.action,
              x.actor,
              x.subject,
              stamp(x.created),
              <details>
                <summary>{x.request.slice(0, 10)}</summary>
                <Json data={x.detail} />
              </details>,
            ])}
          />
        ) : (
          <Load error={q.error} />
        )}
      </Panel>
    </>
  );
}
export function Users() {
  const q = read<User[]>("/users"),
    act = useCommand<User>();
  return (
    <>
      <Heading title="Пользователи" />
      <Panel title="Учётные записи">
        {q.data ? (
          <Table
            columns={["Логин", "Имя", "Роль"]}
            rows={q.data.map((u) => [u.login, u.name, label(u.role)])}
          />
        ) : (
          <Load error={q.error} />
        )}
      </Panel>
      <Panel title="Создать пользователя">
        <form
          className="pad form"
          onSubmit={(e) => act.mutate({ path: "/users", data: form(e) })}
        >
          <label>
            Логин
            <input name="login" required />
          </label>
          <label>
            Имя
            <input name="name" required minLength={2} />
          </label>
          <label>
            Пароль
            <input name="password" type="password" required minLength={12} />
          </label>
          <label>
            Роль
            <select name="role">
              {[
                "FINANCIAL_ANALYST",
                "DATA_ANALYST",
                "DATA_ENGINEER",
                "DATA_STEWARD",
                "ADMIN",
              ].map((r) => (
                <option key={r} value={r}>
                  {label(r)}
                </option>
              ))}
            </select>
          </label>
          <button className="primary" disabled={act.isPending}>
            Создать
          </button>
        </form>
        <ErrorView error={act.error} />
      </Panel>
    </>
  );
}
export function Lab({ scenarios }: { scenarios: Record<string, string> }) {
  const act = useCommand<{
    passed: boolean;
    checks: Record<string, boolean>;
    trace: unknown;
    before: { id: string };
    after: { id: string };
  }>();
  return (
    <>
      <Heading
        title="Quantara Lab"
        sub="Эксперименты с независимыми источниками и отдельным PostgreSQL"
      />
      <Panel title="Сценарий">
        <form
          className="pad toolbar"
          onSubmit={(e) => {
            const selection = form(e);
            act.mutate({
              path:
                "/lab/" +
                selection.scenario +
                (selection.keep_issue ? "?keep_issue=true" : ""),
            });
          }}
        >
          <label>
            Эксперимент
            <select name="scenario">
              {Object.entries(scenarios).map(([id, n]) => (
                <option key={id} value={id}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className="check">
            <input type="checkbox" name="keep_issue" /> Оставить ошибку для
            разбора
          </label>
          <button className="primary" disabled={act.isPending}>
            Запустить сценарий
          </button>
        </form>
        <ErrorView error={act.error} />
      </Panel>
      {act.data && (
        <Panel
          title={act.data.passed ? "Проверка пройдена" : "Проверка не пройдена"}
        >
          <Table
            columns={["Инвариант", "Результат"]}
            rows={Object.entries(act.data.checks).map(([code, v]) => [
              code,
              v ? "OK" : "Ошибка",
            ])}
          />
          <div className="pad toolbar">
            <Link to={"/reports/" + act.data.before.id}>Снимок до</Link>
            <Link to={"/reports/" + act.data.after.id}>Снимок после</Link>
            {act.data.before.id !== act.data.after.id && (
              <Link
                to={
                  "/reports/" +
                  act.data.before.id +
                  "/compare/" +
                  act.data.after.id
                }
              >
                Сравнить снимки
              </Link>
            )}
          </div>
          <details>
            <summary>Запросы и ответы</summary>
            <Json data={act.data.trace} />
          </details>
        </Panel>
      )}
    </>
  );
}
