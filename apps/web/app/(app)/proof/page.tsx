import type { Metadata } from "next";

import { ProofClient } from "@/app/(app)/proof/proof-client";

export const metadata: Metadata = {
  title: "Model Evidence | RevLoop",
  description:
    "Held-out policy evaluation comparing RevLoop's decision engine against a naive baseline on synthetic data.",
};

export default function ProofPage() {
  return <ProofClient />;
}
