'use client';

import { Spotlight, SpotLightItem } from '@/components/ui/spotlight';

// Pattern: plain hover-local spotlight only — no ambient glow, no window-tracked
// hover-focus beam. Matches ui-layouts' base "Spotlight" example (spotlight-card2).
export function SpotlightCard2() {
  return (
    <Spotlight className="h-full" ProximitySpotlight={false} HoverFocusSpotlight={false}>
      <SpotLightItem className="h-full">
        <div className="relative z-10 flex h-full min-h-[300px] flex-col items-center justify-center rounded-xl bg-gradient-to-b from-[#1a1a1a] to-[#0c0c0c] px-6 py-10 text-center transition-colors duration-300 group-hover:from-[#1e1e1e] group-hover:to-[#141414]">
          <svg viewBox="0 0 240 140" className="h-24 w-auto" aria-hidden="true">
            <circle cx="120" cy="66" r="46" fill="#3E7AEE" fillOpacity="0.12" />
            <path
              d="M120 30 L120 76 M120 76 L104 60 M120 76 L136 60"
              stroke="#3E7AEE"
              strokeWidth="6"
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
            <path d="M96 96 H144" stroke="#ffffff" strokeWidth="6" strokeLinecap="round" fill="none" />
          </svg>

          <h3 className="pt-6 text-lg font-semibold text-white transition-colors duration-300 group-hover:text-blue-100 sm:text-xl">
            Instant Setup
          </h3>
          <p className="mx-auto mt-2 max-w-[30ch] text-xs leading-5 text-slate-400 transition-colors duration-300 group-hover:text-slate-200 sm:text-sm sm:leading-6">
            Connect your payment stack in minutes — no migration, nothing to rebuild.
          </p>
        </div>
      </SpotLightItem>
    </Spotlight>
  );
}

export default SpotlightCard2;
