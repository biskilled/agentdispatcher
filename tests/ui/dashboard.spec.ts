import { expect, test } from "@playwright/test";
import { openSettings, openSource } from "./navigation";

test("authenticated monitoring, catalog and scoped keys work at this viewport", async ({
  page,
}) => {
  const session = process.env.DISPATCHER_TEST_SESSION;
  const base = process.env.DISPATCHER_TEST_UI_URL;
  test.skip(!session || !base, "Requires local synthetic demo session");
  await page.context().addCookies([
    {
      name: "dispatcher_session",
      value: session!,
      url: base!,
      httpOnly: true,
    },
  ]);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Usage overview" }),
  ).toBeVisible();
  await expect(page.getByText("Observed attempts")).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("button"),
  ).toHaveText(["Overview", "Job runs", "Sources", "Settings"]);
  await expect(
    page.getByRole("heading", { name: "Reported LLM tokens" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "By person", exact: true }).click();
  await expect(
    page.getByRole("columnheader", { name: "Input tokens", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "Output tokens", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "By application", exact: true })
    .click();

  await expect(page.getByText("Synthetic market API").first()).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export selected usage" }).click();
  const file = await downloaded;
  expect(file.suggestedFilename()).toBe("dispatcher-usage.json");
  expect(await file.failure()).toBeNull();
  await page.screenshot({
    path: `test-results/overview-${test.info().project.name}.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "Job runs", exact: true }).click();
  await expect(page.getByText("Market scan")).toBeVisible();
  await openSource(page, "status");
  await expect(
    page.getByRole("heading", { name: "Reporting sources", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Correlated observations", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("python-sdk", { exact: true }).first(),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await openSettings(page, "AgentDesk");
  await expect(
    page.getByRole("heading", { name: "Connect AgentDesk", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "An operator must configure the AgentDesk identity connection for this installation.",
    ),
  ).toBeVisible();
  await openSettings(page, "Model policies");
  const policyId = `policy-${test.info().project.name}-${Date.now()}`;
  await page.getByLabel("Policy ID", { exact: true }).fill(policyId);
  await page.getByLabel("Application", { exact: true }).fill(policyId);
  await page.getByLabel("Environment", { exact: true }).fill("test");
  await page
    .getByLabel("Allowed model aliases (comma separated)")
    .fill("fixture-a, fixture-b");
  await page
    .getByRole("button", { name: "Activate policy", exact: true })
    .click();
  await expect(
    page.getByText("Policy activated. New gateway requests use this revision."),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Policy to edit", exact: true })
    .selectOption(policyId);
  await expect(
    page.getByRole("heading", { name: "Routing history", exact: true }),
  ).toBeVisible();
  await openSettings(page, "Tool access");
  const toolIssued = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/tools/access") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Create tool credential", exact: true })
    .click();
  const toolGrant = await (await toolIssued).json();
  await expect(
    page.getByText(
      "Save this credential in your MCP client's secret environment. It is shown once; never paste it into a prompt.",
    ),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "I have saved the tool credential",
      exact: true,
    })
    .click();
  await page
    .locator(`[data-grant-id="${toolGrant.id}"]`)
    .getByRole("button", { name: "Revoke tool credential", exact: true })
    .click();
  await expect(page.getByText("Tool credential revoked.")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await openSource(page, "api");
  await expect(
    page.getByText("Synthetic market data", { exact: true }),
  ).toBeVisible();
  const pricingForm = page.locator("form").filter({
    has: page.getByRole("button", { name: "Preview price", exact: true }),
  });
  await pricingForm
    .getByLabel("API ID", { exact: true })
    .fill(`browser-${test.info().project.name}-${Date.now()}`);
  await pricingForm
    .getByLabel("Name", { exact: true })
    .fill("Browser synthetic tariff");
  await pricingForm
    .getByLabel("Effective from", { exact: true })
    .fill("2026-01-01T00:00");
  await pricingForm
    .getByRole("combobox", { name: "Pricing", exact: true })
    .selectOption("per_unit");
  await pricingForm
    .getByLabel("Price per unit / overage", { exact: true })
    .fill("0.25");
  await pricingForm
    .getByLabel("Unit definition", { exact: true })
    .fill("data row");
  await pricingForm
    .getByRole("group", { name: "Quota rule 1", exact: true })
    .getByLabel("Quota limit", { exact: true })
    .fill("10");
  await pricingForm
    .getByRole("button", { name: "Add quota rule", exact: true })
    .click();
  const monthly = pricingForm.getByRole("group", {
    name: "Quota rule 2",
    exact: true,
  });
  await monthly.getByLabel("Quota limit", { exact: true }).fill("1000");
  await monthly
    .getByRole("combobox", { name: "Quota window", exact: true })
    .selectOption("monthly");
  await pricingForm
    .getByRole("button", { name: "Preview price", exact: true })
    .click();
  await expect(
    page.getByText(/Synthetic successful request:.*0.25/),
  ).toBeVisible();
  await pricingForm
    .getByRole("button", { name: "Save pricing version", exact: true })
    .click();
  await expect(
    page.getByText(
      "Pricing version saved. Existing costs retain their original calculation.",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Configuration audit", exact: true }),
  ).toBeVisible();
  await openSource(page, "sdk");
  const keyName = `Browser fixture ${test.info().project.name} ${Date.now()}`;
  await page.getByLabel("Connection name", { exact: true }).fill(keyName);
  await page.getByLabel("Application", { exact: true }).fill("browser-fixture");
  await page.getByLabel("Environment", { exact: true }).fill("test");
  await page
    .getByRole("button", { name: "Add connection", exact: true })
    .click();
  await expect(
    page.getByText("Save this key now. It will not be shown again."),
  ).toBeVisible();
  await page.getByRole("button", { name: "I have saved it" }).click();
  await page
    .getByRole("row")
    .filter({ hasText: keyName })
    .getByRole("button", { name: "Revoke" })
    .click();
  await expect(
    page.getByRole("row").filter({ hasText: keyName }).getByText("revoked"),
  ).toBeVisible();
  await openSettings(page, "Schedules");
  const scheduleId = `schedule-${test.info().project.name}-${Date.now()}`;
  await page.getByLabel("Configuration ID", { exact: true }).fill(scheduleId);
  await page
    .getByLabel("Job name", { exact: true })
    .fill("Browser scheduled fixture");
  await page.getByLabel("Application", { exact: true }).fill("browser-fixture");
  await page.getByLabel("Environment", { exact: true }).fill("test");
  await page
    .getByLabel("First expected (local time)", { exact: true })
    .fill("2030-01-01T00:00");
  await page
    .getByRole("combobox", { name: "Cadence", exact: true })
    .selectOption("fixed");
  await page
    .getByLabel("Fixed interval anchor", { exact: true })
    .fill("2030-01-01T00:00");
  await page
    .getByRole("button", { name: "Save configuration", exact: true })
    .click();
  await expect(
    page.getByText("Schedules configuration saved.", { exact: true }),
  ).toBeVisible();
  const schedule = page
    .locator(".inline-form")
    .filter({ has: page.getByText(scheduleId, { exact: true }) });
  await schedule.getByRole("button", { name: "Disable", exact: true }).click();
  await expect(
    schedule.getByRole("button", { name: "Enable", exact: true }),
  ).toBeVisible();
  await openSettings(page, "Budgets");
  const budgetId = `budget-${test.info().project.name}-${Date.now()}`;
  await page.getByLabel("Configuration ID", { exact: true }).fill(budgetId);
  await page.getByLabel("Budget amount", { exact: true }).fill("25");
  await page
    .getByRole("button", { name: "Save configuration", exact: true })
    .click();
  await expect(
    page.getByText("Budgets configuration saved.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(budgetId, { exact: true }).first()).toBeVisible();
  await openSettings(page, "Configuration");
  await expect(
    page.getByRole("heading", {
      name: "Application configuration",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(/No configuration sources are connected/),
  ).toBeVisible();
  await openSource(page, "gateway");
  await expect(
    page.getByLabel("Allowed model names", { exact: false }),
  ).toBeVisible();
  await openSettings(page, "Workspace");
  await expect(
    page.getByRole("heading", { name: "Installation status" }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("button")
      .last(),
  ).toHaveText("Settings");
  await expect(
    page.getByRole("button", {
      name: /^Open (SDK keys|LLM keys|API catalog)$/,
    }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Database: Ready.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Attribution retention" }),
  ).toBeVisible();
  if (test.info().project.name === "desktop") {
    const horizon = page.getByLabel(
      "Keep attribution for days (blank disables expiry)",
    );
    await horizon.fill("30");
    await page.getByRole("button", { name: "Apply retention policy" }).click();
    await expect(
      page.getByText("Attribution expiry enabled for future worker runs."),
    ).toBeVisible();
    await horizon.fill("");
    await page.getByRole("button", { name: "Apply retention policy" }).click();
    await expect(
      page.getByText("Automatic attribution expiry disabled."),
    ).toBeVisible();
  }
  await page
    .getByRole("button", { name: "Open-source licenses", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Open-source licenses" }),
  ).toBeVisible();
  await expect(page.getByText("react 19.2.0", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();
});
