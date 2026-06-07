# Spec: BOFramework 代码质量与性能优化（P0+P1）

## 1. 背景与目标

### 1.1 背景

BOFramework 是项目的核心元模型驱动框架，采用拦截器链模式实现横切关注点解耦。经过深度代码审查，发现以下问题：

- **死代码**：`bo_framework.py` 中 `_execute_create/_execute_read/_execute_query/_execute_update/_execute_delete` 5个方法永远不会被调用（实际 CRUD 由 `PersistenceInterceptor` 执行），但仍然存在且包含有缺陷的实现，极易造成维护混乱
- **调试残留**：`bo_api.py`、`persistence_interceptor.py`、`bo_framework.py` 中大量 `print()` 语句和写文件日志残留
- **日志级别滥用**：正常流程使用 `logger.critical`，影响生产环境日志可读性
- **SQL 安全**：`LIMIT/OFFSET` 直接拼接而非参数化，字段名未做白名单校验
- **N+1 查询**：`QueryInterceptor._check_can_delete` 逐条查询，大数据量时性能急剧下降
- **缓存无上限**：前端 `boService/metaService` 使用 `Map` 缓存无大小限制，长时间 SPA 运行可能内存泄漏
- **FieldPolicy 每次实例化**：每次请求都创建新的 `FieldPolicyValidationInterceptor` 实例

### 1.2 业务目标

- 消除安全隐患（SQL 参数化）
- 提升代码可维护性（删除死代码、清理调试残留、修正日志级别）
- 优化查询性能（N+1 查询批量化）
- 防止内存泄漏（前端缓存 LRU 上限）
- **零功能回归**：所有修改不影响现有过滤、搜索、分页、CRUD 功能

### 1.3 用户/涉众目标

- **开发团队**：代码更清晰、更易维护、更安全
- **终端用户**：大数据量列表页面响应更快
- **运维团队**：日志更干净、更易排查问题

## 2. 需求类型概览

| 类型 | 适用 | 证据（来源） |
|------|------|-------------|
| 业务需求 | 是 | 提升系统安全性和可维护性 |
| 用户/涉众需求 | 是 | 大数据量场景下性能优化 |
| 解决方案需求 | 是 | SQL 参数化、LRU 缓存、批量 can_delete |
| 功能需求 | 是 | 各 FR 项 |
| 非功能需求 | 是 | 安全性、性能、可维护性 |
| 外部接口需求 | 否 | API 接口不变 |
| 过渡需求 | 否 | 无数据迁移 |

## 3. 功能需求

### FR-001: 删除 bo_framework.py 死代码

- **描述**: 系统必须删除 `bo_framework.py` 中永远不会被调用的 5 个方法：`_execute_create`、`_execute_read`、`_execute_query`、`_execute_update`、`_execute_delete`
- **验收标准**:
  - 删除 L161-L323 的 5 个方法
  - `_execute_core` 方法保持不变（空实现，委托给 PersistenceInterceptor）
  - 所有现有测试通过
  - 无任何代码路径引用这些方法
- **优先级**: Must
- **类型映射**: 解决方案需求 / 可维护性
- **来源**: 代码审查 — `_execute_core` (L144-159) 故意不设置 `context.result`，实际 CRUD 由 PersistenceInterceptor 在 after 阶段执行

### FR-002: SQL 参数化 — LIMIT/OFFSET

- **描述**: 系统必须将 `PersistenceInterceptor._do_list` 中的 `LIMIT {limit} OFFSET {offset}` 改为参数化查询 `LIMIT ? OFFSET ?`
- **验收标准**:
  - `_do_list` 中所有 SQL 的 LIMIT/OFFSET 使用 `?` 占位符
  - `limit` 和 `offset` 值通过参数列表传递
  - 添加 `limit`/`offset` 类型校验（必须为非负整数）
  - 添加 `limit` 上限校验（最大 500，防止恶意请求）
  - 所有现有查询测试通过
