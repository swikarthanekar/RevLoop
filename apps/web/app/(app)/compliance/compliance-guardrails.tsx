import type { LucideIcon } from "lucide-react";
import { MessageSquare, Repeat, ShieldCheck, ShieldOff, Timer, Wallet } from "lucide-react";
import type { ReactNode } from "react";

import { RadialGauge } from "@/components/gauges/radial-gauge";
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
  icon: LucideIcon;
  tone: "on" | "off" | "amber" | "neutral";
}

const TONE_ICON_WRAP: Record<StatCardProps["tone"], string> = {
  on: "bg-gradient-to-br from-emerald-400 to-teal-500",
  off: "bg-gradient-to-br from-rose-400 to-red-500",
  amber: "bg-gradient-to-br from-amber-400 to-orange-500",
  neutral: "bg-gradient-to-br from-neutral-400 to-neutral-500",
};

function StatCard({ label, value, context, icon: Icon, tone }: StatCardProps) {
  return (
    <div className="glass-panel p-5">
      <div className="flex items-start justify-between">
        <dt className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
          {label}
        </dt>
        <span
          aria-hidden="true"
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-white shadow-sm ${TONE_ICON_WRAP[tone]}`}
        >
          <Icon className="h-4 w-4" strokeWidth={2.25} />
        </span>
      </div>
      <dd className="mt-3">
        <span className="block font-display text-2xl font-semibold tabular-nums tracking-tight text-neutral-900">
          {value}
        </span>
        <span className="mt-1 block text-sm text-neutral-600">{context}</span>
      </dd>
    </div>
  );
}

interface GaugeStatCardProps {
  label: string;
  context: string;
  ratio: number;
  centerText: string;
}

function GaugeStatCard({ label, context, ratio, centerText }: GaugeStatCardProps) {
  return (
    <div className="glass-panel flex items-center gap-4 p-5">
      <RadialGauge ratio={ratio} color="#22d3ee" label={label} centerText={centerText} />
      <div>
        <dt className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
          {label}
        </dt>
        <dd className="mt-1 text-sm text-neutral-600">{context}</dd>
      </div>
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
    <span className="inline-flex items-center rounded-full border border-neutral-300 bg-neutral-50 px-2.5 py-1 text-xs font-medium text-neutral-800">
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
    <div className="glass-panel p-5">
      <h3 className="text-sm font-semibold text-neutral-900">{title}</h3>
      <p className="mt-0.5 text-sm text-neutral-600">{description}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {actionTypes.length > 0 ? (
          actionTypes.map((actionType) => (
            <ActionTypePill key={actionType} actionType={actionType} />
          ))
        ) : (
          <p className="text-sm text-neutral-500">{emptyNote}</p>
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
  const confidenceText = `${(policy.minimum_auto_confidence * 100).toFixed(0)}%`;

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
          icon={policy.automation_enabled ? ShieldCheck : ShieldOff}
          tone={policy.automation_enabled ? "on" : "off"}
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
          icon={Wallet}
          tone="amber"
        />
        <GaugeStatCard
          label="Minimum confidence"
          context="Below this confidence, an action always requires manual approval"
          ratio={policy.minimum_auto_confidence}
          centerText={confidenceText}
        />
        <StatCard
          label="Max attempts per case"
          value={String(policy.max_recovery_attempts)}
          context="Recovery stops once a case reaches this many attempts"
          icon={Repeat}
          tone="neutral"
        />
        <StatCard
          label="Max contacts / 24h"
          value={String(policy.max_contacts_per_24h)}
          context="Customer-facing contact is capped per case per day"
          icon={MessageSquare}
          tone="neutral"
        />
        <StatCard
          label="Cooldown between contacts"
          value={formatMinutes(policy.cooldown_minutes)}
          context="Minimum wait before the same case can be contacted again"
          icon={Timer}
          tone="neutral"
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
