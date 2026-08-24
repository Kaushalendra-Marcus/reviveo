'use client';

import Image from 'next/image';
import {
  motion,
  useAnimationFrame,
  useMotionValue,
  useReducedMotion,
  useTransform,
} from 'framer-motion';
import { useEffect, useRef, useState } from 'react';

type Merchant = {
  id: string;
  label: string;
  logo: string;
  color: string;
};

const merchants: Merchant[] = [
  {
    id: 'netflix',
    label: 'Netflix',
    logo: 'https://cdn.simpleicons.org/netflix/E50914',
    color: '#E50914',
  },
  {
    id: 'swiggy',
    label: 'Swiggy',
    logo: 'https://cdn.simpleicons.org/swiggy/FC8019',
    color: '#FC8019',
  },
  {
    id: 'prime-video',
    label: 'Prime Video',
    logo: '/partners/prime-video.png',
    color: '#00A8E1',
  },
  {
    id: 'pw',
    label: 'PW',
    logo: '/partners/pw.png',
    color: '#6c2eb9',
  },
];

const ORBIT_DURATION = 26;
const TAU = Math.PI * 2;

export function IntegrationCarousel() {
  const containerRef = useRef<HTMLDivElement>(null);

  const rotation = useMotionValue(0);

  const [isPaused, setIsPaused] = useState(false);
  const prefersReducedMotion = useReducedMotion();

  /**
   * Every orbit position/scale/opacity below is derived from Math.sin/Math.cos.
   * Those aren't guaranteed to return bit-identical floats between Node (SSR)
   * and the browser's JS engine — the spec only requires an "approximated"
   * result for transcendental functions. That tiny drift (e.g. 31.5 vs
   * 31.499999999999982) was enough to trip React's hydration check on every
   * orbiting logo's inline style. Since the layout only matters once it's
   * actually spinning, skip rendering it until after mount — nothing
   * meaningful to hydrate, nothing to mismatch.
   */
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  /**
   * IMPORTANT:
   *
   * This uses a continuously increasing motion value.
   *
   * Do NOT use:
   * (rotation + value) % 360
   *
   * because wrapping back from 359 -> 0 can cause visible
   * discontinuities / jerks.
   */
  useAnimationFrame((_, delta) => {
    if (isPaused || prefersReducedMotion) return;

    const speed = TAU / (ORBIT_DURATION * 1000);

    rotation.set(rotation.get() + delta * speed);
  });

  return (
    <section className="relative overflow-hidden bg-[#030303] py-20 sm:py-28">
      <div className="mx-auto max-w-7xl px-6 lg:px-8">
        <div className="grid items-center gap-14 lg:grid-cols-[0.9fr_1.1fr]">
          {/* LEFT CONTENT */}
          <div className="relative z-10 max-w-xl">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-blue-400">
              Built for subscription businesses
            </p>

            <h2 className="mt-4 text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Failed payments happen
              <span className="block text-white/45">
                everywhere subscriptions do.
              </span>
            </h2>

            <p className="mt-6 max-w-lg text-base leading-7 text-zinc-400">
              Streaming, food delivery, edtech, or anything billed on a recurring
              cycle — a single failed payment can quietly turn into a lost
              customer. Reviveo is built for exactly this category of business.
            </p>
          </div>

          {/* ORBITAL CAROUSEL */}
          <div
            ref={containerRef}
            onMouseEnter={() => setIsPaused(true)}
            onMouseLeave={() => setIsPaused(false)}
            className="relative h-[460px] w-full select-none overflow-hidden sm:h-[520px] lg:h-[560px]"
          >
            {/* VERY SUBTLE TRACK */}

            <div className="pointer-events-none absolute inset-0">
              <svg
                className="h-full w-full"
                viewBox="0 0 1000 700"
                preserveAspectRatio="xMidYMid meet"
              >
                <defs>
                  <linearGradient
                    id="orbit-gradient"
                    x1="0"
                    y1="0"
                    x2="1"
                    y2="0"
                  >
                    <stop offset="0%" stopColor="#ffffff" stopOpacity="0" />
                    <stop offset="20%" stopColor="#ffffff" stopOpacity="0.03" />
                    <stop offset="50%" stopColor="#ffffff" stopOpacity="0.12" />
                    <stop offset="80%" stopColor="#ffffff" stopOpacity="0.03" />
                    <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
                  </linearGradient>

                  <radialGradient id="center-glow">
                    <stop offset="0%" stopColor="#ffffff" stopOpacity="0.08" />
                    <stop offset="45%" stopColor="#6366f1" stopOpacity="0.04" />
                    <stop offset="100%" stopColor="#000000" stopOpacity="0" />
                  </radialGradient>
                </defs>

                {/* subtle center ambient glow */}
                <ellipse
                  cx="530"
                  cy="350"
                  rx="280"
                  ry="220"
                  fill="url(#center-glow)"
                />

                {/* orbital path */}
                <ellipse
                  cx="530"
                  cy="350"
                  rx="330"
                  ry="220"
                  fill="none"
                  stroke="url(#orbit-gradient)"
                  strokeWidth="1.2"
                />
              </svg>
            </div>

            {/* CENTER AMBIENT GLOW */}

            <div
              className="pointer-events-none absolute left-1/2 top-1/2 h-[250px] w-[250px] -translate-x-1/2 -translate-y-1/2 rounded-full"
              style={{
                background:
                  'radial-gradient(circle, rgba(255,255,255,0.05) 0%, rgba(80,80,130,0.025) 35%, transparent 70%)',
              }}
            />

            {/* ORBITING LOGOS */}

            {mounted &&
              merchants.map((merchant, index) => (
                <OrbitalMerchant
                  key={merchant.id}
                  merchant={merchant}
                  index={index}
                  total={merchants.length}
                  rotation={rotation}
                />
              ))}

            {/* CENTER NODE */}

            <div className="absolute left-1/2 top-1/2 z-30 -translate-x-1/2 -translate-y-1/2">
              {/* soft outer glow */}
              <div
                className="absolute inset-[-35px] rounded-full blur-3xl"
                style={{
                  background:
                    'radial-gradient(circle, rgba(255,255,255,0.07), transparent 70%)',
                }}
              />

              {/* outer ring */}
              <div className="relative rounded-full border border-white/[0.08] bg-white/[0.025] p-1.5 shadow-[0_20px_80px_rgba(0,0,0,0.8)]">
                {/* center */}
                <div className="flex h-[76px] w-[76px] items-center justify-center rounded-full border border-white/[0.10] bg-[#121212] sm:h-[84px] sm:w-[84px]">
                  <Image
                    src="/logo.png"
                    alt="Reviveo"
                    width={38}
                    height={38}
                    className="h-9 w-9 object-contain brightness-0 invert"
                    priority
                  />
                </div>
              </div>
            </div>

            {/* subtle label */}

            <div className="pointer-events-none absolute bottom-5 left-1/2 z-40 -translate-x-1/2 whitespace-nowrap text-[11px] tracking-[0.08em] text-zinc-600">
              THE KIND OF BUSINESSES THIS HAPPENS TO
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function OrbitalMerchant({
  merchant,
  index,
  total,
  rotation,
}: {
  merchant: Merchant;
  index: number;
  total: number;
  rotation: ReturnType<typeof useMotionValue<number>>;
}) {
  /**
   * Each logo gets an evenly spaced starting position.
   */
  const startAngle = (index / total) * TAU;

  /**
   * Orbital geometry.
   *
   * The orbit is wider than tall to create the horizontal
   * Antimetal / Framer-style carousel feeling.
   */
  const x = useTransform(rotation, (r) => {
    const angle = startAngle + r;

    const radiusX = 37;

    return 50 + Math.cos(angle) * radiusX;
  });

  const y = useTransform(rotation, (r) => {
    const angle = startAngle + r;

    const radiusY = 31;

    return 50 + Math.sin(angle) * radiusY;
  });


  const scale = useTransform(rotation, (r) => {
    const depth = (Math.sin(startAngle + r) + 1) / 2;

    return 0.68 + depth * 0.42;
  });

  const opacity = useTransform(rotation, (r) => {
    const depth = (Math.sin(startAngle + r) + 1) / 2;

    return 0.28 + depth * 0.72;
  });

  /**
   * Dynamic size also improves the perspective effect.
   */
  const size = useTransform(rotation, (r) => {
    const depth = (Math.sin(startAngle + r) + 1) / 2;

    return 46 + depth * 26;
  });

  /**
   * Move front logos slightly toward the viewer visually
   * using stronger glow.
   */
  const glow = useTransform(rotation, (r) => {
    const depth = (Math.sin(startAngle + r) + 1) / 2;

    const alpha = 0.02 + depth * 0.11;

    return `0 0 ${20 + depth * 25}px rgba(255,255,255,${alpha})`;
  });

  return (
    <motion.div
      className="absolute left-0 top-0 z-10"
      style={{
        left: useTransform(x, (value) => `${value}%`),
        top: useTransform(y, (value) => `${value}%`),
        x: '-50%',
        y: '-50%',
        scale,
        opacity,
      }}
    >
      <motion.div
        className="flex items-center justify-center rounded-full border border-white/[0.10] bg-[#101010]/95 backdrop-blur-sm"
        style={{
          width: size,
          height: size,
          boxShadow: glow,
        }}
      >
        <div
          className="flex h-full w-full items-center justify-center rounded-full"
          style={{
            background: `radial-gradient(circle at 35% 30%, ${merchant.color}12, transparent 58%)`,
          }}
        >
          <img
            src={merchant.logo}
            alt={merchant.label}
            draggable={false}
            className="h-[42%] w-[42%] object-contain"
            loading="lazy"
          />
        </div>
      </motion.div>
    </motion.div>
  );
}

export default IntegrationCarousel;