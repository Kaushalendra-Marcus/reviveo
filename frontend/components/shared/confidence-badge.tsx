import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { RiskTier } from "@/lib/types";

const RISK_STYLES: Record<RiskTier, string> = {
  low: "bg-emerald-50 text-emerald-700 border-emerald-200",
  medium: "bg-amber-50 text-amber-800 border-amber-200",
  safe: "bg-slate-100 text-slate-700 border-slate-200",
};

/** Shows the numeric confidence plus the risk tier it maps to — never color
 * alone, per the spec's accessibility requirement. */
export function ConfidenceBadge({
  confidence,
  riskTier,
  className,
}: {
  confidence: number;
  riskTier?: RiskTier;
  className?: string;
}) {
  const pct = Math.round(confidence * 100);
  return (
    <Badge
      variant="outline"
      className={cn(
        "rounded-full font-medium tabular-nums",
        riskTier ? RISK_STYLES[riskTier] : "bg-slate-100 text-slate-700 border-slate-200",
        className
      )}
    >
      {pct}% confidence
    </Badge>
  );
}
