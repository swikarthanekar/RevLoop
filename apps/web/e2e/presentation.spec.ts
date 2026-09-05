/**
 * Browser-level regressions for the two presentation defects that were
 * reachable within a minute of clicking around the deployed demo.
 *
 * Both were invisible to the unit suite because both are properties of
 * *rendered, composed* pages: a colour pairing that only breaks once the theme
 * class is applied, and a layout overflow that only appears at a real viewport
 * width. Asserting them here is the only place they can be caught.
 */

import { expect, test, type Page } from "@playwright/test";

import { ADMIN_HEADERS, resetDemoState } from "./fixtures/backend";
import { API_BASE_URL } from "./fixtures/env";

const MOBILE = { width: 390, height: 844 };

/** WCAG 2.1 AA for body text. */
const AA_CONTRAST = 4.5;

/**
 * Relative luminance contrast, computed in the page from resolved styles.
 *
 * Deliberately measured from `getComputedStyle` rather than asserted against
 * expected class names: the defect was that a hardcoded pastel background and
 * an inherited theme foreground were each individually "correct" and only
 * wrong in combination. Only the composed result can catch that.
 */
async function contrastReport(page: Page, selector: string) {
  return page.evaluate((sel) => {
    const lin = (c: number) => {
      const v = c / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    const lum = (rgb: number[]) =>
      0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2]);
    const parse = (s: string): number[] | null => {
      const m = s.match(/rgba?\(([^)]+)\)/);
      return m ? m[1].split(",").map((x) => parseFloat(x.trim())).slice(0, 3) : null;
    };
    const ratio = (fg: number[], bg: number[]) => {
      const a = lum(fg);
      const b = lum(bg);
      return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    };

    const panel = document.querySelector(sel);
    if (!panel) return null;
    const bgRaw = getComputedStyle(panel).backgroundColor;
    const bg = parse(bgRaw);
    if (!bg) return null;

    const rows: { text: string; ratio: number }[] = [];
    const consider = (el: Element) => {
      const text = (el.textContent ?? "").trim();
      if (!text) return;
      const fg = parse(getComputedStyle(el).color);
      if (!fg) return;
      rows.push({ text: text.slice(0, 48), ratio: ratio(fg, bg) });
    };
    consider(panel);
    panel.querySelectorAll("*").forEach((el) => {
      if (el.children.length === 0) consider(el);
    });
    return { background: bgRaw, rows };
  }, selector);
}

async function firstRecoveredCaseId(request: {
  get: (url: string, opts: object) => Promise<{ json: () => Promise<unknown> }>;
}): Promise<string> {
  const response = await request.get(
    `${API_BASE_URL}/api/v1/recovery-cases?status=RECOVERED&limit=1`,
    { headers: ADMIN_HEADERS },
  );
  const body = (await response.json()) as { items: { id: string }[] };
  expect(body.items.length).toBeGreaterThan(0);
  return body.items[0].id;
}

test.describe("dark mode legibility", () => {
  test.use({ colorScheme: "dark" });

  test("the recovered outcome card is readable in dark mode", async ({
    page,
    request,
  }) => {
    // The regression: the panel hardcoded `bg-emerald-50` (near-white) while
    // its text inherited the dark theme's near-white foreground. Measured
    // contrast was 1.04:1 — the recovery amount, the description, and the
    // "Verified via Simulated batch" synthetic-data disclosure were all
    // invisible. Two clicks from the theme toggle.
    await resetDemoState(request);
    const caseId = await firstRecoveredCaseId(request);

    await page.goto(`/recovery/${caseId}`);
    await expect(
      page.locator("[aria-labelledby='case-outcome-heading']"),
    ).toBeVisible();

    const report = await contrastReport(page, "[role='status'][aria-live='polite']");
    expect(report).not.toBeNull();
    expect(report!.rows.length).toBeGreaterThan(0);

    const failing = report!.rows.filter((row) => row.ratio < AA_CONTRAST);
    expect(
      failing,
      `unreadable text on the outcome card (bg ${report!.background}): ` +
        JSON.stringify(failing),
    ).toEqual([]);
  });

  test("the synthetic-data disclosure stays visible in dark mode", async ({
    page,
    request,
  }) => {
    // Called out separately because this is the string it would be worst to
    // hide: being visibly honest about synthetic data is the point.
    await resetDemoState(request);
    const caseId = await firstRecoveredCaseId(request);
    await page.goto(`/recovery/${caseId}`);
    await expect(page.getByText(/Verified via Simulated batch/i)).toBeVisible();
    await expect(page.getByText(/DEMO \/ RAZORPAY TEST MODE/i)).toBeVisible();
  });
});