- **优先级**: Must
- **类型映射**: 解决方案需求 / 安全性
- **来源**: 代码审查 — `_do_list` L331 直接拼接 `LIMIT {limit or 20} OFFSET {offset or 0}`

### FR-003: SQL 参数化 — 字段名白名单校验

- **描述**: 系统必须对 `_do_list` 中动态生成的 SQL 字段名进行白名单校验，确保字段名来自 `meta_object.fields` 定义
- **验收标准**:
  - `_do_list` 中 `filters` 的 key（字段名）必须校验是否在 `meta_object.fields` 中定义
  - 不在白名单中的字段名被忽略并记录 warning 日志
  - `search_or_conditions` 中的字段名来自 `meta_object.fields` 遍历，天然安全，无需额外校验
  - 所有现有过滤测试通过
- **优先级**: Must
- **类型映射**: 解决方案需求 / 安全性
- **来源**: 代码审查 — `_do_list` L236-241 中 `filters[key] = value` 未校验 key 合法性

### FR-004: 清理调试语句

- **描述**: 系统必须清理所有生产代码中的 `print()` 语句和写文件日志
- **验收标准**:
  - `bo_api.py` 中 L39, L43, L47 的 `print(f"[DEBUG]...")` 删除
  - `persistence_interceptor.py` 中 `_do_list` 方法的所有 `print()` 语句删除
  - `persistence_interceptor.py` 中 `_do_list` 方法的写文件日志（`search_debug.log`）删除
  - `bo_framework.py` 中 `_execute_after_interceptors` 的 `print()` 语句删除
  - 保留 `logger.info/debug` 级别的必要日志
  - 所有现有测试通过
- **优先级**: Must
- **类型映射**: 解决方案需求 / 可维护性
- **来源**: 代码审查 — 多处 `print()` 残留

### FR-005: 修正日志级别

- **描述**: 系统必须将正常流程中使用的 `logger.critical` 降级为 `logger.debug`
- **验收标准**:
  - `persistence_interceptor.py` 中 `logger.critical` 改为 `logger.debug`
  - `bo_framework.py` 中 `_execute_query` 的 `logger.critical` 改为 `logger.debug`（此方法将被删除，如未删除则修正）
  - 保留真正的错误场景使用 `logger.error`
  - 保留审计相关使用 `logger.info`
- **优先级**: Must
- **类型映射**: 解决方案需求 / 可维护性
- **来源**: 代码审查 — PersistenceInterceptor L42-43, L52, L66-68 使用 `logger.critical`

### FR-006: can_delete 批量化

- **描述**: 系统必须将 `QueryInterceptor._check_can_delete` 从逐条查询改为批量查询
- **验收标准**:
  - `_check_can_delete` 一次性收集所有需要检查的记录 ID
  - 调用 `ManageService.batch_check_can_delete(object_type, items)` 批量检查
  - 新增 `ManageService.batch_check_can_delete` 方法
  - 100 条记录的 can_delete 检查从 ~200ms 降低到 ~10ms
  - 所有现有 can_delete 相关测试通过
- **优先级**: Should
- **类型映射**: 解决方案需求 / 性能
- **来源**: 代码审查 — QueryInterceptor L107-121 逐条调用 `ManageService.check_can_delete`

### FR-007: FieldPolicy 注册为框架级拦截器

- **描述**: 系统必须将 `FieldPolicyValidationInterceptor` 从每次请求实例化改为框架级注册
- **验收标准**:
  - `FieldPolicyValidationInterceptor` 在 `server.py` 中注册为拦截器（优先级 40，在 ConstraintEngine 之后）
  - `bo_framework.execute()` 中删除每次创建实例的代码（L86-98）
  - FieldPolicy 拦截器在 `before_action` 中执行校验，仅在 `crud_create/crud_update` 时生效
  - 所有现有 FieldPolicy 相关测试通过
