export type Money = string | null;
export interface Point { date: string; amount: string }
export interface Sync { id: string; status: string; error_code: string | null }
export interface Balance { value: string; currency: string; components: Record<string, Money>; source: string; synced_at: number; snapshot_id: string }
export interface Bills {
  official_total: Money; entries_total: string; entry_count: number;
  complete_until: string | null; synced_at: number; snapshot_id: string;
  scope: string; summary_basis: string; source: string; daily: Point[];
  reconciliation_delta: Money; gross: Money; discount: Money;
  services: { name: string; amount: string }[];
  projects: { name: string; amount: string }[];
}
export interface Account {
  id: string; provider: string; name: string; alias: string; currency: string;
  period: string; balance: Balance | null; bills: Bills | null;
  balance_sync: Sync | null; bill_sync: Sync | null;
  balance_stale: boolean; bill_stale: boolean; reason: string | null;
  urgency: "critical" | "warning" | "normal" | "pending";
  daily_average: Money; runway_days: Money; trend: Point[];
  consumption_stale: boolean;
  consumption_window: { from: string; to: string; timezone: string } | null;
  storage_available: boolean;
}
export interface Overview {
  period: string; accounts: Account[];
  totals: { currency: string; amount: Money; covered: number; total_accounts: number; stale: boolean; trend: Point[]; daily_average: Money }[];
  worker_error: string | null;
}
export interface Entry {
  provider_record_id: string | null;
  id: string; day: string; service: string; resource: string; currency: string;
  net: string; gross: Money; discount: Money; project: string; granularity: string;
}
export interface EntryPage { items: Entry[]; next_cursor: string | null; snapshot_id: string | null; total: number | null }