test.describe("mobile layout", () => {
  test.use({ viewport: MOBILE });

  for (const route of ["/dashboard", "/recovery", "/compliance"]) {
    test(`${route} does not scroll horizontally at 390px`, async ({ page }) => {
      // Wide tables are allowed to scroll inside their own container; the page
      // itself must not. The original cause was subtle: the `sr-only` <caption>
      // is `position: absolute`, and escaped its statically-positioned scroll
      // container to sit at document x~1231.
      await page.goto(route);
      await page.waitForLoadState("networkidle");
      const metrics = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }));
      expect(
        metrics.scrollWidth,
        `${route} overflows: scrollWidth ${metrics.scrollWidth} > clientWidth ${metrics.clientWidth}`,
      ).toBeLessThanOrEqual(metrics.clientWidth + 1);
    });
  }

  test("navigation is reachable without a sidebar", async ({ page }) => {
    // Below `md` the sidebar is `hidden md:flex`. Nothing replaced it, so the
    // only way between sections on a phone was typing URLs.
    await page.goto("/dashboard");
    const trigger = page.getByRole("button", { name: /open navigation menu/i });
    await expect(trigger).toBeVisible();

    await trigger.click();
    const panel = page.locator("#mobile-nav-panel");
    await expect(panel).toBeVisible();

    await panel.getByRole("link", { name: /Compliance Guardrails/i }).click();
    await expect(page).toHaveURL(/\/compliance$/);

    // A route change must close the menu rather than leave it over the page.
    await expect(panel).toBeHidden();
  });

  test("every primary destination is reachable on a phone", async ({ page }) => {
    // Sidebar and mobile menu render the same PRIMARY_NAV_ITEMS, so a page
    // added to one is added to both. Asserted anyway: a judge opening this on
    // a phone must be able to reach the evidence and simulator pages, which
    // are the two most differentiating screens.
    await page.goto("/dashboard");
    await page.getByRole("button", { name: /open navigation menu/i }).click();
    const panel = page.locator("#mobile-nav-panel");

    for (const name of [
      /Dashboard/,
      /Recovery Opportunities/,
      /Compliance Guardrails/,
      /Decision Simulator/,
      /Model Evidence/,
    ]) {
      await expect(panel.getByRole("link", { name })).toBeVisible();
    }
  });

  test("the wide recovery table still scrolls inside its own container", async ({
    page,
  }) => {
    // The fix must not have been "make the table narrow": the columns are
    // still there, they just scroll locally.
    await page.goto("/recovery");
    await page.waitForSelector("table tbody tr");

    // Resolved from the table upwards rather than by picking the first
    // `.overflow-x-auto` on the page: the loading skeleton uses the same class,
    // so `.first()` could match a zero-sized element that had not yet been
    // replaced, which is exactly how this assertion flaked.
    const scroller = page
      .locator("div.overflow-x-auto")
      .filter({ has: page.locator("table tbody tr") })
      .first();
    await expect(scroller).toBeVisible();

    const metrics = await scroller.evaluate((el) => ({
      client: el.clientWidth,
      scroll: el.scrollWidth,
    }));
    expect(metrics.client).toBeGreaterThan(0);
    expect(metrics.scroll).toBeGreaterThan(metrics.client);
  });
});

