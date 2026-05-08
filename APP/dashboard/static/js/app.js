const { createApp, ref, computed, onMounted, onUnmounted, watch } = Vue;

// ── API Helper ────────────────────────────────────────────────────────────────
// API is defined in /static/js/api.js (shared across all components)
// This file only defines Vue components — import no duplicate API here.

// ── DashboardHome ─────────────────────────────────────────────────────────────
const DashboardHome = {
    setup() {
        const stats = ref({});
        const recentTasks = ref([]);
        const loading = ref(true);

        const loadStats = async () => {
            try {
                const [dataStats, tasks] = await Promise.all([
                    API.get('/data/stats'),
                    API.get('/tasks/history').catch(() => ({ tasks: [] }))
                ]);
                stats.value = dataStats;
                recentTasks.value = tasks.tasks?.slice(0, 10) || [];
            } catch (err) {
                console.error(err);
            } finally {
                loading.value = false;
            }
        };

        onMounted(loadStats);

        const totalCount = computed(() => {
            let total = 0;
            for (const platforms of Object.values(stats.value)) {
                for (const info of Object.values(platforms)) {
                    total += typeof info === 'object' && info !== null ? (info.count || 0) : (info || 0);
                }
            }
            return total;
        });

        return { stats, recentTasks, loading, totalCount };
    },
    template: `
<div class="dashboard-home">
  <div class="card">
    <h2>📊 数据概览</h2>
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else>
      <div class="stat-cards">
        <div class="stat-card">
          <div class="stat-value">{{ totalCount }}</div>
          <div class="stat-label">总数据条数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ Object.keys(stats).length }}</div>
          <div class="stat-label">数据主题</div>
        </div>
      </div>
      <div v-for="(platforms, subject) in stats" :key="subject" class="subject-row">
        <h3>{{ subject }}</h3>
        <div class="platform-tags">
          <span v-for="(info, platform) in platforms" :key="platform" class="platform-tag">
            {{ platform }}: {{ typeof info === 'object' ? info.count : info }}
          </span>
        </div>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>🕐 最近任务</h2>
    <div v-if="recentTasks.length === 0" class="empty">暂无任务记录</div>
    <table v-else class="data-table">
      <thead><tr><th>任务</th><th>状态</th><th>新增</th><th>耗时</th><th>时间</th></tr></thead>
      <tbody>
        <tr v-for="task in recentTasks" :key="task.id">
          <td>{{ task.task_name }}</td>
          <td><span :class="['status-badge', task.status]">{{ task.status }}</span></td>
          <td>{{ task.new_count || 0 }}</td>
          <td>{{ task.duration ? task.duration + 's' : '-' }}</td>
          <td>{{ task.created_at ? new Date(task.created_at).toLocaleString() : '-' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
    `
};

// ── RuleList ──────────────────────────────────────────────────────────────────
const RuleList = {
    emits: ['switch-tab', 'edit-rule'],
    setup(props, { emit }) {
        const rules = ref([]);
        const showRunDialog = ref(false);
        const runResult = ref(null);
        const runResultDuration = ref(null);
        const runOutput = ref([]);

        const loadRules = async () => {
            try {
                const data = await API.get('/rules');
                rules.value = data.rules || [];
            } catch (err) {
                console.error('loadRules error:', err);
                alert('加载规则失败: ' + err.message);
            }
        };

        const toggleRule = async (rule) => {
            try {
                const enabled = !rule.enabled;
                const data = await API.post(`/rules/${encodeURIComponent(rule.path)}/toggle`, { enabled });
                rule.enabled = data.enabled !== undefined ? data.enabled : enabled;
            } catch (err) {
                console.error('toggleRule error:', err);
                alert('切换状态失败: ' + err.message);
            }
        };

        const runRule = async (rule) => {
            showRunDialog.value = true;
            runResult.value = null;
            runResultDuration.value = null;
            runOutput.value = [{ type: 'info', text: `正在执行 ${rule.name}...` }];

            try {
                const { task_id } = await API.post(`/rules/${encodeURIComponent(rule.path)}/run`, {});

                const es = API.sse(`/api/tasks/stream/${task_id}`, {
                    onData(data) {
                        if (data.type === 'start') {
                            runOutput.value.push({ type: 'info', text: '任务已启动，监控执行中...' });
                        } else if (data.type === 'status') {
                            runOutput.value.push({ type: 'log', text: `[${data.rule}] ${data.msg}` });
                        } else if (data.type === 'progress') {
                            runOutput.value.push({ type: 'log', text: `[${data.rule}] ${data.phase} (${data.current}/${data.total})` });
                        } else if (data.type === 'error') {
                            runOutput.value.push({ type: 'error', text: `❌ [${data.rule}] ${data.message}` });
                        } else if (data.type === 'complete') {
                            runOutput.value.push({ type: 'log', text: `✅ [${data.rule}] 完成: 新增 ${data.new_count} 条，耗时 ${data.duration}s` });
                        } else if (data.type === 'done') {
                            runOutput.value.push({ type: 'done', text: `执行${data.success ? '成功' : '失败'} — 新增: ${data.total_new} | 跳过: ${data.total_skip} | 错误: ${data.total_error} | 耗时: ${data.duration}s` });
                            runResult.value = { success: data.success, new_count: data.total_new, duration: data.duration };
                            runResultDuration.value = data.duration;
                            es.close();
                        }
                    },
                    onError() {
                        runOutput.value.push({ type: 'error', text: 'SSE 连接断开' });
                    }
                });
            } catch (err) {
                console.error('runRule error:', err);
                runResult.value = { success: false, error: err.message };
            }
        };

        const editRule = async (rule) => {
            try {
                const data = await API.get(`/rules/${encodeURIComponent(rule.path)}`);
                emit('switch-tab', 'rule-editor');
                emit('edit-rule', { rule, yaml: data.yaml });
            } catch (err) {
                console.error('editRule error:', err);
                alert('加载规则失败: ' + err.message);
            }
        };

        const createRule = () => {
            emit('switch-tab', 'rule-editor');
            emit('edit-rule', { rule: null, yaml: '' });
        };

        const deleteRule = async (rule) => {
            if (!confirm(`确定要删除规则 "${rule.name}" 吗？此操作不可恢复。`)) return;
            try {
                await API.delete(`/rules/${encodeURIComponent(rule.path)}`);
                await loadRules();
            } catch (err) {
                console.error('deleteRule error:', err);
                alert('删除规则失败: ' + err.message);
            }
        };

        onMounted(loadRules);

        return {
            rules, showRunDialog, runResult, runResultDuration, runOutput,
            loadRules, toggleRule, runRule, editRule, createRule, deleteRule,
        };
    },
    template: `
<div class="rule-list">
  <div class="toolbar">
    <button @click="loadRules" class="btn-primary">刷新</button>
    <button @click="createRule" class="btn-primary">新建规则</button>
    <span class="rule-count">{{ rules.length }} 条规则</span>
  </div>

  <table class="data-table">
    <thead><tr><th>名称</th><th>平台</th><th>主题</th><th>状态</th><th>最近运行</th><th>操作</th></tr></thead>
    <tbody>
      <tr v-for="rule in rules" :key="rule.path">
        <td>{{ rule.name }}</td>
        <td>{{ rule.platform }}</td>
        <td>{{ rule.subject }}</td>
        <td><span :class="['status-badge', rule.enabled ? 'on' : 'off']">{{ rule.enabled ? 'ON' : 'OFF' }}</span></td>
        <td>{{ rule.last_run || '-' }}</td>
        <td>
          <button @click="toggleRule(rule)" class="btn-sm">{{ rule.enabled ? '停用' : '启用' }}</button>
          <button @click="runRule(rule)" class="btn-sm">执行</button>
          <button @click="editRule(rule)" class="btn-sm">编辑</button>
          <button @click="deleteRule(rule)" class="btn-sm btn-danger">删除</button>
        </td>
      </tr>
    </tbody>
  </table>

  <div v-if="showRunDialog" class="dialog-overlay" @click.self="showRunDialog = false">
    <div class="dialog" style="max-width:700px">
      <h3>执行结果</h3>
      <div v-if="runOutput.length > 0" class="terminal-window" style="max-height:300px;overflow-y:auto;margin-bottom:12px">
        <div v-for="(line, i) in runOutput" :key="i" :class="['term-line', line.type]">{{ line.text }}</div>
      </div>
      <div v-if="runResult">
        <p>状态: {{ runResult.success ? '✅ 成功' : '❌ 失败' }}</p>
        <p>新增数据: {{ runResult.new_count ?? '-' }} 条</p>
        <p>耗时: {{ runResult.duration ?? '-' }} 秒</p>
        <p v-if="runResult.error" class="error-msg">{{ runResult.error }}</p>
      </div>
      <div v-else-if="runOutput.length === 0"><p>加载中...</p></div>
      <div style="margin-top:16px;text-align:right">
        <button @click="showRunDialog = false" class="btn-primary">关闭</button>
      </div>
    </div>
  </div>
</div>
    `
};

