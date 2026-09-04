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
const ORIGINAL_DEMO_EMAIL = process.env.NEXT_PUBLIC_DEMO_LOGIN_EMAIL;
const ORIGINAL_DEMO_PASSWORD = process.env.NEXT_PUBLIC_DEMO_LOGIN_PASSWORD;

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
  if (ORIGINAL_DEMO_EMAIL === undefined) {
    delete process.env.NEXT_PUBLIC_DEMO_LOGIN_EMAIL;
  } else {
    process.env.NEXT_PUBLIC_DEMO_LOGIN_EMAIL = ORIGINAL_DEMO_EMAIL;
  }
  if (ORIGINAL_DEMO_PASSWORD === undefined) {
    delete process.env.NEXT_PUBLIC_DEMO_LOGIN_PASSWORD;
  } else {
    process.env.NEXT_PUBLIC_DEMO_LOGIN_PASSWORD = ORIGINAL_DEMO_PASSWORD;
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

function configureDemoCredentials() {
  process.env.NEXT_PUBLIC_DEMO_LOGIN_EMAIL = "demo@example.com";
  process.env.NEXT_PUBLIC_DEMO_LOGIN_PASSWORD = "demo-password-value";
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

describe("LoginForm — demo sign-in button", () => {
  it("is not shown when no demo credentials are configured", () => {
    configureSupabase();
    getSession.mockResolvedValue({ data: { session: null } });

    renderForm();

    expect(
      screen.queryByRole("button", { name: "Continue as demo" }),
    ).not.toBeInTheDocument();
  });

  it("signs in with the configured demo credentials on click, without typing anything", async () => {
    configureSupabase();
    configureDemoCredentials();
    getSession.mockResolvedValue({ data: { session: null } });
    signInWithPassword.mockResolvedValue({ error: null });

    renderForm();
    fireEvent.click(screen.getByRole("button", { name: "Continue as demo" }));

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/dashboard");
    });
    expect(signInWithPassword).toHaveBeenCalledWith({
      email: "demo@example.com",
      password: "demo-password-value",
    });
  });

  it("honors a ?next= redirect target from the demo button too", async () => {
    configureSupabase();
    configureDemoCredentials();
    getSession.mockResolvedValue({ data: { session: null } });
    signInWithPassword.mockResolvedValue({ error: null });
    searchParams = new URLSearchParams({ next: "/recovery/abc-123" });

    renderForm();
    fireEvent.click(screen.getByRole("button", { name: "Continue as demo" }));

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/recovery/abc-123");
    });
  });

  it("shows a distinct error if the demo account itself is rejected", async () => {
    configureSupabase();
    configureDemoCredentials();
    getSession.mockResolvedValue({ data: { session: null } });
    signInWithPassword.mockResolvedValue({ error: { message: "Invalid login credentials" } });

    renderForm();
    fireEvent.click(screen.getByRole("button", { name: "Continue as demo" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Demo sign-in is temporarily unavailable. Use email/password below.",
    );
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("does not let the manual form and the demo button submit concurrently", async () => {
    configureSupabase();
    configureDemoCredentials();
    getSession.mockResolvedValue({ data: { session: null } });
    let resolveSignIn: (value: { error: null }) => void = () => {};
    signInWithPassword.mockReturnValue(
      new Promise((resolve) => {
        resolveSignIn = resolve;
      }),
    );

    renderForm();
    fireEvent.click(screen.getByRole("button", { name: "Continue as demo" }));

    // The manual submit button is now disabled too (shared `submitting`
    // state, so both buttons read "Signing in…"); a click on a disabled
    // button is a no-op in the DOM. Distinguish it from the demo button by
    // its actual type="submit".
    const submitButton = screen
      .getAllByRole("button", { name: /Sign in|Signing in/ })
      .find((button) => button.getAttribute("type") === "submit");
    expect(submitButton).toBeDisabled();
    fireEvent.click(submitButton as HTMLElement);

    resolveSignIn({ error: null });
    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/dashboard");
    });
    expect(signInWithPassword).toHaveBeenCalledTimes(1);
  });
});
