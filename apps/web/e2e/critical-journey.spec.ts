/**
 * Prompt 25 — the critical P0 recovery journey through a real browser.
 *
 * The browser drives the real frontend, which talks to the real FastAPI
 * backend. No application API response is mocked or intercepted. Provider
 * webhooks are genuinely HMAC-signed and posted to the production webhook
 * route.
 */

import { createHash } from "node:crypto";

import { expect, test, type ConsoleMessage, type Page, type Response } from "@playwright/test";

import {
  createFixtureCase,
  getCase,
  getDashboardRecoveredMinor,
  parseInrMinor,
  paymentLinkCreates,
  paymentLinkPaidPayload,
  postSignedWebhook,
  providerRequests,
  resetDemoState,
  resetProviderStub,
  uniqueSuffix,
} from "./fixtures/backend";
import { FIXTURE_AMOUNT_MINOR, FIXTURE_CURRENCY } from "./fixtures/env";

const FIXTURE_AMOUNT_MAJOR = FIXTURE_AMOUNT_MINOR / 100;

/** Collects genuine browser problems so the journey fails on hidden errors. */
function watchForBrowserErrors(page: Page) {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedRequests: string[] = [];

  page.on("console", (message: ConsoleMessage) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error: Error) => {
    pageErrors.push(error.message);
  });
  page.on("response", (response: Response) => {
    const url = response.url();
    if (url.includes("/api/v1/") && response.status() >= 400) {
      // URL and status only — never response bodies or headers.
      failedRequests.push(`${response.status()} ${new URL(url).pathname}`);
    }
  });

  return { consoleErrors, pageErrors, failedRequests };
}

/** Read the Recovered Revenue KPI from the dashboard as minor units. */
async function readRecoveredRevenueKpi(page: Page): Promise<number> {
  const value = page
    .getByRole("term")
    .filter({ hasText: "Recovered Revenue" })
    .locator("xpath=following-sibling::dd[1]")
    .locator("span")
    .first();
  await expect(value).toBeVisible();
  return parseInrMinor((await value.innerText()).trim());
}

/** Navigate to the opportunities list and open the deterministic fixture case. */
async function openFixtureCase(page: Page, customerName: string) {
  await page
    .getByRole("navigation", { name: "Primary" })
    .getByRole("link", { name: "Recovery Opportunities" })
    .click();
  await page.waitForURL("**/recovery");
  await expect(page.getByRole("heading", { name: "Recovery Opportunities", level: 1 })).toBeVisible();

  // The fixture amount is larger than every seeded case, so this filter leaves
  // exactly one row and the test never depends on sort order.
  await page.getByLabel("Minimum amount at risk (₹)").fill(String(FIXTURE_AMOUNT_MAJOR));

  const row = page.getByRole("row").filter({ hasText: customerName });
  await expect(row).toHaveCount(1);
  await row.getByRole("link", { name: `View case for ${customerName}` }).click();
  await page.waitForURL("**/recovery/**");
}

