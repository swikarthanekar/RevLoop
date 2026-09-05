"""Which recovery actions RevLoop executes itself, and which it only recommends.

THE DISTINCTION

Ranking answers "which action is most valuable?". Execution answers "can this
system carry that action out?". They are different questions, and conflating
them is what produced the defect this module exists to close: the decision
engine selected `RETRY_SAME_METHOD` -- correctly, on expected value -- on most
cases, the UI offered an Execute button for it, and the executor then refused
with `422`, because RevLoop has no mechanism to perform it.

The engine now selects only from actions it can actually perform. Actions it
cannot perform are still generated, still scored by the model, and still ranked
and displayed with their true probability and expected value. Nothing is hidden:
the model's real preference stays visible, alongside a statement of why RevLoop
is not the component that acts on it.

WHY THESE TWO ARE ADVISORY

Both are deliberate P0 boundaries, documented before any of this was built, not
gaps left by accident:

- `RETRY_SAME_METHOD` -- RAZORPAY_INTEGRATION.md section 1 lists "direct
  autonomous same-method debit for one-time failures" under **Simulated in P0**,
  and DOMAIN_MODEL.md section 9 states "`RETRY_SAME_METHOD` is a strategy type.
  P0 does not invent unsupported direct payment debits." RevLoop holds no
  mandate or saved token for these customers, so re-attempting the original
  payment requires the customer to authorize it again. The merchant's own
  checkout owns that retry.

- `SEND_RECOVERY_MESSAGE` -- the same section lists "delivery of email/WhatsApp
  unless optional email adapter is added later" under **Simulated in P0**. No
  outreach channel is provisioned, so RevLoop cannot deliver a message.

Making either "executable" would mean either inventing a capability that does
not exist, or relabelling a Payment Link as something it is not. Both trade
honesty for a smoother demo, which is the wrong trade.

SINGLE SOURCE OF TRUTH

This module is the only place the executable set is defined. The action service
gates on it, candidate selection reads it, and the API serves it to the frontend
per candidate, so no client hardcodes a second copy that can drift.
"""

from __future__ import annotations

from enum import Enum

from app.domain.enums import PAYMENT_LINK_MECHANISM_ACTIONS, RecoveryActionType


class ActionExecutionMode(str, Enum):
    """Whether RevLoop performs an action, or only recommends it."""

    #: RevLoop carries this out itself -- a provider call, a schedule, or a
    #: state transition it owns.
    EXECUTABLE = "EXECUTABLE"
    #: RevLoop can rank and recommend this, but something outside RevLoop
    #: performs it. Offering an execute control for it would be a lie.
    ADVISORY = "ADVISORY"


#: Actions RevLoop performs itself.
#:
#: `WAIT` and `STOP` are state transitions RevLoop owns outright.
#: `ESCALATE_TO_HUMAN` records a handoff. The payment-link mechanism actions
#: (`CREATE_PAYMENT_LINK`, `REQUEST_ALTERNATE_PAYMENT_METHOD`) both resolve to a
#: real Razorpay Payment Link -- see `PAYMENT_LINK_MECHANISM_ACTIONS`.
EXECUTABLE_ACTION_TYPES: frozenset[RecoveryActionType] = (
    frozenset(
        {
            RecoveryActionType.WAIT,
            RecoveryActionType.STOP,
            RecoveryActionType.ESCALATE_TO_HUMAN,
        }
    )
    | PAYMENT_LINK_MECHANISM_ACTIONS
)

ADVISORY_ACTION_TYPES: frozenset[RecoveryActionType] = (
    frozenset(RecoveryActionType) - EXECUTABLE_ACTION_TYPES
)

#: Stable machine-readable code naming the missing capability. Served to
#: clients and recorded in analysis factors, so the reason survives into the
#: audit trail rather than living only in UI copy.
ADVISORY_REASON_CODE: dict[RecoveryActionType, str] = {
    RecoveryActionType.RETRY_SAME_METHOD: "NO_AUTONOMOUS_DEBIT_CAPABILITY",
    RecoveryActionType.SEND_RECOVERY_MESSAGE: "NO_OUTREACH_DELIVERY_CHANNEL",
}

#: One plain sentence per advisory action, written to be read by a merchant
#: operator rather than an engineer. A bare "advisory" badge reads as
#: unfinished; saying why it is advisory is the point.
ADVISORY_REASON_TEXT: dict[RecoveryActionType, str] = {
    RecoveryActionType.RETRY_SAME_METHOD: (
        "RevLoop holds no mandate or saved payment token for this customer, so "
        "it cannot re-attempt the original payment without the customer "
        "authorizing it again — your checkout owns that retry. RevLoop executes "
        "the highest-ranked action it can carry out itself."
    ),
    RecoveryActionType.SEND_RECOVERY_MESSAGE: (
        "No email or WhatsApp delivery channel is provisioned in this "
        "deployment, so RevLoop cannot send this message itself. RevLoop "
        "executes the highest-ranked action it can carry out itself."
    ),
}


def execution_mode(action: RecoveryActionType) -> ActionExecutionMode:
    """Whether RevLoop performs `action` itself."""
    if action in EXECUTABLE_ACTION_TYPES:
        return ActionExecutionMode.EXECUTABLE
    return ActionExecutionMode.ADVISORY


def is_executable(action: RecoveryActionType) -> bool:
    return action in EXECUTABLE_ACTION_TYPES


def advisory_reason_code(action: RecoveryActionType) -> str | None:
    """Machine-readable capability gap, or None when RevLoop executes it."""
    return ADVISORY_REASON_CODE.get(action)


def advisory_reason_text(action: RecoveryActionType) -> str | None:
    """Operator-facing explanation, or None when RevLoop executes it."""
    return ADVISORY_REASON_TEXT.get(action)


__all__ = [
    "ADVISORY_ACTION_TYPES",
    "ADVISORY_REASON_CODE",
    "ADVISORY_REASON_TEXT",
    "EXECUTABLE_ACTION_TYPES",
    "ActionExecutionMode",
    "advisory_reason_code",
    "advisory_reason_text",
    "execution_mode",
    "is_executable",
]
