# Spec: E2E 测试体系重构

## 1. 背景与目标

### 1.1 背景

当前 excel-to-diagram 项目的 E2E 测试存在以下严重问题：

- **测试卡死**：`waitForLoadState('networkidle')` 在 Vue SPA 中因持续 API 请求永远无法完成，导致测试永久挂起
- **截图无效**：Playwright 自动截图在 test 结束后捕获，此时页面已回退到首页，所有截图内容相同
- **权限不同步**：修改 `localStorage` 后 Pinia store 未更新，导致权限相关测试失败
- **碎片化严重**：308 个 case 中大量是单操作验证（如"页面应加载"、"应显示侧边栏"），每个 case 独立登录+导航，运行时间约 25 分钟
- **API/UI 混杂**：纯 API 测试（仅用 `request`）混在 UI 测试文件中，不必要地启动了浏览器
- **命名混乱**：部分 describe 使用无意义哈希值（如 `group_4dxzy5`），可读性差
- **覆盖深度不足**：架构数据管理仅验证页面导航，未覆盖 CRUD、过滤、范围选择、导入导出等核心功能；枚举管理未覆盖 inline edit 和 system locked 逻辑；审计日志未验证操作审计

### 1.2 业务目标

- 建立 **功能 → 用例 → Playwright** 三层映射的 E2E 测试体系
- 实现 **冒烟测试**（核心主流程）与 **功能测试**（完整覆盖）的分层运行
- 将测试运行时间从 ~25 分钟降至冒烟 ~3 分钟 / 全量 ~9 分钟
- 消除所有已知的稳定性问题（卡死、截图、权限、导航）
- 覆盖用户核心业务场景的深度验证（CRUD、过滤、导入导出、权限、审计、ValueHelp）

### 1.3 用户/涉众目标

| 涉众 | 目标 |
|------|------|
| 开发者 | 每次提交快速验证核心流程未破坏（~3 分钟） |
| QA | 每日全量回归验证所有功能（~8 分钟），包括 CRUD、过滤、导入导出、权限配置 |
| 项目经理 | 测试报告截图真实反映页面状态，可读性强 |

## 2. 需求类型概览

| 类型 | 适用 | 证据来源 |
|------|------|---------|
| 业务需求 | 是 | 测试体系需支撑持续交付质量保障 |
| 用户/涉众需求 | 是 | 开发者/QA/PM 对测试效率和可信度的要求 |
| 解决方案需求 | 是 | 三层架构、分层运行、共享组件操作层 |
| 功能需求 | 是 | 10 个测试场景的具体验证点 |
| 非功能需求 | 是 | 稳定性、效率、可维护性 |
| 外部接口需求 | 是 | Playwright 配置 |
| 过渡需求 | 是 | 从 16 文件 308 case 迁移到新体系 |

## 3. 功能需求

### FR-001: 三层映射架构

- **描述**：系统必须建立 功能模块 → 测试场景 → Playwright 组织 的三层映射关系，每层职责清晰
- **验收标准**：
  - 第1层：5 大功能域（认证与账户、架构数据、用户权限、业务配置、系统管理）覆盖所有业务模块
  - 第2层：10 个核心测试场景，每个场景是完整的业务流程而非碎片操作
  - 第3层：Playwright 按 smoke/features 两层目录组织
- **优先级**：Must
- **类型映射**：解决方案需求
- **来源**：用户讨论 + 代码分析

### FR-002: 冒烟测试分层

- **描述**：系统必须支持独立运行冒烟测试，仅覆盖 P0 核心主流程
- **验收标准**：
  - 冒烟测试包含：认证与账户设置（S01）、架构数据页面导航与列表查看（S02）
  - 冒烟测试可在 `--project=smoke` 下独立运行
  - 冒烟测试运行时间 ≤ 3 分钟
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：用户需求

### FR-003: 功能测试分层

- **描述**：系统必须包含 P1/P2 功能测试，覆盖所有业务模块的完整功能验证
- **验收标准**：
  - P1 测试：架构数据 CRUD/过滤/导入导出、用户权限、角色权限、架构图
  - P2 测试：枚举管理（含 inline edit）、审计日志
  - 功能测试可在 `--project=features` 下独立运行
  - 全量测试运行时间 ≤ 8 分钟
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：用户需求

### FR-004: 流程化测试用例

- **描述**：每个测试用例必须是完整的业务流程，而非单个操作验证
- **验收标准**：
  - 同一页面/功能的多个验证点合入同一个 case
  - 每个 case 内共享登录状态和导航上下文
  - 总 case 数从 308 降至 ~23（减少 93%）
  - 每个 case 包含 3-10 个验证步骤
- **优先级**：Must
- **类型映射**：解决方案需求
- **来源**：用户讨论（arch-data 融合实践验证）

### FR-005: 共享组件操作层

- **描述**：系统必须提供可复用的组件操作工具函数，替代独立的 UI 通用功能测试文件
- **验收标准**：
  - 提供 `TableHelper`（等待数据、获取行数、打开抽屉、切换 Tab、行操作菜单）
  - 提供 `FormHelper`（填写字段、提交、验证校验消息）
  - 提供 `SelectorHelper`（选择产品版本、选择下拉选项）
  - 提供 `ScopeTreeHelper`（对象范围勾选、关系范围勾选、备注类型过滤）
  - 提供 `ImportExportHelper`（单对象导出/导入、全局批量导出/导入）
  - `ui-common-functions.spec.js` 的验证逻辑迁移为工具函数
