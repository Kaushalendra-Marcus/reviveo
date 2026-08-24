'use client';

import Link from 'next/link';
import dynamic from 'next/dynamic';
import React, { type FormEvent, useRef, useState } from 'react';
import { motion, useInView, useReducedMotion } from 'framer-motion';
import { toast } from 'sonner';

const BlobCanvas = dynamic(() => import('./blob-canvas').then((m) => m.BlobCanvas), {
  ssr: false,
  loading: () => null,
});

export const Footer = () => {
  const wordmarkRef = useRef<HTMLDivElement>(null);
  const isInView = useInView(wordmarkRef, { once: true, margin: '-40px' });
  const prefersReducedMotion = useReducedMotion();
  const [email, setEmail] = useState('');

  const handleNewsletter = (e: FormEvent) => {
    e.preventDefault();
    const form = e.target as HTMLFormElement;
    const formData = new FormData(form);
    const raw = formData.get('newsletter_email')?.toString().trim() ?? '';

    if (!raw || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(raw)) {
      toast.error('Please enter a valid email address.');
      return;
    }

    toast.success('Thanks for subscribing — check your inbox soon.');
    form.reset();
    setEmail('');
  };

  const letters = 'REVIVEO'.split('');

  const letterVariants = {
    hidden: { y: 180 },
    visible: (i: number) => ({
      y: 0,
      transition: {
        type: 'spring' as const,
        stiffness: 110,
        damping: 14,
        delay: i * 0.04,
      },
    }),
  };

  return (
    <footer className="relative overflow-hidden bg-slate-950 text-white">
      {/* subtle reviveo-blue blob ambient — fitted to footer, not fullscreen */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.32] [mask-image:radial-gradient(ellipse_80%_60%_at_50%_75%,black_35%,transparent_78%)]"
      >
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_70%_50%_at_50%_20%,rgba(62,122,238,0.16),transparent_60%)]" />
      </div>

      {/* top section */}
      <div className="relative mx-auto max-w-7xl px-6 pt-12 sm:pt-14 lg:px-8">
        <div className="flex flex-col gap-12 md:flex-row md:justify-between">
          {/* left — headline + newsletter */}
          <div className="max-w-xl">
            <h2 className="text-2xl font-bold tracking-tight sm:text-3xl md:text-4xl">
              Let&apos;s recover revenue together
            </h2>
            <p className="mt-3 text-sm leading-6 text-slate-400 sm:text-base">
              Get product updates, recovery insights and early access to new features.
            </p>

            <div className="mt-6">
              <p className="text-sm font-semibold uppercase tracking-widest text-slate-300 sm:text-base sm:normal-case sm:tracking-normal sm:font-medium">
                Sign up for our newsletter
              </p>

              <form
                onSubmit={handleNewsletter}
                className="relative mt-3 flex items-center overflow-hidden rounded-full border border-white/15 bg-white p-1.5 shadow-lg shadow-black/20"
              >
                <input
                  type="email"
                  name="newsletter_email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Your email *"
                  required
                  aria-label="Email for newsletter"
                  className="h-10 flex-1 bg-transparent px-4 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none"
                />
                <button
                  type="submit"
                  aria-label="Subscribe to newsletter"
                  className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                >
                  <svg
                    width="15"
                    height="15"
                    viewBox="0 0 15 15"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    className="size-4"
                    aria-hidden="true"
                  >
                    <path
                      d="M8.14645 3.14645C8.34171 2.95118 8.65829 2.95118 8.85355 3.14645L12.8536 7.14645C13.0488 7.34171 13.0488 7.65829 12.8536 7.85355L8.85355 11.8536C8.65829 12.0488 8.34171 12.0488 8.14645 11.8536C7.95118 11.6583 7.95118 11.3417 8.14645 11.1464L11.2929 8H2.5C2.22386 8 2 7.77614 2 7.5C2 7.22386 2.22386 7 2.5 7H11.2929L8.14645 3.85355C7.95118 3.65829 7.95118 3.34171 8.14645 3.14645Z"
                      fill="currentColor"
                      fillRule="evenodd"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              </form>
              <p className="mt-2 text-xs text-slate-500">No spam. Unsubscribe anytime.</p>
            </div>
          </div>

          {/* right — links */}
          <div className="flex gap-10 sm:gap-16">
            <nav aria-label="Sitemap">
              <h3 className="text-sm font-semibold uppercase tracking-widest text-white">Sitemap</h3>
              <ul className="mt-4 space-y-2.5">
                <li>
                  <Link href="/" className="text-sm text-slate-300 transition-colors hover:text-white hover:underline underline-offset-4">
                    Home
                  </Link>
                </li>
                <li>
                  <a href="#product" className="text-sm text-slate-300 transition-colors hover:text-white hover:underline underline-offset-4">
                    Product
                  </a>
                </li>
                <li>
                  <a href="#how-it-works" className="text-sm text-slate-300 transition-colors hover:text-white hover:underline underline-offset-4">
                    How It Works
                  </a>
                </li>
                <li>
                  <a href="#safety" className="text-sm text-slate-300 transition-colors hover:text-white hover:underline underline-offset-4">
                    Safety
                  </a>
                </li>
                <li>
                  <Link href="/dashboard" className="text-sm text-slate-300 transition-colors hover:text-white hover:underline underline-offset-4">
                    Dashboard
                  </Link>
                </li>
              </ul>
            </nav>

            <nav aria-label="Social">
              <h3 className="text-sm font-semibold uppercase tracking-widest text-white">Social</h3>
              <ul className="mt-4 space-y-2.5">
                <li>
                  <a
                    href="https://www.linkedin.com"
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-sm text-slate-300 underline underline-offset-4 decoration-white/20 hover:text-white hover:decoration-white"
                  >
                    LinkedIn
                  </a>
                </li>
                <li>
                  <a
                    href="https://twitter.com"
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-sm text-slate-300 underline underline-offset-4 decoration-white/20 hover:text-white hover:decoration-white"
                  >
                    Twitter
                  </a>
                </li>
                <li>
                  <a
                    href="https://github.com"
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-sm text-slate-300 underline underline-offset-4 decoration-white/20 hover:text-white hover:decoration-white"
                  >
                    GitHub
                  </a>
                </li>
                <li>
                  <a
                    href="mailto:hello@reviveo.ai"
                    className="text-sm text-slate-300 underline underline-offset-4 decoration-white/20 hover:text-white hover:decoration-white"
                  >
                    hello@reviveo.ai
                  </a>
                </li>
              </ul>
            </nav>
          </div>
        </div>

        {/* wordmark — animated reveal + 3D blob fitted inside, extra-large */}
        <div
          ref={wordmarkRef}
          className="relative mt-10 overflow-hidden border-y border-white/10 py-10 md:py-16"
        >
          {/* 3D blob — larger, centered behind wordmark */}
          <div className="absolute inset-0">
            <BlobCanvas className="absolute inset-0 h-full w-full opacity-95 scale-[1.05]" color="#3E7AEE" />
            {/* fade the 3D edges so it feels like ambient glow, not a box */}
            <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-slate-950/20 via-transparent to-slate-950/55" />
          </div>

          <span className="sr-only">Reviveo</span>
          <div
            aria-hidden="true"
            className="relative z-10 flex select-none items-center justify-between gap-1 font-black tracking-[-0.06em] leading-none text-blue-500 drop-shadow-[0_2px_18px_rgba(62,122,238,0.4)]"
          >
            {letters.map((ch, i) => (
              <motion.span
                key={`${ch}-${i}`}
                custom={i}
                variants={letterVariants}
                initial={prefersReducedMotion ? 'visible' : 'hidden'}
                animate={prefersReducedMotion || isInView ? 'visible' : 'hidden'}
                className="inline-block text-[15vw] sm:text-[13.5vw] md:text-[12.5vw] lg:text-[150px] xl:text-[190px] 2xl:text-[220px]"
                style={{ display: 'inline-block', overflow: 'hidden' }}
              >
                {ch}
              </motion.span>
            ))}
          </div>
        </div>

        {/* bottom bar */}
        <div className="flex flex-col-reverse gap-3 py-5 text-sm md:flex-row md:items-center md:justify-between">
          <span className="text-slate-400">© {new Date().getFullYear()} Reviveo. All rights reserved.</span>
          <div className="flex items-center gap-6">
            <a href="/privacy" className="font-medium text-slate-300 hover:text-white transition-colors">
              Privacy Policy
            </a>
            <a href="/terms" className="font-medium text-slate-300 hover:text-white transition-colors">
              Terms of Service
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