// ── TaskRunner ────────────────────────────────────────────────────────────────
const TaskRunner = {
    setup() {
        const isRunning = ref(false);
        const output = ref([]);
        const taskHistory = ref([]);
        const activeEs = ref(null);

        const loadHistory = async () => {
            try {
                const data = await API.get('/tasks/history');
                taskHistory.value = data.tasks || [];
            } catch (err) {
                console.error(err);
            }
        };

        const startRunAll = async () => {
            isRunning.value = true;
            output.value = [{ type: 'info', text: '正在创建任务...' }];

            try {
                const { task_id } = await API.post('/tasks/run-all', {});

                const es = API.sse(`/api/tasks/stream/${task_id}`, {
                    onData(data) {
                        if (data.type === 'start') {
                            output.value.push({ type: 'info', text: `任务已启动 (ID: ${task_id})，监控执行中...` });
                        } else if (data.type === 'status') {
                            output.value.push({ type: 'log', text: `[${data.rule}] ${data.msg}` });
                        } else if (data.type === 'progress') {
                            output.value.push({ type: 'log', text: `[${data.rule}] ${data.phase} (${data.current}/${data.total})` });
                        } else if (data.type === 'error') {
                            output.value.push({ type: 'error', text: `❌ [${data.rule}] ${data.message}` });
                        } else if (data.type === 'complete') {
                            output.value.push({ type: 'log', text: `✅ [${data.rule}] 新增 ${data.new_count} 条，耗时 ${data.duration}s` });
                        } else if (data.type === 'done') {
                            const icon = data.success ? '✅' : '❌';
                            output.value.push({ type: 'done', text: `${icon} 执行${data.success ? '成功' : '失败'} — 新增: ${data.total_new} | 跳过: ${data.total_skip} | 错误: ${data.total_error} | 耗时: ${data.duration}s` });
                            isRunning.value = false;
                            activeEs.value = null;
                            loadHistory();
                            es.close();
                        } else if (data.type === 'heartbeat') {
                            // ignore
                        }
                    },
                    onError() {
                        output.value.push({ type: 'error', text: 'SSE 连接断开' });
                        isRunning.value = false;
                        activeEs.value = null;
                    }
                });
                activeEs.value = es;
            } catch (err) {
                output.value.push({ type: 'error', text: '启动失败: ' + err.message });
                isRunning.value = false;
            }
        };

        const stopRunAll = () => {
            activeEs.value?.close();
            activeEs.value = null;
            isRunning.value = false;
        };

        onMounted(loadHistory);
        onUnmounted(() => activeEs.value?.close());

        return { isRunning, output, taskHistory, activeEs, startRunAll, stopRunAll, loadHistory };
    },
    template: `
<div class="task-runner">
  <div class="card">
    <h2>▶️ 立即执行</h2>
    <p>执行所有已启用的采集规则</p>
    <button v-if="!isRunning" @click="startRunAll" class="btn-primary btn-lg">执行所有规则</button>
    <button v-else @click="stopRunAll" class="btn-danger btn-lg">停止</button>

    <div class="terminal-window">
      <div class="terminal-header">实时输出</div>
      <div class="terminal-body">
        <div v-for="(line, i) in output" :key="i" :class="['term-line', line.type]">
          {{ line.text }}
        </div>
        <div v-if="output.length === 0" class="empty">暂无输出</div>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>📋 任务历史</h2>
    <button @click="loadHistory" class="btn-sm" style="margin-bottom:12px">刷新</button>
    <div v-if="taskHistory.length === 0" class="empty">暂无任务记录</div>
    <table v-else class="data-table">
      <thead><tr><th>ID</th><th>任务</th><th>状态</th><th>新增</th><th>耗时</th><th>时间</th></tr></thead>
      <tbody>
        <tr v-for="task in taskHistory" :key="task.id">
          <td>{{ task.id }}</td>
          <td>{{ task.task_name }}</td>
          <td><span :class="['status-badge', task.status]">{{ task.status }}</span></td>
          <td>{{ task.new_count || 0 }}</td>
          <td>{{ task.duration ? task.duration + 's' : '-' }}</td>
          <td>{{ task.created_at ? new Date(task.created_at).toLocaleString() : '-' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
    `
};

