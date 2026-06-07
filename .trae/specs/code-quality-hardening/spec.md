# Spec: 代码质量硬化与安全加固

> **Spec ID**: code-quality-hardening
> **版本**: v1.0.0
> **创建日期**: 2026-05-19
> **状态**: Draft（待审阅确认）
> **优先级**: P0（Critical）
> **关联文档**:
> - [YAML 单一事实原则优化 Spec](../yaml-single-source-of-truth-enhancement/spec.md)
> - [架构总览](../../docs/ARCHITECTURE_V2.md)
> - [YAML 规范 v2.0](../../docs/architecture/02-yaml-conventions-v2.md)

---

## 目录

1. [背景与目标](#一背景与目标)
2. [需求类型概览](#二需求类型概览)
3. [功能需求](#三功能需求)
4. [非功能需求](#四非功能需求)
5. [外部接口需求](#五外部接口需求)
6. [过渡需求](#六过渡需求)
7. [约束与假设](#七约束与假设)
8. [优先级与里程碑建议](#八优先级与里程碑建议)
9. [变更与设计方案（RFC）](#九变更与设计方案rfc)
10. [待明确清单（TBD）](#十待明确清单tbd)

---

## 一、背景与目标

### 1.1 背景

2026-05-19 对 ArchWorkspace 代码库进行了全面代码质量审计，审计范围覆盖：

- **Python 后端**：`server.py`、`bo_framework.py`、`yaml_loader.py`、`rule_chain.py`、`models.py`、`datasource.py`、16 个拦截器、39 个 API 模块、60+ 服务模块
- **YAML Schema**：36 个 YAML 元数据文件
- **Vue 3 前端**：路由系统（`router/index.js` + `dynamicRoutes.js`）、composables、stores、components
- **测试体系**：100+ Python 测试文件、60+ E2E 用例

审计发现 **3 个 P0 Critical 风险和 4 个 P1 High 风险**，涉及安全、工程质量、架构一致性等方面。

### 1.2 业务目标

| 目标 | 衡量指标 | 当前值 | 目标值 |
|------|---------|--------|--------|
| 消除安全漏洞 | CORS 配置正确性、SQL 注入防护 | ⚠️ 存在漏洞 | ✅ 零漏洞 |
| 提升工程质量 | 测试目录清洁度、代码命名一致性 | ⚠️ 混乱 | ✅ 规范化 |
| 完善架构一致性 | YAML actions 命名统一、路由全量动态化 | ⚠️ 不一致 | ✅ 统一 |
| 提高可维护性 | server.py 启动流程复杂度 | 🟡 过高 | ✅ 可拆分 |

### 1.3 涉众目标

| 角色 | 目标 | 收益 |
|------|------|------|
| **后端开发者** | 清晰的启动流程、统一的命名规范 | 降低认知负担，减少出错 |
| **前端开发者** | 单一路由入口、TypeScript 支持 | 提升开发效率 |
| **QA/测试工程师** | 干净的测试目录、可区分调试脚本 | 提升测试效率 |
| **安全审计员** | SQL 注入防护、正确的 CORS 配置 | 满足安全合规 |
| **IT 运维** | 生产环境安全开关、启动容错 | 减少故障停机 |

---

## 二、需求类型概览

| 类型 | 是否适用 | 证据来源 |
|------|---------|---------|
| **业务需求** | 是 | 代码质量审计报告，安全合规要求 |
| **用户/涉众需求** | 是 | 各角色目标分析（见 §1.3） |
| **解决方案需求** | 是 | 代码分析发现的具体问题 |
| **功能需求** | 是 | §3（P0/P1/P2 修复项） |
| **非功能需求** | 是 | 安全性、可维护性、可测试性 |
| **外部接口需求** | 是 | CORS 配置、API 权限检查 |
| **过渡需求** | 是 | YAML 命名迁移、路由渐进式迁移 |

---

## 三、功能需求

### P0（Critical）— 必须立即修复

---

#### FR-001: SQL 注入防护加固

- **描述**: 系统 MUST 对所有动态 SQL 标识符（表名、列名）使用白名单校验或参数化查询，防止 YAML 元数据被恶意构造后导致 SQL 注入。
- **当前问题**:
  - `bo_framework.py:113` — `f"SELECT * FROM {table_name} WHERE id = ?"` 中 `table_name` 未校验
  - `action_executor.py` 中类似模式
  - `cascade_service.py` 中类似模式
- **验收标准**:
  - [ ] 所有 `f"SELECT ... FROM {table_name}"` 模式替换为参数化查询或添加白名单校验
  - [ ] `table_name` 在 YAML 加载时进行正则校验 `^[a-z][a-z0-9_]*$`
  - [ ] 新增安全测试用例覆盖 SQL 注入场景
  - [ ] 代码审查确认无遗漏
- **优先级**: Must（P0）
- **类型映射**: 功能需求 + 非功能需求（安全性）
- **来源**: 代码审计 — [bo_framework.py](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L113)

---

#### FR-002: CORS 安全配置修复

- **描述**: 系统 MUST 在生产环境强制校验 CORS 来源白名单，禁止 `Access-Control-Allow-Origin: *`（允许任意来源）。
- **当前问题**:
  - `server.py:258` — 当 `CORS_ALLOWED_ORIGINS` 为空时，允许任意 Origin
  - 生产环境无强制检查
- **验收标准**:
  - [ ] 生产环境启动时，若 `CORS_ALLOWED_ORIGINS` 为空则**拒绝启动**或输出严重警告
  - [ ] CORS 逻辑修改为：空配置时返回 `403 Forbidden`（而非允许所有来源）
  - [ ] 添加环境区分逻辑：开发环境允许宽松 CORS，生产环境严格校验
  - [ ] 添加 `.env.example` 中的 CORS 配置说明
- **优先级**: Must（P0）
- **类型映射**: 功能需求 + 非功能需求（安全性）
- **来源**: 代码审计 — [server.py](file:///d:/filework/excel-to-diagram/meta/server.py#L251-L263)

---

#### FR-003: 测试目录清理

- **描述**: 系统 MUST 将 `meta/tests/` 中的所有非测试脚本（调试工具、数据填充脚本、诊断工具）移出测试目录。
- **当前问题**:
  - `meta/tests/` 中存在以下非测试文件：
    - 调试脚本：`debug_resolve.py`, `debug_resolve2.py`, `debug_field.py`, `debug_condition.py`, `pinpoint_root_cause.py`
    - 工具脚本：`quick_replace.py`, `quick_replace_debug.py`, `fix_test_paths.py`, `analyze_tests.py`, `batch_update_db_path.py`, `show_db_structure.py`
    - 数据填充脚本：`add_product1.py`, `add_v1_data.py`, `add_test_data_v2.py`, `add_missing_data.py`, `add_version1.py`, `check_products.py`, `init_test_data.py`
    - 其他：`run_all_tests.py`（应移到项目根目录）
- **验收标准**:
  - [ ] 调试脚本移入 `meta/dev/` 目录
  - [ ] 数据填充脚本移入 `scripts/seed/` 目录
  - [ ] 工具脚本移入 `scripts/` 目录
  - [ ] `pytest` 运行时不应意外执行非测试文件
  - [ ] 更新 `pytest.ini`，添加 `testpaths = meta/tests` 和 `python_files = test_*.py`
- **优先级**: Must（P0）
- **类型映射**: 功能需求 + 过渡需求
- **来源**: 代码审计 — `meta/tests/` 目录文件清单

---

### P1（High）— 应尽快修复

---

#### FR-004: YAML Actions 命名规范统一

- **描述**: 系统 MUST 将所有 BO YAML 文件中的 `actions` 命名统一为 `{object_type}_{crud_action}` 格式（如 `product_create`, `product_read`），消除当前混合使用 `crud_create` / `user_create` / `role_create` 的不一致。
- **当前问题**:
  - `product.yaml` — 使用 `crud_create`, `crud_read`, ...（旧风格）
  - `user.yaml` — 使用 `user_create`, `user_read`, ...（新风格）
  - `role.yaml` — 使用 `role_create`, `role_read`, ...（新风格）
  - `menu.yaml` — 使用 `menu_create`, `menu_read`, ...（新风格）
  - 其他 BO YAML 混用两种风格
- **验收标准**:
  - [ ] 所有 BO YAML 的 `actions[].id` 统一为 `{bo_id}_{action}` 格式
  - [ ] `PermissionSyncService` 的 `_parse_code()` 方法适配统一格式
  - [ ] `menu_permission_service.py` 权限推导逻辑适配
  - [ ] 前端 `requiredPermissions` 引用全部更新
  - [ ] 权限表（`permissions` 表）重新同步无残留
  - [ ] 测试用例更新并通过（至少覆盖 product/user/role/menu 四个典型 BO）
- **优先级**: Should（P1）
- **类型映射**: 功能需求 + 过渡需求
- **来源**: 代码审计 — YAML Schema 一致性对比

---

#### FR-005: 静态路由全量迁移到动态路由

- **描述**: 系统 SHOULD 将 `router/index.js` 中所有硬编码的 BO 相关路由迁移到动态路由系统，实现路由配置的"YAML 单一事实原则"。
- **当前问题**:
  - `router/index.js` 中仍有约 15 个业务路由硬编码
  - 新增 BO 时需同时在 YAML 和 Router 两处配置
  - 违背 Spec `yaml-single-source-of-truth-enhancement` 的核心设计目标
- **迁移清单**:
  | 路由路径 | 名称 | 迁移方式 |
  |---------|------|---------|
  | `/product-management` | `product-management` | menu.yaml 添加 `bo_bindings` |
  | `/user-permission/:tab?` | `user-permission` | menu.yaml 添加 `multi_object_hub` 配置 |
  | `/business-config/:tab?` | `business-config` | menu.yaml 添加 `multi_object_hub` 配置 |
  | `/system/archdata` | `ArchDataManagement` | menu.yaml 配置 |
  | `/system/role-permission/:roleId` | `RolePermissionCenter` | 动态路由参数化支持 |
  | `/system/role-detail/:roleId` | `RolePermissionDetail` | 统一为 `/detail/role/:id` |
  | `/detail/:objectType` / `/:id` | `ObjectDetail/Create` | **保留**（通用详情路由，但简化） |
  | `/role/:id` | `RoleDetail` | 合并到 `/detail/role/:id` |
  | `/account` | `AccountSettings` | **保留**（非 BO 页面） |
- **验收标准**:
  - [ ] 所有 BO 对象列表页路由从 `router/index.js` 移除
  - [ ] `menu.yaml` + `menu_auto_generator` 覆盖所有 BO 路由
  - [ ] `dynamicRoutes.js` 支持带参数路由（如 `:id`, `:tab?`）
  - [ ] 保留的非 BO 路由（landing, login, test, account 等）在 `STATIC_ROUTE_PATHS` 中明确维护
  - [ ] E2E 测试通过（60+ 用例）
  - [ ] 硬编码路由数从 ~25 降至 ~8（仅保留 landing、login、test、theme-preview、diagram、config、account、detail 通用路由）
- **优先级**: Should（P1）
- **类型映射**: 功能需求 + 过渡需求
- **来源**: 代码审计 — [router/index.js](file:///d:/filework/excel-to-diagram/src/router/index.js#L34-L181), Spec 文档

---

#### FR-006: server.py 启动流程重构

- **描述**: 系统 SHOULD 将 `server.py` 中 `create_app()` 的启动流程拆分为独立的 Bootstrap 模块，降低单函数复杂度，提高容错性和可测试性。
- **当前问题**:
  - `create_app()` 承担了 9 类职责（见 RFC §9.1）
  - 服务初始化顺序隐式耦合
  - 某个服务初始化失败会导致整个应用无法启动
- **验收标准**:
  - [ ] 创建 `meta/core/app_builder.py` — 应用构建器
  - [ ] 实现 `AppBuilder` 类，支持链式调用
    ```python
    app = (AppBuilder()
        .with_schema_loader(schema_dir)
        .with_data_source(db_path)
        .with_services(data_source)
        .with_interceptors(data_source)
        .with_blueprints()
        .with_error_handlers()
        .build())
    ```
  - [ ] 各初始化阶段独立的 try/except 容错
  - [ ] 非关键服务（如审计日志检查）初始化失败不影响主应用启动
  - [ ] `create_app()` 简化为 AppBuilder 的调用入口
  - [ ] 单元测试可单独测试各 Bootstrap 步骤
- **优先级**: Should（P1）
- **类型映射**: 功能需求 + 非功能需求（可维护性）
- **来源**: 代码审计 — [server.py](file:///d:/filework/excel-to-diagram/meta/server.py#L159-L230)

---

#### FR-007: API 层权限前置检查

- **描述**: 系统 SHOULD 在 API 路由层增加显式的权限前置检查，作为拦截器链权限检查的补充防线（纵深防御）。
- **当前问题**:
  - [bo_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L48-L84) `create_bo` 只有 `@login_required`，无显式对象级权限检查
  - 如果拦截器链中的权限拦截器因配置遗漏未能触发，可能导致权限绕过
- **验收标准**:
  - [ ] 在 `auth_middleware.py` 中新增 `@require_permission(permission_code)` 装饰器
  - [ ] 关键 CRUD API 端点添加权限装饰器：
    ```python
    @bo_bp.route('/<object_type>', methods=['POST'])
    @login_required
    @require_permission('{object_type}:create')  # 动态推导
    def create_bo(object_type): ...
    ```
  - [ ] 权限装饰器失败时返回 `403 Forbidden`，不依赖拦截器链
  - [ ] 添加权限矩阵测试（针对常见 object_type × action 组合）
- **优先级**: Should（P1）
- **类型映射**: 功能需求 + 非功能需求（安全性）
- **来源**: 代码审计 — [bo_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L48-L84)

---

### P2（Medium）— 应计划修复

---

#### FR-008: 前端 TypeScript 渐进引入

- **描述**: 系统 COULD 在前端引入 TypeScript，从核心模块（router、stores、services）开始渐进迁移。
- **验收标准**:
  - [ ] `vite.config.js` 添加 TypeScript 支持（或迁移为 `vite.config.ts`）
  - [ ] `src/router/dynamicRoutes.js` → `dynamicRoutes.ts`
  - [ ] `src/stores/authStore.js` → `authStore.ts`
  - [ ] `src/services/objectTypeService.js` → `objectTypeService.ts`
  - [ ] 引入 `vue-tsc` 进行类型检查
- **优先级**: Could（P2）
- **类型映射**: 非功能需求（代码质量）
- **来源**: 代码审计

---

#### FR-009: 数据库连接池管理

- **描述**: 系统 COULD 为 SQLite 添加连接池管理和并发控制。
- **验收标准**:
  - [ ] 实现 `ConnectionPool` 类，支持最大连接数配置
  - [ ] WAL 模式下正确管理 `.db-shm` 和 `.db-wal` 文件
  - [ ] 定期 WAL checkpoint
  - [ ] 连接获取超时配置
- **优先级**: Could（P2）
- **类型映射**: 非功能需求（性能、可靠性）
- **来源**: 代码审计

---

#### FR-010: CI/CD 代码质量门禁

- **描述**: 系统 COULD 在 CI/CD 流程中增加代码质量检查（lint、安全扫描、一致性检查）。
- **验收标准**:
  - [ ] GitHub Actions 中添加 `pytest` 步骤（失败则阻止合并）
  - [ ] 添加 Python lint（`flake8` 或 `ruff`）
  - [ ] 添加 `permission_sync.check_consistency` 步骤
  - [ ] 添加 `bandit` 安全扫描
  - [ ] 添加前端 `vue-tsc` 类型检查（引入 TS 后）
- **优先级**: Could（P2）
- **类型映射**: 非功能需求（工程质量）
- **来源**: 代码审计 + Spec 文档

---

## 四、非功能需求

### NFR-001: 安全性

- **描述**: 零已知安全漏洞。
- **度量方法**: 安全扫描（bandit）+ 手动代码审查 + OWASP Top 10 对照检查
- **目标值**: 0 个高危漏洞
- **优先级**: Must（P0）
- **关联**: FR-001, FR-002, FR-007

### NFR-002: 可维护性

- **描述**: server.py 单函数行数不超过 100 行，单文件不超过 500 行。
- **度量方法**: `wc -l` + 人工审查
- **目标值**: `create_app()` ≤ 100 行，`server.py` ≤ 500 行
- **优先级**: Should（P1）
- **关联**: FR-006

### NFR-003: 可测试性

- **描述**: 测试目录只包含测试文件，非测试脚本有明确的独立目录。
- **度量方法**: `meta/tests/` 文件清单审查
- **目标值**: 0 个非测试脚本存在于 `meta/tests/` 中
- **优先级**: Must（P0）
- **关联**: FR-003

### NFR-004: 一致性

- **描述**: 所有 BO YAML 的 actions 命名遵循统一规范。
- **度量方法**: 脚本扫描所有 YAML 文件的 `actions[].id` 模式
- **目标值**: 100% 统一为 `{bo_id}_{action}` 格式
- **优先级**: Should（P1）
- **关联**: FR-004

### NFR-005: 架构纯度

- **描述**: 路由配置尽量少地硬编码，尽量多地由 YAML 菜单驱动。
- **度量方法**: 统计 `router/index.js` 中硬编码路由数
- **目标值**: 硬编码路由 ≤ 8（仅保留非 BO 页面）
- **优先级**: Should（P1）
- **关联**: FR-005

---

## 五、外部接口需求

### IF-001: CORS 中间件行为变更

- **类型**: API 安全配置
- **入口**: `Flask @app.after_request` — `add_cors_headers`
- **变更前**: 空 `CORS_ALLOWED_ORIGINS` 时允许任意来源
- **变更后**:
  ```python
  @app.after_request
  def add_cors_headers(response):
      allowed_origins_str = os.environ.get('CORS_ALLOWED_ORIGINS', '')
      allowed_origins = [o.strip() for o in allowed_origins_str.split(',') if o.strip()]
      request_origin = request.headers.get('Origin', '')
      
      is_dev = os.environ.get('FLASK_ENV', 'production') == 'development'
      
      if is_dev and not allowed_origins:
          # 开发环境宽松模式
          response.headers['Access-Control-Allow-Origin'] = request_origin or '*'
      elif allowed_origins and request_origin in allowed_origins:
          response.headers['Access-Control-Allow-Origin'] = request_origin
      else:
          # 生产环境 + 未配置白名单 + 未匹配 → 不设置 CORS 头
          pass
      
      response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
      response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
      response.headers['Access-Control-Allow-Credentials'] = 'true'
      return response
  ```
- **错误处理**: 生产环境未配置 CORS 时，启动阶段输出 WARNING 日志
- **来源**: 代码审计

### IF-002: require_permission 装饰器 API

- **类型**: API 中间件
- **入口**: 新增 `meta/services/auth_middleware.py` 中的 `require_permission` 装饰器
- **签名**:
  ```python
  def require_permission(permission_code: str):
      """
      权限前置检查装饰器
      
      Args:
          permission_code: 权限编码，如 'product:create'。
                          支持 {object_type} 占位符，从 URL 参数动态替换。
      """
  ```
- **使用示例**:
  ```python
  @bo_bp.route('/<object_type>', methods=['POST'])
  @login_required
  @require_permission('{object_type}:create')
  def create_bo(object_type): ...
  ```
- **错误处理**: 权限不足返回 `403 {'success': False, 'error': 'PERMISSION_DENIED', 'message': '需要权限 product:create'}`
- **来源**: 代码审计 + FR-007

---

## 六、过渡需求

### TR-001: YAML Actions 命名迁移

- **描述**: 将旧风格的 `crud_create`/`crud_read`/... action ID 迁移到 `{bo_id}_create`/`{bo_id}_read`/... 新风格。
- **策略**:
  1. **Phase A**: 编写迁移脚本 `scripts/migrate_action_names.py`
     - 读取所有 YAML 文件
     - 将 `crud_*` 替换为 `{bo_id}_*`
     - 备份原文件
  2. **Phase B**: 运行 `permission_sync_service.sync_all()` 重新同步权限表
  3. **Phase C**: 前端权限引用批量更新（搜索替换）
  4. **Phase D**: 运行全量测试验证
- **回滚计划**:
  ```bash
  # 从备份恢复 YAML 文件
  cp meta/schemas/backup_*.yaml meta/schemas/
  # 重新同步权限
  python -m meta.tools.permission_sync --sync --reset
  ```
- **来源**: FR-004

### TR-002: 路由渐进式迁移

- **描述**: 将硬编码路由逐步迁移到动态路由，保持向后兼容。
- **策略**:
  1. 优先迁移简单列表页（如 `/product-management` → menu.yaml 条目）
  2. 复杂路由（如带参数路由）在 Phase 2 处理
  3. 每次迁移后运行 E2E 测试验证
  4. 新旧路由并存至少一个迭代周期
- **回滚计划**: 恢复 `router/index.js` 中的路由定义，禁用对应 menu.yaml 条目
- **来源**: FR-005

### TR-003: 测试目录重组

- **描述**: 将 `meta/tests/` 中的非测试文件迁移到正确位置，不影响现有测试运行。
- **策略**:
  1. 先创建目标目录结构：`meta/dev/`, `scripts/seed/`
  2. 移动文件（使用 `git mv` 保留历史）
  3. 更新可能的 import 引用
  4. 更新 `pytest.ini` 配置
  5. 运行全量测试验证
- **回滚计划**: `git revert`
- **来源**: FR-003

---

## 七、约束与假设

### 7.1 技术约束

- **Python 版本**: 依赖当前 `requirements.txt`，不引入新的 Python 版本依赖
- **Flask 版本**: 使用现有 Flask + Flask-SocketIO，不迁移 Web 框架
- **SQLite**: 不在此 Spec 中切换到 PostgreSQL，数据库迁移属于 P2 FR-009
- **Vue 版本**: 不升级 Vue 主版本，TypeScript 引入为渐进式
- **向后兼容**: 所有变更必须保持现有 API 契约不变（除非明确标记为 Breaking Change）

### 7.2 业务约束

- **开发窗口**: 在 `yaml-single-source-of-truth-enhancement` Spec Phase 4 完成后开始
- **风险等级**: P0 项必须在下一个迭代内完成，P1 项在 2 个迭代内完成

### 7.3 假设

- 所有 YAML 文件结构清晰，可被脚本批量处理 — 假设已确认
- 前端 E2E 测试（60+ 用例）覆盖了关键路径 — 假设已确认
- 权限表数据可通过 `permission_sync_service` 重建 — 假设已确认
- 没有外部系统依赖于具体的 actions 命名格式 — 假设待确认（见 TBD-1）

---

## 八、优先级与里程碑建议

| ID | 需求 | 优先级 | 预估工作量 | 依赖 |
|----|------|--------|-----------|------|
| FR-001 | SQL 注入防护 | Must（P0） | 1 天 | 无 |
| FR-002 | CORS 安全配置 | Must（P0） | 0.5 天 | 无 |
| FR-003 | 测试目录清理 | Must（P0） | 0.5 天 | 无 |
| FR-004 | YAML Actions 命名统一 | Should（P1） | 1.5 天 | FR-003 |
| FR-005 | 静态路由迁移 | Should（P1） | 2 天 | FR-004 |
| FR-006 | server.py 重构 | Should（P1） | 2 天 | 无 |
| FR-007 | API 权限前置检查 | Should（P1） | 1 天 | 无 |
| FR-008 | TypeScript 引入 | Could（P2） | 3 天 | FR-005 |
| FR-009 | 连接池管理 | Could（P2） | 1.5 天 | 无 |
| FR-010 | CI/CD 质量门禁 | Could（P2） | 1 天 | FR-003 |

### 建议里程碑

#### 里程碑 1：安全与工程基础（P0）- 预计 2 天

- FR-001: SQL 注入防护
- FR-002: CORS 安全配置
- FR-003: 测试目录清理

#### 里程碑 2：架构一致性（P1）- 预计 1 周

- FR-004: YAML Actions 命名统一
- FR-005: 静态路由迁移
- FR-006: server.py 启动流程重构
- FR-007: API 权限前置检查

#### 里程碑 3：长期工程提升（P2）- 预计 1 周

- FR-008: TypeScript 渐进引入
- FR-009: 数据库连接池
- FR-010: CI/CD 质量门禁

---

## 九、变更与设计方案（RFC）

### 9.1 As-Is 分析

#### 当前架构痛点

```
┌─────────────────────────────────────────────────────────────────┐
│                      当前架构痛点地图                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  server.py (500+ 行)                                            │
│  ├── 端口管理 (is_port_in_use, kill_processes_on_port)         │
│  ├── PID 管理 (write_pid_file, cleanup_pid_file)               │
│  ├── 环境变量加载 (.env)                                        │
│  ├── 日志配置                                                    │
│  ├── create_app():                                              │
│  │   ├── Schema 注册                                            │
│  │   ├── 10+ 服务初始化                                         │
│  │   ├── 数据库迁移                                              │
│  │   ├── BO Framework + 12 拦截器注册                           │
│  │   ├── 菜单自动生成                                            │
│  │   ├── 审计日志检查                                            │
│  │   ├── 35+ Blueprint 注册                                     │
│  │   ├── 错误处理注册                                            │
│  │   └── CORS 配置                                              │
│  └── main() / WebSocket 初始化                                   │
│                                                                 │
│  meta/tests/ (100+ 文件)                                        │
│  ├── test_*.py (真实测试)                                       │
│  ├── debug_*.py (调试脚本) ← 混乱                               │
│  ├── add_*.py (数据填充) ← 混乱                                 │
│  └── quick_*.py (工具) ← 混乱                                   │
│                                                                 │
│  router/index.js + dynamicRoutes.js                             │
│  ├── 静态路由 ~25 个 (硬编码)                                   │
│  └── 动态路由 (运行时注入)                                      │
│      → 双轨制，违背单一事实原则                                  │
│                                                                 │
│  YAML Schema (36 文件)                                          │
│  ├── product.yaml: crud_create / crud_read (旧风格)            │
│  ├── user.yaml: user_create / user_read (新风格)               │
│  └── → actions 命名不统一                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 相关代码路径

| 文件 | 行数 | 问题 |
|------|------|------|
| [server.py](file:///d:/filework/excel-to-diagram/meta/server.py) | ~500 | 启动流程臃肿 |
| [bo_framework.py](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py) | ~350 | SQL 注入风险 |
| [bo_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py) | ~300 | 缺少权限前置检查 |
| [router/index.js](file:///d:/filework/excel-to-diagram/src/router/index.js) | ~260 | 硬编码路由多 |
| [dynamicRoutes.js](file:///d:/filework/excel-to-diagram/src/router/dynamicRoutes.js) | ~160 | 功能良好但未全面使用 |
| `meta/tests/` | 100+ 文件 | 非测试文件混入 |
| `meta/schemas/*.yaml` | 36 文件 | actions 命名不一致 |

### 9.2 目标状态

```
┌─────────────────────────────────────────────────────────────────┐
│                      目标架构                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  meta/core/app_builder.py (新建)                                │
│  ├── AppBuilder 类 (链式调用)                                   │
│  ├── SchemaLoaderStep                                            │
│  ├── DataSourceStep                                              │
│  ├── ServicesStep                                                │
│  ├── InterceptorsStep                                            │
│  ├── BlueprintsStep                                              │
│  └── ErrorHandlersStep                                           │
│                                                                 │
│  server.py (< 300 行)                                           │
│  └── create_app() → AppBuilder 入口                             │
│                                                                 │
│  meta/tests/ (仅测试文件)                                       │
│  ├── test_*.py ✅                                                │
│  ├── conftest.py ✅                                              │
│  └── (无调试/工具脚本) ✅                                        │
│                                                                 │
│  meta/dev/ (调试脚本)                                            │
│  scripts/seed/ (数据填充)                                        │
│  scripts/ (工具脚本)                                             │
│                                                                 │
│  router/index.js (仅 ~8 个静态路由)                              │
│  ├── landing, login, test, theme-preview                        │
│  ├── diagram, config, account                                   │
│  └── /detail/:objectType (通用 CRUD 路由)                       │
│                                                                 │
│  router/dynamicRoutes.js (所有 BO 路由)                          │
│  ├── menu.yaml → 运行时注入                                     │
│  └── 支持 :id, :tab? 参数                                       │
│                                                                 │
│  YAML Schema (统一命名)                                          │
│  ├── product.yaml: product_create / product_read ✅             │
│  ├── user.yaml: user_create / user_read ✅                      │
│  └── → 100% 统一                                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 9.3 详细设计

#### 9.3.1 AppBuilder 设计（FR-006）

```python
# meta/core/app_builder.py

class AppBuilder:
    """Flask 应用构建器"""
    
    def __init__(self):
        self._app = None
        self._data_source = None
        self._steps_completed = []
        self._errors = []
    
    def with_schema_loader(self, schema_dir: str) -> 'AppBuilder':
        try:
            from meta.core.yaml_loader import register_from_directory
            register_from_directory(schema_dir)
            self._steps_completed.append('schema_loader')
        except Exception as e:
            self._errors.append(('schema_loader', e))
        return self
    
    def with_data_source(self, db_path: str) -> 'AppBuilder':
        try:
            from meta.core.datasource import get_data_source
            self._data_source = get_data_source("sqlite", database=db_path)
            self._steps_completed.append('data_source')
        except Exception as e:
            self._errors.append(('data_source', e))
        return self
    
    def with_services(self) -> 'AppBuilder':
        """初始化所有业务服务（容错模式）"""
        services = [
            ('manage', lambda: init_manage_services(self._data_source)),
            ('auth', lambda: init_auth_services(self._data_source)),
            ('user', lambda: init_user_services(self._data_source)),
            ('role', lambda: init_role_services(self._data_source)),
            # ...
        ]
        for name, init_fn in services:
            try:
                init_fn()
                self._steps_completed.append(f'service:{name}')
            except Exception as e:
                self._errors.append((f'service:{name}', e))
                # 非关键服务失败不阻止启动
        return self
    
    def with_interceptors(self) -> 'AppBuilder':
        """注册拦截器链"""
        # ...
        return self
    
    def with_blueprints(self) -> 'AppBuilder':
        """注册所有 Blueprint"""
        # ...
        return self
    
    def build(self) -> Flask:
        """构建并返回 Flask 应用"""
        self._app = Flask(__name__)
        # 注册错误处理、CORS 等
        # 输出启动总结
        if self._errors:
            logger.warning(f"App started with {len(self._errors)} non-critical errors")
        return self._app
```

#### 9.3.2 SQL 注入防护设计（FR-001）

**方案选择**:

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| A: 统一使用参数化查询 | 标准做法，安全可靠 | 表名/列名无法参数化 | 用于值参数 |
| B: YAML 加载时校验表名 | 源头防护，一次性 | 需修改 yaml_loader | **选定** |
| C: 每个 SQL 执行点加白名单 | 最细粒度 | 维护成本高 | 补充方案 |

**选定方案: B（主） + A（辅）**

```python
# meta/core/yaml_loader.py 中添加

import re
TABLE_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')

def _validate_table_name(table_name: str) -> str:
    if not TABLE_NAME_PATTERN.match(table_name):
        raise ValueError(f"Invalid table_name: {table_name}")
    return table_name

# 在解析 YAML 时调用
def parse_meta_object(data: dict) -> MetaObject:
    table_name = data.get('table_name', '')
    _validate_table_name(table_name)
    # ...
```

#### 9.3.3 require_permission 装饰器设计（FR-007）

```python
# meta/services/auth_middleware.py 中添加

from functools import wraps
from flask import request, jsonify, g

def require_permission(permission_code: str):
    """
    权限前置检查装饰器。
    支持占位符 {object_type} 从 URL 参数动态获取。
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # 解析占位符
            resolved_code = permission_code
            for key, value in kwargs.items():
                resolved_code = resolved_code.replace(f'{{{key}}}', str(value))
            
            # 检查权限
            current_user = get_current_user()
            if not current_user:
                return jsonify({'success': False, 'error': 'UNAUTHORIZED'}), 401
            
            user_permissions = current_user.get('permissions', [])
            if resolved_code not in user_permissions:
                return jsonify({
                    'success': False,
                    'error': 'PERMISSION_DENIED',
                    'message': f'需要权限 {resolved_code}'
                }), 403