- **优先级**：Should
- **类型映射**：解决方案需求
- **来源**：代码分析

### FR-006: 稳定性保障

- **描述**：系统必须消除所有已知的测试稳定性问题
- **验收标准**：
  - 禁止使用 `waitForLoadState('networkidle')`，全部使用 `domcontentloaded`
  - 禁止 `waitForTimeout` 超过 2000ms，优先使用元素可见性等待
  - 所有 `page.goto()` 使用 `{ waitUntil: 'domcontentloaded' }`
  - 所有导航后等待 `.login-overlay` 消失
  - 测试零卡死（无永久挂起）
- **优先级**：Must
- **类型映射**：非功能需求 → 功能化
- **来源**：用户反馈（"上面又卡住了"）

### FR-007: 截图可靠性

- **描述**：测试截图必须真实反映测试执行时的页面状态
- **验收标准**：
  - 使用 `testInfo.attach()` 在关键步骤手动附加截图
  - 禁止依赖 Playwright 自动截图（`screenshot: 'on'`）
  - 每个流程化 case 在关键验证点附加 1-2 张截图
  - 截图内容必须各不相同（非全部首页）
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：用户反馈（"很多截图都是在首页"、"图片的问题反复很多次了"）

### FR-008: 权限状态同步

- **描述**：测试中修改权限必须同时更新 localStorage 和 Pinia store
- **验收标准**：
  - `setAdminPermissions()` 函数同步更新两者
  - 通过 `window.__pinia._s.get('auth')` 更新 Pinia 状态
  - 所有需要管理员权限的测试使用此函数
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：代码分析 + 用户反馈

### FR-009: 统一导航封装

- **描述**：所有页面导航必须使用统一的封装函数
- **验收标准**：
  - `navigateAndWaitForPage()` 处理 goto + waitUntil + login-overlay 等待
  - 禁止在测试代码中直接使用 `page.goto()` 而不等待页面就绪
  - 导航函数支持 `expectedPath` 参数验证路由正确性
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：代码分析

### FR-010: 测试场景定义

- **描述**：系统必须实现以下 10 个核心测试场景，每个场景包含详细的验证点

---

#### S01: 认证与账户设置（P0 冒烟）

| Case | 验证步骤 |
|------|---------|
| C01: 登录流程验证 | 1. 访问登录页 → 验证登录表单可见; 2. 输入正确凭据登录 → 验证跳转到工作台; 3. 输入错误密码 → 验证错误提示; 4. 登出 → 验证回到登录页 |
| C02: 工作台与导航验证 | 1. 登录后验证工作台页面加载; 2. 验证产品卡片展示; 3. 点击侧边栏菜单 → 验证跳转到对应页面; 4. 验证面包屑导航 |
| C03: 账户设置与密码修改验证 | 1. 打开账户设置弹窗 → 验证个人信息展示; 2. 编辑个人信息 → 保存 → 验证更新; 3. 打开密码修改弹窗 → 填写旧密码/新密码/确认密码; 4. 验证表单校验（密码不一致、旧密码错误）; 5. 提交修改 → 验证成功提示 |

---

#### S02: 架构数据 - 页面导航与对象列表（P0 冒烟）

| Case | 验证步骤 |
|------|---------|
| C04: 页面导航与布局验证 | 1. 导航到 `/system/archdata` → 验证页面加载; 2. 验证全局工具栏（产品/版本选择器、导入/导出/图表/刷新按钮）; 3. 验证左侧范围树面板（对象范围/关系范围/过滤条件）; 4. 验证右侧 Tab 区域 |
| C05: 所有对象列表查看验证 | 1. 选择产品版本 → 等待数据加载; 2. 依次切换 5 个 Tab（领域/子领域/服务模块/业务对象/关系）→ 每个Tab验证表格有数据; 3. 验证表格列定义与预期一致; 4. 验证分页器工作正常 |

---

#### S03: 架构数据 - 业务对象与关系 CRUD（P1）

| Case | 验证步骤 |
|------|---------|
| C06: 业务对象 CRUD 流程 | 1. 切换到业务对象 Tab → 验证列表; 2. 点击"新建"→ 验证 Drawer 打开 → 填写表单（通过 ValueHelp 选择所属服务模块）→ 保存 → 验证列表新增记录; 3. 点击行操作"编辑"→ 修改字段 → 保存 → 验证列表更新; 4. 点击行操作"删除"→ 确认弹窗 → 确认 → 验证列表记录消失; 5. afterAll 清理测试数据 |
| C07: 关系 CRUD 流程 | 1. 切换到关系 Tab → 验证列表; 2. 点击"新建"→ 通过 ValueHelp 弹窗选择源业务对象 → 通过 ValueHelp 选择目标业务对象 → 填写其他字段 → 保存 → 验证列表新增; 3. 编辑关系 → 保存 → 验证更新; 4. 删除关系 → 确认 → 验证删除; 5. afterAll 清理测试数据 |
| C08: ValueHelp 功能验证 | 1. 在业务对象新建表单中 → 点击服务模块字段的 ValueHelp 图标 → 验证 SearchHelpDialog 弹窗打开; 2. 在弹窗中搜索 → 验证搜索结果; 3. 选择一条记录 → 验证回填到表单字段; 4. 在关系新建表单中 → 验证业务对象 ValueHelp 能搜索到刚创建的业务对象 |

