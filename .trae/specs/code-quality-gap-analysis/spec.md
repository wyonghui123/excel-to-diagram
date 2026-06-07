# Spec: 代码质量差距分析与工程基础设施加固

> **Spec ID**: code-quality-gap-analysis
> **版本**: v1.0.0
> **创建日期**: 2026-05-19
> **状态**: Draft (待审阅)
> **优先级**: P0 (Critical)
> **关联 Spec**: [yaml-single-source-of-truth-enhancement](../yaml-single-source-of-truth-enhancement/spec.md)
> **分析日期**: 2026-05-19

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [需求类型概览](#2-需求类型概览)
3. [功能需求](#3-功能需求)
4. [非功能需求](#4-非功能需求)
5. [外部接口需求](#5-外部接口需求)
6. [过渡需求](#6-过渡需求)
7. [约束与假设](#7-约束与假设)
8. [优先级与里程碑建议](#8-优先级与里程碑建议)
9. [变更/设计提案 (RFC)](#9-变更设计提案-rfc)
10. [TBD 列表](#10-tbd-列表)

---

## 1. 背景与目标

### 1.1 背景

当前 ArchWorkspace 项目已进入 Phase 3/4 阶段（整体 ~90% 进度），YAML 单一事实原则架构的核心功能已基本实现。然而，在 2026-05-19 进行的全量代码质量深度分析中，发现了若干**阻碍生产化部署的关键质量差距**，主要集中在安全性、测试工程化、和代码一致性三个领域。

**分析范围**：
- Python 后端：`server.py`、`bo_framework.py`、`yaml_loader.py`、`rule_chain.py`、`models.py`、`datasource.py`、`permission_sync_service.py`、`bo_api.py`、拦截器链（12个拦截器）、API 层（35个Blueprint）
- Vue 前端：`router/index.js`、`dynamicRoutes.js`、核心组件/Composables
- YAML Schema：35个 YAML 元数据文件
- 测试体系：100+ 后端测试文件
- **总体评分**: 77/100

### 1.2 业务目标

- **OBJ-1**: 消除所有 P0 安全风险，确保生产环境部署安全基线达标
- **OBJ-2**: 清理测试体系中的工程债务，确保 CI 管道可靠运行
- **OBJ-3**: 统一 YAML Schema 命名规范，消除配置不一致导致的功能隐患
- **OBJ-4**: 完成前端静态路由到动态路由的彻底迁移，实现 YAML 单一事实原则 100% 贯彻
- **OBJ-5**: 提升代码可维护性（server.py 启动流程重构）

### 1.3 用户/涉众目标

| 涉众 | 目标 | 成功标准 |
|------|------|---------|
| **运维团队** | 安全基线达标，可安全部署到生产环境 | CORS 配置正确、无 SQL 注入风险 |
| **开发团队** | 新增 BO 对象只需修改 YAML | 静态路由消除率 100% |
| **测试团队** | 测试目录清洁，CI 可靠 | `meta/tests/` 中零调试脚本 |
| **架构师** | YAML 命名规范统一 | action naming 一致性 100% |

---

## 2. 需求类型概览

| 类型 | 是否适用 | 证据/来源 |
|------|---------|----------|
| 业务需求 | 是 | 生产化部署安全基线需求 |
| 用户/涉众需求 | 是 | 开发/运维/测试团队反馈 |
| 解决方案需求 | 是 | 代码分析报告中的具体技术方案 |
| 功能需求 | 是 | FR-001 ~ FR-020 |
| 非功能需求 | 是 | NFR-001 ~ NFR-006 |
| 外部接口需求 | 是 | IF-001 ~ IF-003 |
| 过渡需求 | 是 | TR-001 ~ TR-003 |

---

## 3. 功能需求

### 3.1 P0 Critical — 必须立即修复

---

#### FR-001: 清理 meta/tests/ 中的非测试文件

- **描述**: 系统必须将 `meta/tests/` 目录中的调试脚本、工具脚本、数据初始化脚本移至专门目录，确保 `pytest` 仅执行真正的测试文件。
- **影响文件**（至少 14 个）:
  - `debug_resolve.py`, `debug_resolve2.py`, `debug_field.py`, `debug_condition.py`
  - `quick_replace.py`, `quick_replace_debug.py`
  - `check_products.py`, `add_product1.py`, `add_v1_data.py`, `add_test_data_v2.py`, `add_missing_data.py`
  - `fix_test_paths.py`, `analyze_tests.py`, `batch_update_db_path.py`
  - `pinpoint_root_cause.py`, `show_db_structure.py`
  - `init_test_data.py`
- **验收标准**:
  - [ ] `meta/tests/` 目录中文件的 `assert` 或 `def test_` 覆盖率 ≥ 95%
  - [ ] 所有调试脚本移至 `meta/dev/` 或 `scripts/` 目录
  - [ ] `python -m pytest meta/tests/ --collect-only` 不再收集到非测试函数
- **优先级**: Must (P0)
- **类型映射**: Functional / Transition
- **来源**: 代码质量分析 [meta/tests/ 目录](file:///d:/filework/excel-to-diagram/meta/tests/) 文件列表审查

---

#### FR-002: 修复 CORS 安全配置

- **描述**: 当 `CORS_ALLOWED_ORIGINS` 环境变量为空时，系统**禁止**设置 `Access-Control-Allow-Origin` 为请求的 `Origin`（通配模式），而应拒绝跨域或无配置场景下使用严格白名单。
- **当前代码** ([server.py:L251-L263](file:///d:/filework/excel-to-diagram/meta/server.py#L251-L263)):
  ```python
  # 风险代码
  elif not allowed_origins:
      response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '')
  ```
- **验收标准**:
  - [ ] 生产环境（`FLASK_ENV=production` 或 `FLASK_DEBUG=false`）下，`CORS_ALLOWED_ORIGINS` 为空时**不启用 CORS**
  - [ ] 开发环境（`FLASK_DEBUG=true`）保持当前宽松行为用于本地调试
  - [ ] `.env.example` 中添加 `CORS_ALLOWED_ORIGINS` 的生产环境注释说明
- **优先级**: Must (P0)
- **类型映射**: Functional / Nonfunctional (Security)
- **来源**: [server.py](file:///d:/filework/excel-to-diagram/meta/server.py#L251-L263) 代码审查

---

#### FR-003: SQL 注入防护加固 — 表名白名单校验

- **描述**: 对所有动态拼接 `table_name` 的 SQL 操作增加白名单校验。`table_name` 只能来自 `MetaObject.table_name`（YAML Schema 中定义的值），不允许任何未经验证的表名进入 SQL 语句。
- **影响范围**:
  - [bo_framework.py:L113](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L113) — `_load_old_data()`
  - `action_executor.py` — CRUD 操作
  - `query_service.py` — 查询构建
  - `association_engine.py` — 关联操作
- **验收标准**:
  - [ ] 新增 `validate_table_name()` 工具函数，基于 `registry` 中的已注册 BO 白名单
  - [ ] 所有动态 SQL 表名接入该校验
  - [ ] 添加单元测试：非法表名应抛出 `ValueError`
  - [ ] YAML 加载时对 `table_name` 添加 Pattern 校验：`^[a-z][a-z0-9_]*$`
- **优先级**: Must (P0)
- **类型映射**: Functional / Nonfunctional (Security)
- **来源**: [bo_framework.py](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L111-L125) 代码审查

---

#### FR-004: YAML Actions 命名规范统一

- **描述**: 统一所有 BO YAML 文件中 `actions` 的 `id` 命名格式为 `{object_type}.{action}`。当前存在三类命名风格混用：
  - **旧 CRUD 风格**: `crud_create`, `crud_read` — 见于 [product.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/product.yaml#L436)
  - **对象前缀风格**: `user_create`, `role_create` — 见于 [user.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/user.yaml#L444)、[role.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/role.yaml#L474)
  - **业务前缀风格**: `menu_create` — 见于 [menu.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/menu.yaml#L261)
- **目标规范**: 统一使用 `{object_type}.{action}` 格式（如 `product.create`）
  - 这允许 `PermissionSyncService` 的 `_parse_code()` 方法正确解析资源类型和动作
- **验收标准**:
  - [ ] 所有 35 个 YAML Schema 文件的 action IDs 统一格式
  - [ ] `PermissionSyncService.validate_consistency()` 通过零错误
  - [ ] 前端权限检查（`authStore.hasPermission()`）兼容新格式
  - [ ] 数据库 `permissions` 表 `code` 列格式一致
- **优先级**: Must (P0)
- **类型映射**: Functional / Transition
- **来源**: 35 个 YAML schema 文件逐文件审查，[PermissionSyncService](file:///d:/filework/excel-to-diagram/meta/services/permission_sync_service.py) 依赖分析

---

### 3.2 P1 High — 应在下一迭代完成

---

#### FR-005: 完成前端静态路由全量迁移到动态路由

- **描述**: 将 [router/index.js](file:///d:/filework/excel-to-diagram/src/router/index.js#L34-L181) 中剩余的 ~25 个硬编码路由全部迁移到 [dynamicRoutes.js](file:///d:/filework/excel-to-diagram/src/router/dynamicRoutes.js) 动态路由系统，通过 API 菜单数据驱动路由注册。
- **待迁移路由清单**:
  | 路由路径 | 当前状态 | 迁移方案 |
  |---------|---------|---------|
  | `/product-management` | 硬编码 | 通过 `menu.yaml` + `bo_bindings` 动态注册 |
  | `/user-permission/:tab?` | 硬编码 | `GenericTabContainer` + `group` props |
  | `/business-config/:tab?` | 硬编码 | 同上 |
  | `/system/role-permission/:roleId` | 硬编码 | 动态详情路由 |
  | `/system/role-detail/:roleId` | 硬编码 | 与 ObjectDetail 统一 |
  | `/system-admin` | 硬编码 | 菜单条目化 |
  | `/system/archdata` | 硬编码 | 菜单条目化 |
  | `/detail/:objectType`, `/detail/:objectType/:id` | 半动态 | 保留但通过菜单数据推导 |
  | `/role/:id` | 硬编码 | 统一到 `ObjectDetail` 模式 |
  | `/account` | 硬编码 | 保留静态路由（非 BO 页面） |
  | `/test`, `/component-comparison`, `/dev/navigation-test` | 开发路由 | 保留静态路由 |
  | `/diagram`, `/config`, `/`, `/dev/theme-preview` | 固定页面 | 保留静态路由 |
- **验收标准**:
  - [ ] 所有 BO 驱动的业务路由完全由 `dynamicRoutes.js` 注册
  - [ ] 仅保留 8 个以内的真正静态路由（LandingPage/Login/Dev/Account）
  - [ ] 新增 BO 对象后无需修改 `router/index.js`
  - [ ] 端到端测试：所有现有路由可正常访问
- **优先级**: Should (P1)
- **类型映射**: Functional / Transition
- **来源**: Spec Phase 3 计划，[router/index.js](file:///d:/filework/excel-to-diagram/src/router/index.js) 审查

---

#### FR-006: 重构 server.py 启动流程（ApplicationBuilder 模式）

- **描述**: 将 [server.py](file:///d:/filework/excel-to-diagram/meta/server.py) 中 `create_app()` 函数（当前约 200+ 行）拆分为职责清晰的 Bootstrap 模块，引入 ApplicationBuilder 模式。
- **当前问题**:
  1. 单函数承担 YAML 注册、10+ 服务初始化、数据库迁移、BO Framework 装配、Blueprint 注册、心跳定时器、WebSocket 初始化
  2. 服务初始化顺序隐式耦合
  3. 任意初始化失败导致整个应用无法启动
- **拟拆分模块**:
  ```python
  # 新建 meta/bootstrap/
  ├── app_builder.py        # ApplicationBuilder 主类
  ├── schema_bootstrap.py   # YAML Schema 注册
  ├── service_bootstrap.py  # 服务层初始化（含依赖顺序）
  ├── migration_bootstrap.py # 数据库迁移
  ├── interceptor_bootstrap.py # BO Framework + 拦截器注册
  └── blueprint_bootstrap.py  # Blueprint 注册
  ```
- **验收标准**:
  - [ ] `create_app()` 代码量从 ~200 行降至 ≤50 行
  - [ ] 各 bootstrap 模块可独立测试
  - [ ] 服务初始化失败时提供明确的错误信息（而非静默失败或整体崩溃）
  - [ ] 支持 `--skip-migrations` 等启动选项
- **优先级**: Should (P1)
- **类型映射**: Functional / Nonfunctional (Maintainability)
- **来源**: [server.py](file:///d:/filework/excel-to-diagram/meta/server.py#L159-L300) `create_app()` 审查

---

#### FR-007: API 层增加显式权限前置检查

- **描述**: 在关键 API 端点（create/update/delete）中增加**显式的权限前置检查**，作为拦截器链权限检查的**双重保险**（Defense in Depth）。
- **当前风险**: [bo_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L48-L84) 的 `create_bo` 仅依赖 `@login_required`，权限检查完全委托给拦截器链，如果拦截器配置遗漏可能存在绕过风险。
- **实现方案**:
  ```python
  from meta.services.auth_middleware import login_required, require_permission
  
  @bo_bp.route('/<object_type>', methods=['POST'])
  @login_required
  @require_permission('{object_type}.create')  # 动态权限检查
  def create_bo(object_type):
      ...
  ```
- **验收标准**:
  - [ ] 所有 CUD 端点（create/update/delete）增加 `@require_permission` 装饰器
  - [ ] 装饰器支持动态参数（从 URL path 提取 `object_type`）
  - [ ] 权限检查失败返回 403 而非 500
  - [ ] 添加 API 权限矩阵集成测试
- **优先级**: Should (P1)
- **类型映射**: Functional / Nonfunctional (Security)
- **来源**: [bo_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py) 审查

---

#### FR-008: 消除 server.py 中的注释死代码

- **描述**: 清理 [server.py](file:///d:/filework/excel-to-diagram/meta/server.py#L120) 中被注释掉的无效导入和模块引用。
- **具体清理项**:
  - `# from meta.api.role_data_permission_api import role_data_permission_bp  # 模块不存在，已废弃` — 应完全删除
  - 所有 `print(f"[SERVER_DEBUG] ...")` — 替换为 `logging.debug()`
- **验收标准**:
  - [ ] 零行被注释掉的 import 语句
  - [ ] 零行 `print()` 调试输出（全部改为 logging）
- **优先级**: Should (P1)
- **类型映射**: Functional (Code Hygiene)
- **来源**: [server.py](file:///d:/filework/excel-to-diagram/meta/server.py#L120) 审查

---

### 3.3 P2 Medium — 可在后续迭代完成

---

#### FR-009: 前端渐进式 TypeScript 引入

- **描述**: 对核心前端模块（router、stores、composables）逐步引入 TypeScript 类型标注，提升代码质量和 IDE 支持。
- **首批目标模块**:
  - `src/router/dynamicRoutes.js` → `dynamicRoutes.ts`
  - `src/stores/authStore.js` → `authStore.ts`
  - `src/composables/useMenuPermissions.js` → `useMenuPermissions.ts`
- **优先级**: Could (P2)
- **来源**: 代码分析 — 前端使用纯 JavaScript，缺少类型安全

---

#### FR-010: 数据库从 SQLite 升级到 PostgreSQL（生产方案）

- **描述**: 为生产环境提供 PostgreSQL 数据源实现，利用现有的 `DataSource` 抽象层。
- **覆盖面**:
  - `datasource.py` 已有 `DataSourceType.POSTGRESQL` 枚举
  - 需实现 `PostgreSQLDataSource` 类
  - 需处理 JSON 字段差异（SQLite TEXT vs PostgreSQL JSONB）
- **优先级**: Could (P2)
- **来源**: [datasource.py](file:///d:/filework/excel-to-diagram/meta/core/datasource.py) 审查

---

#### FR-011: 添加 CI/CD 一致性检查步骤

- **描述**: 在 GitHub Actions 中添加 Spec Phase 2 中计划的 CI 检查步骤（T2.5）。
- **验收标准**:
  - [ ] PR 提交时自动运行 `permission_sync_service.validate_consistency()`
  - [ ] 不一致时 CI 构建失败
  - [ ] 运行 `python -m pytest meta/tests/ --tb=short` 作为必须通过步骤
- **优先级**: Could (P2)
- **来源**: Spec [yaml-single-source-of-truth-enhancement](file:///d:/filework/excel-to-diagram/.trae/specs/yaml-single-source-of-truth-enhancement/spec.md) Phase 2 T2.5

---

## 4. 非功能需求

### NFR-001: 安全 — CORS 严格模式

- **描述**: 生产环境必须配置明确的 `CORS_ALLOWED_ORIGINS` 白名单，禁止通配/自适应 Origin 模式。
- **测量**: 安全扫描工具检查 CORS 响应头
- **优先级**: Must (P0)
- **来源**: [server.py](file:///d:/filework/excel-to-diagram/meta/server.py#L251-L263) 审查

### NFR-002: 安全 — SQL 注入防护

- **描述**: 所有动态 SQL 表名/列名必须通过白名单校验，不得直接拼接到 SQL 字符串中。
- **测量**: 代码审查 + 安全测试用例覆盖
- **优先级**: Must (P0)
- **来源**: [bo_framework.py](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py) 审查

### NFR-003: 可维护性 — server.py 复杂度

- **描述**: `create_app()` 函数圈复杂度应 ≤ 10（当前估计 ≥ 30）。
- **测量**: `radon cc meta/server.py` 或 `pylint`
- **优先级**: Should (P1)
- **来源**: [server.py](file:///d:/filework/excel-to-diagram/meta/server.py) `create_app()` 审查

### NFR-004: 一致性 — YAML Schema 规范

- **描述**: 所有 BO YAML 文件的 `actions.id` 必须遵循 `{object_type}.{action}` 格式。
- **测量**: 自动化 Schema 校验脚本
- **优先级**: Must (P0)
- **来源**: 35 个 YAML Schema 审查

### NFR-005: 测试清洁度 — tests 目录应仅含测试

- **描述**: `meta/tests/` 目录中 100% 文件应为可被 `pytest` 收集的测试文件。
- **测量**: `pytest --collect-only meta/tests/ | wc -l` 应为合理数值
- **优先级**: Must (P0)
- **来源**: `meta/tests/` 目录审查

### NFR-006: 可追溯性 — 日志格式统一

- **描述**: 所有调试输出必须使用 `logging` 模块（标准格式：`%(asctime)s - %(name)s - %(levelname)s - [%(trace_id)s] - %(message)s`），禁止使用 `print()`。
- **测量**: `grep -r "print(" meta/server.py` 结果为零
- **优先级**: Should (P1)
- **来源**: [server.py](file:///d:/filework/excel-to-diagram/meta/server.py) 审查

---

## 5. 外部接口需求

### IF-001: CORS 配置接口

- **类型**: 环境变量
- **入口**: `.env` 文件中的 `CORS_ALLOWED_ORIGINS`
- **请求/响应/交互**:
  - 格式: `CORS_ALLOWED_ORIGINS=http://localhost:3004,https://app.example.com`
  - 逗号分隔的 Origin 白名单
  - 生产环境为必填项
- **错误处理**: 生产环境下未配置时**应用启动失败**并输出明确错误消息
- **优先级**: Must (P0)
- **来源**: FR-002

### IF-002: SQL Table Name Validator 接口

- **类型**: Python 函数接口
- **入口**: `meta/core/safety.py::validate_table_name(table_name: str) -> str`
- **交互**:
  - 输入：待校验的表名
  - 返回：通过校验的表名（不变）
  - 抛出：`ValueError` 当表名不在白名单中
- **白名单来源**: `meta.core.models.registry` 中已注册的所有 `MetaObject.table_name`
- **优先级**: Must (P0)
- **来源**: FR-003

### IF-003: require_permission 装饰器接口

- **类型**: Python 装饰器
- **入口**: `meta/services/auth_middleware.py::require_permission(permission_pattern: str)`
- **交互**:
  - 支持模板字符串：`'{object_type}.create'`，从 URL 参数或 request body 提取
  - 返回：权限通过时放行，否则 `jsonify({'success': False, 'message': 'Permission denied', 'error': 'FORBIDDEN'}), 403`
- **优先级**: Should (P1)
- **来源**: FR-007

---

## 6. 过渡需求

### TR-001: 测试文件迁移

- **描述**: 将 `meta/tests/` 中的调试/工具脚本迁移到 `meta/dev/` 或项目根 `scripts/` 目录。
- **策略**:
  1. 创建 `meta/dev/` 目录
  2. 移动所有非测试 Python 文件（不含 `def test_` 或 `assert` 的文件）
  3. 更新 `pytest.ini` 配置 `testpaths = meta/tests`
  4. 运行全量测试确认无回归
- **回滚计划**: `git revert` + 将文件移回原位置
- **优先级**: Must (P0)
- **来源**: FR-001

### TR-002: YAML Actions 命名迁移

- **描述**: 将所有 YAML Schema 中的 `actions.id` 从旧格式（`crud_*`、`{bo}_create`）统一迁移到 `{object_type}.{action}` 格式。
- **策略**:
  1. 新建 `scripts/migrate_action_names.py` 批量更新 YAML 文件
  2. 同步更新数据库 `permissions` 表的 `code` 列
  3. 更新前端权限码常量
  4. 全量回归测试
- **回滚计划**: Git 版本回退 + 数据库 migration 回滚脚本
- **优先级**: Must (P0)
- **来源**: FR-004

### TR-003: 路由渐进式迁移

- **描述**: 将静态路由逐批迁移到动态路由系统，采用**双轨并行 + 逐批下线**策略。
- **策略**:
  1. Phase 1: `product-management`、`user-permission`、`business-config`（通过菜单数据驱动）
  2. Phase 2: `system/role-permission`、`system/role-detail`、`role/:id`
  3. Phase 3: 验证所有路由均可通过动态系统访问后，移除硬编码路由
- **回滚计划**: 保留硬编码路由作为 fallback 直到动态路由验证通过
- **优先级**: Should (P1)
- **来源**: FR-005

---

## 7. 约束与假设

### 7.1 技术约束

- **C-1**: 项目使用 SQLite 作为开发数据库，部分 SQL 语法（如 JSONB）与 PostgreSQL 不兼容，迁移需注意
- **C-2**: 前端使用纯 JavaScript (Vue 3 SFC)，TypeScript 引入需渐进展开
- **C-3**: 现有 100+ 测试文件依赖特定测试数据，文件移动后需更新 import 路径
- **C-4**: 菜单动态路由系统依赖 `useMenuPermissions()` 和 API `/api/v2/menu/tree`，需确保这些服务稳定运行

### 7.2 业务约束

- **B-1**: 所有改造不能中断日常工作流（前后端独立可启动）
- **B-2**: YAML actions 命名变更需与前端权限检查同步，避免功能回归
- **B-3**: 新命名规范需向后兼容旧的 `permissions` 表记录（提供迁移脚本）

### 7.3 假设

- **A-1**: `meta.core.models.registry` 中所有已注册的 BO 对象对应的 YAML 文件都存在且可加载 — 来源: 已验证
- **A-2**: 前端 `authStore.hasPermission()` 根据 `permissions` 表中 `code` 字段匹配，格式变更需同步 — 来源: 已验证
- **A-3**: 当前无生产环境运行实例，因此可直接修改 CORS 安全策略而无兼容性问题 — 来源: 假设
- **A-4**: 开发环境 `FLASK_DEBUG=true` 保持宽松 CORS 策略 — 来源: 设计决策

---

## 8. 优先级与里程碑建议

### 8.1 所有需求优先级排序

| ID | 需求 | 优先级 | 工作量 | 风险等级 |
|----|------|--------|--------|---------|
| FR-002 | CORS 安全修复 | Must (P0) | 0.5天 | 🔴 阻断生产部署 |
| FR-003 | SQL 注入防护 | Must (P0) | 0.5天 | 🔴 安全隐患 |
| FR-001 | 测试目录清理 | Must (P0) | 0.5天 | 🟡 CI 可靠性 |
| FR-004 | YAML 命名统一 | Must (P0) | 1.5天 | 🟡 全系统影响 |
| FR-008 | server.py 死代码清理 | Should (P1) | 0.5天 | 🟢 低风险 |
| FR-007 | API 权限前置检查 | Should (P1) | 1天 | 🟡 安全加固 |
| FR-005 | 前端路由迁移 | Should (P1) | 2天 | 🟡 功能回归 |
| FR-006 | server.py 启动重构 | Should (P1) | 2天 | 🟡 可维护性 |
| FR-011 | CI/CD 一致性检查 | Could (P2) | 0.5天 | 🟢 低风险 |
| FR-009 | TypeScript 引入 | Could (P2) | 按需渐进 | 🟢 低风险 |
| FR-010 | PostgreSQL 迁移 | Could (P2) | 3天 | 🟢 低风险 |

### 8.2 里程碑建议

| 里程碑 | 范围 | 预计工作量 | 交付物 |
|--------|------|-----------|--------|
| **M1: 安全加固** (第1周) | FR-002, FR-003, FR-007 | 2天 | CORS修复 + SQL白名单 + API权限装饰器 |
| **M2: 工程清理** (第1周) | FR-001, FR-008, FR-004 | 2.5天 | 测试目录清洁 + 死代码清理 + YAML命名统一 |
| **M3: 架构演进** (第2周) | FR-005, FR-006 | 4天 | 路由全量动态化 + server.py Bootstrap重构 |
| **M4: 持续改进** (第3周+) | FR-009, FR-010, FR-011 | 按需 | TypeScript + PostgreSQL + CI增强 |

---

## 9. 变更/设计提案 (RFC)

### 9.1 As-Is 分析

#### 当前架构

```
┌──────────────────────────────────────────────────────────────────┐
│                    当前代码质量现状                                │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ✅ 优秀                                                          │
│  ├── YAML 单一事实源架构完整 (90%+)                               │
│  ├── 拦截器链模式设计优雅 (12个拦截器)                             │
│  ├── 数据模型深度高 (3000+行 dataclass)                           │
│  └── Spec 文档详尽 (1500+行)                                      │
│                                                                  │
│  🔴 P0 风险                                                       │
│  ├── CORS: 无配置时允许任意Origin → 生产安全漏洞                   │
│  ├── SQL注入: table_name 动态拼接无校验                            │
│  ├── tests目录: 100+文件混入15+调试脚本                            │
│  └── YAML命名: 3种action ID格式并存                               │
│                                                                  │
│  🟡 P1 风险                                                       │
│  ├── 前端路由: 双轨制 (25个静态 + 动态)                            │
│  ├── server.py: create_app() 职责过重 (200+行)                     │
│  └── API权限: 缺少显式前置检查                                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

#### 当前问题根源分析

| 问题 | 根因 | 影响 |
|------|------|------|
| CORS 安全漏洞 | 开发便利优先于安全设计 | 生产部署受阻 |
| SQL 注入风险 | 信任 YAML 数据源，缺少 defense-in-depth | 理论风险（YAML 被篡改场景） |
| 测试目录混乱 | 调试习惯欠佳，无清理机制 | CI 可靠性降低 |
| YAML 命名不一致 | 架构演进过程中多次修改风格 | 权限同步可能出错 |
| 路由双轨制 | 渐进式迁移策略的中间态 | 违背单一事实原则 |
| server.py 臃肿 | 功能增量累积，未及时重构 | 启动流程脆弱 |

### 9.2 Target State

#### 目标架构

```
┌──────────────────────────────────────────────────────────────────┐
│                   目标代码质量状态                                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  🔒 安全加固                                                      │
│  ├── CORS: 生产环境强制白名单，无配置即拒绝                        │
│  ├── SQL: table_name 白名单校验 (meta/core/safety.py)             │
│  └── API: 所有CUD端点 @require_permission 双重保险                 │
│                                                                  │
│  🧹 工程清理                                                      │
│  ├── tests/: 纯测试文件，调试脚本 → meta/dev/                      │
│  ├── YAML: 统一 {object_type}.{action} 命名                       │
│  └── server.py: print() → logging, 死代码清理                      │
│                                                                  │
│  🏗️ 架构演进                                                      │
│  ├── router: 静态路由 ≤8个，其余全部动态化                          │
│  └── bootstrap/: ApplicationBuilder 模式                          │
│                                                                  │
│  质量目标                                                         │
│  ├── 安全评分: 65→85                                              │
│  ├── 可维护性: 76→82                                              │
│  └── 总评分: 77→83                                                │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

#### 关键变更

1. **[新增] `meta/core/safety.py`**: SQL 表名校验工具函数 `validate_table_name()`
2. **[新增] `meta/bootstrap/`**: server.py 启动流程拆分为 6 个 Bootstrap 模块
3. **[修改] `meta/server.py`**: CORS 配置按环境区分、死代码清理
4. **[修改] `meta/api/bo_api.py`**: 添加 `@require_permission` 装饰器
5. **[修改] `meta/services/auth_middleware.py`**: 新增 `require_permission` 动态权限装饰器
6. **[批量修改] `meta/schemas/*.yaml`**: 统一 actions 命名格式
7. **[修改] `src/router/index.js`**: 移除 BO 驱动的静态路由
8. **[新增] `scripts/migrate_action_names.py`**: YAML + DB actions 命名迁移脚本
9. **[移动] `meta/tests/` → `meta/dev/`**: 15+ 调试脚本迁移

### 9.3 详细设计

#### 9.3.1 SQL 表名白名单校验器

```python
# 新建 meta/core/safety.py

import re
import logging

logger = logging.getLogger(__name__)

_TABLE_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')
MAX_TABLE_NAME_LENGTH = 64

def validate_table_name(table_name: str) -> str:
    """
    校验 SQL 表名的合法性
    
    规则:
    1. 只能包含小写字母、数字、下划线
    2. 以字母开头
    3. 长度 ≤ 64
    4. 必须在 MetaRegistry 中已注册
    
    Raises:
        ValueError: 表名不合法
    """
    if not table_name or not isinstance(table_name, str):
        raise ValueError(f"Invalid table_name: {table_name!r}")
    
    if len(table_name) > MAX_TABLE_NAME_LENGTH:
        raise ValueError(f"Table name too long: {len(table_name)} > {MAX_TABLE_NAME_LENGTH}")
    
    if not _TABLE_NAME_PATTERN.match(table_name):
        raise ValueError(
            f"Table name '{table_name}' contains invalid characters. "
            f"Only lowercase letters, digits, and underscores are allowed."
        )
    
    return table_name
```

#### 9.3.2 CORS 环境感知配置

```python
# server.py 修改后

@app.after_request
def add_cors_headers(response):
    allowed_origins_str = os.environ.get('CORS_ALLOWED_ORIGINS', '')
    allowed_origins = [o.strip() for o in allowed_origins_str.split(',') if o.strip()]
    request_origin = request.headers.get('Origin', '')
    
    is_dev = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    if allowed_origins and request_origin in allowed_origins:
        response.headers['Access-Control-Allow-Origin'] = request_origin
    elif is_dev:
        response.headers['Access-Control-Allow-Origin'] = request_origin
    else:
        pass  # 生产环境无白名单时不发送 CORS 头
    
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response
```

#### 9.3.3 require_permission 装饰器设计

```python
# meta/services/auth_middleware.py 新增

import re
from functools import wraps
from flask import request, g, jsonify

def require_permission(permission_pattern: str):
    """
    基于模板的权限检查装饰器
    
    用法:
        @require_permission('{object_type}.create')
        def create_bo(object_type):
            ...
    
    模板变量:
        {object_type} - 从 URL 参数提取
    """
    param_names = re.findall(r'\{(\w+)\}', permission_pattern)
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            perm_code = permission_pattern
            for param in param_names:
                value = kwargs.get(param) or request.view_args.get(param)
                if value:
                    perm_code = perm_code.replace(f'{{{param}}}', str(value))
            
            current_user = get_current_user()
            if not current_user:
                return jsonify({'