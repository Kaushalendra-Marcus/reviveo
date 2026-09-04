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
        description="Track recovery actions that are scheduled, awaiting payment, or need approval."
      />
      {isLoading ? (
        <LoadingState rows={8} />
      ) : isError ? (
        <ErrorState message="Could not load recoveries." onRetry={() => refetch()} />
      ) : (
        <EventTable
          events={data?.items ?? []}
          emptyTitle="Active recovery attempts will appear here."
          emptyMessage="When a recovery action is scheduled, awaiting payment, or needs approval, it will show up here."
        />
      )}
    </div>
  );
}