// ── LogViewer ─────────────────────────────────────────────────────────────────
const LogViewer = {
    setup() {
        const logs = ref([]);
        const selectedLog = ref(null);
        const logContent = ref([]);
        const isStreaming = ref(false);
        let es = null;

        const loadLogs = async () => {
            try {
                const data = await API.get('/logs/list');
                logs.value = data.logs || [];
            } catch (err) {
                console.error(err);
            }
        };

        const selectLog = async (log) => {
            selectedLog.value = log;
            logContent.value = [];
            try {
                const data = await API.get(`/logs/tail/${encodeURIComponent(log.name)}?lines=200`);
                logContent.value = data.lines || [];
            } catch (err) {
                console.error(err);
            }
        };

        const startStream = () => {
            isStreaming.value = true;
            logContent.value = [{ type: 'info', text: '[实时监控] 等待新日志...' }];

            es = API.sse('/api/logs/stream', {
                onData(data) {
                    if (data.type === 'log') {
                        logContent.value.push({ type: 'log', text: data.line });
                        if (logContent.value.length > 500) logContent.value.shift();
                    } else if (data.type === 'info') {
                        logContent.value.push({ type: 'info', text: data.msg });
                    }
                },
                onError() {
                    logContent.value.push({ type: 'error', text: '[连接断开]' });
                    isStreaming.value = false;
                }
            });
        };

        const stopStream = () => {
            es?.close();
            isStreaming.value = false;
        };

        onMounted(loadLogs);
        onUnmounted(() => es?.close());

        return { logs, selectedLog, logContent, isStreaming, selectLog, startStream, stopStream, loadLogs };
    },
    template: `
<div class="log-viewer">
  <div class="card">
    <h2>📄 日志列表</h2>
    <button @click="loadLogs" class="btn-sm">刷新</button>
    <div v-if="logs.length === 0" class="empty">暂无日志文件</div>
    <div v-else class="log-list">
      <div
        v-for="log in logs"
        :key="log.name"
        :class="['log-item', selectedLog?.name === log.name ? 'active' : '']"
        @click="selectLog(log)"
      >
        <span class="log-name">{{ log.name }}</span>
        <span class="log-meta">{{ (log.size / 1024).toFixed(1) }} KB · {{ new Date(log.modified_at).toLocaleString() }}</span>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>📜 日志内容 <span v-if="selectedLog"> — {{ selectedLog.name }}</span></h2>
    <div class="toolbar">
      <button v-if="!isStreaming" @click="startStream" class="btn-sm btn-primary">实时监控</button>
      <button v-else @click="stopStream" class="btn-sm btn-danger">停止监控</button>
    </div>
    <div class="terminal-window">
      <div class="terminal-body" style="max-height:500px;overflow-y:auto">
        <div v-for="(line, i) in logContent" :key="i" :class="['term-line', line.type || 'log']">{{ typeof line === 'string' ? line : line.text }}</div>
        <div v-if="logContent.length === 0" class="empty">选择左侧日志文件查看内容</div>
      </div>
    </div>
  </div>
</div>
    `
};

// ── CronManager ───────────────────────────────────────────────────────────────
const CronManager = {
    emits: ['switch-tab'],
    setup() {
        const crons = ref([]);
        const showForm = ref(false);
        const editingCron = ref(null);
        const form = ref({ name: '', schedule: '', rule_path: '', enabled: true });
        const history = ref([]);

        const loadCrons = async () => {
            try {
                const data = await API.get('/cron');
                crons.value = data.crons || [];
            } catch (err) { console.error(err); }
        };

        const loadHistory = async () => {
            try {
                const data = await API.get('/tasks/history');
                history.value = data.tasks?.slice(0, 20) || [];
            } catch (err) { console.error(err); }
        };

        const openCreate = () => {
            editingCron.value = null;
            form.value = { name: '', schedule: '0 * * * *', rule_path: '', enabled: true };
            showForm.value = true;
        };

        const openEdit = (cron) => {
            editingCron.value = cron;
            const parts = [cron.second, cron.minute, cron.hour, cron.day, cron.month, cron.day_of_week].filter(p => p && p !== '*');
            const schedule = parts.length >= 5 ? parts.join(' ') : `${cron.minute} ${cron.hour} ${cron.day} ${cron.month} ${cron.day_of_week}`;
            form.value = { name: cron.name, schedule, rule_path: cron.rule_path || '', enabled: !!cron.enabled };
            showForm.value = true;
        };

        const saveCron = async () => {
            try {
                if (editingCron.value) {
                    await API.post(`/cron/${editingCron.value.id}`, form.value);
                } else {
                    await API.post('/cron', form.value);
                }
                showForm.value = false;
                await loadCrons();
            } catch (err) { alert('保存失败: ' + err.message); }
        };

        const deleteCron = async (cron) => {
            if (!confirm(`删除定时任务 "${cron.name}"？`)) return;
            try {
                await API.delete(`/cron/${cron.id}`);
                await loadCrons();
            } catch (err) { alert('删除失败: ' + err.message); }
        };

        const toggleCron = async (cron) => {
            try {
                await API.post(`/cron/${cron.id}/toggle`, { enabled: !cron.enabled });
                await loadCrons();
            } catch (err) { alert('切换失败: ' + err.message); }
        };

        onMounted(() => { loadCrons(); loadHistory(); });

        return { crons, showForm, editingCron, form, history, openCreate, openEdit, saveCron, deleteCron, toggleCron };
    },
    template: `
<div class="cron-manager">
  <div class="card">
    <h2>⏰ 定时任务</h2>
    <div class="toolbar">
      <button @click="openCreate" class="btn-primary">新建定时任务</button>
      <button @click="loadCrons" class="btn-sm">刷新</button>
    </div>

    <div v-if="crons.length === 0" class="empty">暂无定时任务</div>
    <table v-else class="data-table">
      <thead><tr><th>名称</th><th>规则</th><th>调度表达式</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="cron in crons" :key="cron.id">
          <td>{{ cron.name }}</td>
          <td><code>{{ cron.rule_path || '全部' }}</code></td>
          <td><code>{{ cron.minute }} {{ cron.hour }} {{ cron.day }} {{ cron.month }} {{ cron.day_of_week }}</code></td>
          <td><span :class="['status-badge', cron.enabled ? 'on' : 'off']">{{ cron.enabled ? '启用' : '停用' }}</span></td>
          <td>
            <button @click="toggleCron(cron)" class="btn-sm">{{ cron.enabled ? '停用' : '启用' }}</button>
            <button @click="openEdit(cron)" class="btn-sm">编辑</button>
            <button @click="deleteCron(cron)" class="btn-sm btn-danger">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card">
    <h2>📋 执行历史</h2>
    <button @click="loadHistory" class="btn-sm" style="margin-bottom:12px">刷新</button>
    <div v-if="history.length === 0" class="empty">暂无执行记录</div>
    <table v-else class="data-table">
      <thead><tr><th>任务</th><th>状态</th><th>新增</th><th>耗时</th><th>时间</th></tr></thead>
      <tbody>
        <tr v-for="task in history" :key="task.id">
          <td>{{ task.task_name }}</td>
          <td><span :class="['status-badge', task.status]">{{ task.status }}</span></td>
          <td>{{ task.new_count || 0 }}</td>
          <td>{{ task.duration ? task.duration + 's' : '-' }}</td>
          <td>{{ task.created_at ? new Date(task.created_at).toLocaleString() : '-' }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div v-if="showForm" class="dialog-overlay" @click.self="showForm = false">
    <div class="dialog">
      <h3>{{ editingCron ? '编辑定时任务' : '新建定时任务' }}</h3>
      <div class="form-group">
        <label>名称</label>
        <input v-model="form.name" placeholder="任务名称" />
      </div>
      <div class="form-group">
        <label>Cron 表达式</label>
        <input v-model="form.schedule" placeholder="0 * * * *" />
        <small>格式: 分 时 日 月 周 (例如: 0 * * * * = 每小时)</small>
      </div>
      <div class="form-group">
        <label>规则路径（可选，留空表示全部规则）</label>
        <input v-model="form.rule_path" placeholder="rules/主题/平台.yaml" />
      </div>
      <div class="form-group">
        <label><input type="checkbox" v-model="form.enabled" /> 立即启用</label>
      </div>
      <div style="margin-top:16px;text-align:right">
        <button @click="showForm = false" class="btn-sm">取消</button>
        <button @click="saveCron" class="btn-primary">保存</button>
      </div>
    </div>
  </div>
</div>
    `
};

