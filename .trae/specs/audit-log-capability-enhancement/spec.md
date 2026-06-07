# 审计日志能力完善与治理机制 Spec

> **创建日期**: 2026-05-08
> **相关Spec**: p1-phase-a-aspect-pseudo-variables, metadata-model-governance, virtual-field-query-engine, transaction-system
> **优先级**: P0（核心能力缺失）

---

## 一、Why

### 问题背景

在本次迭代中，新建用户组时发现 `created_at` 字段为空，暴露了审计日志能力的严重缺陷：

#### 问题 1：历史设计规范未被遵守

**历史设计（aspects.yaml）**：
```yaml
- id: created_by
  semantics:
    source_of_truth: audit_logs        # 单一事实源
    derivation:
      from: audit_logs
      rule: "user_name WHERE action = 'CREATE'"
    materialization:
      strategy: redundant_storage       # 过渡方案
      description: 冗余存储于业务表，未来可改为虚拟计算
```

**实际实现**：
- ❌ 没有实现 derivation 查询机制
- ❌ 很多业务操作没有写入 audit_logs
- ❌ `source_of_truth: audit_logs` 的设计被忽略
- ❌ "过渡方案"变成了"永久方案"

#### 问题 2：审计日志写入不完整

| 业务操作 | 写入 audit_logs | 写入 created_by | 问题 |
|----------|-----------------|-----------------|------|
| create_user | ✅ | ❌ | created_by 未填充 |
| create_group | ❌ | ❌ | 完全缺失 |
| create_role | ❌ | ❌ | 完全缺失 |
| update_user | ✅ | ❌ | updated_by 未填充 |

#### 问题 3：缺乏强制约束机制

- 没有代码检查验证 `source_of_truth` 的一致性
- 没有测试验证审计日志的完整性
- 没有技术债务跟踪机制

#### 问题 4：历史事务一致性设计未被正确实施

**历史设计（transaction-system spec FR-007）**：
```
参考 SAP V2 Update 模式：
- 业务操作（insert/update/delete）在主事务中执行
- 主事务提交后，审计日志在独立 mini 事务中写入
- 审计日志写入失败不影响业务结果
- 审计日志写入失败时记录 warning 级别日志
```

**已实现的能力**：
- ✅ `AsyncAuditWriter` - 异步审计日志写入器（参考 SAP V2 Update）
- ✅ `AuditService.retry_failed_record` - 失败记录重试机制
- ✅ `WriteGuard/CascadeGuard` - 冗余字段一致性保障
- ✅ `RedundancyAuditor` - 冗余字段审计器

**未正确实施的问题**：
- ❌ 很多业务操作（如 `create_group`）没有使用 `AsyncAuditWriter`
- ❌ 审计日志写入没有与业务事务分离
- ❌ 失败补偿机制没有被业务代码调用

### 目标

1. **实现 derivation 查询机制** - 从 audit_logs 派生 created_by/updated_by
2. **统一审计日志写入** - 所有操作自动写入 audit_logs（使用已有的 AsyncAuditWriter）
3. **事务一致性保障** - 业务事务与审计日志事务分离（V2 模式）
4. **建立强制约束机制** - 确保设计规范被遵守
5. **建立技术债务跟踪** - 防止"过渡方案"变成永久方案

---

## 二、What Changes

### 核心改进

#### 1. Derivation 查询引擎

实现从 `audit_logs` 派生 `created_by`/`updated_by` 的查询机制：

```python
# meta/core/derivation_executor.py (新建)
class DerivationExecutor:
    """派生字段执行器 - 从 source_of_truth 查询派生字段"""
    
    def derive_field(self, field: MetaField, object_type: str, object_id: int) -> Any:
        """根据 derivation 规则派生字段值"""
        if field.semantics.source_of_truth == 'audit_logs':
            return self._derive_from_audit_logs(field, object_type, object_id)
    
    def _derive_from_audit_logs(self, field: MetaField, object_type: str, object_id: int):
        """从 audit_logs 派生字段"""
        rule = field.semantics.derivation
        # 执行派生规则查询
        ...
```

