import Image from "next/image";
import Link from "next/link";
import { ArrowRight, CheckCircle2, LockKeyhole, Play, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import RecoveryPipelineDiagram from "@/components/RecoveryPipelineDiagram";
import { DecisionContext } from "@/components/homepage/decision-context";
import { BoundedAutonomy } from "@/components/homepage/bounded-autonomy";

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
              width={58}
              height={58}
              className="size-16 object-contain"
              preload
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

            <Link
              href="/dashboard"
              className="transition-colors hover:text-blue-700"
            >
              Dashboard
            </Link>
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
            preload
            sizes="100vw"
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
