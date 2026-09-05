"use client";

import { useMemo, useState } from "react";

import { ErrorState } from "@/components/async-state/error-state";
import { formatMoney } from "@/lib/money/format-money";
import { humanizeEnumLabel } from "@/app/(app)/recovery/recovery-format";
import { ErvWaterfall } from "@/app/(app)/simulator/erv-waterfall";
import { useSimulation } from "@/app/(app)/simulator/use-simulation";
import type {
  FailureCategory,
  SimulatedCandidate,
  SimulationRequest,
} from "@/app/(app)/simulator/simulator-types";

const FAILURE_CATEGORIES: FailureCategory[] = [
  "AUTHENTICATION_FAILURE",
  "PAYMENT_RAIL_DOWNTIME",
  "INSUFFICIENT_FUNDS",
  "BANK_OR_ISSUER_DECLINE",
  "EXPIRED_OR_INVALID_METHOD",
  "TECHNICAL_FAILURE",
  "MANDATE_OR_RECURRING_FAILURE",
  "UNKNOWN",
];

const SEGMENTS = ["REGULAR", "HIGH_VALUE", "NEW", "AT_RISK"];
const METHODS = ["upi", "card", "netbanking", "wallet"] as const;

/** Mirrors the server's own bounds; the server re-validates regardless. */
const AMOUNT_MIN = 100;
const AMOUNT_MAX = 100_000_00;

const DEFAULT_SCENARIO: SimulationRequest = {
  amount_minor: 199900,
  failure_category: "AUTHENTICATION_FAILURE",
  case_type: "PAYMENT_FAILURE",
  payment_method: "card",
  customer_segment: "REGULAR",
  hours_since_failure: 2,
  retry_count_provider: 0,
  recovery_attempts_so_far: 0,
  contacts_last_24h: 0,
  customer_tenure_days: 180,
  lifetime_value_minor: 50_000_00,
  payment_success_rate_90d: 0.8,
  successful_payments_90d: 8,
  failed_payments_30d: 1,
  rail_degraded: false,
  same_method_recent_success: true,
  alternate_method_recent_success: true,
  subscription_status: null,
  provider_retries_active: false,
};

function money(minor: number): string {
  try {
    return formatMoney(minor, "INR");
  } catch {
    return "—";
  }
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-ink">{label}</label>
      {children}
      {hint ? <p className="mt-0.5 text-[11px] text-ink-muted">{hint}</p> : null}
    </div>
  );
}

const INPUT =
  "mt-1 w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500";

