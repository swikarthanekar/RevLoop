import type { PolicyResponse } from "@/app/(app)/compliance/compliance-types";

export const policyFixture: PolicyResponse = {
  currency: "INR",
  auto_action_limit_minor: 500000,
  max_recovery_attempts: 4,
  max_contacts_per_24h: 2,
  minimum_auto_confidence: 0.7,
  cooldown_minutes: 90,
  automation_enabled: true,
  allowed_action_types: [
    "WAIT",
    "RETRY_SAME_METHOD",
    "REQUEST_ALTERNATE_PAYMENT_METHOD",
    "CREATE_PAYMENT_LINK",
    "SEND_RECOVERY_MESSAGE",
    "ESCALATE_TO_HUMAN",
    "STOP",
  ],
  manual_contact_approval_action_types: ["ESCALATE_TO_HUMAN"],
  contact_action_types: ["SEND_RECOVERY_MESSAGE", "CREATE_PAYMENT_LINK"],
  cooldown_action_types: ["SEND_RECOVERY_MESSAGE", "CREATE_PAYMENT_LINK"],
};

export const automationDisabledPolicyFixture: PolicyResponse = {
  ...policyFixture,
  automation_enabled: false,
};
