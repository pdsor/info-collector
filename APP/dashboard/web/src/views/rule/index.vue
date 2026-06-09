<template>
  <SropPage>
    <SropPageHeader title="规则中心" description="版本化 YAML DSL，人工发布、沙箱试采与健康检测。">
      <a-button type="primary" @click="openCreateDrawer"><PlusOutlined /> 新建规则</a-button>
      <a-button @click="loadRules"><ReloadOutlined /> 刷新</a-button>
    </SropPageHeader>

    <a-card class="srop-search-card" :bordered="false">
      <a-form layout="inline" class="srop-search-form">
        <a-form-item label="关键字">
          <a-input
            v-model:value="filters.keyword"
            placeholder="规则名 / 路径 / 主题"
            allow-clear
            autocomplete="off"
            style="width: 260px"
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
        <a-form-item label="状态">
          <a-select
            v-model:value="filters.enabled"
            allow-clear
            placeholder="全部"
            style="width: 140px"
            :options="[
              { value: 'true', label: '已启用' },
              { value: 'false', label: '已停用' },
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
        <div>
          <span class="srop-table-header-title">规则清单</span>
          <span class="srop-table-total">共 {{ filteredRules.length }} 条</span>
        </div>
      </div>

      <a-table
        :columns="columns"
        :data-source="filteredRules"
        :loading="loading"
        :pagination="{ pageSize: 8, showTotal: (t: number) => `共 ${t} 条` }"
        row-key="path"
        size="middle"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <div>
              <strong>{{ record.name || record.path }}</strong>
            </div>
            <code class="srop-mono">{{ record.path }}</code>
          </template>
          <template v-else-if="column.key === 'enabled'">
            <StatusTag :value="record.enabled ? 'PRODUCTION' : 'PAUSED'" />
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space size="small">
              <a-button type="primary" ghost size="small" @click="openEditDrawer(record)">编辑</a-button>
              <a-button size="small" :loading="runningPath === record.path" @click="onRunRule(record)">执行</a-button>
              <a-button size="small" @click="onToggleRule(record)">{{ record.enabled ? '停用' : '启用' }}</a-button>
              <a-popconfirm
                :title="`确定删除规则「${record.name || record.path}」？此操作不可恢复。`"
                ok-text="删除"
                cancel-text="取消"
                ok-type="danger"
                @confirm="onDeleteRule(record)"
              >
                <a-button danger size="small">删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
          <template v-else>{{ textValue(record[column.dataIndex as keyof RuleItem]) }}</template>
        </template>
      </a-table>
    </a-card>

    <a-drawer
      v-model:open="drawerOpen"
      :title="editingRule ? `编辑规则：${editingRule.path}` : '新建规则'"
      :width="900"
      :destroy-on-close="true"
      @close="onDrawerClose"
    >
      <a-spin :spinning="drawerLoading">
        <a-form layout="vertical">
          <a-form-item label="规则路径" required>
            <a-input
              v-model:value="form.path"
              placeholder="rules/subject/example.yaml"
              :disabled="!!editingRule"
            />
          </a-form-item>
          <a-form-item label="YAML 内容" required>
            <a-textarea
              v-model:value="form.yaml"
              :rows="22"
              spellcheck="false"
              class="srop-yaml-editor"
            />
          </a-form-item>
        </a-form>

        <a-alert
          v-if="message"
          :type="messageType"
          :message="message"
          show-icon
          closable
          style="margin: 8px 0"
        />

        <div v-if="previewResult" class="srop-section">
          <div class="srop-table-header">
            <span class="srop-table-header-title">
              试采结果
              <a-tag :color="previewResult.success ? 'green' : 'red'">{{ previewResult.success ? 'SUCCESS' : 'FAILED' }}</a-tag>
            </span>
          </div>
          <div v-if="previewResult.success">
            <p>总条数：{{ previewResult.total_collected || 0 }}，展示前 {{ previewResult.preview_count || 0 }} 条</p>
            <p v-if="previewResult.ocr_summary?.enabled">
              OCR 插件：{{ previewResult.ocr_summary.plugin || 'tesseract' }}，
              图片 {{ previewResult.ocr_summary.images_found || 0 }} 张，
              下载 {{ previewResult.ocr_summary.images_downloaded || 0 }} 张，
              识别成功 {{ previewResult.ocr_summary.ocr_success || 0 }} 张，
              人工复核 {{ previewResult.ocr_summary.manual_review_required || 0 }} 条
            </p>
            <pre class="srop-code-block">{{ prettyJson(previewResult.items || []) }}</pre>
          </div>
          <a-alert v-else type="error" show-icon :message="previewResult.error || '试采失败'" />
        </div>

        <div v-if="healthResult" class="srop-section">
          <div class="srop-table-header">
            <span class="srop-table-header-title">
              健康检测
              <a-tag color="blue">{{ Math.round((healthResult.health_score || 0) * 100) }}%</a-tag>
              <a-tag v-if="healthResult.dom_drifted" color="red">DOM 漂移</a-tag>
            </span>
          </div>
          <p>有效选择器：{{ healthResult.working_selectors }} / {{ healthResult.total_selectors }}</p>
          <a-table
            :columns="healthColumns"
            :data-source="healthRows"
            row-key="name"
            :pagination="false"
            size="small"
          />
        </div>
      </a-spin>

      <template #footer>
        <div class="srop-drawer-footer">
          <a-button @click="onFormat">格式化</a-button>
          <a-button :loading="previewing" :disabled="!form.yaml.trim()" @click="onPreview">沙箱试采</a-button>
          <a-button :loading="healthChecking" :disabled="!form.yaml.trim()" @click="onHealthCheck">健康检测</a-button>
          <a-button @click="drawerOpen = false">取消</a-button>
          <a-button type="primary" :loading="saving" :disabled="!form.path || !form.yaml.trim()" @click="onSave">
            保存
          </a-button>
        </div>
      </template>
    </a-drawer>
  </SropPage>
