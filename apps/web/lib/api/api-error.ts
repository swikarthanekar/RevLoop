export type ApiErrorKind = "http" | "network" | "timeout" | "parse";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly safeMessage: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;
  readonly kind: ApiErrorKind;

  constructor(options: {
    status: number;
    code: string;
    safeMessage: string;
    details?: Record<string, unknown>;
    requestId?: string | null;
    kind?: ApiErrorKind;
  }) {
    super(options.safeMessage);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.safeMessage = options.safeMessage;
    this.details = options.details ?? {};
    this.requestId = options.requestId ?? null;
    this.kind = options.kind ?? "http";
  }
}

interface BackendErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
    request_id?: string;
  };
}

export function parseBackendErrorEnvelope(
  status: number,
  body: unknown,
): ApiError | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const envelope = body as BackendErrorEnvelope;
  const error = envelope.error;
  if (!error || typeof error !== "object") {
    return null;
  }
  const code = typeof error.code === "string" ? error.code : "UNKNOWN_ERROR";
  const message =
    typeof error.message === "string" && error.message.trim()
      ? error.message.trim()
      : "The request could not be completed.";
  const details =
    typeof error.details === "object" && error.details !== null
      ? (error.details as Record<string, unknown>)
      : {};
  const requestId =
    typeof error.request_id === "string" ? error.request_id : null;
  return new ApiError({
    status,
    code,
    safeMessage: message,
    details,
    requestId,
    kind: "http",
  });
}

export function genericApiError(
  kind: ApiErrorKind,
  safeMessage: string,
  status = 0,
): ApiError {
  const code =
    kind === "timeout"
      ? "REQUEST_TIMEOUT"
      : kind === "network"
        ? "NETWORK_ERROR"
        : kind === "parse"
          ? "INVALID_RESPONSE"
          : "UNKNOWN_ERROR";
  return new ApiError({
    status,
    code,
    safeMessage,
    kind,
  });
}
