import { createElement, type ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: ReactNode;
    href: string;
  }) => createElement("a", { href, ...props }, children),
}));

vi.mock("@/lib/api/api-client", () => ({
  ApiClient: class MockApiClient {
    get = vi.fn().mockResolvedValue({ status: "ok" });
  },
}));

import { AppShell } from "@/components/app-shell/app-shell";
import { ENVIRONMENT_BADGE_TEXT } from "@/lib/config/public";
import { PRIMARY_NAV_ITEMS } from "@/components/app-shell/nav-items";

describe("AppShell", () => {
  it("renders primary navigation entries", () => {
    render(
      createElement(
        AppShell,
        null,
        createElement("div", { "data-testid": "main-slot" }, "Page content"),
      ),
    );

    for (const item of PRIMARY_NAV_ITEMS) {
      expect(screen.getByRole("link", { name: new RegExp(item.label) })).toBeInTheDocument();
    }
  });

  it("shows environment badge with demo/test mode text", () => {
    render(createElement(AppShell, null, createElement("div", null, "Page content")));

    expect(screen.getByText(ENVIRONMENT_BADGE_TEXT)).toBeInTheDocument();
    expect(screen.getByText(ENVIRONMENT_BADGE_TEXT).textContent).toMatch(/DEMO/i);
    expect(screen.getByText(ENVIRONMENT_BADGE_TEXT).textContent).toMatch(/TEST MODE/i);
  });

  it("shows demo auth boundary placeholder", () => {
    render(createElement(AppShell, null, createElement("div", null, "Page content")));
    expect(screen.getByText("Demo operator")).toBeInTheDocument();
  });

  it("renders main content slot without fake KPI values", () => {
    render(
      createElement(
        AppShell,
        null,
        createElement(
          "div",
          { "data-testid": "main-slot" },
          "Placeholder milestone content",
        ),
      ),
    );
    expect(screen.getByTestId("main-slot")).toHaveTextContent(
      "Placeholder milestone content",
    );
    expect(screen.queryByText(/₹/)).not.toBeInTheDocument();
    expect(screen.queryByText(/recovered/i)).not.toBeInTheDocument();
  });

  it("marks dashboard nav as current on /dashboard", () => {
    render(createElement(AppShell, null, createElement("div", null, "Page content")));
    const dashboardLink = screen.getByRole("link", { name: /Dashboard/i });
    expect(dashboardLink).toHaveAttribute("aria-current", "page");
  });
});
