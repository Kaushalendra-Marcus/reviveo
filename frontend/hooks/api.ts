import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";

import { ACTIVE_EVENT_POLL_MS, ACTIVE_EVENT_STATUSES, POLL_INTERVAL_MS } from "@/lib/config";
import type {
  ApprovalActionResult,
  AuditEntryOut,
  BatchRunInput,
  BatchRunResult,
  CombinedTimeseriesPoint,
  Customer,
  CustomersPage,
  EventDetail,
  EventOut,
  EventsPage,
  EventsQuery,
  EventStatus,
  GuardrailConfig,
  GuardrailConfigInput,
  HealthResponse,
  PendingApproval,
  RangeDays,
  RawLogResponse,
  StrategyRow,
  TimeseriesPoint,
} from "@/lib/types";
import { api } from "@/lib/api";

export const queryKeys = {
  health: ["health"] as const,
  summary: (range: RangeDays) => ["summary", range] as const,
  timeseries: (range: RangeDays) => ["timeseries", range] as const,
  strategyBreakdown: (range: RangeDays) => ["strategy-breakdown", range] as const,
  strategies: (range: RangeDays) => ["strategies", range] as const,
  events: (query: EventsQuery) => ["events", query] as const,
  event: (eventId: string) => ["event", eventId] as const,
  auditTrail: (eventId: string) => ["audit-trail", eventId] as const,
  rawLog: (eventId: string) => ["raw-log", eventId] as const,
  globalAudit: (page: number) => ["global-audit", page] as const,
  customers: (page: number) => ["customers", page] as const,
  guardrails: ["guardrails"] as const,
  pendingApprovals: ["pending-approvals"] as const,
  lastSimulation: ["last-simulation"] as const,
  recoveries: ["recoveries"] as const,
};

function buildEventsPath(query: EventsQuery): string {
  const params = new URLSearchParams();
  if (query.status) params.set("status", query.status);
  if (query.cause) params.set("cause", query.cause);
  params.set("page", String(query.page ?? 1));
  params.set("page_size", String(query.pageSize ?? 20));
  return `/api/events?${params.toString()}`;
}

/* ── raw fetchers — one function per backend/app/api/routes.py route ────── */
export const fetchHealth = () => api.get<HealthResponse>("/health");
export const fetchSummary = (range: RangeDays) => api.get<import("@/lib/types").SummaryResponse>(`/api/summary?range=${range}`);
export const fetchTimeseries = (range: RangeDays, metric: "recovered" | "at_risk") =>
  api.get<TimeseriesPoint[]>(`/api/summary/timeseries?range=${range}&metric=${metric}`);
export const fetchStrategyBreakdown = (range: RangeDays) =>
  api.get<StrategyRow[]>(`/api/summary/strategy-breakdown?range=${range}`);
export const fetchStrategies = (range: RangeDays) => api.get<StrategyRow[]>(`/api/strategies?range=${range}`);
export const fetchEvents = (query: EventsQuery) => api.get<EventsPage>(buildEventsPath(query));
export const fetchEventDetail = (eventId: string) =>
  api.get<EventDetail>(`/api/events/${encodeURIComponent(eventId)}`);
export const fetchAuditTrail = async (eventId: string): Promise<AuditEntryOut[]> => {
  const data = await api.get<AuditEntryOut[] | { event_id: string; stages: AuditEntryOut[] }>(
    `/api/events/${encodeURIComponent(eventId)}/audit-trail`
  );
  if (Array.isArray(data)) return data;
  return (data as { stages: AuditEntryOut[] }).stages ?? [];
};
export const fetchRawLog = (eventId: string) =>
  api.get<RawLogResponse>(`/api/events/${encodeURIComponent(eventId)}/raw-log`);
/** Accepts both the current `{items,total,page,page_size}` wrapper and the
 * legacy bare array for backward compatibility with older deployments. */
export interface GlobalAuditPage {
  items: AuditEntryOut[];
  total: number;
}
export const fetchGlobalAudit = async (page: number, pageSize = 50): Promise<GlobalAuditPage> => {
  const data = await api.get<GlobalAuditPage | AuditEntryOut[]>(
    `/api/audit-trail?page=${page}&page_size=${pageSize}`
  );
  if (Array.isArray(data)) return { items: data, total: data.length };
  return { items: data.items ?? [], total: data.total };
};
export const fetchCustomers = (page: number, pageSize = 20) =>
  api.get<CustomersPage>(`/api/customers?page=${page}&page_size=${pageSize}`);