- **优先级**: Should
- **类型映射**: 解决方案需求 / 性能 + 架构
- **来源**: 代码审查 — bo_framework.py L87-90 每次请求 `FieldPolicyValidationInterceptor(meta_object=..., data_source=...)`

### FR-008: 前端缓存 LRU 上限

- **描述**: 系统必须为 `boService` 和 `metaService` 的 `Map` 缓存添加 LRU 淘汰策略
- **验收标准**:
  - 新增 `lruCache.js` 工具类，提供 `get/set/delete/clear/size` 方法
  - 最大缓存条目数默认 100
  - 超过上限时淘汰最久未访问的条目
  - `boService` 和 `metaService` 使用 `lruCache` 替换 `Map`
  - 缓存超时逻辑保持不变（boService 5分钟，metaService 10分钟）
  - 前端功能测试通过
- **优先级**: Should
- **类型映射**: 解决方案需求 / 内存安全
- **来源**: 代码审查 — boService.js L13 `this.cache = new Map()` 无大小限制

### FR-009: 前端 Service 基类提取

- **描述**: 系统必须将 `boService` 和 `metaService` 的重复代码提取为基类
- **验收标准**:
  - 新增 `baseService.js`，包含 `_handleResponse`、`_getHeaders`、`_getAuthStore`、缓存逻辑
  - `boService` 和 `metaService` 继承 `BaseService`
  - 401 自动登出逻辑只在基类中实现一次
  - 前端功能测试通过
- **优先级**: Should
- **类型映射**: 解决方案需求 / 可维护性
- **来源**: 代码审查 — 两个 Service 的 `_handleResponse`、`_getHeaders`、缓存逻辑完全重复

## 4. 非功能需求

### NFR-001: 安全性

- **描述**: SQL 查询中不得存在参数直接拼接的情况，所有用户可控输入必须参数化
- **测量**: 代码审查确认无 SQL 拼接；`limit`/`offset` 必须为整数且 `limit <= 500`
- **优先级**: Must
- **来源**: 代码审查

### NFR-002: 性能

- **描述**: can_delete 检查批量优化后，100 条记录的列表查询总延迟应降低 50% 以上
- **测量**: 对比优化前后 100 条记录的 `/api/v2/bo/role` 查询响应时间
- **优先级**: Should
- **来源**: 性能分析

### NFR-003: 零功能回归

- **描述**: 所有修改不得改变现有 API 的行为语义，包括过滤、搜索、分页、排序、CRUD
- **测量**: 所有现有后端测试通过；前端功能手动验证
- **优先级**: Must
- **来源**: 架构原则

### NFR-004: 可维护性

- **描述**: 清理后生产代码中不得存在 `print()` 调试语句和写文件日志
- **测量**: `grep -r "print(" meta/` 无结果；`grep -r "open.*log" meta/` 无结果
- **优先级**: Must
- **来源**: 代码规范

## 5. 外部接口需求

无变更。所有 API 端点、请求/响应格式保持不变。

## 6. 过渡需求

无。不涉及数据迁移或部署变更。

## 7. 约束与假设

### 7.1 技术约束

- 后端使用 Python 3 + Flask + SQLite
- 前端使用 Vue 3 + Element Plus
- SQLite WAL 模式下写操作必须串行
- 现有 50+ 后端测试必须全部通过

### 7.2 业务约束

- 不改变 API 契约（请求/响应格式）
- 不改变 YAML Schema 结构
- 不引入新的外部依赖

### 7.3 假设

