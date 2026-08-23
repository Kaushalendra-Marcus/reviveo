import type {
  AuditTrailResponse,
  Customer,
  EventDetail,
  EventListItem,
  EventsPage,
} from "@/lib/types";

export type RangeKey = "24h" | "7d" | "30d" | "all";

export interface SummaryResponse {
  range: string;
  revenue_at_risk_paise: number;
  recovered_paise: number;
  recovery_rate_pct: number;
  events_processed: number;
  recovered_count: number;
  actions_executed: number;
  action_success_rate_pct: number;
  deltas_vs_previous: {
    revenue_at_risk_pct: number | null;
    recovered_paise_pct: number | null;
    events_processed_pct: number | null;
  };
}

export interface TimeseriesPoint {
  day: string;
  at_risk_paise: number;
  recovered_paise: number;
}

export interface StrategyBreakdownRow {
  action: string;
  execution_mechanism?: string | null;
  attempts: number;
  recovered_count: number;
  recovered_paise?: number;
  amount_paise?: number;
  share_pct?: number;
  success_rate_pct?: number;
}

export interface CustomersPage {
  page: number;
  total: number;
  items: Customer[];
}

export interface GuardrailConfig {
  environment: "test" | "production";
  allowed_channels: string[];
  recovery_window_days: number;
  high_confidence: number;
  low_confidence: number;
  max_retries: number;
  cooldown_hours: number;
  max_autonomous_recovery_amount_paise: number;
  daily_recovery_value_cap_paise: number;
  daily_contact_cap: number;
  daily_counters?: {
    recovery_value_paise?: number;
    contact_count?: number;
  };
}

export interface PendingApproval {
  id: number;
  event_id: string;
  proposed_action: string;
  amount_paise: number;
  reason: string | null;
  ai_summary: string | null;
  status: string;
  created_at: string;
}

export interface PendingApprovalsResponse {
  items: PendingApproval[];
}

export interface GlobalAuditResponse {
  page: number;
  items: AuditTrailResponse["stages"];
}

export interface RawLogResponse {
  event_id: string;
  webhooks: Array<{
    razorpay_event_id: string;
    event_name: string | null;
    raw_payload: string;
    status: string;
    received_at: string;
  }>;
}

export interface BatchSummary {
  [key: string]: unknown;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "reviveo-dev-key";

function query(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(response.status, text || response.statusText);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  summary: (range: RangeKey) =>
    request<SummaryResponse>(`/api/summary${query({ range })}`),
  timeseries: (range: RangeKey) =>
    request<TimeseriesPoint[]>(
      `/api/summary/timeseries${query({ range, granularity: "day" })}`
    ),
  strategyBreakdown: (range: RangeKey) =>
    request<StrategyBreakdownRow[]>(
      `/api/summary/strategy-breakdown${query({ range })}`
    ),
  strategies: (range: RangeKey) =>
    request<StrategyBreakdownRow[]>(`/api/strategies${query({ range })}`),
  events: (params: {
    page?: number;
    page_size?: number;
    status?: string;
    cause?: string;
  }) => request<EventsPage>(`/api/events${query(params)}`),
  eventDetail: (eventId: string) =>
    request<EventDetail>(`/api/events/${eventId}`),
  eventAuditTrail: (eventId: string) =>
    request<AuditTrailResponse>(`/api/events/${eventId}/audit-trail`),
  rawLog: (eventId: string) =>
    request<RawLogResponse>(`/api/events/${eventId}/raw-log`),
  customers: (page = 1, pageSize = 20) =>
    request<CustomersPage>(
      `/api/customers${query({ page, page_size: pageSize })}`
    ),
  guardrails: () => request<GuardrailConfig>("/api/guardrails"),
  updateGuardrails: (body: GuardrailConfig) =>
    request<GuardrailConfig>("/api/guardrails", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  pendingApprovals: () =>
    request<PendingApprovalsResponse>("/api/guardrails/pending-approvals"),
  approve: (approvalId: number) =>
    request<{ ok: boolean }>(`/api/approvals/${approvalId}/approve`, {
      method: "POST",
    }),
  deny: (approvalId: number, reason: string) =>
    request<{ ok: boolean }>(`/api/approvals/${approvalId}/deny`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  auditTrail: (page = 1, pageSize = 50) =>
    request<GlobalAuditResponse>(
      `/api/audit-trail${query({ page, page_size: pageSize })}`
    ),
  batchLastSummary: () => request<BatchSummary>("/api/batch/last-summary"),
  injectDemoEvent: () =>
    request<{ ingested: string; result: unknown }>("/api/demo/inject-event", {
      method: "POST",
      body: JSON.stringify({ type: "payment_failed" }),
    }),
};

export function formatINRFromPaise(value: number | null | undefined) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format((value ?? 0) / 100);
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export type { EventListItem };
