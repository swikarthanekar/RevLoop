import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const getSession = vi.fn();
const onAuthStateChange = vi.fn();
const signOut = vi.fn();
const apiGet = vi.fn();

vi.mock("@/lib/auth/supabase-client", () => ({
  getSupabaseClient: () => ({
    auth: { getSession, onAuthStateChange, signOut },
  }),
}));

vi.mock("@/lib/api/api-client", () => ({
  createDefaultApiClient: () => ({ get: apiGet }),
}));

import { AuthSessionProvider, useAuthSession } from "@/lib/auth/session";

const ORIGINAL_SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ORIGINAL_SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const ORIGINAL_DEV_TOKEN = process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN;

afterEach(() => {
  if (ORIGINAL_SUPABASE_URL === undefined) {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
  } else {
    process.env.NEXT_PUBLIC_SUPABASE_URL = ORIGINAL_SUPABASE_URL;
  }
  if (ORIGINAL_SUPABASE_ANON_KEY === undefined) {
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  } else {
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = ORIGINAL_SUPABASE_ANON_KEY;
  }
  if (ORIGINAL_DEV_TOKEN === undefined) {
    delete process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN;
  } else {
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = ORIGINAL_DEV_TOKEN;
  }
  getSession.mockReset();
  onAuthStateChange.mockReset();
  onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } });
  signOut.mockReset();
  apiGet.mockReset();
});

function configureSupabase() {
  process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "anon-key-value";
}

function Probe() {
  const session = useAuthSession();
  return (
    <div>
      <span data-testid="status">{session.status}</span>
      <span data-testid="role">{session.role ?? "none"}</span>
      <button onClick={() => void session.signOut()}>sign out</button>
    </div>
  );
}

function renderProbe() {
  return render(
    <AuthSessionProvider>
      <Probe />
    </AuthSessionProvider>,
  );
}

describe("AuthSessionProvider — dev mode (Supabase not configured)", () => {
  it("resolves synchronously to authenticated with the dev-token role, no network calls", () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = "dev-operator";

    renderProbe();

    // No "loading" flash: correct on the very first render, no useEffect tick needed.
    expect(screen.getByTestId("status")).toHaveTextContent("authenticated");
    expect(screen.getByTestId("role")).toHaveTextContent("OPERATOR");
    expect(getSession).not.toHaveBeenCalled();
    expect(apiGet).not.toHaveBeenCalled();
  });

  it("is still authenticated with a null role when no dev token is set", () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    delete process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN;

    renderProbe();

    expect(screen.getByTestId("status")).toHaveTextContent("authenticated");
    expect(screen.getByTestId("role")).toHaveTextContent("none");
  });
});

describe("AuthSessionProvider — Supabase configured", () => {
  it("starts loading, then reports unauthenticated with no session", async () => {
    configureSupabase();
    getSession.mockResolvedValue({ data: { session: null } });

    renderProbe();

    expect(screen.getByTestId("status")).toHaveTextContent("loading");
    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
    });
    expect(apiGet).not.toHaveBeenCalled();
  });

  it("resolves the role from /api/v1/auth/me once a session exists", async () => {
    configureSupabase();
    getSession.mockResolvedValue({
      data: { session: { access_token: "jwt-value" } },
    });
    apiGet.mockResolvedValue({
      user_id: "u1",
      organization_id: "o1",
      role: "ADMIN",
    });

    renderProbe();

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated");
    });
    expect(screen.getByTestId("role")).toHaveTextContent("ADMIN");
    expect(apiGet).toHaveBeenCalledWith("/api/v1/auth/me");
  });

  it("treats a session the backend rejects as unauthenticated, not a broken half-state", async () => {
    configureSupabase();
    getSession.mockResolvedValue({
      data: { session: { access_token: "expired-or-unlinked" } },
    });
    apiGet.mockRejectedValue(new Error("401"));

    renderProbe();

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
    });
    expect(screen.getByTestId("role")).toHaveTextContent("none");
  });

  it("signOut() calls supabase.auth.signOut()", async () => {
    configureSupabase();
    getSession.mockResolvedValue({ data: { session: null } });
    signOut.mockResolvedValue({ error: null });

    renderProbe();
    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated");
    });

    screen.getByRole("button", { name: "sign out" }).click();
    await waitFor(() => {
      expect(signOut).toHaveBeenCalledTimes(1);
    });
  });
});
