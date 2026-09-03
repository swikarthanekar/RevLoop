/**
 * Safe presentation rules for the audit timeline.
 *
 * SECURITY MODEL — read before changing anything in this file.
 *
 * `TimelineEntry.evidence` is typed in the OpenAPI contract as an open
 * `Record<string, unknown>`. The contract does NOT document which members are
 * safe to display, and the backend filter (`TimelineService._sanitize_evidence`)
 * is a *denylist*: it removes a fixed set of key names and lets everything else
 * through. A denylist cannot protect the UI from a key that has not been thought
 * of yet (`customer_email_address`, `reasoning`, `raw_response`, `mobile`, …).
 *
 * Therefore this module applies an independent **allowlist**: only the keys
 * enumerated in `SAFE_EVIDENCE_FIELDS` are ever rendered, and each one is
 * additionally type-checked before display. An allowlisted key holding an
 * unexpected type (an object, a nested payload, an over-long blob) is dropped
 * rather than coerced to text, so no key name can be used as a channel for an
 * arbitrary payload.
 *
 * Consequences that must be preserved:
 *  - never `JSON.stringify` an evidence value;
 *  - never iterate raw evidence with `Object.entries` for rendering;
 *  - never add a key here without confirming it is documented and safe.
 */

import { humanizeEnumLabel } from "@/app/(app)/recovery/recovery-format";

export type TimelineCategory =
  | "provider"
  | "analysis"
  | "policy"
  | "approval"
  | "execution"
  | "outcome"
  | "warning"
  | "system";

export interface CategoryPresentation {
  id: TimelineCategory;
  /** Always rendered as visible text — category is never colour/icon only. */
  label: string;
  badgeClass: string;
  markerClass: string;
}

const CATEGORIES: Record<TimelineCategory, CategoryPresentation> = {
  provider: {
    id: "provider",
    label: "Provider event",
    badgeClass: "border-sky-300 bg-sky-50 text-sky-900",
    markerClass: "border-sky-400 bg-sky-100",
  },
  analysis: {
    id: "analysis",
    label: "System analysis",
    badgeClass: "border-violet-300 bg-violet-50 text-violet-900",
    markerClass: "border-violet-400 bg-violet-100",
  },
  policy: {
    id: "policy",
    label: "Policy decision",
    badgeClass: "border-amber-300 bg-amber-50 text-amber-900",
    markerClass: "border-amber-400 bg-amber-100",
  },
  approval: {
    id: "approval",
    label: "User approval",
    badgeClass: "border-indigo-300 bg-indigo-50 text-indigo-900",
    markerClass: "border-indigo-400 bg-indigo-100",
  },
  execution: {
    id: "execution",
    label: "Action execution",
    badgeClass: "border-neutral-300 bg-neutral-100 text-neutral-800",
    markerClass: "border-neutral-400 bg-neutral-100",
  },
  outcome: {
    id: "outcome",
    label: "Recovery outcome",
    badgeClass: "border-emerald-300 bg-emerald-50 text-emerald-900",
    markerClass: "border-emerald-400 bg-emerald-100",
  },
  warning: {
    id: "warning",
    label: "Warning",
    badgeClass: "border-rose-300 bg-rose-50 text-rose-900",
    markerClass: "border-rose-400 bg-rose-100",
  },
  system: {
    id: "system",
    label: "System event",
    badgeClass: "border-neutral-300 bg-neutral-50 text-neutral-700",
    markerClass: "border-neutral-300 bg-neutral-100",
  },
};

/**
 * Event types documented in DOMAIN_MODEL.md section 12 and the STATE_MACHINE.md
 * transition table. `event_type` is NOT a closed enum on the wire — the webhook
 * ingest path records raw provider event names such as `payment.failed` — so
 * anything unmatched falls back to the actor-derived category below.
 */
