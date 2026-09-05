'use client'

import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'

const YOUTUBE_ID = 'jMqsnPQtysM'
// YouTube's embedded player only accepts its own preset rates
// (0.25/0.5/0.75/1/1.25/1.5/1.75/2) — it will silently snap anything else to
// the nearest one. 1.3 isn't a supported preset, so 1.25 is what actually
// plays; this is a YouTube player limitation, not something fixable in code.
const DEFAULT_SPEED = 1.25
const SPEED_OPTIONS = [0.75, 1, 1.25, 1.5, 1.75, 2]

declare global {
  interface Window {
    YT: any
    onYouTubeIframeAPIReady?: () => void
  }
}

export const DemoVideo = () => {
  const containerRef = useRef<HTMLDivElement>(null)
  const playerRef = useRef<any>(null)
  const [speed, setSpeed] = useState(DEFAULT_SPEED)

  useEffect(() => {
    let cancelled = false

    function createPlayer() {
      if (cancelled || !containerRef.current) return
      playerRef.current = new window.YT.Player(containerRef.current, {
        videoId: YOUTUBE_ID,
        playerVars: { rel: 0, modestbranding: 1 },
        events: {
          onReady: (event: any) => {
            event.target.setPlaybackRate(DEFAULT_SPEED)
          },
        },
      })
    }

    if (window.YT && window.YT.Player) {
      createPlayer()
    } else {
      const tag = document.createElement('script')
      tag.src = 'https://www.youtube.com/iframe_api'
      document.body.appendChild(tag)
      const previous = window.onYouTubeIframeAPIReady
      window.onYouTubeIframeAPIReady = () => {
        previous?.()
        createPlayer()
      }
    }

    return () => {
      cancelled = true
      playerRef.current?.destroy?.()
    }
  }, [])

  function handleSpeedChange(rate: number) {
    setSpeed(rate)
    playerRef.current?.setPlaybackRate?.(rate)
  }

  return (
    <section id="demo" className="bg-white py-24 sm:py-32">
      <div className="mx-auto max-w-5xl px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-100px' }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className="mx-auto max-w-2xl text-center"
        >
          <span className="text-sm font-semibold uppercase tracking-[0.14em] text-blue-600">
            Watch it work
          </span>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            See a real recovery, start to finish
          </h2>
          <p className="mt-4 text-lg text-slate-600">
            A five-minute walkthrough of a live Razorpay test-mode payment
            failure being detected, diagnosed, decided on, and recovered by
            Reviveo, guardrails included.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 32 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-100px' }}
          transition={{ duration: 0.7, ease: 'easeOut', delay: 0.1 }}
          className="mx-auto mt-12 max-w-4xl"
        >
          <div
            className={cn(
              'relative aspect-video w-full overflow-hidden rounded-2xl border border-slate-200 bg-slate-950 shadow-2xl shadow-slate-900/10',
              '[&>iframe]:absolute [&>iframe]:inset-0 [&>iframe]:h-full [&>iframe]:w-full'
            )}
          >
            <div ref={containerRef} />
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
            <span className="text-xs font-medium text-slate-500">Playback speed:</span>
            {SPEED_OPTIONS.map((rate) => (
              <button
                key={rate}
                type="button"
                onClick={() => handleSpeedChange(rate)}
                className={cn(
                  'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
                  speed === rate
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                )}
              >
                {rate}x
              </button>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  )
}