function CandidateRow({
  candidate,
  expanded,
  onToggle,
}: {
  candidate: SimulatedCandidate;
  expanded: boolean;
  onToggle: () => void;
}) {
  const advisory = candidate.execution_mode === "ADVISORY";
  return (
    <li
      className={`rounded-md border p-3 ${
        candidate.selected
          ? "border-success-border bg-success-surface"
          : "border-line bg-surface"
      }`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="min-w-0">
          <span
            className={`text-sm font-medium ${
              candidate.selected ? "text-success-ink" : "text-ink"
            }`}
          >
            #{candidate.rank} {humanizeEnumLabel(candidate.action_type)}
          </span>
          {candidate.selected ? (
            <span className="ml-2 rounded border border-success-border px-1.5 py-0.5 text-[11px] font-medium text-success-ink">
              Would execute
            </span>
          ) : null}
          {advisory ? (
            <span className="ml-2 rounded border border-info-border bg-info-surface px-1.5 py-0.5 text-[11px] font-medium text-info-ink">
              Advisory
            </span>
          ) : null}
        </div>
        <div className="text-right">
          <span
            className={`block tabular-nums text-sm font-semibold ${
              candidate.selected ? "text-success-ink" : "text-ink"
            }`}
          >
            {money(candidate.expected_value_minor)}
          </span>
          <span className="block text-[11px] text-ink-muted">
            p = {(candidate.success_probability * 100).toFixed(1)}%
          </span>
        </div>
      </div>

      {advisory && candidate.advisory_reason ? (
        <p className="mt-1.5 text-xs text-info-ink">{candidate.advisory_reason}</p>
      ) : null}

      <p className="mt-1.5 text-xs">
        {candidate.policy_eligible ? (
          <span className="text-ink-muted">
            Policy: eligible
            {candidate.requires_approval ? (
              <span className="font-medium text-warning-ink">
                {" "}
                · requires approval
              </span>
            ) : null}
          </span>
        ) : (
          <span className="text-warning-ink">
            Policy: blocked
            {candidate.policy_reasons.length > 0
              ? ` — ${candidate.policy_reasons.map(humanizeEnumLabel).join(", ")}`
              : ""}
          </span>
        )}
      </p>

      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="mt-2 text-xs font-medium text-ink underline decoration-dotted underline-offset-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
      >
        {expanded ? "Hide the arithmetic" : "Show the arithmetic"}
      </button>

      {expanded ? (
        <div className="mt-2">
          <ErvWaterfall
            currency="INR"
            expectedRecoveredMinor={candidate.expected_recovered_minor}
            actionCostMinor={candidate.action_cost_minor}
            fatiguePenaltyMinor={candidate.fatigue_penalty_minor}
            operationalRiskPenaltyMinor={candidate.operational_risk_penalty_minor}
            delayPenaltyMinor={candidate.delay_penalty_minor}
            expectedValueMinor={candidate.expected_value_minor}
          />
        </div>
      ) : null}
    </li>
  );
}

/**
 * Interactive decision simulator.
 *
 * Turns "we have a model" into something a reader can operate. Every number on
 * the right is produced by the same engine the live product runs — candidate
 * generation, the frozen model, ERV, the policy engine, ranking and
 * capability-aware selection — over the scenario on the left.
 *
 * Read-only: the endpoint creates nothing and changes nothing, so this is safe
 * to hand to someone mid-demo.
 */
export function SimulatorClient() {
  const [scenario, setScenario] = useState<SimulationRequest>(DEFAULT_SCENARIO);
  const [expanded, setExpanded] = useState<string | null>(null);
  const { state, isRefreshing } = useSimulation(scenario);

  const set = useMemo(
    () =>
      <K extends keyof SimulationRequest>(key: K, value: SimulationRequest[K]) =>
        setScenario((current) => ({ ...current, [key]: value })),
    [],
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Decision Simulator
        </h1>
        <p className="mt-1 text-sm text-ink-muted">
          Describe a failed payment and watch the production engine rank the
          actions, price them and apply merchant policy. Nothing here is saved.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <section
          aria-label="Scenario controls"
          className="space-y-3 rounded-lg border border-line bg-surface p-4 lg:col-span-2"
        >
          <Field
            label={`Amount at risk — ${money(scenario.amount_minor ?? 0)}`}
            hint="Crossing the merchant's auto-action limit flips the verdict to requires-approval."
          >
            <input
              type="range"
              min={AMOUNT_MIN}
              max={AMOUNT_MAX}
              step={100}
              value={scenario.amount_minor}
              onChange={(event) => set("amount_minor", Number(event.target.value))}
              className="mt-1 w-full"
            />
          </Field>

          <Field
            label="Failure category"
            hint="Drives which actions are candidates at all."
          >
            <select
              value={scenario.failure_category}
              onChange={(event) =>
                set("failure_category", event.target.value as FailureCategory)
              }
              className={INPUT}
            >
              {FAILURE_CATEGORIES.map((value) => (
                <option key={value} value={value}>
                  {humanizeEnumLabel(value)}
                </option>
              ))}
            </select>
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Payment method">
              <select
                value={scenario.payment_method ?? "card"}
                onChange={(event) =>
                  set(
                    "payment_method",
                    event.target.value as SimulationRequest["payment_method"],
                  )
                }
                className={INPUT}
              >
                {METHODS.map((value) => (
                  <option key={value} value={value}>
                    {value.toUpperCase()}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Customer segment">
              <select
                value={scenario.customer_segment ?? "REGULAR"}
                onChange={(event) => set("customer_segment", event.target.value)}
                className={INPUT}
              >
                {SEGMENTS.map((value) => (
                  <option key={value} value={value}>
                    {humanizeEnumLabel(value)}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <Field label={`Hours since failure — ${scenario.hours_since_failure}h`}>
            <input
              type="range"
              min={0}
              max={168}
              step={1}
              value={scenario.hours_since_failure}
              onChange={(event) =>
                set("hours_since_failure", Number(event.target.value))
              }
              className="mt-1 w-full"
            />
          </Field>

          <Field
            label={`Prior recovery attempts — ${scenario.recovery_attempts_so_far}`}
            hint="Enough attempts trips the merchant's attempt cap."
          >
            <input
              type="range"
              min={0}
              max={5}
              step={1}
              value={scenario.recovery_attempts_so_far}
              onChange={(event) =>
                set("recovery_attempts_so_far", Number(event.target.value))
              }
              className="mt-1 w-full"
            />
          </Field>

          <Field
            label={`Customer success rate (90d) — ${((scenario.payment_success_rate_90d ?? 0) * 100).toFixed(0)}%`}
          >
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={(scenario.payment_success_rate_90d ?? 0) * 100}
              onChange={(event) =>
                set("payment_success_rate_90d", Number(event.target.value) / 100)
              }
              className="mt-1 w-full"
            />
          </Field>

          <label className="flex items-center gap-2 pt-1 text-sm text-ink">
            <input
              type="checkbox"
              checked={scenario.rail_degraded ?? false}
              onChange={(event) => set("rail_degraded", event.target.checked)}
              className="rounded border-line"
            />
            Payment rail is degraded
          </label>
          <p className="text-[11px] text-ink-muted">
            Turn this on and retry-same-method disappears from the candidate set
            entirely — candidate generation removes it, not the interface.
          </p>
        </section>

        <section
          aria-label="Engine decision"
          className="space-y-3 lg:col-span-3"
          aria-busy={isRefreshing}
        >
          {state.status === "error" ? (
            <ErrorState error={state.error} />
          ) : state.status === "loading" ? (
            <div
              className="h-72 animate-pulse rounded-lg border border-line bg-surface"
              aria-hidden="true"
            />
          ) : (
            <>
              <div className="rounded-lg border border-line bg-surface p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
                      Would execute
                    </p>
                    <p className="mt-0.5 text-lg font-semibold text-ink">
                      {state.data.selected_action
                        ? humanizeEnumLabel(state.data.selected_action)
                        : "No eligible action"}
                    </p>
                  </div>
                  {state.data.top_ranked_action &&
                  state.data.top_ranked_action !== state.data.selected_action ? (
                    <p className="max-w-xs text-xs text-info-ink">
                      The model ranks{" "}
                      {humanizeEnumLabel(state.data.top_ranked_action)} highest,
                      but RevLoop does not execute it — see the note on that row.
                    </p>
                  ) : null}
                </div>
                <p className="mt-2 text-[11px] text-ink-muted">
                  Model {state.data.model_version} ·{" "}
                  {state.data.feature_schema_version} · inference source{" "}
                  <span className="font-mono">{state.data.inference_source}</span>{" "}
                  · auto-action limit{" "}
                  {money(state.data.policy_auto_action_limit_minor)}
                </p>
              </div>

              <ul className="space-y-2">
                {state.data.candidates.map((candidate) => (
                  <CandidateRow
                    key={candidate.action_type}
                    candidate={candidate}
                    expanded={expanded === candidate.action_type}
                    onToggle={() =>
                      setExpanded((current) =>
                        current === candidate.action_type
                          ? null
                          : candidate.action_type,
                      )
                    }
                  />
                ))}
              </ul>

              <p className="rounded-md border border-line bg-surface-hover p-3 text-xs text-ink-muted">
                Hypothetical scenario, scored live. No case is created and
                nothing is stored. Probabilities come from the same frozen model
                the live product uses, trained on generated data — see Model
                Evidence for how it performs on a held-out split.
              </p>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
