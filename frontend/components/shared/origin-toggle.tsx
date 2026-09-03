"use client";

import { cn } from "@/lib/utils";
import type { DataOrigin } from "@/lib/types";

export type OriginFilter = DataOrigin | "";

const ORIGIN_OPTIONS: { value: OriginFilter; label: string }[] = [
  { value: "", label: "All" },
  { value: "live_test_mode", label: "Live" },
  { value: "synthetic", label: "Synthetic" },
];

/** Lets the dashboard isolate real Razorpay-verified events from the bulk
 * synthetic demo data seeded for the batch/simulation story — without this,
 * every chart on Overview blends both together and one real live event is
 * invisible next to ~80 synthetic ones. */
export function OriginToggle({ value, onChange }: { value: OriginFilter; onChange: (v: OriginFilter) => void }) {
  return (
    <div className="inline-flex items-center rounded-lg border border-slate-200 bg-white p-0.5">
      {ORIGIN_OPTIONS.map((opt) => (
        <button
          key={opt.value || "all"}
          type="button"
          onClick={() => onChange(opt.value)}
          className={cn(
            "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
            value === opt.value ? "bg-emerald-50 text-emerald-700" : "text-slate-500 hover:text-slate-900"
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
