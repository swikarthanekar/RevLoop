import type { Metadata } from "next";

import { DashboardClient } from "@/app/(app)/dashboard/dashboard-client";

export const metadata: Metadata = {
  title: "Revenue Recovery Overview | RevLoop",
  description:
    "Revenue at risk, recovered revenue and recovery performance for the current RevLoop workspace.",
};

export default function DashboardPage() {
  return <DashboardClient />;
}
