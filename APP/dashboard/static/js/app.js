const { createApp, ref, computed, onMounted, onUnmounted } = Vue;

const fmtNumber = (value) => new Intl.NumberFormat('zh-CN').format(value || 0);
const fmtPercent = (value) => `${Math.round((value || 0) * 100)}%`;
const fmtTime = (value) => value ? new Date(value).toLocaleString('zh-CN') : '-';

const StatusBadge = {
    props: ['value'],
    computed: {
        normalized() {
            return String(this.value || '').toUpperCase();
        }
    },
    template: `<span :class="['status-badge', normalized.toLowerCase()]">{{ normalized || '-' }}</span>`
};

function getNewRuleYaml() {
    return [
        'rule_id: "3fa85f64-5717-4562-b3fc-2c963f66afa6"',
        'source_id: "example-source"',
        'version: 1',
        'status: DRAFT',
        'source:',
        '  platform: "example"',
        '  type: "html"',
        '  url: "https://example.com"',
        'list:',
        '  items_path: "css:article"',
        'extract:',
        '  title:',
        '    selector: "h1"',
        '    type: "text"',
        'output:',
        '  fields:',
        '    - "title"',
        '  save_raw: false',
        'governance:',
        '  sanitize: true',
        '',
    ].join('\n');
}

function splitInlineYamlValues(value) {
    const values = [];
    let current = '';
    let quote = null;
    let nested = 0;
    for (const char of value) {
        if ((char === '"' || char === "'") && !quote) {
            quote = char;
        } else if (char === quote) {
            quote = null;
        } else if (!quote && (char === '[' || char === '{')) {
            nested += 1;
        } else if (!quote && (char === ']' || char === '}')) {
            nested -= 1;
        }

        if (char === ',' && !quote && nested === 0) {
            values.push(current.trim());
            current = '';
        } else {
            current += char;
        }
    }
    if (current.trim()) values.push(current.trim());
    return values;
}

