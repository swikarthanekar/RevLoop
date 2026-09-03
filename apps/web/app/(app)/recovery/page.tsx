import type { Metadata } from "next";

import { RecoveryClient } from "@/app/(app)/recovery/recovery-client";

export const metadata: Metadata = {
  title: "Recovery Opportunities | RevLoop",
  description:
    "Prioritized recoverable revenue cases for the current RevLoop workspace.",
};

export default function RecoveryPage() {
  return <RecoveryClient />;
}
