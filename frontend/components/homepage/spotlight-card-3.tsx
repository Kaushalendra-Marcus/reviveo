'use client';

import { Spotlight, SpotLightItem } from '@/components/ui/spotlight';

export function SpotlightCard3() {
  return (
    <div className="relative rounded-md bg-black px-4 py-8 sm:p-8">
      <Spotlight className="mx-auto w-full" ProximitySpotlight={false} HoverFocusSpotlight={true}>
        <SpotLightItem>
          <div
            className="relative z-10 mx-auto h-full w-full rounded-lg bg-black bg-[linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.05)_1px,transparent_1px)] bg-[size:22px_22px] px-4 py-6 text-center sm:px-8"
          >
            <svg viewBox="0 0 240 140" className="mx-auto h-28 w-auto" aria-hidden="true">
              <defs>
                <linearGradient id="subGrowthArea" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3E7AEE" stopOpacity="0.55" />
                  <stop offset="100%" stopColor="#3E7AEE" stopOpacity="0" />
                </linearGradient>
              </defs>
              <path
                d="M10 110 L45 95 L80 100 L115 70 L150 78 L185 40 L230 22 L230 120 L10 120 Z"
                fill="url(#subGrowthArea)"
              />
              <polyline
                fill="none"
                stroke="#ffffff"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                points="10,110 45,95 80,100 115,70 150,78 185,40 230,22"
              />
              <circle cx="230" cy="22" r="5" fill="#ffffff" />
              <g transform="translate(178,4)">
                <rect width="46" height="20" rx="10" fill="#3E7AEE" />
                <text x="23" y="14" textAnchor="middle" fontSize="11" fontWeight="700" fill="white">
                  3x
                </text>
              </g>
            </svg>

            <h1 className="pt-6 text-3xl font-medium tracking-tight text-white">Subscriber Growth</h1>
            <p className="pt-2 capitalize text-muted-foreground">
              Experience a significant boost in your subscriber <br />
              count, achieving 3x growth.
            </p>
          </div>
        </SpotLightItem>
      </Spotlight>
    </div>
  );
}

export default SpotlightCard3;
