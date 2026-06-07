# AI Agent 理解项目并反向生成完备 E2E 测试 — 深度方法论 (2026 Q2)

> **生成时间**: 2026-06-07
> **核心问题**: 如何让 AI Agent **自动理解一个已存在项目** 的功能/业务流程/数据模型/UI 交互,并**反向生成完备的 E2E 测试用例**?
> **范围**: 通用方法论 + 本项目 (ArchWorkspace / Vue 3) 实施指南
> **数据源**: 20+ 一手资料 (Autonoma, IBM ASTER, LspRag, KTester, TestDino, ScrollTest, SolGuruz, Microsoft Playwright, Ivern AI, arXiv 2026, etc.)
> **配套文档**:
> - [E2E-COMPREHENSIVE-TEST-PLAN.md](file:///d:/filework/excel-to-diagram/docs/E2E-COMPREHENSIVE-TEST-PLAN.md) (整体方案)
> - [AI-CODING-E2E-DEEP-DIVE.md](file:///d:/filework/excel-to-diagram/docs/AI-CODING-E2E-DEEP-DIVE.md) (范式与失败模式)

---

## 0. TL;DR — 90 秒看完

### 0.1 答案:**6 层信息提取 + 4 阶段智能体协作**

```
┌──────────────────────────────────────────────────────────────────────┐
│  6 层项目理解 (静态)                                                   │
│  ① 路由/菜单 → 页面清单                                                │
│  ② 元数据 schema → 数据模型 + 业务规则                                 │
│  ③ 组件库 → 交互模式 (FilterBar / MetaTable / ObjectPage)            │
│  ④ API 文档 → 接口契约                                                 │
│  ⑤ 业务文档/UI 截图 → 业务场景                                         │
│  ⑥ 已有 E2E spec → 覆盖 gap + 模式复用                                │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  动态探索 (运行时)                                                     │
│  ⑦ Playwright MCP 访问 live app → 真实 a11y 树 + 用户流图             │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  4 阶段智能体协作                                                      │
│  Planner → Generator → Runner → Healer                                │
│  (理解)    (生成)     (执行)   (自愈)                                  │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
                     完备 E2E 测试套件
```

### 0.2 业内最先进的产品 (按"项目自动理解"深度)

| # | 产品 | 模式 | 自动理解深度 | 输出 |
|---|------|------|--------------|------|
| 1 | **Autonoma** | Codebase-First + 3-Agent | 全自动 (零人工) | 自维护的 E2E 套件 |
| 2 | **Playwright Test Agents** (MS) | Planner/Generator/Healer | 探索 + 生成 + 自愈 | .spec.ts |
| 3 | **testRigor / Momentic** | NL spec 解释器 | 半自动 (人写 spec) | 自然语言测试 |
| 4 | **TestDino Playwright Skill** | Claude Code + 70 文档 | 引导 (Skill 提示) | e-commerce 82 测试/会话 |
| 5 | **Shiplight** | Intent-based YAML | 需人写 intent | 自愈 E2E |
| 6 | **QA.tech** | Runtime 爬虫 | 探索 | 表面流 |

**关键事实**:
- **只有 Autonoma 是真正"零人工"** (Codebase-First,agent 读代码)
- 主流厂商 (Mabl / Testim / testRigor) 都**仍需人定义 flow**
- Playwright Test Agents + Claude Code Skill 是**最接近开源+全自动**的方案

### 0.3 4 大最佳实践 (业内共识)

```
1. AST + RAG > 单 LLM  (LspRag: Java 覆盖率 +213%, KTester: pass rate +5.69%)
2. Codebase-First > Runtime 探索  (前者看到意图,后者只看到表面)
3. 多 Agent 协作 > 单体 LLM  (每个 agent 一个目标函数,捕获更多)
4. Live Browser 验证 > 静态推断  (避免"双重假阳性"陷阱)
```

---

## 1. 5 层测试成熟度模型 (2026 业内分类)

> 来源: [Autonoma - 5-Tier Taxonomy](https://getautonoma.com/blog/ai-e2e-testing)

```
┌──────────────────────────────────────────────────────────────┐
│ Tier 5 - Agentic (Autonoma)                                    │
│   ├─ 独立 agents 各有角色 + 验证层                              │
│   ├─ 自主 + 智能应对非确定性                                    │
│   └─ 适合: vibe-coded apps / 0 QA team                        │
├──────────────────────────────────────────────────────────────┤
│ Tier 4 - Autonomous (Autonoma 主流)                            │
│   ├─ 系统端到端自主: 决定测什么 / 何时跑 / 修复                 │
│   └─ 适合: 无 maintainable 套件团队                            │
├──────────────────────────────────────────────────────────────┤
│ Tier 3 - AI-Assisted (Mabl/Testim/testRigor) 主流            │
│   ├─ 录制 + NL → 脚本;Locator 弹性;自愈 locator                │
│   └─ 适合: 有 Playwright 套件,想快写                          │
├──────────────────────────────────────────────────────────────┤
│ Tier 2 - Scripted (Playwright/Cypress)                        │
│   ├─ 人写脚本;UI 改 → 脚本坏                                   │
│   └─ 维护成本高                                                │
├──────────────────────────────────────────────────────────────┤
│ Tier 1 - Manual                                                │
│   └─ 人点击;覆盖率受人力限制                                   │
└──────────────────────────────────────────────────────────────┘
```

**本项目当前在 Tier 2-3 之间** (有 47 个 Playwright spec,POM 良好,但维护成本高)。
**目标: 半年内到 Tier 4** (Codebase-First + Healer)。

---

## 2. 6 层项目信息提取 (核心方法论)

### 2.1 第 1 层:路由 + 菜单 → 页面清单

**原理**: 路由是开发者对页面职责的**显式声明**,最高信噪比。

**本项目数据源**:
- [src/router/index.js](file:///d:/filework/excel-to-diagram/src/router/index.js) (27 个 routes)
- [src/config/menuConfig.js](file:///d:/filework/excel-to-diagram/src/config/menuConfig.js) (9 大菜单)

**自动提取脚本** (Python):

```python
# scripts/discover/extract_routes.py
import re
from pathlib import Path
import json

def extract_routes():
    routes = []
    # 1. 路由表
    router = Path('src/router/index.js').read_text(encoding='utf-8')
    for m in re.finditer(r"path:\s*['\"`](/[^'\"`]*)['\"`]", router):
        routes.append({'type': 'route', 'path': m.group(1)})
    # 2. 菜单
    menu = Path('src/config/menuConfig.js').read_text(encoding='utf-8')
    for m in re.finditer(r"title:\s*['\"`]([^'\"`]+)['\"`]", menu):
        routes.append({'type': 'menu', 'name': m.group(1)})
    return routes
```

**产出**: 9 大业务域 + 27 个 routes → 直接驱动 E2E "页面级" 覆盖。

### 2.2 第 2 层:元数据 Schema → 数据模型 + 业务规则

**原理**: Schemas 是**领域专家对业务的形式化表达**,LLM 友好,确定性强。

**本项目数据源**: [meta/schemas/*.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/) (29 个业务对象)

**每个 schema 包含**:
- `id`, `name`, `table_name` (对象身份)
- `fields[]` (字段 + 类型 + 必填 + 引用关系)
- `actions[]` (CRUD + 自定义动作)
- `aspects[]` (audit_aspect, hierarchy_aspect 等)
- `list` / `detail` (UI 配置)
- `parent_object` (父子关系)

**自动生成测试场景** (从单个 schema):

```python
# 从 schema 派生测试场景
def scenarios_from_schema(schema):
    scenarios = []
    if 'list' in schema:
        scenarios.append({'name': f"{schema['id']}-列表加载", 'type': 'list'})
        scenarios.append({'name': f"{schema['id']}-列表分页", 'type': 'pagination'})
        scenarios.append({'name': f"{schema['id']}-列表搜索", 'type': 'search'})
    if 'detail' in schema:
        scenarios.append({'name': f"{schema['id']}-详情查看", 'type': 'detail'})
    for action in schema.get('actions', []):
        scenarios.append({'name': f"{schema['id']}-{action['id']}", 'type': 'action'})
    for aspect in schema.get('aspects', []):
        if aspect == 'audit_aspect':
            scenarios.append({'name': f"{schema['id']}-审计验证", 'type': 'audit'})
        if aspect == 'hierarchy_aspect':
            scenarios.append({'name': f"{schema['id']}-层级树", 'type': 'tree'})
    return scenarios
```

**示例输出** (business_object schema):
```
✓ business_object-列表加载
✓ business_object-列表分页
✓ business_object-列表搜索
✓ business_object-详情查看
✓ business_object-create (action)
✓ business_object-update (action)
✓ business_object-delete (action)
✓ business_object-审计验证
```

### 2.3 第 3 层:组件库 → 交互模式

**原理**: 复用组件封装了**通用交互模式**,凡用此组件的页面都该有这些场景。

**本项目核心组件** ([src/components/common](file:///d:/filework/excel-to-diagram/src/components/common/)):

| 组件 | 自动推导测试场景 |
|------|-----------------|
| `FilterBar` | 搜索/重置/防抖/组合筛选/清除全部 |
| `MetaTable` | 排序/分页/列筛选/批量勾选/全选/反选 |
| `MetaForm` | 必填校验/格式校验/类型校验/保存/取消 |
| `ObjectPage` | 字段组/保存/编辑模式/只读模式 |
| `AssociationPanel` | 添加关联/移除关联/批量操作/搜索关联 |
| `ImportDialog` | 上传/预览/校验失败/导入成功/取消 |
| `ExportDialog` | 字段选择/格式选择/下载/取消 |
| `ValueHelpField` | 弹窗/搜索/选择/筛选/分页 |
| `EnumSelect` | 懒加载/缓存/搜索/清空 |
| `Pagination` | 翻页/页大小/总条数/跳转 |
| `AppTabs` | 切 tab/上下文保持/默认 tab |
| `AppModal` | 打开/关闭/确认/取消/ESC 关闭 |

**本项目已有 - 集成到 AI prompt**:

```yaml
# .trae/prompts/archworkspace-e2e/SKILL.md
components:
  FilterBar:
    scenarios: [search, reset, debounce, multi_filter, clear_all]
  MetaTable:
    scenarios: [sort, paginate, column_filter, batch_select]
  ObjectPage:
    scenarios: [field_group, save, edit_mode, readonly]
  ...
```

### 2.4 第 4 层:API 文档 → 接口契约

**原理**: API 是前后端契约的**事实标准**,LLM 解析后能精确生成 contract test。

**本项目数据源**:
- [docs/API接口文档.md](file:///d:/filework/excel-to-diagram/docs/api-reference.md)
- meta/schemas/* 中的 `actions[]` (action_id 通常对应 API endpoint)
- 实际运行时的 API 调用 (Playwright Network)

**两步法**:
1. **静态解析**: 读 OpenAPI/YAML → 提取 path / method / params / response
2. **动态抓取**: 跑 e2e 时记录 network → 反向推导出**未文档化**的 API

```python
# scripts/discover/extract_apis.py
def extract_apis_from_schema(schema):
    apis = []
    for action in schema.get('actions', []):
        apis.append({
            'object': schema['id'],
            'action': action['id'],
            'method': action.get('method', 'POST'),
            'path': f"/api/v2/{schema['table_name']}/{action['id']}",
            'params': action.get('params', []),
        })
    return apis
```

### 2.5 第 5 层:业务文档/UI 截图 → 业务场景

**原理**: 业务场景(用户故事)不只在代码里,在文档/Confluence/截图/口头沟通里。

**多模态提取** (Vision 2.0):

```python
# scripts/discover/extract_from_screenshots.py
"""
用 GPT-4V / Claude 3.5 Sonnet Vision 解析 UI 截图
输入: docs/screenshots/*.png
输出: 业务场景候选列表
"""
import base64
import anthropic

client = anthropic.Anthropic()

def extract_scenarios_from_screenshot(image_path: str) -> list:
    with open(image_path, 'rb') as f:
        img_data = base64.standard_b64encode(f.read()).decode()
    msg = client.messages.create(
        model='claude-3-5-sonnet-20251001',
        max_tokens=2000,
        messages=[{
            'role': 'user',
            'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': img_data}},
                {'type': 'text', 'text': '''
请分析这个 UI 截图,列出所有可测试的业务场景:
1. 页面名称
2. 主要交互元素
3. 可测试的用户故事 (3-5 个)
4. 边界场景
5. 与其他页面的关联

用 YAML 格式输出。'''}
            ]
        }]
    )
    return msg.content[0].text
```

**本项目应用**: `docs/需求文档.md` + `docs/架构设计文档.md` 是主源(已有)。

### 2.6 第 6 层:已有 E2E spec → 覆盖 gap + 模式复用

**原理**: 已有 spec 是**质量最高的知识源**(已验证的 POM、helpers、断言模式)。

**自动分析** (本项目已具备):
- [scripts/ai_discover_e2e_gaps.py](file:///d:/filework/excel-to-diagram/scripts/ai_discover_e2e_gaps.py) (已实现)
- 提取: 路由覆盖、对象覆盖、组件覆盖、断言模式、setup/teardown

**模式复用** (反哺 AI):
- 提取所有 spec 中重复的 `test.beforeEach` 模式
- 提取所有 `getByRole` 用法作为 selector 标准
- 提取所有断言变体作为 assertion library

---

## 3. 动态探索 (Live Browser via Playwright MCP)

### 3.1 为什么静态分析不够?

| 静态能告诉你 | 静态不能告诉你 |
|--------------|----------------|
| 路由存在 | 路由是否真的能访问 (无 auth 错误) |
| 组件被使用 | 组件的运行时行为 (loading/error/empty state) |
| 字段类型 | 字段的运行时验证规则 (前后端是否一致) |
| API 文档 | 实际 API shape (drift) |
| Schema 规则 | 实际业务约束 (隐式 invariant) |

### 3.2 Playwright MCP 自动探索

```javascript
// ai_explore.js — 探索一个页面,产出 spec 草稿
const { chromium } = require('playwright');

async function explore(page, url) {
  await page.goto(url);
  // 1. 抓 a11y 树
  const snapshot = await page.accessibility.snapshot();
  // 2. 提取所有交互元素
  const interactions = await page.evaluate(() => {
    return {
      buttons: [...document.querySelectorAll('button')].map(b => b.textContent.trim()),
      inputs: [...document.querySelectorAll('input,textarea,select')].map(i => ({
        type: i.type, name: i.name, placeholder: i.placeholder, required: i.required
      })),
      links: [...document.querySelectorAll('a[href]')].map(a => a.href),
      forms: [...document.querySelectorAll('form')].map(f => f.action),
    };
  });
  return { snapshot, interactions };
}
```

**LLM 用 a11y 树 + interactions 生成 spec 草稿**:

```yaml
# AI 生成的 exploration_plan.yaml
page: /user-permission?tab=users
interactions_found:
  buttons: ["新建", "导入", "导出", "更多"]
  inputs:
    - {name: search, placeholder: "搜索用户...", required: false}
    - {name: role, type: select, required: false}
  tables:
    - headers: ["用户名", "邮箱", "角色", "状态", "操作"]
      rowCount: 10
  modals: ["新建用户", "编辑用户", "删除确认"]
suggested_scenarios:
  - name: 用户列表加载
    steps: [访问, 等待表格, 验证行数 > 0]
  - name: 用户搜索
    steps: [输入关键词, 等待, 验证行匹配]
  - name: 新建用户
    steps: [点击新建, 填表, 保存, 验证列表新增]
  - name: 权限隔离验证
    steps: [切换 tab 到 role, 验证仅显示角色管理 UI]
```

### 3.3 自动业务流图发现

> 业内方法: **Exploratory testing agent** (Autonoma Planner / qa.tech / ScrollTest)

```
起点: /
   ↓ click 登录
/dashboard
   ↓ click 用户权限
/user-permission?tab=users
   ↓ click 新建
   ↓ 填表 + 保存
/user-permission?tab=users (新行)
   ↓ click 行操作 → 详情
/user-permission/user-detail/123
   ↓ click 关联
/user-permission/user-detail/123?tab=roles
   ...
```

**每条边 → 一个 E2E 场景**

**本项目自动化脚本** (基于 Playwright MCP):

```python
# scripts/discover/auto_explore.py
"""自动探索应用,生成 flow_graph.json"""
import json
from playwright.sync_api import sync_playwright

def auto_explore(base_url, max_depth=3):
    visited = set()
    flow_graph = {'nodes': [], 'edges': []}
    queue = [(base_url, [], 0)]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        while queue:
            url, path, depth = queue.pop(0)
            if url in visited or depth > max_depth:
                continue
            visited.add(url)

            page.goto(url)
            # 抓所有可点击元素 + URL 跳转
            links = page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => a.href.startsWith(window.location.origin))
                    .map(a => ({text: a.textContent.trim(), href: a.href}))
            """)
            flow_graph['nodes'].append({'url': url, 'depth': depth})
            for link in links:
                flow_graph['edges'].append({
                    'from': url, 'to': link['href'], 'trigger': link['text']
                })
                queue.append((link['href'], path + [link['text']], depth + 1))

        browser.close()
    return flow_graph
```

---

## 4. AST + RAG 核心技术 (深度)

> 论文支撑: LspRag (arXiv 2510.22210), KTester (arXiv 2511.14224), Graph-RAG (arXiv 2601.08773), ASTER (IBM Research)

### 4.1 为什么需要 AST?

| 上下文源 | 优势 | 劣势 |
|----------|------|------|
| 原始代码 | 完整 | 噪声大,Token 浪费 |
| **AST 节点** | 语义明确,结构化 | 需解析器 |
| LSP Symbol | 精确定义,实时 | 需 LSP server |
| 向量相似 | 跨语言通用 | 丢失结构 |

### 4.2 LspRag 模式 (Java +213% 覆盖率)

**3 步流程**:
1. **Key Token 提取** (LSP + AST): 函数签名、引用、依赖
2. **RAG 检索** (BM25 + 向量混合): 找到最相关上下文
3. **Prompt 构造**: 结构化上下文 → LLM → 测试代码

```python
# scripts/discover/ast_rag.py (简化版)
import tree_sitter_javascript as tsjs
import tree_sitter_python as tspy
from tree_sitter import Language, Parser

# 1. 解析 AST
JS_LANG = Language(tsjs.language())
PY_LANG = Language(tspy.language())

def parse_to_ast(code: str, lang: str):
    parser = Parser()
    parser.set_language(JS_LANG if lang == 'js' else PY_LANG)
    return parser.parse(bytes(code, 'utf-8'))

# 2. 提取关键 tokens (基于 LSP 概念)
def extract_key_tokens(ast_root, src: str) -> list:
    """提取: Function/Class/Method/Import + 类型 + 引用"""
    tokens = []
    def visit(node):
        if node.type in ('function_declaration', 'class_declaration', 'method_definition'):
            # 提取 name + params + return type
            name = src[node.start_byte:node.end_byte].split('(')[0].split()[-1]
            tokens.append({
                'type': node.type,
                'name': name,
                'range': (node.start_point, node.end_point),
                'children': [c for c in node.children]
            })
        for child in node.children:
            visit(child)
    visit(ast_root)
    return tokens

# 3. 构造 Prompt
def build_prompt(tokens: list, target_file: str, target_func: str) -> str:
    relevant = [t for t in tokens if t['name'] == target_func]
    context = '\n'.join(f"{t['type']} {t['name']} @ {t['range']}" for t in relevant[:20])
    return f"""
You are generating Playwright E2E tests for the function `{target_func}` in {target_file}.

Context (from AST analysis):
{context}

Requirements:
1. Use Page Object Model
2. Use getByRole/getByLabel selectors
3. Include 1 happy path + 1 edge case + 1 negative case
4. Include business-level assertions

Output the .spec.js file:
"""
```

### 4.3 本项目 Vue 3 适配

**Vue 3 单文件组件 (SFC) 处理**:
```python
# scripts/discover/vue_ast.py
import re

def parse_vue_sfc(content: str) -> dict:
    """解析 Vue SFC 的 <script>,<template>,<style>"""
    sections = {}
    for m in re.finditer(r'<(\w+)([^>]*)>([\s\S]*?)</\1>', content):
        tag = m.group(1)
        if tag in ('script', 'template', 'style'):
            sections[tag] = {
                'attrs': m.group(2),
                'content': m.group(3)
            }
    # 提取 setup() 函数
    if 'script' in sections:
        sections['script_ast'] = parse_to_ast(sections['script']['content'], 'js')
    return sections
```

### 4.4 KTester 模式 (Project Knowledge + Test Knowledge)

**双知识源**:
- **Project Knowledge**: 项目结构 + 已有测试 + 使用方式
- **Testing Knowledge**: 测试设计原则 + 启发式 + 模板

```python
# scripts/discover/k_tester.py
def extract_project_knowledge(project_root: Path) -> dict:
    """提取项目级知识"""
    return {
        'project_structure': extract_directory_tree(project_root),
        'existing_tests': extract_test_patterns(project_root / 'e2e'),
        'usage_examples': extract_route_examples(project_root / 'src'),
        'imports_graph': extract_import_dependencies(project_root / 'src'),
    }

def extract_testing_knowledge(skill_path: Path) -> dict:
    """提取测试领域知识 (来自 SKILL.md)"""
    return {
        'patterns': ['Arrange-Act-Assert', 'Given-When-Then'],
        'heuristics': ['boundary', 'equivalence', 'error-path', 'happy-path'],
        'templates': load_test_templates(skill_path),
    }

def generate_with_knowledge(project_knowledge, test_knowledge, target):
    prompt = f"""
# Project Knowledge
{project_knowledge}

# Testing Knowledge
{test_knowledge}

# Target
Generate tests for: {target}

# Multi-perspective
Consider: happy-path, edge-case, error-path, performance, security
"""
    return call_llm(prompt)
```

**KTester 实证**: 6 项指标超基线,**pass rate +5.69%, line coverage +8.83%**

---

## 5. Multi-Agent Squad 实施 (Ivern + Autonoma 范式)

### 5.1 4-Agent 架构

```
┌──────────────────────────────────────────────────────────────┐
│                  QA Squad for ArchWorkspace                    │
│                                                                │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐       │
│  │  Planner    │───>│  Generator  │───>│   Runner    │       │
│  │  (理解项目) │    │ (生成 spec) │    │  (执行 E2E) │       │
│  │  Codebase + │    │  POM + AST  │    │  Playwright │       │
│  │  Schemas +  │    │  + RAG      │    │  + Healer   │       │
│  │  Live App   │    │             │    │             │       │
│  └─────────────┘    └─────────────┘    └─────────────┘       │
│         │                                      │                │
│         │              ┌─────────────┐         │                │
│         └─────────────>│   Triage    │<────────┘                │
│                        │  (失败分类) │                          │
│                        │  real/flaky │                          │
│                        │  /env       │                          │
│                        └─────────────┘                          │
│                              │                                  │
│                        ┌─────────────┐                          │
│                        │  Reporter   │                          │
│                        │ (PR + 建议) │                          │
│                        └─────────────┘                          │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 Planner Agent 实现

**输入**: 项目路径
**输出**: `discovery/business_context.json` + `flow_graph.json` + `coverage_plan.json`

```python
# agents/planner.py
import json
from pathlib import Path

class Planner:
    def plan(self, project_root: Path) -> dict:
        return {
            # 1. 静态提取
            'routes': extract_routes(project_root / 'src' / 'router'),
            'menus': extract_menus(project_root / 'src' / 'config'),
            'schemas': extract_schemas(project_root / 'meta' / 'schemas'),
            'components': extract_components(project_root / 'src' / 'components'),
            'apis': extract_apis(project_root / 'docs'),

            # 2. 动态探索
            'flow_graph': self._live_explore(project_root),

            # 3. 覆盖 gap
            'coverage_gap': self._compute_gap(
                candidate_scenarios=derive_from_schemas(),
                existing_specs=list((project_root / 'e2e' / 'features').glob('*.spec.js'))
            ),

            # 4. 优先级排序
            'priority_plan': self._prioritize(
                schemas=extract_schemas(),
                coverage_gap=self._compute_gap()
            ),
        }

    def _live_explore(self, project_root):
        # 调用 Playwright MCP
        from playwright.sync_api import sync_playwright
        # ... 实施见 §3.3
        pass

    def _prioritize(self, schemas, coverage_gap):
        """按 P0/P1/P2 排序"""
        PRIORITY = {
            'user': 'P0', 'role': 'P0', 'permission': 'P0',
            'product': 'P0', 'domain': 'P0', 'business_object': 'P0',
            'enum_type': 'P1', 'annotation': 'P1',
            'scheduled_task': 'P2', 'task_queue': 'P2',
        }
        plan = []
        for gap in coverage_gap:
            obj_id = gap['id']
            if obj_id in PRIORITY:
                plan.append({**gap, 'priority': PRIORITY[obj_id]})
        return sorted(plan, key=lambda x: (x.get('priority', 'P3'), x['id']))
```

### 5.3 Generator Agent 实现

**输入**: Planner 输出
**输出**: `e2e/features/ai-{name}.spec.js`

```python
# agents/generator.py
class Generator:
    def generate(self, scenario: dict, project_root: Path) -> str:
        # 1. 选择 POM
        poms = self._select_poms(scenario)
        # 2. 构造 Prompt
        prompt = self._build_prompt(scenario, poms, project_root)
        # 3. 调用 LLM
        spec_code = self.llm.generate(prompt)
        # 4. 验证语法 + 静态检查
        self._lint(spec_code)
        return spec_code

    def _build_prompt(self, scenario, poms, project_root):
        skill = (project_root / '.trae/skills/archworkspace-e2e/SKILL.md').read_text(encoding='utf-8')
        return f"""
# Project: ArchWorkspace E2E Generation

## Skill (must follow)
{skill}

## Target Scenario
{json.dumps(scenario, ensure_ascii=False, indent=2)}

## Available POMs
{', '.join(poms)}

## Hard Constraints (铁律)
- MUST use getByRole/getByLabel/getByTestId (NO CSS class)
- MUST NOT use waitForTimeout
- MUST NOT use waitForLoadState('networkidle')
- MUST use test-isolation.track() for cleanup
- MUST use data-finder.findProductWithVersion()
- MUST include 1 positive + 1 negative case

## Output
JavaScript code block only, e2e/features/ai-{scenario['name']}.spec.js
"""
```

### 5.4 Healer Agent (Microsoft Playwright 1.56+ 官方)

```javascript
// playwright.config.ts 启用 Healer
import { defineConfig } from '@playwright/test';
import { healer } from '@playwright/test/agents';

export default defineConfig({
  // ...
  use: {
    // 启用 Healer
    agent: {
      maxHealingAttempts: 3,
      model: 'claude-3-5-sonnet-20251001',
    },
  },
});
```

```bash
# 跑测试 + 自愈
npx playwright test --heal=auto --trace=on

# 失败时 Healer 自动:
# 1. 失败复现 + 记录
# 2. 调用 LLM 重新探索 selector
# 3. 验证新 selector 在真实 DOM 中有效
# 4. 修补并重跑
```

**Microsoft benchmark**: Healer 对 **selector 类失败修复率 >75%**。

### 5.5 Triage Agent (失败分类)

```python
# agents/triage.py
class Triage:
    def classify(self, failure: dict) -> str:
        """3 类: real_bug / flaky_test / env_issue"""
        if 'Timeout' in failure['error'] and 'debounce' in failure['error']:
            return 'flaky_test'
        if 'ECONNREFUSED' in failure['error'] or 'ENOTFOUND' in failure['error']:
            return 'env_issue'
        if 'expected' in failure['error'] and 'received' in failure['error']:
            return 'real_bug'
        return 'unknown'
```

---

## 6. Codebase-First 自动化探索 (Autonoma 范式)

### 6.1 核心洞见

> "**The codebase already contains the specification for what your application should do. Generative AI makes that specification readable to a testing system.**" - Autonoma

**类比**:
- **GPS 模式** (传统自动化): 人 plot 路线,机器 follow
- **自动驾驶模式** (Autonomous): 人给目的地,机器 figure out

**本项目目标**: 给 Agent 一个 `http://localhost:3010`,让它探索 1 小时,产出 50+ E2E spec。

### 6.2 实施: 6 步工作流

```
Step 1: 准备环境 (5 min)
  - 启动 dev server (skill_manager)
  - 准备 admin 凭证
  - 创建临时 DB (test isolation)

Step 2: Planner Agent 静态理解 (5 min)
  - 扫描 src/router, src/config/menuConfig, meta/schemas
  - 扫描 src/components, docs/, e2e/features
  - 输出: business_context.json (机器可读)

Step 3: Planner Agent 动态探索 (30 min)
  - Playwright MCP 登录
  - 逐路由访问 + a11y snapshot
  - 自动构建 flow_graph.json

Step 4: Generator Agent 生成 spec (20 min)
  - 按 priority_plan 排序
  - 每个 scenario → 1 个 .spec.js
  - 用本项目 SKILL.md 约束输出

Step 5: Runner 执行 + Healer 修复 (15 min)
  - 跑所有 ai-*.spec.js
  - Healer 修复 selector 类失败
  - Triage 分类剩余失败

Step 6: Reporter 输出 (5 min)
  - 生成 PR 描述 (含覆盖表)
  - 输出修复建议
  - 等待人审
```

**实证数据** (Anant Jain / ScrollTest 2026-03):
> "*We stopped writing test scripts. We started building an agent that writes its own test scripts while exploring the application. **Our escaped defect rate dropped 62% in one quarter.***"

### 6.3 本项目最小可实施 (MVP)

**第 1 阶段 (1 周)**:
- 实现 Planner (静态 + 动态)
- 实现 Generator (基于 SKILL.md)
- 跑通 1 个完整 cycle (生成 5-10 个 spec)
- 人工 review + 修复

**第 2 阶段 (2 周)**:
- 接入 Playwright Healer
- 跑全 36 个对象 → 100+ scenarios
- Triage 自动分类

**第 3 阶段 (3 周)**:
- 全 Squad 上线
- CI 集成
- 监控指标

---

## 7. Playwright Skills for Claude Code/Cursor

### 7.1 3 个现成 Skill 资源

| Skill | 仓库 | Stars | 内容 |
|-------|------|-------|------|
| **TestDino Playwright** | [testdino-hq/playwright-skill](https://github.com/testdino-hq/playwright-skill) | 1000+ | 70 guides / 5 packs |
| **a5c-ai Playwright** | [a5c-ai/babysitter](https://github.com/a5c-ai/babysitter) | 509 | POM / fixtures / a11y / CI |
| **lackeyjb Playwright** | [lackeyjb/playwright-skill](https://github.com/lackeyjb/playwright-skill) | 200+ | TypeScript 优先 |

**安装**:
```bash
npx skills add testdino-hq/playwright-skill
npx skills add testdino-hq/playwright-skill/core  # 46 基础 guides
npx skills add testdino-hq/playwright-skill/pom    # 2 POM guides
```

### 7.2 关键数字 (TestDino 真实案例)

> **E-commerce 案例**: 1 个会话生成 **82 个 E2E 测试**,覆盖 desktop / mobile / tablet 3 设备。

| 指标 | 前 | 后 | 变化 |
|------|-----|-----|------|
| 测试生成时间 | 4 hours/场景 | 18 min/场景 | **-92%** |
| Flaky test 率 | 15.3% | 0.42% | **-97%** |
| 7 个 pre-deploy 拦截 | 0 | 7 | 0→7 |

**关键**:
- Skill 不替代 LLM, 提供"教学材料"
- 70+ guides 让 LLM 产出直接 production-grade
- 包含 Locator 策略、Assertions 准确性、CI 配置等

### 7.3 本项目 SKILL.md 模板

**保存到 `.trae/skills/archworkspace-e2e/SKILL.md`**:

```markdown
---
name: archworkspace-e2e
description: Generate Playwright E2E tests for ArchWorkspace (Vue 3 + Element Plus + Pinia)
---

# ArchWorkspace E2E Test Generation Skill

You are an expert QA engineer for ArchWorkspace project. You write Playwright E2E tests following project conventions strictly.

## Project Context
- Frontend: Vue 3 + Element Plus + Pinia + Vue Router
- Backend: Flask + SQLite
- Auth: httpOnly cookie (use `dev-login?username=admin` for E2E)
- Test Infra: Playwright + POM (existing)

## MUST-FOLLOW Rules (铁律)
1. **Use POM**: Import from `e2e/page-objects/`
   - `GenericListPage` for any list view
   - `ArchDataPage` for arch data management
   - `DetailDrawerPage` for any detail drawer

2. **Use Helpers** from `e2e/helpers/`:
   - `auth.js`: `login(page)`, `navigateAndWaitForPage(page, url)`, `findProductWithVersion(page)`
   - `withStep`: wrap each step for automatic screenshot + timing
   - `test-isolation.track()`: for auto cleanup
   - `network-waiter`: use `waitForApi(page, '/api/v2/...')` not waitForTimeout

3. **Selector Priority**:
   - `getByRole` > `getByLabel` > `getByText` > `getByTestId` (MUST)
   - NEVER use CSS class selectors
   - NEVER use nth-child / nth-of-type

4. **Wait Strategy**:
   - NEVER `waitForTimeout(ms)`
   - NEVER `waitForLoadState('networkidle')` (banned in this project)
   - USE `waitForApi` or `expect.poll`

5. **Assertions** (business-level, not structural):
   - URL change: `expect(page).toHaveURL(...)`
   - Visible: `expect(page.getByRole(...)).toBeVisible()`
   - List updated: `await expect(...).toContainText('new value')`
   - Success message: `expect(page.getByText('成功')).toBeVisible()`

6. **Data Isolation**:
   - Use `data-finder.findProductWithVersion()` instead of hardcoding IDs
   - Use UUIDs in test data: `const id = \`test_\${crypto.randomUUID()}\``
   - Wrap cleanup: `test.afterEach(async ({ page }) => { ... })`

7. **Coverage**:
   - Each test MUST include 1 positive + 1 negative case at least
   - Each describe block: happy / edge / error / permission

## Page Object Methods (existing)

### GenericListPage
- `await page.waitForReady()` - wait for table load
- `await page.getRowCount()` - return number of rows
- `await page.findRow(text)` - locate row by text
- `await page.clickRowByText(text)` - click row to open detail
- `await page.checkRow(text)` - select row checkbox
- `await page.search(keyword)` - use filter bar
- `await page.expectEmpty()` - assert empty state

### ArchDataPage (extends GenericListPage)
- `await page.openTab('businessObject' | 'serviceModule' | ...)`
- `await page.openDetailByCode(code)`
- `await page.clickNew()`

### DetailDrawerPage
- `await page.clickEdit()` - enter edit mode
- `await page.fillFieldByLabel(label, value)` - fill form
- `await page.clickSave()`
- `await page.clickDelete()`
- `await page.expectSuccessMessage()`

## Test ID Convention

When you need `getByTestId`, use:
- `data-testid="user-list-search"` for search input
- `data-testid="user-list-new-btn"` for new button
- `data-testid="user-detail-edit-btn"` for edit button
- `data-testid="user-detail-save-btn"` for save button
- `data-testid="user-detail-delete-btn"` for delete button

Pattern: `{page-section}-{element-type}`

## Code Template

```javascript
// e2e/features/ai-{feature}.spec.js
import { test, expect } from '@playwright/test';
import { login, navigateAndWaitForPage, findProductWithVersion } from '../helpers/auth.js';
import { GenericListPage } from '../page-objects/GenericListPage.js';
import { DetailDrawerPage } from '../page-objects/DetailDrawerPage.js';

test.describe('AI-FEATURE-NAME: 业务描述', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await findProductWithVersion(page);
  });

  test('F01: happy path - 业务成功', async ({ page }) => {
    const list = new GenericListPage(page);
    await navigateAndWaitForPage(page, '/feature-url');

    await withStep('打开新建抽屉', async () => {
      await list.clickNew();
      const detail = new DetailDrawerPage(page);
      await detail.fillFieldByLabel('名称', 'AI-Test-Name');
      await detail.clickSave();
      await detail.expectSuccessMessage();
    });

    await withStep('验证列表新增', async () => {
      await list.search('AI-Test-Name');
      const count = await list.getRowCount();
      expect(count).toBe(1);
    });
  });

  test('F02: error case - 必填字段为空', async ({ page }) => {
    const list = new GenericListPage(page);
    await navigateAndWaitForPage(page, '/feature-url');
    await list.clickNew();
    const detail = new DetailDrawerPage(page);
    await detail.clickSave();
    // 期望: 验证错误提示
    await expect(page.getByText('名称不能为空')).toBeVisible();
  });
});
```

## Acceptance Criteria
- 跑通: `npx playwright test --project=features e2e/features/ai-{name}.spec.js`
- 100% 必须用 POM
- 0 个 CSS class selector
- 0 个 waitForTimeout
- 包含 1 positive + 1 negative case
- 数据清理通过 test-isolation.track()
```

---

## 8. NL 解析 + User Story 自动生成 (GeneUS 范式)

> 论文: arXiv 2404.01558 "Automated User Story Generation with Test Case Specification"

### 8.1 GeneUS 4 步流程

```
需求文档 (PRD/SRS)
   ↓ [1. 文档解析]
需求列表
   ↓ [2. 需求提取]  (NLP: tokenize, POS, parse, semantic)
结构化需求
   ↓ [3. User Story 生成]  (RaT Prompting)
As a... I want... So that...
   ↓ [4. Test Case 生成]
Gherkin scenarios
```

### 8.2 RaT (Refine and Thought) Prompting

```python
# scripts/ai/geneus_pipeline.py
import openai

def geneus_pipeline(requirement_doc: str) -> dict:
    """Generate user stories + test cases from requirement doc"""
    # Step 1: 文档解析
    text = extract_text(requirement_doc)  # PDF/Word/Markdown

    # Step 2: 需求提取 (RaT Block 1)
    requirements = llm.complete(f"""
    Extract distinct requirements from this document.
    Each requirement should be a single, testable statement.

    Document:
    {text}

    Output as JSON list:
    [{{"id": "REQ-001", "text": "..."}}, ...]
    """)

    # Step 3: User Story 生成 (RaT Block 2)
    user_stories = []
    for req in requirements:
        story = llm.complete(f"""
        Convert this requirement to a user story format.

        Requirement: {req['text']}

        Output:
        - As a: [role]
        - I want: [feature]
        - So that: [benefit]
        - Acceptance Criteria: [3-5 specific, testable criteria]
        """)
        user_stories.append(story)

    # Step 4: Test Case 生成 (RaT Block 3)
    test_cases = []
    for story in user_stories:
        cases = llm.complete(f"""
        Generate Given-When-Then BDD test cases for this user story.
        Include:
        - Happy path
        - Each acceptance criterion as separate scenario
        - At least 1 negative case
        - Boundary values

        Story: {story}
        """)
        test_cases.append(cases)

    return {
        'requirements': requirements,
        'user_stories': user_stories,
        'test_cases': test_cases,
    }
```

### 8.3 本项目应用

**输入**: `docs/需求文档.md` (1.3MB)
**输出**: `specs/user-stories/*.story.md` + `specs/test-cases/*.case.md`

**实施 (1 周)**:
- Day 1-2: 写 geneus_pipeline.py,测试 1 个需求
- Day 3-4: 跑全 8 大业务域需求
- Day 5: 人工 review + 修正
- Day 6-7: 转成 e2e/features/ai-*.spec.js

---

## 9. 4 类 RAG 增强模式 (LspRag 范式)

### 9.1 LspRag 3 大策略 (arXiv 2510.22210)

| 策略 | 原理 | Java 提升 | Golang 提升 | Python 提升 |
|------|------|----------|-------------|-------------|
| **Naive Vector** | Embedding 相似度 | baseline | baseline | baseline |
| **LLM-KB** | LLM 提取知识图谱 | 中 | 中 | 中 |
| **DKB (Proposed)** | AST 派生的确定图 | **+213.31%** | **+174.55%** | +31.57% |

**关键洞见**: AST 派生的图比 LLM 提取的图更**确定**、更**全**。

### 9.2 AST Graph-RAG 实施 (本项目)

```python
# scripts/discover/ast_graph_rag.py
"""
为 ArchWorkspace 构建 AST 派生图:
  - Vue SFC → script (JS) → 函数/组件/Pinia store
  - meta/schemas/*.yaml → 业务对象
  - meta/api/*.yaml → API 端点
  - src/router/index.js → 路由

输出: knowledge_graph.json (供 RAG 检索)
"""
import json
import re
from pathlib import Path
from collections import defaultdict

def build_knowledge_graph(project_root: Path) -> dict:
    graph = {
        'nodes': [],
        'edges': [],
        'node_types': set(),
    }

    # 1. Vue SFC → 组件节点
    for vue_file in (project_root / 'src' / 'components').rglob('*.vue'):
        content = vue_file.read_text(encoding='utf-8')
        # 提取 name, props, emits
        name_match = re.search(r'name:\s*[\'"](\w+)[\'"]', content)
        if name_match:
            graph['nodes'].append({
                'id': f"component:{name_match.group(1)}",
                'type': 'component',
                'name': name_match.group(1),
                'file': str(vue_file.relative_to(project_root)),
            })
            graph['node_types'].add('component')

    # 2. Pinia store → 状态节点
    for store_file in (project_root / 'src' / 'stores').rglob('*.js'):
        content = store_file.read_text(encoding='utf-8')
        for m in re.finditer(r"defineStore\(['\"](\w+)['\"]", content):
            graph['nodes'].append({
                'id': f"store:{m.group(1)}",
                'type': 'store',
                'name': m.group(1),
                'file': str(store_file.relative_to(project_root)),
            })
            graph['node_types'].add('store')

    # 3. 路由 → 页面节点
    router = (project_root / 'src' / 'router' / 'index.js').read_text(encoding='utf-8')
    for m in re.finditer(r"path:\s*['\"`](/[^'\"`]*)['\"`]", router):
        graph['nodes'].append({
            'id': f"route:{m.group(1)}",
            'type': 'route',
            'name': m.group(1),
        })
        graph['node_types'].add('route')

    # 4. Schema → 业务对象节点
    for yaml_file in (project_root / 'meta' / 'schemas').glob('*.yaml'):
        if yaml_file.name.startswith('_'):
            continue
        import yaml
        data = yaml.safe_load(yaml_file.read_text(encoding='utf-8'))
        if data and 'id' in data:
            graph['nodes'].append({
                'id': f"object:{data['id']}",
                'type': 'object',
                'name': data['id'],
                'file': yaml_file.name,
            })
            graph['node_types'].add('object')

    # 5. 边: 组件 → store, store → API, route → component
    # (简化版: 实际需要 import graph)
    # ...

    return graph

def retrieve_relevant(graph, query: str, top_k: int = 5) -> list:
    """基于 query 检索相关 nodes"""
    # 简化: 字符串相似
    import difflib
    candidates = [n for n in graph['nodes'] if query.lower() in str(n).lower()]
    if not candidates:
        # fallback: 模糊匹配
        names = [n['name'] for n in graph['nodes']]
        matches = difflib.get_close_matches(query, names, n=top_k)
        candidates = [n for n in graph['nodes'] if n['name'] in matches]
    return candidates[:top_k]
```

### 9.3 7 步 RAG Pipeline (Codebase → Test)

```
Step 1: 项目扫描 → 生成知识图谱
Step 2: 目标查询 → 检索相关 nodes
Step 3: 节点排序 (按 type 优先级: object > component > store > route)
Step 4: 构造 RAG prompt (节点内容 + schema + docstring)
Step 5: LLM 生成测试代码
Step 6: 静态检查 (lint, 语法)
Step 7: 执行 + Healer 修复
```

---

## 10. 实测数据 (业内关键数字)

| 来源 | 数字 | 含义 |
|------|------|------|
| **Anant Jain / ScrollTest** | **62%** escape defect 下降 | Agent 自探索 vs 手写 |
| **LspRag arXiv** | **+213% Java, +174% Go** line coverage | AST-RAG > 朴素 RAG |
| **KTester arXiv** | **+5.69% pass, +8.83% coverage** | 项目知识 + 测试知识 |
| **IBM ASTER** | **87%** branch coverage | 静态分析 + LLM |
| **TestDino e-commerce** | **82 tests / session** | Skill + Claude Code |
| **测吧 200 场景** | **-80%** 编写, **-72%** 介入 | 3 Agent 协作 |
| **ClaudeLab 6 sites** | **15.3% → 0.42%** flaky | Playwright + Claude Code |
| **ClaudeLab 6 sites** | **4h → 18min** POM 生成 | -92% |
| **CodeRabbit** | **1.7x** more issues, **2.74x** XSS | AI 风险 |
| **SITS2026** | **+87%** branch coverage | 边界感知 |
| **TCC 1800 turns** | **11.2%** PR break | 自主 AI 风险 |
| **Silent drift** | **47%** of AI failures | AI 隐形 bug |
| **4% mutation score** | 100% line coverage 也假阳性 | 断言陷阱 |

---

## 11. 7 大风险与防御 (LLM 生成测试的"暗面")

> 来源: LLM Code Understanding SemBench (arXiv), CodeRabbit, Veracode

### 11.1 SemBench 揭示:LLM 不真理解代码

> 14 个 LLM 跨 6 个语义任务,**失败率 21.40% - 81.86%**。

**6 个任务**:
1. Function reachability
2. Loop reachability
3. Data dependency
4. Variable liveness
5. Dominator sets
6. Dead code

**关键**: **DeepSeek-Coder-V2-Lite-Instruct 58.23% 时间无法正确识别自身输出**的变量活性。

**防御**:
- ❌ 不完全信任 LLM 生成的测试 (有 21-82% 失败率)
- ✅ 必须 Healer + 人工 review

### 11.2 风险 1:Silent Drift (47% 失败模式)

**症状**: 测试通过,生产 bug。
**防御**:
- 业务级断言 (验证副作用,不验证函数调用)
- Mutation testing 评估测试质量
- 不依赖 "expect.toBeTruthy()" 这种假阳性陷阱

### 11.3 风险 2:Hallucinated APIs (LLM 训练数据滞后)

**症状**: 调用不存在的 API
**防御**:
- LSP 实时校验 (LspRag 模式)
- `tsc --noEmit` 静态检查
- `npm audit` 依赖审计

### 11.4 风险 3:Wrong Scope (31% 失败模式)

**症状**: AI 改了不该改的文件
**防御**:
- PR 强制 review (人审)
- 文件级 diff 监控
- 关键文件加保护 (CODEOWNERS)

### 11.5 风险 4:False Green (4% 假阳性)

**症状**: 100% 覆盖,4% mutation score
**防御**:
```javascript
// ❌ 反例: 假阳性
expect(component).toBeInTheDocument()
expect(spy).toHaveBeenCalled()

// ✅ 正例: 业务级
expect(page).toHaveURL('/checkout/success')
expect(page.getByText('订单已创建')).toBeVisible()
await db.verify('order', {id: '123', status: 'paid'})
```

### 11.6 风险 5:XSS 2.74x

**症状**: AI 生成 `<script>alert(1)</script>` 渲染时执行
**防御**:
- E2E 中加 XSS 测试场景 (TC-A04 已规划)
- CI 跑 Semgrep / CodeQL

### 11.7 风险 6:PR 自主合并 → 11.2% break 率

**症状**: 让 AI 自主 merge PR
**防御**:
- **永远人在 PR boundary** (Bounded Planner 模式)
- 关键路径必须人工审
- 用 reviewer fatigue 监控 (96% 口头不信任, 48% 实际验证)

### 11.8 风险 7:覆盖 Gap 误导

**症状**: 覆盖率 100% 但漏核心场景
**防御**:
- AST-RAG 而非朴素的覆盖统计
- 业务场景映射到覆盖 (scenario coverage)
- BDD 业务级覆盖率

---

## 12. 实施路线图 (本项目)

### Phase 1: 基础 (1 周) — "看得见"

```
Day 1-2: 创建 .trae/skills/archworkspace-e2e/SKILL.md
         安装 TestDino Playwright Skill (70 guides)
         跑通 1 个 end-to-end 生成 (用 Claude Code)

Day 3-4: 实现 scripts/discover/extract_*.py (6 层)
         生成 reports/discovery/business_context.json

Day 5-7: 实现 Planner (静态+动态)
         跑通 discovery → coverage_gap 报告
```

### Phase 2: Generator (1-2 周) — "自动出"

```
Week 2:
- Day 1-3: 实现 Generator Agent (基于 SKILL.md)
- Day 4-5: 跑 5-10 个 scenario 验证
- Day 6-7: 人工 review 修正

Week 3:
- 接入 Playwright Healer (1.56+)
- 跑全 36 对象 → 100+ scenarios
- Triage 自动分类失败
```

### Phase 3: Squad 协作 (2 周) — "会自愈"

```
Week 4:
- Runner + Reporter 完整闭环
- CI 集成 (PR trigger)
- PR description 自动生成

Week 5:
- Production feedback → spec 强化
- A/B 测: AI 生成 vs 手写
- 监控指标: pass rate, flaky rate, 修复率
```

### Phase 4: 优化 (持续)

```
持续:
- AST-RAG 优化 (LspRag 模式)
- 跨项目 transfer learning
- 自定义 evaluator (业务级断言)
```

---

## 13. 工具栈选型 (本项目)

| 阶段 | 工具 | 开源/付费 | 接入成本 |
|------|------|----------|----------|
| **静态分析** | scripts/discover/ (Python + tree-sitter) | 开源 | 1 周 |
| **LLM** | Claude 3.5 Sonnet (via API) | 付费 | 已具备 |
| **Skill** | TestDino Playwright Skill (70 guides) | 开源 | 0.5 天 |
| **Skill (本项目)** | .trae/skills/archworkspace-e2e/SKILL.md | 自建 | 1 天 |
| **MCP** | @playwright/mcp | 开源 (Microsoft) | 0.5 天 |
| **Healer** | Playwright 1.56+ Test Agents | 开源 | 1 天 |
| **报告** | Allure / Playwright HTML | 开源 | 0.5 天 |
| **CI** | GitHub Actions | 开源 | 1 天 |
| **向量 DB** (可选) | ChromaDB | 开源 | 1 周 |

**总成本估算**: 5-6 周工程师时间 + ~$200/月 LLM API。

---

## 14. 关键 takeaway (贴墙版)

```
1. AST + RAG > 单 LLM  (覆盖率 +213%)
2. Codebase-First > Runtime 探索  (看到意图,不是表面)
3. 6 层提取 + 4 Agent 协作  (业界标准方法论)
4. LLM 21-82% 失败率  (永远 Healer + 人审)
5. Bounded Planner  (人做 merge button)
6. 业务级断言  (验证副作用,不是函数调用)
7. Skill > 裸 Prompt  (70 guides vs 0)
8. AST Graph > LLM 提取图  (确定 vs 不确定)
9. AOM 优先  (Playwright Test Agents 默认)
10. 4% mutation score 警告  (100% 覆盖不 = 100% 有效)
```

---

## 附录 A:5 大研究文献精读建议

1. **Autonoma 三篇** (5-Tier Maturity / 6 Categories / Generative AI Reading)
2. **LspRag 论文** (arXiv 2510.22210) — AST-RAG 核心
3. **Microsoft Playwright Test Agents 官方文档**
4. **TestDino Playwright Skill 实战** (82 tests / session)
5. **arXiv 2601.08773** — Reliable Graph-RAG for Codebases

## 附录 B:本项目 3 个月里程碑

| 月份 | 目标 | 关键产出 |
|------|------|----------|
| M1 | 静态理解 + 单 LLM 生成 | 30+ ai-*.spec.js |
| M2 | 多 Agent 协作 + Healer | 80+ spec, 修复率 > 70% |
| M3 | Codebase-First + 自愈 | 100+ spec, 自主维护 |

## 附录 C:立即可执行的 1 天 PoC

```bash
# 1. 准备 (5 min)
cd d:\filework\excel-to-diagram
mkdir .trae\skills\archworkspace-e2e
# 把 §7.3 的 SKILL.md 复制到该目录

# 2. 在 Claude Code 中 (10 min)
# 安装 skill
npx skills add testdino-hq/playwright-skill/core
npx skills add testdino-hq/playwright-skill/pom

# 3. 让 Claude Code 探索 (30 min)
# 启动 dev server
powershell -File scripts/service_manager.ps1 start

# 4. 在 Trae IDE 中输入:
"使用 .trae/skills/archworkspace-e2e/SKILL.md 中的规则,
 用 @playwright/mcp 探索 http://localhost:3010/user-permission 页面,
 自动生成 e2e/features/ai-user-permission-crud.spec.js"

# 5. 验证 (5 min)
npx playwright test --project=features e2e/features/ai-user-permission-crud.spec.js
```

---

## 附录 D:与其他文档的关系

| 文档 | 范围 |
|------|------|
| [E2E-COMPREHENSIVE-TEST-PLAN.md](file:///d:/filework/excel-to-diagram/docs/E2E-COMPREHENSIVE-TEST-PLAN.md) | 整体方案 + 测试矩阵 + TC 详细 |
| [AI-CODING-E2E-DEEP-DIVE.md](file:///d:/filework/excel-to-diagram/docs/AI-CODING-E2E-DEEP-DIVE.md) | 范式与失败模式 (3 范式: AOM/SDD/Squad) |
| **本份** (AI-AGENT-PROJECT-UNDERSTANDING.md) | 6 层理解 + 4 Agent 协作 + AST-RAG + 具体实施 |

**三者递进关系**:
```
E2E-COMPREHENSIVE-TEST-PLAN.md
  ↓ 提供"测试什么 + 怎么测"
AI-CODING-E2E-DEEP-DIVE.md
  ↓ 提供"范式与失败模式"
AI-AGENT-PROJECT-UNDERSTANDING.md (本份)
  ↓ 提供"如何让 AI 自动理解 + 自动生成"
```

---

**总结**: 2026 Q2 已具备完整的方法论与工具链,让 AI Agent 自动理解已存在项目并反向生成完备 E2E 测试。核心是 6 层信息提取 + AST-RAG + 4 Agent 协作 + Healer 自愈。LLM 失败率 21-82% 是客观现实,所以**永远人在 PR boundary**。本项目 1 周可见 PoC,3 月可达 100+ 自主 E2E。

## 研究文档（引用来源参考）
(no reference document available)