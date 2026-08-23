import {
  ACTIVE_EVENT_STATUSES,
  type EventStatus,
} from "@/lib/config";
import type {
  BatchRunResult,
  Cause,
  CustomerDetail,
  EventsPage,
  EventDetail,
  EventsQuery,
  AuditTrailResponse,
  GuardrailConfig,
  GuardrailConfigUpdate,
  HealthResponse,
  MutationResult,
  Paginated,
  PendingApproval,
  RangeKey,
  RawLogResponse,
  SavedSimulationRun,
  SimulationResult,
  StrategyBreakdownRow,
  StrategyPerformanceRow,
  SummaryResponse,
  TimeseriesPoint,
  Customer,
} from "@/lib/types";
import { api } from "@/lib/api";

export const queryKeys = {
  health: ["health"] as const,
  summary: (range: RangeKey) => ["summary", range] as const,
  timeseries: (range: RangeKey) => ["timeseries", range] as const,
  strategyBreakdown: (range: RangeKey) => ["strategy-breakdown", range] as const,
  strategies: (range: RangeKey) => ["strategies", range] as const,
  events: (query: EventsQuery) => ["events", query] as const,
  event: (eventId: string) => ["event", eventId] as const,
  auditTrail: (eventId: string) => ["audit-trail", eventId] as const,
  rawLog: (eventId: string) => ["raw-log", eventId] as const,
  globalAudit: (page: number) => ["global-audit", page] as const,
  customers: (page: number) => ["customers", page] as const,
  customer: (customerId: string) => ["customer", customerId] as const,
  guardrails: ["guardrails"] as const,
  pendingApprovals: ["pending-approvals"] as const,
  lastSimulation: ["last-simulation"] as const,
};

export function buildEventsPath(query: EventsQuery): string {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.cause) params.set("cause", query.cause);
  params.set("page", String(query.page ?? 1));
  params.set("page_size", String(query.pageSize ?? 20));
  return `/api/events?${params.toString()}`;
}

/* ── queries ──────────────────────────────────────────────────────────── */
export const fetchHealth = () => api.get<HealthResponse>("/health");
export const fetchSummary = (range: RangeKey) =>
  api.get<SummaryResponse>(`/api/summary?range=${range}`);
export const fetchTimeseries = (range: RangeKey) =>
  api.get<TimeseriesPoint[]>(`/api/summary/timeseries?range=${range}`);
export const fetchStrategyBreakdown = (range: RangeKey) =>
  api.get<StrategyBreakdownRow[]>(`/api/summary/strategy-breakdown?range=${range}`);
export const fetchStrategies = (range: RangeKey) =>
  api.get<StrategyPerformanceRow[]>(`/api/strategies?range=${range}`);
export const fetchEvents = (query: EventsQuery) => api.get<EventsPage>(buildEventsPath(query));
export const fetchEventDetail = (eventId: string) =>
  api.get<EventDetail>(`/api/events/${encodeURIComponent(eventId)}`);
export const fetchAuditTrail = (eventId: string) =>
  api.get<AuditTrailResponse>(`/api/events/${encodeURIComponent(eventId)}/audit-trail`);
export const fetchRawLog = (eventId: string) =>
  api.get<RawLogResponse>(`/api/events/${encodeURIComponent(eventId)}/raw-log`);
export const fetchGlobalAudit = (page: number, pageSize = 50) =>
  api.get<Paginated<AuditLogRow>>(`/api/audit-trail?page=${page}&page_size=${pageSize}`);
import type { AuditLogRow } from "@/lib/types";
export const fetchCustomers = (page: number, pageSize = 20) =>
  api.get<Paginated<Customer>>(`/api/customers?page=${page}&page_size=${pageSize}`);
export const fetchCustomerDetail = (customerId: string) =>
  api.get<CustomerDetail>(`/api/customers/${encodeURIComponent(customerId)}`);
export const fetchGuardrails = () => api.get<GuardrailConfig>("/api/guardrails");
export const fetchPendingApprovals = () =>
  api.get<{ items: PendingApproval[] }>("/api/guardrails/pending-approvals");
export const fetchLastSimulation = () =>
  api.get<SavedSimulationRun>("/api/batch/last-summary");

/** One parallel query per active status; merged client-side into a single
 * accurate "in-progress" view (backend filters by exactly one status). */
async function fetchActiveEvents(): Promise<EventsPage> {
  const results = await Promise.all(
    ACTIVE_EVENT_STATUSES.map((status) =>
      fetchEvents({ status: status as EventStatus, pageSize: 100 })
    )
  );
  const items = results
    .flatMap((r) => r.items)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  return { page: 1, page_size: items.length, total: items.length, items };
}
export const fetchRecoveries = fetchActiveEvents;

/* ── mutations ────────────────────────────────────────────────────────── */
export const approveApproval = (approvalId: number) =>
  api.post<MutationResult>(`/api/approvals/${approvalId}/approve`);
export const denyApproval = (approvalId: number, reason: string) =>
  api.post<MutationResult>(`/api/approvals/${approvalId}/deny`, { reason });
export const updateGuardrails = (update: Partial<GuardrailConfigUpdate>) =>
  api.put<GuardrailConfig>("/api/guardrails", update);
export interface BatchRunParams {
  n_events: number;
  dry_run: boolean;
  use_ai: boolean;
  seed?: number | null;
}
export const runBatch = (params: BatchRunParams) =>
  api.post<BatchRunResult>("/api/batch/run", {
    ...params,
    seed: params.seed ?? undefined,
  });
export interface SimulationParams {
  n_events: number;
  seed?: number | null;
}
export const runSimulation = (params: SimulationParams) =>
  api.post<SimulationResult>("/api/reports/simulate", {
    ...params,
    seed: params.seed ?? undefined,
  });
