<template>
  <SropPage>
    <SropPageHeader title="归档中心" description="页面归档复核 — 原始内容块、图像识别文本与精抽记录。">
      <a-button @click="load"><ReloadOutlined /> 刷新</a-button>
    </SropPageHeader>

    <a-card class="srop-search-card" :bordered="false">
      <a-form layout="inline" class="srop-search-form">
        <a-form-item label="关键字">
          <a-input
            v-model:value="filters.keyword"
            placeholder="标题 / 域名 / 链接"
            allow-clear
            autocomplete="off"
            style="width: 280px"
          />
        </a-form-item>
        <a-form-item label="平台">
          <a-select
            v-model:value="filters.platform"
            allow-clear
            placeholder="全部"
            style="width: 160px"
            :options="platformOptions"
          />
        </a-form-item>
        <a-form-item label="图像识别">
          <a-select
            v-model:value="filters.ocr"
            allow-clear
            placeholder="全部"
            style="width: 140px"
            :options="[
              { value: 'yes', label: '含图像识别' },
              { value: 'no', label: '无图像识别' },
            ]"
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
        <span class="srop-table-header-title">
          归档页面
          <span class="srop-table-total">共 {{ filteredPages.length }} 条</span>
        </span>
      </div>
      <a-table
        :columns="columns"
        :data-source="filteredPages"
        :loading="loading"
        :pagination="{ pageSize: 8, showTotal: (t: number) => `共 ${t} 条` }"
        row-key="content_hash"
        size="middle"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'title'">
            <a-tooltip :title="record.title || record.source_url">
              <a @click="openDetail(record)">
                {{ record.title || record.source_url || '--' }}
              </a>
            </a-tooltip>
          </template>
          <template v-else-if="column.key === 'contains_ocr'">
            <StatusTag :value="record.contains_ocr ? 'YES' : 'NO'" />
          </template>
          <template v-else-if="column.key === 'requires_structuring'">
            <StatusTag :value="record.requires_structuring ? 'YES' : 'NO'" />
          </template>
          <template v-else-if="column.key === 'fetched_at'">
            {{ fmtTime(record.fetched_at) }}
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-button type="primary" ghost size="small" @click="openDetail(record)">查看详情</a-button>
          </template>
          <template v-else>{{ textValue(record[column.dataIndex as keyof ArchivePage]) }}</template>
        </template>
      </a-table>

      <div v-if="!loading && !filteredPages.length" class="srop-empty">
        暂无归档记录。规则配置 <code>archive.enabled: true</code> 后运行采集任务即可生成。
      </div>
    </a-card>

    <a-drawer
      v-model:open="detailOpen"
      :width="drawerWidth"
      :destroy-on-close="true"
      class="srop-archive-drawer"
      placement="right"
    >
      <template #title>
        <div class="srop-archive-drawer-title">
          <span class="srop-archive-drawer-title-text">
            {{ selected?.title || selected?.source_url || '归档详情' }}
          </span>
          <a-space v-if="selected">
            <a-button size="small" @click="copyUrl">
              <template #icon><CopyOutlined /></template>
              复制链接
            </a-button>
            <a-button size="small" type="primary" ghost @click="openInNewTab">
              <template #icon><LinkOutlined /></template>
              打开原页
            </a-button>
          </a-space>
        </div>
      </template>

      <a-spin :spinning="detailLoading">
        <!-- 元信息 -->
        <a-card class="srop-section srop-archive-meta" :bordered="false" size="small">
          <a-descriptions
            :column="{ xxl: 3, xl: 3, lg: 2, md: 2, sm: 1, xs: 1 }"
            size="small"
            bordered
          >
            <a-descriptions-item label="标题" :span="3">
              <span class="srop-archive-meta-title">{{ selected?.title || '--' }}</span>
            </a-descriptions-item>
            <a-descriptions-item label="来源链接" :span="3">
              <a :href="selected?.source_url" target="_blank" rel="noreferrer" class="srop-archive-meta-link">
                {{ selected?.source_url || '--' }}
              </a>
            </a-descriptions-item>
            <a-descriptions-item label="平台">{{ selected?.platform || '--' }}</a-descriptions-item>
            <a-descriptions-item label="主题">{{ selected?.subject || '--' }}</a-descriptions-item>
            <a-descriptions-item label="域名">{{ selected?.domain || '--' }}</a-descriptions-item>
            <a-descriptions-item label="采集时间">{{ fmtTime(selected?.fetched_at) }}</a-descriptions-item>
            <a-descriptions-item label="发布时间">{{ fmtTime(metaPublishTime) || '--' }}</a-descriptions-item>
            <a-descriptions-item label="内容哈希">
              <code class="srop-mono">{{ shortHash(selected?.content_hash) }}</code>
            </a-descriptions-item>
            <a-descriptions-item label="内容块" :span="3">
              <a-space wrap>
                <a-tag>共 {{ detail?.blocks?.length || 0 }} 块</a-tag>
                <a-tag v-if="blockStats.heading" color="blue">标题 {{ blockStats.heading }}</a-tag>
                <a-tag v-if="blockStats.paragraph">段落 {{ blockStats.paragraph }}</a-tag>
                <a-tag v-if="blockStats.image" color="purple">图片 {{ blockStats.image }}</a-tag>
                <a-tag v-if="blockStats.ocr" color="gold">图像识别 {{ blockStats.ocr }}</a-tag>
                <a-tag v-if="blockStats.table" color="cyan">表格 {{ blockStats.table }}</a-tag>
                <a-tag v-if="blockStats.attachment" color="orange">附件 {{ blockStats.attachment }}</a-tag>
                <a-tag :color="selected?.requires_structuring ? 'blue' : 'default'">
                  {{ selected?.requires_structuring ? '需要精抽' : '无需精抽' }}
                </a-tag>
                <a-tag :color="selected?.contains_table ? 'cyan' : 'default'">
                  {{ selected?.contains_table ? '含表格' : '无表格' }}
                </a-tag>
              </a-space>
            </a-descriptions-item>
          </a-descriptions>
        </a-card>

        <!-- 内容块工具栏 -->
        <div class="srop-archive-toolbar">
          <span class="srop-table-header-title">原文内容</span>
          <a-space>
            <CheckableTag
              v-for="opt in blockTypeFilters"
              :key="opt.value"
              :checked="activeBlockTypes.includes(opt.value)"
              @update:checked="(c: boolean) => toggleBlockType(opt.value, c)"
            >
              {{ opt.label }} ({{ blockStats[opt.value] || 0 }})
            </CheckableTag>
            <a-button size="small" @click="resetBlockFilter">显示全部</a-button>
          </a-space>
        </div>

        <!-- 内容块卡片列表 -->
        <div v-if="visibleBlocks.length" class="srop-archive-blocks">
          <div
            v-for="block in visibleBlocks"
            :key="block.row_key"
            class="srop-archive-block"
            :class="`is-${block.block_type}`"
          >
            <div class="srop-archive-block-meta">
              <span class="srop-archive-block-order">#{{ block.block_order }}</span>
              <a-tag :color="blockTagColor(block.block_type)" class="srop-archive-block-tag">
                {{ blockTypeLabel(block.block_type) }}
                <span v-if="block.block_type === 'heading' && block.level"> H{{ block.level }}</span>
              </a-tag>
            </div>

            <div class="srop-archive-block-body">
              <!-- 标题块 -->
              <component
                v-if="block.block_type === 'heading'"
                :is="headingTag(block.level)"
                class="srop-archive-heading"
              >{{ block.text || '(空标题)' }}</component>

              <!-- 段落块 -->
              <p
                v-else-if="block.block_type === 'paragraph'"
                class="srop-archive-paragraph"
              >{{ block.text || '(空段落)' }}</p>

              <!-- 图片块 -->
              <div v-else-if="block.block_type === 'image'" class="srop-archive-image">
                <a-image
                  v-if="block.source_url"
                  :src="block.source_url"
                  :alt="block.text || '图片'"
                  :width="280"
                  :preview="{ src: block.source_url }"
                />
                <p v-if="block.text" class="srop-archive-image-caption">{{ block.text }}</p>
                <a v-if="block.source_url" :href="block.source_url" target="_blank" rel="noreferrer" class="srop-archive-block-link">
                  {{ block.source_url }}
                </a>
              </div>

              <!-- OCR 块 -->
              <div v-else-if="block.block_type === 'ocr'" class="srop-archive-ocr">
                <a-image
                  v-if="block.source_url"
                  :src="block.source_url"
                  :alt="block.text || '原图'"
                  :width="220"
                  :preview="{ src: block.source_url }"
                />
                <div class="srop-archive-ocr-text">
                  <div class="srop-archive-ocr-label">识别文本</div>
                  <pre class="srop-text-block">{{ block.ocr_text || block.text || '(无识别文本)' }}</pre>
                </div>
              </div>

              <!-- 表格块 -->
              <div v-else-if="block.block_type === 'table'" class="srop-archive-table-wrap">
                <pre class="srop-text-block">{{ block.text || '(空表格)' }}</pre>
              </div>

              <!-- 附件块 -->
              <div v-else-if="block.block_type === 'attachment'" class="srop-archive-attachment">
                <PaperClipOutlined />
                <a v-if="block.source_url" :href="block.source_url" target="_blank" rel="noreferrer">
                  {{ block.text || block.source_url }}
                </a>
                <span v-else>{{ block.text || '(空附件)' }}</span>
              </div>

              <!-- 其他/未知类型 -->
              <pre v-else class="srop-text-block">{{ block.text || block.ocr_text || '(空内容)' }}</pre>
            </div>
          </div>
        </div>
        <div v-else class="srop-empty">暂无内容块</div>

        <!-- 精抽记录 -->
        <template v-if="detail?.structured_records?.length">
          <a-divider orientation="left">精抽记录 ({{ detail.structured_records.length }})</a-divider>
          <a-card
            v-for="(sr, idx) in detail.structured_records"
            :key="idx"
            class="srop-archive-record"
            :bordered="true"
            size="small"
          >
            <template #title>
              <a-tag color="blue">{{ sr.record_type }}</a-tag>
            </template>
            <a-descriptions :column="2" size="small" bordered>
              <a-descriptions-item v-for="(value, key) in sr.data" :key="String(key)" :label="String(key)">
                <span class="srop-archive-record-value">{{ formatValue(value) }}</span>
              </a-descriptions-item>
            </a-descriptions>
          </a-card>
        </template>

        <!-- 静态资源 -->
        <template v-if="detail?.assets?.length">
          <a-divider orientation="left">静态资源 ({{ detail.assets.length }})</a-divider>
          <pre class="srop-code-block">{{ JSON.stringify(detail.assets, null, 2) }}</pre>
        </template>
      </a-spin>
    </a-drawer>
  </SropPage>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import {
  ReloadOutlined,
  SearchOutlined,
  CopyOutlined,
  LinkOutlined,
  PaperClipOutlined,
} from '@ant-design/icons-vue';
import { message as antMessage, Tag } from 'ant-design-vue';
import dayjs from 'dayjs';
import SropPage from '@/components/SropPage.vue';
import SropPageHeader from '@/components/SropPageHeader.vue';
import StatusTag from '@/components/StatusTag.vue';
import { getArchives, getArchiveDetail } from '@/services/archives';
import type { ArchivePage, ArchiveDetail, ArchiveBlock } from '@/types/domain';

