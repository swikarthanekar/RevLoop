import {
  STATUS_TONE_CLASSES,
  getRecoveryCaseStatusPresentation,
} from "@/components/status-badge/mapping";

interface StatusBadgeProps {
  status: string;
  className?: string;
}

export function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  const presentation = getRecoveryCaseStatusPresentation(status);
  const toneClass = STATUS_TONE_CLASSES[presentation.tone];
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${toneClass} ${className}`}
      aria-label={`Status: ${presentation.label}`}
    >
      {presentation.label}
    </span>
  );
}