const EVENT_CATEGORY: Record<string, TimelineCategory> = {
  CASE_CREATED: "provider",
  FAILURE_NORMALIZED: "system",
  ANALYSIS_REQUESTED: "analysis",
  ANALYSIS_COMPLETED: "analysis",
  ANALYSIS_TERMINAL_FAILURE: "warning",
  ACTION_BLOCKED_BY_POLICY: "policy",
  APPROVAL_REQUIRED: "policy",
  APPROVAL_REQUESTED: "policy",
  APPROVED_NOW: "approval",
  APPROVED_LATER: "approval",
  APPROVAL_REJECTED: "approval",
  APPROVAL_REJECTED_STOP: "approval",
  APPROVAL_REJECTED_REANALYZE: "approval",
  ACTION_SCHEDULED: "execution",
  ACTION_DUE: "execution",
  AUTO_EXECUTE: "execution",
  ACTION_EXECUTION_STARTED: "execution",
  ACTION_ACCEPTED_OR_UNKNOWN: "execution",
  ACTION_SUCCEEDED: "execution",
  ACTION_FAILED: "warning",
  ACTION_FAILED_REANALYZE: "warning",
  PAYMENT_LINK_CREATED: "execution",
  PAYMENT_VERIFIED: "outcome",
  OUTCOME_VERIFIED: "outcome",
  CASE_RECOVERED: "outcome",
  CASE_FAILED: "outcome",
  CASE_STOPPED: "outcome",
  RECOVERY_EXHAUSTED: "outcome",
  NEGATIVE_OUTCOME_OR_TIMEOUT: "warning",
  STALE_WEBHOOK_IGNORED: "warning",
  TERMINAL_RECONCILIATION_REQUIRED: "warning",
};

/** `actor_type` is a documented enum: SYSTEM, USER, PROVIDER, MODEL. */
const ACTOR_CATEGORY: Record<string, TimelineCategory> = {
  PROVIDER: "provider",
  MODEL: "analysis",
  USER: "approval",
  SYSTEM: "system",
};

const ACTOR_LABEL: Record<string, string> = {
  SYSTEM: "System",
  USER: "Operator",
  PROVIDER: "Provider",
  MODEL: "Model",
};

/**
 * Resolves the visual category from documented fields only.
 *
 * Category is never inferred from position in the list, event age, or the
 * current case status — only from the entry's own `event_type`, falling back to
 * its `actor_type`.
 */
export function getEventCategory(
  eventType: string,
  actorType: string,
): CategoryPresentation {
  const byEvent = EVENT_CATEGORY[eventType?.trim().toUpperCase() ?? ""];
  if (byEvent) {
    return CATEGORIES[byEvent];
  }
  const byActor = ACTOR_CATEGORY[actorType?.trim().toUpperCase() ?? ""];
  return CATEGORIES[byActor ?? "system"];
}

/**
 * Warning styling is applied only to event types the domain model documents as
 * warnings — chiefly `STALE_WEBHOOK_IGNORED` (STATE_MACHINE.md section 10).
 *
 * There is no per-entry `stale` / `superseded` / `event_version` field in the
 * contract, so no other entry is ever marked stale. Staleness is never derived
 * from an entry's age, its position, or the current case status.
 */
export function isWarningEvent(eventType: string, actorType: string): boolean {
  return getEventCategory(eventType, actorType).id === "warning";
}

/** Human label for the documented actor enum; unknown actors are omitted. */
export function formatActorLabel(actorType: string): string | null {
  if (typeof actorType !== "string") {
    return null;
  }
  return ACTOR_LABEL[actorType.trim().toUpperCase()] ?? null;
}

/**
 * Renders the audit event name. FRONTEND_SPEC Screen 4 shows the raw event type
 * (`ANALYSIS_COMPLETED`) because operators match it against backend audit
 * records, so it is preserved verbatim apart from whitespace trimming.
 */
export function formatEventName(eventType: string): string {
  if (typeof eventType !== "string" || !eventType.trim()) {
    return "UNKNOWN_EVENT";
  }
  return eventType.trim();
}

type EvidenceKind = "enum" | "enumList" | "count" | "reference";

interface EvidenceFieldSpec {
  label: string;
  kind: EvidenceKind;
}

/**
 * The complete set of evidence members this UI will ever display.
 *
 * Every entry is either documented in API_CONTRACTS.md section 10
 * (`provider_event_id`) or emitted by backend application code as structured,
 * non-sensitive operational data. Anything absent from this map is dropped
 * silently, including keys that do not exist yet.
 */
