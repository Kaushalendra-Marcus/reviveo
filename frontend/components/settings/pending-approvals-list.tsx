"use client";

import { useState } from "react";
import Link from "next/link";
import { Bot, CheckCircle2, ExternalLink, XCircle } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/shared/states";
import { useApproveApproval, useDenyApproval, usePendingApprovals } from "@/hooks/api";
import { ACTION_LABELS, MECHANISM_LABELS, formatDateTime, formatINR } from "@/lib/formatters";
import type { PendingApproval } from "@/lib/types";

export function PendingApprovalsList() {
  const { data: approvals, isLoading } = usePendingApprovals();
  const [confirmTarget, setConfirmTarget] = useState<{ approval: PendingApproval; action: "approve" | "deny" } | null>(null);
  const [resultLink, setResultLink] = useState<string | null>(null);

  const approve = useApproveApproval();
  const deny = useDenyApproval();

  function closeDialog() {
    setConfirmTarget(null);
    setResultLink(null);
  }

  function handleConfirm() {
    if (!confirmTarget) return;
    const { approval, action } = confirmTarget;
    const mutation = action === "approve" ? approve : deny;
    mutation.mutate(approval.id, {
      onSuccess: (data) => {
        if (action === "approve" && data.short_url) {
          // Keep the dialog open one more beat so the merchant can actually
          // click through to the payment link — closing immediately (the old
          // behavior) meant the link Reviveo just created was never shown
          // anywhere in the dashboard.
          setResultLink(data.short_url);
        } else {
          toast.success(action === "approve" ? "Action approved and executed" : "Action denied");
          closeDialog();
        }
      },
      onError: (err: unknown) => {
        toast.error("Something went wrong", {
          description: err instanceof Error ? err.message : "Please try again.",
        });
      },
    });
  }

  if (isLoading) {
    return <div className="h-32 animate-pulse rounded-2xl bg-slate-100" />;
  }

  if (!approvals || approvals.length === 0) {
    return (
      <EmptyState
        title="Nothing waiting for approval"
        message="Actions that need human sign-off (low confidence, above the autonomous amount cap, or an outright escalation) will show up here."
        icon={<CheckCircle2 className="size-5" />}
      />
    );
  }

  return (
    <>
      <div className="space-y-3">
        {approvals.map((approval) => (
          <Card key={approval.id} className="rounded-2xl border-amber-200 bg-amber-50/40 shadow-sm">
            <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0 space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    href={`/events/${encodeURIComponent(approval.event_id)}`}
                    className="font-mono text-xs font-medium text-blue-700 hover:underline"
                  >
                    {approval.event_id}
                  </Link>
                  <Badge variant="outline" className="rounded-full border-slate-200 bg-white text-[11px]">
                    {ACTION_LABELS[approval.proposed_action]}
                  </Badge>
                  {approval.execution_mechanism ? (
                    <Badge variant="outline" className="rounded-full border-slate-200 bg-white text-[11px] text-slate-500">
                      {MECHANISM_LABELS[approval.execution_mechanism] ?? approval.execution_mechanism}
                    </Badge>
                  ) : null}
                  <span className="text-xs font-semibold text-slate-900">{formatINR(approval.amount_paise)}</span>
                </div>
                {approval.ai_summary ? (
                  <p className="flex items-start gap-1.5 text-sm text-slate-700">
                    <Bot className="mt-0.5 size-3.5 shrink-0 text-blue-600" />
                    {approval.ai_summary}
                  </p>
                ) : approval.reason ? (
                  <p className="text-sm text-slate-700">{approval.reason}</p>
                ) : null}
                <p className="text-xs text-slate-400">Raised {formatDateTime(approval.created_at)}</p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="border-red-200 text-red-700 hover:bg-red-50 hover:text-red-800"
                  onClick={() => setConfirmTarget({ approval, action: "deny" })}
                >
                  <XCircle className="size-3.5" />
                  Deny
                </Button>
                <Button size="sm" onClick={() => setConfirmTarget({ approval, action: "approve" })}>
                  <CheckCircle2 className="size-3.5" />
                  Approve
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={Boolean(confirmTarget)} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent>
          {resultLink ? (
            <>
              <DialogHeader>
                <DialogTitle>Recovery link created</DialogTitle>
                <DialogDescription>
                  Reviveo created a real Razorpay payment link for this recovery. Open it to complete
                  (or test) the payment — the event updates automatically once Razorpay confirms the outcome.
                </DialogDescription>
              </DialogHeader>
              <a
                href={resultLink}
                target="_blank"
                rel="noreferrer noopener"
                className="flex items-center justify-between gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800 hover:bg-emerald-100"
              >
                <span className="truncate">{resultLink}</span>
                <ExternalLink className="size-4 shrink-0" />
              </a>
              <DialogFooter>
                <Button onClick={closeDialog}>Done</Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle>
                  {confirmTarget?.action === "approve" ? "Approve this action?" : "Deny this action?"}
                </DialogTitle>
                <DialogDescription>
                  {confirmTarget?.action === "approve" ? (
                    <>
                      This will execute <strong>{confirmTarget && ACTION_LABELS[confirmTarget.approval.proposed_action]}</strong> for{" "}
                      <strong>{confirmTarget && formatINR(confirmTarget.approval.amount_paise)}</strong> right away.
                    </>
                  ) : (
                    "This event will be closed without this action running. This cannot be undone."
                  )}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={closeDialog}>
                  Cancel
                </Button>
                <Button
                  variant={confirmTarget?.action === "deny" ? "destructive" : "default"}
                  onClick={handleConfirm}
                  disabled={approve.isPending || deny.isPending}
                >
                  {approve.isPending || deny.isPending
                    ? "Working…"
                    : confirmTarget?.action === "approve"
                      ? "Approve & Execute"
                      : "Deny"}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
