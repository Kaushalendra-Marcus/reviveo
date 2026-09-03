"use client";

import { Download } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { CAUSE_LABELS } from "@/lib/formatters";
import { downloadExport } from "@/lib/api";
import { toast } from "sonner";
import type { Cause, DataOrigin, EventStatus } from "@/lib/types";

const STATUS_OPTIONS: EventStatus[] = [
  "detected",
  "analyzing",
  "action_selected",
  "approval_pending",
  "scheduled",
  "executing",
  "waiting_for_outcome",
  "recovered",
  "expired",
  "escalated",
  "closed",
  "failed",
];

const CAUSE_OPTIONS = Object.keys(CAUSE_LABELS) as Cause[];

const ORIGIN_OPTIONS: { value: DataOrigin; label: string }[] = [
  { value: "live_test_mode", label: "Live (Razorpay-verified)" },
  { value: "synthetic", label: "Synthetic (demo)" },
];

export function EventsToolbar({
  status,
  cause,
  origin,
  onStatusChange,
  onCauseChange,
  onOriginChange,
  showExport = true,
}: {
  status: EventStatus | "";
  cause: Cause | "";
  origin: DataOrigin | "";
  onStatusChange: (status: EventStatus | "") => void;
  onCauseChange: (cause: Cause | "") => void;
  onOriginChange: (origin: DataOrigin | "") => void;
  showExport?: boolean;
}) {
  async function handleExport(format: "csv" | "json") {
    try {
      await downloadExport(format, status || undefined, cause || undefined);
    } catch {
      toast.error("Export failed", { description: "Could not reach the Reviveo API." });
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select value={status || "all"} onValueChange={(v) => onStatusChange(v === "all" ? "" : (v as EventStatus))}>
        <SelectTrigger className="h-9 w-[170px]" size="default">
          <SelectValue placeholder="All statuses" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All statuses</SelectItem>
          {STATUS_OPTIONS.map((s) => (
            <SelectItem key={s} value={s}>
              {s.replace(/_/g, " ")}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={cause || "all"} onValueChange={(v) => onCauseChange(v === "all" ? "" : (v as Cause))}>
        <SelectTrigger className="h-9 w-[170px]" size="default">
          <SelectValue placeholder="All root causes" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All root causes</SelectItem>
          {CAUSE_OPTIONS.map((c) => (
            <SelectItem key={c} value={c}>
              {CAUSE_LABELS[c]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={origin || "all"} onValueChange={(v) => onOriginChange(v === "all" ? "" : (v as DataOrigin))}>
        <SelectTrigger className="h-9 w-[200px]" size="default">
          <SelectValue placeholder="All sources" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All sources</SelectItem>
          {ORIGIN_OPTIONS.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {showExport ? (
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => handleExport("csv")}>
            <Download className="size-3.5" />
            CSV
          </Button>
          <Button variant="outline" size="sm" onClick={() => handleExport("json")}>
            <Download className="size-3.5" />
            JSON
          </Button>
        </div>
      ) : null}
    </div>
  );
}
