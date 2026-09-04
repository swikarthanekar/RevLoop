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
    href: "/dashboard#analytics",
    label: "Analytics",
    hint: "Coming in a later milestone",
  },
];