- `_execute_create/_execute_read/_execute_query/_execute_update/_execute_delete` 无外部调用方 — 来源: 已验证（grep 确认无引用）
- `PersistenceInterceptor._do_list` 是唯一的查询执行路径 — 来源: 已验证（`_execute_core` 故意空实现）
- 前端 SPA 单次会话不超过 2 小时 — 来源: 假设（LRU 缓存 100 条足够）

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 原因 |
|------|------|--------|------|
| FR-001 | 删除死代码 | Must | 消除维护混乱源 |
| FR-002 | SQL 参数化 LIMIT/OFFSET | Must | 安全 |
| FR-003 | 字段名白名单校验 | Must | 安全 |
| FR-004 | 清理调试语句 | Must | 代码质量 |
| FR-005 | 修正日志级别 | Must | 可维护性 |
| FR-006 | can_delete 批量化 | Should | 性能 |
| FR-007 | FieldPolicy 框架级注册 | Should | 性能+架构 |
| FR-008 | 前端缓存 LRU | Should | 内存安全 |
| FR-009 | 前端 Service 基类 | Should | 可维护性 |

**里程碑建议**:
- 里程碑 1 (P0): FR-001 ~ FR-005，后端安全与代码质量修复
- 里程碑 2 (P1): FR-006 ~ FR-009，性能与架构优化

## 9. 变更/设计提案（RFC）

### 9.1 As-Is 分析

**当前架构**:

```
请求 → bo_api.py → BOFramework.execute()
                       ├── ConstraintEngine.validate()
                       ├── FieldPolicyValidationInterceptor (每次新建实例)
                       ├── before 拦截器链
                       ├── _execute_core() (空实现)
                       ├── after 拦截器链
                       │    └── PersistenceInterceptor._do_list() (实际查询)
                       └── 返回 ActionResult
```

**当前问题**:

1. `bo_framework.py` 中 5 个 `_execute_*` 方法是死代码，与 `PersistenceInterceptor` 功能重复
2. `_do_list` 中 `LIMIT/OFFSET` 直接拼接，存在 SQL 注入风险
3. `_do_list` 中 `filters` 的 key 未做白名单校验
4. 大量 `print()` 和写文件日志残留
5. `logger.critical` 滥用
6. `QueryInterceptor._check_can_delete` 逐条查询（N+1 问题）
7. `FieldPolicyValidationInterceptor` 每次请求实例化
8. 前端 `Map` 缓存无上限
9. 前端两个 Service 代码重复

**相关代码路径**:

- `meta/core/bo_framework.py` — L161-323 (死代码), L87-98 (FieldPolicy 实例化), L326-336 (print)
- `meta/core/interceptors/persistence_interceptor.py` — L42-68 (critical), L163-377 (_do_list 含 print + 写文件)
- `meta/core/interceptors/query_interceptor.py` — L107-121 (can_delete N+1)
- `meta/api/bo_api.py` — L39, L43, L47 (print)
- `src/services/boService.js` — 全文件 (缓存无上限 + 代码重复)
- `src/services/metaService.js` — 全文件 (缓存无上限 + 代码重复)

### 9.2 目标状态

**优化后架构**:

```
请求 → bo_api.py → BOFramework.execute()
                       ├── ConstraintEngine.validate()
                       ├── before 拦截器链
                       │    └── FieldPolicyInterceptor (框架级，priority=40)
                       ├── _execute_core() (空实现，不变)
                       ├── after 拦截器链
                       │    ├── PersistenceInterceptor._do_list() (SQL参数化)
                       │    └── QueryInterceptor._check_can_delete() (批量)
                       └── 返回 ActionResult

前端:
  BaseService (基类，含 LRU 缓存 + 统一响应处理)
    ├── BOService extends BaseService
    └── MetaService extends BaseService
```

**关键变更**:

1. 删除 `bo_framework.py` 中 5 个死代码方法
2. `_do_list` SQL 参数化 + 字段名白名单
3. 清理所有 `print()` 和写文件日志
4. 修正日志级别
5. `can_delete` 批量化
6. `FieldPolicy` 注册为框架级拦截器
7. 前端 LRU 缓存 + Service 基类

### 9.3 详细设计

#### 9.3.1 FR-001: 删除死代码

