import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const replaceMock = vi.fn();
let searchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
  useSearchParams: () => searchParams,
}));

const getSession = vi.fn();
const onAuthStateChange = vi.fn();
const signInWithPassword = vi.fn();

vi.mock("@/lib/auth/supabase-client", () => ({
  getSupabaseClient: () => ({
    auth: { getSession, onAuthStateChange, signOut: vi.fn(), signInWithPassword },
  }),
}));

import { AuthSessionProvider } from "@/lib/auth/session";
import { LoginForm } from "@/app/login/login-form";

const ORIGINAL_SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ORIGINAL_SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

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
  replaceMock.mockReset();
  searchParams = new URLSearchParams();
  getSession.mockReset();
  onAuthStateChange.mockReset();
  onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } });
  signInWithPassword.mockReset();
});

function configureSupabase() {
  process.env.NEXT_PUBLIC_SUPABASE_URL = "https://project.supabase.co";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "anon-key-value";
}

function renderForm() {
  return render(
    <AuthSessionProvider>
      <LoginForm />
    </AuthSessionProvider>,
  );
}

describe("LoginForm — dev mode (Supabase not configured)", () => {
  it("explains that sign-in is not required, with no form fields", () => {
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

    renderForm();

    expect(screen.getByText(/Sign-in is not required here/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
  });
});

describe("LoginForm — Supabase configured", () => {
  it("renders the email/password form", () => {
    configureSupabase();
    getSession.mockResolvedValue({ data: { session: null } });

    renderForm();

    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("redirects to the default page on successful sign-in", async () => {
    configureSupabase();
    getSession.mockResolvedValue({ data: { session: null } });
    signInWithPassword.mockResolvedValue({ error: null });

    renderForm();
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "admin@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/dashboard");
    });
    expect(signInWithPassword).toHaveBeenCalledWith({
      email: "admin@example.com",
      password: "correct-password",
    });
  });

  it("redirects to a same-origin ?next= target instead of the default", async () => {
    configureSupabase();
    getSession.mockResolvedValue({ data: { session: null } });
    signInWithPassword.mockResolvedValue({ error: null });
    searchParams = new URLSearchParams({ next: "/recovery/abc-123" });

    renderForm();
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "admin@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/recovery/abc-123");
    });
  });

  it("never follows an external ?next= value", async () => {
    configureSupabase();
    getSession.mockResolvedValue({ data: { session: null } });
    signInWithPassword.mockResolvedValue({ error: null });
    searchParams = new URLSearchParams({ next: "https://evil.example.com" });

    renderForm();
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "admin@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/dashboard");
    });
  });

  it("shows an error and does not redirect on incorrect credentials", async () => {
    configureSupabase();
    getSession.mockResolvedValue({ data: { session: null } });
    signInWithPassword.mockResolvedValue({ error: { message: "Invalid login credentials" } });

    renderForm();
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "admin@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Incorrect email or password.",
    );
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("redirects immediately if a session already exists, without showing the form", async () => {
    configureSupabase();
    getSession.mockResolvedValue({
      data: { session: { access_token: "already-signed-in" } },
    });

    // The provider fetches /api/v1/auth/me via a real ApiClient here since
    // this test doesn't mock @/lib/api/api-client; make it resolve quickly
    // by stubbing global fetch used underneath.
    const originalFetch = global.fetch;
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      text: async () =>
        JSON.stringify({ user_id: "u1", organization_id: "o1", role: "ADMIN" }),
    }) as unknown as typeof fetch;

    renderForm();

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/dashboard");
    });

    global.fetch = originalFetch;
  });
});
