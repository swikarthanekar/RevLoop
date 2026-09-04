"use client";

import { useEffect, useRef, useState } from "react";
import { animate } from "framer-motion";

import { formatMoney } from "@/lib/money/format-money";

interface AnimatedMoneyProps {
  /** Integer minor units, exactly as the backend returned it -- never derived. */
  amountMinor: number | string | null | undefined;
  currency: string;
  className?: string;
  durationSeconds?: number;
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Best-effort formatter matching `safeMoney`'s degrade-to-dash behavior. */
function tryFormat(amountMinor: AnimatedMoneyProps["amountMinor"], currency: string): string {
  if (amountMinor === null || amountMinor === undefined) {
    return "—";
  }
  try {
    return formatMoney(amountMinor, currency);
  } catch {
    return "—";
  }
}

/**
 * Renders a money value through the same central formatter as everywhere
 * else, tweening the displayed number when it changes after the first
 * render.
 *
 * This animates presentation only: every intermediate frame is still an
 * integer minor-unit value fed through `formatMoney`, and the value it
 * settles on is always exactly `amountMinor` as supplied by the backend --
 * nothing here computes or estimates a financial figure. The first render
 * never animates (a count-up from zero on every page load reads as a demo
 * trick, not a real event); only a change to an already-displayed value
 * animates, because that's the moment it actually represents something --
 * a case was just recovered.
 */
export function AnimatedMoney({
  amountMinor,
  currency,
  className,
  durationSeconds = 1.4,
}: AnimatedMoneyProps) {
  const finalFormatted = tryFormat(amountMinor, currency);
  const numeric =
    amountMinor === null || amountMinor === undefined ? NaN : Number(amountMinor);
  const canAnimate = Number.isFinite(numeric);

  const [displayNumeric, setDisplayNumeric] = useState(numeric);
  const previousRef = useRef(numeric);
  const hasMountedRef = useRef(false);

  useEffect(() => {
    const from = previousRef.current;
    const to = numeric;
    previousRef.current = to;

    if (!canAnimate) {
      return;
    }
    if (!hasMountedRef.current) {
      hasMountedRef.current = true;
      setDisplayNumeric(to);
      return;
    }
    if (from === to || !Number.isFinite(from) || prefersReducedMotion()) {
      setDisplayNumeric(to);
      return;
    }

    const controls = animate(from, to, {
      duration: durationSeconds,
      ease: "easeOut",
      onUpdate: (value) => setDisplayNumeric(Math.round(value)),
    });
    return () => controls.stop();
  }, [numeric, canAnimate, durationSeconds]);

  const displayFormatted = canAnimate
    ? tryFormat(displayNumeric, currency)
    : finalFormatted;

  return (
    <span
      className={className}
      role="status"
      aria-live="polite"
      aria-label={`${finalFormatted} ${currency}`}
    >
      {displayFormatted}
    </span>
  );
}
