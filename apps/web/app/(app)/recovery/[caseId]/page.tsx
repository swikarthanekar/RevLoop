import { EmptyState } from "@/components/async-state/error-state";

interface RecoveryCasePlaceholderPageProps {
  params: Promise<{ caseId: string }>;
}

export default async function RecoveryCasePlaceholderPage({
  params,
}: RecoveryCasePlaceholderPageProps) {
  const { caseId } = await params;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Recovery Case Detail</h1>
        <p className="mt-1 text-sm text-neutral-600">
          Case detail for <span className="font-mono text-neutral-800">{caseId}</span> will be
          implemented in a later milestone.
        </p>
      </div>
      <EmptyState
        title="Case detail not implemented yet"
        description="This route establishes navigation shape only. No recommendations, actions, or timeline data are shown."
      />
    </div>
  );
}
