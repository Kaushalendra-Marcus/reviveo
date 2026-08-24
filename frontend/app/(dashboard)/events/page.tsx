import { Suspense } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { LoadingState } from "@/components/shared/states";
import { EventsPageClient } from "./events-client";

export default function EventsPage() {
  return (
    <div>
      <PageHeader
        title="Events"
        description="Every detected payment failure and how Reviveo responded."
      />
      <Suspense fallback={<LoadingState rows={8} />}>
        <EventsPageClient />
      </Suspense>
    </div>
  );
}
