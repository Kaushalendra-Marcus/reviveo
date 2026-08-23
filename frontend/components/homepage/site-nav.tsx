'use client'

import React from 'react'
import Image from 'next/image'
import Link from 'next/link'
import { ArrowRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { TimelineAnimation } from '@/components/ui/timeline-animation'
import { useMediaQuery } from '@/hooks/use-media-query'
import MotionDrawer from '@/components/ui/motion-drawer'

// Site-wide floating navbar for the marketing pages. Rendered as a sibling
// of <main> in page.tsx (NOT nested inside Hero's overflow-hidden section)
// so `fixed` positioning isn't clipped once the user scrolls past the hero —
// browsers clip `position: fixed` descendants to any ancestor with
// non-visible overflow, which was silently hiding the old in-hero navbar.
export const SiteNav = () => {
  const navRef = React.useRef<HTMLDivElement>(null)
  const isMobile = useMediaQuery('(max-width: 768px)')

  return (
    // transform-gpu + will-change-transform force this onto its own GPU
    // compositing layer. Without it, a fixed + backdrop-blur + rounded-corner
    // element like this pill has to recompute its blur against newly-scrolled
    // content every frame, which is the classic WebKit/Chromium combo that
    // makes a fixed blurred nav visibly flicker/shrink mid-scroll.
    <div
      ref={navRef}
      className="fixed inset-x-0 top-0 z-50 transform-gpu will-change-transform"
    >
      {/* Mobile top bar */}
      {isMobile && (
        <div className="flex w-full items-center justify-between gap-4 px-5 pt-4">
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
        <header className="mx-auto w-full max-w-7xl px-6 pt-6 lg:px-8">
          <TimelineAnimation
            animationNum={1}
            timelineRef={navRef}
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
    </div>
  )
}
