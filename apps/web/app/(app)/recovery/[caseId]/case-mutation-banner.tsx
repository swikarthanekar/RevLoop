"use client";

import { ErrorState } from "@/components/async-state/error-state";
import type { MutationState } from "@/app/(app)/recovery/[caseId]/use-case-actions";

interface CaseMutationBannerProps {
  mutation: MutationState;
  onDismiss: () => void;
}

/**
 * Feedback for the most recent mutation.
 *
 * Rendered at page level rather than inside the action panel, because a
 * conflict can move the case into a state whose panel no longer exists (for
 * example an approval that conflicts because the case was already recovered).
 * The message must survive that transition so the operator still learns why
 * their request did not apply.
 *
 * No retry control is offered: a failed mutation is never blindly repeated.
 */
export function CaseMutationBanner({
  mutation,
  onDismiss,
}: CaseMutationBannerProps) {
  if (mutation.status !== "error") {
    return null;
  }

  return (
    <div className="space-y-2">
      {mutation.conflict ? (
        <div
          className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
          role="status"
        >
          <p className="font-medium">This case changed</p>
          <p className="mt-1">
            The case was updated while your request was in progress. The latest
            state has been loaded — review it before trying another action.
          </p>
        </div>
      ) : null}

      <ErrorState error={mutation.error} />

      <button
        type="button"
        onClick={onDismiss}
        className="rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-medium text-neutral-800 hover:bg-neutral-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
      >
        Dismiss
      </button>
    </div>
  );
}
