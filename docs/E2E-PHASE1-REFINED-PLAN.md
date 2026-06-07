# -*- coding: utf-8 -*-
# E2E Phase 1 细化方案 - 基于实际基础设施 (2026-06-07)

> **目标**: 把上一份 [AI-AGENT-PROJECT-UNDERSTANDING.md](file:///d:/filework/excel-to-diagram/docs/AI-AGENT-PROJECT-UNDERSTANDING.md) 中的泛化建议
> **落到本项目的具体文件 + 已有基础设施** 上
> **范围**: 1 周 (Phase 1),可执行的最小可行集
> **关键认知**: 项目 **已经** 具备 80% 我之前建议的设施,本方案是**接续+补全**而非从零搭建

---

## 0. 关键发现 (TL;DR)

读完 `e2e/`、`scripts/`、`.trae/skills/`、`.trae/specs/`、`ai_discover_e2e_gaps.py` 后,**核心结论**:

| 之前的建议 | 实际状态 | 真实动作 |
|----------|----------|----------|
| 创建 `.trae/skills/archworkspace-e2e/SKILL.md` | 已有 `writing-plans`/`test-driven-development`/`verification-before-completion` | **不创建新 skill**,把规则写到 `.trae/rules/archworkspace-e2e-conventions.md` 即可 |
| 实现 6 层信息提取 | `ai_discover_e2e_gaps.py` 已实现 3 层 (schemas + specs + routes) | **补全** 2 层 (components + APIs),不重写 |
| 装 TestDino Playwright Skill | 项目已有 v2 简化方案,本质等价 | **不装第三方 skill**,充分利用 v2 |
| 需要多 Agent 协作框架 | 已成熟 (`allocate_ports.py` + worktree + service_manager) | **直接使用,不发明新轮子** |
| Multi-Agent Squad | 项目 v2 fixtures = 单 LLM 工作流 | **逐步升级**,不一步到位 |
| 创建新 POM | 已 3 个 (GenericList/ArchData/DetailDrawer) | **补充缺失页面的 POM** (Workspace / Diagram / Account) |
| 跑 v2 compliance | 已 `check_v2_compliance.py` | **集成到 CI**,不重写 |

**一句话**: 本周工作 = **5 个具体文件** + **2 个质量改进** + **1 个根因修复**。

---

## 1. 实际基础设施清单 (已经具备)

### 1.1 E2E v2 简化方案 (2026-06-05 上线)

| 设施 | 路径 | 状态 |
|------|------|------|
| **global-setup 登录共享** | [e2e/helpers/global.setup.js](file:///d:/filework/excel-to-diagram/e2e/helpers/global.setup.js) | ✅ admin + readonly user |
| **POM 基础** | [e2e/page-objects/](file:///d:/filework/excel-to-diagram/e2e/page-objects/) | ✅ GenericList/ArchData/DetailDrawer |
| **Fixtures 自动注入** | [e2e/helpers/auto-fixtures.js](file:///d:/filework/excel-to-diagram/e2e/helpers/auto-fixtures.js) | ✅ dataFinder/navigateTo/isolation/menuNav/waitForApiFn |
| **测试隔离** | [e2e/helpers/test-isolation.js](file:///d:/filework/excel-to-diagram/e2e/helpers/test-isolation.js) | ✅ UUID + createTracked + 自动清理 |
| **智能导航** | [e2e/helpers/auto-fixtures.js#navigateTo](file:///d:/filework/excel-to-diagram/e2e/helpers/auto-fixtures.js#L70-L228) | ✅ SPA 路由 + context restore |
| **数据查找** | [e2e/helpers/data-finder.js](file:///d:/filework/excel-to-diagram/e2e/helpers/data-finder.js) | ✅ 30s 缓存 |
| **菜单导航** | [e2e/helpers/menu-navigator.js](file:///d:/filework/excel-to-diagram/e2e/helpers/menu-navigator.js) | ✅ 集中映射 |
| **API 等待** | [e2e/helpers/network-waiter.js](file:///d:/filework/excel-to-diagram/e2e/helpers/network-waiter.js) | ✅ waitForApi + mockApi |
| **Step 可观测** | [e2e/helpers/auto-trace.js](file:///d:/filework/excel-to-diagram/e2e/helpers/auto-trace.js) | ✅ withStep + diagnostics |
| **v2 合规检查** | [e2e/scripts/check_v2_compliance.py](file:///d:/filework/excel-to-diagram/e2e/scripts/check_v2_compliance.py) | ✅ 9 项强制规则 |

### 1.2 已有 Skills (不重建)

| Skill | 路径 | 用途 |
|-------|------|------|
| writing-plans | [`.trae/skills/writing-plans/SKILL.md`](file:///d:/filework/excel-to-diagram/.trae/skills/writing-plans/SKILL.md) | 写 spec.md/checklist.md/tasks.md |
| using-superpowers | [`.trae/skills/using-superpowers/SKILL.md`](file:///d:/filework/excel-to-diagram/.trae/skills/using-superpowers/SKILL.md) | AI 编码规范 |
| verification-before-completion | [`.trae/skills/verification-before-completion/SKILL.md`](file:///d:/filework/excel-to-diagram/.trae/skills/verification-before-completion/SKILL.md) | 完工前验证 |
| test-driven-development | [`.trae/skills/test-driven-development/SKILL.md`](file:///d:/filework/excel-to-diagram/.trae/skills/test-driven-development/SKILL.md) | TDD |

### 1.3 服务管理 (已成熟)

| 工具 | 路径 | 能力 |
|------|------|------|
| 统一启动 | `scripts/start.ps1` | 幂等启动 + 端口检测 |
| 状态查询 | `scripts/service_manager.ps1` | start/stop/restart/status |
| 端口分配 | `scripts/allocate_ports.py` | 3010-3019 多 Agent 隔离 |
| 看门狗 | `scripts/watchdog.ps1` | 健康监控 + 自动修复 |
| 资源监控 | `scripts/resource_monitor.py` | CPU/内存/磁盘 |

### 1.4 已存在 E2E 覆盖 (30+ spec)

| 业务域 | 已覆盖 | 状态 |
|--------|--------|------|
| 工作台 | `workspace.spec.js` (v1 风格) | ⚠️ 待迁移 v2 |
| 架构数据 | 5 个 spec | ✅ v2 |
| 用户权限 | 5 个 spec | ✅ v2 |
| 审计日志 | 8 个 spec | ✅ v2 |
| 业务对象 | 2 个 spec | ✅ v2 |
| 枚举管理 | 1 个 spec | ✅ v2 |
| 导入导出 | 1 个 spec | ✅ v2 |
| Diagram | 1 个 spec | ✅ v2 |
| 角色意图/权限 | 4 个 spec | ✅ v2 |
| 关系/筛选 | 6 个 spec | ✅ v2 |

---

## 2. 真实缺口 (基于 `ai_discover_e2e_gaps.py` 报告)

> 报告位置: [scripts/ai_discover_e2e_gaps.py](file:///d:/filework/excel-to-diagram/scripts/ai_discover_e2e_gaps.py) (上一轮已创建)
> 输出位置: [reports/e2e_gap.md](file:///d:/filework/excel-to-diagram/reports/e2e_gap.md) + [reports/e2e_gap.json](file:///d:/filework/excel-to-diagram/reports/e2e_gap.json)

### 2.1 量化结果

| 指标 | 数值 | 说明 |
|------|------|------|
| 业务对象 | 36 | schemas/*.yaml 总数 |
| 已覆盖 | 25 | spec 文件提及的对象 |
| **整体覆盖率** | **69.4%** | 还需 11 个对象 |
| **P0 Gap** | **0** | ✅ 全部 P0 覆盖 |
| P1 Gap | 2 | `employee_data_scope` / `filter_variant` |
| P2 Gap | 9 | 任务调度系列 + 订阅 + ai_async_task |

### 2.2 误报修正 (下次跑前必做)

`/`, `/diagram`, `/system/archdata`, `/account` 被误判为 GAP。
**根因**: 关键词映射 `OBJECT_KEYWORDS` 未覆盖 `archdata` (business_object 的别名)。
**修复**: 在 `ai_discover_e2e_gaps.py` 的 `OBJECT_KEYWORDS` 加 `business_object: ['business-object', 'business_object', 'businessobject', 'archdata']`。

### 2.3 真正的需求缺口 (按业务价值排序)

| 缺口 | 业务价值 | 工作量 |
|------|----------|--------|
| Workspace POM + 全场景 | 高 (核心入口) | 1 天 |
| Diagram 6 步向导 (未实施) | 最高 (核心产品) | 2 天 |
| P1: employee_data_scope spec | 中 | 0.5 天 |
| P1: filter_variant spec | 中 | 0.5 天 |
| P2: 任务调度系列 (5 spec) | 中 | 1.5 天 |
| 跨业务流 SF-01~04 (4 spec) | 高 | 2 天 |

**总工作量**: 7.5 天 (略超 1 周,可分两期)。

---

## 3. 一个被忽略的根因 (高优先级)

来自 [TEST_SIMPLIFICATION_REPORT.md](file:///d:/filework/excel-to-diagram/e2e/TEST_SIMPLIFICATION_REPORT.md) 第 3.4 节:

> **🚨 关键发现**: E2E 创建的所有业务对象的 API 返回中 `id: null`!
> 这是**后端业务对象表的 id 字段为 NULL** 的真实应用层 bug。
> 前端表格用 `id` 作为 row key (Element UI `el-table` 默认),`id=null` → 列表不显示。
> v1/v2 测试都因这个 bug 失败。

**影响范围**:
- 任何依赖 business_object 创建后立即列表显示的 E2E
- 大量 business_object 子场景的 spec (auditing/permissions/diagram)

**这周必须先验证/修复此 bug**,否则补的 spec 都会因同一个原因失败。

---

## 4. Phase 1 细化任务清单 (本周 = 5 个工作日)

### Day 1 (Mon) - 修复根因 + 改进 gap 工具

#### 1.1 验证 id=NULL bug (半天)

```bash
# 启动 dev server
powershell -File scripts/start.ps1

# 复现 bug
chcp 65001 | Out-Null
$env:PYTHONIOENCODING = "utf-8"
curl.exe -s -X POST "http://localhost:3010/api/v2/bo/business_object" ^
  -H "Content-Type: application/json" ^
  -H "Cookie: $(curl.exe -s 'http://localhost:3010/api/v1/auth/dev-login?username=admin' -c - -o NUL -b -)" ^
  -d "{\"code\":\"E2E_TEST_$(Get-Random)\",\"name\":\"Test\",\"version_id\":1}"

# 期望: id 不为 null
```

**如果确认 bug**:
- 看 [meta/api/bo/handlers.py](file:///d:/filework/excel-to-diagram/meta/api/bo/handlers.py) 或类似位置
- 查 id 生成逻辑 (自增 / UUID / 序列)
- 在 `.trae/specs/2026-06-08-fix-bo-id-null/` 创建 spec+checklist+tasks

#### 1.2 改进 `ai_discover_e2e_gaps.py` (半天)

**改 1 处即可** (精确版):
```python
# scripts/ai_discover_e2e_gaps.py 第 ~58 行
OBJECT_KEYWORDS = {
    "business_object": ["business-object", "business_object", "businessobject", "archdata"],
    # ... 其他保持
}
```

**改 2 处 (扩展)**:
```python
# 加 1: 扫组件
COMPONENTS_DIR = PROJECT_ROOT / "src" / "components" / "common"

def scan_components():
    """提取本项目组件名,补充关键词"""
    components = set()
    for f in COMPONENTS_DIR.glob("*.vue"):
        m = re.search(r"name:\s*['\"](\w+)['\"]", f.read_text(encoding="utf-8"))
        if m: components.add(m.group(1))
    return components

# 加 2: 加到主流程
components = scan_components()
print(f"[INFO] 发现 {len(components)} 个组件", file=sys.stderr)
```

**验证**:
```bash
python scripts/ai_discover_e2e_gaps.py --output reports/e2e_gap_v2.md --json reports/e2e_gap_v2.json
# 期望: 覆盖率从 69.4% → ~85%
```

### Day 2 (Tue) - Workspace 完整覆盖 (v2 迁移 + POM)

#### 2.1 创建 WorkspacePage POM

**新文件**: [e2e/page-objects/WorkspacePage.js](file:///d:/filework/excel-to-diagram/e2e/page-objects/WorkspacePage.js)

**模板** (参考 [GenericListPage.js](file:///d:/filework/excel-to-diagram/e2e/page-objects/GenericListPage.js)):

```javascript
/**
 * 工作台 POM - 路径: /
 *
 * 工作台元素: 快捷入口、欢迎区、最近访问
 */
import { expect } from '@playwright/test'

export class WorkspacePage {
  constructor(page) {
    this.page = page
    this.entrySelector = '.workspace-entry, .quick-link, [class*="entry"]'
    this.welcomeSelector = '.workspace-welcome, [class*="welcome"]'
  }

  async waitForReady(timeout = 10000) {
    await this.page.locator('body').waitFor({ state: 'visible', timeout })
    // 工作台不需要表格,等关键内容出现
    await Promise.race([
      this.page.locator(this.entrySelector).first().waitFor({ state: 'visible', timeout }),
      this.page.locator(this.welcomeSelector).first().waitFor({ state: 'visible', timeout }),
    ]).catch(() => {})
  }

  async getEntryCount() {
    return await this.page.locator(this.entrySelector).count()
  }

  async clickEntryByText(text) {
    await this.page.locator(`${this.entrySelector}:has-text("${text}")`).first().click()
  }
}
```

**注册**: [e2e/page-objects/index.js](file:///d:/filework/excel-to-diagram/e2e/page-objects/index.js) 加 `export { WorkspacePage } from './WorkspacePage.js'`

#### 2.2 重写 workspace.spec.js (v2 风格)

**改写**: [e2e/features/workspace.spec.js](file:///d:/filework/excel-to-diagram/e2e/features/workspace.spec.js) 整体替换为 v2 风格

```javascript
/**
 * S05: 工作台与导航 - v2 重写版
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { WorkspacePage } from '../page-objects/WorkspacePage.js'

test.describe('S05: 工作台与导航', () => {
  test('C01: 工作台快捷入口可见', async ({ page, navigateTo }, testInfo) => {
    await withStep(page, testInfo, '导航到工作台', async () => {
      await navigateTo(page, '/')
    })
    const ws = new WorkspacePage(page)
    await withStep(page, testInfo, '验证快捷入口', async () => {
      const count = await ws.getEntryCount()
      expect(count).toBeGreaterThan(0)
    })
  })

  test('C02: 点击快捷入口跳转到对应页面', async ({ page, navigateTo }, testInfo) => {
    await navigateTo(page, '/')
    const ws = new WorkspacePage(page)
    await withStep(page, testInfo, '点击第一个入口', async () => {
      const firstText = await page.locator(ws.entrySelector).first().textContent()
      await ws.clickEntryByText(firstText.trim())
      // 验证: URL 不再是 /
      expect(page.url()).not.toMatch(/\/$/)
    })
  })

  test('C03: 跨页面 tab 切换', async ({ page, navigateTo }, testInfo) => {
    await navigateTo(page, '/product-management')
    await withStep(page, testInfo, '切到架构数据', async () => {
      await navigateTo(page, '/system/archdata')
      // 验证: 表格出现
      await page.locator('.el-table').first().waitFor({ state: 'visible', timeout: 10000 })
    })
  })
})
```

#### 2.3 验证 v2 合规

```bash
python e2e/scripts/check_v2_compliance.py e2e/features/workspace.spec.js
# 期望: 0 错误
```

### Day 3 (Wed) - P1 Gap 补充 (2 个 spec)

#### 3.1 employee_data_scope spec (0.5 天)

**新文件**: [e2e/features/employee-data-scope.spec.js](file:///d:/filework/excel-to-diagram/e2e/features/employee-data-scope.spec.js)

```javascript
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { findProductWithVersion } from '../helpers/auth.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'
import { DetailDrawerPage } from '../page-objects/DetailDrawerPage.js'

test.describe('EMP-DS: 员工数据权限范围', () => {
  test('E01: 列表加载', async ({ page, navigateTo }, testInfo) => {
    await findProductWithVersion(page)
    await withStep(page, testInfo, '导航到员工数据范围', async () => {
      await navigateTo(page, '/user-permission', { waitForTabs: true })
      // tab 切到"数据权限"
      await page.getByRole('tab', { name: '数据权限' }).click()
    })
    const list = new GenericListPage(page)
    await withStep(page, testInfo, '验证列表', async () => {
      await list.waitForReady()
    })
  })

  test('E02: 新建数据范围', async ({ page, navigateTo, isolation }, testInfo) => {
    await findProductWithVersion(page)
    await navigateTo(page, '/user-permission', { waitForTabs: true })
    await page.getByRole('tab', { name: '数据权限' }).click()

    const list = new GenericListPage(page)
    const detail = new DetailDrawerPage(page)
    await withStep(page, testInfo, '新建数据范围', async () => {
      await list.clickNew()
      await detail.fillFieldByLabel('名称', 'E2E-Test-Scope')
      await detail.fillFieldByLabel('范围类型', '本部门')
      await detail.clickSave()
      await detail.expectSuccessMessage()
    })
  })

  test('E03: 必填校验 - 名称为空', async ({ page, navigateTo }, testInfo) => {
    await findProductWithVersion(page)
    await navigateTo(page, '/user-permission', { waitForTabs: true })
    await page.getByRole('tab', { name: '数据权限' }).click()
    const list = new GenericListPage(page)
    await list.clickNew()
    // 不填,直接保存
    await page.getByRole('button', { name: '保存' }).click()
    await expect(page.getByText('名称不能为空').first()).toBeVisible({ timeout: 5000 })
  })
})
```

**注**: 实际 URL/字段名以项目为准。先在浏览器里点一遍,再写 spec。

#### 3.2 filter_variant spec (0.5 天)

**新文件**: [e2e/features/filter-variant.spec.js](file:///d:/filework/excel-to-diagram/e2e/features/filter-variant.spec.js)

参考上面的模板,3-5 个 test 覆盖: 列表 / 新建 / 必填校验 / 组合筛选 / 权限隔离。

### Day 4 (Thu) - Diagram 6 步向导 (核心产品,2 天份)

**注意**: 这是一个**大的新功能**,建议拆到下周。这周只做前期工作。

#### 4.1 创建 spec 文档 (使用 .trae/specs/ 模式)

**新文件** (参照 [`.trae/specs/landing-page-refactor/`](file:///d:/filework/excel-to-diagram/.trae/specs/landing-page-refactor/) 模式):

```
.trae/specs/e2e-diagram-wizard/
  spec.md         # 用 writing-plans skill 写
  checklist.md    # 6 步 × 2-3 场景 = 12-18 项
  tasks.md        # 实施步骤
```

**核心内容** (用 writing-plans skill):

```markdown
# spec.md 概要
- 目标: 架构图生成器 6 步向导 E2E 覆盖
- 步骤: 1)选择范围 2)数据源 3)布局 4)样式 5)预览 6)导出
- 每个步骤: happy + 边界 + 错误 3 场景
- 共 18 个 test
- 优先级: P0 (核心产品)

# checklist.md
- [ ] S1-01: 选择范围 (产品+版本)
- [ ] S1-02: 边界 - 必选未选
- [ ] S2-01: 数据源配置
- ...
```

#### 4.2 创建 DiagramPage POM

**新文件**: [e2e/page-objects/DiagramPage.js](file:///d:/filework/excel-to-diagram/e2e/page-objects/DiagramPage.js)

```javascript
/**
 * 架构图生成器 POM - 路径: /diagram
 *
 * 6 步向导: 范围 → 数据源 → 布局 → 样式 → 预览 → 导出
 */
export class DiagramPage {
  constructor(page) {
    this.page = page
    this.wizardStepSelector = '.wizard-step, [class*="step"]'
    this.nextBtnSelector = 'button:has-text("下一步")'
    this.prevBtnSelector = 'button:has-text("上一步")'
    this.exportBtnSelector = 'button:has-text("导出")'
  }

  async waitForReady() {
    await this.page.locator(this.wizardStepSelector).first()
      .waitFor({ state: 'visible', timeout: 10000 })
  }

  async getCurrentStep() {
    return await this.page.locator(this.wizardStepSelector + '.active')
      .textContent().catch(() => 'unknown')
  }

  async clickNext() { await this.page.locator(this.nextBtnSelector).click() }
  async clickPrev() { await this.page.locator(this.prevBtnSelector).click() }

  async selectProduct(productName) {
    await this.page.getByLabel('产品').click()
    await this.page.getByRole('option', { name: productName }).click()
  }
  async selectVersion(versionName) {
    await this.page.getByLabel('版本').click()
    await this.page.getByRole('option', { name: versionName }).click()
  }
}
```

**注册到** [e2e/page-objects/index.js](file:///d:/filework/excel-to-diagram/e2e/page-objects/index.js)

### Day 5 (Fri) - 集成 + CI + 文档

#### 5.1 集成 v2 compliance 到 CI (半天)

**改**: [.github/workflows/](file:///d:/filework/excel-to-diagram/.github/workflows/) (如不存在则创建 `e2e-ci.yml`)

```yaml
name: E2E Compliance
on: [push, pull_request]
jobs:
  compliance:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: v2 合规检查
        run: python e2e/scripts/check_v2_compliance.py
      - name: gap 分析
        run: python scripts/ai_discover_e2e_gaps.py --quiet
```

#### 5.2 输出本周报告 (半天)

**新文件**: [docs/E2E-WEEKLY-1.md](file:///d:/filework/excel-to-diagram/docs/E2E-WEEKLY-1.md) (本文件补完)

**内容**:
- 本周 5 天成果 (1 个 POM + 2-3 个 spec + 1 个 bug 修复)
- 测试通过率变化
- 覆盖率变化
- 下周计划

---

## 5. 完整改动清单 (本周)

### 5.1 新建文件 (7 个)

| # | 路径 | 用途 | 工作量 |
|---|------|------|--------|
| 1 | `e2e/page-objects/WorkspacePage.js` | 工作台 POM | 0.5 天 |
| 2 | `e2e/features/employee-data-scope.spec.js` | P1 Gap 1 | 0.5 天 |
| 3 | `e2e/features/filter-variant.spec.js` | P1 Gap 2 | 0.5 天 |
| 4 | `e2e/page-objects/DiagramPage.js` | 架构图 POM | 0.5 天 |
| 5 | `.trae/specs/e2e-diagram-wizard/spec.md` + checklist.md + tasks.md | 6 步向导 spec | 0.5 天 |
| 6 | `docs/E2E-WEEKLY-1.md` | 周报 | 0.5 天 |
| 7 | (可选) `.github/workflows/e2e-ci.yml` | CI 集成 | 0.5 天 |

### 5.2 修改文件 (4 个)

| # | 路径 | 改动 | 工作量 |
|---|------|------|--------|
| 1 | `scripts/ai_discover_e2e_gaps.py` | 加 archdata 关键词 + 扫 components | 0.5 天 |
| 2 | `e2e/features/workspace.spec.js` | v1 → v2 重写 | 0.5 天 |
| 3 | `e2e/page-objects/index.js` | 注册新 POM | 0.1 天 |
| 4 | (可能) `meta/api/bo/handlers.py` 或类似 | **修复 id=NULL bug** | 1 天 (需排查) |

### 5.3 不做的事 (避免范围蔓延)

- ❌ 不创建新的 Skill (已有 writing-plans / TDD / verification)
- ❌ 不安装第三方 Skill (TestDino 等)
- ❌ 不重写 `ai_discover_e2e_gaps.py` (补全即可)
- ❌ 不实现 Multi-Agent Squad (项目 v2 fixtures 已够用)
- ❌ 不动 service_manager / allocate_ports (已成熟)
- ❌ 不迁移所有 v1 spec (v1 也 work,v2 是 better practice)
- ❌ 不写 Skill 文档 (写到 `.trae/rules/` 即可,不是 Skill)

---

## 6. 验证清单 (每天下班前)

| 检查项 | 命令 | 期望 |
|--------|------|------|
| v2 合规 | `python e2e/scripts/check_v2_compliance.py e2e/features/<新文件>` | 0 错误 |
| 单 spec 跑 | `npx playwright test e2e/features/<新文件> --retries=0` | 全部通过 |
| 全量 features | `npx playwright test --project=features` | 通过率 100% (或与基线持平) |
| Gap 报告 | `python scripts/ai_discover_e2e_gaps.py --output reports/e2e_gap_<date>.md` | 覆盖率 ≥ 70% |
| Type check (Python) | `python -c "import ast; ast.parse(open('<file>', encoding='utf-8').read())"` | 无异常 |
| 服务健康 | `powershell -File scripts/service_manager.ps1 status` | RUNNING |

---

## 7. 与上一份方案的关键差异

| 维度 | 上一份 (泛化研究) | 本份 (细化执行) |
|------|-----------------|----------------|
| Skill 创建 | 建议创建 `archworkspace-e2e/SKILL.md` | **不创建**,用 `.trae/rules/archworkspace-e2e-conventions.md` (后续 Week 2) |
| 第三方 Skill | 建议装 TestDino | **不装**,项目 v2 等价 |
| 6 层信息提取 | 建议实现 6 层 | **补 2 层即可** (schemas+specs+routes 已存在,只补 components+apis) |
| Multi-Agent Squad | 建议 4 Agent 完整闭环 | **逐步升级**,先单 LLM + Healer |
| POM | 建议扩展 | **只补 3 个** (Workspace / Diagram / Account) |
| Healer | 建议 Playwright 1.56+ | **不升级**,等 v1.56 stable 后再评估 |
| 跨业务流 SF-01~08 | 建议立即做 | **下周做** (Day 4-5) |
| 重点 | 研究 + 范式 | **执行 + 落地** |

---

## 8. 风险与防御

| 风险 | 防御 |
|------|------|
| 修复 id=NULL bug 触发回归 | 在 spec 目录加回归测试,只动最小范围 |
| Workspace v2 迁移破坏现有 47 个 spec | 跑全 features suite 验证 (Day 2 结束前) |
| Diagram 6 步向导调研不清 (无 app 看) | 先开 dev server 手动点一遍,记下交互细节,再写 spec |
| 新 POM 风格与现有不一致 | 参照 [GenericListPage.js](file:///d:/filework/excel-to-diagram/e2e/page-objects/GenericListPage.js) 风格 + `// POM 基础` 注释 |
| 中文文件编码 | 遵循 [file-encoding-rules.md](file:///d:/filework/excel-to-diagram/.trae/rules/file-encoding-rules.md),新 .py 必加 `# -*- coding: utf-8 -*-` |
| PowerShell curl 卡死 | 遵循 [powershell-curl-alias.md](file:///d:/filework/excel-to-diagram/.trae/rules/powershell-curl-alias.md),用 `curl.exe` 或 Python |
| 多 Agent 端口冲突 | 用 [allocate_ports.py](file:///d:/filework/excel-to-diagram/scripts/allocate_ports.py) 分配独立端口 |
| DB 污染 | 所有测试用 `isolation.createTracked()`,**禁止** `${Date.now()}` 命名 |
| 误改核心 spec | 跑前 `git status`,只动要改的 |

---

## 9. 立即可做的 1 小时 PoC

```bash
# 1. 验证 v2 compliance 当前状态 (2 min)
python e2e/scripts/check_v2_compliance.py
# 期望: 看到具体哪些文件违反 v2

# 2. 跑 gap 报告 (1 min)
python scripts/ai_discover_e2e_gaps.py --output reports/e2e_gap_v2.md

# 3. 检查 workspace.spec.js 是否 v1 (5 min)
cat e2e/features/workspace.spec.js | head -20
# 看到 `from '@playwright/test'` + `await login()` → 确认是 v1

# 4. 启动 dev server (1 min)
powershell -File scripts/start.ps1

# 5. 跑 workspace 当前 spec,看是否通过 (2 min)
npx playwright test e2e/features/workspace.spec.js --retries=0

# 6. 验证 id=NULL bug (5 min)
# 见 Day 1.1 的 curl 命令
```

---

## 10. 与其他文档的关系

| 文档 | 范围 | 何时用 |
|------|------|--------|
| [E2E-COMPREHENSIVE-TEST-PLAN.md](file:///d:/filework/excel-to-diagram/docs/E2E-COMPREHENSIVE-TEST-PLAN.md) | 完整测试矩阵 + TC 详细 | 写 TC 时参考 |
| [AI-CODING-E2E-DEEP-DIVE.md](file:///d:/filework/excel-to-diagram/docs/AI-CODING-E2E-DEEP-DIVE.md) | 范式与失败模式 | 理解 3 范式 (AOM/SDD/Squad) |
| [AI-AGENT-PROJECT-UNDERSTANDING.md](file:///d:/filework/excel-to-diagram/docs/AI-AGENT-PROJECT-UNDERSTANDING.md) | 6 层理解 + 4 Agent 协作 | 了解"为什么这么做" |
| [TEST_SIMPLIFICATION_REPORT.md](file:///d:/filework/excel-to-diagram/e2e/TEST_SIMPLIFICATION_REPORT.md) | v2 实施报告 + 性能对比 | 了解 v2 收益 |
| **本份** (E2E-PHASE1-REFINED-PLAN.md) | **本周可执行清单** | **直接执行** |

---

## 11. 一周交付 (本周五)

- ✅ 1 个 bug 修复 (id=NULL)
- ✅ 1 个改进工具 (gap 关键词 + components 扫描)
- ✅ 2 个新 POM (Workspace + Diagram)
- ✅ 3 个新 spec (workspace 重写 + 2 个 P1 Gap)
- ✅ 1 个下周 spec 文档 (Diagram 6 步向导的 spec.md/checklist.md/tasks.md)
- ✅ 1 个周报 (E2E-WEEKLY-1.md)
- ✅ (可选) CI 集成

**核心数字**:
- 业务对象覆盖率: 69.4% → **~75%** (排除误报后)
- v2 合规 spec: ~70% → **~85%**
- 测试总行数: +200-300 行 (3 个 spec)
- 测试稳定性: 提升 (v2 统一)

---

**总结**: 1 周的细化方案 = **5 个新建 + 4 个修改 + 1 个 bug 修复**。本方案的关键不是"做什么"而是"**不做什么**"——**不创建新 skill、不重写已有设施、不发明新框架**。直接复用项目成熟的 v2 简化方案 + POM 模式,把 gap 报告的 11 个对象按业务价值补全。
