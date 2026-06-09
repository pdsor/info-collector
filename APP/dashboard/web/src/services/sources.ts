import { apiClient } from './apiClient';
import type { SourceItem, SourceSummary } from '@/types/domain';

export function getSourcesList(): Promise<{ sources: SourceItem[] }> {
  return apiClient.get('/sources');
}

export function getSourcesSummary(): Promise<SourceSummary> {
  return apiClient.get('/sources/summary');
}
