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
  // Reaching this now means a client submitted an action the server does not
  // execute — capability-aware selection should prevent it. It is mapped
  // anyway: the generic 422 fallback rendered "Validation failed — The request
  // could not be validated. Review the input and try again" on a form with no
  // input, which told the user nothing and invited them to press the same
  // button again.
  ACTION_NOT_EXECUTABLE: {
    title: "RevLoop does not perform this action",
    message:
      "This action is a recommendation RevLoop hands to your systems, not one it carries out itself.",
    guidance:
      "Pick an action RevLoop executes, or re-analyze the case to get a fresh recommendation.",
  },
  ACTION_NOT_IN_ANALYSIS: {
    title: "Recommendation is out of date",
    message: "This action is not part of the case's current analysis run.",
    guidance: "Refresh the case to load the current recommendation.",
  },
  CASE_ALREADY_RESOLVED: {
    title: "Case already resolved",
    message: "This case has reached a terminal state and accepts no further actions.",
    guidance: "Refresh to see the final outcome.",
  },
  ACTION_NOT_PENDING_APPROVAL: {
    title: "Nothing left to approve",
    message: "This action is no longer awaiting approval.",
    guidance: "Refresh the case to see its current state.",
  },
  ROLE_NOT_ALLOWED: {
    title: "Insufficient permission",
    message: "Your role cannot perform this operation.",
    guidance: "Ask an operator or admin to complete it.",
  },
  DEMO_RESET_NOT_ENABLED: {
    title: "Demo reset is switched off",
    message: "Reset rebuilds the demo tenant and is disabled on this deployment.",
    guidance: "No data was changed. Enable DEMO_RESET_ENABLED to allow it.",
  },
  MODEL_UNAVAILABLE_AND_NO_FALLBACK: {
    title: "Model unavailable",
    message: "The recovery model could not score this case.",
    guidance:
      "No recommendation was recorded and the case is unchanged. Try again shortly.",
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
    // Most 422s here are server-side rules rejecting a request, not a
    // malformed form. "Review the input" was actively misleading on screens
    // with no input at all.
    title: "Request was rejected",
    message: "The server did not accept this request in the case's current state.",
    guidance: "Refresh the case to see the latest state before trying again.",
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