const SAFE_EVIDENCE_FIELDS: Record<string, EvidenceFieldSpec> = {
  failure_category: { label: "Failure category", kind: "enum" },
  selected_action: { label: "Selected action", kind: "enum" },
  policy_reasons: { label: "Policy reasons", kind: "enumList" },
  outcome: { label: "Outcome", kind: "enum" },
  transition_event: { label: "Transition", kind: "enum" },
  previous_status: { label: "Previous status", kind: "enum" },
  new_status: { label: "New status", kind: "enum" },
  case_status: { label: "Case status", kind: "enum" },
  source: { label: "Source", kind: "enum" },
  previous_version: { label: "Previous case version", kind: "count" },
  new_version: { label: "New case version", kind: "count" },
  feature_completeness: { label: "Feature completeness", kind: "count" },
  analysis_run_id: { label: "Analysis run", kind: "reference" },
  provider_event_id: { label: "Provider event", kind: "reference" },
  webhook_event_id: { label: "Webhook event", kind: "reference" },
  source_event_key: { label: "Source event", kind: "reference" },
  payment_id: { label: "Payment reference", kind: "reference" },
};

/** Deterministic display order, independent of backend key ordering. */
const SAFE_EVIDENCE_ORDER = Object.keys(SAFE_EVIDENCE_FIELDS);

/** Reference identifiers are bounded; anything longer is treated as a payload. */
const MAX_REFERENCE_LENGTH = 128;
const MAX_LIST_ITEMS = 6;

/**
 * Shape a reference identifier must match (uuid, `pay_…`, `evt_…`, `a.b:c`).
 *
 * Validating the *value*, not just the key name, means an allowlisted key
 * cannot be used to print prose, a stack trace, a header or an injected line
 * break. Anything with spaces, quotes or control characters is not a reference.
 */
const REFERENCE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]*$/;

export interface SafeEvidenceItem {
  key: string;
  label: string;
  value: string;
  /** Reference identifiers render in a monospace face. */
  mono: boolean;
}

function renderReference(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > MAX_REFERENCE_LENGTH) {
    return null;
  }
  if (!REFERENCE_PATTERN.test(trimmed)) {
    return null;
  }
  return trimmed;
}

function renderEvidenceValue(
  value: unknown,
  kind: EvidenceKind,
): string | null {
  switch (kind) {
    case "enum": {
      if (typeof value !== "string" || !value.trim()) {
        return null;
      }
      if (value.trim().length > MAX_REFERENCE_LENGTH) {
        return null;
      }
      return humanizeEnumLabel(value);
    }
    case "enumList": {
      if (!Array.isArray(value) || value.length === 0) {
        return null;
      }
      // Every member must be a plain string; a single object member disqualifies
      // the whole list rather than being rendered partially.
      if (!value.every((item) => typeof item === "string" && item.trim())) {
        return null;
      }
      return value
        .slice(0, MAX_LIST_ITEMS)
        .map((item) => humanizeEnumLabel(item as string))
        .join(", ");
    }
    case "count": {
      if (typeof value !== "number" || !Number.isFinite(value)) {
        return null;
      }
      return String(value);
    }
    case "reference":
      return renderReference(value);
    default:
      return null;
  }
}

/**
 * Projects raw evidence onto the allowlist.
 *
 * Returns only recognised, correctly typed members. Unknown keys, wrongly typed
 * values and nested objects are dropped without being inspected further.
 */
export function formatSafeEvidence(evidence: unknown): SafeEvidenceItem[] {
  if (
    typeof evidence !== "object" ||
    evidence === null ||
    Array.isArray(evidence)
  ) {
    return [];
  }

  const record = evidence as Record<string, unknown>;
  const items: SafeEvidenceItem[] = [];

  for (const key of SAFE_EVIDENCE_ORDER) {
    if (!Object.prototype.hasOwnProperty.call(record, key)) {
      continue;
    }
    const spec = SAFE_EVIDENCE_FIELDS[key];
    const rendered = renderEvidenceValue(record[key], spec.kind);
    if (rendered === null) {
      continue;
    }
    items.push({
      key,
      label: spec.label,
      value: rendered,
      mono: spec.kind === "reference",
    });
  }

  return items;
}