export const fetchGuardrails = () => api.get<GuardrailConfig>("/api/guardrails");
export const fetchPendingApprovals = async (): Promise<PendingApproval[]> => {
  const data = await api.get<PendingApproval[] | { items: PendingApproval[] }>(
    "/api/guardrails/pending-approvals"
  );
  if (Array.isArray(data)) return data;
  return (data as { items: PendingApproval[] }).items ?? [];
};
export const fetchLastSimulation = () => api.get<BatchRunResult | null>("/api/batch/last-summary");

/** No day is guaranteed to appear in both series (a day with only at-risk
 * events and no recoveries yet only shows up in the `at_risk` series, and
 * vice versa) — union the day keys and default the missing side to 0. */
export async function fetchCombinedTimeseries(range: RangeDays): Promise<CombinedTimeseriesPoint[]> {
  const [recovered, atRisk] = await Promise.all([
    fetchTimeseries(range, "recovered"),
    fetchTimeseries(range, "at_risk"),
  ]);
  const byDay = new Map<string, CombinedTimeseriesPoint>();
  for (const p of atRisk) byDay.set(p.day, { day: p.day, at_risk_paise: p.amount_paise, recovered_paise: 0 });
  for (const p of recovered) {
    const existing = byDay.get(p.day);
    if (existing) existing.recovered_paise = p.amount_paise;
    else byDay.set(p.day, { day: p.day, at_risk_paise: 0, recovered_paise: p.amount_paise });
  }
  return Array.from(byDay.values()).sort((a, b) => a.day.localeCompare(b.day));
}

/** One parallel request per active status; merged client-side into a single
 * "in-progress" view. The backend filters events by exactly one status per
 * call, so there is no single-request way to ask for "any of these statuses". */
async function fetchActiveEvents(): Promise<EventsPage> {
  const results = await Promise.all(
    ACTIVE_EVENT_STATUSES.map((status) => fetchEvents({ status: status as EventStatus, pageSize: 100 }))
  );
  const items: EventOut[] = results
    .flatMap((r) => r.items)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  return { page: 1, page_size: items.length, total: items.length, items };
}
export const fetchRecoveries = fetchActiveEvents;

/* ── mutations (raw) ─────────────────────────────────────────────────── */
export const approveApproval = (approvalId: number, resolvedBy = "merchant") =>
  api.post<ApprovalActionResult>(`/api/approvals/${approvalId}/approve`, { resolved_by: resolvedBy });
export const denyApproval = (approvalId: number, resolvedBy = "merchant") =>
  api.post<ApprovalActionResult>(`/api/approvals/${approvalId}/deny`, { resolved_by: resolvedBy });
export const updateGuardrails = (input: GuardrailConfigInput) =>
  api.put<GuardrailConfig>("/api/guardrails", input);
export const runBatch = (params: BatchRunInput) =>
  api.post<BatchRunResult>("/api/batch/run", { ...params, random_seed: params.random_seed ?? undefined });

/* ── React Query hooks ───────────────────────────────────────────────── *
 * Polling: summary/events/audit poll at POLL_INTERVAL_MS; anything showing
 * an in-flight event (detail, recoveries) polls faster at
 * ACTIVE_EVENT_POLL_MS. `refetchInterval` only runs while mounted/observed. */

export function useHealth() {
  return useQuery({ queryKey: queryKeys.health, queryFn: fetchHealth, refetchInterval: POLL_INTERVAL_MS });
}

export function useSummary(range: RangeDays) {
  return useQuery({
    queryKey: queryKeys.summary(range),
    queryFn: () => fetchSummary(range),
    refetchInterval: POLL_INTERVAL_MS,
  });
}

export function useTimeseries(range: RangeDays) {
  return useQuery({
    queryKey: queryKeys.timeseries(range),
    queryFn: () => fetchCombinedTimeseries(range),
    refetchInterval: POLL_INTERVAL_MS,
  });
}

