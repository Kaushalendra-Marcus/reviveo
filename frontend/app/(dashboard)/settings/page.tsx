"use client";

import { PageHeader } from "@/components/shared/page-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { GuardrailForm } from "@/components/settings/guardrail-form";
import { PendingApprovalsList } from "@/components/settings/pending-approvals-list";
import { usePendingApprovals } from "@/hooks/api";

export default function SettingsPage() {
  const { data: approvals } = usePendingApprovals();
  const pendingCount = approvals?.length ?? 0;

  return (
    <div>
      <PageHeader title="Settings" description="Guardrails, thresholds, and actions waiting on your approval." />

      <Tabs defaultValue="approvals">
        <TabsList>
          <TabsTrigger value="approvals" className="gap-1.5">
            Pending Approvals
            {pendingCount > 0 ? (
              <Badge variant="outline" className="rounded-full border-amber-200 bg-amber-50 px-1.5 text-[10px] text-amber-700">
                {pendingCount}
              </Badge>
            ) : null}
          </TabsTrigger>
          <TabsTrigger value="guardrails">Guardrails</TabsTrigger>
        </TabsList>
        <TabsContent value="approvals" className="mt-4">
          <PendingApprovalsList />
        </TabsContent>
        <TabsContent value="guardrails" className="mt-4">
          <GuardrailForm />
        </TabsContent>
      </Tabs>
    </div>
  );
}