// ── RuleEditor ────────────────────────────────────────────────────────────────
const RuleEditor = {
    props: ['editRuleData'],
    emits: ['switch-tab'],
    setup(props, { emit }) {
        const yaml = ref(props.editRuleData?.yaml || '');
        const isNew = computed(() => !props.editRuleData?.rule);
        const saving = ref(false);
        const message = ref('');
        const activeStep = ref(0);
        const steps = ['基本信息', '数据源', '请求配置', '列表提取', '渲染配置', '分页/去重', '输出与调度'];

        // ── Basic info ──
        const name = ref(props.editRuleData?.rule?.name || '');
        const subject = ref(props.editRuleData?.rule?.subject || '');
        const platform = ref(props.editRuleData?.rule?.platform || '');
        const version = ref('1.0.0');
        const description = ref('');
        const enabled = ref(true);

        // ── Source ──
        const sourceType = ref('html');       // html | api | browser
        const sourceUrl = ref('');
        const sourceBaseUrl = ref('');
        const client = ref('auto');           // auto | mobile | desktop | browser | crawl4ai
        const authType = ref('none');
        // LLM extraction
        const extractionEnabled = ref(false);
        const extractionPrompt = ref('');
        const extractionStrategy = ref('llm');
        const extractionSchema = ref('');     // JSON string

        // ── Request (API) ──
        const reqMethod = ref('GET');
        const reqHeaders = ref('User-Agent: Mozilla/5.0\nContent-Type: application/json');
        const bodyTemplate = ref('');
        const reqParams = ref('');            // key: value per line

        // ── List extraction ──
        const itemsPath = ref('css:.item');
        const fields = ref([{ name: 'title', type: 'field' }]);

        const fieldTypes = ['constant', 'computed', 'field', 'attr', 'xpath'];

        const addField = () => fields.value.push({ name: '', type: 'field' });
        const removeField = (i) => fields.value.splice(i, 1);

        // ── Render ──
        const renderEnabled = ref(false);
        const headless = ref(true);
        const stealth = ref(true);
        const waitForSelector = ref('');
        const waitForTimeout = ref(3000);
        const viewportWidth = ref(1920);
        const viewportHeight = ref(1080);
        const markdown = ref(true);
        const removeForms = ref(false);

        // ── Pagination / Dedup ──
        const paginationEnabled = ref(false);
        const pageParam = ref('pageNum');
        const maxPages = ref(10);
        const dedupIncremental = ref(false);
        const urlToIdPattern = ref('');

        // ── Output / Schedule ──
        const outputFilename = ref('data_{date}.json');
        const outputPath = ref('');
        const scheduleCron = ref('');
        const scheduleEnabled = ref(true);

        // ── YAML raw editor ──
        const showYaml = ref(false);

        // ── Build YAML from form ──
        const buildYaml = () => {
            const lines = [];

            lines.push(`name: "${name.value}"`);
            if (subject.value) lines.push(`subject: "${subject.value}"`);
            lines.push(`version: "${version.value}"`);
            if (description.value) lines.push(`description: "${description.value}"`);
            lines.push(`enabled: ${enabled.value}`);
            lines.push('');

            // source
            lines.push('source:');
            lines.push(`  platform: "${platform.value}"`);
            lines.push(`  type: "${sourceType.value}"`);
            if (subject.value) lines.push(`  subject: "${subject.value}"`);
            if (authType.value && authType.value !== 'none') {
                lines.push(`  auth:`);
                lines.push(`    type: "${authType.value}"`);
            }

            if (sourceType.value === 'api') {
                if (sourceBaseUrl.value) lines.push(`  base_url: "${sourceBaseUrl.value}"`);
            } else {
                if (sourceUrl.value) lines.push(`  url: "${sourceUrl.value}"`);
            }
            if (client.value !== 'auto') lines.push(`  client: "${client.value}"`);

            // extraction
            if (extractionEnabled.value) {
                lines.push('  extraction:');
                lines.push('    enabled: true');
                if (extractionPrompt.value) {
                    lines.push('    prompt: |');
                    extractionPrompt.value.split('\n').forEach(l => lines.push(`      ${l}`));
                }
                lines.push(`    strategy: "${extractionStrategy.value}"`);
                if (extractionSchema.value.trim()) {
                    lines.push('    schema:');
                    try {
                        const schemaObj = JSON.parse(extractionSchema.value);
                        lines.push(`      ${JSON.stringify(schemaObj, null, 2)}`.split('\n').map(l => '    ' + l).join('\n'));
                    } catch (e) {
                        lines.push('      # 无效 JSON schema');
                    }
                }
            }
            lines.push('');

            // request (api)
            if (sourceType.value === 'api') {
                lines.push('request:');
                lines.push(`  method: "${reqMethod.value}"`);
                const headers = {};
                reqHeaders.value.split('\n').forEach(line => {
                    const [k, ...v] = line.split(':');
                    if (k && v.length) headers[k.trim()] = v.join(':').trim();
                });
                if (Object.keys(headers).length) {
                    lines.push('  headers:');
                    Object.entries(headers).forEach(([k, v]) => lines.push(`    ${k}: "${v}"`));
                }
                if (bodyTemplate.value) {
                    lines.push('  body_template: |');
                    bodyTemplate.value.split('\n').forEach(l => lines.push(`    ${l}`));
                }
                if (reqParams.value) {
                    lines.push('  params:');
                    reqParams.value.split('\n').forEach(line => {
                        const [k, ...v] = line.split(':');
                        if (k && v.length) lines.push(`    ${k.trim()}: "${v.join(':').trim()}"`);
                    });
                }
                lines.push('');
            }

            // list
            lines.push('list:');
            lines.push(`  items_path: "${itemsPath.value}"`);
            lines.push('  fields:');
            fields.value.forEach(f => {
                lines.push(`    - name: "${f.name}"`);
                lines.push(`      type: "${f.type}"`);
                if (f.type === 'constant' && f.value !== undefined && f.value !== '') lines.push(`      value: ${JSON.stringify(f.value)}`);
                if (f.type === 'field' && f.path) lines.push(`      path: "${f.path}"`);
                if (f.type === 'attr' && f.path) lines.push(`      path: "${f.path}"`);
                if (f.type === 'attr' && f.attr) lines.push(`      attr: "${f.attr}"`);
                if (f.type === 'xpath' && f.path) lines.push(`      path: "${f.path}"`);
                if (f.type === 'computed' && f.value) {
                    lines.push(`      value: "${f.value}"`);
                    lines.push('      vars:');
                    if (f.vars) {
                        Object.entries(f.vars).forEach(([vk, vv]) => lines.push(`        ${vk}: "${vv}"`));
                    }
                }
                if (f.transform) lines.push(`      transform: "${f.transform}"`);
            });
            lines.push('');

            // render
            if (renderEnabled.value || sourceType.value === 'browser' || client.value === 'browser' || client.value === 'crawl4ai') {
                lines.push('render:');
                if (renderEnabled.value) {
                    lines.push('  enabled: true');
                } else {
                    lines.push('  enabled: false');
                }
                lines.push(`  headless: ${headless.value}`);
                lines.push(`  stealth: ${stealth.value}`);
                if (waitForSelector.value) lines.push(`  wait_for_selector: "${waitForSelector.value}"`);
                if (waitForTimeout.value !== 3000) lines.push(`  wait_for_timeout: ${waitForTimeout.value}`);
                lines.push(`  viewport_width: ${viewportWidth.value}`);
                lines.push(`  viewport_height: ${viewportHeight.value}`);
                if (client.value === 'crawl4ai') {
                    lines.push(`  markdown: ${markdown.value}`);
                    lines.push(`  remove_forms: ${removeForms.value}`);
                }
                lines.push('');
            }

            // pagination (api)
            if (paginationEnabled.value && sourceType.value === 'api') {
                lines.push('pagination:');
                lines.push('  enabled: true');
                if (pageParam.value !== 'pageNum') lines.push(`  page_param: "${pageParam.value}"`);
                if (maxPages.value !== 10) lines.push(`  max_pages: ${maxPages.value}`);
                lines.push('');
            }

            // dedup
            if (dedupIncremental.value || urlToIdPattern.value) {
                lines.push('dedup:');
                lines.push(`  incremental: ${dedupIncremental.value}`);
                if (urlToIdPattern.value) lines.push(`  url_to_id_pattern: "${urlToIdPattern.value}"`);
                lines.push('');
            }

            // output
            lines.push('output:');
            lines.push('  format: json');
            if (outputFilename.value !== 'data_{date}.json') lines.push(`  filename_template: "${outputFilename.value}"`);
            if (outputPath.value) lines.push(`  path: "${outputPath.value}"`);
            lines.push('');

            // schedule
            if (scheduleCron.value) {
                lines.push('schedule:');
                lines.push(`  cron: "${scheduleCron.value}"`);
                lines.push(`  enabled: ${scheduleEnabled.value}`);
            }

            return lines.join('\n');
        };

        const save = async () => {
            if (!name.value || !subject.value || !platform.value) {
                message.value = '请填写名称、主题和平台';
                return;
            }
            const path = `rules/${subject.value}/${platform.value}_${name.value.replace(/\s+/g, '_')}.yaml`;
            saving.value = true;
            message.value = '';
            try {
                const fullYaml = showYaml.value ? yaml.value : buildYaml();
                await API.post('/rules', { path, yaml: fullYaml });
                message.value = '保存成功';
                setTimeout(() => emit('switch-tab', 'rules'), 1000);
            } catch (err) {
                message.value = '保存失败: ' + err.message;
            } finally {
                saving.value = false;
            }
        };

        const prevStep = () => { if (activeStep.value > 0) activeStep.value--; };
        const nextStep = () => { if (activeStep.value < steps.length - 1) activeStep.value++; };

        const typeOptions = [
            { label: 'HTML（直接请求，适合 SSR）', value: 'html' },
            { label: 'API（JSON 接口）', value: 'api' },
            { label: 'Browser（JS 渲染）', value: 'browser' },
        ];

        const clientOptions = [
            { label: 'auto — 自动（桌面优先，内容少时切换移动）', value: 'auto' },
            { label: 'mobile — 强制移动端 UA', value: 'mobile' },
            { label: 'desktop — 强制桌面端 UA', value: 'desktop' },
            { label: 'browser — 浏览器渲染（Playwright）', value: 'browser' },
            { label: 'crawl4ai — 浏览器渲染 + LLM 提取', value: 'crawl4ai' },
        ];

        const extractionStrategyOptions = [
            { label: 'llm — LLM 语义提取', value: 'llm' },
            { label: 'cosine — 余弦相似度语义过滤', value: 'cosine' },
        ];

        return {
            yaml, isNew, saving, message, activeStep, steps,
            name, subject, platform, version, description, enabled,
            sourceType, sourceUrl, sourceBaseUrl, client, authType,
            extractionEnabled, extractionPrompt, extractionStrategy, extractionSchema,
            reqMethod, reqHeaders, bodyTemplate, reqParams,
            itemsPath, fields, fieldTypes, addField, removeField,
            renderEnabled, headless, stealth, waitForSelector, waitForTimeout,
            viewportWidth, viewportHeight, markdown, removeForms,
            paginationEnabled, pageParam, maxPages,
            dedupIncremental, urlToIdPattern,
            outputFilename, outputPath, scheduleCron, scheduleEnabled,
            showYaml, save, prevStep, nextStep, typeOptions, clientOptions, extractionStrategyOptions,
        };
    },
    template: `
<div class="rule-editor">
  <div class="card">
    <h2>{{ isNew ? '➕ 新建规则' : '✏️ 编辑规则' }}</h2>

    <!-- Step indicator -->
    <div class="step-indicator">
      <div v-for="(step, i) in steps" :key="i" :class="['step', i === activeStep ? 'active' : '', i < activeStep ? 'done' : '']" @click="activeStep = i">
        <span class="step-num">{{ i + 1 }}</span>
        <span class="step-label">{{ step }}</span>
      </div>
    </div>

    <!-- ── Step 0: Basic Info ── -->
    <div v-show="activeStep === 0" class="step-panel">
      <div class="form-group">
        <label>规则名称 <span class="required">*</span></label>
        <input v-model="name" placeholder="例如: 巨潮资讯-数据要素公告" style="width:100%;padding:8px" />
      </div>
      <div class="form-row">
        <div class="form-group" style="flex:1">
          <label>主题（subject） <span class="required">*</span></label>
          <input v-model="subject" placeholder="例如: 数据要素" style="width:100%;padding:8px" />
        </div>
        <div class="form-group" style="flex:1">
          <label>平台（platform） <span class="required">*</span></label>
          <input v-model="platform" placeholder="例如: cninfo" style="width:100%;padding:8px" />
        </div>
      </div>
      <div class="form-row">
        <div class="form-group" style="flex:1">
          <label>版本</label>
          <input v-model="version" placeholder="1.0.0" style="width:100%;padding:8px" />
        </div>
        <div class="form-group" style="flex:1">
          <label>是否启用</label>
          <label style="display:flex;align-items:center;gap:8px">
            <input type="checkbox" v-model="enabled" /> 启用此规则
          </label>
        </div>
      </div>
      <div class="form-group">
        <label>描述</label>
        <textarea v-model="description" rows="3" style="width:100%;padding:8px" placeholder="规则用途说明..."></textarea>
      </div>
    </div>

    <!-- ── Step 1: Source ── -->
    <div v-show="activeStep === 1" class="step-panel">
      <div class="form-group">
        <label>数据源类型（type） <span class="required">*</span></label>
        <select v-model="sourceType" style="width:100%;padding:8px">
          <option v-for="opt in typeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
      </div>
      <div class="form-group">
        <label>URL</label>
        <input v-model="sourceUrl" :placeholder="sourceType === 'api' ? 'API 接口 URL（base_url）' : '列表页 URL'" style="width:100%;padding:8px" />
        <small v-if="sourceType === 'api'" style="color:#888">API 类型请使用 base_url 字段（下一步请求配置中）</small>
      </div>
      <div class="form-group">
        <label>UA 客户端策略（client）</label>
        <select v-model="client" style="width:100%;padding:8px">
          <option v-for="opt in clientOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <small style="color:#888">browser = Playwright 渲染；crawl4ai = 支持 LLM 提取的渲染引擎</small>
      </div>

      <!-- LLM Extraction -->
      <div class="section-divider">🤖 LLM 提取配置（仅 crawl4ai 客户端支持）</div>
      <div class="form-group">
        <label><input type="checkbox" v-model="extractionEnabled" /> 启用 LLM 提取</label>
      </div>
      <div v-if="extractionEnabled">
        <div class="form-group">
          <label>提取指令（prompt）</label>
          <textarea v-model="extractionPrompt" rows="4" style="width:100%;padding:8px" placeholder="请从文章页面提取：标题、作者、发布时间、正文内容"></textarea>
        </div>
        <div class="form-group">
          <label>提取策略（strategy）</label>
          <select v-model="extractionStrategy" style="width:100%;padding:8px">
            <option v-for="opt in extractionStrategyOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </div>
        <div class="form-group">
          <label>Schema（可选，JSON 格式）</label>
          <textarea v-model="extractionSchema" rows="4" style="width:100%;padding:8px;font-family:monospace;font-size:12px" placeholder='{"type":"object","properties":{"title":{"type":"string"}}}"></textarea>
        </div>
      </div>
    </div>

    <!-- ── Step 2: Request ── -->
    <div v-show="activeStep === 2" class="step-panel">
      <div class="form-group">
        <label>HTTP 方法</label>
        <select v-model="reqMethod" style="width:100%;padding:8px">
          <option value="GET">GET</option>
          <option value="POST">POST</option>
        </select>
      </div>
      <div class="form-group">
        <label>请求头（每行一个，格式: Key: Value）</label>
        <textarea v-model="reqHeaders" rows="4" style="width:100%;font-family:monospace;font-size:13px;padding:8px" placeholder="User-Agent: Mozilla/5.0&#10;Content-Type: application/json"></textarea>
      </div>
      <div class="form-group">
        <label>POST Body 模板（支持 {变量名} 占位）</label>
        <textarea v-model="bodyTemplate" rows="4" style="width:100%;font-family:monospace;font-size:13px;padding:8px" placeholder="searchkey={keyword}&sdate=&edate="></textarea>
      </div>
      <div class="form-group">
        <label>变量参数（每行一个，格式: 变量名: 值）</label>
        <textarea v-model="reqParams" rows="3" style="width:100%;font-family:monospace;font-size:13px;padding:8px" placeholder="keyword: 数据要素"></textarea>
      </div>
    </div>

    <!-- ── Step 3: List extraction ── -->
    <div v-show="activeStep === 3" class="step-panel">
      <div class="form-group">
        <label>列表项选择器（items_path） <span class="required">*</span></label>
        <input v-model="itemsPath" placeholder="css:.item  或  xpath://div[@class='item']  或  regex:..." style="width:100%;padding:8px;font-family:monospace" />
        <small style="color:#888">格式: css:&lt;selector&gt; | xpath:&lt;expr&gt; | regex:&lt;pattern&gt;</small>
      </div>
      <div class="section-divider">字段定义</div>
      <div v-for="(field, i) in fields" :key="i" class="field-row">
        <div class="field-row-header">
          <span style="font-weight:bold">字段 {{ i + 1 }}</span>
          <button @click="removeField(i)" class="btn-sm btn-danger">删除</button>
        </div>
        <div class="form-row" style="align-items:flex-end">
          <div class="form-group" style="flex:1">
            <label>字段名</label>
            <input v-model="field.name" placeholder="例如: title" style="width:100%;padding:6px" />
          </div>
          <div class="form-group" style="flex:1">
            <label>类型</label>
            <select v-model="field.type" style="width:100%;padding:6px">
              <option v-for="ft in fieldTypes" :key="ft" :value="ft">{{ ft }}</option>
            </select>
          </div>
        </div>
        <div v-if="field.type === 'field'" class="form-group">
          <label>JSONPath 路径（如 $.title）</label>
          <input v-model="field.path" placeholder="$.announcementTitle" style="width:100%;padding:6px;font-family:monospace" />
        </div>
        <div v-if="field.type === 'attr'" class="form-row">
          <div class="form-group" style="flex:1">
            <label>XPath</label>
            <input v-model="field.path" placeholder="xpath://div[@class='img']//img" style="width:100%;padding:6px;font-family:monospace" />
          </div>
          <div class="form-group" style="flex:1">
            <label>属性名</label>
            <input v-model="field.attr" placeholder="src" style="width:100%;padding:6px" />
          </div>
        </div>
        <div v-if="field.type === 'xpath'" class="form-group">
          <label>XPath</label>
          <input v-model="field.path" placeholder="xpath://div[@class='content']//text()" style="width:100%;padding:6px;font-family:monospace" />
        </div>
        <div v-if="field.type === 'constant'">
          <label>固定值</label>
          <input v-model="field.value" placeholder="固定值" style="width:100%;padding:6px" />
        </div>
        <div v-if="field.type === 'computed'">
          <label>模板字符串（可用 {变量名}）</label>
          <input v-model="field.value" placeholder="https://example.com/id/{id}" style="width:100%;padding:6px;font-family:monospace" />
        </div>
        <div v-if="field.type === 'field' || field.type === 'attr'" class="form-group">
          <label>变换函数（可选）</label>
          <input v-model="field.transform" placeholder="strip_html, trim" style="width:100%;padding:6px" />
          <small style="color:#888">可选: strip_html | trim | timestamp_ms_to_iso</small>
        </div>
      </div>
      <button @click="addField" class="btn-sm" style="margin-top:8px">+ 添加字段</button>
    </div>

    <!-- ── Step 4: Render ── -->
    <div v-show="activeStep === 4" class="step-panel">
      <div class="form-group">
        <label><input type="checkbox" v-model="renderEnabled" /> 启用浏览器渲染（render.enabled）</label>
        <small style="color:#888;display:block">当 source.type=browser 或 client=browser/crawl4ai 时，渲染配置自动生效</small>
      </div>
      <div class="form-row">
        <div class="form-group" style="flex:1">
          <label>headless</label>
          <select v-model="headless" style="width:100%;padding:8px">
            <option :value="true">true — 无头模式</option>
            <option :value="false">false — 显示浏览器窗口</option>
          </select>
        </div>
        <div class="form-group" style="flex:1">
          <label>stealth（反爬规避）</label>
          <select v-model="stealth" style="width:100%;padding:8px">
            <option :value="true">true — 启用</option>
            <option :value="false">false — 关闭</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <label>wait_for_selector（等待元素出现）</label>
        <input v-model="waitForSelector" placeholder=".main-content 或 article" style="width:100%;padding:8px" />
      </div>
      <div class="form-row">
        <div class="form-group" style="flex:1">
          <label>wait_for_timeout（ms）</label>
          <input type="number" v-model="waitForTimeout" style="width:100%;padding:8px" />
        </div>
        <div class="form-group" style="flex:1">
          <label>视口宽度</label>
          <input type="number" v-model="viewportWidth" style="width:100%;padding:8px" />
        </div>
        <div class="form-group" style="flex:1">
          <label>视口高度</label>
          <input type="number" v-model="viewportHeight" style="width:100%;padding:8px" />
        </div>
      </div>
      <div v-if="client === 'crawl4ai'" class="section-divider">Crawl4AI 专用配置</div>
      <div v-if="client === 'crawl4ai'" class="form-row">
        <div class="form-group" style="flex:1">
          <label><input type="checkbox" v-model="markdown" /> markdown（返回 Markdown 而非 HTML）</label>
        </div>
        <div class="form-group" style="flex:1">
          <label><input type="checkbox" v-model="removeForms" /> remove_forms（移除表单元素）</label>
        </div>
      </div>
    </div>

    <!-- ── Step 5: Pagination / Dedup ── -->
    <div v-show="activeStep === 5" class="step-panel">
      <div class="section-divider">分页配置（仅 API 类型）</div>
      <div class="form-group">
        <label><input type="checkbox" v-model="paginationEnabled" /> 启用分页</label>
      </div>
      <div v-if="paginationEnabled" class="form-row">
        <div class="form-group" style="flex:1">
          <label>页码参数名</label>
          <input v-model="pageParam" placeholder="pageNum" style="width:100%;padding:8px" />
        </div>
        <div class="form-group" style="flex:1">
          <label>最大页数</label>
          <input type="number" v-model="maxPages" style="width:100%;padding:8px" />
        </div>
      </div>
      <div class="section-divider">去重配置</div>
      <div class="form-group">
        <label><input type="checkbox" v-model="dedupIncremental" /> 启用增量去重</label>
        <small style="color:#888;display:block">开启后相同 requirement+platform+raw_id 的数据会被自动过滤</small>
      </div>
      <div class="form-group">
        <label>url_to_id_pattern（从 URL 提取 raw_id 的正则）</label>
        <input v-model="urlToIdPattern" placeholder="example\\.com/article/(\\d+)" style="width:100%;padding:8px;font-family:monospace" />
        <small style="color:#888">使用捕获组 () 提取 ID 部分，如 tmtpost\\.com/(\\d+)\\.html</small>
      </div>
    </div>

    <!-- ── Step 6: Output / Schedule ── -->
    <div v-show="activeStep === 6" class="step-panel">
      <div class="section-divider">输出配置</div>
      <div class="form-group">
        <label>文件名模板</label>
        <input v-model="outputFilename" placeholder="data_{date}.json" style="width:100%;padding:8px" />
        <small style="color:#888">{date} 会替换为今天的日期 YYYYMMDD</small>
      </div>
      <div class="form-group">
        <label>自定义输出路径（可选，留空使用默认路径 engine/data/{subject}/{platform}/）</label>
        <input v-model="outputPath" placeholder="engine/data/数据要素/cninfo" style="width:100%;padding:8px" />
      </div>
      <div class="section-divider">调度配置（看板 APScheduler）</div>
      <div class="form-group">
        <label>Cron 表达式</label>
        <input v-model="scheduleCron" placeholder="0 8 * * *" style="width:100%;padding:8px" />
        <small style="color:#888">格式: 分 时 日 月 周，例如 0 8 * * * = 每天 8:00 执行</small>
      </div>
    </div>

    <!-- ── YAML Raw Editor ── -->
    <div class="yaml-toggle">
      <label @click="showYaml = !showYaml" style="cursor:pointer">
        <input type="checkbox" v-model="showYaml" /> 直接编辑 YAML（覆盖表单）
      </label>
    </div>
    <div v-if="showYaml" class="form-group">
      <textarea v-model="yaml" rows="20" style="width:100%;font-family:monospace;font-size:13px;padding:8px"></textarea>
    </div>

    <div v-if="message" :class="['msg', message.includes('成功') ? 'success' : 'error']">{{ message }}</div>

    <!-- Navigation -->
    <div class="step-nav">
      <button @click="prevStep" class="btn-sm" :disabled="activeStep === 0">上一步</button>
      <span style="color:#888;font-size:13px">步骤 {{ activeStep + 1 }} / {{ steps.length }}</span>
      <button @click="nextStep" class="btn-sm" :disabled="activeStep === steps.length - 1">下一步</button>
      <button @click="save" class="btn-primary btn-lg" :disabled="saving" style="margin-left:auto">
        {{ saving ? '保存中...' : '保存规则' }}
      </button>
    </div>
  </div>
</div>
    `
};

