import { expect, test } from "@playwright/test";

test("invite link, direct acceptance and workspace switching", async ({
  page,
  browser,
}) => {
  const base = process.env.DISPATCHER_TEST_UI_URL;
  const session = process.env.DISPATCHER_TEST_SESSION;
  const accounts = process.env.DISPATCHER_TEST_INVITE_ACCOUNTS;
  test.skip(
    !base || !session || !accounts,
    "Requires isolated recipient fixtures",
  );
  const recipient = JSON.parse(accounts!)[test.info().project.name];
  await page
    .context()
    .addCookies([
      {
        name: "dispatcher_session",
        value: session!,
        url: base!,
        httpOnly: true,
      },
    ]);
  await page.goto("/");
  const targetTenant = await page
    .getByLabel("Workspace", { exact: true })
    .inputValue();
  const workspaceName = await page
    .getByLabel("Workspace", { exact: true })
    .locator("option:checked")
    .textContent();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("button")
      .last(),
  ).toHaveText("Settings");
  await expect(
    page.getByRole("heading", { name: "Installation status" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Attribution retention" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: /^Open (SDK keys|LLM keys|API catalog)$/,
    }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Access", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Attribution retention" }),
  ).toHaveCount(0);
  await page.getByLabel("Email", { exact: true }).fill(recipient.email);
  await page
    .getByRole("button", { name: "Create invitation", exact: true })
    .click();
  const link = page.getByLabel("Invitation link", { exact: true });
  await expect(link).toBeVisible();
  const url = await link.inputValue();
  const context = await browser.newContext({
    viewport: test.info().project.use.viewport,
  });
  try {
    const invitedPage = await context.newPage();
    await invitedPage.goto(url);
    await expect(
      invitedPage.getByText(
        "Sign in with the invited email address, then accept your workspace invitation.",
      ),
    ).toBeVisible();
    await context.addCookies([
      {
        name: "dispatcher_session",
        value: recipient.session,
        url: base!,
        httpOnly: true,
      },
    ]);
    await invitedPage.reload();
    await expect(
      invitedPage.getByLabel("Invitation token", { exact: true }),
    ).toHaveCount(0);
    await invitedPage
      .getByRole("button", {
        name: `Accept invitation to ${workspaceName}`,
        exact: true,
      })
      .click();
    await expect(
      invitedPage.getByLabel("Workspace", { exact: true }),
    ).toHaveValue(targetTenant);
    await expect(
      invitedPage.getByText(`Joined ${workspaceName}.`, { exact: true }),
    ).toBeVisible();
    await expect(
      invitedPage.getByRole("button", { name: /^Accept invitation to/ }),
    ).toHaveCount(0);
    expect(
      await invitedPage.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await invitedPage.screenshot({
      path: `test-results/invitation-${test.info().project.name}.png`,
      fullPage: true,
    });
  } finally {
    await context.close();
  }
});
