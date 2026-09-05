"use client";

import { ErrorState } from "@/components/async-state/error-state";
import type { ApiClient } from "@/lib/api/api-client";
import { formatMoney } from "@/lib/money/format-money";
import { useEvaluation } from "@/app/(app)/proof/use-evaluation";
import type { Evaluation, PolicySummary } from "@/app/(app)/proof/proof-types";

const CURRENCY = "INR";

function formatRate(rate: string | number): string {
  const value = typeof rate === "string" ? Number.parseFloat(rate) : rate;
  return Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : "—";
}

function money(minor: number): string {
  try {
    return formatMoney(minor, CURRENCY);
  } catch {
    return "—";
  }
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-line bg-surface p-5">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
        {title}
      </h2>
      {description ? (
        <p className="mt-1 text-sm text-ink-muted">{description}</p>
      ) : null}
      <div className="mt-4">{children}</div>
    </section>
  );
}

/**
 * Side-by-side realized recovery for the two policies.
 *
 * Both bars are scaled against the same denominator so their lengths are
 * directly comparable; scaling each to its own maximum would exaggerate the
 * gap, which is exactly the kind of chart a sceptical reader is looking for.
 */
function PolicyComparison({
  revloop,
  baseline,
}: {
  revloop: PolicySummary;
  baseline: PolicySummary;
}) {
  const rows = [
    { label: "RevLoop policy", summary: revloop, accent: true },
    { label: "Naive baseline", summary: baseline, accent: false },
  ];
  const scale = Math.max(
    Number.parseFloat(String(revloop.realized_recovery_rate)),
    Number.parseFloat(String(baseline.realized_recovery_rate)),
    0.0001,
  );

  return (
    <div className="space-y-4">
      {rows.map(({ label, summary, accent }) => {
        const rate = Number.parseFloat(String(summary.realized_recovery_rate));
        const width = Math.max(2, (rate / scale) * 100);
        return (
          <div key={label}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-sm font-medium text-ink">{label}</span>
              <span className="tabular-nums text-lg font-semibold text-ink">
                {formatRate(summary.realized_recovery_rate)}
              </span>
            </div>
            <div
              className="mt-1.5 h-2.5 w-full overflow-hidden rounded-full bg-surface-active"
              role="img"
              aria-label={`${label}: ${formatRate(summary.realized_recovery_rate)} realized recovery`}
            >
              <div
                className={`h-full rounded-full ${
                  accent ? "bg-success-border" : "bg-neutral-500"
                }`}
                style={{ width: `${width}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-ink-muted">
              {money(summary.realized_synthetic_recovered_minor)} realized of{" "}
              {money(summary.amount_at_risk_minor)} at risk ·{" "}
              {summary.selected_intervention_count} interventions ·{" "}
              {summary.stop_count} stops
            </p>
          </div>
        );
      })}
    </div>
  );
}

function Provenance({ evaluation }: { evaluation: Evaluation }) {
  const rows: [string, string][] = [
    ["Scorer", `${evaluation.scorer.model_version} (${evaluation.scorer.model_family})`],
    ["Feature schema", evaluation.scorer.feature_schema_version],
    ["Dataset", evaluation.dataset.dataset_version],
    ["Generator seed", String(evaluation.dataset.seed)],
    ["Split", `${evaluation.dataset.split} (held out)`],
    ["Cases evaluated", String(evaluation.dataset.case_count)],
  ];
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-4 border-b border-line py-1.5">
          <dt className="text-sm text-ink-muted">{label}</dt>
          <dd className="text-right font-mono text-xs text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * Held-out policy evaluation.
 *
 * The most defensible evidence this product has, and it had no interface at
 * all: `POST /api/v1/demo/run-batch` already produced it and nothing called
 * that endpoint.
 *
 * Every figure is read from the backend response. The page computes only bar
 * widths and percentage formatting; it never derives a metric, and it states
 * the synthetic provenance prominently rather than in a footnote, because a
 * reader who discovers that themselves discounts everything else on the screen.
 */
export function ProofClient({ apiClient }: { apiClient?: ApiClient } = {}) {
  const { state, isRecomputing, recomputeError, recompute } =
    useEvaluation(apiClient);

  if (state.status === "loading") {
    return (
      <div className="space-y-4">
        <Header />
        <div
          className="h-64 animate-pulse rounded-lg border border-line bg-surface"
          aria-hidden="true"
        />
        <p className="sr-only" role="status">
          Loading the held-out policy evaluation.
        </p>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="space-y-4">
        <Header />
        <ErrorState error={state.error} />
      </div>
    );
  }

  const { data } = state;
  const evaluation = data.evaluation;
  const revloop = evaluation.revloop_model_policy;
  const baseline = evaluation.naive_baseline_policy;

  const revloopRate = Number.parseFloat(String(revloop.realized_recovery_rate));
  const baselineRate = Number.parseFloat(String(baseline.realized_recovery_rate));
  const pointsGained = (revloopRate - baselineRate) * 100;

  return (
    <div className="space-y-4">
      <Header />

      <div className="rounded-lg border border-warning-border bg-warning-surface p-4">
        <p className="text-sm font-semibold text-warning-ink">
          {evaluation.evaluation_label}
        </p>
        <p className="mt-1 text-sm text-warning-ink">
          These figures come from an offline evaluation on generated data, not
          from merchant traffic. The outcome mechanism behind them is written
          down in <span className="font-mono text-xs">scripts/ml/common.py</span>
          . They show that the policy beats a naive baseline{" "}
          <em>under those stated assumptions</em> — nothing more.
        </p>
      </div>

      <Section
        title="Realized recovery on a held-out split"
        description="Both policies scored over the same cases, by the same frozen model. The test split is never used for model selection."
      >
        <PolicyComparison revloop={revloop} baseline={baseline} />

        <div className="mt-5 flex flex-wrap items-baseline gap-x-6 gap-y-2 border-t border-line pt-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
              Uplift
            </p>
            <p className="text-2xl font-semibold tabular-nums text-ink">
              +{pointsGained.toFixed(2)} pts
            </p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
              Incremental realized
            </p>
            <p className="text-2xl font-semibold tabular-nums text-ink">
              {money(evaluation.incremental_realized_recovered_minor)}
            </p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
              Incremental expected
            </p>
            <p className="text-2xl font-semibold tabular-nums text-ink">
              {money(evaluation.incremental_expected_recovered_minor)}
            </p>
          </div>
        </div>
      </Section>

      <Section
        title="Provenance"
        description="Everything needed to reproduce this run."
      >
        <Provenance evaluation={evaluation} />
      </Section>

      <Section
        title="How this was computed"
        description="Stated so the numbers can be checked rather than taken on trust."
      >
        <ul className="list-disc space-y-1.5 pl-5 text-sm text-ink">
          <li>
            The naive baseline picks the cheapest immediate action and is
            credited a fixed recovery rate; RevLoop&rsquo;s policy ranks
            candidates by expected value and selects only actions it can
            actually execute.
          </li>
          <li>
            Both are scored by the same frozen{" "}
            <span className="font-mono text-xs">
              {evaluation.scorer.model_version}
            </span>{" "}
            artifact, so the comparison isolates the policy, not the model.
          </li>
          <li>
            The cohort is drawn from the held-out test split in sorted case-id
            order — a rule that depends on generated identifiers alone, so
            neither policy can be advantaged by the selection.
          </li>
          <li>
            Realized recovery uses the outcomes the generator sampled, not the
            model&rsquo;s own predictions, so a confident-but-wrong model scores
            badly here.
          </li>
        </ul>
      </Section>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface p-4">
        <div className="min-w-0">
          <p className="text-sm text-ink">
            Computed{" "}
            <time dateTime={data.computed_at} className="font-medium">
              {formatTimestamp(data.computed_at)}
            </time>{" "}
            in {data.duration_seconds.toFixed(1)}s
            {data.recomputed ? " · just recomputed" : " · served from cache"}
          </p>
          <p className="mt-0.5 text-xs text-ink-muted">
            The evaluation is deterministic. Recomputing moves this timestamp
            and leaves every figure above unchanged — that is the check that it
            is a live computation rather than a stored fixture.
          </p>
          {recomputeError ? (
            <p className="mt-1.5 text-xs text-danger-ink" role="alert">
              Recompute failed. The figures above are still the last successful
              run.
            </p>
          ) : null}
        </div>
        <button
          type="button"
          onClick={recompute}
          disabled={isRecomputing}
          aria-busy={isRecomputing}
          className="inline-flex shrink-0 items-center justify-center rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium text-ink hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isRecomputing ? "Recomputing…" : "Recompute"}
        </button>
      </div>
    </div>
  );
}

function Header() {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight text-ink">
        Model Evidence
      </h1>
      <p className="mt-1 text-sm text-ink-muted">
        A held-out comparison of RevLoop&rsquo;s decision policy against a naive
        baseline, scored by the frozen production model.
      </p>
    </div>
  );
}
