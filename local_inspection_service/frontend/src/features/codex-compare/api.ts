import { apiClient } from '../../api/client';
export const ROOT = '/api/text-compare-codex';
export type Box = [number, number, number, number];
export type Decision = 'MATCH' | 'DIFFERENCES' | 'REVIEW_REQUIRED';
export interface Evidence { original: string; image: string; preview: string; size: [number, number] }
export interface Artifact extends Evidence { id: string; source: 'reference' | 'actual'; box: Box }
export interface ReportItem { id: string; status: 'match' | 'difference' | 'uncertain'; reference_text: string; actual_text: string; explanation: string; reference_box: Box | null; actual_box: Box | null; artifact_ids: string[] }
export interface Region { box: Box; polygon?: [number, number][] | null }
export interface LabelElement { id: string; category: string; name: string; description: string; reference: Region | null; actual: Region | null }
export interface LabelCheck { id: string; element_ids: string[]; dimension: string; expected: string; observed: string; status: string; explanation: string; artifact_ids: string[]; decode_ids: string[] }
export interface LabelIssue { id: string; check_id: string; title: string; explanation: string; reference: Region | null; actual: Region | null; artifact_ids: string[]; resolved: boolean }
export interface Task {
  report_version?: string; skill_version?: string; skill_sha256?: string;
  elements?: LabelElement[]; checks?: LabelCheck[]; issues?: LabelIssue[];
  progress?: { total: number; settled: number; elements: number };
  id: string; status: string; created_at: number; sequence: number; parent_id?: string; error?: string;
  model?: string; session_id?: string; finalized: boolean;
  inputs: { reference_region?: Box; standard_name: string; standard_revision_id: string; standard_revision_number: number; reference: Evidence; actual: Evidence };
  counts: Record<ReportItem['status'], number>;
  summary: { decision: Decision; message: string; checked_scope: string; unchecked_scope: string } | null;
  items?: ReportItem[]; artifacts?: Artifact[];
  reviews?: { key: string; created_at: number; value: { decision: Decision; note: string } }[];
}
export const terminal = (status: string) => ['completed','failed','timed_out','cancelled','interrupted'].includes(status);
export const labels: Record<string, string> = { pending: '待检', not_applicable: '不适用', queued: '排队中', running: '核对中', cancel_requested: '正在取消', completed: '已完成', failed: '失败', timed_out: '超时', cancelled: '已取消', interrupted: '运行中断', match: '一致', difference: '差异', uncertain: '待确认', MATCH: '一致', DIFFERENCES: '存在差异', REVIEW_REQUIRED: '无法确认' };
export const mediaURL = (id: string, hash: string) => `${ROOT}/tasks/${encodeURIComponent(id)}/media/${hash}`;
export const capabilities = () => apiClient.get<{ enabled: boolean; model: string }>(`${ROOT}/capabilities`);
export const listTasks = (before = '') => apiClient.get<{items: Task[]; next_cursor: string | null}>(`${ROOT}/tasks?before=${encodeURIComponent(before)}`);
export const getTask = (id: string) => apiClient.get<Task>(`${ROOT}/tasks/${encodeURIComponent(id)}`);
export const post = <T,>(id: string, action: string, body = {}) => apiClient.post<T>(`${ROOT}/tasks/${encodeURIComponent(id)}/${action}`, body);