export function useStrategyBreakdown(range: RangeDays) {
  return useQuery({
    queryKey: queryKeys.strategyBreakdown(range),
    queryFn: () => fetchStrategyBreakdown(range),
    refetchInterval: POLL_INTERVAL_MS,
  });
}

export function useStrategies(range: RangeDays) {
  return useQuery({
    queryKey: queryKeys.strategies(range),
    queryFn: () => fetchStrategies(range),
    refetchInterval: POLL_INTERVAL_MS,
  });
}

export function useEvents(query: EventsQuery) {
  return useQuery({
    queryKey: queryKeys.events(query),
    queryFn: () => fetchEvents(query),
    refetchInterval: POLL_INTERVAL_MS,
    placeholderData: keepPreviousData,
  });
}

export function useRecoveries() {
  return useQuery({
    queryKey: queryKeys.recoveries,
    queryFn: fetchRecoveries,
    refetchInterval: ACTIVE_EVENT_POLL_MS,
  });
}

export function useEventDetail(eventId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.event(eventId ?? ""),
    queryFn: () => fetchEventDetail(eventId as string),
    enabled: Boolean(eventId),
    refetchInterval: ACTIVE_EVENT_POLL_MS,
  });
}

export function useAuditTrail(eventId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.auditTrail(eventId ?? ""),
    queryFn: () => fetchAuditTrail(eventId as string),
    enabled: Boolean(eventId),
    refetchInterval: ACTIVE_EVENT_POLL_MS,
  });
}

export function useRawLog(eventId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.rawLog(eventId ?? ""),
    queryFn: () => fetchRawLog(eventId as string),
    enabled: Boolean(eventId),
  });
}

/** Real `total` from the backend wrapper (legacy bare-array responses fall
 * back to length-based inference inside fetchGlobalAudit). */
export function useGlobalAudit(page: number, pageSize = 50) {
  return useQuery({
    queryKey: queryKeys.globalAudit(page),
    queryFn: () => fetchGlobalAudit(page, pageSize),
    refetchInterval: POLL_INTERVAL_MS,
    placeholderData: keepPreviousData,
  });
}

export function useCustomers(page: number) {
  return useQuery({
    queryKey: queryKeys.customers(page),
    queryFn: () => fetchCustomers(page),
    placeholderData: keepPreviousData,
  });
}

export function useGuardrails() {
  return useQuery({ queryKey: queryKeys.guardrails, queryFn: fetchGuardrails });
}

export function usePendingApprovals() {
  return useQuery({
    queryKey: queryKeys.pendingApprovals,
    queryFn: fetchPendingApprovals,
    refetchInterval: POLL_INTERVAL_MS,
  });
}

/** Returns `null` (not a 404) when no batch has ever been run. */
export function useLastSimulation() {
  return useQuery({ queryKey: queryKeys.lastSimulation, queryFn: fetchLastSimulation, retry: false });
}

/* ── mutation hooks ───────────────────────────────────────────────────── */
function invalidateAfterApprovalDecision(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: queryKeys.pendingApprovals });
  qc.invalidateQueries({ queryKey: ["events"] });
  qc.invalidateQueries({ queryKey: ["event"] });
  qc.invalidateQueries({ queryKey: queryKeys.recoveries });
  qc.invalidateQueries({ queryKey: ["audit-trail"] });
  // Approval execution writes global audit rows too — refresh the
  // audit-trail page if it is mounted.
  qc.invalidateQueries({ queryKey: ["global-audit"] });
}

export function useApproveApproval() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (approvalId: number) => approveApproval(approvalId),
    onSuccess: () => invalidateAfterApprovalDecision(qc),
  });
}

export function useDenyApproval() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (approvalId: number) => denyApproval(approvalId),
    onSuccess: () => invalidateAfterApprovalDecision(qc),
  });
}

export function useUpdateGuardrails() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: GuardrailConfigInput) => updateGuardrails(input),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.guardrails, data);
    },
  });
}

export function useRunBatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: BatchRunInput) => runBatch(params),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.lastSimulation, data);
      qc.invalidateQueries({ queryKey: ["summary"] });
      qc.invalidateQueries({ queryKey: ["timeseries"] });
      qc.invalidateQueries({ queryKey: ["strategy-breakdown"] });
      qc.invalidateQueries({ queryKey: ["strategies"] });
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: queryKeys.recoveries });
    },
  });
}