test.describe("critical recovery journey", () => {
  test.beforeEach(async ({ request }) => {
    await resetDemoState(request);
    await resetProviderStub(request);
  });

  test("recovers revenue end to end through the browser", async ({ page, request }) => {
    const watcher = watchForBrowserErrors(page);
    const suffix = uniqueSuffix();
    const fixture = await createFixtureCase(request, suffix);

    // --- Dashboard: capture the KPI before recovery ------------------------
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: "Revenue Recovery Overview", level: 1 })).toBeVisible();
    const kpiBefore = await readRecoveredRevenueKpi(page);
    const apiBefore = await getDashboardRecoveredMinor(request);
    expect(kpiBefore, "dashboard KPI must match the backend summary").toBe(apiBefore);

    // --- Navigate to the case using real application controls -------------
    await openFixtureCase(page, fixture.customerName);
    await expect(page.getByRole("heading", { name: fixture.customerName, level: 1 })).toBeVisible();
    await expect(page.getByLabel("Status: Detected")).toBeVisible();

    // --- Analyze ----------------------------------------------------------
    const analyzeResponse = page.waitForResponse(
      (response) =>
        response.url().includes(`/recovery-cases/${fixture.caseId}/analyze`) &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Analyze case" }).click();
    expect((await analyzeResponse).status()).toBe(200);

    await expect(page.getByLabel("Status: Recommended")).toBeVisible();

    // --- Recommendation is rendered ---------------------------------------
    const decision = page.getByRole("region", { name: "AI recovery decision" });
    await expect(decision).toBeVisible();
    await expect(decision.getByText("Create payment link", { exact: true })).toBeVisible();
    await expect(
      decision.getByText("Estimated recovery probability", { exact: true }),
    ).toBeVisible();
    await expect(decision.getByText("Expected recovery value", { exact: true })).toBeVisible();
    await expect(decision.getByText("Confidence", { exact: true })).toBeVisible();

    const candidates = page.getByRole("region", { name: "Candidate action comparison" });
    await expect(candidates.getByText("Selected")).toBeVisible();

    // The backend runs with GEMINI_API_KEY empty, so the explanation comes from
    // the deterministic template fallback. It must still be rendered.
    await expect(decision.getByRole("heading", { name: "Why this action" })).toBeVisible();
    await expect(decision.getByText(/Create Payment Link is preferred/)).toBeVisible();

    // The frozen fixture must keep selecting the payment-link action. Anything
    // else means the model, policy or fixture drifted and must be investigated.
    const analyzed = await getCase(request, fixture.caseId);
    expect(analyzed.analysis.selected_action).toBe("CREATE_PAYMENT_LINK");
    expect(analyzed.analysis.model_version).toBe("lr-v1.0.0");
    const selectedCandidate = analyzed.analysis.candidates[0];
    expect(selectedCandidate.requires_approval).toBe(true);
    expect(selectedCandidate.policy_reasons).toContain("AMOUNT_ABOVE_AUTO_ACTION_LIMIT");

    // The verdict that governs the branch below is the one re-evaluated on
    // read, not the flag frozen into the recommendation row. Asserting it here
    // ties the notice the operator reads to the branch they actually get: the
    // panel used to draw that notice from the stored flag, which meant it could
    // promise an approval request for an action that executed immediately, or
    // the reverse.
    expect(analyzed.analysis.selected_action_policy.requires_approval).toBe(true);
    await expect(
      page.getByText(
        "This action requires approval. Submitting creates an approval request rather than executing immediately.",
      ),
    ).toBeVisible();

    // --- Execute: the policy requires approval for this amount ------------
    const executeResponse = page.waitForResponse(
      (response) =>
        response.url().includes(`/recovery-cases/${fixture.caseId}/actions`) &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Execute recovery" }).click();
    expect((await executeResponse).status()).toBe(201);

    await expect(page.getByLabel("Status: Awaiting approval")).toBeVisible();

    // Creating the action must not touch the provider: nothing is sent until an
    // administrator approves.
    expect(await paymentLinkCreates(request)).toHaveLength(0);

    // --- Approve through the real UI as ADMIN -----------------------------
    const approveResponse = page.waitForResponse(
      (response) =>
        response.url().includes("/recovery-actions/") &&
        response.url().endsWith("/approve") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Approve action" }).click();
    expect((await approveResponse).status()).toBe(200);

    await expect(page.getByLabel("Status: Waiting for outcome")).toBeVisible();

    // No outcome may exist yet: sending a link is not recovery.
    const waiting = await getCase(request, fixture.caseId);
    expect(waiting.case.status).toBe("WAITING_FOR_OUTCOME");
    expect(waiting.outcome).toBeNull();
    const providerReference = waiting.latest_action.provider_reference;
    expect(providerReference, "payment link action must carry a provider reference").toBeTruthy();

    // --- The real RazorpayClient created the link against the local stub ---
    const creates = await paymentLinkCreates(request);
    expect(creates, "expected exactly one Payment Link create").toHaveLength(1);
    const [create] = creates;
    expect(create.method).toBe("POST");
    expect(create.path).toBe("/v1/payment_links");
    expect(create.authenticated).toBe(true);
    expect(create.body?.amount).toBe(FIXTURE_AMOUNT_MINOR);
    expect(create.body?.currency).toBe(FIXTURE_CURRENCY);
    expect(create.body?.reference_id).toBe(providerReference);
    expect(create.body?.accept_partial).toBe(false);

    // The production client parsed the stub's response and persisted it, which
    // is what distinguishes this from the provider-not-configured fallback.
    expect(waiting.latest_action.status).toBe("SUCCEEDED");
    expect(waiting.latest_action.provider_status).toBe("created");

    const providerLinkId = createHash("sha256").update(providerReference).digest("hex");
    const expectedLinkId = `plink_${providerLinkId.slice(0, 14)}`;

    // --- Inject a genuinely signed success webhook ------------------------
    // The webhook describes the very link the provider just created.
    const successEventId = `evt_e2e_paid_${suffix}`;
    const successPayload = paymentLinkPaidPayload({
      referenceId: providerReference,
      providerLinkId: expectedLinkId,
      paymentId: `pay_e2e_paid_${suffix}`,
    });
    expect(await postSignedWebhook(request, successPayload, successEventId)).toBe(204);

    // --- The existing bounded polling must observe RECOVERED --------------
    await expect(page.getByLabel("Status: Recovered")).toBeVisible({ timeout: 30_000 });

    const outcomeRegion = page.getByRole("region", { name: "Outcome" });
    await expect(outcomeRegion.getByText("Recovered amount")).toBeVisible();
    await expect(outcomeRegion.getByText(/^Verified via /)).toBeVisible();
    // The recovered money is shown to the user, not just recorded server-side.
    await expect(
      outcomeRegion.getByRole("definition").filter({ hasText: "₹40,000.00" }).first(),
    ).toBeVisible();

    // --- Dashboard KPI increased by exactly the recovered amount ----------
    await page
      .getByRole("navigation", { name: "Primary" })
      .getByRole("link", { name: "Dashboard" })
      .click();
    await page.waitForURL("**/dashboard");
    const kpiAfter = await readRecoveredRevenueKpi(page);
    expect(kpiAfter - kpiBefore).toBe(FIXTURE_AMOUNT_MINOR);

    // --- Replaying the same signed webhook must not double count ----------
    expect(await postSignedWebhook(request, successPayload, successEventId)).toBe(204);
    await page.reload();
    const kpiAfterReplay = await readRecoveredRevenueKpi(page);
    expect(kpiAfterReplay).toBe(kpiAfter);
    expect(await getDashboardRecoveredMinor(request)).toBe(kpiAfter);

    const finalCase = await getCase(request, fixture.caseId);
    expect(finalCase.case.status).toBe("RECOVERED");
    expect(finalCase.outcome.recovered_amount_minor).toBe(FIXTURE_AMOUNT_MINOR);

    // Neither recovery nor the replay may trigger another provider call. Reads
    // such as the downtime lookup during analysis are expected; the Payment Link
    // create must remain the only mutating provider request of the journey.
    expect(await paymentLinkCreates(request)).toHaveLength(1);
    const mutations = (await providerRequests(request)).filter(
      (entry) => entry.method !== "GET",
    );
    expect(
      mutations.map((entry) => `${entry.method} ${entry.path}`),
      "the create must be the only provider mutation",
    ).toEqual(["POST /v1/payment_links"]);

    // --- No hidden browser failures ---------------------------------------
    expect(watcher.pageErrors, "unexpected page errors").toEqual([]);
    expect(watcher.consoleErrors, "unexpected console errors").toEqual([]);
    expect(watcher.failedRequests, "unexpected failed API requests").toEqual([]);
  });
});
