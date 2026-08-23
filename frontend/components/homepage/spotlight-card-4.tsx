'use client';

import { Spotlight, SpotLightItem } from '@/components/ui/spotlight';

// Pattern: ambient proximity glow (always on, tracks the real cursor) plus the
// local hover-flow gradient. Matches ui-layouts' "Proximity" example (spotlight-card4).
export function SpotlightCard4() {
  return (
    <div className="relative rounded-md bg-black px-4 py-8 sm:p-8">
      <Spotlight className="mx-auto w-full" ProximitySpotlight={true} HoverFocusSpotlight={false}>
        <SpotLightItem>
          <div
            className="relative z-10 mx-auto h-full w-full rounded-lg bg-black bg-[linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.05)_1px,transparent_1px)] bg-[size:22px_22px] px-4 py-6 text-center sm:px-8"
          >
            <svg viewBox="0 0 240 140" className="mx-auto h-28 w-auto" aria-hidden="true">
              <rect x="70" y="34" width="42" height="42" rx="10" fill="none" stroke="#ffffff" strokeWidth="4" />
              <rect x="128" y="34" width="42" height="42" rx="10" fill="none" stroke="#3E7AEE" strokeWidth="4" />
              <rect x="99" y="72" width="42" height="42" rx="10" fill="#3E7AEE" fillOpacity="0.18" stroke="#3E7AEE" strokeWidth="4" />
              <path d="M112 55 H128" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" />
              <path d="M120 76 V93" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" />
            </svg>

            <h1 className="pt-6 text-3xl font-medium tracking-tight text-white">Built To Fit In</h1>
            <p className="pt-2 capitalize text-muted-foreground">
              Reviveo slots into the tools your team <br /> already uses — nothing to change.
            </p>
          </div>
        </SpotLightItem>
      </Spotlight>
    </div>
  );
}

export default SpotlightCard4;
