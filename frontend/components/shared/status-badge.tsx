import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { titleCase } from "@/lib/formatters";
import type { EventStatus } from "@/lib/types";

/** Color coding is a secondary signal only — the label text always carries
 * the status, never color alone (frontend-implementation.txt accessibility). */
const STATUS_STYLES: Record<EventStatus, string> = {
  detected: "bg-slate-100 text-slate-700 border-slate-200",
  analyzing: "bg-slate-100 text-slate-700 border-slate-200",
  action_selected: "bg-blue-50 text-blue-700 border-blue-200",
  approval_pending: "bg-amber-50 text-amber-800 border-amber-200",
  scheduled: "bg-blue-50 text-blue-700 border-blue-200",
  executing: "bg-blue-50 text-blue-700 border-blue-200",
  waiting_for_outcome: "bg-indigo-50 text-indigo-700 border-indigo-200",
  recovered: "bg-emerald-50 text-emerald-700 border-emerald-200",
  expired: "bg-slate-100 text-slate-600 border-slate-200",
  escalated: "bg-amber-50 text-amber-800 border-amber-200",
  closed: "bg-slate-100 text-slate-600 border-slate-200",
  failed: "bg-red-50 text-red-700 border-red-200",
};

export function StatusBadge({ status, className }: { status: EventStatus; className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn("rounded-full font-medium", STATUS_STYLES[status], className)}
    >
      {titleCase(status)}
    </Badge>
  );
}
