'use client';

import { Spotlight, SpotLightItem } from '@/components/ui/spotlight';

// Pattern: ambient proximity glow (always on, tracks the real cursor) plus the
// local hover-flow gradient. Matches ui-layouts' "Proximity" example (spotlight-card4).
export function SpotlightCard4() {
  return (
    <Spotlight className="h-full" ProximitySpotlight={true} HoverFocusSpotlight={false}>
      <SpotLightItem className="h-full">
        <div className="relative z-10 flex h-full min-h-[300px] flex-col items-center justify-center rounded-xl bg-gradient-to-b from-[#1a1a1a] to-[#0c0c0c] px-6 py-10 text-center transition-colors duration-300 group-hover:from-[#1e1e1e] group-hover:to-[#141414]">
          <svg viewBox="0 0 240 140" className="h-24 w-auto" aria-hidden="true">
            <rect x="70" y="34" width="42" height="42" rx="10" fill="none" stroke="#ffffff" strokeWidth="4" />
            <rect x="128" y="34" width="42" height="42" rx="10" fill="none" stroke="#3E7AEE" strokeWidth="4" />
            <rect x="99" y="72" width="42" height="42" rx="10" fill="#3E7AEE" fillOpacity="0.18" stroke="#3E7AEE" strokeWidth="4" />
            <path d="M112 55 H128" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" />
            <path d="M120 76 V93" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" />
          </svg>

          <h3 className="pt-6 text-lg font-semibold text-white transition-colors duration-300 group-hover:text-blue-100 sm:text-xl">
            Built To Fit In
          </h3>
          <p className="mx-auto mt-2 max-w-[30ch] text-xs leading-5 text-slate-400 transition-colors duration-300 group-hover:text-slate-200 sm:text-sm sm:leading-6">
            Reviveo slots into the tools your team already uses — nothing to change.
          </p>
        </div>
      </SpotLightItem>
    </Spotlight>
  );
}

export default SpotlightCard4;
