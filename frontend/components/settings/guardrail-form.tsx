"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Info } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { LoadingState, ErrorState } from "@/components/shared/states";
import { useGuardrails, useUpdateGuardrails } from "@/hooks/api";
import { DISABLED_CHANNELS, KNOWN_CHANNELS } from "@/lib/config";
import { formatDateTime } from "@/lib/formatters";
import type { GuardrailConfigInput } from "@/lib/types";

function toInput(cfg: GuardrailConfigInput): GuardrailConfigInput {
  return { ...cfg, allowed_channels: [...cfg.allowed_channels] };
}

export function GuardrailForm() {
  const { data, isLoading, isError, refetch } = useGuardrails();
  const update = useUpdateGuardrails();

  const [form, setForm] = useState<GuardrailConfigInput | null>(null);

  useEffect(() => {
    if (data) setForm(toInput(data));
  }, [data]);

  if (isLoading || !form) return <LoadingState rows={6} />;
  if (isError) return <ErrorState message="Could not load guardrail settings." onRetry={() => refetch()} />;

  const dirty = data ? JSON.stringify(toInput(data)) !== JSON.stringify(form) : false;
  const thresholdInvalid = form.low_confidence >= form.high_confidence;

  function set<K extends keyof GuardrailConfigInput>(key: K, value: GuardrailConfigInput[K]) {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  function toggleChannel(channel: string, enabled: boolean) {
    if (!form) return;
    const next = enabled
      ? [...new Set([...form.allowed_channels, channel])]
      : form.allowed_channels.filter((c) => c !== channel);
    set("allowed_channels", next);
  }

  function handleSave() {
    if (!form || thresholdInvalid) return;
    update.mutate(form, {
      onSuccess: () => toast.success("Guardrail settings saved"),
      onError: (err: unknown) =>
        toast.error("Could not save settings", {
          description: err instanceof Error ? err.message : "Please try again.",
        }),
    });
  }

  return (
    <div className="space-y-4">
      {form.environment === "production" ? (
        <Alert className="border-amber-200 bg-amber-50 text-amber-900">
          <AlertTriangle className="size-4" />
          <AlertTitle>Production environment</AlertTitle>
          <AlertDescription className="text-amber-800">
            Actions in this environment can move real money through live Razorpay credentials.
          </AlertDescription>
        </Alert>
      ) : null}

      <Card className="rounded-2xl border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle>Environment</CardTitle>
          <CardDescription>Which Razorpay credentials this merchant's actions run against.</CardDescription>
        </CardHeader>
        <CardContent>
          <Select value={form.environment} onValueChange={(v) => set("environment", v as "test" | "production")}>
            <SelectTrigger className="w-[220px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="test">Test</SelectItem>
              <SelectItem value="production">Production</SelectItem>
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      <Card className="rounded-2xl border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle>Confidence Thresholds</CardTitle>
          <CardDescription>
            Below the low threshold, actions are always escalated to you. Above the high threshold, actions
            auto-execute once guardrails pass. In between, only low-risk actions auto-execute.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div>
            <div className="mb-2 flex items-center justify-between">
              <Label>High confidence</Label>
              <span className="text-sm font-medium tabular-nums text-slate-900">
                {Math.round(form.high_confidence * 100)}%
              </span>
            </div>
            <Slider
              value={[form.high_confidence]}
              min={0}
              max={1}
              step={0.01}
              onValueChange={([v]) => set("high_confidence", v)}
            />
          </div>
          <div>
            <div className="mb-2 flex items-center justify-between">
              <Label>Low confidence (escalation floor)</Label>
              <span className="text-sm font-medium tabular-nums text-slate-900">
                {Math.round(form.low_confidence * 100)}%
              </span>
            </div>
            <Slider
              value={[form.low_confidence]}
              min={0}
              max={1}
              step={0.01}
              onValueChange={([v]) => set("low_confidence", v)}
            />
          </div>
          {thresholdInvalid ? (
            <p className="flex items-center gap-1.5 text-xs font-medium text-red-600">
              <AlertTriangle className="size-3.5" />
              Low confidence must be less than high confidence.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card className="rounded-2xl border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle>Retry &amp; Recovery Window</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <Label htmlFor="max_retries">Max retries per event</Label>
            <Input
              id="max_retries"
              type="number"
              min={1}
              max={10}
              className="mt-1.5"
              value={form.max_retries}
              onChange={(e) => set("max_retries", Number(e.target.value))}
            />
            {data && data.effective_max_retries < form.max_retries ? (
              <p className="mt-1 flex items-center gap-1 text-xs font-medium text-amber-600">
                <AlertTriangle className="size-3" />
                System ceiling is {data.effective_max_retries} — values above it are clamped server-side.
              </p>
            ) : null}
          </div>
          <div>
            <Label htmlFor="cooldown_hours">Cooldown between attempts (hours)</Label>
            <Input
              id="cooldown_hours"
              type="number"
              min={1}
              max={168}
              className="mt-1.5"
              value={form.cooldown_hours}
              onChange={(e) => set("cooldown_hours", Number(e.target.value))}
            />
          </div>
          <div>
            <Label htmlFor="recovery_window_days">Recovery window (days)</Label>
            <Input
              id="recovery_window_days"
              type="number"
              min={1}
              max={90}
              className="mt-1.5"
              value={form.recovery_window_days}
              onChange={(e) => set("recovery_window_days", Number(e.target.value))}
            />
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-2xl border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle>Spending Caps</CardTitle>
          <CardDescription>Amounts in ₹ — stored as paise internally.</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <Label htmlFor="max_auto_amount">Max autonomous amount per attempt</Label>
            <Input
              id="max_auto_amount"
              type="number"
              min={0}
              className="mt-1.5"
              value={form.max_autonomous_recovery_amount_paise / 100}
              onChange={(e) => set("max_autonomous_recovery_amount_paise", Math.round(Number(e.target.value) * 100))}
            />
            <p className="mt-1 text-xs text-slate-400">Above this, an action always requires approval.</p>
          </div>
          <div>
            <Label htmlFor="daily_cap">Daily recovery value cap</Label>
            <Input
              id="daily_cap"
              type="number"
              min={0}
              className="mt-1.5"
              value={form.daily_recovery_value_cap_paise / 100}
              onChange={(e) => set("daily_recovery_value_cap_paise", Math.round(Number(e.target.value) * 100))}
            />
          </div>
          <div>
            <Label htmlFor="daily_contact_cap">Daily contact cap</Label>
            <Input
              id="daily_contact_cap"
              type="number"
              min={1}
              max={100000}
              className="mt-1.5"
              value={form.daily_contact_cap}
              onChange={(e) => set("daily_contact_cap", Number(e.target.value))}
            />
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-2xl border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle>Allowed Channels</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {KNOWN_CHANNELS.map((channel) => (
            <div key={channel} className="flex items-center justify-between">
              <Label htmlFor={`channel-${channel}`} className="font-normal capitalize">
                {channel.replace("_", " ")}
              </Label>
              <Switch
                id={`channel-${channel}`}
                checked={form.allowed_channels.includes(channel)}
                onCheckedChange={(checked) => toggleChannel(channel, checked)}
              />
            </div>
          ))}
          {DISABLED_CHANNELS.map((channel) => (
            <div key={channel} className="flex items-center justify-between opacity-50">
              <Label className="font-normal capitalize">{channel}</Label>
              <span className="text-xs text-slate-400">Not yet integrated</span>
            </div>
          ))}
          <p className="flex items-start gap-1.5 pt-1 text-xs text-slate-400">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            Only channels actually wired up on the backend can be toggled here.
          </p>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-5 py-4">
        <p className="text-xs text-slate-400">
          {data ? `Last updated ${formatDateTime(data.updated_at)}` : null}
        </p>
        <Button onClick={handleSave} disabled={!dirty || thresholdInvalid || update.isPending}>
          {update.isPending ? "Saving…" : "Save Changes"}
        </Button>
      </div>
    </div>
  );
}