#### 2. 审计日志写入拦截器

**使用已有的 AsyncAuditWriter**（参考 SAP V2 Update 模式）：

```python
# meta/services/audit_interceptor.py (新建或增强)
from meta.services.async_audit_writer import async_audit_writer

@audit_log(object_type='user_group')
def create_group(self, name, code, ...):
    # 业务逻辑
    ...
    # 审计日志异步写入（V2 模式）
    async_audit_writer.submit(
        lambda: audit_service.log_create(
            object_type='user_group',
            object_id=group_id,
            data=data
        ),
        trace_id=trace_id,
        transaction_id=transaction_id
    )
```

**关键特性**：
- 业务事务提交后，审计日志异步写入
- 审计日志写入失败不影响业务结果
- 支持重试和失败记录持久化
- 队列满时降级为同步写入

#### 3. 元数据验证器

验证 `source_of_truth` 的一致性：

```python
# meta/core/metadata_validator.py (新建)
def validate_source_of_truth(meta_obj: MetaObject):
    """验证 source_of_truth 的一致性"""
    for field in meta_obj.fields:
        if field.semantics.source_of_truth == 'audit_logs':
            # 验证是否有 derivation 规则
            # 验证数据库是否有对应字段
            ...
```

#### 4. 技术债务跟踪文档

建立技术债务跟踪机制：

```markdown
# docs/TECH-DEBT.md (新建)

## TD-001: 审计字段冗余存储

**状态**: 🔴 未解决
**优先级**: P0
**描述**: aspects.yaml 定义了 source_of_truth: audit_logs，但实际实现选择了 redundant_storage
**解决方案**: 实现 derivation 查询机制
**负责人**: TBD
**截止日期**: TBD
```

---

## 三、Impact

### 受影响的代码

**后端**：
- `meta/core/derivation_executor.py` - 新建
- `meta/services/audit_interceptor.py` - 新建
- `meta/core/metadata_validator.py` - 新建
- `meta/services/user_service.py` - 添加审计拦截器
- `meta/services/user_group_service.py` - 添加审计拦截器
- `meta/services/role_service.py` - 添加审计拦截器
- `meta/core/action_executor.py` - 集成 derivation 查询

**前端**：
- `src/views/SystemManagement/meta/userMeta.js` - 审计字段自动注入
- `src/views/SystemManagement/meta/roleMeta.js` - 审计字段自动注入
- `src/views/SystemManagement/meta/userGroupMeta.js` - 审计字段自动注入

**文档**：
- `docs/TECH-DEBT.md` - 技术债务跟踪（新建）
- `.trae/rules/audit-compliance.md` - 审计合规规范（新建）

---

## 四、ADDED Requirements

### Requirement: Derivation 查询引擎

系统**必须**支持从 `source_of_truth` 派生字段值，特别是从 `audit_logs` 派生 `created_by`/`updated_by`。

#### Scenario: 从 audit_logs 派生 created_by
- **GIVEN** 字段定义了 `source_of_truth: audit_logs` 和 `derivation` 规则
- **WHEN** 查询该字段的值
- **THEN** 系统从 audit_logs 查询并返回派生值

#### Scenario: 派生规则为 user_name WHERE action = 'CREATE'
- **GIVEN** 字段定义了 `derivation.rule: "user_name WHERE action = 'CREATE'"`
- **WHEN** 派生该字段
- **THEN** 系统执行 SQL 查询获取首次创建操作的用户名

#### Scenario: 派生规则为 user_name ORDER BY created_at DESC LIMIT 1
- **GIVEN** 字段定义了 `derivation.rule: "user_name ORDER BY created_at DESC LIMIT 1 WHERE action IN ('CREATE', 'UPDATE')"`
- **WHEN** 派生该字段
- **THEN** 系统执行 SQL 查询获取最后一次创建或更新操作的用户名

#### Scenario: audit_logs 中无记录时返回空
- **GIVEN** audit_logs 中没有该对象的记录
- **WHEN** 派生 created_by/updated_by
- **THEN** 返回空字符串或 null

