import { Fragment } from "react";
import { Antenna, ArrowDown, ArrowRight, BrainCircuit, CheckCircle2, Layers, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type StageTone = "neutral" | "intelligence" | "control";

interface Stage {
  icon: LucideIcon;
  label: string;
  description: string;
  tone: StageTone;
}

const stages: Stage[] = [
  {
    icon: Antenna,
    label: "Signal",
    description: "A payment event or risk signal enters Reviveo.",
    tone: "neutral",
  },
  {
    icon: Layers,
    label: "Context",
    description:
      "Reviveo combines relevant payment, customer, subscription, and historical context.",
    tone: "neutral",
  },
  {
    icon: BrainCircuit,
    label: "Decision",
    description: "The AI evaluates the situation and selects from allowed recovery actions.",
    tone: "intelligence",
  },
  {
    icon: CheckCircle2,
    label: "Action",
    description: "The decision is executed only after policy and guardrail checks pass.",
    tone: "control",
  },
];

const toneCard: Record<StageTone, string> = {
  neutral: "border-slate-200 bg-white",
  intelligence: "border-blue-200 bg-blue-50",
  control: "border-slate-800 bg-slate-950",
};

const toneIconWrap: Record<StageTone, string> = {
  neutral: "bg-slate-100 text-slate-600",
  intelligence: "bg-blue-100 text-blue-700",
  control: "bg-white/10 text-white",
};

const toneLabel: Record<StageTone, string> = {
  neutral: "text-slate-900",
  intelligence: "text-blue-950",
  control: "text-white",
};

const toneText: Record<StageTone, string> = {
  neutral: "text-slate-500",
  intelligence: "text-blue-700",
  control: "text-slate-300",
};

export function DecisionContext() {
  return (
    <section id="how-it-works" className="border-b border-slate-200 bg-slate-50 py-24">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-bold uppercase tracking-[0.18em] text-blue-700">
            Inside the intelligence layer
          </p>
          <h2 className="mt-4 text-3xl font-bold tracking-tight sm:text-4xl">
            How Reviveo actually decides.
          </h2>
        </div>

        <div className="mt-14 flex flex-col items-stretch gap-4 md:flex-row md:items-stretch md:gap-0">
          {stages.map((stage, index) => (
            <Fragment key={stage.label}>
              <div
                className={cn(
                  "flex flex-1 flex-col items-center rounded-2xl border px-5 py-6 text-center shadow-sm",
                  toneCard[stage.tone]
                )}
              >
                <div
                  className={cn(
                    "flex size-10 items-center justify-center rounded-full",
                    toneIconWrap[stage.tone]
                  )}
                >
                  <stage.icon className="size-5" />
                </div>

                <p
                  className={cn(
                    "mt-3 text-xs font-bold uppercase tracking-[0.14em]",
                    toneText[stage.tone]
                  )}
                >
                  {String(index + 1).padStart(2, "0")}
                </p>

                <p className={cn("mt-1 text-base font-semibold", toneLabel[stage.tone])}>
                  {stage.label}
                </p>

                <p className={cn("mt-2 text-sm leading-6", toneText[stage.tone])}>
                  {stage.description}
                </p>
              </div>

              {index < stages.length - 1 && (
                <div className="flex items-center justify-center py-1 text-slate-300 md:px-3 md:py-0">
                  <ArrowDown className="size-5 md:hidden" />
                  <ArrowRight className="hidden size-5 md:block" />
                </div>
              )}
            </Fragment>
          ))}
        </div>
      </div>
    </section>
  );
}