</template>

<script setup lang="ts">
import { computed, reactive, ref, onMounted } from 'vue';
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue';
import { message as antMessage } from 'ant-design-vue';
import yaml from 'js-yaml';
import SropPage from '@/components/SropPage.vue';
import SropPageHeader from '@/components/SropPageHeader.vue';
import StatusTag from '@/components/StatusTag.vue';
import {
  getRulesList,
  getRuleDetail,
  saveRule,
  previewRule,
  deleteRule,
  toggleRule,
  runRule,
} from '@/services/rules';
import { checkRuleHealth } from '@/services/health';
import type { RuleItem, RulePreviewResult, HealthCheckReport } from '@/types/domain';
import { formatYamlText, getNewRuleYaml } from './yamlUtils';

const loading = ref(false);
const rules = ref<RuleItem[]>([]);

const filters = reactive({
  keyword: '',
  platform: undefined as string | undefined,
  enabled: undefined as string | undefined,
});
const applied = reactive({ ...filters });

const platformOptions = computed(() => {
  const set = new Set(rules.value.map((r) => r.platform).filter(Boolean));
  return Array.from(set).map((p) => ({ value: p as string, label: String(p) }));
});

const filteredRules = computed(() => {
  const keyword = (applied.keyword || '').trim().toLowerCase();
  return rules.value.filter((rule) => {
    if (applied.platform && rule.platform !== applied.platform) return false;
    if (applied.enabled !== undefined && applied.enabled !== '' && rule.enabled !== (applied.enabled === 'true')) {
      return false;
    }
    if (!keyword) return true;
    return [rule.name, rule.path, rule.subject, rule.platform]
      .some((value) => String(value || '').toLowerCase().includes(keyword));
  });
});

const columns = [
  { title: '规则', dataIndex: 'name', key: 'name', width: 320 },
  { title: '主题', dataIndex: 'subject', key: 'subject', width: 160 },
  { title: '平台', dataIndex: 'platform', key: 'platform', width: 140 },
  { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 110 },
  { title: '操作', key: 'actions', width: 280 },
];

const healthColumns = [
  { title: '选择器', dataIndex: 'name', key: 'name', width: 200 },
  { title: '路径', dataIndex: 'selector', key: 'selector' },
  { title: '命中', dataIndex: 'hits', key: 'hits', width: 80 },
  { title: '样本', dataIndex: 'sample', key: 'sample' },
];

const drawerOpen = ref(false);
const drawerLoading = ref(false);
const editingRule = ref<RuleItem | null>(null);
const form = reactive({ path: '', yaml: '' });

const message = ref('');
const messageType = ref<'success' | 'info' | 'warning' | 'error'>('info');
const saving = ref(false);
const previewing = ref(false);
const previewResult = ref<RulePreviewResult | null>(null);
const healthChecking = ref(false);
const healthResult = ref<HealthCheckReport | null>(null);
const runningPath = ref<string | null>(null);

const healthRows = computed(() => {
  if (!healthResult.value?.selectors) return [];
  return Object.entries(healthResult.value.selectors).map(([name, info]) => ({
    name,
    selector: info.error ? `错误：${info.error}` : '-',
    hits: info.hits,
    sample: (info.sample || []).join(' / '),
  }));
});