---

#### S04: 架构数据 - 过滤查询与范围选择（P1）

| Case | 验证步骤 |
|------|---------|
| C09: 过滤查询与排序验证 | 1. 在搜索框输入关键词 → 验证列表过滤; 2. 点击列头排序 → 验证排序方向切换; 3. 打开高级筛选面板 → 设置筛选条件 → 查询 → 验证结果; 4. 重置筛选 → 验证恢复原始列表 |
| C10: 对象范围与关系范围选择验证 | 1. 展开对象范围面板 → 勾选领域节点 → 验证右侧列表按领域过滤; 2. 勾选子领域/服务模块 → 验证跨 Tab 过滤联动; 3. 展开关系范围面板 → 勾选关系分类 → 验证关系 Tab 按分类过滤; 4. 展开过滤条件面板 → 选择备注类型 → 验证对象和关系列表按备注类型过滤; 5. 清空所有范围选择 → 验证恢复完整列表 |

---

#### S05: 架构数据 - 导入导出（P1）

| Case | 验证步骤 |
|------|---------|
| C11: 单对象导出与导入流程 | 1. 切换到业务对象 Tab → 点击"导出"→ 验证导出弹窗; 2. 选择导出范围（当前页）→ 确认导出 → 验证文件下载; 3. 点击"导入"→ 验证导入弹窗 3 步流程; 4. 上传刚导出的文件 → 选择冲突处理（upsert）→ 校验 → 确认导入 → 验证导入结果统计 |
| C12: 全局批量导出流程 | 1. 点击全局工具栏"导出"按钮 → 验证多类型选择区; 2. 勾选多个对象类型 → 验证级联导出选项; 3. 确认导出 → 验证异步导出进度; 4. 验证导出文件下载 |
| C13: 全局批量导入流程 | 1. 点击全局工具栏"导入"按钮 → 验证多类型选择区; 2. 勾选多个对象类型 → 上传文件 → 选择冲突处理; 3. 校验 → 确认导入 → 验证各类型导入结果统计 |

---

#### S06: 用户角色权限 - CRUD 与关联（P1）

| Case | 验证步骤 |
|------|---------|
| C14: 用户 CRUD 与关联验证 | 1. 导航到用户管理 → 验证列表; 2. 新建用户 → 填写表单 → 保存 → 验证列表新增; 3. 编辑用户 → 修改字段 → 保存; 4. 打开用户详情 → 用户组 Tab → 点击"添加关联"→ AssignmentDialog 选择用户组 → 确认 → 验证关联建立; 5. 移除用户组关联 → 确认弹窗 → 验证移除; 6. afterAll 清理测试数据 |
| C15: 用户组 CRUD 与关联验证 | 1. 导航到用户组管理 → 验证列表; 2. 新建用户组 → 保存 → 验证列表新增; 3. 打开用户组详情 → 成员 Tab → 添加成员 → 验证; 4. 打开用户组详情 → 角色 Tab → 点击"管理关联角色"→ GroupRoleDialog 勾选角色 → 保存 → 验证角色关联; 5. 取消角色关联 → 验证移除; 6. afterAll 清理测试数据 |
| C16: 角色 CRUD 与关联验证 | 1. 导航到角色管理 → 验证列表; 2. 新建角色 → 保存 → 验证列表新增; 3. 编辑角色 → 保存; 4. 打开角色详情 → 用户 Tab → 添加用户关联 → 验证; 5. 打开角色详情 → 用户组 Tab → 添加用户组关联 → 验证; 6. afterAll 清理测试数据 |

---

#### S07: 角色权限配置 - 菜单/功能/数据权限/Owner（P1）

| Case | 验证步骤 |
|------|---------|
| C17: 角色权限配置 - 菜单与功能权限 | 1. 导航到角色权限配置页（`/system/role-permission/:roleId`）→ 验证三栏布局; 2. 验证管理维度选择器加载; 3. 在菜单权限矩阵中勾选菜单 → 验证功能权限状态变化（granted/pending/inactive）; 4. 保存权限 → 验证成功提示 |
| C18: 角色权限配置 - 数据权限与 Owner | 1. 在维度范围面板中添加维度值 → 验证自动推导预览; 2. 配置条件规则 → 验证规则列表更新; 3. 在数据权限配置中添加规则（资源类型/权限级别/继承）→ 保存; 4. 验证 Owner 转移功能（如可测试） |

---

#### S08: 枚举管理 - List/Detail/InlineEdit/Mutability（P2）

| Case | 验证步骤 |
|------|---------|
| C19: 枚举列表与详情验证 | 1. 导航到枚举类型管理 → 验证列表加载; 2. 验证列表列（编码/名称/分类/可维护性/维度数/值数量）; 3. 验证筛选器（版本/类别/描述搜索）; 4. 点击行 → 跳转到详情页 → 验证基本信息/维度配置/枚举值子对象区域 |
| C20: 枚举值 Inline Edit 验证 | 1. 在枚举详情页 → 点击"编辑"按钮进入 inline edit 模式; 2. 验证可编辑字段（name/name_en/sort_order/is_active）显示编辑图标; 3. 验证不可编辑字段（code/is_system）灰显且斜体; 4. 修改可编辑字段 → 验证已修改标记（淡绿色背景）; 5. 点击"保存"→ 验证保存成功; 6. 点击"取消"→ 验证放弃修改 |
| C21: Mutability 逻辑验证 | 1. 选择 `mutability=locked` 的枚举 → 验证无法添加/修改/删除枚举值; 2. 选择 `mutability=extensible` 的枚举 → 验证可添加枚举值但不可删除系统值; 3. 选择 `mutability=mutable` 的枚举 → 验证可自由增删改; 4. 选择 `category=system` 的枚举 → 验证整体不可修改/删除 |

