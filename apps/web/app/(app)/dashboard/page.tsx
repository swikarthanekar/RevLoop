import { EmptyState } from "@/components/async-state/error-state";

export default function DashboardPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Executive Dashboard</h1>
        <p className="mt-1 text-sm text-neutral-600">
          Revenue recovery overview shell. KPIs and charts arrive in Prompt 19.
        </p>
      </div>
      <EmptyState
        title="Dashboard not implemented yet"
        description="This milestone establishes the application shell and typed API foundation only. No demo metrics are shown here."
      />
    </div>
  );
}
