import { apiClient } from './apiClient';
import type { HealthCheckReport } from '@/types/domain';

export interface HealthCheckPayload {
  rule: Record<string, unknown>;
  html?: string;
  rule_path?: string;
}

export function checkRuleHealth(payload: HealthCheckPayload): Promise<HealthCheckReport> {
  return apiClient.post('/health/check', payload);
}

export function setHealthBaseline(rulePath: string, html: string): Promise<{ dom_baseline_hash: string }> {
  return apiClient.post('/health/set-baseline', { rule_path: rulePath, html });
}
