'use client'

import React from 'react'
import Image from 'next/image'
import Link from 'next/link'
import { ArrowRight, Menu } from 'lucide-react'
import { useMotionValueEvent, useScroll } from 'framer-motion'

import { Button } from '@/components/ui/button'
import { TimelineAnimation } from '@/components/ui/timeline-animation'
import { useMediaQuery } from '@/hooks/use-media-query'
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'

// Pill starts shrinking as soon as you've scrolled past this many pixels,
// and goes back to full width once you're back within it of the top.
const SCROLL_SHRINK_THRESHOLD = 8

const MOBILE_LINKS = [
  { href: '#product', label: 'Product' },
  { href: '#demo', label: 'Demo' },
  { href: '#how-it-works', label: 'How It Works' },
  { href: '#safety', label: 'Safety' },
]

// Site-wide floating navbar for the marketing pages. Rendered as a sibling
// of <main> in page.tsx (NOT nested inside Hero's overflow-hidden section)
// so `fixed` positioning isn't clipped once the user scrolls past the hero —
// browsers clip `position: fixed` descendants to any ancestor with
// non-visible overflow, which was silently hiding the old in-hero navbar.
export const SiteNav = () => {
  const navRef = React.useRef<HTMLDivElement>(null)
  const isMobile = useMediaQuery('(max-width: 768px)')
  const [isScrolled, setIsScrolled] = React.useState(false)
  const [isMobileNavOpen, setIsMobileNavOpen] = React.useState(false)

  const closeMobileNav = () => setIsMobileNavOpen(false)

  // Full-width pill at the top; shrinks a little once you scroll down,
  // back to full-width the moment you're back at the top.
  const { scrollY } = useScroll()
  useMotionValueEvent(scrollY, 'change', (latest) => {
    const next = latest > SCROLL_SHRINK_THRESHOLD
    setIsScrolled((prev) => (prev === next ? prev : next))
  })

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
          <Sheet open={isMobileNavOpen} onOpenChange={setIsMobileNavOpen}>
            <SheetTrigger asChild>
              <button
                type="button"
                aria-label="Open navigation menu"
                className="flex size-9 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-950 shadow-xs"
              >
                <Menu className="size-4" />
              </button>
            </SheetTrigger>
            <SheetContent side="left" className="w-3/4 max-w-xs border-slate-200 bg-white p-0 text-slate-950">
              <SheetTitle className="sr-only">Navigation menu</SheetTitle>
              <nav className="flex flex-col gap-1 p-5 pt-14">
                <Link href="/" onClick={closeMobileNav} className="mb-3 flex items-center gap-2 text-slate-950">
                  <Image
                    src="/logo.png"
                    alt="Reviveo"
                    width={28}
                    height={28}
                    className="size-7 object-contain"
                  />
                  <span className="font-bold">Reviveo</span>
                </Link>
                {MOBILE_LINKS.map((link) => (
                  <a
                    key={link.href}
                    href={link.href}
                    onClick={closeMobileNav}
                    className="rounded-lg px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
                  >
                    {link.label}
                  </a>
                ))}
                <Link
                  href="/dashboard"
                  onClick={closeMobileNav}
                  className="rounded-lg px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
                >
                  Dashboard
                </Link>
              </nav>
            </SheetContent>
          </Sheet>

          <Button
            asChild
            size="sm"
            variant="brand"
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
        <header
          className={cn(
            'mx-auto w-full px-6 pt-6 transition-[max-width] duration-300 ease-out lg:px-8',
            isScrolled ? 'max-w-5xl' : 'max-w-7xl'
          )}
        >
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
              <a href="#demo" className="transition-colors hover:text-blue-700">
                Demo
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
                size="sm"
                variant="brand"
                className="rounded-lg"
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
