'use client';

import { Spotlight, SpotLightItem } from '@/components/ui/spotlight';

export function SpotlightCards() {
  return (
    <section className="bg-[#1a1a1a] py-16 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="rounded-2xl bg-black p-3 sm:p-5">
          <Spotlight className="grid grid-cols-6 gap-3 auto-rows-[132px] sm:auto-rows-[148px]">
            {/* Top left — area chart with dot 2.5% */}
            <SpotLightItem className="col-span-6 sm:col-span-2">
              <div className="relative z-10 h-full w-full rounded-xl bg-gradient-to-b from-[#1a1a1a] to-[#0c0c0c] p-3">
                <svg viewBox="0 0 200 110" className="h-full w-full">
                  <defs>
                    <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="white" stopOpacity="0.85" />
                      <stop offset="100%" stopColor="white" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <path
                    d="M0 90 L20 75 L35 85 L50 55 L75 60 L95 35 L110 42 L135 22 L160 28 L200 18 L200 90 Z"
                    fill="url(#areaGrad)"
                    opacity="0.9"
                  />
                  <line x1="115" y1="10" x2="115" y2="100" stroke="white" strokeWidth="0.8" opacity="0.9" />
                  <circle cx="115" cy="34" r="7" fill="white" stroke="black" strokeWidth="2" />
                  <g transform="translate(125,26)">
                    <rect x="0" y="0" width="44" height="16" rx="3" fill="#2a2a2a" stroke="white" strokeWidth="0.5" opacity="0.95" />
                    <text x="22" y="11" textAnchor="middle" fontSize="7" fill="white" fontWeight="600">2.5% inc</text>
                  </g>
                </svg>
              </div>
            </SpotLightItem>

            {/* Top middle — zigzag line */}
            <SpotLightItem className="col-span-6 sm:col-span-2">
              <div className="relative z-10 h-full w-full rounded-xl bg-gradient-to-b from-[#1a1a1a] to-[#0c0c0c] p-3">
                <svg viewBox="0 0 200 110" className="h-full w-full">
                  <polyline
                    fill="none"
                    stroke="white"
                    strokeWidth="1.4"
                    opacity="0.95"
                    points="10,85 35,75 55,82 72,62 95,70 115,48 132,58 148,32 162,45 175,28 190,42"
                  />
                  <polyline
                    fill="none"
                    stroke="white"
                    strokeWidth="1"
                    opacity="0.55"
                    points="10,88 35,78 55,85 72,65 95,73 115,51 132,61 148,35 162,48 175,31 190,45"
                  />
                  <line x1="135" y1="20" x2="135" y2="95" stroke="white" strokeWidth="0.7" opacity="0.4" />
                  <circle cx="135" cy="48" r="4.5" fill="white" stroke="black" strokeWidth="1.5" />
                </svg>
              </div>
            </SpotLightItem>

            {/* Right — Track Goals bars (spans 2 rows, 2 cols) */}
            <SpotLightItem className="col-span-6 sm:col-span-2 sm:row-span-2">
              <div className="relative z-10 flex h-full w-full flex-col rounded-xl bg-gradient-to-b from-[#1a1a1a] to-[#0c0c0c] p-4 sm:p-5 transition-colors duration-300 group-hover:from-[#1e1e1e] group-hover:to-[#141414]">
                <div className="flex flex-1 items-end justify-center gap-3 sm:gap-3.5">
                  {[
                    { h: 78, o: 0.95 },
                    { h: 48, o: 0.7 },
                    { h: 62, o: 0.8 },
                    { h: 28, o: 0.55 },
                    { h: 88, o: 1 },
                  ].map((b, i) => (
                    <div
                      key={i}
                      className="w-10 rounded-t-sm transition-all duration-500 group-hover:brightness-125 sm:w-12 md:w-10 lg:w-11"
                      style={{
                        height: `${b.h}%`,
                        background: `linear-gradient(to bottom, rgba(255,255,255,${b.o}) 0%, rgba(120,120,120,${b.o * 0.9}) 55%, rgba(0,0,0,0) 100%)`,
                      }}
                    />
                  ))}
                </div>
                <div className="pt-4 text-center">
                  <h3 className="text-base font-semibold text-white transition-colors duration-300 group-hover:text-blue-100 sm:text-lg">Recovery Rate</h3>
                  <p className="mx-auto mt-1.5 max-w-[32ch] text-[11px] leading-4 text-slate-400 transition-colors duration-300 group-hover:text-slate-200 sm:text-xs sm:leading-5">
                    See exactly how much of your at-risk revenue is being recovered, broken down by strategy and updated as outcomes come in.
                  </p>
                </div>
              </div>
            </SpotLightItem>

            {/* Bottom left — dotted line with axes */}
            <SpotLightItem className="col-span-6 sm:col-span-2">
              <div className="relative z-10 h-full w-full rounded-xl bg-gradient-to-b from-[#1a1a1a] to-[#0c0c0c] p-3">
                <svg viewBox="0 0 200 110" className="h-full w-full">
                  <line x1="12" y1="10" x2="12" y2="100" stroke="white" strokeWidth="0.9" opacity="0.9" />
                  <polyline fill="none" stroke="white" strokeWidth="1" opacity="0.9" points="12,85 30,65 45,78 60,62 75,72 90,58 105,68 120,52 135,62 150,48 165,58 180,42 195,48" />
                  {[30,45,60,75,90,105,120,135,150,165,180,195].map((x, i) => {
                    const y = [65,78,62,72,58,68,52,62,48,58,42,48][i];
                    return <circle key={x} cx={x} cy={y} r="2.2" fill="white" />;
                  })}
                  <g opacity="0.55">
                    <polyline fill="none" stroke="white" strokeWidth="0.8" points="12,100 28,82 42,88 58,78 73,85 88,78 103,82 118,75 133,80 148,72 163,76 178,68 193,72" />
                    {[28,42,58,73,88,103,118,133,148,163,178,193].map((x,i)=>{
                      const y=[82,88,78,85,78,82,75,80,72,76,68,72][i];
                      return <circle key={x} cx={x} cy={y} r="1.8" fill="white" opacity="0.7"/>;
                    })}
                  </g>
                </svg>
              </div>
            </SpotLightItem>

            {/* Bottom middle — star burst */}
            <SpotLightItem className="col-span-6 sm:col-span-2">
              <div className="relative z-10 flex h-full w-full items-center justify-center rounded-xl bg-gradient-to-b from-[#1a1a1a] to-[#0c0c0c] p-3">
                <svg viewBox="0 0 200 140" className="h-full w-full max-h-[120px]">
                  <defs>
                    <radialGradient id="starGrad" cx="50%" cy="50%">
                      <stop offset="0%" stopColor="white" stopOpacity="1" />
                      <stop offset="45%" stopColor="white" stopOpacity="0.85" />
                      <stop offset="100%" stopColor="white" stopOpacity="0" />
                    </radialGradient>
                  </defs>
                  <path
                    d="M100 8 L108 58 L148 28 L118 68 L168 78 L118 88 L148 128 L108 98 L100 148 L92 98 L52 128 L82 88 L32 78 L82 68 L52 28 L92 58 Z"
                    fill="url(#starGrad)"
                    stroke="white"
                    strokeWidth="0.6"
                    opacity="0.95"
                  />
                </svg>
              </div>
            </SpotLightItem>
          </Spotlight>
        </div>
      </div>
    </section>
  );
}

export default SpotlightCards;
