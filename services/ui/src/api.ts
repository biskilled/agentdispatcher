export type Tenant = { tenant_id: string; name: string; role: string };
export type User = { user_id: string; email: string; tenants: Tenant[] };
export type Cost = {
  currency: string | null;
  cost_kind: string;
  cost: string | null;
  attempts: number;
};
export type Overview = {
  counts: {
    attempts: number;
    unknown_cost: number;
    failures: number;
    last_received_at: string | null;
  };
  totals: Cost[];
  breakdown: (Cost & {
    app: string;
    provider: string;
    resource_kind: string;
  })[];
  groups: (Cost & { label: string | null })[];
  trend: (Cost & { day: string; unknown_cost: number })[];
  chart_row_limit: number;
};
export type Usage = Cost & {
  event_id: string;
  occurred_at: string;
  app: string;
  provider: string;
  model: string | null;
  status: string;
  resource_kind: string;
  user_attribution: string;
  verified_user_id: string | null;
  plan_id: string | null;
  payload: Record<string, string | number | null>;
};
export type Job = {
  run_id: string;
  app: string;
  name: string;
  state: string;
  stale: boolean;
  occurred_at: string;
};
export type Key = {
  id: string;
  name: string;
  app: string;
  environment: string;
  revoked_at: string | null;
  expires_at: string;
};
export type Plan = {
  id: string;
  api_id: string;
  effective_at: string;
  plan: {
    name: string;
    pricing: string;
    currency: string;
    unit_price: string | null;
    quota_limit: string | null;
  };
};

/** Call the same-origin backend; tenant selection is always verified server-side. */
export async function apiResponse(
  path: string,
  tenant?: string,
  options: RequestInit = {},
): Promise<Response> {
  const response = await fetch(`/api${path}`, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(tenant ? { "X-Tenant-ID": tenant } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Request failed (${response.status})`,
    );
  }
  return response;
}

/** Decode JSON through the same authenticated boundary used by downloads. */
export async function api<T>(path: string, tenant?: string, options: RequestInit = {}): Promise<T> {
  const response = await apiResponse(path, tenant, options);
  return response.status === 204 ? (undefined as T) : response.json();
}

/** Keep unknown costs distinct from configured zero-cost usage. */
export function money(cost: string | null, currency: string | null): string {
  if (cost === null) return "Unknown";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency || "USD",
    maximumFractionDigits: 4,
  }).format(Number(cost));
}
