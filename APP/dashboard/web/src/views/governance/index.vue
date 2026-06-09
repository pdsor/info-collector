<template>
  <SropPage>
    <SropPageHeader title="治理中心" description="字段完整率、去重、注入风险与质量评分。">
      <a-button @click="load"><ReloadOutlined /> 刷新</a-button>
    </SropPageHeader>

    <div class="srop-metric-grid">
      <div class="srop-metric-card">
        <span class="srop-metric-label">数据文件</span>
        <strong class="srop-metric-value">{{ fmtNumber(summary.file_count) }}</strong>
      </div>
      <div class="srop-metric-card">
        <span class="srop-metric-label">结构化记录</span>
        <strong class="srop-metric-value">{{ fmtNumber(summary.total_items) }}</strong>
      </div>
      <div class="srop-metric-card">
        <span class="srop-metric-label">注入风险</span>
        <strong class="srop-metric-value">{{ fmtNumber(summary.injection_risk_count) }}</strong>
      </div>
      <div class="srop-metric-card">
        <span class="srop-metric-label">平均质量分</span>
        <strong class="srop-metric-value">{{ fmtPercent(summary.avg_quality_score) }}</strong>
      </div>
    </div>

    <a-card class="srop-table-card" :bordered="false">
      <div class="srop-table-header">
        <span class="srop-table-header-title">
          治理记录
          <span class="srop-table-total">共 {{ records.length }} 条</span>
        </span>
      </div>
      <a-table
        :columns="columns"
        :data-source="records"
        :loading="loading"
        :pagination="{ pageSize: 8, showTotal: (t: number) => `共 ${t} 条` }"
        row-key="row_key"
        size="middle"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <StatusTag :value="record.status" />
          </template>
          <template v-else-if="column.key === 'source_file'">
            <code class="srop-mono">{{ record.source_file }}</code>
          </template>
          <template v-else-if="column.key === 'field_completeness'">
            {{ fmtPercent(record.field_completeness) }}
          </template>
          <template v-else-if="column.key === 'quality_score'">
            {{ fmtPercent(record.quality_score) }}
          </template>
          <template v-else>{{ textValue(record[column.dataIndex as keyof GovernanceRecord]) }}</template>
        </template>
      </a-table>
    </a-card>
  </SropPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { ReloadOutlined } from '@ant-design/icons-vue';
import SropPage from '@/components/SropPage.vue';
import SropPageHeader from '@/components/SropPageHeader.vue';
import StatusTag from '@/components/StatusTag.vue';
import { getGovernanceSummary } from '@/services/governance';
import type { GovernanceRecord, GovernanceSummary } from '@/types/domain';

const loading = ref(false);
const summary = ref<GovernanceSummary>({
  file_count: 0,
  total_items: 0,
  injection_risk_count: 0,
  avg_field_completeness: 0,
  avg_quality_score: 0,
});
const rawRecords = ref<GovernanceRecord[]>([]);

const records = computed(() =>
  rawRecords.value.map((r, i) => ({ ...r, row_key: `${r.platform}-${r.source_file}-${i}` })),
);

const columns = [
  { title: '主题', dataIndex: 'subject', key: 'subject', width: 140 },
  { title: '平台', dataIndex: 'platform', key: 'platform', width: 140 },
  { title: '文件', dataIndex: 'source_file', key: 'source_file' },
  { title: '记录数', dataIndex: 'item_count', key: 'item_count', width: 90 },
  { title: '去重数', dataIndex: 'duplicate_count', key: 'duplicate_count', width: 90 },
  { title: '注入风险', dataIndex: 'injection_risk_count', key: 'injection_risk_count', width: 100 },
  { title: '字段完整率', dataIndex: 'field_completeness', key: 'field_completeness', width: 110 },
  { title: '质量分', dataIndex: 'quality_score', key: 'quality_score', width: 100 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 130 },
];

async function load() {
  loading.value = true;
  try {
    const data = await getGovernanceSummary();
    summary.value = data.summary;
    rawRecords.value = data.records || [];
  } finally {
    loading.value = false;
  }
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
  color: var(--srop-text-muted);
  word-break: break-all;
}
</style>
