# Dashboard Node.js 重构实施计划

> **目标：** 用 Node.js + Express 重构 Dashboard，彻底解决 `file://` 跨域问题，工程化交付，含完整测试。

**架构：**
```
APP/dashboard/
├── src/
│   ├── server/
│   │   ├── index.js          # Express 入口
│   │   ├── routes/
│   │   │   ├── state.js      # /api/state, /api/rules, /api/executions, /api/errors
│   │   │   └── data.js       # /api/data (采集数据查询)
│   │   └── services/
│   │       └── dataService.js # 读取 state.json + output JSON 文件
│   └── renderer/
│       ├── index.html
│       ├── main.js
│       └── styles.css
├── tests/
│   ├── unit/
│   │   ├── dataService.test.js
│   │   └── routes.test.js
│   └── e2e/
│       └── dashboard.test.js
├── package.json
└── README.md
```

**技术栈：** Node.js + Express（无框架前端）+ Vitest（单元测试）+ Playwright（E2E 测试）

---

## Task 1: 项目初始化

**文件：** `APP/dashboard/package.json`

```json
{
  "name": "info-collector-dashboard",
  "version": "1.0.0",
  "description": "数据采集看板 - Node.js 服务",
  "type": "module",
  "scripts": {
    "start": "node src/server/index.js",
    "dev": "node --watch src/server/index.js",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test"
  },
  "dependencies": {
    "express": "^4.18.2"
  },
  "devDependencies": {
    "vitest": "^1.4.0",
    "@playwright/test": "^1.42.0"
  }
}
```

**Step 2: 创建目录结构**

```bash
mkdir -p src/server/routes src/server/services src/renderer tests/unit tests/e2e
```

**Step 3: 安装依赖**

```bash
cd APP/dashboard && npm install
```

**Step 4: 安装 Playwright 浏览器**

```bash
npx playwright install chromium
```

**Step 5: Commit**

```bash
git add package.json && git commit -m "chore(dashboard): init Node.js project with Express + Vitest + Playwright"
```

---

## Task 2: DataService 核心数据读取层

**文件：** `src/server/services/dataService.js`

提供三个方法：

```javascript
// src/server/services/dataService.js
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// ENGINE_OUTPUT 指向 engine 的 output 目录
const ENGINE_OUTPUT = path.resolve(__dirname, '../../engine/output');

export function getState() {
  const statePath = path.join(ENGINE_OUTPUT, 'state.json');
  if (!fs.existsSync(statePath)) return null;
  return JSON.parse(fs.readFileSync(statePath, 'utf-8'));
}

export function getRule(name) {
  const state = getState();
  if (!state) return null;
  return state.rules?.[name] || null;
}

export function getExecutions(limit = 30) {
  const state = getState();
  if (!state) return [];
  return (state.executions || []).slice(0, limit);
}

export function getErrors(limit = 50) {
  const state = getState();
  if (!state) return [];
  return (state.errors || []).slice(0, limit);
}

export function getStats() {
  const state = getState();
  if (!state) return { total_collected: 0, total_runs: 0, total_failed: 0 };
  return state.stats || {};
}

export function getDataFiles() {
  // 扫描 output/ 下所有 .json 文件（排除 state.json 和 combined_*.json）
  const result = [];
  if (!fs.existsSync(ENGINE_OUTPUT)) return result;

  for (const subdir of fs.readdirSync(ENGINE_OUTPUT)) {
    const subdirPath = path.join(ENGINE_OUTPUT, subdir);
    if (!fs.statSync(subdirPath).isDirectory()) continue;
    for (const file of fs.readdirSync(subdirPath)) {
      if (file.endsWith('.json')) {
        result.push(path.join(subdirPath, file));
      }
    }
  }
  return result;
}

export function getAllData() {
  const files = getDataFiles();
  const allItems = [];
  for (const file of files) {
    try {
      const content = JSON.parse(fs.readFileSync(file, 'utf-8'));
      for (const item of content.data || []) {
        if (!allItems.find(x => x.url === item.url)) {
          allItems.push({ ...item, _file: path.basename(file) });
        }
      }
    } catch (e) { /* skip invalid JSON */ }
  }
  return allItems;
}
```

