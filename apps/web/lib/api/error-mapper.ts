import { ApiError } from "@/lib/api/api-error";

export interface ErrorPresentation {
  title: string;
  message: string;
  guidance: string;
}

const CODE_GUIDANCE: Record<string, ErrorPresentation> = {
  INVALID_CASE_STATE: {
    title: "Case changed",
    message: "This recovery case is no longer in the expected state.",
    guidance: "Refresh the case and review the latest status before retrying.",
  },
  ACTION_BLOCKED_BY_POLICY: {
    title: "Action blocked by policy",
    message: "The requested action is not permitted under current merchant policy.",
    guidance: "Review policy constraints instead of retrying the same action.",
  },
  ACTION_ALREADY_EXISTS: {
    title: "Action already exists",
    message: "A recovery action is already recorded for this case.",
    guidance: "Refetch the latest action details to avoid duplicate submissions.",
  },
  PAYMENT_PROVIDER_ERROR: {
    title: "Payment provider unavailable",
    message: "The payment provider could not complete the request.",
    guidance: "The recovery case remains safe. Try again later or review provider status.",
  },
  STALE_CASE_VERSION: {
    title: "Stale case version",
    message: "The case changed while this request was in progress.",
    guidance: "Refresh and review the latest case state before retrying.",
  },
};

const STATUS_FALLBACKS: Record<number, Omit<ErrorPresentation, "guidance"> & { guidance: string }> = {
  401: {
    title: "Authentication required",
    message: "Your session is unavailable or has expired.",
    guidance: "Sign in again to continue.",
  },
  403: {
    title: "Insufficient permission",
    message: "You do not have permission to perform this action.",
    guidance: "Contact an administrator if you need access.",
  },
  404: {
    title: "Resource unavailable",
    message: "The requested resource could not be found.",
    guidance: "Verify the link or refresh the page.",
  },
  409: {
    title: "Conflicting state",
    message: "The request conflicted with the current server state.",
    guidance: "Refresh before retrying.",
  },
  422: {
    title: "Validation failed",
    message: "The request could not be validated.",
    guidance: "Review the input and try again.",
  },
  429: {
    title: "Rate limited",
    message: "Too many requests were sent in a short period.",
    guidance: "Wait briefly before trying again.",
  },
  500: {
    title: "Service unavailable",
    message: "The service is temporarily unavailable.",
    guidance: "Try again shortly.",
  },
  502: {
    title: "Service unavailable",
    message: "An upstream service is temporarily unavailable.",
    guidance: "Try again shortly.",
  },
  503: {
    title: "Service unavailable",
    message: "The service is temporarily unavailable.",
    guidance: "Try again shortly.",
  },
};

export function mapApiError(error: ApiError): ErrorPresentation {
  if (error.kind === "timeout") {
    return {
      title: "Request timed out",
      message: "The request took too long to complete.",
      guidance: "Check connectivity and try again.",
    };
  }
  if (error.kind === "network") {
    return {
      title: "Connection problem",
      message: "Unable to reach the RevLoop API.",
      guidance: "Check your network connection and API availability.",
    };
  }
  if (error.kind === "parse") {
    return {
      title: "Unexpected response",
      message: "The server returned an unreadable response.",
      guidance: "Try again or contact support with the reference ID if shown.",
    };
  }

  const byCode = CODE_GUIDANCE[error.code];
  if (byCode) {
    return byCode;
  }

  if (error.status >= 500) {
    return STATUS_FALLBACKS[500];
  }

  const byStatus = STATUS_FALLBACKS[error.status];
  if (byStatus) {
    return byStatus;
  }

  return {
    title: "Request failed",
    message: error.safeMessage,
    guidance: "Try again or refresh the page.",
  };
}