test.describe("error routes", () => {
  test("an unknown route renders a branded, themed 404", async ({ page }) => {
    const response = await page.goto("/this-route-does-not-exist");
    expect(response?.status()).toBe(404);

    await expect(
      page.getByRole("heading", { name: /this page doesn.t exist/i }),
    ).toBeVisible();
    // A way back, rather than a dead end.
    await expect(page.getByRole("link", { name: /dashboard/i })).toBeVisible();

    // Themed, not the unstyled Next.js default.
    const background = await page.evaluate(
      () => getComputedStyle(document.body).backgroundColor,
    );
    expect(background).not.toBe("rgba(0, 0, 0, 0)");
  });
});

test.describe("evidence and simulator pages", () => {
  test("the evidence page renders the held-out comparison", async ({ page }) => {
    // The most defensible number in the product, and it had no UI at all
    // before this: run-batch existed and nothing called it.
    await page.goto("/proof");

    await expect(
      page.getByRole("heading", { name: /model evidence/i }),
    ).toBeVisible();
    // The synthetic label must be visible without scrolling past the figures.
    await expect(page.getByText("SYNTHETIC POLICY SIMULATION")).toBeVisible();
    await expect(page.getByText(/not from merchant traffic/i)).toBeVisible();

    // Provenance a reader needs in order to reproduce the run.
    await expect(page.getByText("test (held out)", { exact: true })).toBeVisible();
    await expect(page.getByText(/lr-v1\.0\.0/).first()).toBeVisible();

    // Both policies, and the uplift between them. `exact` matters here: the
    // page also explains the naive baseline in prose, and Playwright's default
    // substring matching would resolve to those paragraphs too.
    await expect(page.getByText("RevLoop policy", { exact: true })).toBeVisible();
    await expect(page.getByText("Naive baseline", { exact: true })).toBeVisible();
    await expect(page.getByText(/^\+\d+\.\d{2} pts$/)).toBeVisible();
  });

  test("recompute re-runs the evaluation and leaves the figures unchanged", async ({
    page,
  }) => {
    // Determinism is what makes caching honest; this is the check a viewer can
    // perform themselves.
    await page.goto("/proof");
    const rate = page.getByLabel(/RevLoop policy:/);
    await expect(rate).toBeVisible();
    const before = await rate.getAttribute("aria-label");

    await page.getByRole("button", { name: /^recompute$/i }).click();
    await expect(page.getByText(/just recomputed/i)).toBeVisible({ timeout: 60_000 });

    expect(await rate.getAttribute("aria-label")).toBe(before);
  });

  test("the simulator scores a scenario through the real engine", async ({ page }) => {
    await page.goto("/simulator");

    await expect(
      page.getByRole("heading", { name: /decision simulator/i }),
    ).toBeVisible();
    // Attribution: these are the model's numbers, and the page says which model.
    await expect(page.getByText(/Model lr-v1\.0\.0/)).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText("Would execute").first()).toBeVisible();
  });

  test("toggling rail degradation changes the candidate set", async ({ page }) => {
    // Proves the controls drive candidate generation rather than filtering a
    // fixed list in the browser.
    await page.goto("/simulator");
    await expect(page.getByText(/Model lr-v1\.0\.0/)).toBeVisible({
      timeout: 30_000,
    });

    const retry = page.getByText(/Retry same method/i).first();
    await expect(retry).toBeVisible();

    await page.getByLabel(/payment rail is degraded/i).check();
    await expect(page.getByText(/Retry same method/i)).toHaveCount(0, {
      timeout: 30_000,
    });
  });

  test("the ERV arithmetic can be opened and reconciles on screen", async ({
    page,
  }) => {
    await page.goto("/simulator");
    await expect(page.getByText(/Model lr-v1\.0\.0/)).toBeVisible({
      timeout: 30_000,
    });

    await page.getByRole("button", { name: /show the arithmetic/i }).first().click();
    await expect(page.getByText(/How expected value is derived/i)).toBeVisible();
    await expect(page.getByText(/Expected recovery/).first()).toBeVisible();
    await expect(page.getByText(/Expected value/).first()).toBeVisible();
  });
});
