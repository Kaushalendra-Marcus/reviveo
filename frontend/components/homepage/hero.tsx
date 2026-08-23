'use client'

import React from 'react'
import Image from 'next/image'
import Link from 'next/link'
import { motion, useReducedMotion } from 'framer-motion'
import {
  ArrowRight,
  CheckCircle2,
  LockKeyhole,
  Play,
  ShieldCheck,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { TimelineAnimation } from '@/components/ui/timeline-animation'
import { useMediaQuery } from '@/hooks/use-media-query'
import MotionDrawer from '@/components/ui/motion-drawer'

export const Hero = () => {
  const timelineRef = React.useRef<HTMLDivElement>(null)
  const isMobile = useMediaQuery('(max-width: 768px)')
  const prefersReducedMotion = useReducedMotion()

  return (
    <section
      ref={timelineRef}
      className="relative min-h-dvh overflow-hidden bg-slate-950 text-slate-950"
    >
      {/* Background image (same asset the previous hero used) — soft fade/zoom-settle
          on entrance, then a slow, barely-visible ambient drift so the scene feels
          alive without competing with the text for attention. */}
      <motion.div
        className="absolute inset-0 h-full w-full"
        initial={{ opacity: 0, scale: 1.08 }}
        animate={
          prefersReducedMotion
            ? { opacity: 1, scale: 1 }
            : { opacity: 1, scale: [1.08, 1, 1.05, 1] }
        }
        transition={
          prefersReducedMotion
            ? { duration: 0.6, ease: 'easeOut' }
            : {
                opacity: { duration: 1.4, ease: 'easeOut' },
                scale: {
                  duration: 24,
                  times: [0, 0.08, 0.54, 1],
                  repeat: Infinity,
                  repeatType: 'loop',
                  ease: 'easeInOut',
                },
              }
        }
      >
        <Image
          src="/hero-bg_image.png"
          alt=""
          fill
          priority
          sizes="100vw"
          className="object-cover object-center"
        />
      </motion.div>
      {/*
        Depth vignette — the source image is already dark, so instead of a
        whiteout wash (which fought the dark palette and made the headline
        unreadable) this just deepens the far edges slightly for focus.
        Readability comes from light text colors below, not from washing
        the image out.
      */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_45%_at_50%_15%,rgba(2,6,23,0)_0%,rgba(2,6,23,0.15)_60%,rgba(2,6,23,0.4)_100%)]" />

      {/* Mobile top bar */}
      {isMobile && (
        <div className="relative z-20 flex w-full items-center justify-between gap-4 px-5 pt-4">
          <MotionDrawer
            direction="left"
            width={280}
            backgroundColor={'#ffffff'}
            clsBtnClassName="bg-slate-800 border-r border-slate-900 text-white"
            contentClassName="bg-white border-r border-slate-200 text-slate-950"
            btnClassName="bg-white text-slate-950 relative w-fit p-2 left-0 top-0 rounded-full shadow-xs border border-slate-200"
          >
            <nav className="space-y-4">
              <Link href="/" className="mb-2 flex items-center gap-2 text-slate-950">
                <Image
                  src="/logo.png"
                  alt="Reviveo"
                  width={28}
                  height={28}
                  className="size-7 object-contain"
                />
                <span className="font-bold">Reviveo</span>
              </Link>
              <a href="#product" className="block rounded-sm p-2 hover:bg-slate-100">
                Product
              </a>
              <a href="#how-it-works" className="block rounded-sm p-2 hover:bg-slate-100">
                How It Works
              </a>
              <a href="#safety" className="block rounded-sm p-2 hover:bg-slate-100">
                Safety
              </a>
              <Link href="/dashboard" className="block rounded-sm p-2 hover:bg-slate-100">
                Dashboard
              </Link>
            </nav>
          </MotionDrawer>

          <Button
            asChild
            size="sm"
            className="rounded-xl bg-gradient-to-r from-blue-700 to-blue-600"
          >
            <Link href="/dashboard">
              View Dashboard
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        </div>
      )}

      {/* Desktop header — floating pill navbar */}
      {!isMobile && (
        <header className="relative z-20 mx-auto w-full max-w-7xl px-6 pt-6 lg:px-8">
          <TimelineAnimation
            animationNum={1}
            timelineRef={timelineRef}
            className="flex items-center justify-between rounded-xl border border-white bg-white/80 p-2 shadow-sm backdrop-blur-xl"
          >
            <Link href="/" className="flex items-center gap-2 pl-2">
              <Image
                src="/logo.png"
                alt="Reviveo"
                width={32}
                height={32}
                className="size-8 object-contain"
              />
              <div className="flex flex-col leading-tight">
                <span className="text-base font-bold tracking-tight text-slate-950">
                  Reviveo
                </span>
                <span className="-mt-0.5 text-[10px] font-medium text-slate-500">
                  AI Revenue Recovery Agent
                </span>
              </div>
            </Link>

            <nav className="flex items-center gap-8 text-sm font-medium text-slate-600">
              <a href="#product" className="transition-colors hover:text-blue-700">
                Product
              </a>
              <a href="#how-it-works" className="transition-colors hover:text-blue-700">
                How It Works
              </a>
              <a href="#safety" className="transition-colors hover:text-blue-700">
                Safety
              </a>
              <Link href="/dashboard" className="transition-colors hover:text-blue-700">
                Dashboard
              </Link>
            </nav>

            <div className="flex items-center gap-2">
              <Button
                asChild
                variant="ghost"
                size="sm"
                className="font-medium text-slate-700"
              >
                <Link href="/login">Log in</Link>
              </Button>
              <Button
                asChild
                size="sm"
                className="rounded-lg bg-gradient-to-r from-blue-700 to-blue-600 hover:from-blue-800 hover:to-blue-700"
              >
                <Link href="/dashboard">
                  View Dashboard
                  <ArrowRight className="size-4" />
                </Link>
              </Button>
            </div>
          </TimelineAnimation>
        </header>
      )}

      {/* Hero content */}
      <div className="relative z-10 mx-auto flex max-w-7xl flex-col items-center gap-6 px-6 pb-20 pt-16 text-center lg:px-8">
        <TimelineAnimation
          animationNum={2}
          timelineRef={timelineRef}
          className="mx-auto flex w-fit items-center gap-2 rounded-full border border-blue-400/30 bg-white/10 px-5 py-2 backdrop-blur-md"
        >
          <span className="text-base text-blue-300">✦</span>
          <span className="text-sm font-semibold uppercase tracking-[0.14em] text-blue-200">
            AI-Powered Revenue Recovery
          </span>
        </TimelineAnimation>

        <TimelineAnimation
          as="h1"
          animationNum={3}
          timelineRef={timelineRef}
          className="mx-auto mt-3 max-w-5xl text-5xl font-bold tracking-[-0.045em] text-white sm:text-6xl lg:text-8xl"
        >
          Recover revenue
          <br />
          <span className="bg-gradient-to-r from-blue-400 via-indigo-300 to-purple-300 bg-clip-text text-transparent">
            before it disappears.
          </span>
        </TimelineAnimation>

        <TimelineAnimation
          as="p"
          animationNum={4}
          timelineRef={timelineRef}
          className="mx-auto max-w-3xl text-lg leading-8 text-slate-300 sm:text-xl"
        >
          Reviveo detects failed and at-risk payments, understands the root
          cause, chooses the right recovery action, and brings your revenue
          back — automatically and safely.
        </TimelineAnimation>

        <TimelineAnimation
          animationNum={5}
          timelineRef={timelineRef}
          className="mt-4 flex flex-col items-center justify-center gap-4 sm:flex-row"
        >
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
        </TimelineAnimation>

        <TimelineAnimation
          animationNum={6}
          timelineRef={timelineRef}
          className="mt-6 flex flex-wrap items-center justify-center gap-x-8 gap-y-4 text-sm font-medium text-slate-300"
        >
          <div className="flex items-center gap-2">
            <ShieldCheck className="size-5 text-blue-400" />
            <span>Enterprise-grade security</span>
          </div>

          <span className="hidden size-1 rounded-full bg-slate-500 sm:block" />

          <div className="flex items-center gap-2">
            <LockKeyhole className="size-5 text-blue-400" />
            <span>Built-in guardrails</span>
          </div>

          <span className="hidden size-1 rounded-full bg-slate-500 sm:block" />

          <div className="flex items-center gap-2">
            <CheckCircle2 className="size-5 text-blue-400" />
            <span>Full audit trail</span>
          </div>
        </TimelineAnimation>
      </div>
    </section>
  )
}