---

#### S09: 审计日志 - 展示与操作审计验证（P2）

| Case | 验证步骤 |
|------|---------|
| C22: 日志列表与筛选验证 | 1. 导航到审计日志页面 → 验证统计卡片（今日操作/安全事件/失败/总数）; 2. 验证日志列表列（时间/类型/级别/操作/对象类型/业务标识/操作人）; 3. 使用筛选器（日志类型/操作类型/对象类型/操作人/时间范围）→ 验证过滤结果; 4. 点击行 → 验证详情抽屉内容 |
| C23: 操作审计验证 | 1. 在架构数据页执行创建操作 → 切换到审计日志 → 验证 CREATE 日志记录; 2. 执行编辑操作 → 验证 UPDATE 日志（含旧值/新值）; 3. 执行删除操作 → 验证 DELETE 日志; 4. 执行关联操作 → 验证 ASSOCIATE/DISSOCIATE 日志; 5. 执行导入导出 → 验证对应操作日志 |

---

#### S10: 架构图生成流程（P1）

| Case | 验证步骤 |
|------|---------|
| C24: 架构图生成验证 | 1. 导航到架构图页面 → 验证 5 步流程; 2. 选择产品版本 → 选择范围 → 选择图表类型 → 配置 → 验证图表展示 |

---

#### S11: 产品版本管理 CRUD（P1）

| Case | 验证步骤 |
|------|---------|
| C25: 产品 CRUD 流程 | 1. 导航到产品管理页面（`/product-management`）→ 验证列表加载; 2. 点击"新建"→ 填写产品表单（名称、编码、描述）→ 保存 → 验证列表新增记录; 3. 点击行操作"编辑"→ 修改字段 → 保存 → 验证列表更新; 4. 点击行操作"删除"→ 确认弹窗 → 确认 → 验证列表记录消失; 5. afterAll 清理测试数据 |
| C26: 版本 CRUD 流程 | 1. 在产品详情中 → 切换到版本 Tab → 验证版本列表; 2. 点击"新建版本"→ 填写版本表单（版本号、描述、状态）→ 保存 → 验证列表新增; 3. 编辑版本 → 保存 → 验证更新; 4. 删除版本 → 确认 → 验证删除; 5. afterAll 清理测试数据 |

**场景汇总**：

| 场景ID | 场景名称 | 优先级 | Case数 | 文件位置 |
|--------|---------|--------|--------|---------|
| S01 | 认证与账户设置 | P0 冒烟 | 3 | smoke/auth.smoke.spec.js |
| S02 | 架构数据 - 页面导航与对象列表 | P0 冒烟 | 2 | smoke/arch-data.smoke.spec.js |
| S03 | 架构数据 - 业务对象与关系 CRUD | P1 | 3 | features/arch-data-crud.spec.js |
| S04 | 架构数据 - 过滤查询与范围选择 | P1 | 2 | features/arch-data-filter.spec.js |
| S05 | 架构数据 - 导入导出 | P1 | 3 | features/arch-data-import-export.spec.js |
| S06 | 用户角色权限 - CRUD 与关联 | P1 | 3 | features/user-permission.spec.js |
| S07 | 角色权限配置 | P1 | 2 | features/role-permission.spec.js |
| S08 | 枚举管理 | P2 | 3 | features/enum-management.spec.js |
| S09 | 审计日志 | P2 | 2 | features/audit-log.spec.js |
| S10 | 架构图 | P1 | 1 | features/diagram.spec.js |
| S11 | 产品版本管理 | P1 | 2 | features/product-version.spec.js |
| **合计** | | | **26** | |

- **验收标准**：
  - 11 个场景全部实现
  - 每个场景包含 1-5 个流程化 case
  - 总 case 数约 26 个
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：用户讨论 + 代码分析

### FR-011: 测试数据工厂

- **描述**：系统必须提供测试数据工厂，统一管理测试所需的前置数据
- **验收标准**：
  - `findProductWithVersion()` 函数从 API 获取可用的产品版本
  - `findEnumByMutability(mutability)` 函数获取指定可维护性的枚举
  - `findRoleWithPermissions()` 函数获取有权限配置的角色
  - 数据不足时优雅 skip 而非 fail
  - 测试数据获取逻辑与测试验证逻辑分离
- **优先级**：Should
- **类型映射**：解决方案需求
- **来源**：代码分析

### FR-012: 测试数据清理

- **描述**：测试中创建的数据必须在 afterAll 中清理，避免污染测试环境
- **验收标准**：
  - CRUD 测试创建的记录在 afterAll 中删除
  - 使用唯一标识（如 `test_${timestamp}`）创建数据，便于清理
  - 清理失败时记录日志但不影响测试结果
