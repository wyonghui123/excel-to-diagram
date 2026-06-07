# ArchWorkspace 端到端前端测试完整方案

> **版本**: v1.0 | **日期**: 2026-06-07 | **范围**: ArchWorkspace / excel-to-diagram
> **目标**: 用 AI Coding 最佳实践，自动化理解产品核心场景，输出相对完备的 E2E 测试用例
> **现状**: 已具备 Playwright + POM + global-setup + 40+ features 的基础设施

---

## 第一部分:AI Coding E2E 行业最佳实践 (2026)

### 1.1 AI 写 E2E 失败的 5 种核心模式

> 来源: [Augment Code 2026 研究](https://www.augmentcode.com/guides/why-ai-coding-agents-fail-e2e-tests)

| 失败模式 | 根因 | 解决契约 |
|----------|------|----------|
| **选择器脆弱/幻觉** | 写 CSS 类名(`.btn-primary`),引用不存在的 `data-testid`,基于假设的 DOM 嵌套写 XPath | **契约**: 固定 `data-testid` 策略 + 优先 `getByRole`/`getByText` |
| **时序假设/竞态** | 写死 `waitForTimeout(2000)`,CI 环境网速/CPU 不同导致不稳定 | **契约**: 禁用 `waitForLoadState('networkidle')` + 基于 API/元素的 `waitForResponse` |
| **跨层 schema 漂移** | 前端/后端在分离会话中生成,响应字段对不上 | **契约**: OpenAPI/Zod 强类型 + 共享 schema |
| **隐式时序** | 假设动画完成,假设 Store 已 commit | **契约**: Playwright `expect.poll()` + Store $subscribe 事件 |
| **断言硬编码** | 写 `expect(text).toBe('管理员')` 而不是 `expect(role).toBeOneOf([...])` | **契约**: 业务级断言 + 可变预期枚举 |

**对我们的启示**:
- 本项目已强制 `data-testid` 优先级(可在 `playwright.config.js` 加 globalSetup 校验)
- 已有 `waitForApi` + `withStep` 框架(需在更多 spec 中落实)
- **本次方案目标**: 用 AI 自动化发现 + 生成测试,**避免硬编码断言,优先语义定位**

### 1.2 5 种 AI 写 E2E 的方法 (按 context 深度排序)

> 来源: [TestDino 2026 指南](https://testdino.com/blog/ai-write-playwright-tests)

| 方法 | 工具 | 上下文深度 | 适用场景 |
|------|------|------------|----------|
| **Playwright MCP** | @playwright/mcp | 实时浏览器 + a11y snapshot | 交互式探索/调试/单条生成 |
| **Playwright CLI** | npx playwright-cli | YAML snapshot + 离线 artifact | 批量生成/CI/长会话 |
| **Test Agents (Planner+Generator+Healer)** | 内置 | 结构化三阶段 | 自愈回归 |
| **Playwright Skills** | 加载 SKILL.md | 框架专属 prompt | 一致生产级 |
| **本项目方案 (Hybrid)** | MCP + 静态分析 + Spec 驱动 | **代码 + Spec + 浏览器 + DB** | **企业级全套生成** |

### 1.3 4 大支柱 (业内共识)

```
┌─────────────────────────────────────────────────────────────────┐
│  1. INTENT (意图)  - 自然语言描述业务,不是点击步骤                   │
│  2. CONTRACT (契约) - OpenAPI + Zod + 共享 fixture                  │
│  3. SEMANTIC (语义) - getByRole/getByText/data-testid              │
│  4. OBSERVABILITY (可观测) - trace + video + console + network    │
└─────────────────────────────────────────────────────────────────┘
```

### 1.4 提示词工程 (Prompt Engineering for E2E)

> 来源: [TestDriver 2026](https://testdriver.ai/articles/generate-test-cases-automatically)

**The 4 Pillars of Effective Prompt**:
1. **Context**: 描述功能、用户角色、初始状态
2. **User Actions**: 每次点击、输入、导航
3. **Success Criteria**: pass/fail 条件(消息、重定向、数据)
4. **Edge Cases**: 非法输入、异常流、边界值

**本项目应用的 Prompt 模板** (见第五部分)

---

## 第二部分:产品核心场景自动化发现

### 2.1 自动发现方法 (4 个数据源)

```
┌────────────────────────────────────────────────────────────────────┐
│  1. 路由 + 菜单  →  src/router/index.js + src/config/menuConfig.js │
│  2. 元数据模型  →  meta/schemas/*.yaml (40+ 对象)                  │
│  3. 组件清单  →  src/components/common/index.js (50+ 组件)         │
│  4. 已有测试  →  e2e/features/*.spec.js (40+ spec)                  │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 通过路由 + 菜单自动发现页面级场景

| 路由 | 页面 | 业务域 | 自动化覆盖度 |
|------|------|--------|--------------|
| `/` | 工作台 (ArchWorkspace) | 入口 | **未覆盖** |
| `/diagram` | 架构图生成器 | 核心 | 已覆盖 (1 spec) |
| `/system/archdata` | 架构数据管理 (5 tab) | 核心 | **已覆盖核心,缺完整 tab 联动** |
| `/product-management` | 产品管理 | 配置 | **未覆盖** |
| `/user-permission` | 用户/用户组/角色 (3 tab) | 权限 | 部分覆盖 |
| `/business-config` | 业务配置 (枚举) | 配置 | **未覆盖** |
| `/system-admin` | 日志管理 | 审计 | 已覆盖 (10+ spec) |
| `/system/task-management` | 任务调度 (4 子页) | 运维 | **未覆盖** |
| `/account` | 账户设置 | 个人 | **未覆盖** |
| `/detail/:objectType/:id` | 对象详情 (动态生成) | 核心 | 已覆盖 (ObjectPage 通用) |

**覆盖率计算**: 9 大业务域,已自动化 4 个 (44%)。

### 2.3 通过元数据模型自动发现数据级场景

**自动发现脚本** (一次性执行,生成 `discovery-report.json`):

```python
# scripts/discover_e2e_scenarios.py
import yaml, json, glob
from pathlib import Path

def discover():
    schemas_dir = Path('meta/schemas')
    objects = {}
    for yaml_file in schemas_dir.glob('*.yaml'):
        if yaml_file.name.startswith('_'): continue
        with open(yaml_file, encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        obj_id = data.get('id')
        if not obj_id: continue
        objects[obj_id] = {
            'file': yaml_file.name,
            'fields': len(data.get('fields', [])),
            'actions': [a.get('id') for a in data.get('actions', [])],
            'aspects': data.get('aspects', []),
            'has_crud': all(k in data for k in ('list','detail')),
            'has_audit': 'audit_aspect' in data.get('aspects', []),
        }
    Path('discovery-report.json').write_text(
        json.dumps(objects, indent=2, ensure_ascii=False), encoding='utf-8'
    )
    print(f'[discover] {len(objects)} objects found')

if __name__ == '__main__':
    discover()
```

**结果示例 (29 个业务对象)**:

| 对象 | CRUD | 审计 | 关联 | 优先级 |
|------|------|------|------|--------|
| `user` | ✓ | ✓ | user_group, role | P0 |
| `role` | ✓ | ✓ | permission, user | P0 |
| `user_group` | ✓ | ✓ | user, role | P0 |
| `permission` | ✓ | ✓ | - | P0 |
| `product` | ✓ | ✓ | version | P0 |
| `version` | ✓ | ✓ | product | P0 |
| `domain` | ✓ | ✓ | sub_domain | P0 |
| `sub_domain` | ✓ | ✓ | domain, business_object | P0 |
| `business_object` | ✓ | ✓ | sub_domain, service_module, relationship | P0 |
| `service_module` | ✓ | ✓ | sub_domain, business_object | P0 |
| `relationship` | ✓ | ✓ | business_object | P0 |
| `enum_type` | ✓ | ✓ | enum_value | P1 |
| `enum_value` | ✓ | ✓ | enum_type | P1 |
| `annotation` | ✓ | ✓ | business_object | P1 |
| `audit_log` | R | - | - | P1 |
| `menu` | ✓ | - | parent_menu | P2 |
| `scheduled_task` | ✓ | ✓ | - | P2 |
| `task_queue` | R | - | - | P2 |
| `task_execution` | R | - | - | P2 |
| `ai_async_task` | R | - | - | P2 |
| ... | | | | |

### 2.4 通过组件清单自动发现交互场景

**核心可复用组件** (src/components/common):

```
[原子层]   AppButton, AppInput, AppSelect, AppModal, AppTabs, AppSideNav
[业务层]   FilterBar, MetaTable, MetaForm, MasterDetailLayout, Pagination
[复合层]   MetaListPage, DetailPage, ObjectPage, AssociationPanel
[辅助层]   AuditLog, ImportDialog, ExportDialog, ValueHelpField, EnumSelect
```

**交互模式自动发现**:
- `FilterBar` → 搜索/重置/防抖/多选场景
- `MetaTable` → 排序/分页/列筛选/批量操作场景
- `ObjectPage` → 字段组/校验/保存/取消场景
- `AssociationPanel` → 关联对象/添加/移除/批量场景
- `ImportDialog` → 上传/预览/校验/导入场景
- `ExportDialog` → 字段选择/格式选择/下载场景
- `ValueHelpField` → 弹窗/搜索/选择/筛选场景
- `EnumSelect` → 懒加载/缓存/搜索场景

### 2.5 核心用户故事 (User Story Mapping)

**8 大用户故事** (覆盖 80% 业务价值):

| ID | 角色 | 故事 | 优先级 |
|----|------|------|--------|
| US-01 | 架构师 | 上传 Excel → 生成应用架构图 → 导出 PNG/SVG | P0 |
| US-02 | 架构师 | 在架构数据管理中维护业务对象、关系 | P0 |
| US-03 | 管理员 | 创建用户/角色/用户组,并分配权限 | P0 |
| US-04 | 管理员 | 配置数据权限(按角色/按维度范围) | P0 |
| US-05 | 架构师 | 配置枚举类型,供业务对象引用 | P1 |
| US-06 | 管理员 | 查看审计日志,追溯所有变更 | P0 |
| US-07 | 架构师 | 使用条件规则配置动态权限 | P1 |
| US-08 | 运维 | 调度任务、查看 AI 异步任务 | P2 |

---

## 第三部分:E2E 测试矩阵 (Coverage Matrix)

### 3.1 分层测试金字塔

```
                    /\
                   /  \
                  / E2E \         10-20 用例 (本方案重点)
                 / (本方) \
                /----------\
               / 集成测试  \       已有 (e2e/features/*.spec.js)
              /   (40+)    \
             /--------------\
            /  单元测试 (单)  \    已有 (src/**/__tests__)
           /------------------\
          / E2E 子流程 (深入)   \  建议新增 (10-15 个深度流程)
         /----------------------\
```

### 3.2 必做场景 (Smoke) - 7 个

> 必须 100% 通过,部署前必跑

| ID | 场景 | 步骤 | 期望 |
|----|------|------|------|
| S01 | 用户登录/登出 | 输入 admin → 登录 → 工作台 | 看到工作台 |
| S02 | 工作台快捷入口 | 登录 → 点击 "进入产品管理" | 进入产品列表 |
| S03 | 架构数据加载 | 选产品+版本 → 进入架构数据 | 看到 5 个 tab |
| S04 | 业务对象列表 | 业务对象 tab → 看到表格 | 至少 1 行数据 |
| S05 | 详情抽屉打开 | 点击业务对象行 | 看到详情侧滑 |
| S06 | 审计日志可访问 | 访问系统管理 → 日志 | 看到日志列表 |
| S07 | 登出回登录页 | 退出登录 | 看到登录表单 |

### 3.3 核心场景 (Features) - 20 个

> 覆盖 80% 业务,产品迭代验证

| 编号 | 业务域 | 场景 | 关键步骤 | 已有 spec | 待办 |
|------|--------|------|----------|-----------|------|
| F01 | 架构图 | Excel 导入 → 6 步向导 → 生成图 | 上传/选中心/选关系/选类型/配置/展示 | `diagram.spec.js` | **需补全 6 步** |
| F02 | 架构图 | 导出 (PNG/SVG/JSON) | 在展示步 → 选格式 → 下载 | ❌ | **新增** |
| F03 | 架构图 | 布局切换 (Dagre/ELK) | 在配置步 → 切布局 → 重渲 | ❌ | **新增** |
| F04 | 架构数据 | 业务对象 CRUD (新建/编辑/删除) | 工具栏新建 → 抽屉填表 → 保存 → 列表有 | `arch-data-crud.spec.js` | **需加深** |
| F05 | 架构数据 | 服务模块 CRUD | 同 F04 模式 | `arch-data-crud.spec.js` | **需加深** |
| F06 | 架构数据 | 关系配置 (1:N/N:N) | 业务对象详情 → 添加关联 | `arch-data-crud.spec.js` | **需加深** |
| F07 | 架构数据 | 多 Tab 联动 (业务对象 → 关系 → 服务模块) | 切 tab 验证上下文保持 | ❌ | **新增** |
| F08 | 架构数据 | 导入 Excel (单对象/全局) | 工具栏导入 → 上传文件 → 校验 | `import-export.spec.js` | **需加深** |
| F09 | 架构数据 | 导出 Excel (单对象/全局) | 行操作 → 导出 → 下载 | `import-export.spec.js` | **需加深** |
| F10 | 产品/版本 | 产品 CRUD | 工具栏新建 → 表单 → 保存 | `product-crud.spec.js` | **需加深** |
| F11 | 产品/版本 | 版本管理 (新增/激活/历史) | 产品详情 → 版本 tab → 操作 | `product-version.spec.js` | **需加深** |
| F12 | 权限 | 用户 CRUD | 用户 tab → 工具栏 → 抽屉 | `user-role.spec.js` | **需加深** |
| F13 | 权限 | 角色 CRUD + 权限分配 | 角色 tab → 详情 → 权限矩阵 | `role-permission-center.spec.js` | **需加深** |
| F14 | 权限 | 用户组 CRUD + 成员管理 | 用户组 tab → 详情 → 添加成员 | `user-group-detail.spec.js` | **需加深** |
| F15 | 权限 | 数据权限配置 (条件规则) | 角色 → 条件规则 → 配置维度 | `condition-rule-dialog.spec.js` | **需加深** |
| F16 | 权限 | 权限 Explainer (为什么有这个权限) | 角色详情 → 权限来源分析 | `permission-explainer.spec.js` | 已覆盖 |
| F17 | 业务配置 | 枚举类型 CRUD | 业务配置 tab → 新建 → 填值 | `enum-management.spec.js` | **需加深** |
| F18 | 审计 | 日志查看 (按对象/按动作/按级别) | 系统管理 → 日志 → 筛选 | 10+ spec | 已覆盖 |
| F19 | 审计 | 日志详情 (变更 diff) | 点击日志 → 抽屉 | `audit-log-detail.spec.js` | **需加深** |
| F20 | 个人 | 账户设置 (个人资料/改密) | 用户菜单 → 账户设置 | `auth.smoke.spec.js` | **需补全** |

### 3.4 高级场景 (Advanced) - 10 个

> 性能/安全/兼容性,周级回归

| 编号 | 类别 | 场景 | 关键点 |
|------|------|------|--------|
| A01 | 性能 | 1000 行表格渲染 | 1000 行 < 3s 渲染完成 |
| A02 | 性能 | 5 Tab 快速切换 | 切 tab < 500ms,无白屏 |
| A03 | 性能 | 大量筛选器组合 | 7 个筛选器联动 < 1s |
| A04 | 安全 | XSS 注入测试 (在文本字段输入 `<script>`) | 不应执行 |
| A05 | 安全 | 越权访问 (用 user 角色访问 admin 路由) | 重定向到工作台 |
| A06 | 兼容 | 浏览器兼容 (Chrome/Firefox/Edge) | 主要功能可用 |
| A07 | 可访问 | 键盘导航 (Tab 键/Enter/Space) | 核心流程可走通 |
| A08 | 可观测 | 网络异常 (断网/慢网) | 友好错误提示 |
| A09 | 状态 | 重复操作防护 (双击保存) | 不重复提交 |
| A10 | 状态 | 会话过期 (token 失效) | 跳转登录页 |

### 3.5 跨业务流场景 (E2E Sub-flow) - 8 个

> 模拟真实用户一天的工作流,确保跨模块协作

| 编号 | 场景 | 步骤 | 业务价值 |
|------|------|------|----------|
| SF-01 | **新员工入职** | admin 创建用户 → 分配角色 → 验证菜单可见性 | 权限核心流程 |
| SF-02 | **权限变更审计** | 角色新增权限 → 查看审计日志 → 看到变更 | 审计可追溯 |
| SF-03 | **产品发布** | 新建产品 → 新建版本 → 激活版本 → 验证架构数据切换 | 版本管理 |
| SF-04 | **数据导入完整流程** | 下载模板 → 填数据 → 上传 → 校验 → 导入成功 | 业务核心 |
| SF-05 | **架构图生成完整** | 选中心范围 → 配置 → 生成图 → 调整布局 → 导出 | 核心输出 |
| SF-06 | **业务对象关系维护** | 新建 BO → 添加关联 BO → 设置关系类型 → 查看关系图 | 关系管理 |
| SF-07 | **枚举管理完整** | 新建枚举类型 → 添值 → 在 BO 中引用 → 验证下拉 | 配置管理 |
| SF-08 | **任务调度完整** | 新建定时任务 → 触发 → 查看执行记录 → 验证结果 | 运维流程 |

---

## 第四部分:核心场景详细用例 (Detailed Test Cases)

### TC-F01: 架构图生成完整流程 (US-01)

```
优先级: P0
前置条件: admin 已登录,产品+版本已存在,Excel 模板已就绪
类型: smoke (P0 简化版) + feature (P0 完整版)
```

**步骤**:

1. 登录 → 工作台
2. 点击 "架构图" 菜单
3. 验证 6 步骤导航器显示
4. **Step 0 (导入)**: 上传 Excel 文件 `business_objects_demo.xlsx`
   - 预期: 步骤 0 出现 "下一步" 按钮可点
   - 验证: 文件名显示
5. 点击 "下一步" → 进入 Step 1 (中心)
6. **Step 1 (中心)**: 选择中心域 "财务云"
   - 预期: 选中后高亮
   - 验证: 中心域列表显示已选
7. 点击 "下一步" → Step 2 (关系)
8. **Step 2 (关系)**: 选择 "依赖" 关系类型
9. 点击 "下一步" → Step 3 (类型)
10. **Step 3 (类型)**: 选择 "应用架构图 (AA)"
11. 点击 "下一步" → Step 4 (配置)
12. **Step 4 (配置)**: 选 "按域分组" + "ELK 布局"
13. 点击 "下一步" → Step 5 (展示)
14. **Step 5 (展示)**: 验证 Mermaid SVG 已渲染
    - 验证: SVG 元素数 > 5
    - 验证: 节点含业务对象名称
15. 点击 "导出" → 选 PNG → 下载
    - 验证: 文件下载成功,大小 > 10KB

**断言**:

```javascript
// 语义断言,非硬编码
expect(page.locator('.mermaid svg')).toBeVisible()
expect(await page.locator('.mermaid svg .node').count()).toBeGreaterThan(5)

// 业务断言
const svgText = await page.locator('.mermaid svg').textContent()
expect(svgText).toMatch(/财务|应收|应付/)  // 业务名称存在
```

---

### TC-F04: 业务对象 CRUD 完整流程 (US-02)

```
优先级: P0
前置条件: admin 登录,产品+版本已选
```

**步骤**:

1. 导航到 `/system/archdata?productId=1&versionId=1`
2. 等待 "业务对象" tab 默认显示
3. **创建**:
   - 工具栏点击 "新建"
   - 抽屉打开,填字段:
     - 编码: `e2e_bo_{uuid}`
     - 名称: `E2E测试业务对象`
     - 所属子域: 选择 "财务"
   - 点击 "保存"
   - 断言: 出现 success message
   - 断言: 列表新增一行
4. **读取**:
   - 点击新建行 → 抽屉打开
   - 断言: 字段值正确
5. **更新**:
   - 抽屉内点 "编辑"
   - 修改名称为 `E2E测试-已修改`
   - 保存
   - 关闭抽屉
   - 断言: 列表行名称已更新
6. **关联关系**:
   - 在业务对象详情 → "关联" tab
   - 添加关联业务对象 `e2e_target_{uuid}`
   - 保存
   - 断言: 关联 tab 显示 1 条
7. **删除**:
   - 在列表勾选新建的 BO
   - 工具栏 "删除" → 确认对话框 → 确认
   - 断言: 列表行消失
   - 断言: 关联 tab 同步删除

**异常场景 (Negative)**:

- **N1**: 编码重复 → 期望出现 "编码已存在" 错误
- **N2**: 必填字段为空 → 期望字段红框 + 提示
- **N3**: 关联不存在对象 → 期望搜索无结果
- **N4**: 删除被引用对象 → 期望提示 "存在关联,无法删除"

**数据清理**: 测试结束自动 track 清理

---

### TC-F12 + F13: 用户角色权限完整流程 (US-03)

```
优先级: P0
```

**步骤**:

1. 导航到 `/user-permission` (用户 tab 默认)
2. **创建用户**:
   - 新建用户 `e2e_user_{uuid}` / 邮箱 / 密码
   - 保存 → 列表有
3. **创建角色**:
   - 切到 "角色" tab
   - 新建 `e2e_role_{uuid}`
   - 保存
4. **分配权限**:
   - 点击新角色 → 详情
   - 权限矩阵: 勾选 "架构数据-查看"
   - 保存
5. **用户分配角色**:
   - 回到用户 tab
   - 编辑新建用户
   - "角色" 多选 → 选新建角色
   - 保存
6. **创建用户组**:
   - 切到 "用户组" tab
   - 新建 `e2e_group_{uuid}`
   - 添加成员 (刚创建的用户)
   - 保存
7. **验证**:
   - 用新用户登录 (`dev-login?username=e2e_user_xxx`)
   - 验证: 看不到 "产品管理" 菜单
   - 验证: 看到 "架构数据" 菜单
8. **审计验证**:
   - 用 admin 登录
   - 进入审计日志
   - 筛选: 对象=user, 动作=CREATE
   - 断言: 看到刚才创建用户的日志

**清理**: 自动 track 全部清理

---

### TC-SF-01: 新员工入职完整流程 (跨业务域)

```
优先级: P0
覆盖: 用户/角色/权限/审计
业务价值: 验证跨模块协作
```

**步骤 (一气呵成)**:

```
1. 登录 admin
2. 创建角色 "e2e_role_architect_{uuid}" (架构师)
3. 角色权限配置:
   - 架构数据-查看 ✓
   - 架构图-生成 ✓
   - 产品管理-查看 ✓
4. 创建用户 "e2e_employee_{uuid}"
5. 用户关联角色 (步骤 3 创建的)
6. 登出
7. 用新用户 dev-login
8. 验证菜单可见性:
   - 看到: 工作台、架构数据、架构图 ✓
   - 看不到: 系统管理、用户权限 ✓
9. 进入架构数据 → 看到 5 tab (但编辑按钮禁用)
10. 尝试进入产品管理 → 403 或重定向
11. 登出
12. 用 admin 重新登录
13. 审计日志 → 筛选: 对象=user → 看到刚才 CREATE 日志
14. 全部清理
```

**关键断言**:

```javascript
// 跨域一致性断言
const menuItems = await page.locator('.app-side-nav .nav-item').allTextContents()
expect(menuItems.some(t => t.includes('架构数据'))).toBe(true)
expect(menuItems.some(t => t.includes('系统管理'))).toBe(false)
```

---

### TC-F15: 条件规则配置 (US-07, 高级)

```
优先级: P1
前置条件: 至少 2 个 BO, 1 个用户组
```

**步骤**:

1. 进入角色详情 → "条件规则" tab
2. 新建规则:
   - 名称: "e2e_rule_finance_only"
   - 条件表达式: `domain.code == 'finance'`
3. 验证: 表达式解析正确 (UI 显示已解析)
4. 保存
5. 验证: 规则出现在列表
6. 编辑规则 → 改表达式
7. 删除规则 → 确认
8. **联动测试**:
   - 用该角色用户登录
   - 验证: 只能看到 domain=finance 的 BO

---

### TC-F08 + F09: 导入导出完整流程 (核心)

```
优先级: P0
```

**导出步骤**:
1. 进入架构数据 → 业务对象 tab
2. 单行操作 → "导出 JSON"
3. 验证: 文件下载,JSON 合法,字段齐全
4. 全选 → 工具栏 "批量导出"
5. 验证: 导出文件含所有选中行

**导入步骤**:
6. 下载模板
7. 模板填数据
8. 工具栏 "导入" → 上传
9. 验证: 导入预览显示新行
10. 确认导入
11. 验证: 列表新增

**异常场景**:
- N1: 文件格式错误 → 期望友好提示
- N2: 必填字段缺失 → 期望高亮错误行
- N3: 重复导入 → 期望 "覆盖/跳过" 选择

---

### TC-A04: XSS 安全测试 (高级)

```
优先级: P1
前置条件: 任一文本输入字段
```

**步骤**:
1. 进入任一对象新建
2. 在 "名称" 字段输入 `<script>alert('xss')</script>`
3. 保存
4. 验证:
   - 不应弹窗 (XSS 阻止)
   - 字段值应被转义显示为文本
5. 列表搜索 `&lt;script&gt;` 验证转义存储

**断言**:

```javascript
// 验证未执行脚本
let alertFired = false
page.on('dialog', async d => { alertFired = true; await d.dismiss() })
// ... 操作 ...
expect(alertFired).toBe(false)

// 验证显示转义文本
const cellText = await page.locator('.el-table__row:has-text("&lt;")').first().textContent()
expect(cellText).toContain('&lt;script&gt;')
```

---

## 第五部分:AI 自动化生成测试场景的实践指引

### 5.1 5 步 AI 自动生成工作流

```
┌─────────────────────────────────────────────────────────────┐
│  Step 1: 自动发现 (Discovery)                                 │
│  → 扫描 router/menu/schemas/components                       │
│  → 生成 coverage-gap.json (哪些场景未覆盖)                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Spec 解析 (Spec Parsing)                             │
│  → 读取 docs/specs/*.md / docs/需求文档.md                    │
│  → LLM 提取: 用户故事 + 验收条件 (Gherkin-like)               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 3: 用例草稿生成 (Test Draft)                            │
│  → 输入: 用户故事 + 路由 + 已覆盖 spec                        │
│  → 输出: 详细 spec 草稿 (Given/When/Then)                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 4: 代码生成 (Code Gen)                                 │
│  → 输入: spec 草稿 + POM + helpers                           │
│  → 输出: *.spec.js (符合项目 E2E 铁律)                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 5: 自愈验证 (Self-heal)                                │
│  → 执行测试                                                 │
│  → 失败时 AI 修复选择器/等待/断言                            │
│  → 提交修复到 spec.md 作为知识沉淀                            │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 标准化 Prompt 模板 (4 大支柱)

```markdown
# E2E Test Generator Prompt for ArchWorkspace

## Context (背景)
- Project: ArchWorkspace (Vue 3 + Element Plus + Pinia)
- Backend: Flask + SQLite
- Auth: httpOnly cookie (dev-login for E2E)
- Test Infra: Playwright + POM (GenericListPage, ArchDataPage, DetailDrawerPage)
- 已存在 helpers: auth.js, global.setup.js, data-finder.js, test-isolation.js

## User Actions (用户操作)
场景: {场景名}
步骤:
1. 导航到 {URL}
2. 在 {selector} 输入 {value}
3. 点击 {button}
4. 验证 {expected}

## Success Criteria (成功标准)
- [ ] 成功消息出现
- [ ] 列表新增/更新/删除
- [ ] URL 跳转正确
- [ ] 抽屉/Drawer 状态正确
- [ ] 字段值正确持久化

## Edge Cases (边界场景)
- 必填字段为空 → 字段验证
- 数据重复 → 唯一性约束
- 关联对象不存在 → 友好错误
- 取消操作 → 状态回滚
- 重复点击 → 防止重复提交

## Output Rules (输出规则)
1. **MUST** use Page Object Model (导入 GenericListPage/ArchDataPage/DetailDrawerPage)
2. **MUST** use testInfo.attach() 截图,不用 'on'
3. **MUST** use `getByRole` / `getByText` / data-testid (no CSS class)
4. **MUST NOT** use `waitForLoadState('networkidle')`
5. **MUST NOT** use `waitForTimeout()` (用 `waitForResponse`/`waitForApi`)
6. **MUST** use UUID 命名 + test-isolation.track() 清理
7. **MUST** use data-finder.productWithVersion() 而非硬编码 ID
8. **MUST** include 1 positive + 1 negative case
```

### 5.3 AI 自动发现脚本 (复用 Part 2.3)

```python
# scripts/discover_e2e_gaps.py
"""
扫描现有测试 + 元数据,生成 E2E coverage gap 报告
"""
import json, re
from pathlib import Path

def scan_existing_specs():
    """扫描已存在的 spec 文件,提取覆盖的路由/对象"""
    spec_dir = Path('e2e/features')
    covered = set()
    for spec in spec_dir.glob('*.spec.js'):
        content = spec.read_text(encoding='utf-8')
        # 提取测试 ID
        test_ids = re.findall(r"test\(['\"]([CMSAF]\d+):", content)
        covered.update(test_ids)
    return covered

def scan_schemas():
    """扫描元数据,提取应被覆盖的对象"""
    schemas = Path('meta/schemas')
    objects = []
    for f in schemas.glob('*.yaml'):
        if f.name.startswith('_'): continue
        data = __import__('yaml').safe_load(f.read_text(encoding='utf-8'))
        if data.get('id'):
            objects.append({
                'id': data['id'],
                'has_list': 'list' in data,
                'has_crud': all(k in data for k in ('list', 'detail')),
            })
    return objects

def generate_gap_report():
    covered = scan_existing_specs()
    objects = scan_schemas()
    # ... 生成 gap 报告 ...
    print(f'已覆盖: {len(covered)} 个 spec')
    print(f'业务对象总数: {len(objects)}')
    print(f'未覆盖: {sum(1 for o in objects if o["id"] not in str(covered))}')

if __name__ == '__main__':
    generate_gap_report()
```

### 5.4 自动化生成 (LLM Call 示例)

```python
# scripts/ai_generate_spec.py
"""
输入: 场景描述 + Prompt 模板
输出: spec.js 文件
"""
import anthropic
from pathlib import Path

PROMPT_TEMPLATE = Path('.trae/prompts/e2e-generator.md').read_text()

def generate_spec(scenario: dict) -> str:
    client = anthropic.Anthropic()
    prompt = PROMPT_TEMPLATE.replace('{scenario}', json.dumps(scenario, ensure_ascii=False))
    msg = client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=4000,
        messages=[{'role': 'user', 'content': prompt}]
    )
    # 提取 code block
    import re
    code = re.search(r'```javascript\n([\s\S]+?)\n```', msg.content[0].text)
    return code.group(1) if code else msg.content[0].text

# 调用
scenario = {
    'name': 'TC-F12: 用户 CRUD',
    'user_story': '管理员创建/编辑/删除用户',
    'route': '/user-permission',
    'tab': 'users',
    'poms': ['GenericListPage', 'DetailDrawerPage'],
}
spec_code = generate_spec(scenario)
Path(f'e2e/features/ai-user-crud.spec.js').write_text(spec_code)
```

### 5.5 自愈循环 (Healer Agent)

```python
# scripts/ai_heal_failed_tests.py
"""
失败 spec → AI 修复 → 重跑
"""
def heal_test(failed_spec: str, error_log: str) -> str:
    # 1. 解析失败原因
    diagnosis = diagnose_error(error_log)
    # 2. 修复策略
    if 'locator' in diagnosis:
        fix = ai_fix_locator(failed_spec, error_log)
    elif 'timeout' in diagnosis:
        fix = ai_fix_timing(failed_spec, error_log)
    elif 'assertion' in diagnosis:
        fix = ai_fix_assertion(failed_spec, error_log)
    return fix
```

### 5.6 与现有基础设施集成

**已具备** (无需新做):
- ✅ Playwright + 3 个 project (smoke/features/permissions)
- ✅ POM (GenericListPage, ArchDataPage, DetailDrawerPage)
- ✅ global-setup (一次登录,所有 project 共享)
- ✅ data-finder (智能查找产品+版本)
- ✅ test-isolation (自动清理)
- ✅ withStep (自动截图+计时)
- ✅ network-waiter (基于 API 等待)

**需要新增** (基于本方案):

1. **`e2e/scenarios/` 目录** (业务场景化)
   - `e2e/scenarios/cross-flow/` (跨业务流,8 个 SF)
   - `e2e/scenarios/negative/` (异常场景,10+ 个)
   - `e2e/scenarios/security/` (安全,5 个)
   - `e2e/scenarios/performance/` (性能,3 个)

2. **增强的 POM**
   - `e2e/page-objects/WorkspacePage.js` (工作台)
   - `e2e/page-objects/DiagramPage.js` (架构图 6 步向导)
   - `e2e/page-objects/UserPermissionPage.js` (用户/角色/用户组 tab 容器)
   - `e2e/page-objects/AuditLogPage.js` (审计日志页)

3. **`scripts/ai-discover-e2e-gaps.py`** (覆盖率 gap 报告)
4. **`scripts/ai-generate-spec.py`** (LLM 生成 spec)
5. **`scripts/ai-heal-spec.py`** (失败自愈)

---

## 第六部分:实施路线图

### Phase 1: 基础补全 (1 周)

| 任务 | 工作量 | 产出 |
|------|--------|------|
| 补全 F01-F11 现有 spec 的深度 | 3 天 | 11 个 spec 加强 |
| 新增 SF-01 ~ SF-04 跨域场景 | 2 天 | 4 个 e2e/scenarios/cross-flow/*.spec.js |
| 新增 4 个 POM (WorkspacePage/DiagramPage/UserPermissionPage/AuditLogPage) | 1 天 | 4 个新 POM |

### Phase 2: 高级场景 (1 周)

| 任务 | 工作量 | 产出 |
|------|--------|------|
| 高级场景 A01-A10 | 3 天 | 10 个 e2e/scenarios/*/ |
| 安全测试 A04-A05 (XSS + 越权) | 1 天 | 2 个安全 spec |
| 性能基准 | 1 天 | 1 个 perf spec |
| 跨域 SF-05 ~ SF-08 | 2 天 | 4 个跨域 spec |

### Phase 3: AI 自动化 (1 周)

| 任务 | 工作量 | 产出 |
|------|--------|------|
| `scripts/ai-discover-e2e-gaps.py` | 1 天 | gap 报告工具 |
| `scripts/ai-generate-spec.py` + Prompt 模板 | 2 天 | 自动生成工具 |
| `scripts/ai-heal-spec.py` | 2 天 | 自愈工具 |
| CI 集成 | 1 天 | `.github/workflows/e2e-ai.yml` |

### 总计: 3 周,18 个新 spec,4 个新 POM,3 个 AI 工具

---

## 第七部分:参考与延伸

### 7.1 行业最佳实践参考

| 来源 | 关键 takeaway |
|------|---------------|
| [Augment Code - Why AI Coding Agents Fail E2E Tests](https://www.augmentcode.com/guides/why-ai-coding-agents-fail-e2e-tests) | 5 大失败模式 + 契约修复 |
| [TestDino - 5 Methods to Automate Playwright with AI](https://testdino.com/blog/ai-write-playwright-tests) | MCP / CLI / Test Agents / Skills 对比 |
| [Ivern AI - QA Squad Architecture](https://ivern.ai/blog/ai-agents-for-software-testing-qa-automation-2026) | 多 Agent 协作:Writer/Runner/Triage/Reporter |
| [TestDriver - Auto Test Case Generation](https://testdriver.ai/articles/generate-test-cases-automatically) | 4 大支柱 Prompt + 实用模板 |
| [Shiplight - 8 AI Testing Tools 2026](https://www.shiplight.ai/blog/ai-testing-tools-auto-generate-test-cases) | 工具对比 (testRigor, Mabl, Shiplight) |
| [Mark AI Code - Use AI to Write Playwright in 20 Min](https://markaicode.com/ai-playwright-tests-complex-ui/) | DOM 快照 + 约束 Prompt |
| [QA Skills - AI Test Generation Guide](https://qaskills.sh/blog/ai-test-generation-tools-guide) | Skill-augmented AI (3x 质量提升) |

### 7.2 项目内部参考

| 文档 | 路径 |
|------|------|
| E2E 简化方案 v2 | `e2e/TEST_SIMPLIFICATION_PLAN.md` |
| E2E 实施报告 | `e2e/TEST_SIMPLIFICATION_REPORT.md` |
| E2E 铁律 | `.trae/rules/e2e-testing.md` |
| 浏览器测试验证 | `.trae/rules/browser-test-verification.md` |
| AI 内容防护 | `.trae/rules/ai-content-protection.md` |
| 元数据 schema | `meta/schemas/*.yaml` |
| 需求文档 | `docs/需求文档.md` |
| 架构设计 | `docs/架构设计文档.md` |
| POM 基础 | `e2e/page-objects/` |
| Helper 库 | `e2e/helpers/` |

### 7.3 后续可拓展方向

1. **基于 Trace 的回归分析**: 用 TestTelemetry 收集操作链,自动识别"未被测试覆盖"的高频操作
2. **变更驱动测试 (CDC)**: Git diff → 推断哪些 spec 需要重跑
3. **AI 测试评分 (Mutation Testing)**: 自动注入 fault,验证 spec 能否捕获
4. **跨浏览器视觉回归**: Percy / Playwright Trace + 截图比对

---

## 附录 A:已具备的 E2E 资产清单

### A.1 测试目录结构 (本项目)

```
e2e/
├── .auth/                      # 共享登录态
│   ├── admin.json
│   └── user.json
├── helpers/                    # 辅助函数
│   ├── auth.js                 # 登录/导航/权限 (主)
│   ├── global.setup.js         # 一次登录
│   ├── auto-fixtures.js        # test 扩展
│   ├── auto-trace.js           # withStep 自动截图
│   ├── data-finder.js          # 智能查找数据
│   ├── test-isolation.js       # 自动清理
│   ├── network-waiter.js       # API 智能等待
│   └── menu-navigator.js       # 菜单驱动导航
├── page-objects/               # POM
│   ├── GenericListPage.js      # 通用列表
│   ├── ArchDataPage.js         # 架构数据
│   └── DetailDrawerPage.js     # 详情抽屉
├── features/                   # 功能测试 (40+)
│   ├── business-object-crud.spec.js
│   ├── user-role.spec.js
│   ├── audit-log*.spec.js
│   ├── ...
├── smoke/                      # 冒烟测试
│   ├── auth.smoke.spec.js
│   └── arch-data.smoke.spec.js
└── specs/                      # 探索性
```

### A.2 关键 POM 方法 (已实现)

`GenericListPage`:
- `waitForReady()`, `getRowCount()`, `getColumnHeaders()`
- `findRow(text)`, `clickRowByText(text)`, `expectRowExists()`, `expectRowNotExists()`
- `checkRow(text)`, `search(keyword)`, `expectEmpty()`

`ArchDataPage` (继承 GenericListPage):
- `openTab('businessObject' | 'serviceModule' | ...)`
- `openDetailByCode(code)`, `clickNew()`

`DetailDrawerPage`:
- `clickEdit()`, `fillFieldByLabel()`, `clickSave()`, `clickDelete()`
- `expectSuccessMessage()`, `close()`

### A.3 关键 Helper 函数

`auth.js`:
- `login(page)`, `setAdminPermissions(page)`
- `navigateAndWaitForPage(page, url)`
- `findProductWithVersion(page)`
- `attachAndVerifyScreenshot(page, testInfo, name)`
- `checkPageHealth(page)`, `assertHealthy(page)`
- `waitForStable(page, selector)`, `waitForDomExists(page, selector)`

---

## 附录 B:本方案输出统计

| 类别 | 数量 |
|------|------|
| 必做 Smoke 场景 | 7 |
| 核心 Features 场景 | 20 |
| 高级 Advanced 场景 | 10 |
| 跨业务流 SF 场景 | 8 |
| 详细测试用例 (TC) | 8 (本方案中详细) |
| 缺失场景 (待补) | 25+ |
| 业务对象数 (元数据) | 29 |
| 已覆盖业务对象 | ~10 |
| 覆盖率 | ~35% |
| 目标覆盖率 | 80%+ |

---

**总结**: 本项目已具备企业级 E2E 基础 (POM + global-setup + data-finder + test-isolation),但核心场景覆盖度约 35%。按本方案的 3 周路线图,可达 80%+ 业务场景覆盖 + AI 自动化发现/生成/自愈闭环,实现"AI Coding 最佳实践"在 E2E 领域的完整落地。
