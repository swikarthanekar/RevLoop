import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "@/lib/api/api-client";
import { ApiError } from "@/lib/api/api-error";
import type { AccessTokenProvider } from "@/lib/auth/token-provider";

class StaticTokenProvider implements AccessTokenProvider {
  constructor(private readonly token: string | null) {}

  async getAccessToken(): Promise<string | null> {
    return this.token;
  }
}

function mockFetch(response: Partial<Response> & { jsonBody?: unknown; textBody?: string }) {
  return vi.fn(async (): Promise<Response> => {
    const textBody =
      response.textBody ??
      (response.jsonBody !== undefined ? JSON.stringify(response.jsonBody) : "");
    return {
      ok: response.ok ?? true,
      status: response.status ?? 200,
      headers: new Headers({
        "content-type": "application/json",
      }),
      text: async () => textBody,
    } as Response;
  });
}

function getRequestHeaders(
  fetchImpl: ReturnType<typeof vi.fn>,
): Headers {
  const init = fetchImpl.mock.calls[0]?.[1] as RequestInit | undefined;
  expect(init?.headers).toBeInstanceOf(Headers);
  return init!.headers as Headers;
}

describe("ApiClient", () => {
  it("returns typed JSON for successful GET", async () => {
    const fetchImpl = mockFetch({ jsonBody: { status: "ok" } });
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: new StaticTokenProvider(null),
      fetchImpl: fetchImpl as typeof fetch,
    });

    const payload = await client.get<{ status: string }>("/health");
    expect(payload.status).toBe("ok");
  });

  it("adds Bearer token when provider returns a token", async () => {
    const fetchImpl = mockFetch({ jsonBody: { status: "ok" } });
    const client = new ApiClient({
      baseUrl: "http://localhost:8000/",
      tokenProvider: new StaticTokenProvider("jwt-token-value"),
      fetchImpl: fetchImpl as typeof fetch,
    });

    await client.get("/health");
    const headers = getRequestHeaders(fetchImpl);
    expect(headers.get("Authorization")).toBe("Bearer jwt-token-value");
  });

  it("does not add Authorization when token is absent", async () => {
    const fetchImpl = mockFetch({ jsonBody: { status: "ok" } });
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: new StaticTokenProvider(null),
      fetchImpl: fetchImpl as typeof fetch,
    });

    await client.get("/health");
    const headers = getRequestHeaders(fetchImpl);
    expect(headers.get("Authorization")).toBeNull();
  });

  it("parses backend error envelope", async () => {
    const fetchImpl = mockFetch({
      ok: false,
      status: 409,
      jsonBody: {
        error: {
          code: "STALE_CASE_VERSION",
          message: "Case version is stale.",
          details: { case_id: "abc" },
          request_id: "req_test_1",
        },
      },
    });
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: new StaticTokenProvider(null),
      fetchImpl: fetchImpl as typeof fetch,
    });

    await expect(client.get("/api/v1/recovery-cases/1")).rejects.toEqual(
      expect.objectContaining<Partial<ApiError>>({
        status: 409,
        code: "STALE_CASE_VERSION",
        safeMessage: "Case version is stale.",
        requestId: "req_test_1",
      }),
    );
  });

  it("maps non-json 500 to safe ApiError", async () => {
    const fetchImpl = mockFetch({
      ok: false,
      status: 500,
      textBody: "<html>error</html>",
    });
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: new StaticTokenProvider(null),
      fetchImpl: fetchImpl as typeof fetch,
    });

    await expect(client.get("/health")).rejects.toMatchObject({
      kind: "http",
      status: 500,
    });
  });

  it("maps empty error body to safe ApiError", async () => {
    const fetchImpl = mockFetch({ ok: false, status: 502, textBody: "" });
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: new StaticTokenProvider(null),
      fetchImpl: fetchImpl as typeof fetch,
    });

    await expect(client.get("/health")).rejects.toMatchObject({
      kind: "http",
      status: 502,
    });
  });

  it("classifies network failures", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: new StaticTokenProvider(null),
      fetchImpl: fetchImpl as typeof fetch,
    });

    await expect(client.get("/health")).rejects.toMatchObject({
      kind: "network",
      code: "NETWORK_ERROR",
    });
  });

  it("classifies timeout failures", async () => {
    const fetchImpl = vi.fn(async (_url: RequestInfo, init?: RequestInit): Promise<Response> => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    }) as typeof fetch;
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: new StaticTokenProvider(null),
      timeoutMs: 5,
      fetchImpl: fetchImpl as typeof fetch,
    });

    await expect(client.get("/health")).rejects.toMatchObject({
      kind: "timeout",
      code: "REQUEST_TIMEOUT",
    });
  });

  it("does not automatically retry failed requests", async () => {
    const fetchImpl = mockFetch({
      ok: false,
      status: 429,
      jsonBody: { error: { code: "RATE_LIMIT", message: "Too many requests" } },
    });
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: new StaticTokenProvider(null),
      fetchImpl: fetchImpl as typeof fetch,
    });

    await expect(client.get("/health")).rejects.toBeInstanceOf(ApiError);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("does not log or expose bearer token in error surfaces", async () => {
    const consoleSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const secret = "super-secret-jwt-token";
    const fetchImpl = mockFetch({
      ok: false,
      status: 401,
      jsonBody: {
        error: {
          code: "UNAUTHORIZED",
          message: "Authentication required",
        },
      },
    });
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: new StaticTokenProvider(secret),
      fetchImpl: fetchImpl as typeof fetch,
    });

    await expect(client.get("/health")).rejects.toMatchObject({
      safeMessage: "Authentication required",
    });

    const caught = await client.get("/health").catch((error: unknown) => error);
    expect(JSON.stringify(caught)).not.toContain(secret);
    expect(consoleSpy).not.toHaveBeenCalled();
    consoleSpy.mockRestore();
  });
});