- **优先级**：Should
- **类型映射**：解决方案需求
- **来源**：用户确认

## 4. 非功能需求

### NFR-001: 稳定性

- **描述**：测试套件必须零卡死、零误报
- **度量**：连续 5 次全量运行，0 次 permanent freeze，flaky rate < 5%
- **优先级**：Must
- **来源**：用户反馈（"这个问题叠加前面那个问题把整个e2e测试变得无效"）

### NFR-002: 效率

- **描述**：测试运行时间必须满足分层目标
- **度量**：
  - 冒烟测试（2 个场景，5 case）：≤ 3 分钟
  - 全量测试（11 个场景，26 case）：≤ 9 分钟
- **优先级**：Must
- **来源**：用户需求

### NFR-003: 可维护性

- **描述**：测试代码必须结构清晰、命名有意义、可复用
- **度量**：
  - 无无意义命名（如 `group_4dxzy5`）
  - 共享操作通过工具函数复用，无重复的 5+ 行代码块
  - 新增功能模块时，只需新增 1 个 spec 文件 + 1-3 个 case
- **优先级**：Should
- **来源**：代码分析

### NFR-004: 可读性

- **描述**：测试报告必须清晰反映测试内容和结果
- **度量**：
  - 截图内容与测试步骤一一对应
  - case 名称描述完整业务流程
  - skip 原因明确（数据不足、权限不够等）
- **优先级**：Must
- **来源**：用户反馈

## 5. 外部接口需求

### IF-001: Playwright 配置

- **类型**：配置接口
- **端点**：`playwright.config.js`
- **交互**：
  - 支持 `--project=smoke`、`--project=features` 两种运行模式
  - `workers: 1`（稳定性优先）
  - `timeout: 60000`
  - `retries: 1`
  - HTML 报告输出到 `test-results/`
- **来源**：代码分析

## 6. 过渡需求

### TR-001: 文件迁移

- **描述**：从当前 16 个文件 308 case 迁移到新体系
- **策略**：
  1. 创建新目录结构 `e2e/smoke/`、`e2e/features/`、`e2e/shared/`
  2. 按场景逐个创建新 spec 文件
  3. 每创建一个新文件，运行对应测试验证通过
  4. 全部新文件验证通过后，删除旧文件
  5. 更新 `playwright.config.js` 配置
- **回滚方案**：保留旧文件直到新体系完全验证通过，通过 git revert 回滚
- **来源**：代码分析

### TR-002: helpers 扩展

- **描述**：扩展现有 `e2e/helpers/auth.js` 并新增 `e2e/shared/components.js` 和 `e2e/helpers/test-data.js`
- **策略**：
  1. 在 `auth.js` 中保留现有函数（login、navigateAndWaitForPage、attachScreenshot、setAdminPermissions）
  2. 新增 `shared/components.js` 提供 TableHelper、FormHelper、SelectorHelper、ScopeTreeHelper、ImportExportHelper
  3. 新增 `helpers/test-data.js` 提供测试数据工厂
- **回滚方案**：新文件独立，不影响现有代码
- **来源**：代码分析

### TR-003: 元数据 API 测试迁移

- **描述**：将纯 API 测试（S13）迁移到后端测试框架（pytest）
- **策略**：
  1. 在 `meta/tests/` 目录下创建 `test_metadata_api.py`
  2. 将 UI Config、Schema、Associations、权限、枚举 Mutability API 测试迁移到 pytest
  3. 从 E2E 测试中移除 `api/` 目录
- **回滚方案**：独立文件，不影响现有代码
- **来源**：用户确认

## 7. 约束与假设

### 7.1 技术约束

- 测试框架为 Playwright，不引入其他测试框架
- 前端为 Vue 3 + Pinia，导航等待策略必须适配 SPA
- 后端为 Flask，API 测试使用 pytest
- 测试在 Windows 环境运行

### 7.2 业务约束

- 测试依赖后端 API 可用（Flask 服务需启动）
- 测试依赖测试数据存在（产品、版本、用户、枚举等）
- 管理员权限测试依赖 `admin` 账户可用
- CRUD 测试可能受 mutability 约束（system 枚举不可修改）
- 导入导出测试需要 xlsx 文件（先导出再导入）

### 7.3 假设

- `window.__pinia` 已在 `main.js` 中暴露 → 已验证（Verified）
- 后端 API 端口 3010，前端端口 9323 → 已验证（Verified）
- 测试环境中有可用的产品版本数据 → 需验证（TBD）
- 测试环境中有不同 mutability 的枚举类型 → 已验证（locked/extensible/mutable 均存在）

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 理由 |
|----|------|--------|------|
| FR-006 | 稳定性保障 | Must | 无稳定性则测试无效 |
| FR-007 | 截图可靠性 | Must | 截图无效则报告不可信 |
| FR-004 | 流程化测试用例 | Must | 效率和可维护性的基础 |
| FR-001 | 三层映射架构 | Must | 体系核心架构 |
| FR-002 | 冒烟测试分层 | Must | 核心价值交付 |
| FR-010 | 测试场景定义 | Must | 具体验证点 |
| FR-009 | 统一导航封装 | Must | 稳定性保障 |
| FR-008 | 权限状态同步 | Must | 权限测试基础 |
| FR-003 | 功能测试分层 | Must | 完整覆盖 |
| FR-005 | 共享组件操作层 | Should | 提升可维护性 |
| FR-011 | 测试数据工厂 | Should | 提升可维护性 |
| FR-012 | 测试数据清理 | Should | 保持环境干净 |

