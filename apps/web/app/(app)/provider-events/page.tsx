import type { Metadata } from "next";

import { ProviderEventsClient } from "@/app/(app)/provider-events/provider-events-client";

export const metadata: Metadata = {
  title: "Provider Events | RevLoop",
  description:
    "Received Razorpay webhooks, their signature verification result and the deduplication decision.",
};

export default function ProviderEventsPage() {
  return <ProviderEventsClient />;
}
