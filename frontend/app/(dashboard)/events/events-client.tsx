"use client";

import { useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { EventsToolbar } from "@/components/events/events-toolbar";
import { EventTable } from "@/components/events/event-table";
import { Pagination } from "@/components/shared/pagination";
import { LoadingState, ErrorState } from "@/components/shared/states";
import { useEvents } from "@/hooks/api";
import type { Cause, DataOrigin, EventStatus } from "@/lib/types";

const PAGE_SIZE = 20;

export function EventsPageClient() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const status = (searchParams.get("status") as EventStatus | null) ?? "";
  const cause = (searchParams.get("cause") as Cause | null) ?? "";
  const origin = (searchParams.get("origin") as DataOrigin | null) ?? "";
  const page = Number(searchParams.get("page") ?? "1") || 1;

  const updateParams = useCallback(
    (next: Record<string, string | number | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(next)) {
        if (value === null || value === "") params.delete(key);
        else params.set(key, String(value));
      }
      router.push(`/events?${params.toString()}`);
    },
    [router, searchParams]
  );

  const { data, isLoading, isError, refetch } = useEvents({ status, cause, origin, page, pageSize: PAGE_SIZE });

  return (
    <div>
      <div className="mb-4">
        <EventsToolbar
          status={status}
          cause={cause}
          origin={origin}
          onStatusChange={(s) => updateParams({ status: s, page: 1 })}
          onCauseChange={(c) => updateParams({ cause: c, page: 1 })}
          onOriginChange={(o) => updateParams({ origin: o, page: 1 })}
        />
      </div>

      {isLoading ? (
        <LoadingState rows={8} />
      ) : isError ? (
        <ErrorState message="Could not load events." onRetry={() => refetch()} />
      ) : (
        <>
          <EventTable events={data!.items} />
          <Pagination
            page={data!.page}
            pageSize={PAGE_SIZE}
            total={data!.total}
            onPageChange={(p) => updateParams({ page: p })}
          />
        </>
      )}
    </div>
  );
}