// ── DataHashRouter ────────────────────────────────────────────────────────────
const DataHashRouter = {
    setup() {
        const route = ref(window.location.hash || '#/data');
        const routeSubject = ref('');

        const parseHash = () => {
            const hash = window.location.hash;
            route.value = hash || '#/data';
            if (hash.startsWith('#/data/')) {
                routeSubject.value = decodeURIComponent(hash.slice('#/data/'.length));
            } else {
                routeSubject.value = '';
            }
        };

        const navigate = (path) => {
            window.location.hash = path;
        };

        onMounted(() => {
            parseHash();
            window.addEventListener('hashchange', parseHash);
        });

        onUnmounted(() => {
            window.removeEventListener('hashchange', parseHash);
        });

        return { route, routeSubject, navigate };
    },
    template: `
<component :is="route === '#/data' || route === '#/data/' ? 'DataSubjectList' : 'DataSubjectDetail'"
    :subject="routeSubject" />
    `
};

// ── DataSubjectList ───────────────────────────────────────────────────────────
const DataSubjectList = {
    setup() {
        const summary = ref([]);
        const loading = ref(false);

        const loadSummary = async () => {
            loading.value = true;
            try {
                const data = await API.get('/data/summary');
                summary.value = data || [];
            } catch (err) { console.error(err); } finally {
                loading.value = false;
            }
        };

        const totalForSubject = (s) => {
            return s.platforms.reduce((acc, p) => acc + (p.count || 0), 0);
        };

        const goDetail = (subject) => {
            window.location.hash = '#/data/' + encodeURIComponent(subject);
        };

        onMounted(loadSummary);

        return { summary, loading, totalForSubject, goDetail };
    },
    template: `
<div class="dp-detail">
  <div class="dp-card">
    <div class="dp-detail-header">
      <h2 class="dp-subject-title">📊 数据预览</h2>
    </div>

    <div v-if="loading" class="dp-loading">
      <div class="dp-loading-spinner"></div>
      <span>加载中...</span>
    </div>
    <div v-else-if="summary.length === 0" class="dp-empty">
      <div class="dp-empty-icon">📭</div>
      <div>暂无数据</div>
    </div>
    <div v-else>
      <div class="dp-subject-grid">
        <div v-for="s in summary" :key="s.subject" class="dp-subject-card" @click="goDetail(s.subject)">
          <div class="dp-subject-card-name">{{ s.subject }}</div>
          <div class="dp-subject-card-meta">
            <span class="dp-subject-card-total">{{ totalForSubject(s) }}</span>
            <span class="dp-subject-card-sources">{{ s.platforms.length }} 个来源</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
    `,
};

