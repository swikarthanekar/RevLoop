export type RecoveryCaseStatusValue =
  | "DETECTED"
  | "ANALYZING"
  | "RECOMMENDED"
  | "AWAITING_APPROVAL"
  | "SCHEDULED"
  | "EXECUTING"
  | "WAITING_FOR_OUTCOME"
  | "RECOVERED"
  | "FAILED"
  | "STOPPED";

export type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";

export interface StatusPresentation {
  label: string;
  tone: StatusTone;
}

export const RECOVERY_CASE_STATUS_MAP: Record<RecoveryCaseStatusValue, StatusPresentation> = {
  DETECTED: { label: "Detected", tone: "info" },
  ANALYZING: { label: "Analyzing", tone: "info" },
  RECOMMENDED: { label: "Recommended", tone: "info" },
  AWAITING_APPROVAL: { label: "Awaiting approval", tone: "warning" },
  SCHEDULED: { label: "Scheduled", tone: "info" },
  EXECUTING: { label: "Executing", tone: "info" },
  WAITING_FOR_OUTCOME: { label: "Waiting for outcome", tone: "warning" },
  RECOVERED: { label: "Recovered", tone: "success" },
  FAILED: { label: "Failed", tone: "danger" },
  STOPPED: { label: "Stopped", tone: "neutral" },
};

export function getRecoveryCaseStatusPresentation(
  status: string,
): StatusPresentation {
  const mapped = RECOVERY_CASE_STATUS_MAP[status as RecoveryCaseStatusValue];
  if (mapped) {
    return mapped;
  }
  return { label: "Unknown", tone: "neutral" };
}

export const STATUS_TONE_CLASSES: Record<StatusTone, string> = {
  neutral: "border-neutral-300 bg-neutral-50 text-neutral-700",
  info: "border-info-border bg-info-surface text-info-ink",
  success: "border-success-border bg-success-surface text-success-ink",
  warning: "border-warning-border bg-warning-surface text-warning-ink",
  danger: "border-danger-border bg-danger-surface text-danger-ink",
};
