import { expect, test, type Page } from "@playwright/test";
import { openSource } from "./navigation";

test("manage gateway services and default without changing app identity", async ({
  page,
}) => {
  const base = process.env.DISPATCHER_TEST_UI_URL;
  const session = process.env.DISPATCHER_TEST_SESSION;
  test.skip(!base || !session, "Requires a synthetic administrator fixture");
  await page.context().addCookies([
    {
      name: "dispatcher_session",
      value: session!,
      url: base!,
      httpOnly: true,
    },
  ]);
  let routing = {
    aliases: {} as Record<string, string>,
    default_model: null as string | null,
    allowed_models: ["configured-model", "second-model"],
    revision: "a".repeat(64),
  };
  await page.route("**/api/gateway/keys", (route) =>
    route.fulfill({
      json: [
        {
          id: "synthetic-gateway",
          name: "AgentTrade",
          app: "agenttrade",
          environment: "test",
          expires_at: "2099-01-01T00:00:00Z",
          revoked_at: null,
          allowed_models: routing.allowed_models,
        },
      ],
    }),
  );
  await page.route(
    "**/api/gateway/keys/synthetic-gateway/routing",
    async (route) => {
      if (route.request().method() === "PUT") {
        const body = route.request().postDataJSON();
        expect(body.revision).toBe(routing.revision);
        routing = { ...routing, ...body, revision: "b".repeat(64) };
      }
      await route.fulfill({ json: routing });
    },
  );
  await page.goto("/");
  await openSource(page, "gateway");
  await page
    .getByRole("button", { name: "Services & default", exact: true })
    .click();
  await page
    .getByLabel("Default provider / model")
    .selectOption("second-model");
  await page.getByRole("button", { name: "Add service", exact: true }).click();
  await page
    .getByLabel("Service name 1", { exact: true })
    .fill("trade-analysis");
  await page
    .getByRole("combobox", { name: "Target model 1", exact: true })
    .selectOption("configured-model");
  await page
    .getByRole("button", { name: "Save services", exact: true })
    .click();
  await expect(page.getByLabel("Gateway routing", { exact: true })).toHaveCount(
    0,
  );
  expect(routing.aliases).toEqual({ "trade-analysis": "configured-model" });
  expect(routing.default_model).toBe("second-model");
  await page
    .getByRole("button", { name: "Services & default", exact: true })
    .click();
  await expect(page.getByLabel("Service name 1", { exact: true })).toHaveValue(
    "trade-analysis",
  );
  await page
    .getByLabel("Service name 1", { exact: true })
    .fill("market-research");
  await page.screenshot({
    path: `test-results/gateway-services-${test.info().project.name}.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page
    .getByRole("button", { name: "Save services", exact: true })
    .click();
  expect(routing.aliases).toEqual({ "market-research": "configured-model" });
  await page
    .getByRole("button", { name: "Services & default", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Remove service 1", exact: true })
    .click();
  await page.getByLabel("Default provider / model").selectOption("");
  await page
    .getByRole("button", { name: "Save services", exact: true })
    .click();
  expect(routing.aliases).toEqual({});
  expect(routing.default_model).toBeNull();
  await expect(
    page.getByRole("row").filter({ hasText: "AgentTrade" }),
  ).toContainText("agenttrade");
});

test("connections use three clear paths and one provider-independent account sync", async ({
  page,
}) => {
  const base = process.env.DISPATCHER_TEST_UI_URL;
  const session = process.env.DISPATCHER_TEST_SESSION;
  test.skip(!base || !session, "Requires synthetic administrator");
  await page.context().addCookies([
    {
      name: "dispatcher_session",
      value: session!,
      url: base!,
      httpOnly: true,
    },
  ]);
  await page.goto("/");
  await expect(page.getByRole("group", { name: "Usage views" })).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Filter usage", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("Application / device", { exact: true }),
  ).toBeVisible();
  await openSource(page, "gateway");
  await expect(
    page.getByRole("tablist", { name: "Source types" }).getByRole("tab"),
  ).toHaveText([
    "Application LLM calls",
    "CLI account usage",
    "Other API usage",
  ]);
  await expect(page.getByLabel("Gateway API base URL")).toBeVisible();
  await page
    .getByRole("tab", { name: "Application LLM calls", exact: true })
    .press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "CLI account usage", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  const name = `Account sync ${test.info().project.name} ${Date.now()}`;
  await page.getByLabel("Connection name", { exact: true }).fill(name);
  await page
    .getByLabel("Device / user label", { exact: true })
    .fill(`browser-device-${test.info().project.name}`);
  await page.getByLabel("Environment", { exact: true }).fill("test");
  await page
    .getByRole("button", { name: "Add connection", exact: true })
    .click();
  await expect(
    page.getByText("Save this key now. It will not be shown again."),
  ).toBeVisible();
  const key = await page.locator(".secret code").textContent();
  const received = await page.request.post("/api/accounts/snapshots", {
    headers: { Authorization: `Bearer ${key}` },
    data: {
      snapshots: ["copilot", "cursor", "gemini"].map((provider) => ({
        provider,
        account: "Browser fixture",
        source: "api",
        status: "ready",
        collected_at: new Date().toISOString(),
        observed_at: new Date().toISOString(),
        windows: [{ label: "Weekly", used_percent: 25 }],
      })),
    },
  });
  expect(received.status()).toBe(202);
  await page
    .getByRole("button", { name: "I have saved it", exact: true })
    .click();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await page
    .getByLabel("Application / device", { exact: true })
    .fill(`browser-device-${test.info().project.name}`);
  const filteredAccounts = page.waitForResponse((response) =>
    response.url().includes("/api/accounts?app_name="),
  );
  await page
    .getByRole("button", { name: "Apply filters", exact: true })
    .click();
  await filteredAccounts;
  for (const name of ["copilot", "cursor", "gemini"]) {
    await expect(page.getByRole("heading", { name, exact: true })).toHaveCount(
      1,
    );
    await expect(
      page.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
  }
  await page.getByLabel("Provider", { exact: true }).fill("cursor");
  await page
    .getByRole("button", { name: "Apply filters", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "cursor", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "copilot", exact: true }),
  ).toHaveCount(0);
  await page.screenshot({
    path: `test-results/accounts-${test.info().project.name}.png`,
    fullPage: true,
  });
  await page.locator(".account-usage").screenshot({
    path: `test-results/account-card-${test.info().project.name}.png`,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await openSource(page, "accounts");
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(page.getByLabel("Provider", { exact: true })).toHaveValue("cursor");
  await expect(page.getByRole("heading", { name: "cursor", exact: true })).toHaveCount(1);
  await openSource(page, "accounts");
  await page
    .getByRole("row")
    .filter({ hasText: name })
    .getByRole("button", { name: "Revoke", exact: true })
    .click();
  await expect(
    page.getByRole("row").filter({ hasText: name }).getByText("revoked"),
  ).toBeVisible();
  await openSource(page, "gateway");
  await page.screenshot({
    path: `test-results/sources-${test.info().project.name}.png`,
    fullPage: true,
  });
});
