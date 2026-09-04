"use client";

import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";

import { RevenueFlowScene } from "@/components/hero-flow/revenue-flow-scene";
import { useWebglSupported } from "@/components/hero-flow/use-webgl-supported";
import {
  buildFlowStages,
  type FlowSourceMetrics,
} from "@/components/hero-flow/flow-stage-data";

interface RevenueFlowHeroProps {
  metrics: FlowSourceMetrics;
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function StageLabels({ stages }: { stages: ReturnType<typeof buildFlowStages> }) {
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-4 grid grid-cols-4 gap-2 px-6 text-center sm:bottom-6 sm:px-10">
      {stages.map((stage) => (
        <div key={stage.id}>
          <p
            className="text-xs font-semibold uppercase tracking-wide sm:text-sm"
            style={{ color: stage.colorHex }}
          >
            {stage.label}
          </p>
          <p className="mt-0.5 hidden text-[11px] text-white/50 sm:block">
            {stage.sublabel}
          </p>
        </div>
      ))}
    </div>
  );
}

/**
 * Static, motion-free presentation of the same four stages -- visual only.
 * Labels are rendered once, by `StageLabels`, which overlays both this and
 * the Canvas branch, so text is never duplicated between the two.
 */
function StaticFallback({ stages }: { stages: ReturnType<typeof buildFlowStages> }) {
  return (
    <div className="flex h-full items-center justify-center px-6 pb-14">
      <div className="grid w-full max-w-3xl grid-cols-4 gap-3">
        {stages.map((stage) => (
          <div key={stage.id} className="flex items-center justify-center">
            <div
              className="h-12 w-12 rounded-full sm:h-16 sm:w-16"
              style={{
                background: `radial-gradient(circle at 35% 30%, ${stage.colorHex}, transparent 70%)`,
                boxShadow: `0 0 24px ${stage.colorHex}66`,
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Dashboard hero: the four-stage recovery pipeline rendered as a Three.js
 * scene when WebGL is available, degrading to a static gradient rendering of
 * the same four stages otherwise (older browsers, headless test runners, or
 * a user who prefers reduced motion). Every number driving node size and
 * particle density comes from the real dashboard summary via `metrics`.
 */
export function RevenueFlowHero({ metrics }: RevenueFlowHeroProps) {
  const webglSupported = useWebglSupported();
  const stages = buildFlowStages(metrics);
  const reducedMotion = prefersReducedMotion();

  return (
    <div
      className="relative h-64 w-full overflow-hidden rounded-2xl border border-white/10 bg-ink-950 bg-mesh-ink shadow-glass sm:h-72"
      role="img"
      aria-label={`Revenue recovery pipeline: ${stages
        .map((stage) => stage.label)
        .join(" to ")}`}
    >
      <div className="absolute inset-0 bg-grid-fade" aria-hidden="true" />

      {webglSupported && !reducedMotion ? (
        <Suspense fallback={<StaticFallback stages={stages} />}>
          <Canvas
            dpr={[1, 1.75]}
            camera={{ position: [0, 0.6, 11], fov: 38 }}
            gl={{ antialias: true, alpha: true }}
          >
            <RevenueFlowScene stages={stages} />
          </Canvas>
        </Suspense>
      ) : (
        <StaticFallback stages={stages} />
      )}

      <StageLabels stages={stages} />
    </div>
  );
}
