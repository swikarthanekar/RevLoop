import { EmptyState } from "@/components/async-state/error-state";

export default function RecoveryPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Recovery Opportunities</h1>
        <p className="mt-1 text-sm text-neutral-600">
          Prioritized recoverable revenue cases will appear here in a later milestone.
        </p>
      </div>
      <EmptyState
        title="Recovery table not implemented yet"
        description="No synthetic case counts, probabilities, or amounts are displayed in this placeholder."
      />
    </div>
  );
}
