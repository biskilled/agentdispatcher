import { expect, test, type Page } from "@playwright/test";
import { openSource } from "./navigation";

async function openReporting(page: Page, source: string) {
  await openSource(page, source);
  await page
    .getByText(
      source === "sdk"
        ? "Add job and API reporting"
        : "Manage direct reporting (outside the LLM gateway)",
      { exact: true },
    )
    .click();
}

test("manage source connections inside their tabs", async ({ page }) => {
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
  await page.goto("/");
  await page.getByRole("button", { name: "Sources", exact: true }).click();
  await expect(
    page.getByRole("tab", { name: "LLM gateway", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(
    page.getByRole("heading", { name: "Connect once through LiteLLM" }),
  ).toBeVisible();
  await expect(page.getByLabel("Gateway API base URL")).toBeVisible();
  await openSource(page, "codex");
  await expect(
    page.getByLabel("Connection name", { exact: true }),
  ).not.toBeVisible();
  await page
    .getByRole("button", { name: "Connect LLM calls through LiteLLM" })
    .click();
  await expect(
    page.getByRole("tab", { name: "LLM gateway", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  for (const source of ["sdk", "codex", "claude", "mcp"]) {
    await openReporting(page, source);
    await expect(
      page.getByRole("heading", { name: /^Workspace invitations/ }),
    ).toHaveCount(0);
    const name = `${source}-${test.info().project.name}-${Date.now()}`;
    await page.getByLabel("Connection name", { exact: true }).fill(name);
    await page.getByLabel("Application", { exact: true }).fill(name);
    await page.getByLabel("Environment", { exact: true }).fill("test");
    await page
      .getByRole("button", { name: "Add connection", exact: true })
      .click();
    await expect(
      page.getByText("Save this key now. It will not be shown again."),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "I have saved it", exact: true })
      .click();
    await page
      .getByRole("row")
      .filter({ hasText: name })
      .getByRole("button", { name: "Edit", exact: true })
      .click();
    const edit = page.locator("section").filter({
      has: page.getByRole("heading", {
        name: "Edit connection",
        exact: true,
      }),
    });
    await edit
      .getByLabel("Connection name", { exact: true })
      .fill(`${name}-renamed`);
    await edit
      .getByRole("button", { name: "Save connection", exact: true })
      .click();
    const row = page.getByRole("row").filter({ hasText: `${name}-renamed` });
    await expect(row).toBeVisible();
    await page.reload();
    await openReporting(page, source);
    await expect(row).toBeVisible();
    await openSource(page, source === "sdk" ? "codex" : "sdk");
    await expect(
      page.getByRole("row").filter({ hasText: `${name}-renamed` }),
    ).toHaveCount(0);
    await openReporting(page, source);
    await row.getByRole("button", { name: "Revoke", exact: true }).click();
    await expect(row.getByText("revoked", { exact: true })).toBeVisible();
  }
  await openSource(page, "codex");
  await page
    .getByRole("tab", { name: "Codex", exact: true })
    .press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Claude Code", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await openSource(page, "api");
  await expect(
    page.getByRole("heading", { name: "API connections", exact: true }),
  ).toBeVisible();
  await openSource(page, "gateway");
  await expect(
    page.getByLabel("Allowed model names", { exact: false }),
  ).toBeVisible();
  const loaded = page.waitForResponse((response) =>
    response.url().endsWith("/api/coverage"),
  );
  await openSource(page, "status");
  expect((await loaded).status()).toBe(200);
  const refreshed = page.waitForResponse((response) =>
    response.url().endsWith("/api/coverage"),
  );
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  expect((await refreshed).status()).toBe(200);
  await openSource(page, "gateway");
  await page.getByText("Application setup", { exact: true }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: `test-results/sources-${test.info().project.name}.png`,
    fullPage: true,
  });
});
