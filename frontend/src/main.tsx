import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/600.css";
import "./styles.css";
import { useState } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter, NavLink, Route, Routes } from "react-router";
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
} from "@tanstack/react-query";
import {
  Activity,
  Archive,
  BookOpen,
  ChartNoAxesCombined,
  Database,
  FileStack,
  FlaskConical,
  GitCompare,
  Layers,
  LogOut,
  Settings,
  ShieldCheck,
  UsersRound,
} from "lucide-react";
import { api, read, session, type User } from "./data";
import { Compare, Finance, Metric, Reports, Snapshot } from "./finance";
import {
  Audit,
  Lab,
  Mapping,
  Quality,
  RawIndex,
  RawPage,
  RunPage,
  Runs,
  SourcePage,
  Sources,
  Users,
  Warehouse,
} from "./operations";
import { Brand, ErrorView, form, Heading, label } from "./ui";

const client = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 3000 } },
});
function Login({ done }: { done: (u: User) => void }) {
  const action = useMutation({
    mutationFn: (data: unknown) =>
      api<User & { token: string }>("/auth/login", "POST", data),
    onSuccess: (u) => {
      session(u.token);
      done(u);
    },
  });
  return (
    <div className="sign-in">
      <section>
        <Brand />
        <h1>Вход в Quantara</h1>
        <p>Рабочая область финансовых данных</p>
        <form className="form" onSubmit={(e) => action.mutate(form(e))}>
          <label>
            Логин
            <input name="login" autoComplete="username" required />
          </label>
          <label>
            Пароль
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              required
            />
          </label>
          <ErrorView error={action.error} />
          <button className="primary" disabled={action.isPending}>
            Войти
          </button>
        </form>
      </section>
      <div className="intro">
        <ChartNoAxesCombined size={50} />
        <h2>От первичной записи до отчёта</h2>
        <p>
          Объединяйте учебные данные ERP, банковских выписок и курсов.
          Проверяйте, из каких записей сложился показатель.
        </p>
      </div>
    </div>
  );
}
function App() {
  const [user, U] = useState<User | null>(null);
  if (!user) return <Login done={U} />;
  return (
    <Workspace
      user={user}
      logout={() => {
        session("");
        client.clear();
        U(null);
      }}
    />
  );
}
function Workspace({ user, logout }: { user: User; logout: () => void }) {
  const financial = ["ADMIN", "FINANCIAL_ANALYST", "DATA_ANALYST"].includes(
    user.role,
  );
  const data = user.role !== "FINANCIAL_ANALYST";
  const admin = user.role === "ADMIN";
  const lab = read<{ enabled: boolean; scenarios: Record<string, string> }>(
    "/lab",
    admin,
  );
  const nav = [
    ...(financial
      ? [
          { path: "/", title: "Финансовый обзор", Icon: ChartNoAxesCombined },
          { path: "/accrual", title: "Начисления", Icon: BookOpen },
          { path: "/cash", title: "Денежные потоки", Icon: Activity },
          { path: "/balances", title: "Задолженность", Icon: Layers },
          { path: "/budget", title: "План / факт", Icon: GitCompare },
          { path: "/reconciliation", title: "Сверка", Icon: ShieldCheck },
          { path: "/reports", title: "Отчётные снимки", Icon: FileStack },
          { path: "/scenarios", title: "Сценарии", Icon: FlaskConical },
        ]
      : []),
    { path: "/sources", title: "Источники", Icon: Database },
    { path: "/runs", title: "Мониторинг ETL", Icon: Activity },
    ...(data
      ? [
          { path: "/quality", title: "Качество", Icon: ShieldCheck },
          { path: "/quarantine", title: "Карантин", Icon: Archive },
          { path: "/warehouse", title: "Хранилище", Icon: Database },
          { path: "/raw", title: "Происхождение", Icon: Layers },
          { path: "/mapping", title: "Маппинг", Icon: Settings },
        ]
      : []),
    ...(admin
      ? [
          { path: "/audit", title: "Аудит", Icon: BookOpen },
          { path: "/users", title: "Пользователи", Icon: UsersRound },
        ]
      : []),
    ...(lab.data?.enabled
      ? [{ path: "/lab", title: "Лаборатория", Icon: FlaskConical }]
      : []),
  ];
  return (
    <div className="shell">
      <aside>
        <Brand />
        <nav aria-label="Разделы">
          {nav.map(({ path, title, Icon }) => (
            <NavLink key={path} to={path} end={path === "/"}>
              <Icon size={16} />
              {title}
            </NavLink>
          ))}
        </nav>
        <footer>Синтетические данные</footer>
      </aside>
      <div className="workspace">
        <header className="top">
          <span>Рабочая область / Финансы и данные</span>
          <div>
            <b>{user.name}</b>
            <span>{label(user.role)}</span>
            <button
              aria-label="Выйти"
              onClick={() =>
                void api("/auth/logout", "POST").then(logout, logout)
              }
            >
              <LogOut size={16} />
            </button>
          </div>
        </header>
        <main>
          <Routes>
            <Route
              path="/"
              element={
                financial ? (
                  <Finance section="overview" user={user} />
                ) : (
                  <Runs user={user} />
                )
              }
            />
            {financial && (
              <>
                {[
                  "accrual",
                  "cash",
                  "balances",
                  "budget",
                  "reconciliation",
                  "scenarios",
                ].map((section) => (
                  <Route
                    key={section}
                    path={"/" + section}
                    element={
                      <Finance key={section} section={section} user={user} />
                    }
                  />
                ))}
                <Route path="/reports" element={<Reports user={user} />} />
                <Route path="/reports/:id" element={<Snapshot />} />
                <Route path="/reports/:id/metric/:code" element={<Metric />} />
                <Route
                  path="/reports/:id/compare/:other"
                  element={<Compare />}
                />
              </>
            )}
            <Route path="/sources" element={<Sources />} />
            <Route path="/sources/:source" element={<SourcePage />} />
            <Route path="/runs" element={<Runs user={user} />} />
            <Route path="/runs/:id" element={<RunPage />} />
            <Route path="/raw/:id" element={<RawPage />} />
            {data && (
              <>
                <Route path="/quality" element={<Quality />} />
                <Route path="/quarantine" element={<Quality quarantine />} />
                <Route path="/warehouse" element={<Warehouse />} />
                <Route path="/raw" element={<RawIndex />} />
                <Route path="/mapping" element={<Mapping user={user} />} />
              </>
            )}
            {admin && (
              <>
                <Route path="/audit" element={<Audit />} />
                <Route path="/users" element={<Users />} />
              </>
            )}
            {lab.data?.enabled && (
              <Route
                path="/lab"
                element={<Lab scenarios={lab.data.scenarios} />}
              />
            )}
            <Route path="*" element={<Heading title="Раздел недоступен" />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={client}>
    <HashRouter>
      <App />
    </HashRouter>
  </QueryClientProvider>,
);
