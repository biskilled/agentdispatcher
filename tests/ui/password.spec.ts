import { expect, test } from "@playwright/test";

test("password login reaches the scoped dashboard and logout revokes access", async ({ page }) => {
  const email = process.env.DISPATCHER_TEST_LOGIN_EMAIL;
  const password = process.env.DISPATCHER_TEST_LOGIN_PASSWORD;
  test.skip(!email || !password, "Requires an explicitly configured test login");
  await page.goto("/");
  await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
  await page.getByLabel("Email address").fill(email!);
  await page.getByLabel("Password", { exact: true }).fill(password!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Usage overview" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
});
