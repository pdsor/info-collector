const { createApp, ref, computed, onMounted } = Vue;

// 临时空组件（Phase 2/3 填充）
const DashboardHome = { 
    template: "<div class='card'><h2>首页</h2><p>统计数据加载中...</p></div>" 
};
const RuleList = { 
    template: "<div class='card'><h2>规则管理</h2><p>规则列表加载中...</p></div>" 
};
const CronManager = { 
    template: "<div class='card'><h2>Cron 调度</h2><p>Cron 管理加载中...</p></div>" 
};
const TaskRunner = { 
    template: "<div class='card'><h2>任务执行</h2><p>任务执行加载中...</p></div>" 
};
const LogViewer = { 
    template: "<div class='card'><h2>日志查看</h2><p>日志查看加载中...</p></div>" 
};
const DataPreview = { 
    template: "<div class='card'><h2>数据预览</h2><p>数据预览加载中...</p></div>" 
};

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
        
        const currentComponent = computed(() => {
            const tab = tabs.find(t => t.id === currentTab.value);
            return tab ? tab.component : "DashboardHome";
        });
        
        return { tabs, currentTab, currentComponent };
    }
});

app.component("DashboardHome", DashboardHome);
app.component("RuleList", RuleList);
app.component("CronManager", CronManager);
app.component("TaskRunner", TaskRunner);
app.component("LogViewer", LogViewer);
app.component("DataPreview", DataPreview);

app.mount("#app");
