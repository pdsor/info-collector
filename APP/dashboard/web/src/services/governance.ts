import { apiClient } from './apiClient';
import type { GovernanceRecord, GovernanceSummary } from '@/types/domain';

export interface GovernancePayload {
  summary: GovernanceSummary;
  records: GovernanceRecord[];
}

export function getGovernanceSummary(): Promise<GovernancePayload> {
  return apiClient.get('/governance/summary');
}
