const { createApp, ref, computed, onMounted, onUnmounted } = Vue;

// ── API Helper ────────────────────────────────────────────────────────────────
const API = {
    base: "/api",

    async get(path) {
        const r = await fetch(this.base + path);
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },

    async post(path, body) {
        const r = await fetch(this.base + path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },

    async delete(path) {
        const r = await fetch(this.base + path, { method: "DELETE" });
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },

    sse(url, handlers) {
        const es = new EventSource(url);
        // 普通消息（data: xxx，无 event: name）
        es.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                // 忽略心跳（由专门监听器处理）
                if (data.type === 'heartbeat') return;
                handlers.onData?.(data);
            } catch {}
        };
        // 命名事件：done（任务结束）
        es.addEventListener('done', (e) => {
            try {
                const data = JSON.parse(e.data);
                handlers.onData?.(data);  // data.type === 'done'
            } catch {}
        });
        es.onerror = (e) => { handlers.onError?.(e); };
        return es;
    }
};

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
            for (const subject of Object.values(stats.value)) {
                for (const count of Object.values(subject)) {
                    total += count;
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
          <span v-for="(count, platform) in platforms" :key="platform" class="platform-tag">
            {{ platform }}: {{ count }}
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
        const rulePath = ref(props.editRuleData?.rule?.path || '');
        const name = ref(props.editRuleData?.rule?.name || '');
        const subject = ref(props.editRuleData?.rule?.subject || '');
        const platform = ref(props.editRuleData?.rule?.platform || '');
        const isNew = computed(() => !props.editRuleData?.rule);
        const saving = ref(false);
        const message = ref('');

        const save = async () => {
            if (!name.value || !subject.value || !platform.value) {
                message.value = '请填写名称、主题和平台';
                return;
            }
            const path = `rules/${subject.value}/${platform.value}_${name.value.replace(/\s+/g, '_')}.yaml`;
            saving.value = true;
            message.value = '';
            try {
                const fullYaml = yaml.value || generateSkeleton();
                await API.post('/rules', { path, yaml: fullYaml });
                message.value = '保存成功';
                setTimeout(() => emit('switch-tab', 'rules'), 1000);
            } catch (err) {
                message.value = '保存失败: ' + err.message;
            } finally {
                saving.value = false;
            }
        };

        const generateSkeleton = () => {
            return `source:
  name: "${name.value}"
  platform: ${platform.value}
  subject: ${subject.value}
  enabled: true

platform:
  type: generic
  # 在此填写平台配置

trigger:
  type: schedule
  interval: 3600

fields:
  - name: title
    type: string
  - name: url
    type: string
  - name: published_at
    type: datetime
`;
        };

        return { yaml, rulePath, name, subject, platform, isNew, saving, message, save };
    },
    template: `
<div class="rule-editor">
  <div class="card">
    <h2>{{ isNew ? '➕ 新建规则' : '✏️ 编辑规则' }}</h2>

    <div class="form-group">
      <label>规则名称</label>
      <input v-model="name" placeholder="例如: 公告抓取" style="width:100%;padding:8px" />
    </div>

    <div class="form-row">
      <div class="form-group" style="flex:1">
        <label>主题</label>
        <input v-model="subject" placeholder="例如: 数据要素" style="width:100%;padding:8px" />
      </div>
      <div class="form-group" style="flex:1">
        <label>平台</label>
        <input v-model="platform" placeholder="例如: cninfo" style="width:100%;padding:8px" />
      </div>
    </div>

    <div class="form-group">
      <label>YAML 内容</label>
      <textarea v-model="yaml" rows="20" style="width:100%;font-family:monospace;font-size:13px;padding:8px" placeholder="在此填写 YAML 规则内容，或留空点击保存自动生成框架"></textarea>
    </div>

    <div v-if="message" :class="['msg', message.includes('成功') ? 'success' : 'error']">{{ message }}</div>

    <div class="toolbar">
      <button @click="save" class="btn-primary btn-lg" :disabled="saving">
        {{ saving ? '保存中...' : '保存规则' }}
      </button>
    </div>
  </div>
</div>
    `
};

// ── DataPreview ──────────────────────────────────────────────────────────────
const DataPreview = {
    setup() {
        const subjects = ref([]);
        const platforms = ref([]);
        const selectedSubject = ref('');
        const selectedPlatform = ref('');
        const items = ref([]);
        const total = ref(0);
        const loading = ref(false);
        const expandedItem = ref(null);

        const loadSubjects = async () => {
            try {
                const data = await API.get('/data/subjects');
                subjects.value = data.subjects || [];
            } catch (err) { console.error(err); }
        };

        const loadPlatforms = async () => {
            if (!selectedSubject.value) return;
            try {
                const data = await API.get(`/data/platforms?subject=${encodeURIComponent(selectedSubject.value)}`);
                platforms.value = data.platforms || [];
            } catch (err) { console.error(err); }
        };

        const loadData = async () => {
            if (!selectedSubject.value || !selectedPlatform.value) return;
            loading.value = true;
            try {
                const data = await API.get(`/data/preview?subject=${encodeURIComponent(selectedSubject.value)}&platform=${encodeURIComponent(selectedPlatform.value)}`);
                items.value = data.items || [];
                total.value = data.total || 0;
            } catch (err) { console.error(err); } finally {
                loading.value = false;
            }
        };

        const toggleExpand = (item) => {
            expandedItem.value = expandedItem.value === item ? null : item;
        };

        watch(selectedSubject, loadPlatforms);
        watch([selectedSubject, selectedPlatform], loadData);

        onMounted(loadSubjects);

        return { subjects, platforms, selectedSubject, selectedPlatform, items, total, loading, expandedItem, toggleExpand };
    },
    template: `
<div class="data-preview">
  <div class="card">
    <h2>🔍 数据预览</h2>
    <div class="form-row">
      <div class="form-group" style="flex:1">
        <label>主题</label>
        <select v-model="selectedSubject" style="width:100%;padding:8px">
          <option value="">-- 选择主题 --</option>
          <option v-for="s in subjects" :key="s" :value="s">{{ s }}</option>
        </select>
      </div>
      <div class="form-group" style="flex:1">
        <label>平台</label>
        <select v-model="selectedPlatform" style="width:100%;padding:8px" :disabled="!selectedSubject">
          <option value="">-- 选择平台 --</option>
          <option v-for="p in platforms" :key="p" :value="p">{{ p }}</option>
        </select>
      </div>
    </div>

    <div v-if="selectedSubject && selectedPlatform" class="data-info">
      共 <strong>{{ total }}</strong> 条记录，显示前 {{ items.length }} 条
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="items.length === 0 && (selectedSubject && selectedPlatform)" class="empty">暂无数据</div>
    <div v-else>
      <div v-for="(item, i) in items" :key="i" class="data-item">
        <div class="data-item-header" @click="toggleExpand(item)">
          <span class="expand-icon">{{ expandedItem === item ? '▼' : '▶' }}</span>
          <span v-for="(v, k) in Object.entries(item).slice(0, 4)" :key="k" class="data-chip">
            <strong>{{ k }}:</strong> {{ v }}
          </span>
        </div>
        <div v-if="expandedItem === item" class="data-item-detail">
          <pre>{{ JSON.stringify(item, null, 2) }}</pre>
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
            { id: "data", label: "数据预览", component: "DataPreview" },
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
app.component("DataPreview", DataPreview);
app.component("RuleEditor", RuleEditor);

app.mount("#app");