**修改文件**: `meta/core/bo_framework.py`

删除以下方法（约 160 行）:
- `_execute_create` (L161-183)
- `_execute_read` (L185-203)
- `_execute_query` (L205-279)
- `_execute_update` (L281-308)
- `_execute_delete` (L310-323)

保留:
- `_execute_core` (L144-159) — 空实现是设计意图
- `_execute_before_interceptors` (L139-142)
- `_execute_after_interceptors` (L325-336) — 但需清理 print (见 FR-004)

**影响分析**: 无功能影响。已确认 `_execute_core` 不调用任何 `_execute_*` 方法，所有 CRUD 走 `PersistenceInterceptor`。

#### 9.3.2 FR-002: SQL 参数化 LIMIT/OFFSET

**修改文件**: `meta/core/interceptors/persistence_interceptor.py`

`_do_list` 方法中两处 SQL 修改:

```python
# 修改前
count_sql = f"SELECT COUNT(*) as count FROM {meta_object.table_name} {where_sql}"
sql = f"SELECT * FROM {meta_object.table_name} {where_sql} ORDER BY id DESC LIMIT {limit or 20} OFFSET {offset or 0}"

# 修改后
safe_limit = min(int(limit or 20), 500)
safe_offset = max(int(offset or 0), 0)

count_sql = f"SELECT COUNT(*) as count FROM {meta_object.table_name} {where_sql}"
sql = f"SELECT * FROM {meta_object.table_name} {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?"
# 参数追加 safe_limit, safe_offset
```

无搜索分支（`else` 分支）中的 `ds.find()` 和 `ds.count()` 已通过 `QueryBuilder` 参数化，无需修改。

**影响分析**: 无功能影响。`limit`/`offset` 值不变，只是传递方式从拼接改为参数化。

#### 9.3.3 FR-003: 字段名白名单校验

**修改文件**: `meta/core/interceptors/persistence_interceptor.py`

在 `_do_list` 的 `for key, value in params.items()` 循环中，对 `else` 分支添加白名单校验:

```python
# 修改前
else:
    field = meta_object.get_field(key)
    if field:
        filters[field.db_column] = value
    else:
        filters[key] = value  # 无校验，任意 key 可传入

# 修改后
else:
    field = meta_object.get_field(key)
    if field:
        filters[field.db_column] = value
    else:
        logger.warning(f"[_do_list] Ignoring unknown filter field: {key}")
        # 不再添加到 filters
```

**影响分析**: 如果前端传入了 YAML 中未定义的字段名作为过滤条件，之前会被原样传入 SQL（可能报错或被忽略），现在会被明确忽略并记录 warning。现有合法过滤不受影响。

#### 9.3.4 FR-004: 清理调试语句

**修改文件**:

1. `meta/api/bo_api.py`:
   - 删除 L39: `print(f"[DEBUG] create_bo START...", flush=True)`
   - 删除 L43: `print(f"[DEBUG] data={data}", flush=True)`
   - 删除 L47: `print(f"[DEBUG] result: ...", flush=True)`

2. `meta/core/interceptors/persistence_interceptor.py`:
   - 删除 `_do_list` 中所有 `print()` 语句（约 15 处）
   - 删除 `_do_list` 中写文件日志代码（L165-172, L179-180, L192, L248, L273, L278-289, L291-292, L296-298, L300-301, L324-325, L347-348, L366-367, L369-370）
   - 删除 `import sys` 和 `log_file` 变量

3. `meta/core/bo_framework.py`:
   - 删除 `_execute_after_interceptors` 中所有 `print()` 语句（L326-336）

**影响分析**: 无功能影响。仅删除调试输出。

#### 9.3.5 FR-005: 修正日志级别

**修改文件**: `meta/core/interceptors/persistence_interceptor.py`

