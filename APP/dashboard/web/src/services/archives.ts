import { apiClient } from './apiClient';
import type { ArchiveDetail, ArchivePage } from '@/types/domain';

export function getArchives(): Promise<{ pages: ArchivePage[]; total: number }> {
  return apiClient.get('/archives');
}

export function getArchiveDetail(contentHash: string): Promise<ArchiveDetail> {
  return apiClient.get(`/archives/${encodeURIComponent(contentHash)}`);
}