---

### Requirement: 审计日志写入拦截器

系统**必须**提供统一的审计日志写入机制，所有业务操作自动写入 audit_logs。

**关键约束**：必须使用已有的 `AsyncAuditWriter`，实现 V2 异步写入模式（参考 SAP V2 Update）。

#### Scenario: 创建操作自动写入审计日志
- **GIVEN** 业务方法使用 `@audit_log(object_type='user_group')` 装饰器
- **WHEN** 执行创建操作
- **THEN** 系统通过 AsyncAuditWriter 异步写入 audit_logs，action='CREATE'

#### Scenario: 更新操作自动写入审计日志
- **GIVEN** 业务方法使用 `@audit_log(object_type='user_group')` 装饰器
- **WHEN** 执行更新操作
- **THEN** 系统通过 AsyncAuditWriter 异步写入 audit_logs，action='UPDATE'，记录字段变更

#### Scenario: 删除操作自动写入审计日志
- **GIVEN** 业务方法使用 `@audit_log(object_type='user_group')` 装饰器
- **WHEN** 执行删除操作
- **THEN** 系统通过 AsyncAuditWriter 异步写入 audit_logs，action='DELETE'

#### Scenario: 审计日志包含完整上下文
- **GIVEN** 审计日志写入
- **WHEN** 写入 audit_logs
- **THEN** 包含 user_id, user_name, ip_address, user_agent, trace_id 等完整上下文

#### Scenario: 业务事务与审计日志事务分离（V2 模式）
- **GIVEN** 业务操作在主事务中执行
- **WHEN** 主事务提交成功
- **THEN** 审计日志在独立 mini 事务中异步写入
- **AND** 审计日志写入失败不影响业务结果
- **AND** 审计日志写入失败时记录 warning 级别日志

#### Scenario: 审计日志写入失败自动重试
- **GIVEN** 审计日志写入失败
- **WHEN** AsyncAuditWriter 检测到失败
- **THEN** 自动重试最多 3 次
- **AND** 重试失败后持久化失败记录到 audit_logs 表
- **AND** 可通过 AuditService.retry_failed_record 手动重试

#### Scenario: 队列满时降级为同步写入
- **GIVEN** AsyncAuditWriter 队列已满
- **WHEN** 提交新的审计日志
- **THEN** 降级为同步写入
- **AND** 记录 warning 日志

---

### Requirement: 元数据验证器

系统**必须**验证 `source_of_truth` 的一致性，确保设计规范被遵守。

#### Scenario: 验证 source_of_truth 与 derivation 一致
- **GIVEN** 字段定义了 `source_of_truth: audit_logs`
- **WHEN** 运行元数据验证
- **THEN** 系统检查是否有对应的 `derivation` 规则，缺失时报错

#### Scenario: 警告冗余存储与 source_of_truth 冲突
- **GIVEN** 字段定义了 `source_of_truth: audit_logs` 但 `materialization.strategy: redundant_storage`
- **WHEN** 运行元数据验证
- **THEN** 系统输出警告，提示这是技术债务

#### Scenario: 启动时自动验证
- **GIVEN** 应用启动
- **WHEN** 加载元模型
- **THEN** 系统自动运行元数据验证，输出验证结果

---

### Requirement: 技术债务跟踪机制

系统**必须**建立技术债务跟踪机制，防止"过渡方案"变成永久方案。

#### Scenario: 记录技术债务
- **GIVEN** 发现设计规范未被遵守
- **WHEN** 创建技术债务记录
- **THEN** 记录包含状态、优先级、描述、解决方案、负责人、截止日期

#### Scenario: 定期回顾技术债务
- **GIVEN** 技术债务记录存在
- **WHEN** 每周/每月回顾
- **THEN** 更新状态，推进解决

#### Scenario: 新增功能时检查技术债务
- **GIVEN** 开发新功能
- **WHEN** 查阅技术债务列表
- **THEN** 避免引入类似问题

---

### Requirement: 前端审计字段自动注入

