import type { ReactNode } from "react";

import { Money } from "@/components/money/money";
import { humanizeEnumLabel } from "@/app/(app)/compliance/compliance-format";
import type {
  PolicyResponse,
  RecoveryActionType,
} from "@/app/(app)/compliance/compliance-types";

interface StatCardProps {
  label: string;
  value: ReactNode;
  context: string;
  accent?: "on" | "off" | "neutral";
}

const ACCENT_BAR: Record<NonNullable<StatCardProps["accent"]>, string> = {
  on: "bg-emerald-600 dark:bg-emerald-400",
  off: "bg-rose-500 dark:bg-rose-400",
  neutral: "bg-neutral-400",
};

function StatCard({ label, value, context, accent = "neutral" }: StatCardProps) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-line bg-surface p-5">
      <span
        aria-hidden="true"
        className={`absolute inset-x-0 top-0 h-1 ${ACCENT_BAR[accent]}`}
      />
      <dt className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
        {label}
      </dt>
      <dd className="mt-2">
        <span className="block text-2xl font-semibold tabular-nums tracking-tight text-ink">
          {value}
        </span>
        <span className="mt-1 block text-sm text-ink-muted">{context}</span>
      </dd>
    </div>
  );
}

function formatMinutes(minutes: number): string {
  if (minutes <= 0) {
    return "None";
  }
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder > 0 ? `${hours}h ${remainder}m` : `${hours}h`;
}

function ActionTypePill({ actionType }: { actionType: RecoveryActionType }) {
  return (
    <span className="inline-flex items-center rounded-full border border-line bg-surface-hover px-2.5 py-1 text-xs font-medium text-ink">
      {humanizeEnumLabel(actionType)}
    </span>
  );
}

interface ActionGroupProps {
  title: string;
  description: string;
  actionTypes: RecoveryActionType[];
  emptyNote: string;
}

function ActionGroup({ title, description, actionTypes, emptyNote }: ActionGroupProps) {
  return (
    <div className="rounded-lg border border-line bg-surface p-5">
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      <p className="mt-0.5 text-sm text-ink-muted">{description}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {actionTypes.length > 0 ? (
          actionTypes.map((actionType) => (
            <ActionTypePill key={actionType} actionType={actionType} />
          ))
        ) : (
          <p className="text-sm text-ink-muted">{emptyNote}</p>
        )}
      </div>
    </div>
  );
}

interface ComplianceGuardrailsProps {
  policy: PolicyResponse;
}

/**
 * Read-only view of the exact MerchantPolicy row the policy engine enforces
 * on every recovery decision (`app/policies/engine.py` on the backend).
 * Nothing here is descriptive copy -- every figure and every action-type
 * grouping is the literal enforced configuration, read back.
 */
export function ComplianceGuardrails({ policy }: ComplianceGuardrailsProps) {
  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard
          label="Automation"
          value={policy.automation_enabled ? "Enabled" : "Disabled"}
          context={
            policy.automation_enabled
              ? "Eligible actions execute automatically, subject to the limits below"
              : "Every action currently requires manual approval"
          }
          accent={policy.automation_enabled ? "on" : "off"}
        />
        <StatCard
          label="Auto-action limit"
          value={
            <Money
              amountMinor={policy.auto_action_limit_minor}
              currency={policy.currency}
            />
          }
          context="Above this amount, an action always requires manual approval"
        />
        <StatCard
          label="Minimum confidence"
          value={`${(policy.minimum_auto_confidence * 100).toFixed(0)}%`}
          context="Below this confidence, an action always requires manual approval"
        />
        <StatCard
          label="Max attempts per case"
          value={String(policy.max_recovery_attempts)}
          context="Recovery stops once a case reaches this many attempts"
        />
        <StatCard
          label="Max contacts / 24h"
          value={String(policy.max_contacts_per_24h)}
          context="Customer-facing contact is capped per case per day"
        />
        <StatCard
          label="Cooldown between contacts"
          value={formatMinutes(policy.cooldown_minutes)}
          context="Minimum wait before the same case can be contacted again"
        />
      </dl>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ActionGroup
          title="Allowed actions"
          description="The only action types this policy permits the engine to recommend."
          actionTypes={policy.allowed_action_types}
          emptyNote="No action types are currently allowed."
        />
        <ActionGroup
          title="Requires manual approval"
          description="Customer-facing actions that always wait for a human, regardless of confidence."
          actionTypes={policy.manual_contact_approval_action_types}
          emptyNote="No action types require manual approval."
        />
        <ActionGroup
          title="Subject to contact cooldown"
          description="Action types rate-limited by the contact cap and cooldown above."
          actionTypes={policy.cooldown_action_types}
          emptyNote="No action types are subject to cooldown."
        />
      </div>
    </div>
  );
}
