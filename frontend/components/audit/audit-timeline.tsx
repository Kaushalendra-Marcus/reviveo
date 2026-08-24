import {
  Radar,
  Search,
  GitBranch,
  ShieldCheck,
  Zap,
  Flag,
  Bot,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/states";
import { formatDateTime } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import type { AuditEntryOut, AuditStage } from "@/lib/types";

const STAGE_META: Record<AuditStage, { label: string; icon: LucideIcon; color: string }> = {
  detected: { label: "Detected", icon: Radar, color: "bg-slate-100 text-slate-600" },
  analyzed: { label: "Analyzed", icon: Search, color: "bg-slate-100 text-slate-600" },
  decided: { label: "Decided", icon: GitBranch, color: "bg-blue-100 text-blue-700" },
  guardrail: { label: "Guardrail Check", icon: ShieldCheck, color: "bg-amber-100 text-amber-700" },
  executed: { label: "Executed", icon: Zap, color: "bg-indigo-100 text-indigo-700" },
  outcome: { label: "Outcome", icon: Flag, color: "bg-emerald-100 text-emerald-700" },
};

export function AuditTimeline({ entries }: { entries: AuditEntryOut[] }) {
  if (entries.length === 0) {
    return <EmptyState title="No audit entries yet" message="Stages appear here as the pipeline processes this event." />;
  }

  return (
    <ol className="relative space-y-6 pl-1">
      {entries.map((entry, idx) => {
        const meta = STAGE_META[entry.stage] ?? STAGE_META.detected;
        const Icon = meta.icon;
        const isLast = idx === entries.length - 1;
        return (
          <li key={entry.id} className="relative flex gap-4">
            {!isLast ? (
              <span className="absolute top-9 left-[15px] h-[calc(100%_-_4px)] w-px bg-slate-200" aria-hidden />
            ) : null}
            <div
              className={cn(
                "z-10 flex size-8 shrink-0 items-center justify-center rounded-full ring-4 ring-white",
                meta.color
              )}
            >
              <Icon className="size-4" />
            </div>
            <div className="min-w-0 flex-1 pb-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-slate-900">{meta.label}</p>
                <span className="text-xs text-slate-400">{formatDateTime(entry.created_at)}</span>
                {entry.ai_used ? (
                  <Badge variant="outline" className="gap-1 rounded-full border-blue-200 bg-blue-50 text-[11px] text-blue-700">
                    <Bot className="size-3" />
                    {entry.ai_model ?? "AI"}
                    {entry.ai_latency_ms !== null ? ` · ${entry.ai_latency_ms}ms` : ""}
                  </Badge>
                ) : null}
                {entry.fallback_triggered ? (
                  <Badge variant="outline" className="gap-1 rounded-full border-amber-200 bg-amber-50 text-[11px] text-amber-700">
                    <TriangleAlert className="size-3" />
                    Fallback used
                  </Badge>
                ) : null}
              </div>
              {entry.message ? <p className="mt-1 text-sm text-slate-600">{entry.message}</p> : null}
              {Object.keys(entry.payload ?? {}).length > 0 ? (
                <pre className="mt-2 overflow-x-auto rounded-lg bg-slate-50 px-3 py-2 font-mono text-[11px] leading-relaxed text-slate-600">
                  {JSON.stringify(entry.payload, null, 2)}
                </pre>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