const CheckableTag = Tag.CheckableTag;

const loading = ref(false);
const pages = ref<ArchivePage[]>([]);

const filters = reactive({
  keyword: '',
  platform: undefined as string | undefined,
  ocr: undefined as 'yes' | 'no' | undefined,
});
const applied = reactive({ ...filters });

const platformOptions = computed(() => {
  const set = new Set(pages.value.map((p) => p.platform).filter(Boolean));
  return Array.from(set).map((p) => ({ value: p, label: p }));
});

const filteredPages = computed(() => {
  const keyword = (applied.keyword || '').trim().toLowerCase();
  return pages.value.filter((page) => {
    if (applied.platform && page.platform !== applied.platform) return false;
    if (applied.ocr === 'yes' && !page.contains_ocr) return false;
    if (applied.ocr === 'no' && page.contains_ocr) return false;
    if (!keyword) return true;
    return [page.title, page.source_url, page.domain, page.subject]
      .some((value) => String(value || '').toLowerCase().includes(keyword));
  });
});

const columns = [
  { title: '标题', dataIndex: 'title', key: 'title' },
  { title: '平台', dataIndex: 'platform', key: 'platform', width: 130 },
  { title: '主题', dataIndex: 'subject', key: 'subject', width: 130 },
  { title: '块数', dataIndex: 'block_count', key: 'block_count', width: 80 },
  { title: '含图像识别', dataIndex: 'contains_ocr', key: 'contains_ocr', width: 110 },
  { title: '需精抽', dataIndex: 'requires_structuring', key: 'requires_structuring', width: 90 },
  { title: '采集时间', dataIndex: 'fetched_at', key: 'fetched_at', width: 170 },
  { title: '操作', key: 'actions', width: 120 },
];

