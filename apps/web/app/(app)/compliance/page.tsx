import type { Metadata } from "next";

import { ComplianceClient } from "@/app/(app)/compliance/compliance-client";

export const metadata: Metadata = {
  title: "Compliance Guardrails | RevLoop",
  description:
    "The literal merchant policy RevLoop's decision engine enforces on every recovery action.",
};

export default function CompliancePage() {
  return <ComplianceClient />;
}