系统**必须**在前端元数据中自动注入审计字段，无需手动配置。

#### Scenario: 自动注入 created_at/updated_at 列
- **GIVEN** 前端定义实体元数据
- **WHEN** 使用 `enhanceMetaWithAudit()` 增强
- **THEN** 自动追加 created_at, updated_at 列到 tableColumns

#### Scenario: 自动启用变更历史
- **GIVEN** 前端定义实体元数据
- **WHEN** 使用 `enhanceMetaWithAudit()` 增强
- **THEN** 自动设置 `showChangeHistory: true`

#### Scenario: 自动添加审计字段过滤器
- **GIVEN** 前端定义实体元数据
- **WHEN** 使用 `enhanceMetaWithAudit()` 增强
- **THEN** 自动追加 created_at_range 过滤器到 filterFields

---

## 五、MODIFIED Requirements

### Requirement: aspects.yaml 审计字段定义

**原需求**: 审计字段使用 `redundant_storage` 作为过渡方案

**修改后**: 审计字段**必须**同时支持两种模式：
1. **冗余存储模式**（当前实现）：业务表存储 created_by/updated_by
2. **派生模式**（新增）：从 audit_logs 派生 created_by/updated_by

```yaml
- id: created_by
  semantics:
    source_of_truth: audit_logs
    derivation:
      from: audit_logs
      rule: "user_name WHERE action = 'CREATE'"
    auto_fill:
      on_create: $user.name
  materialization:
    strategy: redundant_storage  # 保留，但标记为技术债务
    tech_debt_id: TD-001         # 新增：关联技术债务
```

### Requirement: user_group_service 审计日志写入

**原需求**: 手动写入 created_at/updated_at

**修改后**: 使用 `@audit_log` 装饰器自动写入审计日志：

```python
@audit_log(object_type='user_group')
def create_group(self, name, code, ...):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor = self.ds.execute(
        """INSERT INTO user_groups (..., created_at, updated_at, created_by, updated_by) 
           VALUES (..., ?, ?, ?, ?)""",
        [..., now, now, user_id, user_id]
    )
    # 审计日志由装饰器自动写入
    return cursor.lastrowid
```

---

## 六、技术方案

### 6.1 Derivation 查询引擎

```python
# meta/core/derivation_executor.py

class DerivationExecutor:
    """派生字段执行器
    
    参考 SAP CDS Virtual Field 机制
    """
    
    def __init__(self, data_source: DataSource):
        self.ds = data_source
    
    def derive_field(self, field: MetaField, object_type: str, object_id: int) -> Any:
        """根据 derivation 规则派生字段值"""
        if not hasattr(field, 'semantics') or not field.semantics:
            return None
        
        source = getattr(field.semantics, 'source_of_truth', None)
        if source == 'audit_logs':
            return self._derive_from_audit_logs(field, object_type, object_id)
        
        return None
    
    def _derive_from_audit_logs(self, field: MetaField, object_type: str, object_id: int) -> Any:
        """从 audit_logs 派生字段值"""
        derivation = getattr(field.semantics, 'derivation', None)
        if not derivation:
            return None
        
        rule = derivation.get('rule', '')
        
        # 解析规则
        if 'user_name WHERE action' in rule:
            return self._derive_user_name(object_type, object_id, rule)
        
        return None
    
    def _derive_user_name(self, object_type: str, object_id: int, rule: str) -> Optional[str]:
        """派生用户名"""
        if "action = 'CREATE'" in rule:
            query = """
                SELECT user_name FROM audit_logs 
                WHERE object_type = ? AND object_id = ? AND action = 'CREATE'
                ORDER BY created_at ASC LIMIT 1
            """
        elif "action IN ('CREATE', 'UPDATE')" in rule:
            query = """
                SELECT user_name FROM audit_logs 
                WHERE object_type = ? AND object_id = ? AND action IN ('CREATE', 'UPDATE')
                ORDER BY created_at DESC LIMIT 1
            """
        else:
            return None
        
        result = self.ds.execute(query, [object_type, object_id]).fetchone()
        return result[0] if result else None
    
    def derive_batch(self, fields: List[MetaField], object_type: str, object_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """批量派生字段值（性能优化）"""
        results = {}
        for object_id in object_ids:
            results[object_id] = {}
            for field in fields:
                results[object_id][field.id] = self.derive_field(field, object_type, object_id)
        return results
```

