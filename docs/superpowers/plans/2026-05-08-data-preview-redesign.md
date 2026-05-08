# 数据预览模块改版实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将数据预览从「主题+平台二级下拉」改为「主题列表页 → 主题详情页」模式，支持主题内跨来源搜索和原始 JSON 展开。

**架构：** 后端新增 `summary` 接口并改造 `preview` 接口（platform 可选）；前端用 hash 路由（`#/data`、`#/data/:subject`）切换列表/详情组件，替换现有 DataPreview 组件。

**技术栈：** Flask（Python）、Vue 3 CDN（Vanilla JS）、SQLite、Vanilla HTML/CSS

---

## 文件结构

```
APP/dashboard/apis/data_api.py     # 修改：新增 summary 接口，改造 preview（platform 可选）
APP/dashboard/static/js/app.js     # 修改：替换 DataPreview，新增 DataSubjectList + DataSubjectDetail，hash 路由
APP/dashboard/static/css/style.css # 修改：新增列表页和详情页样式
```

---

## 任务 1：后端 — 新增 summary 接口

**文件：** `APP/dashboard/apis/data_api.py:106-121`

- [ ] **步骤 1：在 `data_api.py` 末尾新增 `/summary` 接口**

在 `data_api.py` 约第 106 行（`list_subjects` 之后）添加：

```python
@data_bp.route("/summary", methods=["GET"])
def data_summary():
    """GET /api/data/summary — 主题摘要，供列表页使用"""
    engine_data = _get_data_dir()
    if not os.path.exists(engine_data):
        return jsonify([])

    result = []
    try:
        for subject in sorted(os.listdir(engine_data)):
            s_path = os.path.join(engine_data, subject)
            if not os.path.isdir(s_path):
                continue
            platforms = []
            total = 0
            try:
                for platform in sorted(os.listdir(s_path)):
                    p_path = os.path.join(s_path, platform)
                    if not os.path.isdir(p_path):
                        continue
                    json_files = glob.glob(os.path.join(p_path, "*.json"))
                    json_files = [f for f in json_files if not os.path.basename(f).startswith("combined")]
                    latest_file = max(json_files) if json_files else None
                    count = _count_items_in_file(latest_file) if latest_file else 0
                    total += count
                    platforms.append({
                        "name": platform,
                        "count": count,
                        "latest_file": os.path.basename(latest_file) if latest_file else None,
                    })
            except OSError:
                platforms = []
            result.append({
                "subject": subject,
                "platforms": platforms,
                "total": total,
            })
    except OSError:
        pass
    return jsonify(result)
```

- [ ] **步骤 2：验证接口**

```bash
curl -s "http://localhost:5000/api/data/summary" | python3 -m json.tool
```

预期：返回 `[{subject, platforms: [{name, count, latest_file}], total}]` 结构

- [ ] **步骤 3：commit**

```bash
git add APP/dashboard/apis/data_api.py && git commit -m "feat(data_api): add /api/data/summary endpoint"
```

---

## 任务 2：后端 — preview 接口支持空 platform

**文件：** `APP/dashboard/apis/data_api.py:147-170`

- [ ] **步骤 1：修改 `preview_data` 函数，使 platform 可选**

找到现有 `preview_data` 函数（约第 147-170 行），替换为以下逻辑：

```python
@data_bp.route("/preview", methods=["GET"])
def preview_data():
    """GET /api/data/preview?subject=xxx&platform=xxx&limit=10&page=1&page_size=50
    platform 为空时返回该主题下所有来源数据（跨平台合并）"""
    subject = request.args.get("subject", "")
    platform = request.args.get("platform", "")
    limit = min(int(request.args.get("limit", 100)), 200)
    page = max(int(request.args.get("page", 1)), 1)
    page_size = min(int(request.args.get("page_size", 50)), 100)
    offset = (page - 1) * page_size

    if not subject:
        return jsonify({"error": "subject required"}), 400

    engine_data = _get_data_dir()

    # 收集所有匹配的 json 文件
    subject_dir = os.path.join(engine_data, subject)
    if not os.path.exists(subject_dir):
        return jsonify({"error": "Subject not found"}), 404

    json_files = []
    if platform:
        p_path = os.path.join(subject_dir, platform)
        if os.path.isdir(p_path):
            json_files = glob.glob(os.path.join(p_path, "*.json"))
    else:
        for p in os.listdir(subject_dir):
            p_path = os.path.join(subject_dir, p)
            if os.path.isdir(p_path):
                json_files.extend(glob.glob(os.path.join(p_path, "*.json")))

    json_files = [f for f in json_files if not os.path.basename(f).startswith("combined")]
    if not json_files:
        return jsonify({"items": [], "total": 0, "page": page, "page_size": page_size})

    latest_files = sorted(json_files, key=lambda f: os.path.basename(f), reverse=True)[:5]
    all_items = []
    for f in latest_files:
        items, _ = _load_items_from_file(f, limit=None)
        for item in items:
            item["_source_file"] = os.path.basename(f)
        all_items.extend(items)

    total = len(all_items)
    paginated = all_items[offset:offset + page_size]

    return jsonify({
        "items": paginated,
        "total": total,
        "page": page,
        "page_size": page_size,
        "platform": platform or "all",
    })
```

