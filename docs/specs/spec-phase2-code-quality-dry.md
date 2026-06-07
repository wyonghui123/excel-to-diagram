# Phase 2 代码质量优化 — DRY 消除 & 操作符歧义修复

> **父 Spec**: [spec-code-quality-performance-optimization.md](spec-code-quality-performance-optimization.md)
> **Phase**: Phase 2 (P1 级别)
> **范围**: FR-P1-001 ~ FR-P1-005
> **日期**: 2026-05-26

---

## 目录

1. [概述与头部产品方法论](#1-概述与头部产品方法论)
2. [FR-P1-001: audit_interceptor 重复代码消除](#2-fr-p1-001-audit_interceptor)
3. [FR-P1-002: hierarchy_validation 重复代码消除](#3-fr-p1-002-hierarchy_validation)
4. [FR-P1-003: enum_protection 重复代码消除](#4-fr-p1-003-enum_protection)
5. [FR-P1-004: association_engine 重复代码消除](#5-fr-p1-004-association_engine)
6. [FR-P1-005: SQL 操作符检测歧义修复](#6-fr-p1-005-sql-操作符检测歧义修复)
7. [实施顺序与依赖关系](#7-实施顺序与依赖关系)
8. [变更影响评估](#8-变更影响评估)

---

## 1. 概述与头部产品方法论

### 1.1 Phase 2 目标

Phase 2 聚焦 P1 优先级的代码质量优化，核心思想是 **消除重复代码**（DRY）和 **修复潜在缺陷**。5 个 FR 全部涉及代码级别的重构，不改变外部 API 行为。

### 1.2 头部产品方案映射

| 我们的问题 | SAP CAP 方案 | Salesforce 方案 | ServiceNow 方案 | 推荐方案 |
|---|---|---|---|---|
| 重复拦截器逻辑 | `@Before/@After` handler 注册 + AOP | `TriggerHandler` 虚基类 + 覆写 | Script Include 共享逻辑 + 基表继承 | **Template Method** |
| 重复校验逻辑 | `prepend()` 注册通配符 handler | `IObjectValidator` 接口 + `ValidationEngine` | UIVallidationUtils + 元数据引擎 | **提取公共方法** |
| 重复关联操作 | CQN `srv.send()` 委托模式 | Domain 层 `triggerHandler()` 统一调度 | Subflow 可复用逻辑块 | **策略分派 + Template Method** |
| 操作符歧义 | CQN 结构化查询（无字符串歧义） | SOQL 结构化查询（无字符串歧义） | GlideRecord API（无字符串歧义） | **按长度降序检测** |
| 重复硬编码映射 | CDS 注解驱动（模型即配置） | Selector 字段列表集中 | Sys Properties JSON 配置 | **元数据推导** |

### 1.3 统一的 DRY 消除模式

我们从三个头部产品的实践中提炼出以下核心模式，将在 Phase 2 中应用：

**模式 A — Template Method（模板方法）**：适用于"骨架相同，细节不同"的场景。定义算法的骨架，将可变步骤延迟到子类或参数化。

**模式 B — 公共逻辑提取**：适用于"两个方法中的代码块完全一致"的场景。将重复代码段提取为私有/模块级函数。

**模式 C — 策略分派（Dispatch Table）**：适用于"多组方法共享相同的类型分派逻辑"的场景。将分派逻辑集中到一个方法中，通过映射表路由。

**模式 D — 元数据推导（Metadata Resolution）**：适用于"硬编码映射字典重复"的场景。从 YAML 元模型中自动推导表名/字段名/图标等映射。

---

## 2. FR-P1-001: audit_interceptor

### 2.1 源码位置

| 文件 | 路径 | 行数 |
|---|---|---|
| audit_interceptor.py | `meta/core/interceptors/audit_interceptor.py` | 371 行 |
| association_engine.py | `meta/core/association_engine.py` | 1347 行（跨文件重复） |

### 2.2 现状分析

#### 2.2.1 重复 1：`_log_associate` vs `_log_dissociate`（核心重复）

```python
# L232-275: _log_associate（43行）
def _log_associate(self, context, config):
    params = context.params
    tgt_type = params.get('tgt_type')
    tgt_id = params.get('tgt_id')
    association_name = params.get('association_name', 'members')  

    src_display = self._get_object_display(context.object_type, context.object_id, context.data_source)
    tgt_display = self._get_object_display(tgt_type, tgt_id, context.data_source)

    type_name_map = {
        'user': '用户', 'user_group': '用户组',
        'role': '角色', 'permission': '权限',
    }
    src_type_name = type_name_map.get(context.object_type, context.object_type)
    tgt_type_name = type_name_map.get(tgt_type, tgt_type)

    association_name_map = {
        'members': '成员', 'roles': '角色', 'permissions': '权限',
    }
    association_display = association_name_map.get(association_name, association_name)

    self._structured_logger.log_business(
        action='ASSOCIATE',          # ← 唯一差异点 1
        object_type=context.object_type,
        object_id=context.object_id,
        user_id=context.user_id,
        user_name=context.user_name,
        field_name=association_display,
        old_data=None,               # ← 唯一差异点 2
        new_data={'target_type': tgt_type_name, 'target_display': tgt_display, 'target_id': tgt_id},  # ← 差异点 3
        ip_address=getattr(context, 'ip_address', None),
        trace_id=context.trace_id,
        parent_object_type=tgt_type,
        parent_object_id=tgt_id,
        level='INFO'
    )
    logger.info(f"Logged ASSOCIATE on ...")  # ← 唯一差异点 4

# L276-318: _log_dissociate（43行）
# 差异点仅为：action='DISSOCIATE', old_data/data 交换, 日志文字
```

**精确重复统计**：

| 行范围 | 内容 | 重复率 |
|---|---|---|
| L234-260 (27行) | 参数提取 + type/association 映射 | **100%** |
| L262-272 (11行) | `log_business()` 调用（除 3 个参数差异） | **73%** |
| L274-275 (2行) | logger.info | **0%**（文字不同） |

**总计**: 43 行中约 38 行完全或高度重复，重复率 **~88%**。

#### 2.2.2 重复 2：硬编码映射字典（同一方法内多次出现）

`type_name_map` (L242-247) 和 `association_name_map` (L251-254) 在两个方法中各定义一次，完全相同。

#### 2.2.3 重复 3：跨文件 `_get_object_display` ≈ `_get_target_display`

```python
# audit_interceptor.py L320-350
def _get_object_display(self, object_type, object_id, data_source):
    display_field_map = {
        'user': 'display_name', 'user_group': 'name',
        'role': 'name', 'permission': 'name',
    }
    table_map = {
        'user': 'users', 'user_group': 'user_groups',
        'role': 'roles', 'permission': 'permissions',
    }
    # ... 查询逻辑 ...

# association_engine.py L1322-1347
def _get_target_display(self, tgt_type, tgt_id, data_source):
    display_field_map = {
        'user': 'display_name', 'user_group': 'name',  # ← 完全相同
        'role': 'name', 'permission': 'name',           # ← 完全相同
    }
    table_map = {
        'user': 'users', 'user_group': 'user_groups',    # ← 完全相同
        'role': 'roles', 'permission': 'permissions',     # ← 完全相同
    }
    # ... 查询逻辑 ...
```

两个方法的功能语义完全相同：根据 `object_type` 和 `object_id` 获取对象的业务显示名称。重复行数：约 25 行。

#### 2.2.4 额外发现：association_engine 中循环依赖的风险

[association_engine.py:L24-61](file:///d:/filework/excel-to-diagram/meta/core/association_engine.py#L24-L61) `_write_audit_log()` 方法内部直接实例化 `AuditInterceptor` 并调用其实例方法，构成了从 association_engine → audit_interceptor 的隐式依赖。虽然当前未造成循环导入（audit_interceptor 不 import association_engine），但这种耦合是不健康的，应通过服务注册或注入方式解耦。

### 2.3 头部产品方案对比

#### SAP CAP — `@Before/@After` handler 模式

SAP CAP 通过 phase registration (`srv.before()/srv.after()`) 注册可复用的 handler。对于关联审计，CAP 的做法是在 AFTER 阶段注册单一 handler，通过 `req.event` 参数区分操作类型：

```javascript
// CAP 模式：单一 handler 处理 ASSOCIATE/DISSOCIATE
this.after(['ASSOCIATE', 'DISSOCIATE'], '*', (data, req) => {
    const action = req.event;
    const logEntry = buildLogEntry(action, req.target, data);
    auditLog.write(logEntry);
});
```

**启示**：将 `_log_associate` 和 `_log_dissociate` 合并为参数化的 `_log_association_event(action, context, config)`。

#### ServiceNow — Script Include 集中化

ServiceNow 将 `typeNameMap` 和 `tableMap` 等跨表常规定义在 `Script Include` 的全局配置中，所有 Business Rule 引用同一份。

**启示**：提取 `type_name_map` 和 `association_name_map` 为模块级常量或从 YAML 元模型推导。

#### Salesforce — Selector 层集中字段映射

Salesforce Enterprise Pattern 中，所有字段→表映射集中在 `Selector` 层，其他层不持有映射逻辑。

**启示**：`_get_object_display()`/`_get_target_display()` 的硬编码映射字典应提取为共享工具函数，或从 `registry` 元模型中动态推导。

### 2.4 细化方案

#### 2.4.1 方案 A：合并 `_log_associate` 和 `_log_dissociate`（模式 B — 公共逻辑提取）

```python
# 提取为模块级常量（从 YAML 元模型也可动态推导）
_TYPE_DISPLAY_MAP = {
    'user': '用户', 'user_group': '用户组',
    'role': '角色', 'permission': '权限',
}

_ASSOCIATION_DISPLAY_MAP = {
    'members': '成员', 'roles': '角色', 'permissions': '权限',
}

class AuditInterceptor(Interceptor):

    def _log_association_event(self, context, config, action):
        """
        统一的关联操作审计日志记录。

        消除 _log_associate / _log_dissociate 中 ~88% 的重复代码。
        参考 SAP CAP 的 event-based handler 模式。
        """
        params = context.params
        tgt_type = params.get('tgt_type')
        tgt_id = params.get('tgt_id')
        association_name = params.get('association_name', 'members')

        src_display = self._get_object_display(
            context.object_type, context.object_id, context.data_source)
        tgt_display = self._get_object_display(
            tgt_type, tgt_id, context.data_source)

        src_type_name = _TYPE_DISPLAY_MAP.get(context.object_type, context.object_type)
        tgt_type_name = _TYPE_DISPLAY_MAP.get(tgt_type, tgt_type)
        association_display = _ASSOCIATION_DISPLAY_MAP.get(association_name, association_name)

        if action == 'ASSOCIATE':
            old_data_val = None
            new_data_val = {
                'target_type': tgt_type_name,
                'target_display': tgt_display,
                'target_id': tgt_id,
            }
        else:  # DISSOCIATE
            old_data_val = {
                'target_type': tgt_type_name,
                'target_display': tgt_display,
                'target_id': tgt_id,
            }
            new_data_val = None

        self._structured_logger.log_business(
            action=action,
            object_type=context.object_type,
            object_id=context.object_id,
            user_id=context.user_id,
            user_name=context.user_name,
            field_name=association_display,
            old_data=old_data_val,
            new_data=new_data_val,
            ip_address=getattr(context, 'ip_address', None),
            trace_id=context.trace_id,
            parent_object_type=tgt_type,
            parent_object_id=tgt_id,
            level='INFO'
        )
        logger.info(
            f"[AuditInterceptor] Logged {action} on "
            f"{context.object_type}/{context.object_id} -> {tgt_type}:{tgt_id}"
        )

    # after_action 中的调用点改为：
    # self._log_association_event(context, action_config, context.action.upper())
```

**收益**：
- 消除 ~38 行重复代码（减少 44% 方法长度）
- `type_name_map`/`association_name_map` 提升为模块常量，全局唯一定义
- 新增关联类型（如 `transfer`/`copy`）时只需修改一处

#### 2.4.2 方案 B：提取共享的 `get_object_display()` 工具函数

新建或使用已有的工具模块，消除跨文件硬编码映射重复：

```python
# meta/core/model_utils.py（新建或在现有模块中添加）

_OBJECT_DISPLAY_FIELD_MAP = {
    'user': 'display_name',
    'user_group': 'name',
    'role': 'name',
    'permission': 'name',
}

_OBJECT_TABLE_MAP = {
    'user': 'users',
    'user_group': 'user_groups',
    'role': 'roles',
    'permission': 'permissions',
}


def get_object_display(object_type: str, object_id: int, data_source) -> str:
    """获取业务对象的显示名称（从 YAML 元数据推导显示字段和表名）"""
    try:
        # 优先从 meta_object 的 display_field 属性推导
        from meta.core.models import registry
        meta_obj = registry.get(object_type)
        if meta_obj:
            display_field = meta_obj.get_display_field()  # 需新增方法
            table_name = meta_obj.table_name
            if display_field and table_name:
                cursor = data_source.execute(
                    f"SELECT {display_field} FROM {table_name} WHERE id = ?",
                    [object_id]
                )
                row = cursor.fetchone()
                if row:
                    return row[0]
        
        # 降级：使用硬编码映射
        display_field = _OBJECT_DISPLAY_FIELD_MAP.get(object_type, 'name')
        table_name = _OBJECT_TABLE_MAP.get(object_type, object_type)
        cursor = data_source.execute(
            f"SELECT {display_field} FROM {table_name} WHERE id = ?",
            [object_id]
        )
        row = cursor.fetchone()
        if row:
            return row[0]
        return f"{object_type}:{object_id}"
    except Exception as e:
        logger.warning(f"Failed to get display for {object_type}/{object_id}: {e}")
        return f"{object_type}:{object_id}"
```

同时替换：
- [audit_interceptor.py:L320-350](file:///d:/filework/excel-to-diagram/meta/core/interceptors/audit_interceptor.py#L320-L350) `_get_object_display()` → 调用 `get_object_display()`
- [association_engine.py:L1322-1347](file:///d:/filework/excel-to-diagram/meta/core/association_engine.py#L1322-L1347) `_get_target_display()` → 调用 `get_object_display()`

**收益**：消除 ~50 行跨文件重复代码。

#### 2.4.3 方案 C：解耦 association_engine 中的审计日志写入

当前 [association_engine.py:L24-61](file:///d:/filework/excel-to-diagram/meta/core/association_engine.py#L24-L61) `_write_audit_log()` 直接实例化 `AuditInterceptor`，违反了依赖倒置原则。

**建议**（低优先级，Phase 3 或后续优化）：通过引入简单的 Service Locator 或事件发布机制解耦。

### 2.5 验收标准

- [ ] `_log_associate` 和 `_log_dissociate` 合并为 `_log_association_event(action, context, config)`
- [ ] `type_name_map` 和 `association_name_map` 提取为模块级常量
- [ ] `after_action()` 中两处调用点更新
- [ ] 所有现有审计日志测试通过
- [ ] `_get_object_display()` 提取为共享工具函数（可选，跨 FR-P1-004 联合）
- [ ] 任一文件的硬编码映射仅保留一份降级映射

### 2.6 风险评估

| 风险 | 级别 | 缓解措施 |
|---|---|---|
| `after_action()` 调用点更新遗漏 | 低 | 该方法仅 2 处调用（L103-105），检查范围明确 |
| 合并后的方法签名兼容性 | 低 | 新增内部方法，不改变公共 API |
| `get_object_display()` 提取后的导入循环 | 中 | 放在独立工具模块 `meta/core/model_utils.py`，避免循环 |

---

## 3. FR-P1-002: hierarchy_validation

### 3.1 源码位置

| 文件 | 路径 | 行数 |
|---|---|---|
| hierarchy_validation_interceptor.py | `meta/core/interceptors/hierarchy_validation_interceptor.py` | 103 行 |

### 3.2 现状分析

#### 3.2.1 重复的错误收集代码块（15行完全重复）

```python
# L53-L67: _validate_update 中的错误收集逻辑
if not result.valid:
    if 'violations' not in context.extra:
        context.extra['violations'] = []
    context.extra['violations'].append({
        'type': 'hierarchy_validation',
        'message': result.message,
        'error_code': result.error_code,
        'details': result.details,
    })
    context.result = type(context.result)(
        success=False,
        data=None,
        message=result.message,
        errors=[result.message],
    )

# L87-L101: _validate_delete 中的错误收集逻辑
# ↑ 完全相同的 15 行代码，逐字符一致
```

**精确重复统计**：15 行完全一致（L53-67 ≈ L87-101），重复率 **100%**。

#### 3.2.2 两个方法的差异分析

```python
# _validate_update (L41-69)
def _validate_update(self, context):
    try:
        from meta.services.hierarchy_validation_service import validate_update
        if context.old_data is None:   # ← 差异点 1: null check
            return
        result = validate_update(...)   # ← 差异点 2: 调用不同 service 方法
        # [相同的 15 行错误收集代码]    # ← 重复!
    except Exception as e:
        logger.debug(...)

# _validate_delete (L71-103)
def _validate_delete(self, context):
    force = context.params.get('force', False)  # ← 差异点 3: force check
    if force:
        return
    try:
        from meta.services.hierarchy_validation_service import validate_delete
        obj_id = context.object_id
        if obj_id is None:             # ← 差异点 4: null check (不同)
            return
        result = validate_delete(...)   # ← 差异点 5: 调用不同 service 方法
        # [相同的 15 行错误收集代码]    # ← 重复!
    except Exception as e:
        logger.debug(...)
```

**差异总结**：两个方法仅在前置检查和调用的 service 函数上不同，错误处理逻辑完全一致。

### 3.3 头部产品方案对比

#### Salesforce — `ValidationResult` 聚合模式

Salesforce 的 `ValidationEngine` 将错误收集集中到一个地方：

```java
public static void validate(Schema.SObjectType sObjectType, ...) {
    IObjectValidator validator = validators.get(sObjectType);
    ValidationResult result = validator.validate*(...);
    if (result != null && !result.isValid) {
        // 集中的错误收集 — 所有 validator 复用
        for (SObject so : newList) {
            for (String err : result.errors) {
                so.addError(err);
            }
        }
    }
}
```

**启示**：提取 `_handle_validation_result(context, result)` 公共方法。

#### SAP CAP — `req.error()` 统一错误处理

CAP 对所有 handler 的错误处理统一使用 `req.error()`：

```javascript
this.before('UPDATE', '*', (req) => {
    const result = validateSomething(req.data);
    if (!result.valid) {
        req.error(400, result.message);  // 统一的错误报告
    }
});
```

### 3.4 细化方案

#### 唯一方案：提取 `_handle_validation_result()`（模式 B）

```python
def _handle_validation_result(self, context, result):
    """统一的层级校验结果处理。

    消除 _validate_update/_validate_delete 中 15 行完全重复的错误收集代码。
    参考 Salesforce ValidationEngine 的集中错误收集模式。
    """
    if result.valid:
        return

    if 'violations' not in context.extra:
        context.extra['violations'] = []
    context.extra['violations'].append({
        'type': 'hierarchy_validation',
        'message': result.message,
        'error_code': result.error_code,
        'details': result.details,
    })
    context.result = type(context.result)(
        success=False,
        data=None,
        message=result.message,
        errors=[result.message],
    )


def _validate_update(self, context):
    try:
        from meta.services.hierarchy_validation_service import validate_update
        if context.old_data is None:
            return
        result = validate_update(
            context.object_type,
            context.old_data,
            context.params,
            context.data_source,
        )
        self._handle_validation_result(context, result)
    except Exception as e:
        logger.debug(f"[HierarchyValidation] update validation skipped: {e}")


def _validate_delete(self, context):
    force = context.params.get('force', False)
    if force:
        return
    try:
        from meta.services.hierarchy_validation_service import validate_delete
        obj_id = context.object_id
        if obj_id is None:
            return
        result = validate_delete(
            context.object_type,
            obj_id,
            context.data_source,
        )
        self._handle_validation_result(context, result)
    except Exception as e:
        logger.debug(f"[HierarchyValidation] delete validation skipped: {e}")
```

**收益**：
- 消除 15 行重复代码
- `_validate_update` 从 28 行缩减为 18 行（-36%）
- `_validate_delete` 从 32 行缩减为 20 行（-38%）
- 未来新增校验方法时无需复制错误收集代码

### 3.5 验收标准

- [ ] `_handle_validation_result(context, result)` 正确提取
- [ ] `_validate_update` 和 `_validate_delete` 调用新的公共方法
- [ ] 所有现有层级校验测试通过
- [ ] `force` 参数行为不变

### 3.6 风险评估

| 风险 | 级别 | 缓解措施 |
|---|---|---|
| `type(context.result)` 依赖 `context.result` 可能为 None | 低 | 检查调用路径：两个方法调用前 `context.result` 已由框架初始化为默认 `ActionResult` |
| 不同校验需要不同 violation type | 低 | 可以将 `'type'` 作为参数传入 `_handle_validation_result()` |

---

## 4. FR-P1-003: enum_protection

### 4.1 源码位置

| 文件 | 路径 | 行数 |
|---|---|---|
| enum_protection_interceptor.py | `meta/core/interceptors/enum_protection_interceptor.py` | 274 行 |

### 4.2 现状分析

#### 4.2.1 四个校验方法的重复模式分析

```python
# ── enum_type 组（2个方法） ──

# _validate_enum_type_update (L119-135)
def _validate_enum_type_update(self, context):
    old_data = context.old_data                    # 共同步骤 1
    if not old_data: return                         # 共同步骤 2
    if old_data.get('category') == 'system':        # 共同步骤 3（category check）
        context.result = ActionResult(...)           # 共同步骤 4（ActionResult 构造）
        logger.warning(f"...修改...")                # 差异：日志文字

# _validate_enum_type_delete (L137-169)
def _validate_enum_type_delete(self, context):
    old_data = context.old_data                    # 共同步骤 1 ✅
    if not old_data: return                         # 共同步骤 2 ✅
    enum_type_id = ...                              # 额外步骤：获取 id
    if old_data.get('category') == 'system':        # 共同步骤 3 ✅（category check）
        context.result = ActionResult(...)           # 共同步骤 4 ✅
        logger.warning(f"...删除...")               # 差异：日志文字
        return                                      # 额外步骤：提前返回
    has_values = self._has_enum_values(...)         # 额外步骤：检查枚举值
    if has_values:
        context.result = ActionResult(...)           # 额外 ActionResult

# ── enum_value 组（2个方法） ──

# _validate_enum_value_update (L171-198)
def _validate_enum_value_update(self, context):
    old_data = context.old_data                    # 共同步骤 1
    if not old_data: return                         # 共同步骤 2
    enum_type_id = ...                              # 共同步骤 3（获取 enum_type_id）
    if not enum_type_id: return                     # 共同步骤 4
    try:
        enum_type = self._get_enum_type(...)        # 共同步骤 5（查询 enum_type）
        if not enum_type: return                    # 共同步骤 6
        if enum_type.get('mutability') == 'locked':  # 共同步骤 7（locked check）
            context.result = ActionResult(...)       # 共同步骤 8（ActionResult）
            logger.warning(f"...修改...")            # 差异：日志文字
    except Exception as e:
        logger.debug(...)

# _validate_enum_value_delete (L200-239)
def _validate_enum_value_delete(self, context):
    old_data = context.old_data                    # 共同步骤 1 ✅
    if not old_data: return                         # 共同步骤 2 ✅
    enum_type_id = old_data.get('enum_type_id')     # 共同步骤 3 ✅
    if not enum_type_id: return                     # 共同步骤 4 ✅
    if old_data.get('is_system') == 1:              # 额外步骤：is_system check
        context.result = ActionResult(...)           # 额外 ActionResult
        logger.warning(...)
        return
    try:
        enum_type = self._get_enum_type(...)        # 共同步骤 5 ✅
        if not enum_type: return                    # 共同步骤 6 ✅
        if enum_type.get('mutability') == 'locked':  # 共同步骤 7 ✅
            context.result = ActionResult(...)       # 共同步骤 8 ✅
            logger.warning(f"...删除...")            # 差异：日志文字
    except Exception as e:
        logger.debug(...)
```

**重复模式映射**：

| 重复元素 | `_validate_enum_type_update` | `_validate_enum_type_delete` | `_validate_enum_value_update` | `_validate_enum_value_delete` |
|---|---|---|---|---|
| old_data null check | ✅ | ✅ | ✅ | ✅ |
| category=='system' check | ✅ | ✅ | — | — |
| mutability=='locked' check | — | — | ✅ | ✅ |
| locked 后的 ActionResult | — | — | ✅ (L186-195) | ✅ (L228-238) |
| system 后的 ActionResult | ✅ (L125-134) | ✅ (L145-154) | — | — |

**重复度统计**：

- **enum_type 组**：2 个方法共享 `category=='system'` 检查的 ActionResult 构造模式（约 10 行重复）
- **enum_value 组**：2 个方法共享 `mutability=='locked'` 检查的 ActionResult 构造模式（约 10 行重复）+ `_get_enum_type()` 调用链（约 10 行重复）
- **总计**: 约 30 行重复代码

#### 4.2.2 BUG：`_get_enum_type()` 双重查询

```python
# L242-261: 存在功能性 bug
def _get_enum_type(self, context, enum_type_id):
    try:
        cursor = context.data_source.execute(       # ← 第 1 次查询
            "SELECT * FROM enum_types WHERE id = ?", [enum_type_id]
        )
        row = cursor.fetchone()
        if not row:
            return None

        cursor = context.data_source.execute(       # ← 第 2 次查询（完全相同！）
            "SELECT * FROM enum_types WHERE id = ?", [enum_type_id]
        )
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))                  # ← row 来自第 1 次查询，cols 来自第 2 次！
```

**问题**：
1. 执行了两次完全相同的 SQL 查询（L245 和 L253），浪费一次 IO
2. `row` 来自第 1 次 `fetchone()`，`cols` 来自第 2 次 cursor——这两个数据来自不同查询结果，虽然 SQL 相同，但违反了逻辑正确性
3. 并发场景下，如果两次查询之间有写操作插入/删除了记录，row 和 cols 可能不匹配（概率极低但理论上存在）

**修复**：合并为一次查询，直接从第一次 cursor 获取列名：

```python
def _get_enum_type(self, context, enum_type_id):
    try:
        cursor = context.data_source.execute(
            "SELECT * FROM enum_types WHERE id = ?", [enum_type_id]
        )
        row = cursor.fetchone()
        if not row:
            return None
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))
    except Exception as e:
        logger.debug(f"[EnumProtection] Failed to get enum_type {enum_type_id}: {e}")
        return None
```

### 4.3 头部产品方案对比

#### SAP CAP — `@Before` 阶段统一校验

SAP CAP 使用多级钩子链处理复杂的校验规则：

```javascript
// CAP 模式：层级化校验逻辑
this.before('UPDATE', 'EnumTypes', (req) => {
    if (req.data.category === 'system') { req.error(403, 'Immutable'); }
});
this.before('DELETE', 'EnumValues', (req) => {
    const enumType = await SELECT.one.from('EnumTypes', req.data.enum_type_id);
    if (enumType.mutability === 'locked') { req.error(403, 'Locked'); }
});
```

**启示**：将 `category=='system'` 检查和 `mutability=='locked'` 检查分别提取为独立的校验器子方法，由统一的分派逻辑组合。

#### Salesforce — `IValidationRule` 组合模式

Salesforce 每个校验规则是独立的 `IValidationRule` 实现，通过 `ValidationEngine` 组合：

```java
// 独立的可复用的规则
class CategoryIsSystemRule implements IValidationRule { ... }
class MutabilityIsLockedRule implements IValidationRule { ... }
class IsSystemValueRule implements IValidationRule { ... }

// 针对不同操作，组合不同规则集合
public ValidationResult validateUpdate(...) {
    return ValidationResult.and(
        new CategoryIsSystemRule().validate(records),
        new MutabilityIsLockedRule().validate(records),
    );
}
```

### 4.4 细化方案

#### 4.4.1 方案 A：提取公共校验方法（推荐，模式 B）

```python
def _validate_enum_type_immutable(self, context, action_name='修改'):
    """检查系统枚举不可变"""
    old_data = context.old_data
    if not old_data:
        return False
    if old_data.get('category') == 'system':
        context.result = ActionResult(
            success=False,
            data=None,
            message=f"系统枚举不可{action_name}",
            errors=["SYSTEM_ENUM_IMMUTABLE"],
        )
        logger.warning(
            f"[EnumProtection] Blocked {action_name} enum_type: "
            f"id={context.object_id} is system enum"
        )
        return True
    return False


def _validate_enum_type_update(self, context):
    self._validate_enum_type_immutable(context, '修改')


def _validate_enum_type_delete(self, context):
    if self._validate_enum_type_immutable(context, '删除'):
        return
    old_data = context.old_data
    if not old_data:
        return
    enum_type_id = context.object_id or old_data.get('id')
    has_values = self._has_enum_values(context, enum_type_id)
    if has_values:
        context.result = ActionResult(
            success=False, data=None,
            message="该枚举类型下有枚举值，无法删除",
            errors=["HAS_VALUES"],
        )
        logger.warning(
            f"[EnumProtection] Blocked delete enum_type: "
            f"id={enum_type_id} has values"
        )
```

#### 4.4.2 方案 B：枚举值校验的统一 locked 检查（模式 B）

```python
def _check_enum_locked(self, context, enum_type_id, action_name='修改'):
    """检查枚举类型是否已锁定"""
    try:
        enum_type = self._get_enum_type(context, enum_type_id)
        if not enum_type:
            return False
        if enum_type.get('mutability') == 'locked':
            context.result = ActionResult(
                success=False, data=None,
                message=f"该枚举类型已锁定，不可{action_name}值",
                errors=["ENUM_LOCKED"],
            )
            logger.warning(
                f"[EnumProtection] Blocked {action_name} enum_value: "
                f"enum_type={enum_type_id} is locked"
            )
            return True
    except Exception as e:
        logger.debug(f"[EnumProtection] Enum value validation skipped: {e}")
    return False


def _validate_enum_value_update(self, context):
    old_data = context.old_data
    if not old_data:
        return
    enum_type_id = context.params.get('enum_type_id') or old_data.get('enum_type_id')
    if not enum_type_id:
        return
    self._check_enum_locked(context, enum_type_id, '修改')


def _validate_enum_value_delete(self, context):
    old_data = context.old_data
    if not old_data:
        return
    enum_type_id = old_data.get('enum_type_id')
    if not enum_type_id:
        return
    if old_data.get('is_system') == 1:
        context.result = ActionResult(
            success=False, data=None,
            message="系统预置值不可删除",
            errors=["SYSTEM_VALUE_IMMUTABLE"],
        )
        logger.warning(...)
        return
    self._check_enum_locked(context, enum_type_id, '删除')
```

#### 4.4.3 方案 C：修复 `_get_enum_type()` 双重查询 BUG（必须修复）

```python
def _get_enum_type(self, context, enum_type_id):
    try:
        cursor = context.data_source.execute(
            "SELECT * FROM enum_types WHERE id = ?", [enum_type_id]
        )
        row = cursor.fetchone()
        if not row:
            return None
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))
    except Exception as e:
        logger.debug(f"[EnumProtection] Failed to get enum_type {enum_type_id}: {e}")
        return None
```

**收益**：
- 消除约 20 行重复代码
- 修复功能性 BUG（双重查询）
- 每次枚举锁定检查减少 1 次数据库查询
- 新增枚举保护规则时只需调用公共方法

### 4.5 验收标准

- [ ] `_validate_enum_type_immutable(context, action_name)` 正确提取
- [ ] `_check_enum_locked(context, enum_type_id, action_name)` 正确提取
- [ ] `_get_enum_type()` 双重查询 BUG 修复
- [ ] 4 个 `_validate_enum_*` 方法正确重构
- [ ] 所有枚举保护校验逻辑行为不变
- [ ] 现有枚举保护测试通过

### 4.6 风险评估

| 风险 | 级别 | 缓解措施 |
|---|---|---|
| `action_name` 参数可能与其他调用参数混淆 | 低 | 仅 4 个方法调用，参数语义清晰 |
| `_get_enum_type()` 修复后的游标行为差异 | 极低 | 修复后逻辑与标准 `find_by_id()` 一致，且消除了原有潜在 bug |

---

## 5. FR-P1-004: association_engine

### 5.1 源码位置

| 文件 | 路径 | 行数 |
|---|---|---|
| association_engine.py | `meta/core/association_engine.py` | 1347 行 |
| query_service.py | `meta/services/query_service.py` | `add_table_alias_to_where` 在 2 处重复 |

### 5.2 现状分析

#### 5.2.1 重复 1：四组方法的类型分派模式重复（核心重复）

```python
# associate (L62-79)：18 行
def associate(self, context):
    params = context.params
    association_name = params.get('association_name', '')     # 1. 提取参数
    assoc_meta = self._resolve_assoc_meta(...)                  # 2. 解析元数据
    if assoc_meta is None:
        return self._fallback_associate(context)                # 3. 降级处理
    assoc_type = assoc_meta.get('type', 'many_to_many')        # 4. 获取类型
    if assoc_type == 'many_to_many':                            # 5. 类型分派
        return self._associate_m2m(context, assoc_meta)
    elif assoc_type == 'composition':
        return self._associate_composition(context, assoc_meta)
    elif assoc_type == 'reference':
        return self._associate_reference(context, assoc_meta)
    return ActionResult(...)

# assign (L119-136)：18 行 ← 与 associate 结构相同（86%）
# dissociate (L81-98)：18 行 ← 同上（83%）
# unassign (L138-155)：18 行 ← 同上（83%）
# query_associations (L100-117)：18 行 ← 分派略有不同（反相 m2m/reference/composition）
# count (L215-232)：18 行 ← 分派略有不同
# batch_query_associations (L234-255)：22 行 ← 更复杂的分派
```

**分派模式结构分析**：

```
associate/assign:          m2m → composition → reference      → unknown
dissociate/unassign:       m2m → reference    → composition   → unknown
query_associations:        m2m → reference    → composition   → empty
count:                     m2m → reference    → composition   → zero
batch_query_associations:  m2m → composition  → reverse_m2m   → empty
```

**重复度统计**：

| 方法对 | 行数 | 重复行 | 重复率 | 差异 |
|---|---|---|---|---|
| associate vs assign | 18/18 | 14 | 78% | fallback 名称、具体方法名 |
| dissociate vs unassign | 18/18 | 15 | 83% | fallback 名称、具体方法名 |
| associate vs dissociate | 18/18 | 13 | 72% | 分派目标方法名、composition 处理 |
| query_associations vs count | 18/18 | 13 | 72% | 分派顺序、默认值 |

**总计**：约 90 行高度重复的分派代码。

#### 5.2.2 重复 2：`add_table_alias_to_where` 在 2 处重复定义

```python
# query_service.py L809-819: _execute_computed_field_query() 内
def add_table_alias_to_where(sql: str, alias: str) -> str:
    pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(=|<>|!=|>|<|>=|<=|LIKE|ILIKE|IN|NOT IN|IS|IS NOT)\s*'
    def replace_column(match):
        col = match.group(1)
        op = match.group(2)
        if col.upper() in ('WHERE', 'AND', 'OR', 'NOT', 'NULL', 'TRUE', 'FALSE'):
            return match.group(0)
        if '.' in col:
            return match.group(0)
        return f"{alias}.{col} {op} "
    return re.sub(pattern, replace_column, sql, flags=re.IGNORECASE)

# query_service.py L988-999: _execute_virtual_field_query() 内
def add_table_alias_to_where(sql: str, alias: str) -> str:     # ← 完全相同！
    import re                                                   # ← 完全相同！
    pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(=|<>|!=|>|<|>=|<=|LIKE|ILIKE|IN|NOT IN|IS|IS NOT)\s*'
    def replace_column(match):
        col = match.group(1)
        op = match.group(2)
        if col.upper() in ('WHERE', 'AND', 'OR', 'NOT', 'NULL', 'TRUE', 'FALSE'):
            return match.group(0)
        if '.' in col:
            return match.group(0)
        return f"{alias}.{col} {op} "
    return re.sub(pattern, replace_column, sql, flags=re.IGNORECASE)
```

**完全重复的 11 行代码（L809-819 ≈ L988-999，唯一差异是 L989 有重复的 `import re`）。**

#### 5.2.3 重复 3：`_associate_m2m` 和 `_assign_m2m` 的核心逻辑重复

```python
# _associate_m2m (L297-349): 53行
def _associate_m2m(self, context, assoc_meta):
    # 1. 参数提取
    src_id = params.get('src_id')
    tgt_type = params.get('tgt_type')
    tgt_id = params.get('tgt_id')
    metadata = params.get('metadata', {})

    # 2. 存在性检查
    existence_error = self._validate_source_target_existence(...)
    if existence_error: return existence_error

    # 3. 基数约束检查
    cardinality_error = self._check_cardinality_constraint(...)
    if cardinality_error: return cardinality_error

    # 4. 中间表字段解析
    through = assoc_meta.get('through')
    source_key = assoc_meta.get('source_key')
    target_key = assoc_meta.get('target_key')
    if not through or not source_key or not target_key:
        return self._fallback_associate(context)

    # 5. 已存在检查
    existing = self._check_m2m_exists(...)
    if existing: return ActionResult(...)

    # 6. 构建 SQL（columns + metadata_fields）
    cols = [source_key, target_key]
    vals = [src_id, tgt_id]
    meta_fields = assoc_meta.get('metadata_fields', [])
    ... meta_fields 处理 ...

    # 7. INSERT 执行
    placeholders = ','.join(['?'] * len(cols))
    col_names = ','.join(cols)
    sql = f"INSERT OR REPLACE INTO {through} ({col_names}) VALUES ({placeholders})"

    # _assign_m2m (L351-403): 53行
    # 步骤 1-6 完全相同
    # 差异点：
    #   - sql = f"INSERT INTO ..." vs "INSERT OR REPLACE INTO ..."  （差异 L338 vs L393）
    #   - 额外: self._write_audit_log() 调用                      （额外 L397）
    #   - 额外: UNIQUE constraint failed 处理                     （额外 L400-401）
```

**重复度**：2 个方法各 53 行，约 45 行重复（85%）。

#### 5.2.4 重复 4：`_associate_reference` 和 `_assign_reference` 类似

```python
# _associate_reference (L998-1033)：36行
# _assign_reference (L622-652)：31行
# 差异：_assign_reference 无 get_target_display，无 audit_log
```

#### 5.2.5 重复 5：跨文件 `_get_target_display` ≈ `_get_object_display`

见 [2.2.3](#223-重复-3跨文件-_get_object_display--_get_target_display) 分析，由 FR-P1-001 统一处理。

### 5.3 头部产品方案对比

#### SAP CAP — `srv.send()` 委托模式

CAP 通过 `srv.send()` 处理不同 association 类型，将分派委托给框架：

```javascript
// CAP 模式：框架自动处理 association 分派
this.on('ASSOCIATE', 'Books', async (req) => {
    await srv.send({ query: req.query, target: 'my.bookshop.Books' });
});
```

#### Salesforce — `TriggerHandler.triggerHandler()` 统一分派

Salesforce Trigger Framework 的 `triggerHandler()` 方法通过 `switch on Trigger.operationType` 统一处理分派，消除每个 Trigger 中的 `if-else` 重复。

**启示**：将四组方法的分派逻辑统一到 `_dispatch_association(context, operation_type)`。

### 5.4 细化方案

#### 5.4.1 方案 A：提取分派逻辑（模式 C — 策略分派表）

```python
# 分派映射表 — 定义每种操作对应的类型→方法映射
_DISPATCH_TABLE = {
    'associate': {
        'many_to_many': '_associate_m2m',
        'composition': '_associate_composition',
        'reference': '_associate_reference',
    },
    'dissociate': {
        'many_to_many': '_dissociate_m2m',
        'reference': '_dissociate_reference',
        'composition': None,  # composition 不支持 dissociate
    },
    'assign': {
        'many_to_many': '_assign_m2m',
        'composition': '_assign_composition',
        'reference': '_assign_reference',
    },
    'unassign': {
        'many_to_many': '_unassign_m2m',
        'reference': '_unassign_reference',
        'composition': None,
    },
    'query': {
        'many_to_many': '_query_m2m',
        'reference': '_query_reference',
        'composition': '_query_composition',
        'one_to_many': '_query_composition',
    },
    'count': {
        'many_to_many': '_count_m2m',
        'reference': '_count_reference',
        'composition': '_count_composition',
        'one_to_many': '_count_composition',
    },
}

# composition 不支持取消关联的特殊消息
_COMPOSITION_UNSUPPORTED_MSG = {
    'dissociate': "Composition关联不支持取消关联，请使用删除子对象",
    'unassign': "Composition关联不支持取消关联",
}


class AssociationEngine:

    def _dispatch(self, context, operation):
        """
        统一的分派方法 — 消除 associate/assign/dissociate/unassign/query/count
        中 ~90 行高度重复的分派代码。

        参考 SAP CAP 的 srv.send() 委托模式和 Salesforce TriggerHandler 统一分派。
        """
        params = context.params
        association_name = params.get('association_name', '')
        assoc_meta = self._resolve_assoc_meta(context.object_type, association_name)

        if assoc_meta is None:
            # 降级处理
            fallback_map = {
                'associate': self._fallback_associate,
                'dissociate': self._fallback_dissociate,
                'assign': self._fallback_associate,
                'unassign': self._fallback_dissociate,
                'query': lambda ctx: self._fallback_query_associations(ctx, association_name),
                'count': lambda ctx: ActionResult(success=True, data={'count': 0}),
            }
            fallback = fallback_map.get(operation)
            if fallback:
                return fallback(context)
            return ActionResult(success=True, data={'count': 0})

        assoc_type = assoc_meta.get('type', 'many_to_many')

        dispatch_map = _DISPATCH_TABLE.get(operation, {})
        method_name = dispatch_map.get(assoc_type)

        if method_name is None:
            # composition 在 dissociate/unassign 时返回不支持消息
            if assoc_type == 'composition' and operation in _COMPOSITION_UNSUPPORTED_MSG:
                return ActionResult(
                    success=False,
                    message=_COMPOSITION_UNSUPPORTED_MSG[operation]
                )
            return ActionResult(
                success=False,
                message=f"Unknown association type: {assoc_type}"
            )

        method = getattr(self, method_name)
        return method(context, assoc_meta)

    # 简化后的公开方法（各只有 2 行）
    def associate(self, context):
        return self._dispatch(context, 'associate')

    def assign(self, context):
        return self._dispatch(context, 'assign')

    def dissociate(self, context):
        return self._dispatch(context, 'dissociate')

    def unassign(self, context):
        return self._dispatch(context, 'unassign')

    def query_associations(self, context):
        return self._dispatch(context, 'query')

    def count(self, context):
        return self._dispatch(context, 'count')
```

**收益**：
- 消除 ~90 行重复的分派代码
- 新增关联类型时只需修改 `_DISPATCH_TABLE`
- 统一的降级处理和 composition 不支持消息管理

#### 5.4.2 方案 B：提取 `add_table_alias_to_where` 为模块级函数

```python
# meta/core/sql_utils.py（新建或附加到现有工具模块）

import re

# 保留关键字列表
_SQL_RESERVED_WORDS = frozenset({
    'WHERE', 'AND', 'OR', 'NOT', 'NULL', 'TRUE', 'FALSE',
    'SELECT', 'FROM', 'JOIN', 'INNER', 'LEFT', 'RIGHT', 'ON',
    'ORDER', 'BY', 'GROUP', 'HAVING', 'LIMIT', 'OFFSET',
    'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER',
    'IS', 'IN', 'LIKE', 'ILIKE', 'BETWEEN', 'EXISTS', 'AS',
    'ASC', 'DESC', 'DISTINCT', 'ALL', 'UNION', 'CASE', 'WHEN',
    'THEN', 'ELSE', 'END', 'SET', 'VALUES', 'INTO',
})

_COLUMN_ALIAS_PATTERN = re.compile(
    r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*'
    r'(=|<>|!=|>|<|>=|<=|LIKE|ILIKE|IN|NOT IN|IS|IS NOT)\s*',
    re.IGNORECASE,
)


def add_table_alias_to_where(sql: str, alias: str) -> str:
    """为 WHERE 子句中的裸列名添加表别名前缀。

    用于 computed_field 和 virtual_field 排序查询中，
    消除 _execute_computed_field_query 和 _execute_virtual_field_query
    中的重复定义。
    """
    def replace_column(match):
        col = match.group(1)
        op = match.group(2)
        if col.upper() in _SQL_RESERVED_WORDS:
            return match.group(0)
        if '.' in col:
            return match.group(0)
        return f"{alias}.{col} {op} "

    return _COLUMN_ALIAS_PATTERN.sub(replace_column, sql)
```

然后替换：
- [query_service.py:L809](file:///d:/filework/excel-to-diagram/meta/services/query_service.py#L809-L819) → `from meta.core.sql_utils import add_table_alias_to_where`
- [query_service.py:L988](file:///d:/filework/excel-to-diagram/meta/services/query_service.py#L988-L999) → 同上

**收益**：消除 22 行重复定义代码，SQL 保留字列表集中维护。

#### 5.4.3 方案 C（可选，低优先级）：合并 `_associate_m2m` / `_assign_m2m` 核心逻辑

这两个方法共享 ~85% 的逻辑，可以提取 `_build_and_execute_m2m_insert()` 公共方法。但考虑到两者的差异（`INSERT OR REPLACE` vs `INSERT`、是否写审计日志、是否处理 UNIQUE 冲突），合并的价值相对有限。**建议 Phase 2 先行跳过，Phase 3 评估。**

### 5.5 验收标准

- [ ] `_dispatch(context, operation)` 统一分派方法实现
- [ ] `associate/assign/dissociate/unassign/query_associations/count` 简化为 2 行委托
- [ ] 所有现有关联操作测试通过
- [ ] `add_table_alias_to_where` 提取为模块级函数
- [ ] 两处调用点替换为导入引用
- [ ] `_get_target_display()` → `get_object_display()` 替换（联合 FR-P1-001）
- [ ] composition 不支持 dissociate/unassign 的错误消息不变

### 5.6 风险评估

| 风险 | 级别 | 缓解措施 |
|---|---|---|
| `_dispatch` 分派表遗漏已有类型 | 中 | 使用分派初始化时验证表完整性 |
| `batch_associate` 等批量方法不受影响 | 低 | 它们调用的是 `self.assign()`/`self.unassign()`，间接走 `_dispatch` |
| `getattr(self, method_name)` 安全性 | 极低 | 方法名来自 `_DISPATCH_TABLE` 字符串常量，不来自外部输入 |
| `add_table_alias_to_where` 提取后行为差异 | 低 | 提取时不改变任何逻辑，仅改变定义位置 |

---

## 6. FR-P1-005: SQL 操作符检测歧义修复

### 6.1 源码位置

| 文件 | 路径 | 关键行 |
|---|---|---|
| sql_adapters.py | `meta/core/sql_adapters.py` | L226-282 (`_build_conditions`) |
| persistence_interceptor.py | `meta/core/interceptors/persistence_interceptor.py` | L390-404 (`>=`/`<=` 过滤器生成) |

### 6.2 现状分析

#### 6.2.1 现有操作符检测逻辑

```python
# sql_adapters.py L248-263
if ' >=' in key:                                        # L248: >= 先于 > 检测 ✓
    field = key.split(' >=')[0]
    conditions.append(f"{field} >= {self._placeholder()}")
    params.append(value)
elif ' <=' in key:                                       # L252: <= 先于 < 检测 ✓
    field = key.split(' <=')[0]
    conditions.append(f"{field} <= {self._placeholder()}")
    params.append(value)
elif ' >' in key and not key.endswith('>'):              # L256: BUG — 误伤合法 >
    field = key.split(' >')[0]
    conditions.append(f"{field} > {self._placeholder()}")
    params.append(value)
elif ' <' in key and not key.endswith('<'):              # L260: BUG — 误伤合法 <
    field = key.split(' <')[0]
    conditions.append(f"{field} < {self._placeholder()}")
    params.append(value)
elif 'LIKE' in key.upper():                              # L264: LIKE 检测
    ...
elif 'IN' in key.upper():                                # L268: IN 检测
    ...
else:                                                    # L277: 默认精确匹配
    conditions.append(f"{key} = {self._placeholder()}")
    params.append(value)
```

#### 6.2.2 BUG 详细分析

```
输入: key = "age >"
期望: conditions = ["age > ?"]
实际: 进入 L277 else 分支 → conditions = ["age > = ?"]  ← 错误！
```

**根因**：`not key.endswith('>')` 旨在排除 `key = "age >="`（避免 `>` 误匹配 `>=`），但它也排除了 `key = "age >"`。

**为什么 `elif` 链已不足以保护**：
1. L248 `' >=' in key` 先检测 `>=`，所以 `key = "age >="` 永远不会走到 L256
2. 但 `' >' in 'age >='` 为 `True`，如果移除了 `not key.endswith('>')` 守卫，且第一个 `if` 条件为 False（比如 key = `"age >="` 不在分支中），才会出错
3. 由于 `if-elif` 链保证了 `>=` 先于 `>`，所以 `not key.endswith('>')` 是冗余且有害的

#### 6.2.3 实际调用模式验证

通过追踪代码发现，`"field >="` 格式的过滤器键由 [persistence_interceptor.py:L390-L404](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L390-L404) 生成：

```python
# persistence_interceptor.py — _do_list() 中
# 仅生成 >= 和 <= 格式的过滤键，不生成 > 和 <
elif key.endswith('_start'):
    filters[f"{field.db_column} >="] = value         # L390
elif key.endswith('_end'):
    filters[f"{field.db_column} <="] = value         # L402
```

**结论**：当前代码路径中 `>` 和 `<` 过滤器永远不会被生成，但 `_build_conditions()` 中保留了这些分支作为防御性代码。然而，其中的 BUG 使得如果有人尝试使用 `"field >"` 过滤器，它会静默地回退到精确匹配 `=`，产生不可察觉的错误结果。

### 6.3 头部产品方案对比

#### SAP CAP — CQN 结构化查询

CAP 使用 CQN（Core Query Notation）作为结构化查询语言，不存在字符串操作符歧义：

```javascript
// CQN 查询是结构化的，无歧义
SELECT.from('Books')
  .where({ stock: { '>': 0 } })          // 明确的操作符
  .and({ price: { '>=': 10 } })
```

**启示**：如果未来重构查询层，可考虑使用结构化过滤对象替代字符串解析。

#### ServiceNow — GlideRecord API

ServiceNow 用方法调用替代字符串拼接：

```javascript
var gr = new GlideRecord('incident');
gr.addQuery('priority', '>=', 3);   // 方法参数，无歧义
gr.addQuery('state', '!=', 7);
```

### 6.4 细化方案

#### 唯一方案：修复操作符检测逻辑 + 添加负向测试

```python
def _build_conditions(self, filters: Dict[str, Any]) -> tuple:
    """构建SQL WHERE条件。

    操作符检测按长度降序以确保 >= 不会被 > 误匹配。
    参考 Django ORM 和 SQLAlchemy 的做法。
    """
    conditions = []
    params = []

    for key, value in filters.items():
        # 处理 __in 后缀（Django风格多选过滤）
        if key.endswith('__in'):
            field = key[:-4]
            if isinstance(value, str):
                values = [v.strip() for v in value.split(',') if v.strip()]
            else:
                values = list(value) if hasattr(value, '__iter__') else [value]
            if values:
                placeholders = ', '.join([self._placeholder()] * len(values))
                conditions.append(f"{field} IN ({placeholders})")
                params.extend(values)
            continue

        # 按长度降序检测操作符（长操作符优先，消除歧义）
        #          操作符     SQL 操作符    列名提取方式
        operators = [
            (' >=', '>=', lambda k: k.split(' >=')[0]),
            (' <=', '<=', lambda k: k.split(' <=')[0]),
            (' >',  '>',  lambda k: k.split(' >')[0]),
            (' <',  '<',  lambda k: k.split(' <')[0]),
        ]

        matched = False
        for detect, sql_op, extract_fn in operators:
            if detect in key:
                field = extract_fn(key).strip()
                conditions.append(f"{field} {sql_op} {self._placeholder()}")
                params.append(value)
                matched = True
                break

        if matched:
            continue

        # LIKE 模糊搜索
        if 'LIKE' in key.upper():
            field = key.replace(' LIKE', '').replace(' like', '').strip()
            conditions.append(f"{field} LIKE {self._placeholder()}")
            params.append(value)
            continue

        # IN 多选过滤
        if 'IN' in key.upper():
            field = key.replace(' IN', '').replace(' in', '').strip()
            if isinstance(value, (list, tuple)):
                placeholders = ', '.join([self._placeholder()] * len(value))
                conditions.append(f"{field} IN ({placeholders})")
                params.extend(value)
            else:
                conditions.append(f"{field} IN ({self._placeholder()})")
                params.append(value)
            continue

        # 默认精确匹配
        conditions.append(f"{key} = {self._placeholder()}")
        params.append(value)

    return conditions, params
```

**关键改进**：

| 项目 | 修改前 | 修改后 |
|---|---|---|
| `>=` 检测 | `if ' >=' in key` | 不变（保持正确） |
| `>` 检测 | `elif ' >' in key and not key.endswith('>')` ❌ | `(' >', ...)` 在 `>=` 之后检查 ✓ |
| `<=` 检测 | `elif ' <=' in key` | 不变（保持正确） |
| `<` 检测 | `elif ' <' in key and not key.endswith('<')` ❌ | `(' <', ...)` 在 `<=` 之后检查 ✓ |
| 代码结构 | 冗长的 if-elif 链 | 操作符表 + for 循环（更易扩展） |
| LIKE 检测 | `'LIKE' in key.upper()` | 不变（位置调整到操作符检测之后） |

**关于 `key.endswith()` 检查移除的安全性论证**：

由于操作符在列表中按 `>=` → `<=` → `>` → `<` 的顺序排列（带空格前缀的字符串比较），`>=` 总是先于 `>` 被检测。例如：
- `"age >="`: `' >=' in key` → True → 匹配 `>=` ✓（永远不会到达 `>`）
- `"age >"`:  `' >=' in key` → False, `' >' in key` → True → 匹配 `>` ✓

`break` 语句确保第一个匹配的立即生效，后续检测不再执行。这种**按长度降序 + break** 的方式是业界标准做法。

### 6.5 需要新增的负向测试用例

```python
# tests/test_sql_adapters_filters.py（新增测试文件）

def test_build_conditions_gte_operator():
    """测试 >= 操作符正确解析"""
    adapter = SQLiteAdapter()
    conditions, params = adapter._build_conditions({"age >=": 18})
    assert "age >= ?" in conditions[0]

def test_build_conditions_gt_operator():
    """测试 > 操作符正确解析（之前有 BUG）"""
    adapter = SQLiteAdapter()
    conditions, params = adapter._build_conditions({"age >": 18})
    assert "age > ?" in conditions[0]
    # BUG 修复前此断言会失败（被错误解析为 age > = ?）

def test_build_conditions_lte_operator():
    """测试 <= 操作符正确解析"""
    adapter = SQLiteAdapter()
    conditions, params = adapter._build_conditions({"price <=": 100})
    assert "price <= ?" in conditions[0]

def test_build_conditions_lt_operator():
    """测试 < 操作符正确解析（之前有 BUG）"""
    adapter = SQLiteAdapter()
    conditions, params = adapter._build_conditions({"price <": 100})
    assert "price < ?" in conditions[0]

def test_build_conditions_mixed_operators():
    """测试混合操作符的正确解析"""
    adapter = SQLiteAdapter()
    conditions, params = adapter._build_conditions({
        "age >=": 18, "age <": 65, "status": "active"
    })
    condition_strs = " ".join(conditions)
    assert "age >= ?" in condition_strs
    assert "age < ?" in condition_strs
    assert "status = ?" in condition_strs

def test_build_conditions_field_name_with_gt_in_name():
    """测试字段名包含 'gt' 的边界情况（如 hashtag）"""
    adapter = SQLiteAdapter()
    conditions, params = adapter._build_conditions({"hashtag": "test"})
    assert "hashtag = ?" in conditions[0]
    # ' >' 出现在 'hashtag' 中也会被空格前缀排除
```

### 6.6 验收标准

- [ ] 操作符检测按长度降序（`>=` → `>` → `<=` → `<`）
- [ ] `not key.endswith('>')` / `not key.endswith('<')` 移除
- [ ] 所有现有 `_build_conditions` 调用点行为不变
- [ ] 5 个新增测试用例全部通过
- [ ] 现有 SQL 适配器测试全部通过
- [ ] persistence_interceptor 的 `>=`, `<=` 过滤器继续正常工作

### 6.7 风险评估

| 风险 | 级别 | 缓解措施 |
|---|---|---|
| 字段名包含 `>=`、`<=`、`>`、`<` 字符串 | 极低 | 使用空格前缀检测（`' >='`），正常字段名不含空格 |
| LIKE/IN 先检测可能导致 LIKE 中 `>` 误匹配 | 低 | LIKE/IN 移到操作符检测之后，添加 break 确保不 fall through |
| 操作符表顺序变更影响 | 极低 | 测试覆盖 4 种操作符 + 混合场景 + 边界条件 |

---

## 7. 实施顺序与依赖关系

```
FR-P1-005 (sql_adapters)    ← 独立，无依赖
    ↓
FR-P1-003 (enum_protection) ← 独立，无依赖
    ↓
FR-P1-002 (hierarchy)       ← 独立，无依赖
    ↓
FR-P1-001 (audit_interceptor) ← 依赖 FR-P1-004 (共享 get_object_display 提取)
    ↓
FR-P1-004 (association_engine) ← 与 FR-P1-001 互有轻度依赖
```

**推荐顺序**：
1. **FR-P1-005** 先修（单一文件，明确 BUG 修复 + 测试）
2. **FR-P1-003** 次之（添加 utils 文件 + BUG 修复）
3. **FR-P1-002**（纯提取，变更面最小）
4. **FR-P1-001**（提取 module 常量）
5. **FR-P1-004** 最后（变更面最大，改 6 个公开方法签名为委托）

### 建议分批

| 批次 | FR | 预计变更文件数 | 风险级别 |
|---|---|---|---|---|
| 第一批 | P1-005 + P1-003 | 2-3 | 低 |
| 第二批 | P1-002 + P1-001 | 2-3 | 低 |
| 第三批 | P1-004 | 2-3 | 中 |

---

## 8. 变更影响评估

### 8.1 变更文件汇总

| FR | 文件 | 变更类型 | 影响范围 |
|---|---|---|---|
| P1-001 | `meta/core/interceptors/audit_interceptor.py` | 重构（合并方法+提取常量） | 仅内部方法 |
| P1-001 | `meta/core/model_utils.py`（新建） | 新增 | 供 audit/association_engine 引用 |
| P1-001 | `meta/core/association_engine.py` | 重构（替换 `_get_target_display` 调用） | 1处调用 |
| P1-002 | `meta/core/interceptors/hierarchy_validation_interceptor.py` | 重构（提取公共方法） | 仅内部方法 |
| P1-003 | `meta/core/interceptors/enum_protection_interceptor.py` | 重构+Bug修复 | 仅内部方法 |
| P1-004 | `meta/core/association_engine.py` | 重构（分派表+简化公开方法） | 6个公开方法 |
| P1-004 | `meta/services/query_service.py` | 重构（提取重复函数） | 2处调用 |
| P1-004 | `meta/core/sql_utils.py`（新建） | 新增 | 供 query_service 引用 |
| P1-005 | `meta/core/sql_adapters.py` | Bug修复（操作符检测） | `_build_conditions` 核心方法 |
| P1-005 | `meta/tests/test_sql_adapters_filters.py`（新建） | 新增测试 | 5个新测试用例 |

### 8.2 回归测试范围

| FR | 需要运行的测试 | 关键验证点 |
|---|---|---|
| P1-001 | `test_audit_*.py`, `test_change_notification*.py` | 审计日志正确写入（ASSOCIATE/DISSOCIATE） |
| P1-002 | `test_hierarchy_validation*.py` | 层级校验错误收集、force 参数 |
| P1-003 | `test_enum_protection*.py` | 枚举保护规则不变、BUG修复后查询次数减少 |
| P1-004 | `test_association*.py` | associate/assign/dissociate/unassign/query/count 行为不变 |
| P1-005 | `test_sql_adapters*.py`, `test_connection_pool.py` | `>=`/`<=` 过滤器不变、新增 `>`/`<` 测试 |

### 8.3 性能影响评估

| FR | 性能影响 | 说明 |
|---|---|---|
| P1-003 | **正向**（修复 BUG 后每次枚举检查减少 1 次 SQL 查询） | `_get_enum_type()` 从 2 次查询变为 1 次 |
| P1-004 | **极微正向**（分派表 O(1) 替代 if-elif 链 O(n)） | 理论上更快，但差异可忽略 |
| P1-005 | **无影响**（操作符检测逻辑纯重构） | `>`/`<` 分支当前未被调用 |
| P1-001/002 | **无影响** | 纯代码重组 |

### 8.4 回滚策略

所有变更均为纯重构（P1-005 修复除外），不改变外部 API 行为。如需回滚：

```bash
# 按文件级别回滚
git checkout -- meta/core/interceptors/audit_interceptor.py
git checkout -- meta/core/interceptors/hierarchy_validation_interceptor.py
git checkout -- meta/core/interceptors/enum_protection_interceptor.py
git checkout -- meta/core/association_engine.py
git checkout -- meta/core/sql_adapters.py
git checkout -- meta/services/query_service.py

# 删除新建文件
rm meta/core/model_utils.py
rm meta/core/sql_utils.py
rm meta/tests/test_sql_adapters_filters.py
```

---

## 附录 A: 消除的重复代码统计

| FR | 方法名/代码块 | 原始行数 | 重复行数 | 重复率 | 消除后行数 | 净减少 |
|---|---|---|---|---|---|---|
| P1-001 | `_log_associate` + `_log_dissociate` | 43+43=86 | 38 | 88% | 50 | -36 |
| P1-001 | `_get_object_display` + `_get_target_display`（跨文件） | 31+25=56 | 25 | 80% | 30 | -26 |
| P1-002 | `_validate_update` 错误收集 + `_validate_delete` 错误收集 | 15+15=30 | 15 | 100% | 15 | -15 |
| P1-003 | 4个 `_validate_enum_*` 中的重复模式 | 17+33+28+40=118 | 30 | 25% | 88 | -30 |
| P1-003 | `_get_enum_type()` 双重查询 BUG | 18 | 9（第二次查询） | 50% | 9 | -9 |
| P1-004 | 6个公开方法的分派逻辑 | 18×6+22=130 | 90 | 69% | 40 | -90 |
| P1-004 | `add_table_alias_to_where` 重复定义 | 11+11=22 | 11 | 100% | 11 | -11 |
| P1-005 | `_build_conditions()` 有歧义的操作符检测 | 16（>和<分支） | — | — | 12 | -4 |

**总计**：净消除约 **221 行**重复/冗余代码，同时修复 **2 个潜在 BUG**（enum 双重查询 + SQL 操作符歧义）。

## 附录 B: 参考资源

| 产品 | 关键模式 | 参考链接 |
|---|---|---|
| SAP CAP | Event Handler Phases (`@Before`/`@On`/`@After`) | [CAP Service SDK](https://cap.cloud.sap/docs/node.js/core-services) |
| SAP CAP | `@cap-js/audit-logging` plugin | [Audit Logging Plugin](https://cap.cloud.sap/docs/plugins/audit-logging) |
| Salesforce | TriggerHandler Framework | [Apex Trigger Framework](https://developer.salesforce.com/docs/atlas.en-us.apexcode.meta/apexcode/apex_triggers.htm) |
| Salesforce | Enterprise Patterns (Selector/Domain/Service) | [Apex Enterprise Patterns](https://developer.salesforce.com/wiki/apex_enterprise_patterns) |
| ServiceNow | Script Includes (DRY utility classes) | [Script Includes](https://docs.servicenow.com/bundle/tokyo-application-development/page/script/server-scripting/concept/c_ScriptIncludes.html) |
| ServiceNow | Flow Designer Subflows | [Flow Designer Subflows](https://docs.servicenow.com/bundle/tokyo-build-workflows/page/administer/flow-designer/concept/flow-designer-subflows.html) |
| ServiceNow | Metadata-Driven Validations (Sys Properties) | [System Properties](https://docs.servicenow.com/bundle/tokyo-platform-administration/page/administer/reference-pages/concept/c_SystemProperties.html) |