function formatYamlText(source) {
    const text = String(source || '').replace(/\r\n/g, '\n').trim();
    if (!text) return '';

    const lines = [];
    for (const rawLine of text.split('\n')) {
        const line = rawLine.replace(/\s+$/g, '');
        const objectMatch = line.match(/^(\s*)([^:#][^:]*):\s*\{\s*(.+)\s*\}\s*$/);
        const arrayMatch = line.match(/^(\s*)([^:#][^:]*):\s*\[\s*(.*)\s*\]\s*$/);

        if (objectMatch) {
            const [, indent, key, body] = objectMatch;
            lines.push(`${indent}${key.trim()}:`);
            for (const part of splitInlineYamlValues(body)) {
                const pair = part.match(/^([^:]+):\s*(.+)$/);
                if (!pair) throw new Error(`无法格式化字段：${part}`);
                lines.push(`${indent}  ${pair[1].trim()}: ${pair[2].trim()}`);
            }
            continue;
        }

        if (arrayMatch) {
            const [, indent, key, body] = arrayMatch;
            lines.push(`${indent}${key.trim()}:`);
            for (const item of splitInlineYamlValues(body)) {
                if (item) lines.push(`${indent}  - ${item}`);
            }
            continue;
        }

        lines.push(line);
    }

    return `${lines.join('\n')}\n`;
}

const SourceCenter = {
    setup() {
        const loading = ref(true);
        const sources = ref([]);
        const summary = ref({ total: 0, active: 0, paused: 0, avg_trust_score: 0 });
        const filter = ref('');

        const load = async () => {
            loading.value = true;
            try {
                const [sourceData, summaryData] = await Promise.all([
                    API.get('/sources'),
                    API.get('/sources/summary'),
                ]);
                sources.value = sourceData.sources || [];
                summary.value = summaryData;
            } finally {
                loading.value = false;
            }
        };

        const filteredSources = computed(() => {
            const keyword = filter.value.trim().toLowerCase();
            if (!keyword) return sources.value;
            return sources.value.filter(source => [
                source.name, source.domain, source.category, source.parser_strategy, source.lifecycle_status
            ].some(value => String(value || '').toLowerCase().includes(keyword)));
        });

        onMounted(load);
        return { loading, sources, summary, filter, filteredSources, load, fmtNumber, fmtPercent };
    },
    template: `
<section class="console-view">
  <header class="view-header">
    <div>
      <h1>Source Center</h1>
      <p>来源注册、状态、信任分与解析策略</p>
    </div>
    <button @click="load">刷新</button>
  </header>

  <div class="metric-grid">
    <div class="metric"><span>来源总数</span><strong>{{ fmtNumber(summary.total) }}</strong></div>
    <div class="metric"><span>ACTIVE</span><strong>{{ fmtNumber(summary.active) }}</strong></div>
    <div class="metric"><span>PAUSED</span><strong>{{ fmtNumber(summary.paused) }}</strong></div>
    <div class="metric"><span>平均信任分</span><strong>{{ fmtPercent(summary.avg_trust_score) }}</strong></div>
  </div>

  <div class="panel">
    <div class="panel-bar">
      <h2>来源列表</h2>
      <input v-model="filter" placeholder="筛选来源、域名、分类" />
    </div>
    <div v-if="loading" class="empty">加载中...</div>
    <table v-else class="data-table dense">
      <thead>
        <tr><th>来源</th><th>域名</th><th>类型</th><th>分类</th><th>信任分</th><th>反爬</th><th>状态</th><th>规则</th></tr>
      </thead>
      <tbody>
        <tr v-for="source in filteredSources" :key="source.id">
          <td><strong>{{ source.name }}</strong></td>
          <td>{{ source.domain || '-' }}</td>
          <td>{{ source.type }}</td>
          <td>{{ source.category || '-' }}</td>
          <td><div class="score"><span :style="{width: (source.trust_score * 100) + '%'}"></span></div>{{ fmtPercent(source.trust_score) }}</td>
          <td>{{ source.anti_crawl_level }}</td>
          <td><StatusBadge :value="source.lifecycle_status" /></td>
          <td><code>{{ source.rule_path }}</code></td>
        </tr>
      </tbody>
    </table>
  </div>
</section>`
};

const RuleCenter = {
    setup() {
        const rules = ref([]);
        const selected = ref(null);
        const yaml = ref('');
        const message = ref('');
        const loading = ref(false);
        const previewing = ref(false);
        const previewResult = ref(null);

        const loadRules = async () => {
            const data = await API.get('/rules');
            rules.value = data.rules || [];
        };

        const editRule = async (rule) => {
            selected.value = rule;
            message.value = '';
            const data = await API.get(`/rules/${encodeURIComponent(rule.path)}`);
            yaml.value = data.yaml || '';
        };

        const newRule = () => {
            selected.value = { path: 'rules/new_rule.yaml', name: '新规则' };
            yaml.value = getNewRuleYaml();
            message.value = '';
            previewResult.value = null;
        };

        const formatRuleYaml = () => {
            message.value = '';
            try {
                yaml.value = formatYamlText(yaml.value);
                message.value = 'YAML 已格式化';
            } catch (err) {
                message.value = `格式化失败：${err.message}`;
            }
        };

        const saveRule = async () => {
            if (!selected.value?.path) return;
            loading.value = true;
            message.value = '';
            try {
                await API.post('/rules', { path: selected.value.path, yaml: yaml.value });
                message.value = '规则已保存';
                await loadRules();
            } catch (err) {
                message.value = `保存失败：${err.message}`;
            } finally {
                loading.value = false;
            }
        };

        const previewRule = async () => {
            previewing.value = true;
            message.value = '';
            previewResult.value = null;
            try {
                const data = await API.post('/rules/preview', { yaml: yaml.value, limit: 5 });
                previewResult.value = data;
                message.value = data.success ? '试采完成' : `试采失败：${data.error || '未知错误'}`;
            } catch (err) {
                previewResult.value = { success: false, error: err.message };
                message.value = `试采失败：${err.message}`;
            } finally {
                previewing.value = false;
            }
        };

        const toggleRule = async (rule) => {
            await API.post(`/rules/${encodeURIComponent(rule.path)}/toggle`, { enabled: !rule.enabled });
            await loadRules();
        };

        const runRule = async (rule) => {
            const data = await API.post(`/rules/${encodeURIComponent(rule.path)}/run`, {});
            message.value = `任务已创建：${data.task_id}`;
        };

        onMounted(loadRules);
        const prettyJson = (value) => JSON.stringify(value, null, 2);

        return { rules, selected, yaml, message, loading, previewing, previewResult, loadRules, editRule, newRule, formatRuleYaml, saveRule, previewRule, toggleRule, runRule, prettyJson };
    },
    template: `
<section class="console-view split-view">
  <div>
    <header class="view-header">
      <div>
        <h1>Rule Center</h1>
        <p>版本化 YAML DSL、人工发布与沙箱试采入口</p>
      </div>
      <button @click="newRule">新建</button>
    </header>
    <div class="panel">
      <div class="panel-bar"><h2>规则清单</h2><button @click="loadRules">刷新</button></div>
      <table class="data-table dense">
        <thead><tr><th>规则</th><th>主题</th><th>平台</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="rule in rules" :key="rule.path" :class="{selected: selected?.path === rule.path}">
            <td><strong>{{ rule.name }}</strong><br><code>{{ rule.path }}</code></td>
            <td>{{ rule.subject || '-' }}</td>
            <td>{{ rule.platform || '-' }}</td>
            <td><StatusBadge :value="rule.enabled ? 'PRODUCTION' : 'PAUSED'" /></td>
            <td class="actions">
              <button @click="editRule(rule)">编辑</button>
              <button @click="runRule(rule)">执行</button>
              <button @click="toggleRule(rule)">{{ rule.enabled ? '停用' : '启用' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <aside class="panel editor-panel">
    <div class="panel-bar">
      <h2>{{ selected ? selected.path : 'YAML 编辑器' }}</h2>
      <div class="actions">
        <button :disabled="!yaml.trim()" @click="formatRuleYaml">格式化</button>
        <button :disabled="!selected || loading || previewing" @click="previewRule">试采</button>
        <button :disabled="!selected || loading" @click="saveRule">保存</button>
      </div>
    </div>
    <textarea v-model="yaml" spellcheck="false" placeholder="选择或新建规则"></textarea>
    <div class="message" v-if="message">{{ message }}</div>
    <div class="preview-panel" v-if="previewResult">
      <div class="panel-bar">
        <h2>试采结果</h2>
        <span>{{ previewResult.status || (previewResult.success ? 'SUCCESS' : 'FAILED') }}</span>
      </div>
      <div v-if="previewResult.success">
        <p>总条数：{{ previewResult.total_collected }}，展示：{{ previewResult.preview_count }}</p>
        <p v-if="previewResult.ocr_summary && previewResult.ocr_summary.enabled">
          OCR 插件：{{ previewResult.ocr_summary.plugin || 'tesseract' }}，
          图片 {{ previewResult.ocr_summary.images_found || 0 }} 张，
          下载 {{ previewResult.ocr_summary.images_downloaded || 0 }} 张，
          识别成功 {{ previewResult.ocr_summary.ocr_success || 0 }} 张，
          人工复核 {{ previewResult.ocr_summary.manual_review_required || 0 }} 条
        </p>
        <pre>{{ prettyJson(previewResult.items || []) }}</pre>
      </div>
      <div v-else class="message">{{ previewResult.error }}</div>
    </div>
  </aside>
</section>`
};

const TaskCenter = {
    setup() {
        const tasks = ref([]);
        const running = ref(false);
        const logs = ref([]);
        let stream = null;

        const loadHistory = async () => {
            const data = await API.get('/tasks/history');
            tasks.value = data.tasks || [];
        };

        const runAll = async () => {
            logs.value = [];
            running.value = true;
            const { task_id } = await API.post('/tasks/run-all', {});
            logs.value.push({ type: 'status', text: `任务 ${task_id} 已创建` });
            stream = API.sse(`/api/tasks/stream/${task_id}`, {
                onData(data) {
                    if (data.type === 'status') logs.value.push({ type: 'status', text: `[${data.rule}] ${data.msg}` });
                    if (data.type === 'progress') logs.value.push({ type: 'status', text: `[${data.rule}] ${data.phase} ${data.current}/${data.total}` });
                    if (data.type === 'error') logs.value.push({ type: 'error', text: `[${data.rule}] ${data.message}` });
                    if (data.type === 'complete') logs.value.push({ type: 'done', text: `[${data.rule}] 新增 ${data.new_count}` });
                    if (data.type === 'done') {
                        logs.value.push({ type: data.success ? 'done' : 'error', text: `完成：新增 ${data.total_new}，错误 ${data.total_error}` });
                        running.value = false;
                        loadHistory();
                        stream?.close();
                    }
                },
                onError() {
                    logs.value.push({ type: 'error', text: '事件流断开' });
                    running.value = false;
                }
            });
        };

        const stop = () => {
            stream?.close();
            running.value = false;
        };

        onMounted(loadHistory);
        onUnmounted(() => stream?.close());
        return { tasks, running, logs, loadHistory, runAll, stop, fmtTime };
    },
    template: `
<section class="console-view">
  <header class="view-header">
    <div>
      <h1>Task Center</h1>
      <p>任务状态机、实时事件、手动执行和审计记录</p>
    </div>
    <div class="actions">
      <button @click="loadHistory">刷新</button>
      <button v-if="!running" @click="runAll">执行全部</button>
      <button v-else class="danger" @click="stop">停止监听</button>
    </div>
  </header>

  <div class="panel">
    <div class="panel-bar"><h2>实时事件</h2><span>{{ running ? 'RUNNING' : 'IDLE' }}</span></div>
    <div class="log-stream">
      <div v-for="(line, index) in logs" :key="index" :class="['log-line', line.type]">{{ line.text }}</div>
      <div v-if="logs.length === 0" class="empty">暂无实时事件</div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-bar"><h2>任务历史</h2></div>
    <table class="data-table dense">
      <thead><tr><th>ID</th><th>任务</th><th>状态</th><th>触发</th><th>新增</th><th>耗时</th><th>创建时间</th></tr></thead>
      <tbody>
        <tr v-for="task in tasks" :key="task.id">
          <td>{{ task.id }}</td>
          <td><strong>{{ task.task_name }}</strong><br><code>{{ task.rule_path || '全部规则' }}</code></td>
          <td><StatusBadge :value="task.ng_status || task.status" /></td>
          <td>{{ task.trigger_type || '-' }}</td>
          <td>{{ task.new_count || 0 }}</td>
          <td>{{ task.duration ? task.duration + 's' : '-' }}</td>
          <td>{{ fmtTime(task.created_at) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</section>`
};

const GovernanceCenter = {
    setup() {
        const data = ref({ summary: {}, records: [] });
        const loading = ref(true);
        const load = async () => {
            loading.value = true;
            try {
                data.value = await API.get('/governance/summary');
            } finally {
                loading.value = false;
            }
        };
        onMounted(load);
        return { data, loading, load, fmtNumber, fmtPercent };
    },
    template: `
<section class="console-view">
  <header class="view-header">
    <div>
      <h1>Governance Center</h1>
      <p>字段完整率、去重、注入风险和质量评分</p>
    </div>
    <button @click="load">刷新</button>
  </header>

  <div class="metric-grid">
    <div class="metric"><span>数据文件</span><strong>{{ fmtNumber(data.summary.file_count) }}</strong></div>
    <div class="metric"><span>结构化记录</span><strong>{{ fmtNumber(data.summary.total_items) }}</strong></div>
    <div class="metric"><span>注入风险</span><strong>{{ fmtNumber(data.summary.injection_risk_count) }}</strong></div>
    <div class="metric"><span>平均质量分</span><strong>{{ fmtPercent(data.summary.avg_quality_score) }}</strong></div>
  </div>

  <div class="panel">
    <div class="panel-bar"><h2>治理记录</h2></div>
    <div v-if="loading" class="empty">加载中...</div>
    <table v-else class="data-table dense">
      <thead><tr><th>主题</th><th>平台</th><th>文件</th><th>记录数</th><th>字段完整率</th><th>质量分</th><th>风险</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="record in data.records" :key="record.subject + record.platform + record.source_file">
          <td>{{ record.subject || '-' }}</td>
          <td>{{ record.platform || '-' }}</td>
          <td><code>{{ record.source_file }}</code></td>
          <td>{{ record.item_count }}</td>
          <td>{{ fmtPercent(record.field_completeness) }}</td>
          <td>{{ fmtPercent(record.quality_score) }}</td>
          <td>{{ record.injection_risk_count }}</td>
          <td><StatusBadge :value="record.status" /></td>
        </tr>
      </tbody>
    </table>
  </div>
</section>`
};

const ArchiveCenter = {
    setup() {
        const pages = ref([]);
        const loading = ref(true);
        const selected = ref(null);
        const detail = ref(null);
        const detailLoading = ref(false);

        const load = async () => {
            loading.value = true;
            try {
                const resp = await API.get('/archives');
                pages.value = resp.pages || [];
            } finally {
                loading.value = false;
            }
        };

        const selectPage = async (page) => {
            if (selected.value?.content_hash === page.content_hash) {
                selected.value = null;
                detail.value = null;
                return;
            }
            selected.value = page;
            detail.value = null;
            detailLoading.value = true;
            try {
                detail.value = await API.get(`/archives/${page.content_hash}`);
            } finally {
                detailLoading.value = false;
            }
        };

        const blockTypeLabel = (type) => ({
            heading: '标题', paragraph: '段落', image: '图片',
            ocr: 'OCR', table: '表格', attachment: '附件',
        }[type] || type);

        onMounted(load);
        return { pages, loading, load, selected, detail, detailLoading, selectPage, blockTypeLabel, fmtNumber };
    },
    template: `
<section class="console-view">
  <header class="view-header">
    <div>
      <h1>Archive Center</h1>
      <p>页面归档复核 — 原始内容块、OCR 文本与精抽记录</p>
    </div>
    <button @click="load">刷新</button>
  </header>

  <div class="split-view" style="display:flex;gap:1rem;align-items:flex-start;">
    <!-- 左侧列表 -->
    <div style="flex:1;min-width:0;">
      <div class="panel">
        <div class="panel-bar"><h2>归档页 ({{ fmtNumber(pages.length) }})</h2></div>
        <div v-if="loading" class="empty">加载中...</div>
        <table v-else-if="pages.length" class="data-table dense">
          <thead><tr><th>标题</th><th>平台</th><th>主题</th><th>块数</th><th>OCR</th><th>精抽</th><th>时间</th></tr></thead>
          <tbody>
            <tr
              v-for="p in pages"
              :key="p.content_hash"
              :class="{ active: selected?.content_hash === p.content_hash }"
              style="cursor:pointer"
              @click="selectPage(p)"
            >
              <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="p.title || p.source_url">
                {{ p.title || p.source_url || '-' }}
              </td>
              <td>{{ p.platform || '-' }}</td>
              <td>{{ p.subject || '-' }}</td>
              <td>{{ p.block_count }}</td>
              <td><StatusBadge :value="p.contains_ocr ? 'YES' : 'NO'" /></td>
              <td><StatusBadge :value="p.requires_structuring ? 'YES' : 'NO'" /></td>
              <td style="white-space:nowrap;font-size:0.8em">{{ (p.fetched_at || '').slice(0,19).replace('T',' ') }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">暂无归档记录。规则配置 <code>archive.enabled: true</code> 后运行采集任务。</div>
      </div>
    </div>

    <!-- 右侧详情 -->
    <div v-if="selected" style="flex:1;min-width:0;">
      <div class="panel">
        <div class="panel-bar">
          <h2>{{ selected.title || selected.source_url }}</h2>
          <button @click="selected=null;detail=null" style="margin-left:auto">关闭</button>
        </div>
        <div v-if="detailLoading" class="empty">加载中...</div>
        <div v-else-if="detail">
          <div style="padding:0.5rem 1rem;font-size:0.82em;color:#888;word-break:break-all">
            <a :href="selected.source_url" target="_blank">{{ selected.source_url }}</a>
          </div>
          <!-- 内容块 -->
          <div style="padding:0 1rem 0.5rem">
            <strong>内容块 ({{ (detail.blocks||[]).length }})</strong>
          </div>
          <table class="data-table dense" style="margin:0 1rem;width:calc(100% - 2rem)">
            <thead><tr><th>#</th><th>类型</th><th>内容</th></tr></thead>
            <tbody>
              <tr v-for="b in detail.blocks" :key="b.id">
                <td>{{ b.block_order }}</td>
                <td><code>{{ blockTypeLabel(b.block_type) }}</code></td>
                <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:0.85em">
                  {{ b.text || b.ocr_text || (b.source_url ? '[图片] '+b.source_url : '') || '-' }}
                </td>
              </tr>
            </tbody>
          </table>
          <!-- 精抽记录 -->
          <div v-if="(detail.structured_records||[]).length" style="margin-top:1rem;padding:0 1rem 0.5rem">
            <strong>精抽记录 ({{ detail.structured_records.length }})</strong>
            <table class="data-table dense" style="margin-top:0.25rem">
              <thead><tr><th>类型</th><th>字段</th><th>值</th></tr></thead>
              <tbody>
                <template v-for="sr in detail.structured_records" :key="sr.record_type+JSON.stringify(sr.data)">
                  <tr v-for="(v,k) in sr.data" :key="k">
                    <td><code>{{ sr.record_type }}</code></td>
                    <td>{{ k }}</td>
                    <td>{{ v }}</td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>`
};

const app = createApp({
    setup() {
        const tabs = [
            { id: 'sources', label: 'Source Center', component: 'SourceCenter' },
            { id: 'rules', label: 'Rule Center', component: 'RuleCenter' },
            { id: 'tasks', label: 'Task Center', component: 'TaskCenter' },
            { id: 'governance', label: 'Governance Center', component: 'GovernanceCenter' },
            { id: 'archives', label: 'Archive Center', component: 'ArchiveCenter' },
        ];
        const currentTab = ref('sources');
        const currentComponent = computed(() => tabs.find(tab => tab.id === currentTab.value)?.component || 'SourceCenter');
        return { tabs, currentTab, currentComponent };
    }
});

app.component('StatusBadge', StatusBadge);
app.component('SourceCenter', SourceCenter);
app.component('RuleCenter', RuleCenter);
app.component('TaskCenter', TaskCenter);
app.component('GovernanceCenter', GovernanceCenter);
app.component('ArchiveCenter', ArchiveCenter);
app.mount('#app');
