// 通用 API 响应包装与列表查询参数定义

export interface ApiResponse<T = unknown> {
  code?: number;
  message?: string;
  data?: T;
  // 后端目前直接返回业务字段，没有统一包装；保留 ApiResponse 作为未来扩展用
  [key: string]: unknown;
}

export interface PaginatedData<T> {
  records: T[];
  total: number;
  page?: number;
  page_size?: number;
}

// 列表查询参数：模糊字段沿用 { value, operator: '~' } 结构
export interface ListFilterValue {
  value: string | number | null | undefined;
  operator: '~' | '=' | '>' | '<' | '>=' | '<=' | '!=';
}

export type ListFilters = Record<string, ListFilterValue | string | number | undefined | null>;

export interface ListParams {
  page?: number;
  page_size?: number;
  filters?: ListFilters;
}

// SSE 事件
export interface SseHandlers<T = unknown> {
  onData?: (data: T) => void;
  onError?: (err: Event) => void;
  onClose?: () => void;
}
