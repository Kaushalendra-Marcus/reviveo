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
import type { Cause, EventStatus } from "@/lib/types";

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

export function EventsToolbar({
  status,
  cause,
  onStatusChange,
  onCauseChange,
  showExport = true,
}: {
  status: EventStatus | "";
  cause: Cause | "";
  onStatusChange: (status: EventStatus | "") => void;
  onCauseChange: (cause: Cause | "") => void;
  showExport?: boolean;
}) {
  async function handleExport(format: "csv" | "json") {
    try {
      await downloadExport(format, status || undefined);
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
