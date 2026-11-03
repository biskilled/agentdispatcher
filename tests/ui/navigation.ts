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
  await page.locator(`#source-tab-${section}`).click();
}
