---
alwaysApply: false
description: "审计合规规范：审计日志、操作追踪、权限合规"
globs: "meta/api/*,meta/core/audit*,meta/core/models_annotations.py"
---

# 审计合规规范

> 最后更新: 2026-06-07 | 状态: 活跃
> 本文档定义了审计日志的合规要求，确保所有业务操作都正确记录审计日志。

---

## 一、审计日志写入规范

### 1.1 必须记录审计日志的操作

| 操作类型 | 说明 | 示例 |
|----------|------|------|
| **CREATE** | 创建操作 | 创建用户、创建角色、创建用户组 |
| **UPDATE** | 更新操作 | 更新用户信息、更新角色权限 |
| **DELETE** | 删除操作 | 删除用户、删除角色、删除用户组 |
| **ASSIGN** | 分配操作 | 分配角色、分配权限、分配用户组成员 |
| **REVOKE** | 撤销操作 | 撤销角色、撤销权限 |

### 1.2 审计日志必须包含的信息

| 字段 | 说明 | 是否必须 |
|------|------|----------|
| `object_type` | 操作对象类型 | [REQUIRED] 必须 |
| `object_id` | 操作对象ID | [REQUIRED] 必须 |
| `action` | 操作类型 | [REQUIRED] 必须 |
| `user_id` | 操作用户ID | [REQUIRED] 必须 |
| `user_name` | 操作用户名 | [REQUIRED] 必须 |
| `ip_address` | 操作IP地址 | [REQUIRED] 必须 |
| `created_at` | 操作时间 | [REQUIRED] 必须 |
| `old_data` | 变更前数据 | [CONDITIONAL] UPDATE/DELETE 必须 |
| `new_data` | 变更后数据 | [CONDITIONAL] CREATE/UPDATE 必须 |
| `trace_id` | 追踪ID | [RECOMMENDED] 推荐 |
| `user_agent` | 用户代理 | [RECOMMENDED] 推荐 |

### 1.3 审计日志写入方式

**必须使用 `AsyncAuditWriter`**（参考 SAP V2 Update 模式）：

```python
from meta.services.audit_interceptor import audit_log, AuditInterceptor

# 方式 1: 使用装饰器（推荐）
@audit_log(object_type='user_group')
def create_group(self, name, code, ...):
    ...

# 方式 2: 使用 AuditInterceptor
audit_interceptor = AuditInterceptor(data_source)
audit_interceptor.log_create(
    object_type='user',
    object_id=user_id,
    data={'username': username, ...},
)
```

**禁止直接写入 audit_logs 表**：

```python
# [X] 错误方式
_data_source.execute("""
    INSERT INTO audit_logs (...)
    VALUES (...)
""")

# [OK] 正确方式
audit_interceptor.log_create(...)
```

---

## 二、后端审计日志实现

### 2.1 审计拦截器机制 (v2 更新)

**当前实现**：使用 `AuditInterceptor` 拦截器，自动记录所有 BO 操作。

**文件位置**: [meta/core/interceptors/audit_interceptor.py](../../meta/core/interceptors/audit_interceptor.py)

**工作原理**：

```
BO Framework 执行操作
    |
    v
Interceptor Chain 调用
    |
    v
ContextInterceptor (初始化上下文)
    |
    v
LockInterceptor (获取锁)
    |
    v
DataPermissionInterceptor (权限检查)
    |
    v
[业务逻辑执行]
    |
    v
AuditInterceptor.after_action() <- 自动写入审计日志
    |
    v
PersistenceInterceptor (持久化)
```

**YAML 配置方式**：

```yaml
# 在 YAML 中启用审计
id: user
aspects: [audit_aspect]           # 自动注入审计字段

audit:
  enabled: true                    # 启用审计日志
  strategy: business_only          # 策略：all/business_only/minimal
  fields: [username, email, status] # 审计字段列表
  sensitive_fields: [password_hash] # 敏感字段（仅记录变更，不记录值）
```

**审计数据结构**：

```python
# AuditInterceptor 内部生成的审计记录
{
    "object_type": "user",
    "object_id": 42,
    "action": "UPDATE",
    "actor_id": 1,
    "actor_name": "admin",
    "timestamp": "2026-05-19T15:30:00Z",
    "trace_id": "abc123",              # X-Trace-Id
    "changes": [                       # 变更详情
        {
            "field": "status",
            "old_value": "inactive",
            "new_value": "active"
        },
        {
            "field": "email",
            "old_value": "old@test.com",
            "new_value": "new@test.com"
        }
    ],
    "context": {
        "ip_address": "192.168.1.100",
        "user_agent": "Mozilla/5.0...",
        "source": "ui"                 # ui/api/migration/script
    }
}
```

### 2.2 手动触发审计（可选）

如果需要在自定义逻辑中手动记录审计日志：

```python
from meta.core.interceptors.audit_interceptor import AuditInterceptor

def custom_business_logic():
    # ... 业务逻辑 ...

    # 手动触发审计（不推荐，优先使用 Interceptor）
    audit = AuditInterceptor()
    audit.log_manual(
        object_type="user",
        object_id=42,
        action="CUSTOM_ACTION",
        changes={"field": "value"},
        context={}
    )
```

---

## 三、source_of_truth 一致性要求

### 3.1 定义规则

当字段定义了 `source_of_truth` 时，**必须**同时定义 `derivation` 规则：