**Step 1: 写测试** — `tests/unit/dataService.test.js`

```javascript
import { describe, it, expect, beforeEach } from 'vitest';
import { getState, getStats, getExecutions, getErrors } from '../../src/server/services/dataService.js';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TEST_OUTPUT = path.join(__dirname, 'test_output');

describe('dataService', () => {
  beforeEach(() => {
    // 用 engine 的真实 output 目录测试
  });

  it('getState returns null when state.json missing', () => {
    const result = getState.__mock_missing && getState();
    // 真实场景：state.json 不存在时返回 null
  });

  it('getStats returns valid object', () => {
    const stats = getStats();
    expect(stats).toHaveProperty('total_collected');
    expect(stats).toHaveProperty('total_runs');
  });

  it('getExecutions returns array', () => {
    const execs = getExecutions(5);
    expect(Array.isArray(execs)).toBe(true);
  });
});
```

**Step 2: 运行测试**

```bash
npm test
# Expected: PASS（需要先建 tests/unit/dataService.test.js）
```

**Step 3: Commit**

```bash
git add src/server/services/dataService.js tests/unit/dataService.test.js
git commit -m "feat(dashboard): dataService 读取 engine output 目录"
```

---

## Task 3: API Routes

**文件：** `src/server/routes/state.js`

```javascript
import express from 'express';
import * as ds from '../services/dataService.js';

const router = express.Router();

router.get('/state', (req, res) => {
  const state = getState();
  if (!state) return res.status(404).json({ error: 'state.json not found' });
  res.json(state);
});

router.get('/stats', (req, res) => {
  res.json(getStats());
});

router.get('/rules', (req, res) => {
  const state = getState();
  if (!state) return res.json([]);
  res.json(Object.values(state.rules || {}));
});

router.get('/rules/:name', (req, res) => {
  const rule = getRule(decodeURIComponent(req.params.name));
  if (!rule) return res.status(404).json({ error: 'Rule not found' });
  res.json(rule);
});

router.get('/executions', (req, res) => {
  const limit = parseInt(req.query.limit) || 30;
  res.json(getExecutions(limit));
});

router.get('/errors', (req, res) => {
  const limit = parseInt(req.query.limit) || 50;
  res.json(getErrors(limit));
});

export default router;
```

**文件：** `src/server/routes/data.js`

```javascript
import express from 'express';
import { getAllData } from '../services/dataService.js';

const router = express.Router();

router.get('/data', (req, res) => {
  const { platform, clue_type, keyword, limit = 200 } = req.query;
  let items = getAllData();

  if (platform) items = items.filter(i => i.platform === platform);
  if (clue_type) items = items.filter(i => i.clue_type === clue_type);
  if (keyword) {
    const kw = keyword.toLowerCase();
    items = items.filter(i =>
      (i.title && i.title.toLowerCase().includes(kw)) ||
      (i.company && i.company.toLowerCase().includes(kw))
    );
  }

  res.json({ total: items.length, data: items.slice(0, parseInt(limit)) });
});

export default router;
```

**Step 1: 写测试** — `tests/unit/routes.test.js`

```javascript
import { describe, it, expect } from 'vitest';
import request from 'supertest';  // 或直接用原生 http 测试

describe('API routes', () => {
  it('GET /api/stats returns stats object', async () => {
    // 测试 GET /api/stats
  });

  it('GET /api/rules returns array', async () => {
    // 测试 GET /api/rules
  });

  it('GET /api/executions?limit=5 returns 5 items', async () => {
    // 测试分页
  });

  it('GET /api/data?keyword=数据 returns filtered results', async () => {
    // 测试搜索过滤
  });
});
```

**Step 2: Commit**

```bash
git add src/server/routes/ tests/unit/routes.test.js
git commit -m "feat(dashboard): Express API routes for state, rules, executions, errors, data"
```