// ── DataSubjectDetail ─────────────────────────────────────────────────────────
const DataSubjectDetail = {
    props: ['subject'],
    setup(props) {
        const items = ref([]);
        const total = ref(0);
        const loading = ref(false);
        const expandedItem = ref(null);
        const searchQuery = ref('');
        const currentPage = ref(1);
        const pageSize = 50;

        const loadData = async () => {
            loading.value = true;
            try {
                const data = await API.get(`/data/preview?subject=${encodeURIComponent(props.subject)}&page=${currentPage.value}&page_size=${pageSize}`);
                items.value = data.items || [];
                total.value = data.total || 0;
            } catch (err) { console.error(err); } finally {
                loading.value = false;
            }
        };

        const filteredItems = computed(() => {
            if (!searchQuery.value) return items.value;
            const q = searchQuery.value.toLowerCase();
            return items.value.filter(item =>
                (item.title && item.title.toLowerCase().includes(q)) ||
                (item.platform && item.platform.toLowerCase().includes(q)) ||
                (item._source_file && item._source_file.toLowerCase().includes(q))
            );
        });

        const toggleExpand = (item) => {
            expandedItem.value = expandedItem.value === item ? null : item;
        };

        const totalPages = computed(() => Math.ceil(total.value / pageSize));

        const prevPage = () => {
            if (currentPage.value > 1) {
                currentPage.value--;
            }
        };

        const nextPage = () => {
            if (currentPage.value < totalPages.value) {
                currentPage.value++;
            }
        };

        watch([() => props.subject, currentPage], loadData);
        onMounted(loadData);

        return { items, total, loading, expandedItem, searchQuery, currentPage, pageSize, filteredItems, toggleExpand, totalPages, prevPage, nextPage };
    },
    template: `
<div class="dp-detail">
  <div class="dp-card">
    <div class="dp-detail-header">
      <button class="dp-back-btn" @click.prevent="history.back()">← 返回</button>
      <h2 class="dp-subject-title">{{ subject }}</h2>
      <span class="dp-stat-badge">共 <strong>{{ total }}</strong> 条</span>
    </div>

    <div class="dp-search-wrap">
      <input v-model="searchQuery" type="search" class="dp-search-input" placeholder="搜索标题、来源..." />
    </div>

    <div v-if="loading" class="dp-loading">
      <div class="dp-loading-spinner"></div>
      <span>加载中...</span>
    </div>
    <div v-else-if="filteredItems.length === 0" class="dp-empty">
      <div class="dp-empty-icon">📭</div>
      <div>暂无数据</div>
    </div>
    <div v-else>
      <div class="dp-table-wrap">
        <table class="dp-table">
          <thead>
            <tr>
              <th>来源</th>
              <th>标题</th>
              <th>时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(item, i) in filteredItems" :key="i">
              <tr>
                <td><span class="dp-platform-tag">{{ item.platform || '-' }}</span></td>
                <td class="dp-title-cell">{{ item.title || '-' }}</td>
                <td class="dp-time-cell">{{ item.publish_time || item.time || '-' }}</td>
                <td>
                  <button class="dp-action-btn" @click="toggleExpand(item)">
                    {{ expandedItem === item ? '收起' : '展开' }}
                  </button>
                </td>
              </tr>
              <tr v-if="expandedItem === item" class="dp-expand-row">
                <td colspan="4">
                  <div class="dp-expand-content">
                    <pre>{{ JSON.stringify(item, null, 2) }}</pre>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div class="dp-pagination">
        <span class="dp-pagination-info">共 {{ total }} 条，第 {{ currentPage }} / {{ totalPages }} 页</span>
        <div class="dp-pagination-controls">
          <button class="dp-page-btn" :disabled="currentPage <= 1" @click="prevPage">上一页</button>
          <span class="dp-page-current">{{ currentPage }} / {{ totalPages }}</span>
          <button class="dp-page-btn" :disabled="currentPage >= totalPages" @click="nextPage">下一页</button>
        </div>
      </div>
    </div>
  </div>
</div>
    `
};