```yaml
# [OK] 正确
- id: created_by
  semantics:
    source_of_truth: audit_logs
    derivation:
      from: audit_logs
      rule: "user_name WHERE action = 'CREATE'"

# [X] 错误
- id: created_by
  semantics:
    source_of_truth: audit_logs
    # 缺少 derivation 规则
```

### 3.2 materialization 策略

当使用 `redundant_storage` 策略时，**必须**关联技术债务 ID：

```yaml
# [OK] 正确
- id: created_by
  materialization:
    strategy: redundant_storage
    tech_debt_id: TD-001  # 关联技术债务

# [X] 错误
- id: created_by
  materialization:
    strategy: redundant_storage
    # 缺少 tech_debt_id
```

### 3.3 验证机制

应用启动时**必须**运行元数据验证：

```python
from meta.core.metadata_validator import MetadataValidator

def validate_metadata_on_startup():
    validator = MetadataValidator()
    result = validator.validate_all()
    validator.log_results()

    if not result['valid']:
        logger.warning("[Startup] Metadata validation failed")
```

---

## 四、代码审查检查清单

### 4.1 审计日志检查

- [ ] 新增业务方法是否使用 `@audit_log` 装饰器？
- [ ] 新增实体是否引用 `audit_aspect`？
- [ ] `source_of_truth` 是否有对应的 `derivation` 规则？
- [ ] `redundant_storage` 是否关联了 `tech_debt_id`？
- [ ] 审计日志是否使用 `AsyncAuditWriter`？

### 4.2 事务一致性检查

- [ ] 业务事务是否与审计日志事务分离？
- [ ] 审计日志写入失败是否不影响业务结果？
- [ ] 是否支持审计日志失败重试？

### 4.3 元数据检查

- [ ] 新增实体是否有对应的 YAML schema？
- [ ] 新增字段是否定义了 `semantics`？
- [ ] 新增字段是否定义了 `ui` 配置？

---

## 五、前端审计集成 (v2 更新)

### 5.1 MetaListPage 自动审计

**当前实现**：前端通过 `MetaListPage` 组件和 `useMetaList` Composable 与后端 BO Framework 对接，**审计由后端 AuditInterceptor 自动完成**，前端无需额外代码。

```vue
<!-- [OK] 正确：使用元数据驱动组件，审计自动处理 -->
<template>
  <MetaListPage
    object-type="user"
    :enable-detail="true"
    :enable-auto-crud="true"
    @toolbar-action="handleAction"
  />
</template>

<script setup>
// 所有 CRUD 操作都会触发后端 AuditInterceptor
// 无需手动调用任何审计 API
</script>
```

### 5.2 审计日志查看组件

**组件位置**: [AuditLog.vue](../../src/components/common/AuditLog/AuditLog.vue)

在对象详情页中嵌入审计日志面板：

```vue
<DetailPage :object-type="user" :record-id="userId">
  <template #tab-audit>
    <AuditLog
      :object-type="user"
      :object-id="userId"
      :show-changes="true"
      :show-context="false"
    />
  </template>
</DetailPage>
```

### 5.3 审计数据展示格式

**时间线展示**：

```
2026-05-19 15:30:00 | admin (ID:1) 更新了此记录
|-- 状态: inactive -> active
|-- 邮箱: old@test.com -> new@test.com
|
2026-05-19 14:20:00 | system 创建了此记录
|-- 用户名: admin
|-- 邮箱: admin@example.com
\-- 状态: active
```

**变更高亮规则**：

- 新增字段：[ADDED] 绿色背景
- 删除字段：[REMOVED] 红色背景（显示删除线）
- 修改字段：[MODIFIED] 黄色背景（old -> new）
- 敏感字段：[MASKED] 隐藏实际值，仅显示 `***` 或 `[REDACTED]`

---

## 六、违规处理

### 6.1 违规级别

| 级别 | 说明 | 处理方式 |
|------|------|----------|
| **ERROR** | 严重违规（如缺少 derivation 规则） | 阻止部署 |
| **WARNING** | 警告（如缺少 tech_debt_id） | 记录日志，允许部署 |
| **INFO** | 提示（如使用 redundant_storage） | 记录日志 |

### 6.2 违规记录

所有违规记录都应添加到 `docs/TECH-DEBT.md` 中。

---

## 七、参考资料

### 7.1 SAP 最佳实践

- [SAP CDS Virtual Field](https://help.sap.com/doc/saphelp_nw750/7.5.5/en-US/cf/e84f2b4c0d4a11d189710000e829fbbb/content.htm)
- [SAP Change Documents](https://help.sap.com/doc/saphelp_nw750/7.5.5/en-US/4e/c8873c1e3b11d19550000e83534297/content.htm)

### 7.2 内部文档

- `docs/TECH-DEBT.md` - 技术债务跟踪
- `.trae/specs/audit-log-capability-enhancement` - 审计日志能力完善 Spec
- `.trae/specs/transaction-system` - 事务系统完备性改造 Spec

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-07 | AI Assistant | 修复章节编号混乱（原 2.2/2.3/3.1 错误编号），重编号为 3.1/3.2/3.3/4.1/4.2/4.3/5.1/5.2/5.3/6.1/6.2/7.1/7.2 |
| 2026-05-08 | AI Assistant | 创建审计合规规范文档 |
