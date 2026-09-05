import type { Metadata } from "next";

import { SimulatorClient } from "@/app/(app)/simulator/simulator-client";

export const metadata: Metadata = {
  title: "Decision Simulator | RevLoop",
  description:
    "Score a hypothetical failed payment through RevLoop's production decision engine.",
};

export default function SimulatorPage() {
  return <SimulatorClient />;
}
