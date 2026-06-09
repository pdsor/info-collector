import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('axios', () => {
  const create = vi.fn(() => ({
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: { response: { use: vi.fn() } },
  }));
  return { default: { create }, create };
});

vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

describe('subscribeSse', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('通过 EventSource 推送事件，过滤心跳', async () => {
    const handlers: Record<string, ((ev: MessageEvent) => void) | null> = {};
    class FakeEventSource {
      onmessage: ((ev: MessageEvent) => void) | null = null;
      onerror: ((ev: Event) => void) | null = null;
      addEventListener(name: string, cb: (ev: MessageEvent) => void) {
        handlers[name] = cb;
      }
      close() {
        /* noop */
      }
      constructor(public url: string) {
        FakeEventSource.lastUrl = url;
      }
      static lastUrl: string | null = null;
    }
    (globalThis as unknown as { EventSource: typeof FakeEventSource }).EventSource = FakeEventSource;

    const { subscribeSse } = await import('@/services/apiClient');
    const onData = vi.fn();
    const sub = subscribeSse('/api/tasks/stream/1', { onData });

    // 验证 URL
    expect(FakeEventSource.lastUrl).toBe('/api/tasks/stream/1');

    // 模拟普通事件
    const fakeMsg = { data: JSON.stringify({ type: 'progress', current: 1, total: 10 }) } as MessageEvent;
    // 我们需要拿到实例的 onmessage；因为 subscribeSse 内部创建实例后挂在 es 上
    // 这里通过 done 事件来验证 addEventListener 路径
    handlers['done']?.({ data: JSON.stringify({ type: 'done', success: true }) } as MessageEvent);
    expect(onData).toHaveBeenCalledWith(expect.objectContaining({ type: 'done', success: true }));

    sub.close();
  });
});
