'use client';

import { Spotlight, SpotLightItem } from '@/components/ui/spotlight';

export function SpotlightCard3() {
  return (
    <Spotlight className="h-full" ProximitySpotlight={false} HoverFocusSpotlight={true}>
      <SpotLightItem className="h-full">
        <div className="relative z-10 flex h-full min-h-[300px] flex-col items-center justify-center rounded-xl bg-gradient-to-b from-[#1a1a1a] to-[#0c0c0c] px-6 py-10 text-center transition-colors duration-300 group-hover:from-[#1e1e1e] group-hover:to-[#141414]">
          <svg viewBox="0 0 240 140" className="h-24 w-auto" aria-hidden="true">
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
            <g transform="translate(170,4)">
              <rect width="60" height="20" rx="10" fill="#3E7AEE" />
              <text x="30" y="14" textAnchor="middle" fontSize="10" fontWeight="700" fill="white">
                LIVE
              </text>
            </g>
          </svg>

          <h3 className="pt-6 text-lg font-semibold text-white transition-colors duration-300 group-hover:text-blue-100 sm:text-xl">
            Revenue Trends
          </h3>
          <p className="mx-auto mt-2 max-w-[30ch] text-xs leading-5 text-slate-400 transition-colors duration-300 group-hover:text-slate-200 sm:text-sm sm:leading-6">
            Watch recovered revenue and subscriber health update in real time as outcomes come in.
          </p>
        </div>
      </SpotLightItem>
    </Spotlight>
  );
}

export default SpotlightCard3;
