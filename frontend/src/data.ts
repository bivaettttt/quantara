import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
let token = "";
export function session(value: string) {
  token = value;
}
export async function api<T>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    headers: {
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...(data === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  if (response.status === 204) return undefined as T;
  if (
    response.ok &&
    response.headers.get("Content-Type")?.startsWith("text/csv")
  )
    return (await response.text()) as T;
  const result = await response.json();
  if (!response.ok)
    throw Error(
      result.detail +
        " · " +
        response.status +
        " · " +
        (result.request_id ?? ""),
    );
  return result;
}
export const read = <T>(path: string, enabled = true) =>
  useQuery({
    queryKey: [path],
    queryFn: () => api<T>(path),
    enabled,
    retry: false,
  });
export function useCommand<T>() {
  const query = useQueryClient();
  return useMutation({
    mutationFn: ({ path, data }: { path: string; data?: unknown }) =>
      api<T>(path, "POST", data),
    onSuccess: () => {
      void query.invalidateQueries();
    },
  });
}
export type User = { login: string; name: string; role: string };
export type ReportMeta = {
  id: string;
  start_date: string;
  end_date: string;
  quality: string;
  checksum: string;
  method: string;
  created: string;
};
export type Evidence = {
  raw: number;
  source?: string;
  external_id?: string;
  revision?: number;
  mapping?: number;
  run?: string;
  fx_raw?: number;
  related_raw?: number[];
  amount: string;
};
export type Measure = {
  value: string | null;
  known: string;
  excluded: number[];
  contributions: Evidence[];
};
export type Report = ReportMeta & {
  manifest: {
    mapping: number;
    transform: string;
    unavailable: string[];
    records: Record<string, unknown>[];
    excluded: Record<string, unknown>[];
  };
  result: {
    metrics: Record<string, Measure>;
    breakdown: Record<string, Record<string, string>>;
    budget: {
      month: string;
      category: string;
      actual: string;
      budget: string | null;
      variance: string | null;
      performance: string | null;
    }[];
    reconciliation: {
      code: string;
      object: string;
      expected?: string;
      actual?: string;
      difference?: string | null;
      raw: number[];
    }[];
  };
};
export type Source = {
  source: string;
  sequence: number;
  last_success: string | null;
  last_error: string | null;
  status: string;
};
export type Counts = {
  received: number;
  accepted: number;
  duplicates: number;
  rejected: number;
  start_cursor: number;
  end_cursor: number;
  error: string | null;
};
export type Run = {
  id: string;
  request: string;
  mode: string;
  status: string;
  started: string;
  finished: string;
  summary: {
    sources?: Record<string, Counts>;
    quarantined?: number;
    error?: string;
  };
  issues?: Issue[];
};
export type Issue = {
  id: number;
  source: string;
  dimension: string;
  code: string;
  raw: number | null;
  run: string;
  created: string;
  detail: unknown;
};
export type Raw = {
  id: number;
  source: string;
  entity: string;
  external_id: string;
  revision: number;
  disposition: string;
  received: string;
  run: string;
  hash: string;
  payload: unknown;
  stage: unknown[];
  issues: Issue[];
};
export type Fact = {
  source: string;
  entity: string;
  external_id: string;
  revision: number;
  raw: number;
  mapping: number;
  amount: string | null;
  currency: string | null;
  category: string | null;
  business_date: string | null;
};
export type Comparison = {
  metrics: {
    code: string;
    before: string | null;
    after: string | null;
    delta: string | null;
    percent: string | null;
  }[];
  changed: {
    source: string;
    entity: string;
    external_id: string;
    before: Evidence | null;
    after: Evidence | null;
  }[];
  quality_changes: unknown;
};
