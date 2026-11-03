import { type Page } from "@playwright/test";

/** Reach administrative controls through the same Settings path as a user. */
export async function openSettings(page: Page, section: string) {
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page
    .getByLabel("Settings section", { exact: true })
    .selectOption(section);
}
