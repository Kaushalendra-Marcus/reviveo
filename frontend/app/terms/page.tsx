import type { Metadata } from "next";

import { SiteNav } from "@/components/homepage/site-nav";
import { Footer } from "@/components/homepage/footer";

export const metadata: Metadata = {
  title: "Terms of Service — Reviveo",
  description: "Terms for using the Reviveo demo build.",
};

export default function TermsOfServicePage() {
  return (
    <>
      <SiteNav />
      <main className="min-h-screen bg-white text-slate-950">
        <div className="mx-auto max-w-3xl px-6 pt-40 pb-24 lg:px-8">
          <p className="text-sm font-bold uppercase tracking-[0.18em] text-blue-700">
            Legal
          </p>
          <h1 className="mt-4 text-4xl font-bold tracking-tight">Terms of Service</h1>
          <p className="mt-4 text-sm text-slate-500">
            Reviveo is currently a prototype built for experimentation and
            demonstration, running against Razorpay&apos;s test environment. By
            using this build, you agree to the terms below.
          </p>

          <div className="mt-10 space-y-8 text-sm leading-7 text-slate-700">
            <section>
              <h2 className="text-lg font-semibold text-slate-950">
                No production use
              </h2>
              <p className="mt-2">
                This build is not intended to process real customer payments or
                make binding financial decisions. All recovery actions run
                against Razorpay test-mode credentials unless explicitly
                configured otherwise, and every AI-proposed action is bounded by
                the deterministic guardrail layer described on the homepage.
              </p>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-slate-950">
                Provided as-is
              </h2>
              <p className="mt-2">
                Reviveo is provided without warranty of any kind, express or
                implied, including fitness for a particular purpose. Metrics
                shown in demo or simulation mode (including any modeled
                recovery-rate comparisons) are labeled as such and are not a
                guarantee of real-world performance.
              </p>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-slate-950">
                Changes
              </h2>
              <p className="mt-2">
                These terms may change as the product moves from prototype to
                production. Material changes will be reflected on this page.
              </p>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-slate-950">Contact</h2>
              <p className="mt-2">
                Questions about these terms can be sent to{" "}
                <a
                  href="mailto:hello@reviveo.ai"
                  className="text-blue-700 underline underline-offset-4"
                >
                  hello@reviveo.ai
                </a>
                .
              </p>
            </section>
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}
