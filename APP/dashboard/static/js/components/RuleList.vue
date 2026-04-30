<template>
<div class="rule-list">
  <div class="toolbar">
    <button @click="loadRules" class="btn-primary">刷新</button>
    <button @click="createRule" class="btn-primary">新建规则</button>
    <span class="rule-count">{{ rules.length }} 条规则</span>
  </div>

  <table class="data-table">
    <thead>
      <tr>
        <th>名称</th>
        <th>平台</th>
        <th>主题</th>
        <th>状态</th>
        <th>最近运行</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="rule in rules" :key="rule.path">
        <td>{{ rule.name }}</td>
        <td>{{ rule.platform }}</td>
        <td>{{ rule.subject }}</td>
        <td>
          <span :class="['status-badge', rule.enabled ? 'on' : 'off']">
            {{ rule.enabled ? 'ON' : 'OFF' }}
          </span>
        </td>
        <td>{{ rule.last_run || '-' }}</td>
        <td>
          <button @click="toggleRule(rule)" class="btn-sm" :title="rule.enabled ? '停用' : '启用'">
            {{ rule.enabled ? '停用' : '启用' }}
          </button>
          <button @click="runRule(rule)" class="btn-sm" title="立即执行">执行</button>
          <button @click="editRule(rule)" class="btn-sm" title="编辑">编辑</button>
          <button @click="deleteRule(rule)" class="btn-sm btn-danger" title="删除">删除</button>
        </td>
      </tr>
    </tbody>
  </table>

  <!-- Run Result Dialog -->
  <div v-if="showRunDialog" class="dialog-overlay" @click.self="showRunDialog = false">
    <div class="dialog">
      <h3>执行结果</h3>
      <div v-if="runResult">
        <p>状态: {{ runResult.success ? '✅ 成功' : '❌ 失败' }}</p>
        <p>新增数据: {{ runResult.new_count ?? runResult.newCount ?? '-' }} 条</p>
        <p>耗时: {{ runResult.duration ?? runResultDuration ?? '-' }} 秒</p>
        <p v-if="runResult.error" class="error-msg">{{ runResult.error }}</p>
      </div>
      <div v-else>
        <p>加载中...</p>
      </div>
      <div style="margin-top: 16px; text-align: right;">
        <button @click="showRunDialog = false" class="btn-primary">关闭</button>
      </div>
    </div>
  </div>
</div>
</template>

<script>
const { ref, onMounted } = Vue;

const RuleList = {
  emits: ['switch-tab', 'edit-rule'],
  setup(props, { emit }) {
    const rules = ref([]);
    const showRunDialog = ref(false);
    const runResult = ref(null);
    const runResultDuration = ref(null);

    const loadRules = async () => {
      try {
        const resp = await fetch('/api/rules');
        if (!resp.ok) throw new Error('Failed to load rules');
        const data = await resp.json();
        rules.value = data.rules || [];
      } catch (err) {
        console.error('loadRules error:', err);
        alert('加载规则失败: ' + err.message);
      }
    };

    const toggleRule = async (rule) => {
      try {
        const enabled = !rule.enabled;
        const resp = await fetch(`/api/rules/${encodeURIComponent(rule.path)}/toggle`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled }),
        });
        if (!resp.ok) throw new Error('Failed to toggle rule');
        const data = await resp.json();
        // Update local state
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
      try {
        const resp = await fetch(`/api/rules/${encodeURIComponent(rule.path)}/run`, {
          method: 'POST',
        });
        const data = await resp.json();
        runResult.value = data;
        if (data.duration !== undefined) {
          runResultDuration.value = data.duration;
        }
      } catch (err) {
        console.error('runRule error:', err);
        runResult.value = { success: false, error: err.message };
      }
    };

    const editRule = async (rule) => {
      try {
        const resp = await fetch(`/api/rules/${encodeURIComponent(rule.path)}`);
        if (!resp.ok) throw new Error('Failed to load rule');
        const data = await resp.json();
        // Emit to parent to switch to rule-editor tab
        // Use emits equivalent in setup
        emit('switch-tab', 'rule-editor');
        emit('edit-rule', { rule, yaml: data.yaml });
      } catch (err) {
        console.error('editRule error:', err);
        alert('加载规则失败: ' + err.message);
      }
    };

    const createRule = () => {
      // Emit to parent to switch to rule-editor tab for new rule
      emit('switch-tab', 'rule-editor');
      emit('edit-rule', { rule: null, yaml: '' });
    };

    const deleteRule = async (rule) => {
      if (!confirm(`确定要删除规则 "${rule.name}" 吗？此操作不可恢复。`)) {
        return;
      }
      try {
        const resp = await fetch(`/api/rules/${encodeURIComponent(rule.path)}`, {
          method: 'DELETE',
        });
        if (!resp.ok) throw new Error('Failed to delete rule');
        // Reload rules
        await loadRules();
      } catch (err) {
        console.error('deleteRule error:', err);
        alert('删除规则失败: ' + err.message);
      }
    };

    onMounted(() => {
      loadRules();
    });

    return {
      rules,
      showRunDialog,
      runResult,
      runResultDuration,
      loadRules,
      toggleRule,
      runRule,
      editRule,
      createRule,
      deleteRule,
    };
  },
  emits: ['switch-tab', 'edit-rule'],
};

export default RuleList;
</script>

<style scoped>
.rule-list {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 16px;
}

.rule-count {
  margin-left: auto;
  color: #666;
  font-size: 13px;
}

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.status-badge.on {
  background: #e6f7ff;
  color: #1890ff;
}

.status-badge.off {
  background: #f5f5f5;
  color: #999;
}

.error-msg {
  color: #ff4d4f;
  margin-top: 8px;
}
</style>