**建议里程碑**：

- **里程碑 1**：基础设施（目录结构、helpers 扩展、Playwright 配置、共享组件操作层）
- **里程碑 2**：冒烟测试（S01 + S02，验证稳定性策略）
- **里程碑 3**：架构数据深度测试（S03 + S04 + S05，验证 CRUD/过滤/导入导出/ValueHelp）
- **里程碑 4**：用户权限与角色权限（S06 + S07，验证 CRUD/关联/权限配置）
- **里程碑 5**：枚举管理（S08，验证 inline edit / mutability）
- **里程碑 6**：审计日志与架构图与产品版本（S09 + S10 + S11）
- **里程碑 7**：清理旧文件 + 更新项目规则 + 迁移 API 测试到 pytest

## 9. 变更/设计方案（RFC）

### 9.1 现状分析

- **当前架构**：16 个 spec 文件平铺在 `e2e/` 目录，无分层
- **当前问题**：
  1. 308 个 case 碎片化，每个 case 独立登录+导航
  2. 纯 API 测试混在 UI 文件中，不必要启动浏览器
  3. `networkidle` 导致测试卡死
  4. 自动截图捕获的是 test 结束后的页面状态
  5. `ui-common-functions.spec.js` 作为测试文件存在，但其逻辑应作为工具函数复用
  6. `core-object-verification.spec.js` 1362 行、39 case、11 个无意义命名的 describe
  7. 架构数据管理仅验证页面导航，未覆盖 CRUD/过滤/范围选择/导入导出
  8. 枚举管理未覆盖 inline edit 和 mutability 逻辑
  9. 审计日志未验证操作审计（CUD/关联/导入导出是否被记录）
  10. 导入导出作为独立场景，与架构数据管理割裂
- **相关代码路径**：
  - `e2e/*.spec.js`（16 个文件）
  - `e2e/helpers/auth.js`
  - `playwright.config.js`
  - `src/main.js`（`window.__pinia` 暴露）
  - `src/components/common/MultiObjectManagementPage/`（架构数据管理页面）
  - `src/components/common/RelationScopeTree/`（范围选择树）
  - `src/components/common/MetaListPage/InlineEditCell.vue`（inline edit）
  - `src/views/SystemManagement/AuditLogManagement.vue`（审计日志）

### 9.2 目标状态

- **目标架构**：两层目录（smoke/features）+ 共享工具层（helpers + shared）
- **关键变更**：
  1. 新建 `e2e/smoke/`、`e2e/features/`、`e2e/shared/` 目录
  2. 新建 `e2e/shared/components.js`（含 ScopeTreeHelper、ImportExportHelper）
  3. 新建 `e2e/helpers/test-data.js`（含 findEnumByMutability、findRoleWithPermissions）
  4. 重写 10 个场景的 spec 文件（流程化 case）
  5. 架构数据管理从 1 个场景拆分为 4 个场景（导航/CRUD/过滤/导入导出）
  6. 导入导出融入架构数据场景
  7. 认证、工作台、账户设置合并为 1 个场景
  8. 元数据 API 测试迁移到 pytest
  9. 更新 `playwright.config.js` 支持 projects 分层
  10. 删除旧的 16 个 spec 文件

### 9.3 详细设计

#### 9.3.1 目录结构

```
e2e/
├── smoke/                                    # P0 冒烟测试
│   ├── auth.smoke.spec.js                    # S01: 认证与账户设置（3 case）
│   └── arch-data.smoke.spec.js               # S02: 架构数据导航与列表（2 case）
│
├── features/                                 # P1/P2 功能测试
│   ├── arch-data-crud.spec.js                # S03: 业务对象与关系CRUD（3 case）
│   ├── arch-data-filter.spec.js              # S04: 过滤查询与范围选择（2 case）
│   ├── arch-data-import-export.spec.js       # S05: 导入导出（3 case）
│   ├── user-permission.spec.js               # S06: 用户角色权限CRUD与关联（3 case）
│   ├── role-permission.spec.js               # S07: 角色权限配置（2 case）
│   ├── enum-management.spec.js               # S08: 枚举管理（3 case）
│   ├── audit-log.spec.js                     # S09: 审计日志（2 case）
│   ├── diagram.spec.js                       # S10: 架构图（1 case）
│   └── product-version.spec.js               # S11: 产品版本管理（2 case）
│
├── helpers/
│   ├── auth.js                               # 现有：登录、导航、截图、权限
│   └── test-data.js                          # 新增：测试数据工厂
│
└── shared/
    └── components.js                         # 新增：TableHelper, FormHelper, SelectorHelper, ScopeTreeHelper, ImportExportHelper, ValueHelpHelper
```

#### 9.3.2 共享组件操作层设计

