import {
  LayoutDashboard,
  ListChecks,
  RotateCcw,
  Users,
  Layers,
  ScrollText,
  FlaskConical,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { label: "Events", href: "/events", icon: ListChecks },
  { label: "Recoveries", href: "/recoveries", icon: RotateCcw },
  { label: "Customers", href: "/customers", icon: Users },
  { label: "Strategies", href: "/strategies", icon: Layers },
  { label: "Audit Trail", href: "/audit-trail", icon: ScrollText },
  { label: "Reports", href: "/reports", icon: FlaskConical },
  { label: "Settings", href: "/settings", icon: Settings },
];