- [ ] **步骤 2：验证接口（platform=all）**

```bash
curl -s "http://localhost:5000/api/data/preview?subject=数据要素" | python3 -c "import sys,json; d=json.load(sys.stdin); print('total:', d.get('total'), 'count:', len(d.get('items',[])), 'page:', d.get('page'))"
```

预期：`total > 0`，`count` 等于 `page_size` 或更少

- [ ] **步骤 3：commit**

```bash
git add APP/dashboard/apis/data_api.py && git commit -m "feat(data_api): preview supports no platform, returns all sources in subject"
```

---

## 任务 3：前端 — 替换 DataPreview 组件（主题列表 + hash 路由）

**文件：** `APP/dashboard/static/js/app.js:1177-1270`

- [ ] **步骤 1：替换 DataPreview 组件，实现 hash 路由**

找到 `// ── DataPreview ──────────────────────────────────────────────────────────────`（约第 1177 行）到文件末尾，替换为：

```javascript
// ── Hash Router ─────────────────────────────────────────────────────────────
const DataHashRouter = {
    setup() {
        const route = ref(window.location.hash || '#/data');
        const routeSubject = ref('');

        const updateRoute = () => {
            const hash = window.location.hash || '#/data';
            route.value = hash;
            const match = hash.match(/^#\/data\/(.+)$/);
            routeSubject.value = match ? decodeURIComponent(match[1]) : '';
        };

        onMounted(() => {
            window.addEventListener('hashchange', updateRoute);
            updateRoute();
        });

        onUnmounted(() => {
            window.removeEventListener('hashchange', updateRoute);
        });

        const navigate = (path) => { window.location.hash = path; };

        return { route, routeSubject, navigate };
    },
    template: `
      <DataSubjectList v-if="route === '#/data'" />
      <DataSubjectDetail v-else-if="route.startsWith('#/data/')" :subject="routeSubject" />
    `
};

// ── DataSubjectList ─────────────────────────────────────────────────────────
const DataSubjectList = {
    setup() {
        const summary = ref([]);
        const loading = ref(false);

        const loadSummary = async () => {
            loading.value = true;
            try {
                const data = await API.get('/data/summary');
                summary.value = data || [];
            } catch (err) {
                console.error(err);
            } finally {
                loading.value = false;
            }
        };

        const totalForSubject = (s) => s.platforms.reduce((acc, p) => acc + (p.count || 0), 0);

        const goDetail = (subject) => {
            window.location.hash = `#/data/${encodeURIComponent(subject)}`;
        };

        onMounted(loadSummary);

        return { summary, loading, totalForSubject, goDetail };
    },
    template: `
<div class="data-subject-list">
  <div class="card">
    <h2>📊 数据预览</h2>
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="summary.length === 0" class="empty">暂无数据</div>
    <table v-else class="data-table">
      <thead>
        <tr><th>主题</th><th>来源数</th><th>总条数</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="s in summary" :key="s.subject">
          <td><strong>{{ s.subject }}</strong></td>
          <td>{{ s.platforms.length }}</td>
          <td>{{ totalForSubject(s) }}</td>
          <td><button class="btn-sm btn-primary" @click="goDetail(s.subject)">详情 →</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
    `
};

