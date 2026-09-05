import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  AdvisoryNotice,
} from "@/app/(app)/recovery/[caseId]/advisory-notice";
import {
  advisoryTopRankedCandidateFixture,
  recommendedCaseFixture,
  selectedCandidateFixture,
} from "@/app/(app)/recovery/[caseId]/__fixtures__/case-fixtures";
import type { CaseAnalysis } from "@/app/(app)/recovery/[caseId]/case-types";

function analysisWith(overrides: Partial<CaseAnalysis>): CaseAnalysis {
  const base = recommendedCaseFixture.analysis;
  if (!base) {
    throw new Error("fixture must carry an analysis");
  }
  return { ...base, ...overrides };
}

describe("AdvisoryNotice", () => {
  it("explains why the model's top choice is not the one being executed", () => {
    render(
      <AdvisoryNotice
        analysis={analysisWith({
          top_ranked_action: "RETRY_SAME_METHOD",
          selected_action: "REQUEST_ALTERNATE_PAYMENT_METHOD",
          candidates: [
            { ...advisoryTopRankedCandidateFixture },
            { ...selectedCandidateFixture, rank: 2 },
          ],
        })}
        candidates={[
          { ...advisoryTopRankedCandidateFixture },
          { ...selectedCandidateFixture, rank: 2 },
        ]}
      />,
    );

    // Names the model's actual preference rather than hiding it. It appears
    // both in the heading and in the body sentence, which is intentional.
    expect(screen.getAllByText(/Retry same method/i).length).toBeGreaterThan(0);
    // Gives a reason, not a bare badge — a badge alone reads as unfinished.
    expect(screen.getByText(/no mandate or saved payment token/i)).toBeInTheDocument();
    // States what is being executed instead.
    expect(
      screen.getAllByText(/Request alternate payment method/i).length,
    ).toBeGreaterThan(0);
  });

  it("renders nothing when the selected action is already the top-ranked one", () => {
    const { container } = render(
      <AdvisoryNotice
        analysis={analysisWith({
          top_ranked_action: "REQUEST_ALTERNATE_PAYMENT_METHOD",
          selected_action: "REQUEST_ALTERNATE_PAYMENT_METHOD",
          candidates: [selectedCandidateFixture],
        })}
        candidates={[selectedCandidateFixture]}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("stays silent when the top choice was skipped for policy, not capability", () => {
    // A policy block is already explained by the policy panel. Claiming a
    // capability limit here would misattribute the reason.
    const policyBlockedTop = {
      ...selectedCandidateFixture,
      action_type: "CREATE_PAYMENT_LINK",
      rank: 1,
      policy_eligible: false,
      execution_mode: "EXECUTABLE" as const,
      advisory_reason: null,
      advisory_reason_code: null,
    };
    const { container } = render(
      <AdvisoryNotice
        analysis={analysisWith({
          top_ranked_action: "CREATE_PAYMENT_LINK",
          selected_action: "REQUEST_ALTERNATE_PAYMENT_METHOD",
          candidates: [policyBlockedTop, { ...selectedCandidateFixture, rank: 2 }],
        })}
        candidates={[policyBlockedTop, { ...selectedCandidateFixture, rank: 2 }]}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
