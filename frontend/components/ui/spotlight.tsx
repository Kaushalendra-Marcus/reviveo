'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

type SpotlightContextValue = {
  hoverFocusSpotlight: boolean;
  cursorFlowGradient: boolean;
  /** Raw window mouse position — shared so every item's HoverFocusSpotlight lines up with the real cursor. */
  mousePosition: { x: number; y: number };
};

const SpotlightContext = React.createContext<SpotlightContextValue | null>(null);

function useSpotlightContext(component: string) {
  const context = React.useContext(SpotlightContext);
  if (!context) {
    throw new Error(`${component} must be used inside a <Spotlight> component.`);
  }
  return context;
}

export type SpotlightProps = React.HTMLAttributes<HTMLDivElement> & {
  /** Soft ambient glow that follows the cursor across the whole component, even off any card. Default: true */
  ProximitySpotlight?: boolean;
  /** Focused spotlight that only lights up over the card currently hovered/focused, positioned by the real cursor. Default: false */
  HoverFocusSpotlight?: boolean;
  /** Local highlight inside each card that flows with the cursor while hovering that specific card. Default: true */
  CursorFlowGradient?: boolean;
};

export const Spotlight = ({
  className,
  children,
  ProximitySpotlight = true,
  HoverFocusSpotlight = false,
  CursorFlowGradient = true,
  ...props
}: SpotlightProps) => {
  const [mousePosition, setMousePosition] = React.useState({ x: 0, y: 0 });

  // Track raw window cursor position (not container-relative) so the glow stays
  // correct no matter which card in the grid is under the pointer.
  React.useEffect(() => {
    if (!ProximitySpotlight && !HoverFocusSpotlight) return;

    const updateMousePosition = (event: MouseEvent) => {
      setMousePosition({ x: event.clientX, y: event.clientY });
    };

    window.addEventListener('mousemove', updateMousePosition);
    return () => window.removeEventListener('mousemove', updateMousePosition);
  }, [ProximitySpotlight, HoverFocusSpotlight]);

  return (
    <SpotlightContext.Provider
      value={{
        hoverFocusSpotlight: HoverFocusSpotlight,
        cursorFlowGradient: CursorFlowGradient,
        mousePosition,
      }}
    >
      <div className={cn('relative', className)} {...props}>
        {ProximitySpotlight && (
          // bg-fixed anchors the gradient to viewport coordinates, so "at Xpx Ypx"
          // (raw clientX/clientY) lines up correctly wherever this sits on the page.
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 bg-fixed"
            style={{
              background: `radial-gradient(700px circle at ${mousePosition.x}px ${mousePosition.y}px, rgba(255,255,255,0.06), transparent 65%)`,
            }}
          />
        )}
        {children}
      </div>
    </SpotlightContext.Provider>
  );
};

export type SpotLightItemProps = React.HTMLAttributes<HTMLDivElement>;

export const SpotLightItem = ({ className, children, ...props }: SpotLightItemProps) => {
  const { hoverFocusSpotlight, cursorFlowGradient, mousePosition } = useSpotlightContext('SpotLightItem');

  const containerRef = React.useRef<HTMLDivElement>(null);
  const [localPosition, setLocalPosition] = React.useState({ x: 0, y: 0 });

  const handleMouseMove = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!cursorFlowGradient || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    setLocalPosition({ x: event.clientX - rect.left, y: event.clientY - rect.top });
  };

  return (
    <div
      ref={containerRef}
      onMouseMove={handleMouseMove}
      className={cn(
        'group relative overflow-hidden rounded-xl border border-white/10 bg-white/[0.02] p-[1px]',
        className
      )}
      {...props}
    >
      {/* Cursor flow gradient — local to THIS card, computed from its own bounding box
          so the highlight always sits under the pointer regardless of grid position. */}
      {cursorFlowGradient && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -inset-px opacity-0 transition-opacity duration-300 group-hover:opacity-100"
          style={{
            background: `radial-gradient(650px circle at ${localPosition.x}px ${localPosition.y}px, rgba(62,122,238,0.35), transparent 44%)`,
          }}
        />
      )}

      {/* Hover-focus spotlight — only visible over the hovered card (group-hover), but
          positioned by the real window cursor (from context) so it reads as one
          continuous light source sweeping across the grid, not a per-card glow. */}
      {hoverFocusSpotlight && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 rounded-xl bg-fixed opacity-0 transition-opacity duration-300 group-hover:opacity-100"
          style={{
            background: `radial-gradient(circle at ${mousePosition.x}px ${mousePosition.y}px, rgba(62,122,238,0.45), transparent 45%)`,
          }}
        />
      )}

      {/* inner border + subtle glow on hover */}
      <div className="pointer-events-none absolute inset-0 rounded-xl border border-transparent opacity-0 transition-all duration-300 group-hover:opacity-100 group-hover:border-blue-500/30 group-hover:shadow-[0_0_22px_rgba(62,122,238,0.35)]" />

      {children}
    </div>
  );
};
