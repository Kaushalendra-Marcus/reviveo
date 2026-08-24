"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { RawLogResponse } from "@/lib/types";

function JsonBlock({ label, value, defaultOpen = false }: { label: string; value: unknown; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-xl border border-slate-200 bg-white">
      <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-left">
        <span className="text-sm font-semibold text-slate-900">{label}</span>
        <ChevronDown className={cn("size-4 text-slate-400 transition-transform", open && "rotate-180")} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <pre className="max-h-[420px] overflow-auto border-t border-slate-100 bg-slate-950 px-4 py-3 font-mono text-[11px] leading-relaxed text-slate-100">
          {JSON.stringify(value, null, 2)}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  );
}

/** Unfiltered internal state, straight from db.py rows — deliberately shows
 * more than the typed endpoints (e.g. SQLite 0/1 booleans) so this can act
 * as a genuine debug view rather than a prettier copy of the audit trail. */
export function RawLogPanel({ data }: { data: RawLogResponse }) {
  return (
    <div className="space-y-3">
      <JsonBlock label="Event Row" value={data.event} defaultOpen />
      <JsonBlock label={`Audit Log (${data.audit_log.length})`} value={data.audit_log} />
      <JsonBlock label={`Decisions (${data.decisions.length})`} value={data.decisions} />
      <JsonBlock label={`Recovery Attempts (${data.recovery_attempts.length})`} value={data.recovery_attempts} />
    </div>
  );
}