```javascript
// e2e/shared/components.js

export class TableHelper {
  constructor(page) { this.page = page }
  async waitForData(timeout = 15000) { ... }
  async getRowCount() { ... }
  async openFirstRowDrawer() { ... }
  async clickTab(tabName) { ... }
  async clickRowAction(actionText) { ... }
  async sortByColumn(columnName) { ... }
  async searchByKeyword(keyword) { ... }
}

export class FormHelper {
  constructor(page) { this.page = page }
  async fillField(label, value) { ... }
  async submit() { ... }
  async cancel() { ... }
  async expectValidation(message) { ... }
}

export class SelectorHelper {
  constructor(page) { this.page = page }
  async selectProductVersion(productId, versionId) { ... }
  async selectOption(selectSelector, optionText) { ... }
}

export class ScopeTreeHelper {
  constructor(page) { this.page = page }
  async expandPanel(panelName) { ... }  // 'object' | 'relation' | 'filter'
  async checkObjectNode(nodeLabel) { ... }
  async checkRelationNode(nodeLabel) { ... }
  async selectAnnotationCategory(categories) { ... }
  async selectRelationType(types) { ... }
  async clearAllScopes() { ... }
  async refreshRelationScope() { ... }
}

export class ImportExportHelper {
  constructor(page) { this.page = page }
  async exportSingleObject(objectType, options = {}) { ... }
  async importSingleObject(objectType, filePath, conflictMode = 'upsert') { ... }
  async exportMultiType(objectTypes, options = {}) { ... }
  async importMultiType(objectTypes, filePath, conflictMode = 'upsert') { ... }
  async verifyImportResult(expectedCounts) { ... }
}

export class ValueHelpHelper {
  constructor(page) { this.page = page }
  async openDialog(fieldLabel) { ... }  // 点击字段的 ValueHelp 图标
  async search(keyword) { ... }  // 在弹窗中搜索
  async selectItem(itemText) { ... }  // 选择一条记录
  async confirm() { ... }  // 确认选择
  async verifyFieldFilled(fieldLabel, expectedValue) { ... }  // 验证回填
}
```

#### 9.3.3 测试数据工厂设计

```javascript
// e2e/helpers/test-data.js

export async function findProductWithVersion(request, baseURL) { ... }

export async function findEnumByMutability(request, baseURL, mutability) {
  const resp = await request.get(`${baseURL}/api/v2/bo/enum_type`)
  if (!resp.ok()) return null
  const enums = await resp.json()
  return (enums.items || enums).find(e => e.mutability === mutability) || null
}

export async function findRoleWithPermissions(request, baseURL) {
  const resp = await request.get(`${baseURL}/api/v1/roles`)
  if (!resp.ok()) return null
  const roles = await resp.json()
  return roles[0] || null
}

export async function ensureTestData(request, baseURL, type) { ... }
```

#### 9.3.4 Playwright 配置设计

```javascript
// playwright.config.js 关键变更

const baseUse = {
  baseURL: 'http://localhost:9323',
  actionTimeout: 10000,
  locale: 'zh-CN',
}

module.exports = {
  testDir: './e2e',
  timeout: 60000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 1,
  retries: 1,
  reporter: [['html', { open: 'never' }], ['list']],

  projects: [
    {
      name: 'smoke',
      testDir: './e2e/smoke',
      testMatch: '*.smoke.spec.js',
      use: { ...baseUse },
    },
    {
      name: 'features',
      testDir: './e2e/features',
      use: { ...baseUse },
    },
  ],
}
```

**运行命令**：
```bash
npx playwright test --project=smoke      # 冒烟测试（~3分钟）
npx playwright test --project=features   # 功能测试（~5分钟）
npx playwright test                      # 全量测试（~8分钟）
```

#### 9.3.5 稳定性策略规则

| 规则 | 禁止 | 替代方案 |
|------|------|---------|
| R01 | `waitForLoadState('networkidle')` | `domcontentloaded` + 元素可见性等待 |
| R02 | `waitForTimeout(>2000)` | `waitFor()` 等元素状态 |
| R03 | `page.goto()` 无 `waitUntil` | `{ waitUntil: 'domcontentloaded' }` |
| R04 | 导航后不等待 login-overlay | `waitFor({ state: 'hidden' })` |
| R05 | 自动截图 `screenshot: 'on'` | `testInfo.attach()` 手动附加 |
| R06 | 仅改 localStorage 不改 Pinia | `setAdminPermissions()` 同步两者 |
| R07 | 直接 `page.goto()` 无后续等待 | `navigateAndWaitForPage()` 封装 |

#### 9.3.6 当前 16 个文件 → 新体系的映射

