import { apiClient, subscribeSse, type SseOptions, type SseSubscriber } from './apiClient';
import type { TaskHistoryItem, TaskItemsResponse, TaskStreamEvent } from '@/types/domain';

export function getTaskHistory(): Promise<{ tasks: TaskHistoryItem[] }> {
  return apiClient.get('/tasks/history');
}

export function getTaskDetail(taskId: number): Promise<TaskHistoryItem> {
  return apiClient.get(`/tasks/${taskId}`);
}

export function getTaskItems(taskId: number): Promise<TaskItemsResponse> {
  return apiClient.get(`/tasks/${taskId}/items`);
}

export async function getTaskLogs(taskId: number): Promise<TaskStreamEvent[]> {
  const text = await apiClient.get<string>(`/tasks/${taskId}/logs`, {
    responseType: 'text',
    transformResponse: [(data) => data],
  });
  return String(text || '')
    .split('\n')
    .filter(Boolean)
    .map((line) => JSON.parse(line) as TaskStreamEvent);
}

export function runAllTasks(): Promise<{ task_id: number; status: string }> {
  return apiClient.post('/tasks/run-all', {});
}

export function runSingleTask(rulePath: string): Promise<{ task_id: number; status: string }> {
  return apiClient.post(`/tasks/run-single/${encodeURIComponent(rulePath)}`, {});
}

// SSE 流：直接走 /api/tasks/stream/<id>
export function streamTask(taskId: number, options: SseOptions<TaskStreamEvent>): SseSubscriber {
  return subscribeSse<TaskStreamEvent>(`/api/tasks/stream/${taskId}`, options);
}