```python
# 修改前
logger.critical(f"\n[PersistenceInterceptor] after_action() 入口!")
logger.critical(f"   action={context.action}, is_crud={context.is_crud_action}")
logger.critical(f"通过检查，准备执行持久化操作...")
logger.critical(f"调用 _do_list: action={context.action}")
logger.critical(f"_do_list 完成! total=...")

# 修改后
logger.debug(f"[PersistenceInterceptor] after_action: action={context.action}")
logger.debug(f"[PersistenceInterceptor] executing _do_list")
logger.debug(f"[PersistenceInterceptor] _do_list completed")
```

**影响分析**: 无功能影响。仅改变日志级别。

#### 9.3.6 FR-006: can_delete 批量化

**修改文件**:
- `meta/core/interceptors/query_interceptor.py`
- `meta/services/manage_service.py` (新增方法)

**QueryInterceptor 修改**:

```python
# 修改前
def _check_can_delete(self, context, items):
    meta_obj = context.meta_object
    if not meta_obj or not getattr(meta_obj, 'deletability', None):
        return
    try:
        from meta.services.manage_service import ManageService
        service = ManageService(context.data_source)
        for item in items:  # N+1 查询！
            if isinstance(item, dict):
                item['can_delete'] = service.check_can_delete(context.object_type, item)
    except Exception as e:
        for item in items:
            if isinstance(item, dict):
                item['can_delete'] = True

# 修改后
def _check_can_delete(self, context, items):
    meta_obj = context.meta_object
    if not meta_obj or not getattr(meta_obj, 'deletability', None):
        return
    try:
        from meta.services.manage_service import ManageService
        service = ManageService(context.data_source)
        can_delete_map = service.batch_check_can_delete(context.object_type, items)
        for item in items:
            if isinstance(item, dict):
                item_id = item.get('id')
                item['can_delete'] = can_delete_map.get(item_id, True)
    except Exception as e:
        logger.debug(f"[QueryInterceptor] can_delete check skipped: {e}")
        for item in items:
            if isinstance(item, dict):
                item['can_delete'] = True
```

**ManageService 新增方法**:

```python
def batch_check_can_delete(self, object_type, items):
    """批量检查记录是否可删除"""
    deletability = ... # 从 registry 获取
    result = {}
    if not deletability:
        return {item.get('id'): True for item in items if isinstance(item, dict)}
    
    # 根据 deletability 类型批量检查
    # 例如: no_system_delete → 一次查询获取所有 is_system=True 的 ID
    # 例如: has_children → 一次 COUNT GROUP BY 查询
    
    return result
```

**影响分析**: 无功能影响。`can_delete` 的判断逻辑不变，只是从逐条查询改为批量查询。

#### 9.3.7 FR-007: FieldPolicy 框架级注册

**修改文件**:
- `meta/core/bo_framework.py` — 删除 L86-98 的内联实例化
- `meta/core/interceptors/field_policy_interceptor.py` — 新建拦截器
- `meta/server.py` — 注册拦截器

**新建 FieldPolicyInterceptor**:

```python
class FieldPolicyInterceptor(Interceptor):
    @property
    def priority(self) -> int:
        return 40  # 在 ConstraintEngine 之后，AssociationInterceptor 之前

    def before_action(self, context):
        if context.action not in ('crud_create', 'crud_update'):
            return
        
        from meta.services.field_policy_validation import FieldPolicyValidationInterceptor
        validator = FieldPolicyValidationInterceptor(
            meta_object=context.meta_object,
            data_source=context.data_source
        )
        
        if context.action == 'crud_create':
            validation_result = validator.validate_create(context.params, {
                'user_id': context.user_id,
                'user_name': context.user_name,
            })
        else:
            validation_result = validator.validate_update(
                context.object_id, context.params, {
                    'user_id': context.user_id,
                    'user_name': context.user_name,
                }
            )
        
        if not validation_result.valid:
            from meta.core.exceptions import FieldPolicyViolationError
            raise FieldPolicyViolationError(validation_result.get_error_message())

    def after_action(self, context):
        pass
```