const detailOpen = ref(false);
const detailLoading = ref(false);
const selected = ref<ArchivePage | null>(null);
const detail = ref<ArchiveDetail | null>(null);

// 响应式抽屉宽度：窗口够宽时给到 1080，过窄时按视口比例
const drawerWidth = ref(1080);
function updateDrawerWidth() {
  const w = window.innerWidth;
  drawerWidth.value = Math.min(1180, Math.max(720, Math.floor(w * 0.86)));
}

type BlockWithKey = ArchiveBlock & { row_key: string };

const blockTypeFilters = [
  { value: 'heading', label: '标题' },
  { value: 'paragraph', label: '段落' },
  { value: 'image', label: '图片' },
  { value: 'ocr', label: '图像识别' },
  { value: 'table', label: '表格' },
  { value: 'attachment', label: '附件' },
];

const activeBlockTypes = ref<string[]>([]);

const blockStats = computed(() => {
  const stats: Record<string, number> = {};
  for (const b of detail.value?.blocks || []) {
    const t = b.block_type as string;
    stats[t] = (stats[t] || 0) + 1;
  }
  return stats;
});

const visibleBlocks = computed<BlockWithKey[]>(() => {
  const blocks = (detail.value?.blocks || []) as BlockWithKey[];
  if (!activeBlockTypes.value.length) return blocks;
  return blocks.filter((b) => activeBlockTypes.value.includes(b.block_type as string));
});

