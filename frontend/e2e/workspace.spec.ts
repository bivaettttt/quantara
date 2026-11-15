import { expect, test, type Page } from "@playwright/test";
const password = process.env.QUANTARA_DEMO_PASSWORD ?? "Quantara-local-demo";
async function login(page: Page, who: string) {
  await page.getByRole("textbox", { name: "Логин" }).fill(who);
  await page.getByLabel("Пароль").fill(password);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByRole("button", { name: "Выйти" })).toBeVisible({
    timeout: 15000,
  });
}
async function nav(page: Page, name: string) {
  await page
    .getByRole("navigation")
    .getByRole("link", { name, exact: true })
    .click();
}
async function shot(page: Page, name: string) {
  if (!process.env.QUANTARA_SHOTS) return;
  await page.evaluate(() => document.fonts.ready);
  await page.mouse.move(3, 3);
  await page.screenshot({
    path: process.env.QUANTARA_SHOTS + "/" + name + ".png",
  });
}
async function lab(page: Page, scenario: string, keepIssue = false) {
  await nav(page, "Лаборатория");
  await page
    .getByRole("combobox", { name: "Эксперимент" })
    .selectOption(scenario);
  if (keepIssue)
    await page
      .getByRole("checkbox", { name: "Оставить ошибку для разбора" })
      .check();
  await page.getByRole("button", { name: "Запустить сценарий" }).click();
  await expect(
    page.getByRole("heading", { name: "Проверка пройдена" }),
  ).toBeVisible({ timeout: 12000 });
}

test("immutable report drills into raw and FX, then a source correction explains the difference", async ({
  page,
}) => {
  await page.goto("/");
  await shot(page, "login");
  await login(page, "admin");
  await expect(
    page.getByText("Выручка по начислению", { exact: true }).first(),
  ).toBeVisible();
  await shot(page, "dashboard");
  await nav(page, "Начисления");
  await expect(
    page.getByRole("heading", { name: "Структура доходов" }),
  ).toBeVisible();
  await shot(page, "accrual");
  await page
    .locator(".metrics section")
    .filter({ hasText: "Выручка по начислению" })
    .getByRole("link")
    .click();
  await expect(
    page.getByRole("link", { name: "INV-101", exact: true }),
  ).toBeVisible();
  await shot(page, "kpi");
  await page.getByRole("link", { name: "INV-101", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Исходная запись" }),
  ).toBeVisible();
  await shot(page, "lineage");
  await nav(page, "Денежные потоки");
  await expect(
    page.getByRole("heading", { name: "Сверка банковского остатка" }),
  ).toBeVisible();
  await shot(page, "cash");
  await nav(page, "План / факт");
  await expect(
    page.getByRole("heading", { name: "Бюджет по категориям" }),
  ).toBeVisible();
  await shot(page, "budget");
  await nav(page, "Сверка");
  await expect(
    page.getByRole("cell", { name: "Частичная оплата" }).first(),
  ).toBeVisible();
  await shot(page, "reconciliation");
  await nav(page, "Отчётные снимки");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await shot(page, "reports");
  await lab(page, "correction");
  await shot(page, "lab");
  await page.getByRole("link", { name: "Сравнить снимки" }).click();
  await expect(
    page.getByRole("heading", { name: "Изменившиеся записи" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: /^1[\s\u202f]500,00 ₽$/ }).first(),
  ).toBeVisible();
  await shot(page, "comparison");
  await nav(page, "Сценарии");
  await page.getByRole("spinbutton", { name: "Выручка, %" }).fill("10");
  await page.getByRole("button", { name: "Рассчитать сценарий" }).click();
  await expect(
    page.getByRole("heading", { name: "Результат сценария" }),
  ).toBeVisible();
  await shot(page, "scenario");
});

test("engineer sees ETL runs and steward can trace a quarantined revision", async ({
  page,
}) => {
  await page.goto("/");
  await login(page, "admin");
  await nav(page, "Источники");
  await expect(
    page.getByRole("link", { name: "ERP", exact: true }),
  ).toBeVisible();
  await shot(page, "sources");
  await nav(page, "Мониторинг ETL");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await shot(page, "etl");
  await page.locator("tbody tr").first().getByRole("link").click();
  await expect(
    page.getByRole("heading", { name: "Результаты по источникам" }),
  ).toBeVisible();
  await shot(page, "run");
  await lab(page, "missing_fx", true);
  await nav(page, "Качество");
  await expect(
    page.getByRole("cell", { name: "FX_MISSING" }).first(),
  ).toBeVisible();
  await shot(page, "quality");
  await nav(page, "Карантин");
  await expect(
    page.getByRole("heading", { name: "Отклонённые записи" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "FX_MISSING" }).first(),
  ).toBeVisible();
  await shot(page, "quarantine");
  await page.getByRole("button", { name: "Выйти" }).click();
  await login(page, "finance");
  await page.evaluate(() => (location.hash = "#/runs"));
  await expect(
    page.getByRole("heading", { name: "Мониторинг ETL" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Запустить ETL" })).toHaveCount(
    0,
  );
});
