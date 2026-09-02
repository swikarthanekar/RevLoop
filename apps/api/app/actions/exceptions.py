"""Recovery action domain errors (Prompt 16)."""


class RecoveryActionError(Exception):
    """Base error for recovery action execution."""


class ActionNotFoundError(RecoveryActionError):
    """Raised when an action cannot be found for the tenant."""


class CaseNotActionableError(RecoveryActionError):
    """Raised when the case cannot accept actions."""


class StaleRecommendationError(RecoveryActionError):
    """Raised when the recommendation/analysis run is no longer current."""


class ActionBlockedByPolicyError(RecoveryActionError):
    """Raised when policy blocks the requested action."""

    def __init__(self, *, reasons: tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__("Action blocked by policy.")


class UnsupportedActionError(RecoveryActionError):
    """Raised when Prompt 16 does not execute the requested action type."""


class ActionConflictError(RecoveryActionError):
    """Raised when an equivalent action already exists or blocks execution."""


class PaymentProviderError(RecoveryActionError):
    """Raised when provider returns a definitive failure."""


class PaymentProviderTimeoutError(RecoveryActionError):
    """Raised when provider timeout is known not to have created a side effect."""
