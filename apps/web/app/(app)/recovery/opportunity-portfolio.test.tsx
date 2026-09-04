import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

import { OpportunityPortfolio } from "@/app/(app)/recovery/opportunity-portfolio";
import {
  scoredCaseFixture,
  unscoredCaseFixture,
} from "@/app/(app)/recovery/__fixtures__/recovery-fixtures";

describe("OpportunityPortfolio", () => {
  it("renders one accessible bubble per case, including cases with null scoring", () => {
    render(
      <OpportunityPortfolio
        items={[scoredCaseFixture, unscoredCaseFixture]}
        currency="INR"
      />,
    );

    expect(
      screen.getByRole("img", { name: /Portfolio of 2 recovery opportunities/i }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });

  it("renders nothing for an empty case list", () => {
    const { container } = render(<OpportunityPortfolio items={[]} currency="INR" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("lists each distinct failure category once in the legend", () => {
    render(
      <OpportunityPortfolio
        items={[scoredCaseFixture, unscoredCaseFixture]}
        currency="INR"
      />,
    );

    expect(
      screen.getByRole("list", { name: "Failure category legend" }),
    ).toHaveTextContent("Payment rail downtime");
    expect(
      screen.getByRole("list", { name: "Failure category legend" }),
    ).toHaveTextContent("Unspecified");
  });
});
