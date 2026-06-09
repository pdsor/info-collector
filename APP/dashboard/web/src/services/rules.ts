import { apiClient } from './apiClient';
import type { RuleItem, RuleDetail, RulePreviewResult } from '@/types/domain';

export function getRulesList(): Promise<{ rules: RuleItem[] }> {
  return apiClient.get('/rules');
}

export function getRuleDetail(path: string): Promise<RuleDetail> {
  return apiClient.get(`/rules/${encodeURIComponent(path)}`);
}

export function saveRule(path: string, yaml: string): Promise<{ success?: boolean }> {
  return apiClient.post('/rules', { path, yaml });
}

export function previewRule(yaml: string, limit = 5): Promise<RulePreviewResult> {
  return apiClient.post('/rules/preview', { yaml, limit });
}

export function deleteRule(path: string): Promise<{ success?: boolean }> {
  return apiClient.delete(`/rules/${encodeURIComponent(path)}`);
}

export function toggleRule(path: string, enabled: boolean): Promise<{ enabled?: boolean }> {
  return apiClient.post(`/rules/${encodeURIComponent(path)}/toggle`, { enabled });
}

export function runRule(path: string): Promise<{ task_id: number; status: string }> {
  return apiClient.post(`/rules/${encodeURIComponent(path)}/run`, {});
}
