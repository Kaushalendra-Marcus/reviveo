import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import RecoveryPipelineDiagram from "@/components/RecoveryPipelineDiagram";
import { DecisionContext } from "@/components/homepage/decision-context";
import { BoundedAutonomy } from "@/components/homepage/bounded-autonomy";
import { Hero } from "@/components/homepage/hero";

export default function Home() {
  return (
    <main className="min-h-screen overflow-x-hidden bg-white text-slate-950">
      {/* HERO — includes its own header/nav (desktop floating navbar + mobile drawer) */}
      <Hero />

      {/* THE RECOVERY ENGINE — the central architecture diagram, the main visual identity of the product */}
      <RecoveryPipelineDiagram />

      {/* HOW REVIVEO DECIDES — signal / context / decision / action */}
      <DecisionContext />

      {/* SAFETY — bounded autonomy, single focused idea instead of a generic feature grid */}
      <BoundedAutonomy />

      {/* FINAL CTA */}
      <section className="py-24">
        <div className="mx-auto max-w-4xl px-6 text-center lg:px-8">
          <h2 className="text-4xl font-bold tracking-tight sm:text-5xl">
            Stop letting failed payments become lost revenue.
          </h2>

          <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-slate-600">
            Open Reviveo and see how payment failures move through the complete
            recovery lifecycle.
          </p>

          <Button
            asChild
            size="lg"
            className="mt-9 h-16 rounded-xl bg-gradient-to-r from-blue-700 to-blue-600 px-8 text-base"
          >
            <Link href="/dashboard">
              View Dashboard
              <ArrowRight className="size-5" />
            </Link>
          </Button>
        </div>
      </section>
    </main>
  );
}