### 6.2 审计日志写入拦截器

```python
# meta/services/audit_interceptor.py

from functools import wraps
from flask import g, request
from datetime import datetime
import json

def audit_log(object_type: str):
    """审计日志装饰器
    
    自动记录业务操作到 audit_logs
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # 获取用户上下文
            user_id = getattr(g, 'user_id', None)
            user_name = getattr(g, 'user_name', None)
            trace_id = getattr(g, 'trace_id', None)
            
            # 判断操作类型
            func_name = func.__name__.lower()
            if 'create' in func_name:
                action = 'CREATE'
            elif 'update' in func_name:
                action = 'UPDATE'
            elif 'delete' in func_name:
                action = 'DELETE'
            else:
                action = 'UNKNOWN'
            
            # 记录变更前数据（更新/删除时）
            old_data = None
            if action in ['UPDATE', 'DELETE']:
                object_id = kwargs.get('id') or kwargs.get('group_id') or kwargs.get('role_id') or kwargs.get('user_id')
                if object_id:
                    old_data = self._get_object(object_id)
            
            # 执行业务操作
            result = func(self, *args, **kwargs)
            
            # 记录变更后数据（创建/更新时）
            new_data = None
            object_id = None
            if result:
                if isinstance(result, int):
                    object_id = result
                    if action == 'CREATE':
                        new_data = self._get_object(object_id)
                elif isinstance(result, dict):
                    object_id = result.get('id')
                    new_data = result
            
            # 写入审计日志
            if object_id:
                _write_audit_log(
                    object_type=object_type,
                    object_id=object_id,
                    action=action,
                    user_id=user_id,
                    user_name=user_name,
                    ip_address=request.remote_addr if request else None,
                    user_agent=request.headers.get('User-Agent', '') if request else None,
                    trace_id=trace_id,
                    old_data=old_data,
                    new_data=new_data
                )
            
            return result
        return wrapper
    return decorator

def _write_audit_log(**kwargs):
    """写入审计日志"""
    from meta.core.datasource import get_data_source
    ds = get_data_source()
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    ds.execute("""
        INSERT INTO audit_logs 
        (object_type, object_id, action, user_id, user_name, ip_address, user_agent, 
         created_at, trace_id, extra_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        kwargs['object_type'],
        kwargs['object_id'],
        kwargs['action'],
        kwargs.get('user_id'),
        kwargs.get('user_name'),
        kwargs.get('ip_address'),
        kwargs.get('user_agent'),
        now,
        kwargs.get('trace_id'),
        json.dumps({
            'old_data': kwargs.get('old_data'),
            'new_data': kwargs.get('new_data')
        }) if kwargs.get('old_data') or kwargs.get('new_data') else None
    ])
```

### 6.3 元数据验证器

