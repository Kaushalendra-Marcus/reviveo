import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import RecoveryPipelineDiagram from "@/components/RecoveryPipelineDiagram";
import { DecisionContext } from "@/components/homepage/decision-context";
import { BoundedAutonomy } from "@/components/homepage/bounded-autonomy";
import { Hero } from "@/components/homepage/hero";
import { Footer } from "@/components/homepage/footer";
import { SiteNav } from "@/components/homepage/site-nav";
import { ProblemStatement } from "@/components/homepage/problem-statement";
import { IntegrationCarousel } from "@/components/homepage/integration-carousel";
import { ProductHighlights } from "@/components/homepage/product-highlights";

export default function Home() {
  return (
    <>
      {/* Sibling of <main>, not nested inside it — <main> has overflow-x-hidden,
          which (like Hero's own overflow-hidden) clips `position: fixed`
          descendants. Keeping SiteNav outside is what lets it stay fixed for
          the whole page instead of disappearing past the hero. */}
      <SiteNav />

      <main className="min-h-screen overflow-x-hidden bg-white text-slate-950">
        {/* HERO — background + content only now; nav lives in <SiteNav /> above */}
        <Hero />

        {/* THE INVISIBLE LEAK — problem statement & root causes breakdown */}
        <ProblemStatement />

        {/* THE RECOVERY ENGINE — the central architecture diagram, the main visual identity of the product */}
        <section id="product">
          <RecoveryPipelineDiagram />
        </section>

        {/* INTEGRATION ORBITAL — Antimetal-inspired logo carousel */}
        <IntegrationCarousel />

        {/* WHY TEAMS CHOOSE REVIVEO — individual spotlight-effect feature cards */}
        <ProductHighlights />

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
              variant="brand"
              className="mt-9 h-16 rounded-xl px-8 text-base"
            >
              <Link href="/dashboard">
                View Dashboard
                <ArrowRight className="size-5" />
              </Link>
            </Button>
          </div>
        </section>

        <Footer />
      </main>
    </>
  );
}
