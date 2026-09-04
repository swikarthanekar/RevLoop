import type { LucideIcon } from "lucide-react";
import { BarChart3, LayoutDashboard, ShieldCheck, Target } from "lucide-react";

export interface AppNavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  disabled?: boolean;
  hint?: string;
}

export const PRIMARY_NAV_ITEMS: AppNavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/recovery", label: "Recovery Opportunities", icon: Target },
  { href: "/compliance", label: "Compliance Guardrails", icon: ShieldCheck },
  {
    href: "/dashboard#analytics",
    label: "Analytics",
    icon: BarChart3,
    hint: "Coming in a later milestone",
  },
];