// ── Main App ──────────────────────────────────────────────────────────────────
const app = createApp({
    setup() {
        const tabs = [
            { id: "home", label: "📊 首页", component: "DashboardHome" },
            { id: "rules", label: "规则管理", component: "RuleList" },
            { id: "cron", label: "Cron调度", component: "CronManager" },
            { id: "tasks", label: "任务执行", component: "TaskRunner" },
            { id: "logs", label: "日志查看", component: "LogViewer" },
            { id: "data", label: "数据预览", component: "DataHashRouter" },
        ];

        const currentTab = ref("home");
        const editRuleData = ref(null);

        const currentComponent = computed(() => {
            const tab = tabs.find(t => t.id === currentTab.value);
            return tab ? tab.component : "DashboardHome";
        });

        const handleSwitchTab = (tabId) => { currentTab.value = tabId; };
        const handleEditRule = (data) => { editRuleData.value = data; };

        return { tabs, currentTab, currentComponent, editRuleData, handleSwitchTab, handleEditRule };
    },
    methods: {
        onSwitchTab(tabId) { this.currentTab = tabId; },
        onEditRule(data) { this.editRuleData = data; }
    }
});

app.component("DashboardHome", DashboardHome);
app.component("RuleList", RuleList);
app.component("CronManager", CronManager);
app.component("TaskRunner", TaskRunner);
app.component("LogViewer", LogViewer);
app.component("DataHashRouter", DataHashRouter);
app.component("DataSubjectList", DataSubjectList);
app.component("DataSubjectDetail", DataSubjectDetail);
app.component("RuleEditor", RuleEditor);

app.mount("#app");
