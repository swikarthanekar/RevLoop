export type UserRole = "ANALYST" | "OPERATOR" | "ADMIN";

const DEV_TOKEN_ROLE: Record<string, UserRole> = {
  "dev-analyst": "ANALYST",
  "dev-operator": "OPERATOR",
  "dev-admin": "ADMIN",
};

/**
 * Best-effort, UI-only role hint derived from the current dev-mode bearer
 * token (`NEXT_PUBLIC_DEV_AUTH_TOKEN`).
 *
 * This exists purely so the recovery-case UI does not offer a control the
 * backend will always reject for this role (FRONTEND_SPEC.md section 6.E).
 * It grants nothing: `apps/api/app/api/routes/recovery_actions.py`'s
 * `require_execute_role`/`require_approval_role` dependencies are the sole
 * source of authorization truth, and every mutation is re-checked
 * server-side regardless of what this function returns.
 *
 * When production Supabase auth ships, this should read the role from the
 * verified session/JWT claims instead of the literal dev token string.
 */
export function currentUserRole(): UserRole | null {
  const token = process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN?.trim();
  if (!token) {
    return null;
  }
  return DEV_TOKEN_ROLE[token] ?? null;
}

/** Mirrors `_EXECUTE_ROLES` in apps/api/app/api/routes/recovery_actions.py. */
export function canExecuteActions(role: UserRole | null): boolean {
  return role === "OPERATOR" || role === "ADMIN";
}

/** Mirrors `_APPROVAL_ROLES` in apps/api/app/api/routes/recovery_actions.py. */
export function canApproveActions(role: UserRole | null): boolean {
  return role === "ADMIN";
}
