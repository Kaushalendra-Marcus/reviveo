"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Menu, CircleDot, Bot } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useHealth } from "@/hooks/api";
import { cn } from "@/lib/utils";
import { NavLinks } from "./nav-links";

export function AppHeader() {
  const [open, setOpen] = useState(false);
  const { data: health, isLoading } = useHealth();

  const isLive = health?.run_mode === "live";

  return (
    <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center gap-3 border-b border-slate-200 bg-white/85 px-4 backdrop-blur-sm sm:px-6">
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden"
        onClick={() => setOpen(true)}
        aria-label="Open navigation"
      >
        <Menu className="size-5" />
      </Button>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetHeader className="border-b border-slate-200 px-5 py-4">
            <SheetTitle asChild>
              <Link href="/" className="flex items-center gap-2.5" onClick={() => setOpen(false)}>
                <Image src="/logo.png" alt="" width={26} height={26} className="size-6 object-contain" />
                <span className="text-base font-bold tracking-tight text-slate-950">Reviveo</span>
              </Link>
            </SheetTitle>
          </SheetHeader>
          <div className="px-3 py-4">
            <NavLinks onNavigate={() => setOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>

      <div className="flex flex-1 items-center justify-end gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
                isLive
                  ? "border-blue-200 bg-blue-50 text-blue-700"
                  : "border-slate-200 bg-slate-50 text-slate-600"
              )}
            >
              <CircleDot className="size-3" />
              {isLoading ? "Checking…" : isLive ? "Live · Razorpay Test Mode" : "Demo Mode · Synthetic"}
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {isLive
              ? "Connected to Razorpay test-mode credentials."
              : "Running fully synthetic — no Razorpay or Claude credentials configured."}
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
                health?.ai_configured
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-slate-200 bg-slate-50 text-slate-600"
              )}
            >
              <Bot className="size-3" />
              {isLoading ? "Checking…" : health?.ai_configured ? "Agent Active" : "Agent Deterministic"}
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {health?.ai_configured
              ? "Claude tool-use is configured and available for decisions."
              : "No Anthropic key configured — decisions use the deterministic policy engine only."}
          </TooltipContent>
        </Tooltip>
      </div>
    </header>
  );
}
