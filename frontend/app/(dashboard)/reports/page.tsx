"use client";

import { useState } from "react";
import { FlaskConical, Info, Play } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { EmptyState, LoadingState } from "@/components/shared/states";
import { useHealth, useLastSimulation, useRunBatch } from "@/hooks/api";
import { formatDateTime, formatINR } from "@/lib/formatters";
import type { BatchRunResult } from "@/lib/types";

function ResultColumn({ title, result }: { title: string; result: BatchRunResult["baseline"] }) {
  if (!result) return null;
  return (
    <div className="flex-1 rounded-xl border border-slate-200 bg-white p-4">
      <p className="text-xs font-medium text-slate-500">{title}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-slate-950">{formatINR(result.recovered_paise)}</p>
      <p className="mt-0.5 text-xs text-slate-500">{result.recovered_count} of {result.n_events} events recovered</p>
      <p className="mt-2 text-sm font-medium tabular-nums text-slate-700">
        {Math.round(result.recovery_rate * 100)}% recovery rate
      </p>
    </div>
  );
}

export default function ReportsPage() {
  const health = useHealth();
  const lastSimulation = useLastSimulation();
  const runBatch = useRunBatch();

  const [nEvents, setNEvents] = useState(50);
  const [dryRun, setDryRun] = useState(true);
  const [useAi, setUseAi] = useState(false);
  const [seed, setSeed] = useState<string>("");

  const result = runBatch.data ?? lastSimulation.data ?? null;

  function handleRun() {
    runBatch.mutate(
      {
        n_events: nEvents,
        dry_run: dryRun,
        use_ai: useAi,
        random_seed: seed.trim() ? Number(seed) : null,
      },
      {
        onSuccess: () => toast.success("Batch run complete"),
        onError: (err: unknown) =>
          toast.error("Batch run failed", { description: err instanceof Error ? err.message : "Please try again." }),
      }
    );
  }

  const lift =
    result?.baseline && result?.treatment
      ? {
          paise: result.treatment.recovered_paise - result.baseline.recovered_paise,
          count: result.treatment.recovered_count - result.baseline.recovered_count,
          points: (result.treatment.recovery_rate - result.baseline.recovery_rate) * 100,
        }
      : null;

  return (
    <div>
      <PageHeader
        title="Reports"
        description="Run a reproducible synthetic batch through the real pipeline and compare it against a no-intervention baseline."
      />

      <Card className="rounded-2xl border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle>Run a Batch</CardTitle>
          <CardDescription>
            Every batch runs the same events through both a modeled "no recovery system" baseline and the real
            pipeline (treatment), using the same random seed for both — the treatment can only add recoveries on
            top of what would have happened anyway.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <Label htmlFor="n_events">Number of events</Label>
              <Input
                id="n_events"
                type="number"
                min={1}
                max={2000}
                className="mt-1.5"
                value={nEvents}
                onChange={(e) => setNEvents(Number(e.target.value))}
              />
            </div>
            <div>
              <Label htmlFor="seed">Random seed (optional)</Label>
              <Input
                id="seed"
                type="number"
                placeholder="42"
                className="mt-1.5"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
              />
            </div>
          </div>

          <div className="flex flex-col gap-4 sm:flex-row sm:gap-8">
            <div className="flex items-center gap-2.5">
              <Switch id="dry_run" checked={dryRun} onCheckedChange={setDryRun} />
              <Label htmlFor="dry_run" className="font-normal">
                Dry run (no live Razorpay calls)
              </Label>
            </div>
            <div className="flex items-center gap-2.5">
              <Switch id="use_ai" checked={useAi} onCheckedChange={setUseAi} />
              <Label htmlFor="use_ai" className="font-normal">
                Use AI agent for decisions
              </Label>
            </div>
          </div>

          {useAi && !health.data?.ai_configured ? (
            <Alert>
              <Info className="size-4" />
              <AlertDescription>
                No Anthropic key is configured — decisions will fall back to the deterministic policy engine
                automatically, and that fallback will be visible in each event's audit trail.
              </AlertDescription>
            </Alert>
          ) : null}

          <Button onClick={handleRun} disabled={runBatch.isPending} className="w-full sm:w-auto">
            <Play className="size-4" />
            {runBatch.isPending ? "Running…" : "Run Batch"}
          </Button>
        </CardContent>
      </Card>

      <Card className="mt-4 rounded-2xl border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle>Results</CardTitle>
        </CardHeader>
        <CardContent>
          {runBatch.isPending ? (
            <LoadingState rows={3} />
          ) : lastSimulation.isLoading && !runBatch.data ? (
            <LoadingState rows={3} />
          ) : !result ? (
            <EmptyState
              title="No batch has run yet"
              message="Run a batch above to see a baseline-vs-treatment comparison."
              icon={<FlaskConical className="size-5" />}
            />
          ) : (
            <div className="space-y-4">
              <div className="flex flex-col gap-3 sm:flex-row">
                <ResultColumn title="Baseline (no recovery system)" result={result.baseline} />
                <ResultColumn title="Treatment (Reviveo pipeline)" result={result.treatment} />
              </div>

              {lift ? (
                <div className="rounded-xl border border-blue-200 bg-blue-50/60 p-4">
                  <p className="text-sm font-medium text-blue-900">
                    +{formatINR(lift.paise)} recovered · +{lift.count} payments · +{lift.points.toFixed(1)} points
                    recovery rate
                  </p>
                </div>
              ) : null}

              {result.treatment ? (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                  {[
                    ["Executed", result.treatment.executed],
                    ["Scheduled", result.treatment.scheduled],
                    ["Pending Approval", result.treatment.pending_approval],
                    ["Expired", result.treatment.expired],
                    ["Events", result.treatment.n_events],
                  ].map(([label, value]) => (
                    <div key={label as string} className="rounded-lg bg-slate-50 px-3 py-2 text-center">
                      <p className="text-lg font-semibold tabular-nums text-slate-900">{value as number}</p>
                      <p className="text-[11px] text-slate-500">{label}</p>
                    </div>
                  ))}
                </div>
              ) : null}

              <p className="text-xs text-slate-400">{result.label}</p>
              <p className="text-xs text-slate-400">
                Run {formatDateTime(result.created_at)} · {result.use_ai ? "AI-assisted" : "Deterministic"} ·{" "}
                {result.dry_run ? "Dry run" : "Live calls"}
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
