"use client";

import {
  Banknote,
  CheckCircle2,
  Clock,
  CreditCard,
  RefreshCw,
  ShieldAlert,
  XCircle,
  Zap,
} from "lucide-react";

export function ProblemStatement() {
  return (
    <section id="problem" className="relative border-y border-white/10 bg-slate-950 py-24 text-white overflow-hidden">
      {/* Background glow matching Hero gradient */}
      <div className="absolute left-1/2 top-1/2 -z-10 h-[600px] w-[900px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-blue-600/10 blur-[140px]" />

      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        {/* Section Header matching Hero text styling */}
        <div className="mx-auto max-w-3xl text-center">
          <div className="mx-auto flex w-fit items-center gap-2 rounded-full border border-blue-400/30 bg-white/10 px-5 py-2 backdrop-blur-md">
            <span className="text-base text-blue-300">✦</span>
            <span className="text-sm font-semibold uppercase tracking-[0.14em] text-blue-200">
              The Hidden Revenue Leak
            </span>
          </div>

          <h2 className="mt-6 text-4xl font-bold tracking-[-0.045em] text-white sm:text-5xl lg:text-7xl">
            Why <span className="bg-gradient-to-r from-blue-400 via-indigo-300 to-purple-300 bg-clip-text text-transparent">10-15% of your ARR</span> disappears every year.
          </h2>

          <p className="mt-6 text-lg leading-8 text-slate-300 sm:text-xl">
            Most subscription churn doesn&apos;t happen because customers want to cancel. It happens silently in the background when payment mandates fail, cards expire, or bank gateways drop transactions.
          </p>
        </div>

        {/* Big Problem Stats Grid matching Hero dark aesthetic */}
        <div className="mt-16 grid gap-6 sm:grid-cols-3">
          <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-8 backdrop-blur-sm">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-blue-500/15 text-blue-400">
              <Banknote className="size-6" />
            </div>
            <p className="mt-6 text-4xl sm:text-5xl font-bold tracking-tight text-white">12.4%</p>
            <p className="mt-2 text-sm font-semibold text-slate-200">Average ARR Lost to Payment Failure</p>
            <p className="mt-2 text-xs leading-5 text-slate-400">
              For a $1M ARR SaaS, over $120,000 is left on the table every year due to unrecovered billing failures.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-8 backdrop-blur-sm">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-blue-500/15 text-blue-400">
              <RefreshCw className="size-6" />
            </div>
            <p className="mt-6 text-4xl sm:text-5xl font-bold tracking-tight text-white">58%</p>
            <p className="mt-2 text-sm font-semibold text-slate-200">Involuntary Churn Share</p>
            <p className="mt-2 text-xs leading-5 text-slate-400">
              More than half of overall customer drop-offs are purely mechanical, not intentional cancellations.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-8 backdrop-blur-sm">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-blue-500/15 text-blue-400">
              <ShieldAlert className="size-6" />
            </div>
            <p className="mt-6 text-4xl sm:text-5xl font-bold tracking-tight text-white">74%</p>
            <p className="mt-2 text-sm font-semibold text-slate-200">Permanent Loss After Hard Locks</p>
            <p className="mt-2 text-xs leading-5 text-slate-400">
              When subscription access is locked abruptly by a hard failure, 3 out of 4 customers never return.
            </p>
          </div>
        </div>

        {/* The 4 Failure Causes Illustration & Breakdown */}
        <div className="mt-24">
          <div className="text-center">
            <p className="text-sm font-bold uppercase tracking-[0.18em] text-blue-400">
              Root Cause Matrix
            </p>
            <h3 className="mt-3 text-3xl font-bold tracking-tight text-white sm:text-4xl">
              Four distinct reasons why payments fail — and why one rule can&apos;t fix them all.
            </h3>
          </div>

          <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {/* Cause 1 */}
            <div className="group relative rounded-3xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-sm transition hover:border-blue-400/40 hover:bg-white/[0.05]">
              <div className="flex items-center justify-between">
                <div className="flex size-10 items-center justify-center rounded-xl bg-blue-500/15 text-blue-400">
                  <CreditCard className="size-5" />
                </div>
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-slate-200">
                  Card Expired
                </span>
              </div>
              <h4 className="mt-5 text-base font-semibold text-white">Expired / Re-issued Card</h4>
              <p className="mt-2 text-xs leading-5 text-slate-300">
                Card details changed or hit expiration date. Immediate retries will fail 100% of the time.
              </p>
              <div className="mt-6 flex items-center gap-2 rounded-xl border border-blue-400/20 bg-blue-500/10 p-3 text-xs font-medium text-blue-300">
                <Zap className="size-3.5 shrink-0 text-blue-400" />
                <span>Fix: Automated payment update link.</span>
              </div>
            </div>

            {/* Cause 2 */}
            <div className="group relative rounded-3xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-sm transition hover:border-indigo-400/40 hover:bg-white/[0.05]">
              <div className="flex items-center justify-between">
                <div className="flex size-10 items-center justify-center rounded-xl bg-indigo-500/15 text-indigo-400">
                  <Clock className="size-5" />
                </div>
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-slate-200">
                  Low Balance
                </span>
              </div>
              <h4 className="mt-5 text-base font-semibold text-white">Insufficient Funds</h4>
              <p className="mt-2 text-xs leading-5 text-slate-300">
                Recurring charge hit 24-48 hours before payday. Retrying immediately irritates customers.
              </p>
              <div className="mt-6 flex items-center gap-2 rounded-xl border border-indigo-400/20 bg-indigo-500/10 p-3 text-xs font-medium text-indigo-300">
                <Zap className="size-3.5 shrink-0 text-indigo-400" />
                <span>Fix: Smart Retry 24h window.</span>
              </div>
            </div>

            {/* Cause 3 */}
            <div className="group relative rounded-3xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-sm transition hover:border-purple-400/40 hover:bg-white/[0.05]">
              <div className="flex items-center justify-between">
                <div className="flex size-10 items-center justify-center rounded-xl bg-purple-500/15 text-purple-400">
                  <RefreshCw className="size-5" />
                </div>
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-slate-200">
                  Gateway Spike
                </span>
              </div>
              <h4 className="mt-5 text-base font-semibold text-white">Bank Downtime / Timeout</h4>
              <p className="mt-2 text-xs leading-5 text-slate-300">
                Temporary bank network outage or gateway connection drop during recurring debit.
              </p>
              <div className="mt-6 flex items-center gap-2 rounded-xl border border-purple-400/20 bg-purple-500/10 p-3 text-xs font-medium text-purple-300">
                <Zap className="size-3.5 shrink-0 text-purple-400" />
                <span>Fix: Cooldown check + retry.</span>
              </div>
            </div>

            {/* Cause 4 */}
            <div className="group relative rounded-3xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-sm transition hover:border-blue-400/40 hover:bg-white/[0.05]">
              <div className="flex items-center justify-between">
                <div className="flex size-10 items-center justify-center rounded-xl bg-blue-500/15 text-blue-400">
                  <ShieldAlert className="size-5" />
                </div>
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-slate-200">
                  Bank Decline
                </span>
              </div>
              <h4 className="mt-5 text-base font-semibold text-white">Bank Decline & 2FA Flag</h4>
              <p className="mt-2 text-xs leading-5 text-slate-300">
                Issuer declined auto-debit requiring customer authentication or fresh authorization.
              </p>
              <div className="mt-6 flex items-center gap-2 rounded-xl border border-blue-400/20 bg-blue-500/10 p-3 text-xs font-medium text-blue-300">
                <Zap className="size-3.5 shrink-0 text-blue-400" />
                <span>Fix: Approval Queue → Link.</span>
              </div>
            </div>
          </div>
        </div>

        {/* Comparison Graphic: Naive Dunning vs Reviveo Engine */}
        <div className="mt-24 rounded-3xl border border-white/10 bg-white/[0.02] p-8 backdrop-blur-md sm:p-12">
          <div className="mx-auto max-w-2xl text-center">
            <h3 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
              Why traditional dunning tools fail
            </h3>
            <p className="mt-2 text-sm text-slate-400">
              Most billing systems treat every failure the same — firing dumb retry loops until the card is blocked.
            </p>
          </div>

          <div className="mt-10 grid gap-8 md:grid-cols-2">
            {/* Traditional Dunning */}
            <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6">
              <div className="flex items-center gap-3">
                <div className="flex size-8 items-center justify-center rounded-full bg-red-500/20 text-red-400">
                  <XCircle className="size-4" />
                </div>
                <h4 className="font-semibold text-red-300">Traditional Naive Dunning</h4>
              </div>
              <ul className="mt-5 space-y-3 text-xs text-slate-300">
                <li className="flex items-start gap-2">
                  <span className="text-red-400">✕</span>
                  <span>Fires static, rigid retry schedules regardless of error reason</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-red-400">✕</span>
                  <span>Repeatedly hits expired or blocked cards, triggering bank fraud flags</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-red-400">✕</span>
                  <span>Cancels customer subscriptions abruptly with zero human oversight</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-red-400">✕</span>
                  <span>Low recovery rates (~20-30%) and high customer churn</span>
                </li>
              </ul>
            </div>

            {/* Reviveo Autonomous Recovery */}
            <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-6">
              <div className="flex items-center gap-3">
                <div className="flex size-8 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400">
                  <CheckCircle2 className="size-4" />
                </div>
                <h4 className="font-semibold text-emerald-300">Reviveo Autonomous Engine</h4>
              </div>
              <ul className="mt-5 space-y-3 text-xs text-slate-300">
                <li className="flex items-start gap-2">
                  <span className="text-emerald-400">✓</span>
                  <span>AI classifies root cause directly from Razorpay failure signals</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-emerald-400">✓</span>
                  <span>Confidence score & risk-tier based decisions (Low Risk = Auto, High Risk = Queue)</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-emerald-400">✓</span>
                  <span>Strict financial guardrails (Amount caps, cooldowns, contact limits)</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-emerald-400">✓</span>
                  <span>80%+ recovery rate with full audit trail and human control</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
