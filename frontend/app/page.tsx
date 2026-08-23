import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  LockKeyhole,
  Play,
  Radar,
  ReceiptText,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import RecoveryPipelineDiagram from "@/components/RecoveryPipelineDiagram";

const workflow = [
  { label: "Payment Event", icon: ReceiptText },
  { label: "Detect", icon: Radar },
  { label: "Analyze", icon: BrainCircuit },
  { label: "AI Decision", icon: RefreshCw },
  { label: "Guardrails", icon: LockKeyhole },
  { label: "Execute", icon: CheckCircle2 },
  { label: "Outcome", icon: ShieldCheck },
];

const steps = [
  {
    number: "01",
    title: "Detect",
    text: "Capture failed payments and at-risk revenue signals in real time.",
  },
  {
    number: "02",
    title: "Analyze",
    text: "Understand the root cause using payment and customer context.",
  },
  {
    number: "03",
    title: "Recover",
    text: "Choose and execute the safest recovery action within guardrails.",
  },
  {
    number: "04",
    title: "Measure",
    text: "Attribute recovered revenue only when the payment succeeds.",
  },
];

const safety = [
  {
    title: "Policy-defined actions",
    text: "AI can only choose from explicitly approved recovery actions.",
  },
  {
    title: "Built-in guardrails",
    text: "Retry, cooldown, confidence, and amount limits are always enforced.",
  },
  {
    title: "Human approval",
    text: "Large or uncertain recovery actions can wait for human approval.",
  },
  {
    title: "Complete audit trail",
    text: "Every decision, action, and outcome remains traceable.",
  },
];

