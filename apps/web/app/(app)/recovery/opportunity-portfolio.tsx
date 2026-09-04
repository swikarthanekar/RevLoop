"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";

import { niceAxisMax } from "@/components/charts/chart-utils";
import { caseDetailHref } from "@/app/(app)/recovery/recovery-table";
import { humanizeEnumLabel, safeMoney } from "@/app/(app)/recovery/recovery-format";
import type { RecoveryCaseListItem } from "@/app/(app)/recovery/recovery-types";

const PALETTE = [
  "#f59e0b",
  "#818cf8",
  "#22d3ee",
  "#fb7185",
  "#a78bfa",
  "#34d399",
  "#f472b6",
  "#38bdf8",
];

function hashString(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function colorForCategory(category: string): string {
  return PALETTE[hashString(category) % PALETTE.length];
}

/** Deterministic value in [-1, 1] from a string, used only to nudge apart
 * bubbles that would otherwise sit exactly on top of one another -- real
 * portfolios rarely share an identical probability and amount, but this
 * demo's synthetic data sometimes does. */
function jitterUnit(seed: string): number {
  return (hashString(seed) % 2000) / 1000 - 1;
}

const VIEW_WIDTH = 960;
const VIEW_HEIGHT = 320;
const PAD_LEFT = 56;
const PAD_RIGHT = 20;
const PAD_TOP = 16;
const PAD_BOTTOM = 36;
const MIN_RADIUS = 7;
const MAX_RADIUS = 32;

interface Bubble {
  item: RecoveryCaseListItem;
  x: number;
  y: number;
  radius: number;
  color: string;
  category: string;
}

interface OpportunityPortfolioProps {
  items: RecoveryCaseListItem[];
  currency: string;
}

/**
 * Portfolio view of the current page of recovery opportunities: recovery
 * probability on the x-axis, amount at risk on the y-axis, bubble size by
 * expected recoverable value, colored by failure category. Every case is a
 * real, clickable data point -- nothing here re-ranks or re-scores cases,
 * it only lays out the same fields the table renders.
 */
export function OpportunityPortfolio({ items, currency }: OpportunityPortfolioProps) {
  const router = useRouter();

  const { bubbles, categories, yMax } = useMemo(() => {
    const maxAmount = items.reduce(
      (acc, item) => Math.max(acc, item.amount_at_risk_minor),
      0,
    );
    const axisMax = niceAxisMax(maxAmount || 1);
    const maxErv = items.reduce(
      (acc, item) => Math.max(acc, item.expected_recoverable_minor ?? 0),
      0,
    );

    const plotWidth = VIEW_WIDTH - PAD_LEFT - PAD_RIGHT;
    const plotHeight = VIEW_HEIGHT - PAD_TOP - PAD_BOTTOM;
    const categorySet = new Set<string>();

    const built: Bubble[] = items.map((item) => {
      const category = item.failure_category ?? "Unspecified";
      categorySet.add(category);
      const probability = item.recovery_probability ?? 0;
      const erv = item.expected_recoverable_minor ?? 0;
      const sizeRatio = maxErv > 0 ? Math.sqrt(erv / maxErv) : 0;

      // A small deterministic nudge so cases that land on (near-)identical
      // coordinates -- common in this demo's synthetic scoring -- are still
      // individually visible and clickable rather than fully overlapping.
      // Bounded well within the model's own stated uncertainty ("a model
      // estimate, not a guarantee"), so it declutters without misleading.
      const jitterX = jitterUnit(`${item.id}:x`) * 0.05 * plotWidth;
      const jitterY = jitterUnit(`${item.id}:y`) * 0.16 * plotHeight;

      const rawX = PAD_LEFT + Math.min(1, Math.max(0, probability)) * plotWidth;
      const rawY =
        PAD_TOP +
        plotHeight -
        Math.min(1, item.amount_at_risk_minor / axisMax) * plotHeight;

      return {
        item,
        x: Math.min(
          VIEW_WIDTH - PAD_RIGHT,
          Math.max(PAD_LEFT, rawX + jitterX),
        ),
        y: Math.min(
          VIEW_HEIGHT - PAD_BOTTOM,
          Math.max(PAD_TOP, rawY + jitterY),
        ),
        radius: MIN_RADIUS + sizeRatio * (MAX_RADIUS - MIN_RADIUS),
        color: colorForCategory(category),
        category,
      };
    });

    return {
      bubbles: built,
      categories: [...categorySet].sort(),
      yMax: axisMax,
    };
  }, [items]);

  if (items.length === 0) {
    return null;
  }

  const goToCase = (caseId: string) => router.push(caseDetailHref(caseId));

  return (
    <div className="glass-panel p-5">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-base font-semibold tracking-tight text-neutral-900">
            Opportunity portfolio
          </h2>
          <p className="mt-0.5 text-sm text-neutral-600">
            Recovery probability vs. amount at risk. Bubble size is expected
            recoverable value; color is failure category.
          </p>
        </div>
        <ul className="flex flex-wrap gap-x-3 gap-y-1" aria-label="Failure category legend">
          {categories.map((category) => (
            <li key={category} className="flex items-center gap-1.5 text-xs text-neutral-600">
              <span
                aria-hidden="true"
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: colorForCategory(category) }}
              />
              {humanizeEnumLabel(category)}
            </li>
          ))}
        </ul>
      </div>

      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Portfolio of ${bubbles.length} recovery opportunities plotted by recovery probability and amount at risk`}
      >
        <line
          x1={PAD_LEFT}
          y1={VIEW_HEIGHT - PAD_BOTTOM}
          x2={VIEW_WIDTH - PAD_RIGHT}
          y2={VIEW_HEIGHT - PAD_BOTTOM}
          stroke="#e5e7eb"
        />
        <line
          x1={PAD_LEFT}
          y1={PAD_TOP}
          x2={PAD_LEFT}
          y2={VIEW_HEIGHT - PAD_BOTTOM}
          stroke="#e5e7eb"
        />

        {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
          <text
            key={tick}
            x={PAD_LEFT + tick * (VIEW_WIDTH - PAD_LEFT - PAD_RIGHT)}
            y={VIEW_HEIGHT - PAD_BOTTOM + 18}
            textAnchor="middle"
            className="fill-neutral-400 text-[10px]"
          >
            {Math.round(tick * 100)}%
          </text>
        ))}
        <text
          x={(PAD_LEFT + VIEW_WIDTH - PAD_RIGHT) / 2}
          y={VIEW_HEIGHT - 4}
          textAnchor="middle"
          className="fill-neutral-500 text-[10px] font-medium"
        >
          Recovery probability
        </text>

        <text
          x={PAD_LEFT - 8}
          y={PAD_TOP + 4}
          textAnchor="end"
          className="fill-neutral-400 text-[10px]"
        >
          {safeMoney(yMax, currency)}
        </text>
        <text
          x={PAD_LEFT - 8}
          y={VIEW_HEIGHT - PAD_BOTTOM}
          textAnchor="end"
          className="fill-neutral-400 text-[10px]"
        >
          {safeMoney(0, currency)}
        </text>

        {bubbles.map(({ item, x, y, radius, color, category }) => (
          <g
            key={item.id}
            role="button"
            tabIndex={0}
            className="cursor-pointer outline-none"
            onClick={() => goToCase(item.id)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                goToCase(item.id);
              }
            }}
            aria-label={`${item.customer.display_name}: ${safeMoney(
              item.amount_at_risk_minor,
              item.currency,
            )} at risk, ${Math.round((item.recovery_probability ?? 0) * 100)}% recovery probability, ${humanizeEnumLabel(category)}`}
          >
            <circle
              cx={x}
              cy={y}
              r={radius}
              fill={color}
              fillOpacity={0.55}
              stroke={color}
              strokeWidth={1.5}
              className="transition-[fill-opacity] duration-150 hover:fill-opacity-80 focus-visible:fill-opacity-80"
            />
          </g>
        ))}
      </svg>
    </div>
  );
}
