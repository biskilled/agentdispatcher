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
  await page.getByRole("button", { name: "API catalog", exact: true }).click();
  await expect(
    page.getByText("Synthetic market data", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "SDK keys", exact: true }).click();
  const keyName = `Browser fixture ${test.info().project.name}`;
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
  await page
    .getByRole("button", { name: "Open-source licenses", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Open-source licenses" }),
  ).toBeVisible();
  await expect(page.getByText("react 19.2.0", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();
});