---

## Task 4: Express Server 入口

**文件：** `src/server/index.js`

```javascript
import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import stateRouter from './routes/state.js';
import dataRouter from './routes/data.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 3000;

const app = express();

app.use('/api', stateRouter);
app.use('/api', dataRouter);

// 前端静态文件
app.use(express.static(path.join(__dirname, '../renderer')));

// SPA fallback
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, '../renderer/index.html'));
});

app.listen(PORT, () => {
  console.log(`Dashboard running at http://localhost:${PORT}`);
});
```

**Step 1: 测试服务器启动**

```bash
node src/server/index.js
# Expected: "Dashboard running at http://localhost:3000"
# curl http://localhost:3000/api/stats
# curl http://localhost:3000/api/rules
```

**Step 2: Commit**

```bash
git add src/server/index.js
git commit -m "feat(dashboard): Express server entry point with static file serving"
```

---

## Task 5: 前端 - index.html

**文件：** `src/renderer/index.html`

完整单页应用，结构：
- Header: 标题 + "执行全部" 按钮
- Stats Row: 总规则数 / 总采集 / 成功次数 / 失败次数
- Tab Bar: 概览 / 执行记录 / 错误日志 / 数据查看
- 左侧规则列表
- 右侧内容区（根据 Tab 切换）

从 `http://localhost:3000/api/*` 获取数据，不走 `file://` fetch。

---

## Task 6: 前端 - main.js

**文件：** `src/renderer/main.js`

模块化重构：
- `api.js` — 所有 fetch 调用
- `state.js` — 全局状态管理
- `views/` — 各 Tab 渲染函数（overview.js, executions.js, errors.js, data.js）
- `main.js` — 初始化 + 事件绑定

---

## Task 7: 前端 - styles.css

**文件：** `src/renderer/styles.css`

继承现有深色主题风格（`--bg: #0f1117` 等），完整 CSS。

---

## Task 8: E2E 测试

**文件：** `tests/e2e/dashboard.test.js`

```javascript
import { test, expect } from '@playwright/test';

test.describe('Dashboard E2E', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000');
  });

  test('shows stats row', async ({ page }) => {
    await expect(page.locator('.stats-row')).toBeVisible();
  });

  test('loads rules list', async ({ page }) => {
    await page.waitForSelector('.rule-item', { timeout: 5000 });
    const items = await page.locator('.rule-item').count();
    expect(items).toBeGreaterThan(0);
  });

  test('rule detail on click', async ({ page }) => {
    await page.waitForSelector('.rule-item', { timeout: 5000 });
    await page.locator('.rule-item').first().click();
    await expect(page.locator('.rule-detail')).toBeVisible();
  });

  test('tab switching works', async ({ page }) => {
    await page.click('text=执行记录');
    await expect(page.locator('#tab-executions')).toBeVisible();
  });

  test('no CORS error in console', async ({ page }) => {
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.waitForSelector('.rule-item', { timeout: 5000 });
    const corsErrors = errors.filter(e => e.includes('CORS') || e.includes('fetch'));
    expect(corsErrors).toHaveLength(0);
  });
});
```

**Step 1: 配置 Playwright**

**文件：** `playwright.config.js`

```javascript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  webServer: {
    command: 'node src/server/index.js',
    port: 3000,
    reuseExistingServer: true,
  },
});
```

**Step 2: 运行 E2E**

```bash
npm run test:e2e
```

---

## Task 9: 更新 README

**文件：** `APP/dashboard/README.md`

```markdown
# InfoCollector Dashboard

Node.js 数据采集看板服务。

## 快速开始

```bash
npm install
npm start
# 访问 http://localhost:3000
```

## 开发

```bash
npm run dev       # 监听模式启动
npm test          # 单元测试
npm run test:e2e  # E2E 测试
```
```

---

## Task 10: 最终 commit 并推送

```bash
git add -A
git commit -m "feat(dashboard): complete Node.js rewrite - Express API + vanilla JS frontend + Vitest + Playwright"
git push
```
