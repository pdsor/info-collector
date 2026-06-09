<template>
  <SropPage>
    <SropPageHeader title="来源中心" description="来源注册、状态、信任分与解析策略，由 YAML 规则派生。">
      <a-button @click="refresh"><ReloadOutlined /> 刷新</a-button>
    </SropPageHeader>

    <div class="srop-metric-grid">
      <div class="srop-metric-card">
        <span class="srop-metric-label">来源总数</span>
        <strong class="srop-metric-value">{{ fmtNumber(summary.total) }}</strong>
      </div>
      <div class="srop-metric-card">
        <span class="srop-metric-label">已启用</span>
        <strong class="srop-metric-value">{{ fmtNumber(summary.active) }}</strong>
      </div>
      <div class="srop-metric-card">
        <span class="srop-metric-label">已停用</span>
        <strong class="srop-metric-value">{{ fmtNumber(summary.paused) }}</strong>
      </div>
      <div class="srop-metric-card">
        <span class="srop-metric-label">平均信任分</span>
        <strong class="srop-metric-value">{{ fmtPercent(summary.avg_trust_score) }}</strong>
      </div>
    </div>

    <a-card class="srop-search-card" :bordered="false">
      <a-form layout="inline" class="srop-search-form">
        <a-form-item label="关键字">
          <a-input
            v-model:value="filters.keyword"
            placeholder="来源名 / 域名 / 分类 / 解析策略"
            allow-clear
            autocomplete="off"
            style="width: 260px"
          />
        </a-form-item>
        <a-form-item label="状态">
          <a-select
            v-model:value="filters.status"
            allow-clear
            placeholder="全部"
            style="width: 140px"
            :options="statusOptions"
          />
        </a-form-item>
        <a-form-item label="类型">
          <a-select
            v-model:value="filters.type"
            allow-clear
            placeholder="全部"
            style="width: 140px"
            :options="typeOptions"
          />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" @click="onSearch"><SearchOutlined /> 查询</a-button>
        </a-form-item>
        <a-form-item>
          <a-button @click="onReset">重置</a-button>
        </a-form-item>
      </a-form>
    </a-card>

    <a-card class="srop-table-card" :bordered="false">
      <div class="srop-table-header">
        <div>
          <span class="srop-table-header-title">来源列表</span>
          <span class="srop-table-total">共 {{ filteredSources.length }} 条</span>
        </div>
      </div>
      <a-table
        :columns="columns"
        :data-source="filteredSources"
        :loading="loading"
        :pagination="{ pageSize: 8, showTotal: (t: number) => `共 ${t} 条` }"
        row-key="id"
        size="middle"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <strong>{{ record.name }}</strong>
          </template>
          <template v-else-if="column.key === 'type'">
            {{ typeLabel(record.type) }}
          </template>
          <template v-else-if="column.key === 'trust_score'">
            <span class="srop-score-bar"><span :style="{ width: `${(record.trust_score || 0) * 100}%` }"></span></span>
            {{ fmtPercent(record.trust_score) }}
          </template>
          <template v-else-if="column.key === 'anti_crawl_level'">
            {{ antiCrawlLabel(record.anti_crawl_level) }}
          </template>
          <template v-else-if="column.key === 'lifecycle_status'">
            <StatusTag :value="record.lifecycle_status" />
          </template>
          <template v-else-if="column.key === 'rule_path'">
            <code class="srop-mono">{{ record.rule_path }}</code>
          </template>
          <template v-else>{{ textValue(record[column.dataIndex as keyof SourceItem]) }}</template>
        </template>
      </a-table>
    </a-card>
  </SropPage>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue';
import SropPage from '@/components/SropPage.vue';
import SropPageHeader from '@/components/SropPageHeader.vue';
import StatusTag from '@/components/StatusTag.vue';
import { getSourcesList, getSourcesSummary } from '@/services/sources';
import type { SourceItem, SourceSummary } from '@/types/domain';

const loading = ref(false);
const sources = ref<SourceItem[]>([]);
const summary = ref<SourceSummary>({ total: 0, active: 0, paused: 0, avg_trust_score: 0 });

const filters = reactive({
  keyword: '',
  status: undefined as string | undefined,
  type: undefined as string | undefined,
});
const applied = reactive({ ...filters });

const statusOptions = [
  { value: 'ACTIVE', label: '已启用' },
  { value: 'PAUSED', label: '已停用' },
];

const typeOptions = computed(() => {
  const types = new Set(sources.value.map((s) => s.type).filter(Boolean));
  return Array.from(types).map((t) => ({ value: t, label: typeLabel(t) }));
});

function typeLabel(type: string): string {
  return ({ api: '接口', website: '网页', html: '网页' } as Record<string, string>)[type] || type;
}

function antiCrawlLabel(level: string): string {
  return ({ low: '低', medium: '中', high: '高' } as Record<string, string>)[level] || level || '--';
}

const columns = [
  { title: '来源', dataIndex: 'name', key: 'name', width: 200 },
  { title: '域名', dataIndex: 'domain', key: 'domain', width: 200 },
  { title: '类型', dataIndex: 'type', key: 'type', width: 90 },
  { title: '分类', dataIndex: 'category', key: 'category', width: 140 },
  { title: '信任分', dataIndex: 'trust_score', key: 'trust_score', width: 180 },
  { title: '反爬等级', dataIndex: 'anti_crawl_level', key: 'anti_crawl_level', width: 100 },
  { title: '状态', dataIndex: 'lifecycle_status', key: 'lifecycle_status', width: 110 },
  { title: '规则路径', dataIndex: 'rule_path', key: 'rule_path' },
];

const filteredSources = computed(() => {
  const keyword = (applied.keyword || '').trim().toLowerCase();
  return sources.value.filter((source) => {
    if (applied.status && source.lifecycle_status !== applied.status) return false;
    if (applied.type && source.type !== applied.type) return false;
    if (!keyword) return true;
    return [source.name, source.domain, source.category, source.parser_strategy, source.lifecycle_status]
      .some((value) => String(value || '').toLowerCase().includes(keyword));
  });
});

async function load() {
  loading.value = true;
  try {
    const [list, sum] = await Promise.all([getSourcesList(), getSourcesSummary()]);
    sources.value = list.sources || [];
    summary.value = sum;
  } finally {
    loading.value = false;
  }
}

function refresh() {
  return load();
}

function onSearch() {
  Object.assign(applied, filters);
}

function onReset() {
  filters.keyword = '';
  filters.status = undefined;
  filters.type = undefined;
  Object.assign(applied, filters);
  return load();
}

function fmtNumber(v?: number | null) {
  return new Intl.NumberFormat('zh-CN').format(v || 0);
}
function fmtPercent(v?: number | null) {
  return `${Math.round((v || 0) * 100)}%`;
}
function textValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '--';
  return String(value);
}

onMounted(load);
</script>

<style scoped>
.srop-mono {
  font-family: var(--srop-font-mono);
  font-size: 12px;
  color: #344054;
  word-break: break-all;
}
</style>
