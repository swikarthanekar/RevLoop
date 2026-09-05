export interface AppNavItem {
  href: string;
  label: string;
  disabled?: boolean;
  hint?: string;
}

export const PRIMARY_NAV_ITEMS: AppNavItem[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/recovery", label: "Recovery Opportunities" },
  { href: "/compliance", label: "Compliance Guardrails" },
  {
    href: "/simulator",
    label: "Decision Simulator",
    hint: "Score a hypothetical failure live",
  },
  {
    href: "/proof",
    label: "Model Evidence",
    hint: "Held-out policy evaluation",
  },
  {
    href: "/provider-events",
    label: "Provider Events",
    hint: "Webhook signature and dedup decisions",
  },
  {
    href: "/dashboard#analytics",
    label: "Analytics",
    // Previously "Coming in a later milestone", which under-sold finished work:
    // the link scrolls to charts that are live and backend-fed.
    hint: "Recovery trend, action effectiveness, failure mix",
  },
];
