import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios';
import { message } from 'ant-design-vue';

// 统一 API 客户端：业务页面禁止直接引入 axios
const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

const instance: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

instance.interceptors.response.use(
  (response) => response,
  (error) => {
    // 后端目前直接返回业务字段或 { error }，未走统一 code 包装
    const status = error?.response?.status;
    const payload = error?.response?.data;
    const text =
      (typeof payload === 'string' && payload) ||
      payload?.error ||
      payload?.message ||
      error?.message ||
      '请求失败';
    if (status === 401) {
      message.warning('未登录或登录已过期');
    } else if (status && status >= 500) {
      message.error(`服务端错误：${text}`);
    } else if (status) {
      message.error(text);
    } else {
      message.error(`网络异常：${text}`);
    }
    return Promise.reject(new Error(text));
  },
);

export const apiClient = {
  async get<T = unknown>(path: string, config?: AxiosRequestConfig): Promise<T> {
    const res = await instance.get<T>(path, config);
    return res.data;
  },
  async post<T = unknown>(path: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const res = await instance.post<T>(path, body, config);
    return res.data;
  },
  async put<T = unknown>(path: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const res = await instance.put<T>(path, body, config);
    return res.data;
  },
  async patch<T = unknown>(path: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const res = await instance.patch<T>(path, body, config);
    return res.data;
  },
  async delete<T = unknown>(path: string, config?: AxiosRequestConfig): Promise<T> {
    const res = await instance.delete<T>(path, config);
    return res.data;
  },
};

// SSE 订阅器：直接基于 EventSource，未走 axios。url 不含 /api 前缀时自动拼接
export interface SseSubscriber {
  close: () => void;
}

export interface SseOptions<T> {
  onData?: (data: T) => void;
  onEvent?: (name: string, data: T) => void;
  onError?: (err: Event) => void;
}

export function subscribeSse<T = unknown>(url: string, options: SseOptions<T> = {}): SseSubscriber {
  const fullUrl = url.startsWith('http') || url.startsWith('/') ? url : `${BASE_URL}/${url}`;
  const es = new EventSource(fullUrl);

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as T & { type?: string };
      if ((data as { type?: string }).type === 'heartbeat') return;
      options.onData?.(data);
    } catch {
      // 解析失败忽略
    }
  };

  es.addEventListener('done', (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data) as T;
      options.onData?.(data);
      options.onEvent?.('done', data);
    } catch {
      /* noop */
    }
  });

  es.addEventListener('heartbeat', () => {
    /* 仅用于保活，忽略 */
  });

  es.onerror = (err) => {
    options.onError?.(err);
  };

  return {
    close: () => es.close(),
  };
}

export { BASE_URL };