// ── DataSubjectDetail ────────────────────────────────────────────────────────
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
                const data = await API.get(
                    `/data/preview?subject=${encodeURIComponent(props.subject)}&page=${currentPage.value}&page_size=${pageSize}`
                );
                items.value = data.items || [];
                total.value = data.total || 0;
            } catch (err) {
                console.error(err);
            } finally {
                loading.value = false;
            }
        };

        const filteredItems = computed(() => {
            if (!searchQuery.value.trim()) return items.value;
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

        const prevPage = () => { if (currentPage.value > 1) currentPage.value--; };
        const nextPage = () => { if (currentPage.value < totalPages.value) currentPage.value++; };

        watch([() => props.subject, currentPage], loadData);
        onMounted(loadData);

        return { items, total, loading, expandedItem, searchQuery,
                 filteredItems, currentPage, totalPages, toggleExpand,
                 prevPage, nextPage };
    },
    template: `
<div class="data-subject-detail">
  <div class="card">
    <div class="detail-header">
      <button class="btn-sm" onclick="window.location.hash='#/data'">← 返回</button>
      <h2 style="margin:0">{{ subject }}</h2>
      <span class="data-info">共 <strong>{{ total }}</strong> 条</span>
    </div>

    <div class="form-group" style="margin:12px 0">
      <input type="text" v-model="searchQuery" placeholder="搜索标题、来源..." style="width:100%;padding:8px">
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="filteredItems.length === 0" class="empty">暂无数据</div>
    <table v-else class="data-table">
      <thead>
        <tr><th>来源</th><th>标题</th><th>时间</th><th>操作</th></tr>
      </thead>
      <tbody>
        <template v-for="(item, i) in filteredItems" :key="i">
          <tr>
            <td><span class="source-tag">{{ item._source_file ? item._source_file.split('_')[0] : '-' }}</span></td>
            <td>{{ item.title || '-' }}</td>
            <td>{{ item.pub_time || item.time || '-' }}</td>
            <td><button class="btn-xs" @click="toggleExpand(item)">{{ expandedItem === item ? '收起' : '展开' }}</button></td>
          </tr>
          <tr v-if="expandedItem === item" class="json-expand-row">
            <td colspan="4"><pre class="json-detail">{{ JSON.stringify(item, null, 2) }}</pre></td>
          </tr>
        </template>
      </tbody>
    </table>

    <div v-if="totalPages > 1" class="pagination">
      <button class="btn-sm" @click="prevPage" :disabled="currentPage === 1">上一页</button>
      <span>{{ currentPage }} / {{ totalPages }}</span>
      <button class="btn-sm" @click="nextPage" :disabled="currentPage === totalPages">下一页</button>
    </div>
  </div>
</div>
    `
};
```

- [ ] **步骤 2：更新注册组件和挂载**

找到 `app.component("DataPreview", DataPreview)`（约第 1308 行），替换为：

```javascript
app.component("DataHashRouter", DataHashRouter);
app.component("DataSubjectList", DataSubjectList);
app.component("DataSubjectDetail", DataSubjectDetail);
```

找到 tabs 中的 `{ id: "data", label: "数据预览", component: "DataPreview" }`（约第 1281 行），替换为：

```javascript
{ id: "data", label: "数据预览", component: "DataHashRouter" },
```

找到主 app 的 `template`（约第 1287 行附近），将 `currentComponent` 的使用改为 `<component :is="currentComponent" />` 的渲染方式，或直接将 `DataPreview` 替换为 `DataHashRouter`。

找到主 app 的 `setup()` 返回值中，确认包含 `handleSwitchTab` 并正确使用。

- [ ] **步骤 3：验证**

访问 `http://localhost:5000`，点击「数据预览」tab，应该看到主题列表（来自 summary 接口）。点击任意主题「详情」应该显示详情页。刷新页面状态保持。

- [ ] **步骤 4：commit**

```bash
git add APP/dashboard/static/js/app.js && git commit -m "feat(dashboard): replace DataPreview with DataSubjectList + DataSubjectDetail"
```

---

## 任务 4：样式

**文件：** `APP/dashboard/static/css/style.css`

- [ ] **步骤 1：添加样式**

在 `style.css` 末尾添加：

```css
/* ── 数据预览改版 ── */
.data-subject-list h2 { margin-bottom: 16px; }
.detail-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.detail-header h2 { flex: 1; }
.source-tag {
    background: var(--bg-secondary);
    color: var(--text-muted);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 11px;
    font-family: monospace;
}
.json-expand-row td { padding: 0 !important; background: var(--bg-secondary); }
.json-detail {
    margin: 8px 16px;
    padding: 12px;
    background: #1e1e1e;
    color: #d4d4d4;
    border-radius: 6px;
    font-size: 12px;
    max-height: 300px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-all;
}
.pagination { display: flex; align-items: center; gap: 12px; justify-content: center; margin-top: 16px; }
.data-table { width: 100%; border-collapse: collapse; }
.data-table th { text-align: left; padding: 8px 12px; border-bottom: 2px solid var(--border); color: var(--text-muted); font-size: 12px; text-transform: uppercase; }
.data-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); }
.data-table tr:hover td { background: var(--bg-secondary); }
.data-info { color: var(--text-muted); font-size: 13px; }
.btn-xs { padding: 2px 8px; font-size: 11px; }
```

- [ ] **步骤 2：验证样式**

页面主题列表、详情页、JSON 展开、分页控件均正确显示。

- [ ] **步骤 3：commit**

```bash
git add APP/dashboard/static/css/style.css && git commit -m "style(dashboard): add data preview redesign styles"
```

---

## 任务 5：集成验证 + 推送

- [ ] **步骤 1：整体功能验证**

1. 访问 `http://localhost:5000` → 数据预览 tab → 看到主题列表
2. 点击「详情」→ 跳转到 `/#/data/{subject}` → 显示数据表格
3. 搜索框输入关键字 → 列表过滤正确
4. 点击「展开」→ JSON 以手风琴展开
5. 分页正常（上一页/下一页）
6. 刷新页面 → 路由状态保持

- [ ] **步骤 2：推送**

```bash
git push
```

---

## 验收标准

- [ ] `GET /api/data/summary` 返回主题摘要
- [ ] `GET /api/data/preview?subject=X`（无 platform）返回该主题所有来源数据
- [ ] 主题列表页显示所有主题、来源数、总条数
- [ ] 详情页正确显示该主题下所有来源数据
- [ ] 搜索框能正确过滤主题内数据
- [ ] 展开行显示原始 JSON，手风琴行为正确
- [ ] 分页正常工作
- [ ] URL 可分享，刷新页面状态保持
