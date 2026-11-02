import { expect, test } from "@playwright/test";

test("connected YAML review, failed activation and rollback", async ({
  page,
}) => {
  const base = process.env.DISPATCHER_TEST_CONFIG_UI_URL;
  const session = process.env.DISPATCHER_TEST_SESSION;
  test.skip(
    !base || !session,
    "Requires isolated configuration browser fixture",
  );
  const source = test.info().project.name;
  await page.context().addCookies([
    {
      name: "dispatcher_session",
      value: session!,
      url: base!,
      httpOnly: true,
    },
  ]);
  await page.goto(base!);
  await page
    .getByRole("button", { name: "Configuration", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Configuration source", exact: true })
    .selectOption(source);
  await page
    .getByRole("button", { name: "Scan current version", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "llm.model", exact: true })
    .selectOption("model-b");
  const proposal = page.waitForResponse((response) =>
    response.url().endsWith(`/${source}/proposals`),
  );
  await page
    .getByRole("button", { name: "Prepare review", exact: true })
    .click();
  const change = await (await proposal).json();
  const reviewed = page.locator("article").filter({
    has: page.getByRole("heading", {
      name: `${source} · proposed`,
      exact: true,
    }),
  });
  const applied = page.waitForResponse((response) =>
    response.url().endsWith(`/${change.id}/apply`),
  );
  await reviewed
    .getByRole("button", { name: "Apply reviewed changes", exact: true })
    .click();
  const version = await (await applied).json();
  await expect(
    page.getByRole("heading", {
      name: `${source} · awaiting activation`,
      exact: true,
    }),
  ).toBeVisible();
  const headers = {
    Authorization: `Bearer ${process.env.DISPATCHER_TEST_CONFIG_KEY}`,
    Origin: base!,
  };
  const failed = await page.request.post(
    `${base}/api/configurations/changes/${change.id}/activation`,
    {
      headers,
      data: { digest: version.digest, success: false },
    },
  );
  expect(failed.ok()).toBeTruthy();
  await page
    .getByRole("button", { name: "Scan current version", exact: true })
    .click();
  const failure = page.locator("article").filter({
    has: page.getByRole("heading", {
      name: `${source} · activation failed`,
      exact: true,
    }),
  });
  await expect(failure).toBeVisible();
  await page.screenshot({
    path: `test-results/configuration-${source}.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await failure
    .getByRole("button", { name: "Restore previous values", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: `${source} · rolled back`, exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Scan current version", exact: true })
    .click();
  await expect(
    page.getByRole("combobox", { name: "llm.model", exact: true }),
  ).toHaveValue("model-a");
});
