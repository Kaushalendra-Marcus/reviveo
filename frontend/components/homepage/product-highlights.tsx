import { SpotlightCard2 } from '@/components/homepage/spotlight-card-2';
import { SpotlightCard3 } from '@/components/homepage/spotlight-card-3';
import { SpotlightCard4 } from '@/components/homepage/spotlight-card-4';

export function ProductHighlights() {
  return (
    <section className="bg-slate-950 py-24">
      <div className="mx-auto max-w-6xl px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-bold uppercase tracking-[0.18em] text-blue-400">
            Why teams choose Reviveo
          </p>
          <h2 className="mt-4 text-3xl font-bold tracking-tight text-white sm:text-4xl">
            Built for revenue teams, not just engineers.
          </h2>
        </div>

        <div className="mt-14 grid gap-6 sm:grid-cols-3">
          <SpotlightCard2 />
          <SpotlightCard3 />
          <SpotlightCard4 />
        </div>
      </div>
    </section>
  );
}

export default ProductHighlights;
