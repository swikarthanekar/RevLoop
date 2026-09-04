"use client";

import { useEffect, useRef, useState } from "react";

import {
  STATUS_TONE_CLASSES,
  getRecoveryCaseStatusPresentation,
} from "@/components/status-badge/mapping";

interface StatusBadgeProps {
  status: string;
  className?: string;
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

const HIGHLIGHT_DURATION_MS = 900;

/**
 * Status pill that briefly highlights when `status` changes after mount --
 * a case moving to a new state is a real event (an approval executed, an
 * outcome landed), not a value to greet with a flourish on every page load.
 * First mount and re-renders with an unchanged status never animate.
 */
export function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  const presentation = getRecoveryCaseStatusPresentation(status);
  const toneClass = STATUS_TONE_CLASSES[presentation.tone];

  const previousStatusRef = useRef(status);
  const hasMountedRef = useRef(false);
  const [justChanged, setJustChanged] = useState(false);

  useEffect(() => {
    if (!hasMountedRef.current) {
      hasMountedRef.current = true;
      previousStatusRef.current = status;
      return;
    }
    if (previousStatusRef.current === status) {
      return;
    }
    previousStatusRef.current = status;
    if (prefersReducedMotion()) {
      return;
    }
    setJustChanged(true);
    const timeout = setTimeout(() => setJustChanged(false), HIGHLIGHT_DURATION_MS);
    return () => clearTimeout(timeout);
  }, [status]);

  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium transition-all duration-300 ease-out ${toneClass} ${
        justChanged ? "scale-110 ring-2 ring-neutral-400 ring-offset-1" : "scale-100"
      } ${className}`}
      aria-label={`Status: ${presentation.label}`}
    >
      {presentation.label}
    </span>
  );
}
