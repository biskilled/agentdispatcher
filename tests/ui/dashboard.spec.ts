import { expect, test } from "@playwright/test";

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
  await expect(page.getByText("Synthetic market API").first()).toBeVisible();
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
  await page.getByRole("button", { name: "AgentDesk", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Connect AgentDesk", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "An operator must configure the AgentDesk identity connection for this installation.",
    ),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Model policies", exact: true })
    .click();
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
  await page.getByRole("button", { name: "Experiments", exact: true }).click();
  await page.getByLabel("Experiment name", { exact: true }).fill(policyId);
  await page.getByLabel("Application", { exact: true }).fill(policyId);
  await page.getByLabel("Environment", { exact: true }).fill("test");
  await page
    .getByLabel("Baseline model alias", { exact: true })
    .fill("fixture-a");
  await page
    .getByLabel("Candidate model alias", { exact: true })
    .fill("fixture-b");
  await page.getByLabel("Maximum average task latency (ms)").fill("1000");
  await page
    .getByRole("button", { name: "Create experiment", exact: true })
    .click();
  await expect(
    page.getByText(
      "Experiment created. Assign it to a compatible model policy to start routing tasks.",
    ),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Experiment", exact: true })
    .selectOption({ label: policyId });
  await expect(page.getByText("No assignments").first()).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "API catalog", exact: true }).click();
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
  await page.getByRole("button", { name: "SDK keys", exact: true }).click();
  const keyName = `Browser fixture ${test.info().project.name} ${Date.now()}`;
  await page.getByLabel("Key name", { exact: true }).fill(keyName);
  await page.getByLabel("Application", { exact: true }).fill("browser-fixture");
  await page.getByLabel("Environment", { exact: true }).fill("test");
  await page.getByRole("button", { name: "Create key", exact: true }).click();
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
  await page.getByRole("button", { name: "Schedules", exact: true }).click();
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
  await page.getByRole("button", { name: "Budgets", exact: true }).click();
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
  await page
    .getByRole("button", { name: "Configuration", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Application configuration",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(/No configuration sources are connected/),
  ).toBeVisible();
  await page.getByRole("button", { name: "LLM keys", exact: true }).click();
  await expect(
    page.getByLabel("Allowed model names", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Open-source licenses", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Open-source licenses" }),
  ).toBeVisible();
  await expect(page.getByText("react 19.2.0", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();
});