const metaPublishTime = computed(() => {
  const meta = detail.value?.meta as Record<string, unknown> | undefined;
  return (meta?.publish_time as string | null | undefined) || undefined;
});

function toggleBlockType(type: string, checked: boolean) {
  if (checked) {
    if (!activeBlockTypes.value.includes(type)) activeBlockTypes.value.push(type);
  } else {
    activeBlockTypes.value = activeBlockTypes.value.filter((t) => t !== type);
  }
}

function resetBlockFilter() {
  activeBlockTypes.value = [];
}

async function load() {
  loading.value = true;
  try {
    const data = await getArchives();
    pages.value = data.pages || [];
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  Object.assign(applied, filters);
}

function onReset() {
  filters.keyword = '';
  filters.platform = undefined;
  filters.ocr = undefined;
  Object.assign(applied, filters);
}

async function openDetail(page: ArchivePage) {
  selected.value = page;
  detail.value = null;
  activeBlockTypes.value = [];
  detailOpen.value = true;
  detailLoading.value = true;
  try {
    const data = await getArchiveDetail(page.content_hash);
    data.blocks = (data.blocks || []).map((b, i) => ({
      ...b,
      row_key: `${page.content_hash}-${b.id ?? i}-${b.block_order}`,
    })) as ArchiveDetail['blocks'];
    detail.value = data;
  } finally {
    detailLoading.value = false;
  }
}

function blockTypeLabel(type: string) {
  return ({
    heading: '标题',
    paragraph: '段落',
    image: '图片',
    ocr: '图像识别',
    table: '表格',
    attachment: '附件',
  } as Record<string, string>)[type] || type;
}

function blockTagColor(type: string) {
  return ({
    heading: 'blue',
    paragraph: 'default',
    image: 'purple',
    ocr: 'gold',
    table: 'cyan',
    attachment: 'orange',
  } as Record<string, string>)[type] || 'default';
}

function headingTag(level: unknown): string {
  const n = Number(level) || 2;
  return `h${Math.min(Math.max(n, 1), 6)}`;
}

function shortHash(hash?: string | null) {
  if (!hash) return '--';
  return hash.length > 20 ? `${hash.slice(0, 10)}…${hash.slice(-6)}` : hash;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '--';
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}

function fmtTime(value?: string | null) {
  if (!value) return '--';
  const d = dayjs(value);
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm:ss') : value;
}

function textValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '--';
  return String(value);
}

