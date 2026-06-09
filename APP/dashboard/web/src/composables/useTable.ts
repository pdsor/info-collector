import { reactive, ref, computed } from 'vue';
import type { Ref } from 'vue';

// useTable：统一封装列表分页、loading、刷新与查询参数
export interface UseTableOptions<T> {
  fetcher: (params: { page: number; pageSize: number }) => Promise<{ records: T[]; total: number }>;
  pageSize?: number;
}

export interface PaginationState {
  current: number;
  pageSize: number;
  total: number;
  showTotal: (total: number) => string;
  showSizeChanger: boolean;
}

export function useTable<T = unknown>(options: UseTableOptions<T>) {
  const loading = ref(false);
  const records: Ref<T[]> = ref([]);
  const pagination = reactive<PaginationState>({
    current: 1,
    pageSize: options.pageSize ?? 8,
    total: 0,
    showTotal: (total: number) => `共 ${total} 条`,
    showSizeChanger: false,
  });

  async function load() {
    loading.value = true;
    try {
      const { records: rows, total } = await options.fetcher({
        page: pagination.current,
        pageSize: pagination.pageSize,
      });
      records.value = rows;
      pagination.total = total;
    } finally {
      loading.value = false;
    }
  }

  function refresh() {
    pagination.current = 1;
    return load();
  }

  function handleChange(page: { current?: number; pageSize?: number }) {
    if (page.current) pagination.current = page.current;
    if (page.pageSize) pagination.pageSize = page.pageSize;
    return load();
  }

  return {
    loading,
    records,
    pagination,
    load,
    refresh,
    handleChange,
  };
}

// 客户端分页：当后端一次性返回全量时使用
export function useClientTable<T>(source: Ref<T[]>, pageSize = 8) {
  const pagination = reactive<PaginationState>({
    current: 1,
    pageSize,
    total: 0,
    showTotal: (total: number) => `共 ${total} 条`,
    showSizeChanger: false,
  });

  const paged = computed(() => {
    pagination.total = source.value.length;
    const start = (pagination.current - 1) * pagination.pageSize;
    return source.value.slice(start, start + pagination.pageSize);
  });

  function reset() {
    pagination.current = 1;
  }

  function handleChange(page: { current?: number; pageSize?: number }) {
    if (page.current) pagination.current = page.current;
    if (page.pageSize) pagination.pageSize = page.pageSize;
  }

  return { pagination, paged, reset, handleChange };
}