export default function Home() {
  return (
    <main className="min-h-screen overflow-x-hidden bg-white text-slate-950">
      {/* HEADER */}
      <header className="absolute inset-x-0 top-0 z-30">
        <div className="mx-auto flex h-24 max-w-7xl items-center justify-between px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-3">
            <Image
              src="/logo.png"
              alt="Reviveo"
              width={48}
              height={48}
              className="size-11 object-contain"
              priority
            />

            <div className="flex flex-col">
              <span className="text-2xl font-bold tracking-tight text-slate-950">
                Reviveo
              </span>

              <span className="text-xs font-medium text-slate-500">
                AI Revenue Recovery Agent
              </span>
            </div>
          </Link>

          <nav className="hidden items-center gap-9 text-sm font-medium text-slate-700 lg:flex">
            <a
              href="#product"
              className="transition-colors hover:text-blue-700"
            >
              Product
            </a>

            <a
              href="#how-it-works"
              className="transition-colors hover:text-blue-700"
            >
              How It Works
            </a>

            <a
              href="#safety"
              className="transition-colors hover:text-blue-700"
            >
              Safety
            </a>

            <a
              href="#dashboard"
              className="transition-colors hover:text-blue-700"
            >
              Dashboard
            </a>
          </nav>

          <div className="flex items-center gap-4">
            <Button
              asChild
              variant="ghost"
              className="hidden font-medium text-slate-700 md:inline-flex"
            >
              <Link href="/login">Log in</Link>
            </Button>

            <Button
              asChild
              className="rounded-xl bg-gradient-to-r from-blue-700 to-blue-600 px-6 shadow-lg shadow-blue-500/20 hover:from-blue-800 hover:to-blue-700"
            >
              <Link href="/dashboard">
                View Dashboard
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>
        </div>
      </header>

      {/* HERO */}
      <section className="relative min-h-[860px] overflow-hidden">
        {/* Provided background image */}
        <div className="absolute inset-0">
          <Image
            src="/hero-bg-image.png"
            alt=""
            fill
            priority
            className="object-cover object-center"
          />
        </div>

        {/* White overlay for readable content */}
        <div className="absolute inset-0 bg-white/15" />

        {/* Soft center light */}
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.88)_0%,rgba(255,255,255,0.5)_35%,rgba(255,255,255,0.08)_75%)]" />

        <div className="relative z-10 mx-auto flex min-h-[860px] max-w-7xl flex-col items-center justify-center px-6 pb-20 pt-36 text-center lg:px-8">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-white/60 px-5 py-2 backdrop-blur-md">
            <span className="flex size-5 items-center justify-center text-blue-700">
              <span className="text-base">✦</span>
            </span>

            <span className="text-sm font-semibold uppercase tracking-[0.14em] text-blue-800">
              AI-Powered Revenue Recovery
            </span>
          </div>

          {/* Main headline */}
          <h1 className="mt-9 max-w-5xl text-5xl font-bold tracking-[-0.045em] text-slate-950 sm:text-6xl lg:text-8xl">
            Recover revenue
            <br />
            <span className="bg-gradient-to-r from-blue-700 to-blue-500 bg-clip-text text-transparent">
              before it disappears.
            </span>
          </h1>

          {/* Description */}
          <p className="mt-7 max-w-3xl text-lg leading-8 text-slate-600 sm:text-xl">
            Reviveo detects failed and at-risk payments, understands the root
            cause, chooses the right recovery action, and brings your revenue
            back — automatically and safely.
          </p>

          {/* CTA */}
          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Button
              asChild
              size="lg"
              className="h-16 rounded-xl bg-gradient-to-r from-blue-700 to-blue-600 px-8 text-base shadow-xl shadow-blue-500/25 hover:from-blue-800 hover:to-blue-700"
            >
              <Link href="/dashboard">
                Start Recovering Revenue
                <ArrowRight className="size-5" />
              </Link>
            </Button>

            <Button
              asChild
              size="lg"
              variant="outline"
              className="h-16 rounded-xl border-slate-300 bg-white/65 px-8 text-base backdrop-blur-md hover:bg-white"
            >
              <a href="#how-it-works">
                <Play className="size-4 fill-current" />
                See How It Works
              </a>
            </Button>
          </div>

          {/* Trust indicators */}
          <div className="mt-12 flex flex-wrap items-center justify-center gap-x-8 gap-y-4 text-sm font-medium text-slate-600">
            <div className="flex items-center gap-2">
              <ShieldCheck className="size-5 text-blue-600" />
              <span>Enterprise-grade security</span>
            </div>

            <span className="hidden size-1 rounded-full bg-slate-400 sm:block" />

            <div className="flex items-center gap-2">
              <LockKeyhole className="size-5 text-blue-600" />
              <span>Built-in guardrails</span>
            </div>

            <span className="hidden size-1 rounded-full bg-slate-400 sm:block" />

            <div className="flex items-center gap-2">
              <CheckCircle2 className="size-5 text-blue-600" />
              <span>Full audit trail</span>
            </div>
          </div>
        </div>
      </section>

      {/* PRODUCT WORKFLOW */}
      <section id="product" className="relative border-b border-slate-200 bg-white py-24">
        <div className="mx-auto max-w-7xl px-6 lg:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <p className="text-sm font-bold uppercase tracking-[0.18em] text-blue-700">
              The Recovery Engine
            </p>

            <h2 className="mt-4 text-4xl font-bold tracking-tight sm:text-5xl">
              One intelligent recovery loop.
            </h2>

            <p className="mt-5 text-lg leading-8 text-slate-600">
              From the first payment signal to verified recovered revenue,
              Reviveo manages the complete recovery lifecycle.
            </p>
          </div>

          <div className="mt-16 rounded-3xl border border-slate-200 bg-slate-50/80 p-5 shadow-sm lg:p-8">
            <div className="grid gap-3 md:grid-cols-7">
              {workflow.map((item, index) => {
                const Icon = item.icon;

                return (
                  <div key={item.label} className="relative">
                    <div className="flex min-h-32 flex-col items-center justify-center rounded-2xl border border-slate-200 bg-white p-4 text-center transition-transform duration-200 hover:-translate-y-1">
                      <div className="flex size-11 items-center justify-center rounded-xl bg-blue-50 text-blue-700">
                        <Icon className="size-5" />
                      </div>

                      <p className="mt-3 text-sm font-semibold text-slate-900">
                        {item.label}
                      </p>
                    </div>

                    {index < workflow.length - 1 && (
                      <div className="absolute left-[calc(100%-5px)] top-1/2 z-10 hidden w-5 border-t border-dashed border-blue-300 md:block" />
                    )}
                  </div>
                );
              })}
            </div>

            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
                <p className="font-semibold text-amber-950">
                  Human approval when needed
                </p>

                <p className="mt-2 text-sm leading-6 text-amber-800">
                  High-value or uncertain recovery actions pause before
                  execution.
                </p>
              </div>

              <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5">
                <p className="font-semibold text-rose-950">
                  Safe failure handling
                </p>

                <p className="mt-2 text-sm leading-6 text-rose-800">
                  Blocked actions are explained and logged instead of silently
                  repeating.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section id="how-it-works" className="py-24">
        <div className="mx-auto max-w-7xl px-6 lg:px-8">
          <div className="flex flex-col justify-between gap-8 lg:flex-row lg:items-end">
            <div className="max-w-2xl">
              <p className="text-sm font-bold uppercase tracking-[0.18em] text-blue-700">
                How it works
              </p>

              <h2 className="mt-4 text-4xl font-bold tracking-tight sm:text-5xl">
                From payment failure to revenue recovered.
              </h2>
            </div>

            <p className="max-w-md text-slate-600">
              Reviveo combines payment signals, AI reasoning, and strict
              operational guardrails into a measurable recovery system.
            </p>
          </div>

          <div className="mt-16 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map((step) => (
              <div
                key={step.title}
                className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-lg"
              >
                <span className="text-sm font-bold text-blue-600">
                  {step.number}
                </span>

                <h3 className="mt-10 text-xl font-bold">{step.title}</h3>

                <p className="mt-3 text-sm leading-7 text-slate-600">
                  {step.text}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>
      
      <section>
        <RecoveryPipelineDiagram/>
      </section>
      {/* DASHBOARD */}
      <section
        id="dashboard"
        className="border-y border-slate-200 bg-slate-50 py-24"
      >
        <div className="mx-auto grid max-w-7xl items-center gap-14 px-6 lg:grid-cols-[0.85fr_1.15fr] lg:px-8">
          <div>
            <p className="text-sm font-bold uppercase tracking-[0.18em] text-blue-700">
              Merchant dashboard
            </p>

            <h2 className="mt-4 text-4xl font-bold tracking-tight sm:text-5xl">
              See every recovery decision.
            </h2>

            <p className="mt-6 text-lg leading-8 text-slate-600">
              Monitor payment events, recovery performance, AI decisions,
              approvals, guardrails, and outcomes from one operational
              workspace.
            </p>

            <Button asChild size="lg" className="mt-8">
              <Link href="/dashboard">
                Open Dashboard
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>

          <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl shadow-slate-300/40">
            <Image
              src="/sample.png"
              alt="Reviveo dashboard preview"
              width={1536}
              height={1024}
              className="h-auto w-full"
            />
          </div>
        </div>
      </section>

      {/* SAFETY */}
      <section id="safety" className="bg-slate-950 py-24 text-white">
        <div className="mx-auto grid max-w-7xl gap-14 px-6 lg:grid-cols-[0.8fr_1.2fr] lg:px-8">
          <div>
            <p className="text-sm font-bold uppercase tracking-[0.18em] text-blue-400">
              Safety first
            </p>

            <h2 className="mt-4 text-4xl font-bold tracking-tight sm:text-5xl">
              AI acts within boundaries.
            </h2>

            <p className="mt-6 max-w-lg text-lg leading-8 text-slate-400">
              Reviveo is designed for controlled autonomy. The agent can reason
              and act, but policy and guardrails define exactly what it is
              allowed to do.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {safety.map((item) => (
              <div
                key={item.title}
                className="rounded-2xl border border-white/10 bg-white/[0.04] p-6"
              >
                <ShieldCheck className="size-6 text-blue-400" />

                <h3 className="mt-5 font-semibold">{item.title}</h3>

                <p className="mt-3 text-sm leading-6 text-slate-400">
                  {item.text}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

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