async function copyUrl() {
  if (!selected.value?.source_url) return;
  try {
    await navigator.clipboard.writeText(selected.value.source_url);
    antMessage.success('链接已复制');
  } catch {
    antMessage.warning('复制失败，请手动选取链接');
  }
}

function openInNewTab() {
  if (selected.value?.source_url) {
    window.open(selected.value.source_url, '_blank', 'noreferrer');
  }
}

onMounted(() => {
  load();
  updateDrawerWidth();
  window.addEventListener('resize', updateDrawerWidth);
});

onUnmounted(() => {
  window.removeEventListener('resize', updateDrawerWidth);
});
</script>

<style scoped>
.srop-mono {
  font-family: var(--srop-font-mono);
  font-size: 12px;
  color: var(--srop-text-muted);
  word-break: break-all;
}

.srop-archive-drawer-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.srop-archive-drawer-title-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
  font-weight: 600;
}

.srop-archive-drawer :deep(.ant-drawer-body) {
  background: #f7f9fc;
  padding: 16px 20px 28px;
}

.srop-archive-meta {
  margin-bottom: 16px;
}

.srop-archive-meta-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--srop-text);
}

.srop-archive-meta-link {
  word-break: break-all;
}

.srop-archive-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 8px 2px 12px;
  gap: 12px;
}

.srop-archive-blocks {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.srop-archive-block {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 16px;
  background: var(--srop-container-bg);
  border: 1px solid var(--srop-border-light);
  border-radius: 8px;
  padding: 14px 18px;
}

.srop-archive-block.is-heading {
  border-left: 3px solid var(--srop-primary);
}

.srop-archive-block.is-ocr {
  border-left: 3px solid #d97706;
}

.srop-archive-block.is-image {
  border-left: 3px solid #7c3aed;
}

.srop-archive-block.is-attachment {
  border-left: 3px solid #ea580c;
}

.srop-archive-block.is-table {
  border-left: 3px solid #06b6d4;
}

.srop-archive-block-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding-top: 2px;
}

.srop-archive-block-order {
  font-family: var(--srop-font-mono);
  font-size: 12px;
  color: var(--srop-text-dim);
}

.srop-archive-block-tag {
  margin: 0;
}

.srop-archive-block-body {
  min-width: 0;
  word-break: break-word;
}

.srop-archive-heading {
  margin: 0;
  font-weight: 600;
  color: var(--srop-text);
  line-height: 1.45;
}

h1.srop-archive-heading { font-size: 20px; }
h2.srop-archive-heading { font-size: 18px; }
h3.srop-archive-heading { font-size: 16px; }
h4.srop-archive-heading { font-size: 15px; }
h5.srop-archive-heading,
h6.srop-archive-heading { font-size: 14px; }

.srop-archive-paragraph {
  margin: 0;
  font-size: 14px;
  line-height: 1.75;
  color: var(--srop-text-body);
  white-space: pre-wrap;
}

.srop-archive-image,
.srop-archive-ocr {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.srop-archive-image-caption {
  margin: 0;
  font-size: 12px;
  color: var(--srop-text-dim);
}

.srop-archive-ocr {
  flex-direction: row;
  align-items: flex-start;
  gap: 16px;
}

.srop-archive-ocr-text {
  flex: 1;
  min-width: 0;
}

.srop-archive-ocr-label {
  font-size: 12px;
  color: var(--srop-text-dim);
  margin-bottom: 4px;
}

.srop-archive-table-wrap {
  overflow-x: auto;
}

.srop-archive-attachment {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--srop-primary);
}

.srop-archive-block-link {
  font-size: 12px;
  color: var(--srop-text-dim);
  word-break: break-all;
}

.srop-archive-record {
  margin-bottom: 12px;
}

.srop-archive-record-value {
  font-size: 13px;
  word-break: break-word;
  white-space: pre-wrap;
}

@media (max-width: 1024px) {
  .srop-archive-block {
    grid-template-columns: minmax(0, 1fr);
  }

  .srop-archive-ocr {
    flex-direction: column;
  }
}
</style>
