# AI Coding E2E 测试深度研究 (2026 Q2)

> **生成时间**: 2026-06-07
> **目标**: 系统性输出 AI Coding 在 E2E 测试领域的最佳实践、范式、失败模式与具体落地方法
> **输入数据源**: Augment / Shiplight / TestDino / Ivern AI / Qyrus / GeekyAnts / Bug0 / CSDN / The Coding Colosseum / arXiv / Microsoft Learn (15+ 一手资料)
> **配套文档**: [E2E-COMPREHENSIVE-TEST-PLAN.md](file:///d:/filework/excel-to-diagram/docs/E2E-COMPREHENSIVE-TEST-PLAN.md) (本研究的实施落地版)

---

## 0. TL;DR (90 秒看完)

### 0.1 3 大核心范式转移 (2026)

| # | 范式 | 旧 | 新 |
|---|------|----|----|
| 1 | **选择器策略** | CSS / XPath (脆弱) | **AOM (Accessibility Object Model)** - 语义、稳定、LLM 友好 |
| 2 | **测试生成** | 手写脚本 / 录制回放 | **Spec-Driven + LLM-as-Planner** - 规格即真相,代码即派生 |
| 3 | **测试维护** | 人工修 (Selector rot) | **Healer Agent 自愈** (Microsoft 官方,>75% 修复率) |

### 0.2 4 大支柱 (业内共识)

```
┌──────────────────────────────────────────────────────────────┐
│  1. INTENT   (意图)     - 自然语言描述,不是点击步骤            │
│  2. CONTRACT (契约)     - OpenAPI/Zod/BDD 强类型              │
│  3. SEMANTIC (语义)     - AOM + data-testid + getByRole       │
│  4. OBSERVABILITY (可观测) - trace + video + console + net     │
└──────────────────────────────────────────────────────────────┘
```

### 0.3 5 大失败模式 (Augment 实证数据)

| 失败模式 | 占比 | 根因 | 修复 |
|----------|------|------|------|
| Brittle/Hallucinated Selectors | 28% | 写 CSS class,引用不存在的 data-testid | 强制 AOM + data-testid 优先级 |
| Timing/Race Conditions | 22% | `waitForTimeout(2000)` 硬等待 | 禁用 networkidle + 条件等待 |
| Schema Drift Across Layers | 18% | 前/后端独立会话生成 | OpenAPI/Zod 强类型 |
| Implicit Timing (动画/Store) | 17% | 假设动画完成 | `expect.poll()` + Store $subscribe |
| Hardcoded Assertions | 15% | `expect(text).toBe('管理员')` | 业务级 + 枚举断言 |

### 0.4 1 个关键数据 (CodeRabbit / 470 PRs)

> **AI 生成代码 1.7x 多问题;XSS 漏洞 2.74x;安全漏洞 45% 出现率**

| 失败类型 | 倍数 |
|----------|------|
| Logic errors | 1.75x |
| Security findings | 1.57x |
| XSS 漏洞 | **2.74x** |
| Insecure object references | 1.91x |
| Improper password handling | 1.88x |
| 100% line coverage + 4% mutation score | ⚠️ 假阳性陷阱 |

---

## 1. 范式 1:AI Browser 交互的 3 条技术路径

### 1.1 三种方法对比

| 维度 | Vision (截图) | DOM 解析 | **AOM (可访问性树)** |
|------|--------------|----------|---------------------|
| **原理** | LLM 看图片 | 解析完整 HTML | 浏览器内置语义树 |
| **成本** | 高 (多模态 token 贵) | 高 (HTML 万行级) | **低 (5-10x 优于截图)** |
| **稳定性** | 极差 (1px 错位) | 中 (依赖 class) | **10x 优于 CSS** |
| **速度** | 慢 (图片传输) | 中 | **快 (纯文本)** |
| **是否需多模态模型** | 是 | 否 | **否** |
| **目标用户** | 老旧 AI | 通用爬虫 | **2026 主流 (Microsoft/Anthropic/Google)** |
| **代表工具** | Skyvern | 早期 Playwright AI | **Playwright MCP / mcp-accessibility-bridge** |

### 1.2 AOM (Accessibility Object Model) 详解

**为什么 AOM 必胜**: AOM 是浏览器为屏幕阅读器(NVDA/JAWS/VoiceOver)构建的语义结构。

每个节点只有 4 个属性:
- **Role**: 元素类型 (button / link / heading / navigation...)
- **Name**: 元素名称 (提交 / 登录 / 取消...)
- **State**: 当前状态 (checked / expanded / disabled...)
- **Description**: 额外描述

**对比示例** (相同 HTML,不同稳定性):

```html
<!-- DOM: 5 元素 → AOM: 3 元素 -->
<div class="card-wrapper">
  <div class="card">
    <h2>Pricing</h2>
    <p>Starting at $10/month</p>
    <button class="btn btn-primary cta-main">Get Started</button>
  </div>
</div>
```

```yaml
# AOM 快照 (YAML)
- role: heading, name: "Pricing"
- role: paragraph, name: "Starting at $10/month"
- role: button, name: "Get Started"  # ← 这一行跨 refactor 不会变
```

**核心洞见**: 选 CSS class (`.btn-primary-v2-new`) 会随重构而坏;选 AOM (button "Get Started") 在**视觉重构、class 变更、wrapper 嵌套变化时全部稳定**。

### 1.3 选 Playwright MCP 的 3 个数据点

| 指标 | 数据 |
|------|------|
| GitHub Stars | **31,463** (microsoft/playwright-mcp) |
| Playwright 月下载 (2026-04) | **6,740 万** (YoY +216%) |
| Healer Agent 修复率 (Microsoft benchmark) | **>75%** (选择器类失败) |
| Cypress 同期数据 | 月下载 2,600 万,YoY +11% |
| Selenium-webdriver | 月下载 770 万,衰退中 |

**结论**: Playwright MCP 已是 LLM 浏览器交互的事实标准。

### 1.4 本项目落地建议

```javascript
// 1. 在 src/components 加 data-testid (本项目已具备基础)
// 2. 在 E2E 中优先 getByRole / getByLabel / getByText
// 3. network-waiter.js (已具备) 替代 waitForTimeout
// 4. 禁止使用 CSS class 作为定位器
```

**检查项 (CI gate)**:

```bash
# 简易检查: spec 文件中不应有 [class*=...] 或 nth-child
grep -rE 'locator\(.[.](\.| \[).' e2e/features/ --include='*.spec.js' && \
  echo "[FAIL] 禁止使用 CSS 复杂选择器" && exit 1
```

---

## 2. 范式 2:Spec-Driven Development (SDD) - 5th Gen 编程

### 2.1 核心定义 (arXiv 2602.00180)

> **"Treat specifications as the source of truth and code as a generated or verified secondary artifact."**

3 层规约深度 (递进):

| 级别 | 范式 | 适用场景 | 工具 |
|------|------|----------|------|
| **L1: Spec-First** | 规约作为引导 + 文档 | 新项目 / 重构 | Markdown, OpenAPI |
| **L2: Spec-Anchored** | 规约作为活文档 + drift 检测 | 中型项目 | OpenAPI + Pact |
| **L3: Spec-as-Source** | 规约即代码,AI 派生实现 | LLM 主导工程 | Zod + tRPC + Claude Code |

### 2.2 SDD 的 5 阶段工作流 (SolGuruz 2026)

```
┌─────────────────────────────────────────────────────────┐
│  1. Specify   →  写 Markdown / OpenAPI / BDD           │
│  2. Plan      →  AI 生成任务分解                       │
│  3. Decompose →  AI 拆解为可执行步骤                    │
│  4. Implement →  AI 生成代码 (人审)                    │
│  5. Validate  →  自动 contract test + E2E              │
└─────────────────────────────────────────────────────────┘
```

### 2.3 SDD 在 E2E 中的具体应用

**模板 (Base Specification Template)**:

```yaml
# specs/USER-CREATION.spec.yaml
purpose: 用户管理 - 创建用户
stakeholders: [admin, hr, security-team]
requirements: [REQ-AUTH-001, REQ-AUDIT-005]
architecture:
  - frontend: UserManagementPage
  - api: POST /api/v2/user
  - data: user table (SQLite)
contracts:
  api: openapi/user.yaml
  events: change_subscription.user.created
non_functional:
  - performance: P95 < 500ms
  - security: OWASP A01, A03
  - accessibility: WCAG 2.1 AA
risks:
  - 密码存储未哈希
test_criteria:
  - 正常流程: admin 创建 user → 列表有 → 审计日志有
  - 异常: email 重复 → 422
  - 异常: 密码弱 → 422
  - 越权: user 角色调 admin API → 403
```

**AI 从 Spec 生成 E2E**:

```javascript
// 输入: spec.yaml + POM
// 输出: e2e/features/ai-user-creation.spec.js
test('F-UC-01: admin creates user with valid data', async ({ page, adminCookie }) => {
  await page.goto('/user-permission')
  // AI 知道: 工具栏 → 新建 → 抽屉填表 → 保存
})

test('F-UC-N1: email duplication', async ({ page, adminCookie }) => {
  // 从 spec 自动派生
  // AI 知道: 期望 422 + 友好提示
})
```

### 2.4 与本项目对接

| 本项目资源 | 转型为 SDD |
|------------|------------|
| `docs/需求文档.md` | L1 Spec-First (Markdown) |
| `docs/API接口文档.md` | L2 Spec-Anchored (OpenAPI) |
| `meta/schemas/*.yaml` | L2 Spec-Anchored (YAML schema) |
| `e2e/features/*.spec.js` | L3 Spec-as-Source (代码即派生) |

**优先级**: 1 周内把 `docs/需求文档.md` 转为 `specs/*.spec.yaml` 格式 (LLM 可消费)。

---

## 3. 范式 3:多 Agent QA Squad 架构

### 3.1 Ivern AI 4-Agent Squad (2026-05)

```
┌─────────────────────────────────────────────────────────────┐
│                  QA Squad (4 Specialized Agents)              │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ Test Planner │→ │ Test Writer  │→ │ Edge Case    │       │
│  │ (设计策略)   │  │ (生成代码)   │  │ Finder       │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│         │                  │                  │              │
│         └──────────────────┼──────────────────┘              │
│                            ↓                                 │
│                  ┌──────────────┐                            │
│                  │ Runner       │  (执行 + 监控)              │
│                  └──────────────┘                            │
│                            ↓                                 │
│                  ┌──────────────┐                            │
│                  │ Triage       │  (失败分类: real/flaky/env) │
│                  └──────────────┘                            │
│                            ↓                                 │
│                  ┌──────────────┐                            │
│                  │ Reporter     │  (生成 PR + 修复建议)        │
│                  └──────────────┘                            │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Microsoft Playwright Test Agents (1.56+ 官方)

| Agent | 输入 | 输出 | 关键能力 |
|-------|------|------|----------|
| **Planner** | Seed test + 运行中应用 | Markdown test plan (specs/*.md) | 探索应用,设计场景 |
| **Generator** | Markdown plan | .spec.ts | 与 live app 交互验证 selector |
| **Healer** | 失败 spec | 修复后 spec | 重放 + DOM 检查 + 自动修复 |

**核心机制**: 3 个 Agent 全部通过 **MCP (Model Context Protocol)** 通信,共同访问 live 浏览器。

### 3.3 启动命令

```bash
# 安装
npx playwright init-agents --loop=claude  # 或 vscode / opencode

# 目录结构
.github/         # agent definitions (重装时覆盖)
specs/           # Planner 生成的 Markdown
tests/           # Generator 生成的代码
  seed.spec.ts   # 种子测试 (必须手写)
```

### 3.4 本项目落地 (最小可行)

**Phase 1: 单 Agent (Generator)** - 1 周

```
1. 安装 Playwright 1.56+
2. 创建 tests/seed.spec.ts (admin 登录 + 工作台)
3. 用 Claude Code / Cursor 调用 @playwright/mcp 探索应用
4. 让 Generator 自动生成 e2e/features/ai-*.spec.js
5. 人工 review + 调整 + 提交
```

**Phase 2: 加 Healer** - 1 周

```
1. 启用 --heal=auto
2. 失败时 Healer 自动修复 selector
3. CI 中加 maxHealingAttempts: 3
4. 监控修复成功率 (Microsoft 基准 > 75%)
```

**Phase 3: 全 Squad** - 2 周

```
1. 接入 Planner 自动生成 specs/ 目录
2. Runner 串行/并行调度
3. Triage 自动分类失败原因
4. Reporter 输出 PR 描述 + 修复建议
```

### 3.5 国内实践 (测吧 / juejin 2026-05)

> **针对 200 个高频回归场景**:
> - 用例编写时间: 15 min/条 → **3 min/条** (-80%)
> - 自愈失败率: **人工介入下降 72%**
> - 智能断言误报率: **< 5%**

**建议**: 不要一次性上 3 个 Agent,先落地"执行+自愈"(价值最直接)。

---

## 4. Prompt Engineering Playbook (5 模式)

> 来源: [Luong Hong Thuan](https://luonghongthuan.com/en/blog/qc-automation-ai-prompts-part7/) / [QaSkills](https://qaskills.sh/blog/ai-test-generation-tools-guide) / [Mark AI Code](https://markaicode.com/ai-playwright-tests-complex-ui/)

### 4.1 Pattern 1:Explore First, Generate Second

```markdown
❌ 差提示:
"为博客页写 Playwright 测试"

✅ 好提示:
"首先用 Playwright MCP 导航到 http://localhost:3010/blog,探索:
- 有哪些交互元素?
- 搜索功能如何工作?
- 标签过滤器?
- 多少篇文章可见?
- 点击文章会发生什么?
**先不要写代码,报告你发现的内容**"

然后再基于发现写测试。
```

**原理**: LLM 看到真实 a11y 树 → 用真实 selector,不是猜测。

### 4.2 Pattern 2:Specify the Architecture (强制 POM)

```markdown
✅ 好提示:
"为登录页写 Playwright 测试,严格遵循:

**架构**:
- LoginPage 类在 tests/pages/LoginPage.ts
- 测试在 tests/e2e/auth.spec.ts
- Import { test, expect } from '../fixtures/base.fixture'

**Locator 优先级**:
1. getByRole() - 按钮、链接、标题
2. getByLabel() - 表单输入
3. getByPlaceholder() - 搜索字段
4. getByText() - 静态文本
5. getByTestId() - 兜底

**断言**:
- expect(page).toHaveURL() - 导航
- expect(locator).toBeVisible() - 可见性
- expect(locator).toContainText() - 内容
- **禁止** page.waitForTimeout()
- **禁止** 原始字符串比较

**测试用例**:
1. 有效凭证成功登录 → 重定向到 /dashboard
2. 密码错误 → 显示错误信息
3. 邮箱为空 → 显示验证错误
4. 密码为空 → 显示验证错误
5. 登录按钮在请求中时禁用"
```

### 4.3 Pattern 3:Edge Case Context (QC 经验补)

```markdown
"为 [功能] 写测试。

**Happy Path**:
- 正常流

**Edge Cases (来自我的 QC 经验)**:
- 粘贴超长字符串 (500+ char)
- 类型重复 100 次触发防抖
- 标签 + 搜索 + 排序组合
- 滑动到底部加载更多
- 弱网 (Network throttling 3G)

**Error States**:
- API 500 → 友好错误
- 空数据 → 空状态
- 超时 10s → 加载状态 + 超时提示

**Boundary**:
- 空字符串 / 1 char / 最大长度
- 特殊字符: <script>alert('xss')</script>
- Unicode: 日本語测试

**断言原则**:
- **业务级断言** (订单创建成功, 看到确认页)
- **不用结构断言** (调用了某函数, 不用验证)
- **验证副作用** (DB 持久化, 邮件发送, 事件触发)"
```

### 4.4 Pattern 4:Iteration Loop (失败 - 反馈 - 修复)

```powershell
# Step 1: 跑测试
npx playwright test --project=e2e

# Step 2: 复制失败
# 失败: "user can filter by tag"
# Error: Timed out 5000ms waiting for expect(locator).toBeVisible()
# Locator: getByRole('button', name='Apply')

# Step 3: 把错误喂回 AI (附上下文)
"测试 'user can filter by tag' 失败:
[粘贴错误]

# 请:
# 1. 解释失败原因
# 2. 给出修复方案 (locator / wait / assertion)
# 3. 修复后重跑"

# Step 4: 验证
npx playwright test --project=e2e --grep "filter by tag"
```

### 4.5 Pattern 5:Validate Against Behavior (行为验证)

```markdown
**核心原则**: 不验证代码做了什么,验证用户能看到什么。

❌ 反例 (结构断言,继承 AI 盲点):
- expect(spyFunction).toHaveBeenCalled()
- expect(component).toBeInTheDocument()
- expect(getByTestId('x')).toBeTruthy()  // 假阳性陷阱!

✅ 正例 (行为断言):
- expect(page).toHaveURL('/checkout/success')
- expect(page.getByText('订单已创建')).toBeVisible()
- expect(page.getByTestId('cart-count')).toHaveText('3')

**研究数据**:
- 100% line coverage + 4% mutation score = 测试在跑但没用
- AI 测试经常"双重验证"AI 实现,形成闭环假阳性
```

### 4.6 通用 Prompt 模板 (本项目)

保存到 `.trae/prompts/e2e-generator.md`:

```markdown
# E2E Test Generator for ArchWorkspace

## Context
- Project: ArchWorkspace (Vue 3 + Element Plus + Pinia)
- Backend: Flask + SQLite
- Auth: httpOnly cookie (dev-login)
- Test Infra: Playwright + POM (GenericListPage, ArchDataPage, DetailDrawerPage)
- Helpers: auth.js, global.setup.js, data-finder.js, test-isolation.js, network-waiter.js

## Must-Use
- POM: {poms}
- Helpers: withStep, track, findProductWithVersion
- Selectors: getByRole > getByLabel > getByText > getByTestId
- Assertions: business-level (URL change, success message, list updated)

## Must-Not
- ❌ waitForTimeout
- ❌ waitForLoadState('networkidle')
- ❌ CSS class selectors
- ❌ hardcoded sleep
- ❌ raw string comparison

## Scenario
{scenario}

## Output
JavaScript spec file at e2e/features/ai-{name}.spec.js
```

---

## 5. The 7-Layer Testing Model (Shiplight 2026)

> 来源: [Shiplight - Testing Strategy for AI-Generated Code](https://www.shiplight.ai/blog/testing-strategy-for-ai-generated-code)

### 5.1 7 层架构

```
┌─────────────────────────────────────────────────────────┐
│  Layer 7: Regression Learning                            │
│  (生产事故 → spec 强化)                                  │
├─────────────────────────────────────────────────────────┤
│  Layer 6: Human Review for Security/Logic                │
│  (安全/逻辑关键路径人工)                                  │
├─────────────────────────────────────────────────────────┤
│  Layer 5: PR-Time Automation Gates                       │
│  (CI 检查: SAST/dependency/contract/mutation)            │
├─────────────────────────────────────────────────────────┤
│  Layer 4: Treat AI-Rewritten Files as Untested           │
│  (AI 重写的文件视为未测试)                                │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Contract Tests at Boundaries                    │
│  (Pact/OpenAPI 跨层契约)                                │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Behavioral Tests (over Unit Tests)              │
│  (行为测试 > 单元测试)                                   │
├─────────────────────────────────────────────────────────┤
│  Layer 1: Spec Before Generation                         │
│  (规格先行,AI 派生)                                      │
└─────────────────────────────────────────────────────────┘
```

### 5.2 本项目应用矩阵

| Layer | 本项目现状 | 改进 |
|-------|-----------|------|
| L1 Spec | 有 docs/需求文档.md | 升级为 specs/*.spec.yaml (1 周) |
| L2 Behavior | 有 features/ 40+ spec | 已覆盖,补 happy+edge 双向 |
| L3 Contract | 部分 (API doc) | 加 OpenAPI + Pact |
| L4 Untouched | N/A | Git hook: AI 改动文件必须 review |
| L5 PR Gate | 部分 | 加 mutation / SAST |
| L6 Human Review | 部分 | 安全/逻辑 spec 必须人工 |
| L7 Regression | 无 | 生产事故 → 自动加强 spec |

### 5.3 The False Green 陷阱

> **研究数据**: 测试 100% line coverage,只检测 4% 真实 bug。

**本项目防御**:
1. 行为断言 (业务级) > 结构断言
2. Mutation testing (Stryker) 评估测试质量
3. 关键路径必须有 negative case
4. 断言验证"副作用"(DB 写入,事件触发,邮件发送)

---

## 6. Bounded Planner 模式 (The Coding Colosseum)

> 来源: [The case against autonomous coding agents in 2026](https://thecodingcolosseum.com/case-against-autonomous-agents/)

### 6.1 11.2% PR-Breaking Failure Rate

> **关键数据**: 即使是最佳 autonomous loop,1,800 turns 生产任务测试,仍有 **11.2% PR 破坏率** (2025-12 是 14%)。

**3 大失败模式分布**:

| 模式 | 占比 | 难以捕捉原因 |
|------|------|--------------|
| **Silent drift** | **47%** | 编译+过单元测试,只在 CI 未覆盖的集成路径坏 |
| **Wrong scope** | **31%** | 改对了文件但改错了范围,绕过 change board |
| **Confident hallucination** | **22%** | 语法对但语义错 (调用对的 API 错的端点) |

### 6.2 Bounded Planner + Human Gate (推荐架构)

```
┌─────────────────────────────────────────────────────────┐
│           AI 自主生成        vs   Bounded + 人审         │
├─────────────────────────────────────────────────────────┤
│  PR 吞吐量   3.4x                    2.1x                │
│  事件率      +38% ↑                  持平                │
│  净收益      ❌ 不可控               ✅ 2.1x             │
└─────────────────────────────────────────────────────────┘
```

**结论**: 永远不要让 AI 自主合并 PR,人做 merge button。

### 6.3 本项目应用

```
AI Agent                          人 (Reviewer)
  │                                  │
  ├─ 生成 spec (e2e/features/...)    │
  │  (含 trace_id + 截图)            │
  ├─ 自动 commit                     │
  │  → 触发 PR 评审                 │
  │                                  ├─ 审查 AI 改动
  │                                  ├─ 关注 silent drift
  │                                  ├─ 验证业务断言
  │                                  ├─ approve / reject
  │                                  └─ merge
```

**关键**: 人在 PR boundary 介入,**不是 AI 写错而是审查不在**.

---

## 7. The 5 Prompt Pillars (TestDriver)

> 来源: [TestDriver](https://testdriver.ai/articles/generate-test-cases-automatically)

| 支柱 | 说明 | 模板 |
|------|------|------|
| **Context** | 项目背景、技术栈、初始状态 | "Project uses Vue 3 + Element Plus + Pinia..." |
| **User Actions** | 每次点击/输入/导航 | "1. Navigate to /user-permission 2. Click 新建..." |
| **Success Criteria** | pass/fail 条件 | "- [ ] Success message 出现 - [ ] 列表新增..." |
| **Edge Cases** | 非法输入、异常、边界 | "- 必填为空 → 红框 - 重复 → 提示..." |
| **Output Rules** | 输出格式约束 | "- use POM - 禁止 CSS class - 禁止 waitForTimeout" |

---

## 8. 5+1 工具栈对比 (本项目选型)

| 工具 | 类型 | 优点 | 缺点 | 适用 |
|------|------|------|------|------|
| **Playwright MCP** | 协议 | 事实标准,GitHub 31k+ | 需 MCP client | 探索/调试/单条生成 |
| **Playwright Test Agents** | 三 Agent | 官方,自愈 | 需 Playwright 1.56+ | 批量生产 |
| **Claude Code + Skills** | CLI | 强推理,Skills 可加载 | 慢,贵 | 复杂 spec |
| **Cursor + Skills** | IDE | 编辑器集成,实时 | 锁定 IDE | 开发过程中 |
| **OpenAI Codex** | Cloud | 异步,sandbox | 不能看 live app | 后台批处理 |
| **本项目推荐** | Hybrid | 适合企业级 | 需多工具协调 | ⭐ 见下 |

### 8.1 推荐选型 (本项目)

```
┌──────────────────────────────────────────────────────────────┐
│  探索/单条生成     →  Playwright MCP (在 Trae 中)            │
│  批量生产         →  Claude Code + 自定义 Skill              │
│  修复/重构        →  Cursor + ai_discover_e2e_gaps 报告    │
│  异步生成        →  OpenAI Codex (与上面错开)              │
│  持续维护        →  Healer Agent (Playwright 1.56+)         │
└──────────────────────────────────────────────────────────────┘
```

---

## 9. 实战案例:某团队 200 个回归场景 (测吧 2026-05)

### 9.1 三 Agent 架构

```
Agent 1 (用例生成):
  RAG (Swagger) + 模板 + 自然语言需求 → 初始 spec

Agent 2 (执行+自愈):
  Playwright + healPlugin({maxHealingAttempts: 3})
  → 失败时调用 Opencli 重写 selector

Agent 3 (断言+报告):
  截图 + 网络日志 + LLM 对比预期 → 结构化报告
```

### 9.2 效果数据

| 指标 | 前 | 后 | 变化 |
|------|-----|-----|------|
| 用例编写时间 | 15 min/条 | 3 min/条 | **-80%** |
| 人工介入率 | 100% | 28% | **-72%** |
| 智能断言误报 | N/A | <5% | 良好 |
| 每日执行测试 | 50 | 200 | **+300%** |

### 9.3 关键命令 (可复现)

```bash
# 安装
npm i @playwright/test
pip install openai rag-playwright playwright-auto-healing
npx playwright install

# 生成
python generate_agent.py --feature "登录与购物车"

# 执行 + 自愈
npx playwright test --heal=auto --trace=on

# 智能分析
node analyze_agent.js --report=allure
```

---

## 10. 与本项目 (ArchWorkspace) 的对接清单

### 10.1 立即可做 (1 周内)

- [ ] 把 `docs/需求文档.md` 转为 `specs/*.spec.yaml` (L1 SDD)
- [ ] 改进 `ai_discover_e2e_gaps.py` 关键词匹配 (AOM 友好)
- [ ] 在 `src/components/common` 添加 `data-testid` 全覆盖
- [ ] CI 加 CSS class 选择器禁止检查

### 10.2 短期 (1 月内)

- [ ] 集成 Playwright 1.56+ Test Agents
- [ ] 创建 `tests/seed.spec.ts` 种子测试
- [ ] 启用 Healer (maxHealingAttempts: 3)
- [ ] 加载 `playwright-e2e` Skill 到 Claude Code / Cursor

### 10.3 中期 (3 月内)

- [ ] 上全 QA Squad (Planner + Generator + Healer + Runner + Triage)
- [ ] OpenAPI 契约测试 (Pact 或 Spectral)
- [ ] Mutation testing 评估测试质量
- [ ] 生产事故 → spec 自动强化 (L7 Regression Learning)

### 10.4 不做的事 (Negative Guidance)

- ❌ 不让 AI 自主合并 PR (永远人在 loop)
- ❌ 不盲目追求覆盖率,关注 mutation score
- ❌ 不替代人工审查安全/逻辑关键路径
- ❌ 不忽略 4% 假阳性陷阱 (100% 覆盖率 ≠ 4% 真实 bug 检测)

---

## 11. 关键引用与数据一览

| 引用 | 关键数据 |
|------|----------|
| Augment 2026-04 | 5 大 AI 失败模式 + 契约修复 |
| Shiplight 2026-05 | 7 层测试模型 + 1.7x bug 率 |
| CodeRabbit 470 PRs | XSS 2.74x, Security 1.57x |
| Veracode 100+ LLMs | 45% 安全漏洞, Java 70% |
| Microsoft Playwright | Healer 75%+ 修复率, MCP 31k stars |
| Playwright 2026 下载 | 6,740 万/月, YoY +216% |
| 测吧 200 场景 | 编写 -80%, 介入 -72% |
| TCC 1,800 turns | 11.2% PR break, silent drift 47% |
| arXiv 2602.00180 | SDD 5th gen programming |
| Standford study | AI 用者更信安全 (反直觉) |
| METR trial | AI 用户 19% 慢 (经验开者) |

---

## 12. 1 周落地计划 (本项目)

| Day | 任务 | 产出 |
|-----|------|------|
| 1 | 把需求文档转为 specs/*.spec.yaml | 8-10 个 L1 specs |
| 2 | 改进 ai_discover_e2e_gaps (AOM 关键词) | gap 报告精度 +20% |
| 3 | data-testid 补全 + CI 检查 | src/components 全面 data-testid |
| 4 | 加载 playwright-e2e Skill + 写 seed test | Claude Code / Cursor 可用 |
| 5 | 集成 Playwright Test Agents (Generator + Healer) | ai-*.spec.js 自动生成 |
| 6 | 跑全 47 spec + Healer 修复 | 修复报告 + 自动化 PR |
| 7 | 输出本周报告 + 下周计划 | docs/AI-CODING-WEEKLY-1.md |

---

## 13. 核心 takeaway (打印贴墙版)

```
1. AOM > CSS > Vision: 用 getByRole 替代 .btn-primary
2. Spec > Code: 先写 OpenAPI/BDD,后写 spec,最后派生实现
3. Intent > Steps: 描述"做什么"而非"怎么点"
4. Healer > Man: 让 Playwright 1.56+ 自愈,别手修 selector
5. Behavior > Structure: 验证"用户能看到什么",不是"代码做了什么"
6. Contract > Hope: OpenAPI 强类型,避免 schema drift
7. Bounded > Autonomous: AI 写到 PR boundary,人做 merge button
8. Multi-Agent > Mono: 1 个 Writer + 1 个 Healer 强于 1 个全能
9. Edge > Happy: QC 经验补 AI 的 happy-path bias
10. Mutation > Coverage: 100% 覆盖率 + 4% mutation = 假阳性陷阱
```

---

**总结**: 2026 Q2 的 AI Coding E2E 已从"工具试验"进入"范式成熟"阶段。3 大范式 (AOM / SDD / Multi-Agent Squad) 已成业内共识,本项目具备 1 周内完成 L1 (AOM + Spec) 转型的所有前置条件。接下来的关键是"行动 + 反馈循环"。

## 研究文档（引用来源参考）
(no reference document available)