```python
# meta/core/metadata_validator.py

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class MetadataValidator:
    """元数据验证器
    
    验证元数据配置的一致性和完整性
    """
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.tech_debts = []
    
    def validate_all(self, meta_objects: List['MetaObject']) -> Dict[str, Any]:
        """验证所有元对象"""
        for meta_obj in meta_objects:
            self.validate(meta_obj)
        
        return {
            'valid': len(self.errors) == 0,
            'errors': self.errors,
            'warnings': self.warnings,
            'tech_debts': self.tech_debts
        }
    
    def validate(self, meta_obj: 'MetaObject'):
        """验证单个元对象"""
        for field in meta_obj.fields:
            self._validate_field(field, meta_obj.id)
    
    def _validate_field(self, field: 'MetaField', object_id: str):
        """验证字段"""
        if not hasattr(field, 'semantics') or not field.semantics:
            return
        
        # 验证 source_of_truth
        source = getattr(field.semantics, 'source_of_truth', None)
        if source:
            self._validate_source_of_truth(field, object_id, source)
    
    def _validate_source_of_truth(self, field: 'MetaField', object_id: str, source: str):
        """验证 source_of_truth 一致性"""
        
        # 检查是否有 derivation 规则
        derivation = getattr(field.semantics, 'derivation', None)
        if not derivation:
            self.errors.append({
                'type': 'MISSING_DERIVATION',
                'object': object_id,
                'field': field.id,
                'message': f"Field {field.id} has source_of_truth={source} but no derivation rule"
            })
        
        # 检查 materialization 策略
        materialization = getattr(field, 'materialization', None)
        if materialization and materialization.get('strategy') == 'redundant_storage':
            tech_debt_id = materialization.get('tech_debt_id')
            if not tech_debt_id:
                self.warnings.append({
                    'type': 'TECH_DEBT_MISSING_ID',
                    'object': object_id,
                    'field': field.id,
                    'message': f"Field {field.id} uses redundant_storage but no tech_debt_id. "
                               f"This should be tracked as technical debt."
                })
            
            self.tech_debts.append({
                'id': tech_debt_id or f'TD-{field.id}',
                'object': object_id,
                'field': field.id,
                'description': f"Field {field.id} uses redundant_storage but source_of_truth is {source}",
                'solution': f"Implement derivation query for {field.id}"
            })
    
    def log_results(self):
        """输出验证结果"""
        if self.errors:
            logger.error(f"[MetadataValidator] {len(self.errors)} errors found:")
            for error in self.errors:
                logger.error(f"  - {error['message']}")
        
        if self.warnings:
            logger.warning(f"[MetadataValidator] {len(self.warnings)} warnings found:")
            for warning in self.warnings:
                logger.warning(f"  - {warning['message']}")
        
        if self.tech_debts:
            logger.info(f"[MetadataValidator] {len(self.tech_debts)} technical debts found:")
            for debt in self.tech_debts:
                logger.info(f"  - [{debt['id']}] {debt['description']}")
        
        if not self.errors and not self.warnings:
            logger.info("[MetadataValidator] All validations passed")
```

### 6.4 前端元数据增强

```javascript
// src/utils/metaEnhancer.js

/**
 * 元数据增强器 - 自动注入审计字段和能力
 */
export function enhanceMetaWithAudit(meta) {
  const auditFields = [
    {
      key: 'created_at',
      label: '创建时间',
      type: 'time',
      width: '160px',
      sortable: true,
      ui: { visible: true, editable: false }
    },
    {
      key: 'updated_at',
      label: '变更时间',
      type: 'time',
      width: '160px',
      sortable: true,
      ui: { visible: true, editable: false }
    }
  ]
  
  const auditFilters = [
    {
      key: 'created_at_range',
      label: '创建时间',
      type: 'date_range',
      placeholder: '选择时间范围'
    }
  ]
  
  // 1. 自动追加审计列
  if (!meta.tableColumns) meta.tableColumns = []
  const existingKeys = new Set(meta.tableColumns.map(c => c.key))
  for (const field of auditFields) {
    if (!existingKeys.has(field.key)) {
      meta.tableColumns.push(field)
    }
  }
  
  // 2. 自动追加审计过滤器
  if (!meta.filterFields) meta.filterFields = []
  const existingFilterKeys = new Set(meta.filterFields.map(f => f.key))
  for (const filter of auditFilters) {
    if (!existingFilterKeys.has(filter.key)) {
      meta.filterFields.push(filter)
    }
  }
  
  // 3. 自动启用变更历史
  if (meta.showChangeHistory === undefined) {
    meta.showChangeHistory = true
  }
  
  return meta
}
```

---

## 七、实施计划

