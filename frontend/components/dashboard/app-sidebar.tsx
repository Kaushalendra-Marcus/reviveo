import Link from "next/link";
import Image from "next/image";
import { NavLinks } from "./nav-links";

export function AppSidebar() {
  return (
    <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-white lg:flex lg:flex-col">
      <div className="flex h-16 items-center gap-2.5 border-b border-slate-200 px-5">
        <Link href="/" className="flex items-center gap-2.5">
          <Image src="/logo.png" alt="" width={28} height={28} className="size-7 object-contain" />
          <span className="text-base font-bold tracking-tight text-slate-950">Reviveo</span>
        </Link>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-4">
        <NavLinks />
      </div>
      <div className="border-t border-slate-200 p-4">
        <Link
          href="/"
          className="text-xs font-medium text-slate-400 transition-colors hover:text-slate-600"
        >
          ← Back to homepage
        </Link>
      </div>
    </aside>
  );
}