**bo_framework.py 修改**:

删除 L86-98:
```python
# 删除这段代码
if action in ('crud_create', 'crud_update'):
    field_policy_validator = FieldPolicyValidationInterceptor(...)
    if action == 'crud_create':
        validation_result = field_policy_validator.validate_create(...)
    else:
        validation_result = field_policy_validator.validate_update(...)
    if not validation_result.valid:
        return ActionResult(success=False, message=validation_result.get_error_message())
```

**server.py 修改**:

```python
from meta.core.interceptors.field_policy_interceptor import FieldPolicyInterceptor
bo_framework.register_interceptor(FieldPolicyInterceptor())
```

**影响分析**: 功能等价。FieldPolicy 校验逻辑不变，只是从 `execute()` 内部提前返回改为拦截器 `before_action` 抛异常。需确认 `execute()` 的异常处理能正确捕获 `FieldPolicyViolationError` 并返回 `ActionResult(success=False)`。

**风险**: 当前 `execute()` 中 FieldPolicy 校验失败返回 `ActionResult(success=False)`，改为拦截器抛异常后，需要确保 `_execute_error_interceptors` 和 `except` 块能正确处理，返回相同格式的 `ActionResult`。

**缓解方案**: 在 `execute()` 的 `except` 块中捕获 `FieldPolicyViolationError`，返回 `ActionResult(success=False, message=str(e))`。

#### 9.3.8 FR-008: 前端缓存 LRU

**新建文件**: `src/utils/lruCache.js`

```javascript
export class LRUCache {
  constructor(maxSize = 100) {
    this.maxSize = maxSize
    this.cache = new Map()
  }

  get(key) {
    if (!this.cache.has(key)) return null
    const value = this.cache.get(key)
    this.cache.delete(key)
    this.cache.set(key, value)  // 移到末尾（最近访问）
    if (Date.now() - value.timestamp < value.timeout) {
      return value.data
    }
    this.cache.delete(key)
    return null
  }

  set(key, data, timeout = 5 * 60 * 1000) {
    if (this.cache.has(key)) {
      this.cache.delete(key)
    }
    this.cache.set(key, { data, timestamp: Date.now(), timeout })
    while (this.cache.size > this.maxSize) {
      const firstKey = this.cache.keys().next().value
      this.cache.delete(firstKey)
    }
  }

  delete(prefix) {
    for (const key of this.cache.keys()) {
      if (key.startsWith(prefix)) {
        this.cache.delete(key)
      }
    }
  }

  clear() {
    this.cache.clear()
  }

  get size() {
    return this.cache.size
  }
}
```

**修改文件**: `src/services/boService.js`, `src/services/metaService.js`

```javascript
// 修改前
this.cache = new Map()
this.cacheTimeout = 5 * 60 * 1000

// 修改后
import { LRUCache } from '@/utils/lruCache'
this.cache = new LRUCache(100)
// 删除 this.cacheTimeout（超时逻辑已内置于 LRUCache）
```

**影响分析**: 无功能影响。缓存行为等价，仅增加淘汰策略。

#### 9.3.9 FR-009: 前端 Service 基类

**新建文件**: `src/services/baseService.js`

```javascript
import { API_BASE_V2, getHeaders } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { LRUCache } from '@/utils/lruCache'

export class BaseService {
  constructor(cacheMaxSize = 100, cacheTimeout = 5 * 60 * 1000) {
    this.cache = new LRUCache(cacheMaxSize)
    this.cacheTimeout = cacheTimeout
  }

  _getAuthStore() {
    return useAuthStore()
  }

  _getHeaders() {
    return getHeaders(this._getAuthStore())
  }

  _getCacheKey(...parts) {
    return parts.join(':')
  }

  async _handleResponse(response) {
    if (!response) {
      return { success: false, message: '网络请求失败' }
    }
    const data = await response.json()
    if (response.status === 401) {
      this._getAuthStore().logout()
      return { success: false, message: '未授权，请重新登录', code: 401 }
    }
    if (!response.ok) {
      return {
        success: false,
        message: data.message || `请求失败: ${response.status}`,
        code: response.status,
        errors: data.errors || []
      }
    }
    return data
  }
}
```

