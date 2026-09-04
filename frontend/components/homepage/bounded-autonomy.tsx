import { ShieldCheck } from "lucide-react";

const constraints = [
  "Policy-defined actions",
  "Retry limits",
  "Cooldown limits",
  "Confidence thresholds",
  "Amount limits",
  "Human approval for risky cases",
  "Complete audit trail",
];

export function BoundedAutonomy() {
  return (
    <section id="safety" className="bg-slate-950 py-24 text-white">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center lg:gap-16">
          <div>
            <p className="text-sm font-bold uppercase tracking-[0.18em] text-blue-400">
              Bounded autonomy
            </p>

            <h2 className="mt-4 text-3xl font-bold tracking-tight sm:text-4xl">
              The AI is not the final authority.
            </h2>

            <p className="mt-5 text-base leading-7 text-slate-300">
              Reviveo&apos;s AI can reason about a failed payment and recommend or take a
              recovery action, but it never acts outside limits your team defines. Every
              decision is bounded, every risky case is routed to a person, and every
              outcome is written to a trail your team can review.
            </p>
          </div>

          <div className="relative rounded-3xl border border-dashed border-white/20 bg-white/[0.03] p-8">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-full bg-blue-500/15 text-blue-400">
                <ShieldCheck className="size-5" />
              </div>
              <p className="text-sm font-semibold text-white">Guardrail boundary</p>
            </div>

            <div className="mt-6 flex flex-wrap gap-2">
              {constraints.map((item) => (
                <span
                  key={item}
                  className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-200"
                >
                  {item}
                </span>
              ))}
            </div>

            <p className="mt-6 text-xs leading-5 text-slate-400">
              The AI Decision Engine can only choose actions that already exist inside this
              boundary. Nothing it does can widen the boundary itself.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
