import type { AccessTokenProvider } from "@/lib/auth/token-provider";
import {
  ApiError,
  genericApiError,
  parseBackendErrorEnvelope,
} from "@/lib/api/api-error";
import { API_REQUEST_TIMEOUT_MS, getApiBaseUrl } from "@/lib/config/public";

export interface ApiClientOptions {
  baseUrl: string;
  tokenProvider: AccessTokenProvider;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}

function joinUrl(baseUrl: string, path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${baseUrl.replace(/\/$/, "")}${normalizedPath}`;
}

async function readResponseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  const text = await response.text();
  if (!text) {
    return null;
  }
  if (contentType.includes("application/json")) {
    try {
      return JSON.parse(text) as unknown;
    } catch {
      return null;
    }
  }
  return null;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly tokenProvider: AccessTokenProvider;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(options: ApiClientOptions) {
    this.baseUrl = options.baseUrl;
    this.tokenProvider = options.tokenProvider;
    this.timeoutMs = options.timeoutMs ?? API_REQUEST_TIMEOUT_MS;
    // `fetch` must keep its original receiver: browsers reject `window.fetch`
    // called with any other `this` ("Illegal invocation"), which would fail the
    // request before it is ever dispatched.
    this.fetchImpl =
      options.fetchImpl ?? ((input, init) => globalThis.fetch(input, init));
  }

  async request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);
    const headers = new Headers(options.headers ?? {});
    headers.set("Accept", "application/json");

    const token = await this.tokenProvider.getAccessToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    let body: BodyInit | undefined;
    if (options.body !== undefined) {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(options.body);
    }

    try {
      const response = await this.fetchImpl(joinUrl(this.baseUrl, path), {
        ...options,
        headers,
        body,
        signal: controller.signal,
      });

      const payload = await readResponseBody(response);
      if (!response.ok) {
        const parsed = parseBackendErrorEnvelope(response.status, payload);
        if (parsed) {
          throw parsed;
        }
        throw genericApiError(
          "http",
          "The request could not be completed.",
          response.status,
        );
      }

      if (payload === null) {
        throw genericApiError("parse", "The server returned an empty response.");
      }
      return payload as T;
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }
      if (error instanceof DOMException && error.name === "AbortError") {
        throw genericApiError("timeout", "The request timed out.");
      }
      if (error instanceof Error) {
        throw genericApiError("network", "Unable to reach the RevLoop API.");
      }
      throw genericApiError("network", "Unable to reach the RevLoop API.");
    } finally {
      clearTimeout(timeoutId);
    }
  }

  get<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  post<T>(path: string, body: unknown, options: ApiRequestOptions = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "POST", body });
  }
}

export function createDefaultApiClient(
  tokenProvider: AccessTokenProvider,
  overrides?: Partial<ApiClientOptions>,
): ApiClient {
  return new ApiClient({
    baseUrl: getApiBaseUrl(),
    tokenProvider,
    ...overrides,
  });
}
