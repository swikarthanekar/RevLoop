/**
 * Prompt 25 — browser-level safety regressions for recovery actions.
 *
 * These complement the critical journey: they prove that rapid duplicate
 * interaction stays exactly-once at both the action-creation and the approval
 * boundary, and that a genuine concurrent conflict is surfaced and reconciled
 * against authoritative server state.
 */

import { expect, test, type Page, type Response } from "@playwright/test";

import {
  ADMIN_HEADERS,
  createFixtureCase,
  getCase,
  paymentLinkCreates,
  resetDemoState,
  resetProviderStub,
  uniqueSuffix,
} from "./fixtures/backend";
import { API_BASE_URL } from "./fixtures/env";

/** Analyze a freshly created case through the real UI. */
async function analyze(page: Page, caseId: string) {
  await page.goto(`/recovery/${caseId}`);
  await expect(page.getByLabel("Status: Detected")).toBeVisible();
  await page.getByRole("button", { name: "Analyze case" }).click();
  await expect(page.getByLabel("Status: Recommended")).toBeVisible();
}

/** Record every response for a recovery mutation path. */
function watchPosts(page: Page, matches: (url: string) => boolean) {
  const statuses: number[] = [];
  let requests = 0;
  page.on("request", (req) => {
    if (req.method() === "POST" && matches(req.url())) {
      requests += 1;
    }
  });
  page.on("response", (res: Response) => {
    if (res.request().method() === "POST" && matches(res.url())) {
      statuses.push(res.status());
    }
  });
  return {
    get requests() {
      return requests;
    },
    statuses,
  };
}

test.describe("recovery action safety", () => {
  test.beforeEach(async ({ request }) => {
    await resetDemoState(request);
    await resetProviderStub(request);
  });

  test("rapid duplicate Execute recovery creates exactly one action", async ({
    page,
    request,
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));

    const fixture = await createFixtureCase(request, uniqueSuffix());
    await analyze(page, fixture.caseId);

    const creation = watchPosts(page, (url) => url.endsWith(`/${fixture.caseId}/actions`));

    // A realistic impatient double-click on the real action-creation control,
    // performed before any RecoveryAction exists.
    await page.getByRole("button", { name: "Execute recovery" }).dblclick();

    // The canonical fixture requires approval, so this is the authoritative
    // state after creation.
    await expect(page.getByLabel("Status: Awaiting approval")).toBeVisible();

    const created = await getCase(request, fixture.caseId);
    expect(created.case.status).toBe("AWAITING_APPROVAL");
    expect(created.latest_action.attempt_number).toBe(1);
    expect(created.latest_action.status).toBe("PENDING_APPROVAL");
    const actionId = created.latest_action.id;
    expect(actionId).toBeTruthy();

    // Whether the UI emitted one request or raced, every response must be
    // contract-valid and the backend must have created exactly one action.
    expect(
      creation.statuses.every((status) => status === 201 || status === 409),
      `action-creation statuses were ${creation.statuses.join(",")}`,
    ).toBe(true);
    expect(creation.statuses.filter((status) => status === 201).length).toBeLessThanOrEqual(1);

    // Nothing may reach the provider before approval.
    expect(await paymentLinkCreates(request)).toHaveLength(0);

    // --- Approval is also exactly once, and triggers exactly one provider POST
    const approval = watchPosts(page, (url) => url.endsWith("/approve"));
    await page.getByRole("button", { name: "Approve action" }).dblclick();
    await expect(page.getByLabel("Status: Waiting for outcome")).toBeVisible();

    const settled = await getCase(request, fixture.caseId);
    expect(settled.case.status).toBe("WAITING_FOR_OUTCOME");
    // Still the same single action, still its first attempt.
    expect(settled.latest_action.id).toBe(actionId);
    expect(settled.latest_action.attempt_number).toBe(1);
    expect(settled.latest_action.status).toBe("SUCCEEDED");
    expect(settled.outcome).toBeNull();

    expect(approval.statuses.filter((status) => status === 200).length).toBe(1);
    expect(approval.statuses.every((status) => status === 200 || status === 409)).toBe(true);

    // One approval, one Payment Link. The duplicate interaction added nothing.
    const creates = await paymentLinkCreates(request);
    expect(creates).toHaveLength(1);
    expect(creates[0].body?.reference_id).toBe(settled.latest_action.provider_reference);

    await expect(page.getByRole("button", { name: "Approve action" })).toHaveCount(0);
    expect(pageErrors, "unexpected page errors").toEqual([]);
  });

  test("a genuine concurrent conflict is surfaced and reconciled", async ({ page, request }) => {
    const fixture = await createFixtureCase(request, uniqueSuffix());
    await analyze(page, fixture.caseId);
    await page.getByRole("button", { name: "Execute recovery" }).click();
    await expect(page.getByLabel("Status: Awaiting approval")).toBeVisible();

    const loaded = await getCase(request, fixture.caseId);
    const staleVersion = loaded.case.version;
    const actionId = loaded.latest_action.id;

    // A second, entirely legitimate client approves first. The browser is now
    // holding a stale version with a stale enabled control.
    const concurrent = await request.post(
      `${API_BASE_URL}/api/v1/recovery-actions/${actionId}/approve`,
      { headers: ADMIN_HEADERS, data: { expected_case_version: staleVersion } },
    );
    expect(concurrent.status()).toBe(200);

    const drifted = await getCase(request, fixture.caseId);
    expect(drifted.case.version).toBeGreaterThan(staleVersion);

    const conflict = page.waitForResponse(
      (res) => res.request().method() === "POST" && res.url().endsWith("/approve"),
    );
    await page.getByRole("button", { name: "Approve action" }).click();
    const conflictResponse = await conflict;

    expect(
      conflictResponse.status(),
      `expected an authoritative 409 for the stale approval, got ${conflictResponse.status()}`,
    ).toBe(409);
    const conflictBody = await conflictResponse.json();
    expect(["STALE_CASE_VERSION", "ACTION_NOT_PENDING_APPROVAL"]).toContain(
      conflictBody.error.code,
    );

    // The browser tells the user the case changed and reloads server state.
    await expect(page.getByText("This case changed")).toBeVisible();
    await expect(page.getByLabel("Status: Waiting for outcome")).toBeVisible();

    // The stale control is gone rather than retrying in a loop.
    await expect(page.getByRole("button", { name: "Approve action" })).toHaveCount(0);

    const final = await getCase(request, fixture.caseId);
    expect(final.case.status).toBe("WAITING_FOR_OUTCOME");
    expect(final.latest_action.attempt_number).toBe(1);
    // The rejected duplicate approval must not have produced a second link.
    expect(await paymentLinkCreates(request)).toHaveLength(1);
  });
});
