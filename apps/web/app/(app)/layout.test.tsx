import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  usePathname: () => "/recovery/abc-123",
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...rest
  }: {
    children: React.ReactNode;
    href: string;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const apiGet = vi.fn();
vi.mock("@/lib/api/api-client", () => ({
  ApiClient: class MockApiClient {
    get = vi.fn().mockResolvedValue({ status: "ok" });
  },
  createDefaultApiClient: () => ({ get: apiGet }),
}));

const getSession = vi.fn();
const onAuthStateChange = vi.fn();
vi.mock("@/lib/auth/supabase-client", () => ({
  getSupabaseClient: () => ({
    auth: { getSession, onAuthStateChange, signOut: vi.fn() },
  }),
}));

import ShellLayout from "@/app/(app)/layout";
import { AuthSessionProvider } from "@/lib/auth/session";

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
  replaceMock.mockReset();
  apiGet.mockReset();
  getSession.mockReset();
  onAuthStateChange.mockReset();
  onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } });
});

function configureSupabase() {
  process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "anon-key-value";
}

function renderLayout() {
  return render(
    <AuthSessionProvider>
      <ShellLayout>
        <div>Protected content</div>
      </ShellLayout>
    </AuthSessionProvider>,
  );
}

describe("(app) ShellLayout guard — dev mode", () => {
  it("renders children directly, no redirect", () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN = "dev-admin";

    renderLayout();

    expect(screen.getByText("Protected content")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });
});

describe("(app) ShellLayout guard — Supabase configured", () => {
  it("shows a loading state before the session resolves", () => {
    configureSupabase();
    getSession.mockReturnValue(new Promise(() => {})); // never resolves

    renderLayout();

    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });

  it("redirects to /login with a next param when there is no session", async () => {
    configureSupabase();
    getSession.mockResolvedValue({ data: { session: null } });

    renderLayout();

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith(
        "/login?next=%2Frecovery%2Fabc-123",
      );
    });
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });

  it("renders children inside the app shell once authenticated", async () => {
    configureSupabase();
    getSession.mockResolvedValue({
      data: { session: { access_token: "jwt-value" } },
    });
    apiGet.mockResolvedValue({ user_id: "u1", organization_id: "o1", role: "ADMIN" });

    renderLayout();

    await waitFor(() => {
      expect(screen.getByText("Protected content")).toBeInTheDocument();
    });
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
