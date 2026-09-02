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
  info: "border-sky-200 bg-sky-50 text-sky-800",
  success: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  danger: "border-rose-200 bg-rose-50 text-rose-800",
};
