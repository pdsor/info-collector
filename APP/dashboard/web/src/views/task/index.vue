<template>
  <SropPage>
    <SropPageHeader title="任务中心" description="任务状态机、实时事件流与执行历史。">
      <a-button v-if="!running" type="primary" :loading="starting" @click="onRunAll">
        <ThunderboltOutlined /> 执行全部
      </a-button>
      <a-button v-else danger @click="onStop">停止监听</a-button>
      <a-button @click="loadHistory"><ReloadOutlined /> 刷新</a-button>
    </SropPageHeader>

    <a-card class="srop-table-card" :bordered="false">
      <div class="srop-table-header">
        <span class="srop-table-header-title">
          实时事件
          <a-tag :color="running ? 'blue' : 'default'" style="margin-left: 8px">{{ running ? '执行中' : '空闲' }}</a-tag>
          <span class="srop-table-total" v-if="currentTaskId">任务 #{{ currentTaskId }}</span>
        </span>
        <a-button v-if="logs.length" size="small" @click="logs = []">清空</a-button>
      </div>
      <div class="srop-log-stream">
        <div
          v-for="(line, index) in logs"
          :key="index"
          class="srop-log-line"
          :class="line.type"
        >{{ line.text }}</div>
        <div v-if="!logs.length" class="srop-empty">暂无实时事件</div>
      </div>
    </a-card>

    <a-card class="srop-table-card" :bordered="false">
      <div class="srop-table-header">
        <span class="srop-table-header-title">
          任务历史 <span class="srop-table-total">最近 50 条</span>
        </span>
      </div>
      <a-table
        :columns="columns"
        :data-source="tasks"
        :loading="loading"
        :pagination="{ pageSize: 8, showTotal: (t: number) => `共 ${t} 条` }"
        row-key="id"
        size="middle"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'task_name'">
            <div><strong>{{ record.task_name }}</strong></div>
            <code class="srop-mono">{{ record.rule_path || '全部规则' }}</code>
          </template>
          <template v-else-if="column.key === 'ng_status'">
            <StatusTag :value="record.ng_status || record.status" />
          </template>
          <template v-else-if="column.key === 'duration'">
            {{ record.duration ? `${record.duration.toFixed(2)}s` : '--' }}
          </template>
          <template v-else-if="column.key === 'created_at'">
            {{ fmtTime(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-button size="small" type="link" @click="openTaskDetail(record)">详情</a-button>
          </template>
          <template v-else>{{ textValue(record[column.dataIndex as keyof TaskHistoryItem]) }}</template>
        </template>
      </a-table>
    </a-card>

    <a-drawer
      v-model:open="detailOpen"
      class="task-detail-drawer"
      width="86vw"
      :title="detailTask ? `任务 #${detailTask.id} 全过程明细` : '任务全过程明细'"
      :destroy-on-close="false"
    >
      <a-spin :spinning="detailLoading">
        <template v-if="detailTask">
          <a-descriptions size="small" bordered :column="3" class="task-detail-section">
            <a-descriptions-item label="任务">{{ detailTask.task_name }}</a-descriptions-item>
            <a-descriptions-item label="状态">
              <StatusTag :value="detailTask.ng_status || detailTask.status" />
            </a-descriptions-item>
            <a-descriptions-item label="触发">{{ detailTask.trigger_type || '--' }}</a-descriptions-item>
            <a-descriptions-item label="新增">{{ detailTask.new_count ?? 0 }}</a-descriptions-item>
            <a-descriptions-item label="耗时">{{ formatDuration(detailTask.duration) }}</a-descriptions-item>
            <a-descriptions-item label="创建时间">{{ fmtTime(detailTask.created_at) }}</a-descriptions-item>
            <a-descriptions-item label="规则" :span="3">
              <code class="srop-mono">{{ detailTask.rule_path || '全部规则' }}</code>
            </a-descriptions-item>
            <a-descriptions-item v-if="detailTask.message" label="消息" :span="3">
              {{ detailTask.message }}
            </a-descriptions-item>
          </a-descriptions>

          <a-alert
            v-if="!detailRun"
            class="task-detail-section"
            type="warning"
            show-icon
            message="没有找到本任务对应的 PostgreSQL 采集运行记录"
            description="旧任务或迁移前任务不会有 raw/deduped/filtered 明细；新任务跑完后会写入全过程记录。"
          />

          <a-descriptions v-else size="small" bordered :column="3" class="task-detail-section">
            <a-descriptions-item label="采集运行">{{ detailRun.id }}</a-descriptions-item>
            <a-descriptions-item label="规则名称">{{ detailRun.rule_name }}</a-descriptions-item>
            <a-descriptions-item label="平台">{{ detailRun.platform || '--' }}</a-descriptions-item>
            <a-descriptions-item label="本次抓取">
              <a-tag color="blue">{{ detailRun.total_collected ?? 0 }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="新增入库">
              <a-tag color="green">{{ detailRun.saved_count ?? 0 }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="去重过滤">
              <a-tag color="orange">{{ detailRun.dedup_filtered ?? 0 }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="开始时间">{{ fmtTime(detailRun.started_at) }}</a-descriptions-item>
            <a-descriptions-item label="结束时间">{{ fmtTime(detailRun.finished_at) }}</a-descriptions-item>
            <a-descriptions-item label="引擎耗时">{{ formatDuration(detailRun.duration_seconds) }}</a-descriptions-item>
            <a-descriptions-item label="输出路径" :span="3">
              <code class="srop-mono">{{ detailRun.output_path || '--' }}</code>
            </a-descriptions-item>
          </a-descriptions>

          <a-tabs v-model:active-key="activeDetailTab" size="small">
            <a-tab-pane key="logs" :tab="`执行日志 ${detailLogs.length}`">
              <div class="srop-log-stream detail-log-stream">
                <div
                  v-for="(event, index) in detailLogs"
                  :key="index"
                  class="srop-log-line"
                  :class="eventLogType(event)"
                >{{ formatEvent(event) }}</div>
                <div v-if="!detailLogs.length" class="srop-empty">暂无日志事件</div>
              </div>
            </a-tab-pane>
            <a-tab-pane key="raw" :tab="`本次抓取 raw ${detailItems.raw.length}`">
              <TaskItemTable :items="detailItems.raw" stage="raw" />
            </a-tab-pane>
            <a-tab-pane key="deduped" :tab="`新增 deduped ${detailItems.deduped.length}`">
              <TaskItemTable :items="detailItems.deduped" stage="deduped" />
            </a-tab-pane>
            <a-tab-pane key="filtered" :tab="`过滤 filtered ${detailItems.filtered.length}`">
              <TaskItemTable :items="detailItems.filtered" stage="filtered" />
            </a-tab-pane>
          </a-tabs>
        </template>
      </a-spin>
    </a-drawer>
  </SropPage>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, onUnmounted, ref, type Component } from 'vue';
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons-vue';
import { Table, Tag, TypographyParagraph, message as antMessage } from 'ant-design-vue';
import dayjs from 'dayjs';
import MarkdownIt from 'markdown-it';
import SropPage from '@/components/SropPage.vue';
import SropPageHeader from '@/components/SropPageHeader.vue';
import StatusTag from '@/components/StatusTag.vue';
import { getTaskDetail, getTaskHistory, getTaskItems, getTaskLogs, runAllTasks, streamTask } from '@/services/tasks';
import type { CollectionRun, CollectionRunItem, TaskHistoryItem, TaskStreamEvent } from '@/types/domain';
import type { SseSubscriber } from '@/services/apiClient';

const loading = ref(false);
const tasks = ref<TaskHistoryItem[]>([]);
const running = ref(false);
const starting = ref(false);
const currentTaskId = ref<number | null>(null);
const logs = ref<{ type: string; text: string }[]>([]);
const detailOpen = ref(false);
const detailLoading = ref(false);
const detailTask = ref<TaskHistoryItem | null>(null);
const detailRun = ref<CollectionRun | null>(null);
const detailLogs = ref<TaskStreamEvent[]>([]);
const activeDetailTab = ref('logs');
const detailItems = ref<Record<'raw' | 'deduped' | 'filtered', CollectionRunItem[]>>({
  raw: [],
  deduped: [],
  filtered: [],
});
let subscriber: SseSubscriber | null = null;

const columns = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
  { title: '任务', dataIndex: 'task_name', key: 'task_name' },
  { title: '状态', dataIndex: 'ng_status', key: 'ng_status', width: 120 },
  { title: '触发', dataIndex: 'trigger_type', key: 'trigger_type', width: 90 },
  { title: '新增', dataIndex: 'new_count', key: 'new_count', width: 80 },
  { title: '耗时', dataIndex: 'duration', key: 'duration', width: 100 },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
  { title: '操作', key: 'action', width: 90, fixed: 'right' },
];

const itemColumns = [
  { title: '标题', dataIndex: 'title', key: 'title', width: 280 },
  { title: '发布时间', key: 'publish_time', width: 150 },
  { title: 'raw_id', dataIndex: 'raw_id', key: 'raw_id', width: 150 },
  { title: 'URL', dataIndex: 'url', key: 'url', width: 220 },
  { title: '去重状态', key: 'dedup', width: 240 },
  { title: '内容哈希', dataIndex: 'content_hash', key: 'content_hash', width: 150 },
];

const AntTable = Table as unknown as Component;
const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: false,
});

function renderMarkdown(value?: string) {
  return markdown.render(value || '');
}

const TaskItemTable = defineComponent({
  name: 'TaskItemTable',
  props: {
    items: {
      type: Array as () => CollectionRunItem[],
      required: true,
    },
    stage: {
      type: String,
      required: true,
    },
  },
  setup(props) {
    const pagination = computed(() => ({ pageSize: 10, showTotal: (total: number) => `共 ${total} 条` }));
    return () => h(
      AntTable,
      {
        columns: itemColumns,
        dataSource: props.items,
        rowKey: (_record: CollectionRunItem, index: number) => `${props.stage}-${_record.raw_id || _record.url || index}`,
        pagination: pagination.value,
        size: 'small',
        scroll: { x: 1300 },
      },
      {
        bodyCell: ({ column, record }: { column: { key: string; dataIndex?: string }; record: CollectionRunItem }) => {
          if (column.key === 'title') {
            return h('div', { class: 'task-item-title' }, [
              h('div', record.title || '--'),
              record.data?.source
                ? h('span', { class: 'srop-table-total' }, String(record.data.source))
                : null,
            ]);
          }
          if (column.key === 'publish_time') {
            return fmtTime(String(record.data?.publish_time || record.data?.date || record.collected_at || ''));
          }
          if (column.key === 'url') {
            return record.url
              ? h('a', { href: record.url, target: '_blank', rel: 'noreferrer' }, '打开')
              : '--';
          }
          if (column.key === 'dedup') {
            if (props.stage === 'filtered') {
              return h('div', { class: 'task-dedup-cell' }, [
                h(Tag, { color: 'orange' }, () => record.filter_reason || '已过滤'),
                h('div', { class: 'task-old-item' }, `匹配：${record.matched_existing_id || record.matched_existing_item?.id || '--'}`),
                record.matched_existing_item?.title
                  ? h('div', { class: 'task-old-item' }, `旧数据：${record.matched_existing_item.title}`)
                  : null,
              ]);
            }
            return h(Tag, { color: props.stage === 'deduped' ? 'green' : 'blue' }, () => props.stage === 'deduped' ? '新增入库' : '原始抓取');
          }
          if (column.key === 'content_hash') {
            return h('code', { class: 'srop-mono' }, shortHash(record.content_hash));
          }
          const value = record[column.dataIndex as keyof CollectionRunItem];
          return textValue(value);
        },
        expandedRowRender: ({ record }: { record: CollectionRunItem }) => h('div', { class: 'task-expanded-content' }, [
          h('div', { class: 'task-article-panel' }, [
            h('div', { class: 'task-json-title' }, '文章正文'),
            record.archive?.body_text
              ? h(TypographyParagraph, { copyable: true, class: 'task-article-text' }, () => record.archive?.body_text || '')
              : h('div', { class: 'srop-empty' }, '暂无归档正文'),
          ]),
          record.archive?.ocr_text
            ? h('div', { class: 'task-article-panel' }, [
              h('div', { class: 'task-json-title' }, 'OCR Markdown'),
              h('div', {
                class: 'task-markdown-rendered',
                innerHTML: renderMarkdown(record.archive?.ocr_text || ''),
              }),
            ])
            : null,
          h('div', { class: 'task-json-grid' }, [
            h('div', [
              h('div', { class: 'task-json-title' }, 'data'),
              h(TypographyParagraph, { copyable: true, class: 'task-json-block' }, () => jsonText(record.data)),
            ]),
            h('div', [
              h('div', { class: 'task-json-title' }, 'governance'),
              h(TypographyParagraph, { copyable: true, class: 'task-json-block' }, () => jsonText(record.governance)),
            ]),
          ]),
        ]),
      },
    );
  },
});

async function loadHistory() {
  loading.value = true;
  try {
    const data = await getTaskHistory();
    tasks.value = data.tasks || [];
  } finally {
    loading.value = false;
  }
}

async function openTaskDetail(record: TaskHistoryItem) {
  detailOpen.value = true;
  detailLoading.value = true;
  detailTask.value = record;
  detailRun.value = record.collection_run || null;
  detailLogs.value = [];
  detailItems.value = { raw: [], deduped: [], filtered: [] };
  activeDetailTab.value = 'logs';
  try {
    const [task, items, taskLogs] = await Promise.all([
      getTaskDetail(record.id),
      getTaskItems(record.id),
      getTaskLogs(record.id),
    ]);
    detailTask.value = task;
    detailRun.value = items.run || task.collection_run || null;
    detailItems.value = items.items || { raw: [], deduped: [], filtered: [] };
    detailLogs.value = taskLogs;
  } catch (err) {
    antMessage.error(`加载任务详情失败：${(err as Error).message}`);
  } finally {
    detailLoading.value = false;
  }
}

async function onRunAll() {
  starting.value = true;
  logs.value = [];
  try {
    const data = await runAllTasks();
    currentTaskId.value = data.task_id;
    logs.value.push({ type: 'status', text: `任务 #${data.task_id} 已创建` });
    running.value = true;
    openStream(data.task_id);
  } catch (err) {
    antMessage.error(`创建任务失败：${(err as Error).message}`);
  } finally {
    starting.value = false;
  }
}

function openStream(taskId: number) {
  subscriber = streamTask(taskId, {
    onData: handleEvent,
    onError: () => {
      logs.value.push({ type: 'error', text: '事件流断开' });
      running.value = false;
    },
  });
}

function handleEvent(event: TaskStreamEvent) {
  const rule = event.rule ? `[${event.rule}] ` : '';
  if (event.type === 'status') {
    logs.value.push({ type: 'status', text: `${rule}${event.msg || event.status || ''}` });
  } else if (event.type === 'progress') {
    logs.value.push({ type: 'status', text: `${rule}${event.phase || ''} ${event.current ?? '-'} / ${event.total ?? '-'}` });
  } else if (event.type === 'error') {
    logs.value.push({ type: 'error', text: `${rule}${event.message || ''}` });
  } else if (event.type === 'skip') {
    logs.value.push({ type: 'skip', text: `${rule}跳过：${event.reason || ''}` });
  } else if (event.type === 'complete') {
    logs.value.push({ type: 'done', text: `${rule}完成，新增 ${event.new_count || 0}` });
  } else if (event.type === 'done') {
    logs.value.push({
      type: event.success ? 'done' : 'error',
      text: `完成：新增 ${event.total_new || 0}，跳过 ${event.total_skip || 0}，错误 ${event.total_error || 0}`,
    });
    running.value = false;
    subscriber?.close();
    subscriber = null;
    loadHistory();
  }
}

function onStop() {
  subscriber?.close();
  subscriber = null;
  running.value = false;
  logs.value.push({ type: 'status', text: '已停止监听事件流（任务仍在后台运行）' });
}

function fmtTime(value?: string) {
  if (!value) return '--';
  const parsed = dayjs(value);
  if (!parsed.isValid()) return '--';
  return parsed.format('YYYY-MM-DD HH:mm:ss');
}

function formatDuration(value?: number) {
  if (!value && value !== 0) return '--';
  return `${Number(value).toFixed(2)}s`;
}

function textValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '--';
  return String(value);
}

function shortHash(value?: string) {
  if (!value) return '--';
  return value.length > 12 ? `${value.slice(0, 12)}...` : value;
}

function jsonText(value?: Record<string, unknown>) {
  return JSON.stringify(value || {}, null, 2);
}

function eventLogType(event: TaskStreamEvent) {
  if (event.type === 'error') return 'error';
  if (event.type === 'skip') return 'skip';
  if (event.type === 'complete' || event.type === 'summary' || event.type === 'done') return 'done';
  return 'status';
}

function formatEvent(event: TaskStreamEvent) {
  const rule = event.rule ? `[${event.rule}] ` : '';
  if (event.type === 'status') return `${rule}${event.msg || event.status || ''}`;
  if (event.type === 'progress') return `${rule}${event.phase || ''} ${event.current ?? '-'} / ${event.total ?? '-'}`;
  if (event.type === 'error') return `${rule}${event.message || ''}`;
  if (event.type === 'skip') return `${rule}跳过：${event.reason || ''}`;
  if (event.type === 'complete') return `${rule}规则完成，新增 ${event.new_count || 0}，耗时 ${formatDuration(event.duration)}`;
  if (event.type === 'summary') return `汇总完成，耗时 ${formatDuration(event.duration)}`;
  if (event.type === 'done') return `完成：新增 ${event.total_new || 0}，跳过 ${event.total_skip || 0}，错误 ${event.total_error || 0}`;
  return JSON.stringify(event);
}

onMounted(loadHistory);
onUnmounted(() => subscriber?.close());
</script>

<style scoped>
.srop-mono {
  font-family: var(--srop-font-mono);
  font-size: 12px;
  color: var(--srop-text-dim);
}

.task-detail-section {
  margin-bottom: 16px;
}

.detail-log-stream {
  max-height: 360px;
}

.task-item-title {
  min-width: 0;
}

.task-dedup-cell {
  display: grid;
  gap: 4px;
}

.task-old-item {
  color: var(--srop-text-dim);
  font-size: 12px;
  line-height: 1.4;
}

.task-json-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.task-expanded-content {
  display: grid;
  gap: 12px;
}

.task-article-panel {
  min-width: 0;
}

.task-article-text {
  max-height: 360px;
  margin-bottom: 0;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
}

.task-json-title {
  margin-bottom: 6px;
  color: var(--srop-text-dim);
  font-size: 12px;
}

.task-json-block {
  max-height: 260px;
  margin-bottom: 0;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.task-markdown-rendered {
  max-height: 420px;
  overflow: auto;
  color: var(--srop-text);
  font-size: 13px;
  line-height: 1.6;
}

.task-markdown-rendered :deep(table) {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.task-markdown-rendered :deep(th),
.task-markdown-rendered :deep(td) {
  max-width: 360px;
  padding: 6px 8px;
  border: 1px solid var(--srop-border);
  vertical-align: top;
  white-space: normal;
  word-break: break-word;
}

.task-markdown-rendered :deep(th) {
  background: var(--srop-bg-soft);
  color: var(--srop-text-strong);
  font-weight: 600;
}

.task-markdown-rendered :deep(p) {
  margin: 0 0 8px;
  white-space: pre-wrap;
}

@media (max-width: 900px) {
  .task-json-grid {
    grid-template-columns: 1fr;
  }
}
</style>
