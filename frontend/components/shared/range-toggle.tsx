"use client";

import { RANGE_OPTIONS } from "@/lib/config";
import { cn } from "@/lib/utils";
import type { RangeDays } from "@/lib/types";

export function RangeToggle({ value, onChange }: { value: RangeDays; onChange: (v: RangeDays) => void }) {
  return (
    <div className="inline-flex items-center rounded-lg border border-slate-200 bg-white p-0.5">
      {RANGE_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={cn(
            "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
            value === opt.value ? "bg-blue-50 text-blue-700" : "text-slate-500 hover:text-slate-900"
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
