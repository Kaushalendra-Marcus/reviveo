"use client";

import { PageHeader } from "@/components/shared/page-header";
import { LoadingState, ErrorState } from "@/components/shared/states";
import { EventTable } from "@/components/events/event-table";
import { useRecoveries } from "@/hooks/api";

export default function RecoveriesPage() {
  const { data, isLoading, isError, refetch } = useRecoveries();

  return (
    <div>
      <PageHeader
        title="Recoveries"
        description="All in-progress recoveries — waiting for outcome, scheduled or pending approval."
      />
      {isLoading ? (
        <LoadingState rows={8} />
      ) : isError ? (
        <ErrorState message="Could not load recoveries." onRetry={() => refetch()} />
      ) : (
        <EventTable
          events={data?.items ?? []}
          emptyTitle="No active recoveries"
          emptyMessage="When a recovery is scheduled, awaiting payment, or pending approval, it appears here."
        />
      )}
    </div>
  );
}
