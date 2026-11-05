import { type Page } from "@playwright/test";

/** Reach administrative controls through the same Settings path as a user. */
export async function openSettings(page: Page, section: string) {
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page
    .getByRole("navigation", { name: "Settings navigation" })
    .locator(`button[data-settings-section="${section}"]`)
    .click();
}

/** Source setup and connection management share one tabbed workspace. */
export async function openSource(page: Page, section: string) {
  await page.getByRole("button", { name: "Sources", exact: true }).click();
  if (section === "status") {
    const diagnostics = page
      .locator("details")
      .filter({
        has: page
          .locator("summary")
          .filter({ hasText: /^Reporting diagnostics$/ }),
      })
      .first();
    if ((await diagnostics.getAttribute("open")) === null)
      await diagnostics.locator("summary").first().click();
  } else if (["sdk", "codex", "claude", "mcp"].includes(section)) {
    await page.locator("#source-tab-gateway").click();
    const advanced = page
      .locator("details")
      .filter({
        has: page
          .locator("summary")
          .filter({ hasText: /^Advanced reporting:/ }),
      })
      .first();
    if ((await advanced.getAttribute("open")) === null)
      await advanced.locator("summary").first().click();
    await advanced
      .getByRole("combobox", { name: "Reporting type", exact: true })
      .selectOption(section);
  } else await page.locator(`#source-tab-${section}`).click();
}
