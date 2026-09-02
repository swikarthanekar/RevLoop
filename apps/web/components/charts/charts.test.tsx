import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HorizontalBarChart } from "@/components/charts/horizontal-bar-chart";
import { TrendChart } from "@/components/charts/trend-chart";

const identity = (value: number) => `₹${value}`;

describe("TrendChart", () => {
  const points = [
    { label: "29 Aug", values: [92, 61] },
    { label: "30 Aug", values: [104, 72] },
    { label: "31 Aug", values: [88, 59] },
  ];
  const series = [
    { id: "at_risk", label: "At risk", color: "#b45309" },
    { id: "recovered", label: "Recovered", color: "#047857", dashed: true },
  ];

  it("exposes an accessible chart image with a descriptive label", () => {
    render(
      <TrendChart
        points={points}
        series={series}
        formatValue={identity}
        ariaLabel="Recovery trend across 3 reporting days"
      />,
    );

    expect(
      screen.getByRole("img", { name: "Recovery trend across 3 reporting days" }),
    ).toBeInTheDocument();
  });

  it("labels each series in a text legend", () => {
    render(
      <TrendChart
        points={points}
        series={series}
        formatValue={identity}
        ariaLabel="Recovery trend"
      />,
    );

    expect(screen.getByText("At risk")).toBeInTheDocument();
    expect(screen.getByText("Recovered")).toBeInTheDocument();
  });

  it("distinguishes series by stroke style, not colour alone", () => {
    const { container } = render(
      <TrendChart
        points={points}
        series={series}
        formatValue={identity}
        ariaLabel="Recovery trend"
      />,
    );

    const dashed = container.querySelectorAll("path[stroke-dasharray]");
    expect(dashed.length).toBeGreaterThan(0);
  });

  it("renders x-axis category labels", () => {
    render(
      <TrendChart
        points={points}
        series={series}
        formatValue={identity}
        ariaLabel="Recovery trend"
      />,
    );

    expect(screen.getByText("29 Aug")).toBeInTheDocument();
    expect(screen.getByText("31 Aug")).toBeInTheDocument();
  });

  it("handles an all-zero dataset without producing invalid geometry", () => {
    const { container } = render(
      <TrendChart
        points={[
          { label: "01 Sep", values: [0, 0] },
          { label: "02 Sep", values: [0, 0] },
        ]}
        series={series}
        formatValue={identity}
        ariaLabel="Recovery trend"
      />,
    );

    const paths = [...container.querySelectorAll("path")];
    expect(paths.length).toBeGreaterThan(0);
    for (const path of paths) {
      expect(path.getAttribute("d")).not.toContain("NaN");
    }
  });

  it("handles a single sparse data point", () => {
    const { container } = render(
      <TrendChart
        points={[{ label: "01 Sep", values: [10, 4] }]}
        series={series}
        formatValue={identity}
        ariaLabel="Recovery trend"
      />,
    );

    expect(screen.getByText("01 Sep")).toBeInTheDocument();
    for (const path of container.querySelectorAll("path")) {
      expect(path.getAttribute("d")).not.toContain("NaN");
    }
  });

  it("thins dense axis labels so they stay legible", () => {
    const dense = Array.from({ length: 40 }, (_value, index) => ({
      label: `D${index}`,
      values: [index, index / 2],
    }));

    render(
      <TrendChart
        points={dense}
        series={series}
        formatValue={identity}
        ariaLabel="Recovery trend"
      />,
    );

    expect(screen.getByText("D0")).toBeInTheDocument();
    expect(screen.getByText("D39")).toBeInTheDocument();
    expect(screen.queryByText("D1")).not.toBeInTheDocument();
  });
});

describe("HorizontalBarChart", () => {
  const data = [
    {
      id: "retry",
      label: "Retry payment",
      value: 0.53,
      valueLabel: "52.9%",
      detail: "18 of 34 attempts",
    },
    {
      id: "alternate",
      label: "Request alternate payment method",
      value: 0.71,
      valueLabel: "71.4%",
      detail: "15 of 21 attempts",
    },
  ];

  it("renders a labelled list with visible values", () => {
    render(<HorizontalBarChart data={data} ariaLabel="Recovery rate by action type" />);

    const list = screen.getByRole("list", { name: "Recovery rate by action type" });
    expect(within(list).getByText("Retry payment")).toBeInTheDocument();
    expect(within(list).getByText("52.9%")).toBeInTheDocument();
    expect(within(list).getByText("71.4%")).toBeInTheDocument();
  });

  it("carries the value in each bar's accessible name", () => {
    render(<HorizontalBarChart data={data} ariaLabel="Recovery rate by action type" />);

    expect(
      screen.getByRole("img", { name: "Retry payment: 52.9%, 18 of 34 attempts" }),
    ).toBeInTheDocument();
  });

  it("shows supporting detail text alongside each bar", () => {
    render(<HorizontalBarChart data={data} ariaLabel="Recovery rate by action type" />);

    expect(screen.getByText("18 of 34 attempts")).toBeInTheDocument();
    expect(screen.getByText("15 of 21 attempts")).toBeInTheDocument();
  });

  it("truncates a long label for display but keeps it in the title attribute", () => {
    const longLabel = "Request alternate payment method for high value subscription";
    render(
      <HorizontalBarChart
        data={[{ id: "long", label: longLabel, value: 1, valueLabel: "100.0%" }]}
        ariaLabel="Recovery rate by action type"
      />,
    );

    expect(screen.getByTitle(longLabel)).toBeInTheDocument();
    expect(screen.queryByText(longLabel)).not.toBeInTheDocument();
  });

  it("handles an all-zero dataset without collapsing layout", () => {
    render(
      <HorizontalBarChart
        data={[{ id: "zero", label: "No recoveries", value: 0, valueLabel: "0.0%" }]}
        ariaLabel="Recovery rate by action type"
      />,
    );

    expect(screen.getByText("No recoveries")).toBeInTheDocument();
    expect(screen.getByText("0.0%")).toBeInTheDocument();
  });
});