### Phase 1: 核心能力实现（3天）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 1.1 实现 DerivationExecutor | 派生字段查询引擎 | P0 |
| 1.2 实现 audit_interceptor | 审计日志写入装饰器 | P0 |
| 1.3 实现 MetadataValidator | 元数据验证器 | P0 |
| 1.4 修复 user_group_service | 添加审计拦截器 | P0 |
| 1.5 修复 user_service | 添加审计拦截器 | P0 |
| 1.6 修复 role_service | 添加审计拦截器 | P0 |

### Phase 2: 前端集成（2天）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 2.1 实现 metaEnhancer | 前端元数据增强 | P1 |
| 2.2 重构 userMeta | 使用 enhanceMetaWithAudit | P1 |
| 2.3 重构 roleMeta | 使用 enhanceMetaWithAudit | P1 |
| 2.4 重构 userGroupMeta | 使用 enhanceMetaWithAudit | P1 |

### Phase 3: 验证与文档（1天）

| 任务 | 说明 | 优先级 |
|------|------|--------|
| 3.1 创建 TECH-DEBT.md | 技术债务跟踪文档 | P1 |
| 3.2 创建 audit-compliance.md | 审计合规规范 | P1 |
| 3.3 编写单元测试 | DerivationExecutor, MetadataValidator | P1 |
| 3.4 编写集成测试 | 完整审计流程测试 | P1 |

---

## 八、验收标准

### 功能验收
- [ ] 新建用户组时 created_at 自动填充
- [ ] 新建用户组时 created_by 自动填充
- [ ] 更新用户组时 updated_at 自动填充
- [ ] 更新用户组时 updated_by 自动填充
- [ ] 审计日志自动写入 audit_logs 表
- [ ] 变更历史正确显示

### 验证验收
- [ ] MetadataValidator 检测到 source_of_truth 不一致时报错
- [ ] MetadataValidator 检测到 redundant_storage 时输出警告
- [ ] 应用启动时自动运行元数据验证

### 文档验收
- [ ] TECH-DEBT.md 记录了所有技术债务
- [ ] audit-compliance.md 定义了审计合规规范
- [ ] 所有技术债务都有负责人和截止日期

---

## 九、如何保障下次不忘记

### 机制 1: 启动时自动验证

```python
# meta/server.py

from meta.core.metadata_validator import MetadataValidator
from meta.core.yaml_loader import load_all_meta_objects

def validate_metadata_on_startup():
    """启动时验证元数据"""
    meta_objects = load_all_meta_objects()
    validator = MetadataValidator()
    result = validator.validate_all(meta_objects)
    validator.log_results()
    
    if not result['valid']:
        logger.warning("[Startup] Metadata validation failed, please fix errors")

# 在应用启动时调用
validate_metadata_on_startup()
```

### 机制 2: 技术债务强制关联

```yaml
# aspects.yaml
- id: created_by
  materialization:
    strategy: redundant_storage
    tech_debt_id: TD-001  # 强制关联技术债务 ID
```

### 机制 3: 代码审查检查清单

```markdown
# .trae/rules/code-review-checklist.md

## 审计日志检查

- [ ] 新增业务方法是否使用 @audit_log 装饰器？
- [ ] 新增实体是否引用 audit_aspect？
- [ ] source_of_truth 是否有对应的 derivation 规则？
- [ ] redundant_storage 是否关联了 tech_debt_id？
```

### 机制 4: 定期技术债务回顾

```markdown
# docs/TECH-DEBT-REVIEW.md

## 每周回顾

- [ ] 检查所有 TD-* 状态
- [ ] 更新负责人和截止日期
- [ ] 推进解决方案
```

---

## 十、参考资料

- [SAP CDS Virtual Field](https://help.sap.com/doc/saphelp_nw750/7.5.5/en-US/cf/e84f2b4c0d4a11d189710000e829fbbb/content.htm)
- [SAP Change Documents](https://help.sap.com/doc/saphelp_nw750/7.5.5/en-US/4e/c8873c1e3b11d19550000e83534297/content.htm)
- `p1-phase-a-aspect-pseudo-variables` spec - Aspect 和 Pseudo Variables
- `metadata-model-governance` spec - 元数据治理规范
- `virtual-field-query-engine` spec - 虚拟字段查询引擎
