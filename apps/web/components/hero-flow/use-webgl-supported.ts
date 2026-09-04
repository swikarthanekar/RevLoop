"use client";

import { useEffect, useState } from "react";

/**
 * Detects real WebGL support before mounting the Three.js canvas. jsdom (unit
 * tests) and a handful of locked-down browsers report no WebGL context, and
 * the hero must degrade to a static gradient rather than crash or render a
 * blank canvas in either case.
 */
export function useWebglSupported(): boolean | null {
  const [supported, setSupported] = useState<boolean | null>(null);

  useEffect(() => {
    try {
      const canvas = document.createElement("canvas");
      const context =
        canvas.getContext("webgl2") ?? canvas.getContext("webgl");
      setSupported(Boolean(context));
    } catch {
      setSupported(false);
    }
  }, []);

  return supported;
}