async function loadRules() {
  loading.value = true;
  try {
    const data = await getRulesList();
    rules.value = data.rules || [];
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
  filters.enabled = undefined;
  Object.assign(applied, filters);
}

function openCreateDrawer() {
  editingRule.value = null;
  form.path = 'rules/new_rule.yaml';
  form.yaml = getNewRuleYaml();
  message.value = '';
  previewResult.value = null;
  healthResult.value = null;
  drawerOpen.value = true;
}

async function openEditDrawer(rule: RuleItem) {
  editingRule.value = rule;
  form.path = rule.path;
  form.yaml = '';
  message.value = '';
  previewResult.value = null;
  healthResult.value = null;
  drawerOpen.value = true;
  drawerLoading.value = true;
  try {
    const detail = await getRuleDetail(rule.path);
    form.yaml = detail.yaml || '';
  } catch (err) {
    setMessage(`加载规则失败：${(err as Error).message}`, 'error');
  } finally {
    drawerLoading.value = false;
  }
}

function onDrawerClose() {
  editingRule.value = null;
  form.path = '';
  form.yaml = '';
  message.value = '';
  previewResult.value = null;
  healthResult.value = null;
}

function onFormat() {
  try {
    form.yaml = formatYamlText(form.yaml);
    setMessage('YAML 已格式化', 'success');
  } catch (err) {
    setMessage(`格式化失败：${(err as Error).message}`, 'error');
  }
}

async function onPreview() {
  previewing.value = true;
  previewResult.value = null;
  try {
    const data = await previewRule(form.yaml, 5);
    previewResult.value = data;
    setMessage(data.success ? '试采完成' : `试采失败：${data.error || '未知错误'}`, data.success ? 'success' : 'warning');
  } catch (err) {
    previewResult.value = { success: false, error: (err as Error).message };
    setMessage(`试采失败：${(err as Error).message}`, 'error');
  } finally {
    previewing.value = false;
  }
}

async function onHealthCheck() {
  healthChecking.value = true;
  healthResult.value = null;
  try {
    const ruleObj = yaml.load(form.yaml) as Record<string, unknown>;
    if (!ruleObj || typeof ruleObj !== 'object') {
      throw new Error('YAML 内容无效');
    }
    const report = await checkRuleHealth({
      rule: ruleObj,
      rule_path: editingRule.value?.path,
    });
    healthResult.value = report;
    const score = Math.round((report.health_score || 0) * 100);
    setMessage(`健康度 ${score}% (${report.working_selectors}/${report.total_selectors} 选择器有效)`,
      score >= 80 ? 'success' : score >= 50 ? 'warning' : 'error');
  } catch (err) {
    setMessage(`健康检测失败：${(err as Error).message}`, 'error');
  } finally {
    healthChecking.value = false;
  }
}

async function onSave() {
  saving.value = true;
  try {
    await saveRule(form.path, form.yaml);
    setMessage('规则已保存', 'success');
    antMessage.success('规则已保存');
    await loadRules();
    drawerOpen.value = false;
  } catch (err) {
    setMessage(`保存失败：${(err as Error).message}`, 'error');
  } finally {
    saving.value = false;
  }
}

async function onToggleRule(rule: RuleItem) {
  try {
    const next = !rule.enabled;
    const data = await toggleRule(rule.path, next);
    rule.enabled = data.enabled ?? next;
    antMessage.success(`已${next ? '启用' : '停用'}：${rule.name || rule.path}`);
  } catch (err) {
    antMessage.error(`切换失败：${(err as Error).message}`);
  }
}

async function onDeleteRule(rule: RuleItem) {
  try {
    await deleteRule(rule.path);
    antMessage.success(`已删除：${rule.name || rule.path}`);
    await loadRules();
  } catch (err) {
    antMessage.error(`删除失败：${(err as Error).message}`);
  }
}

async function onRunRule(rule: RuleItem) {
  runningPath.value = rule.path;
  try {
    const data = await runRule(rule.path);
    antMessage.success(`任务已创建：#${data.task_id}，请到任务中心查看进度`);
  } catch (err) {
    antMessage.error(`执行失败：${(err as Error).message}`);
  } finally {
    runningPath.value = null;
  }
}

function setMessage(text: string, type: 'success' | 'info' | 'warning' | 'error') {
  message.value = text;
  messageType.value = type;
}

function prettyJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function textValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '--';
  return String(value);
}

onMounted(loadRules);
</script>

<style scoped>
.srop-mono {
  font-family: var(--srop-font-mono);
  font-size: 12px;
  color: #4b5563;
  word-break: break-all;
}

.srop-yaml-editor {
  font-family: var(--srop-font-mono);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre;
}
</style>