| 当前文件 | case数 | → 新位置 | 新case数 | 变化 |
|---------|--------|---------|---------|------|
| auth.spec.js | 22 | smoke/auth.smoke.spec.js | 3 | 融合+合并工作台+账户设置 |
| navigation-flow.spec.js | 7 | 合入 smoke/auth.smoke.spec.js | 0 | 合并 |
| arch-data-navigation.spec.js | 5 | smoke/arch-data.smoke.spec.js | 2 | 已融合 |
| product-version-management.spec.js | 18 | 合入 arch-data（产品选择在全局工具栏） | 0 | 合并 |
| diagram.spec.js | 8 | features/diagram.spec.js | 1 | 融合 |
| user-role-management.spec.js | 46 | features/user-permission.spec.js | 3 | 大幅融合 |
| association-metadata.spec.js | 3 | 合入 user-permission.spec.js | 0 | 合并 |
| role-permission-center.spec.js | 21 | features/role-permission.spec.js | 2 | 融合 |
| permission.spec.js | 29 | features/role-permission.spec.js | 2 | 合并+拆API到pytest |
| enum-type-management.spec.js | 13 | features/enum-management.spec.js | 3 | 融合+拆API到pytest |
| audit-log.spec.js | 10 | features/audit-log.spec.js | 2 | 融合+增加审计验证 |
| account-settings.spec.js | 7 | 合入 smoke/auth.smoke.spec.js | 0 | 合并 |
| import-export.spec.js | 7 | features/arch-data-import-export.spec.js | 3 | 融合入架构数据 |
| core-object-verification.spec.js | 39 | 移到 meta/tests/test_metadata_api.py | 0 | 拆到pytest |
| annotation-metadata.spec.js | 11 | 移到 meta/tests/test_metadata_api.py | 0 | 拆到pytest |
| ui-common-functions.spec.js | 21 | shared/components.js | 0 | → 工具函数 |
| **合计** | **308** | | **23** | **-93%** |

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| A: 两层目录 + 流程化 case + 深度覆盖 | 清晰分层、高效运行、覆盖核心业务 | 迁移工作量较大 | **选择** |
| B: 保留平铺目录 + 仅融合 case | 迁移工作量小 | 无分层运行能力、目录混乱、覆盖不足 | 拒绝 |
| C: 使用 Cypress 替代 Playwright | 内置等待策略更友好 | 重新学习成本、不兼容现有代码 | 拒绝 |

### 9.5 实施与迁移计划

**实施顺序**：

1. **里程碑 1：基础设施**
   - 创建目录结构 `e2e/smoke/`、`e2e/features/`、`e2e/shared/`
   - 新建 `e2e/shared/components.js`（TableHelper、FormHelper、SelectorHelper、ScopeTreeHelper、ImportExportHelper）
   - 新建 `e2e/helpers/test-data.js`（findProductWithVersion、findEnumByMutability 等）
   - 更新 `playwright.config.js`（projects 配置）

2. **里程碑 2：冒烟测试**
   - 创建 `auth.smoke.spec.js`（S01，3 case：登录+工作台+账户设置）
   - 迁移 `arch-data.smoke.spec.js`（S02，2 case，已有基础）
   - 运行 `--project=smoke` 验证

3. **里程碑 3：架构数据深度测试**
   - 创建 `arch-data-crud.spec.js`（S03，2 case）
   - 创建 `arch-data-filter.spec.js`（S04，2 case）
   - 创建 `arch-data-import-export.spec.js`（S05，3 case）
   - 运行验证

4. **里程碑 4：用户权限与角色权限**
   - 创建 `user-permission.spec.js`（S06，3 case）
   - 创建 `role-permission.spec.js`（S07，2 case）
   - 运行验证

5. **里程碑 5：枚举管理**
   - 创建 `enum-management.spec.js`（S08，3 case）
   - 重点验证 inline edit 和 mutability 逻辑
   - 运行验证

6. **里程碑 6**：审计日志与架构图与产品版本
   - 创建 `audit-log.spec.js`（S09，2 case，含操作审计验证）
   - 创建 `diagram.spec.js`（S10，1 case）
   - 创建 `product-version.spec.js`（S11，2 case）
   - 运行验证

7. **里程碑 7：清理与迁移**
   - 删除旧的 16 个 spec 文件
   - 创建 `meta/tests/test_metadata_api.py`（元数据 API 测试）
   - 更新 `.trae/rules/project_rules.md`
   - 运行全量测试验证

**风险缓解**：

| 风险 | 缓解策略 |
|------|---------|
| 迁移过程中测试覆盖度下降 | 逐场景迁移，新旧并行直到全部验证 |
| 流程化 case 中某步骤失败导致后续步骤无法执行 | 每个步骤用 try/catch 包裹，失败时记录但继续 |
| 共享组件操作层与实际 UI 不匹配 | 每个 Helper 方法提供 fallback 和错误提示 |
| CRUD 测试可能破坏现有数据 | 使用唯一标识创建测试数据，afterAll 中清理 |
| 导入导出测试需要 xlsx 文件 | 先导出再导入，无需预置文件 |
| 枚举 mutability 测试依赖特定数据 | `findEnumByMutability()` 动态查找，无数据时 skip |

**测试策略**：

- 单元测试：共享组件操作层（TableHelper、FormHelper、ScopeTreeHelper、ImportExportHelper）
- 集成测试：每个 spec 文件独立运行验证
- E2E 测试：全量运行验证（`npx playwright test`）
- API 测试：pytest 运行 `meta/tests/test_metadata_api.py`

**回滚方案**：

- 每个里程碑完成后 git commit
- 如新体系有问题，`git revert` 回到上一个里程碑
- 旧文件在里程碑 7 之前保留

## 10. TBD 列表

| ID | 项目 | 缺失信息 | 下一步 |
|----|------|---------|--------|
| TBD-1 | 测试环境产品版本数据 | 测试环境中是否有可用的产品版本数据 | 实施时验证，无数据时 skip |
| TBD-2 | API 测试认证方式 | pytest API 测试是否需要认证 | 实施时验证 |

**注**：以下 TBD 已确认并关闭：
- ~~CI 集成~~ → 暂不需要
- ~~测试数据清理~~ → 在 afterAll 中清理
- ~~导入导出测试文件~~ → 先导出再导入
- ~~枚举 mutability 测试数据~~ → 已创建 test_mutable_enum
