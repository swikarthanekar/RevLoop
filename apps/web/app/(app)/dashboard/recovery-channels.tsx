import {
  DashboardSection,
} from "@/app/(app)/dashboard/dashboard-section";

interface ChannelCardProps {
  title: string;
  status: "live" | "roadmap";
  description: string;
  detail: string;
}

function ChannelCard({ title, status, description, detail }: ChannelCardProps) {
  const isLive = status === "live";
  return (
    <div
      className={`relative overflow-hidden rounded-xl border p-4 ${
        isLive
          ? "border-emerald-200 bg-emerald-50/60"
          : "border-dashed border-neutral-300 bg-neutral-50"
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-neutral-900">{title}</h3>
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${
            isLive
              ? "border-emerald-300 bg-white text-emerald-700"
              : "border-neutral-300 bg-white text-neutral-600"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              isLive ? "bg-emerald-500" : "bg-neutral-400"
            }`}
            aria-hidden="true"
          />
          {isLive ? "Live today" : "Roadmap"}
        </span>
      </div>
      <p className="mt-2 text-sm text-neutral-700">{description}</p>
      <p className="mt-2 text-xs text-neutral-500">{detail}</p>
    </div>
  );
}

/**
 * Honest channel roadmap. Payment-failure recovery is the only channel this
 * build actually executes end to end; overdue receivables are explicitly
 * labeled as the next extension of the same engine rather than implied to be
 * live. Nothing here claims functionality the product does not have.
 */
export function RecoveryChannels() {
  return (
    <DashboardSection
      title="Recovery channels"
      description="What the recovery engine acts on today, and what it extends to next."
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <ChannelCard
          title="Payment failures"
          status="live"
          description="Detected from Razorpay webhooks, scored, decided and worked end to end -- everything on this dashboard."
          detail="Sources: subscription.charged.failed, payment.failed, and related provider events."
        />
        <ChannelCard
          title="Overdue invoices"
          status="roadmap"
          description="The same detection -> decision -> policy -> action pipeline, extended to receivables that go overdue rather than payments that fail outright."
          detail="Next extension: thread an Invoice revenue source through the existing recovery engine -- no new decisioning logic required."
        />
      </div>
    </DashboardSection>
  );
}
