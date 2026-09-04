import type { Metadata } from "next";
import Link from "next/link";

import { SiteNav } from "@/components/homepage/site-nav";
import { Footer } from "@/components/homepage/footer";

export const metadata: Metadata = {
  title: "Privacy Policy — Reviveo",
  description: "How Reviveo handles data in its current test/demo build.",
};

export default function PrivacyPolicyPage() {
  return (
    <>
      <SiteNav />
      <main className="min-h-screen bg-white text-slate-950">
        <div className="mx-auto max-w-3xl px-6 pt-40 pb-24 lg:px-8">
          <p className="text-sm font-bold uppercase tracking-[0.18em] text-blue-700">
            Legal
          </p>
          <h1 className="mt-4 text-4xl font-bold tracking-tight">Privacy Policy</h1>
          <p className="mt-4 text-sm text-slate-500">
            Reviveo is currently an AI revenue-recovery prototype running against
            Razorpay&apos;s test environment. This page describes how the current
            build handles data — it is not a substitute for a formal legal
            policy, which will be published before any production customer data
            is processed.
          </p>

          <div className="mt-10 space-y-8 text-sm leading-7 text-slate-700">
            <section>
              <h2 className="text-lg font-semibold text-slate-950">
                What data this build touches
              </h2>
              <p className="mt-2">
                The current demo runs on Razorpay test-mode credentials and a
                synthetic batch of simulated payment events for a fictional demo
                merchant. No real customer payment data is processed by this
                build.
              </p>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-slate-950">
                Data recorded during a session
              </h2>
              <p className="mt-2">
                Where a live Razorpay test-mode flow is used, Reviveo stores the
                webhook payloads, decisions, guardrail checks, and outcomes
                needed to power the audit trail — the same records described in
                the product&apos;s{" "}
                <Link href="/" className="text-blue-700 underline underline-offset-4">
                  architecture overview
                </Link>
                .
              </p>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-slate-950">
                Third parties
              </h2>
              <p className="mt-2">
                Payment processing runs through Razorpay (test mode). AI-assisted
                decisions, where enabled, are processed by Anthropic&apos;s
                Claude API. Neither is configured to receive real customer data
                in this build.
              </p>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-slate-950">Contact</h2>
              <p className="mt-2">
                Questions about this build can be sent to{" "}
                <a
                  href="mailto:yadavkausha4a5@gmail.com"
                  className="text-blue-700 underline underline-offset-4"
                >
                  yadavkausha4a5@gmail.com
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