**修改 boService.js / metaService.js**: 继承 BaseService，删除重复代码。

**影响分析**: 无功能影响。代码重构，行为等价。

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| A: FieldPolicy 保持内联实例化 | 改动最小 | 每次请求创建实例，架构不一致 | 拒绝 |
| B: FieldPolicy 注册为拦截器 | 架构一致，性能更好 | 需处理异常返回格式 | 选中 |
| A: can_delete 保持逐条查询 | 改动最小 | N+1 性能问题 | 拒绝 |
| B: can_delete 批量化 | 性能提升显著 | 需新增 ManageService 方法 | 选中 |
| A: 前端缓存用 Map | 无需改动 | 内存泄漏风险 | 拒绝 |
| B: 前端缓存用 LRU | 防止内存泄漏 | 新增工具类 | 选中 |

### 9.5 实施与迁移计划

**实施顺序**:

1. **Step 1**: FR-001 删除死代码 — 风险最低，先清理
2. **Step 2**: FR-004 清理调试语句 — 风险低
3. **Step 3**: FR-005 修正日志级别 — 风险低
4. **Step 4**: FR-002 SQL 参数化 LIMIT/OFFSET — 需仔细测试
5. **Step 5**: FR-003 字段名白名单校验 — 需仔细测试
6. **Step 6**: FR-007 FieldPolicy 框架级注册 — 需处理异常格式
7. **Step 7**: FR-006 can_delete 批量化 — 需新增方法
8. **Step 8**: FR-008 前端缓存 LRU — 前端修改
9. **Step 9**: FR-009 前端 Service 基类 — 前端重构

**风险缓解**:

| 风险 | 缓解策略 |
|------|---------|
| 删除死代码误删 | grep 确认无引用后再删除；运行全部测试 |
| SQL 参数化改变查询语义 | 对比修改前后 SQL 输出；参数化不改变值 |
| 字段名白名单误拒合法字段 | 记录 warning 日志；检查所有前端过滤字段是否在 YAML 中定义 |
| FieldPolicy 异常格式变化 | 在 `execute()` 的 except 块捕获 `FieldPolicyViolationError`，返回相同格式 |
| can_delete 批量化逻辑差异 | 逐项对比 `check_can_delete` 和 `batch_check_can_delete` 的判断结果 |

**测试策略**:

- 单元测试: 每个修改点对应的现有测试必须通过
- 集成测试: 完整的 CRUD + 查询 + 过滤 + 搜索流程
- E2E 测试: 前端列表页加载、过滤、搜索、分页、CRUD 操作
- 性能测试: 对比 can_delete 优化前后的查询响应时间

**回滚计划**:

- 每个 Step 独立提交，可单独回滚
- 后端修改通过 git revert 回滚
- 前端修改通过 git revert 回滚
- 无数据库迁移，无需数据回滚

## 10. TBD 列表

| ID | 项目 | 缺失信息 | 下一步 |
|------|------|---------|--------|
| TBD-1 | ManageService.batch_check_can_delete 实现细节 | 需要了解现有 `check_can_delete` 的所有 deletability 类型及其 SQL 查询模式 | 阅读 ManageService.check_can_delete 完整实现后设计批量方案 |
| TBD-2 | FieldPolicyViolationError 异常类 | 需确认是否已存在此类，或需新建 | 检查 exceptions.py |
| TBD-3 | 前端过滤字段是否全部在 YAML 中定义 | FR-003 白名单校验可能拒绝前端当前使用的某些字段 | 检查前端所有过滤请求参数 |
