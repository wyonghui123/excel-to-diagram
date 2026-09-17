#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write the permission spec markdown file with UTF-8 encoding.

This script is used to avoid Chinese character corruption (? marks)
that occurs when using the Write tool directly on .md files.
"""

from pathlib import Path
import sys

# Target file path (use raw string to avoid escape issues)
target_file = Path(r"d:\filework\excel-to-diagram\docs\specs\spec-permission-unification-wildcard-2026-07-19.md")

# Ensure parent directory exists
target_file.parent.mkdir(parents=True, exist_ok=True)

# Markdown content (UTF-8 encoded in source file)
content = '''# Spec: 权限体系统一与 `*` 通配符支持

> **Spec ID**: spec-permission-unification-wildcard-2026-07-19
> **创建日期**: 2026-07-19
> **状态**: Draft (待评审)
> **作者**: AI Assistant
> **优先级**: P1 (高)
> **范围**: P1.1 三层权限体系统一 + P1.6 `*` 通配符支持 + 6.3.11 Owner 机制统一

---

## 1. 背景与目标

### 1.1 研究背景

本 Spec 整合以下研究与 TODO 文档：

1. **WILDCARD_SUPPORT_RESEARCH.md** — Dimension Scope 和 Condition 的 `*` 通配符支持研究
2. **INDUSTRY_PERMISSION_RESEARCH_OVERVIEW.md §6.3.11** — Owner 机制的统一模型
3. **INDUSTRY_PERMISSION_RESEARCH_OVERVIEW.md §6.4** — 9 机制 → 3 层统一模型
4. **PERMISSION_TODOS.md P1.1** — 三层权限体系统一（核心架构债）
5. **PERMISSION_TODOS.md P1.6** — Dimension Scope 和 Condition 支持 `*` 通配符

### 1.2 核心问题

#### 问题 1：`*` 通配符支持不完整

| 层级 | 当前支持 `*` | 需要支持 |
|------|------------|---------|
| 功能权限（PermissionInterceptor） | ✅ 已支持 | `*` 跳过功能权限检查 |
| Dimension Scope（DimensionScopeEngine） | ❌ 不支持 | `scope_mode=\'all\'` 或 `dimension_values=\'*\'` |
| Condition（ConditionEvaluator） | ❌ 不支持 | `condition=\'*\'` 表示无条件匹配 |
| 写路径（WriteScopeInterceptor） | ✅ 功能权限 `*` 跳过 | dimension scope `*` 也需跳过 |

#### 问题 2：Owner 机制分散，读/写路径不对称

Owner 逻辑分散在 3 个模块：
- owner_chain_interceptor.py（写路径）
- chain_owner_resolver.py（共享）
- data_permission_interceptor.py L859-962（读路径 owner exception）

3 路径校验：直接 owner_id / 沿 HIERARCHY_CHAIN 追 product.owner_id / fallback created_by

#### 问题 3：三层权限体系并存（核心架构债）

当前 3 层权限体系并存：
1. M11 声明式 RLS（rls_rules/*.yaml）
2. DimensionScopeEngine（运行时派生，实际主路径）
3. DataPermissionService（旧表，已为空）

### 1.3 目标

1. 统一 `*` 通配符支持 — 功能权限、Dimension Scope、Condition 三层均支持
2. Owner 机制统一 — 统一到 data_permission_rules 的 rule_type=\'owner\'
3. 三层权限体系统一 — data_permission_rules 表作为 SSOT，PermissionResolver 作为统一 PDP
4. Secure by Default 约束 — `*` 受 visibility scope / org level / field mask / Prohibition 约束

---

## 2. 现有实现深度分析

### 2.1 数据库表结构现状

#### role_dimension_scopes 表（generated_schema.sql L308-315）

```sql
CREATE TABLE IF NOT EXISTS role_dimension_scopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    dimension_code VARCHAR(200) NOT NULL,
    dimension_values TEXT NOT NULL,
    inherit_children INTEGER DEFAULT 1,
    scope_mode VARCHAR(200) DEFAULT \'include\'
)
```

scope_mode 枚举只有 include/exclude，缺少 all。

#### permission_rules 表（generated_schema.sql L263-275）

```sql
CREATE TABLE IF NOT EXISTS permission_rules (
    role_id INTEGER NOT NULL,
    resource_type VARCHAR(200) NOT NULL,
    condition TEXT NOT NULL,
    permission_level VARCHAR(200) NOT NULL DEFAULT \'read\',
    is_denied INTEGER DEFAULT 0,
    inherit_to_children INTEGER DEFAULT 1,
    propagate_to_parents INTEGER DEFAULT 1,
    ...
)
```

没有 rule_type 字段，无法与 role_dimension_scopes 统一。

### 2.2 `*` 通配符使用现状

- permission_interceptor.py L85-88: 功能权限支持 `*`
- write_scope_interceptor.py L343-344: 写路径功能权限 `*` 跳过
- data_permission_interceptor.py L727-736: 数据权限拦截器 `*` 跳过

### 2.3 Condition Evaluator 现状

- 支持操作符: =, !=, <, >, <=, >=, IN, NOT IN, LIKE, STARTS_WITH, CONTAINS
- 未支持 `*` 通配符

### 2.4 Dimension Scope Engine 现状

- expand_dimension_values 只支持 JSON list 格式，不支持 `*`
- HIERARCHY_CHAIN = [\'product\', \'version\', \'domain\', \'sub_domain\']

### 2.5 Owner 机制现状

Owner 逻辑分散在 3 个模块，读/写路径不对称。

### 2.6 Gap 分析矩阵

| 层级 | 当前支持 `*` | Owner 统一 | 三层统一 |
|------|------------|-----------|---------|
| 功能权限 | ✅ | N/A | 需统一到 PDP |
| Dimension Scope | ❌ 需支持 all | N/A | 需统一到 data_permission_rules |
| Condition | ❌ 需支持 `*` | N/A | 需统一到 data_permission_rules |
| Owner | N/A | ❌ 分散在 3 模块 | 需统一到 rule_type=\'owner\' |
| 写路径 | ✅ 功能权限 `*` | ❌ 需统一 | 需委托 PDP |
| 读路径 | ✅ `*` 跳过 | ❌ 需统一 | 需委托 PDP |

---

## 3. 统一模型设计

### 3.1 data_permission_rules 统一表设计

```sql
CREATE TABLE IF NOT EXISTS data_permission_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    rule_type VARCHAR(50) NOT NULL,  -- \'dimension\' | \'condition\' | \'visibility\' | \'owner\'
    resource_type VARCHAR(200),      -- BO 类型
    dimension_code VARCHAR(200),     -- 维度编码（dimension 用）
    condition TEXT,                  -- 条件表达式（支持 \'*\'）
    scope_mode VARCHAR(20) DEFAULT \'include\',  -- \'include\' | \'exclude\' | \'all\'
    permission_level VARCHAR(50) DEFAULT \'read\',
    is_denied INTEGER DEFAULT 0,     -- Prohibition 标记
    inherit_to_children INTEGER DEFAULT 1,
    propagate_to_parents INTEGER DEFAULT 1,
    created_at VARCHAR(200),
    created_by INTEGER,
    updated_at VARCHAR(200)
);
```

### 3.2 `*` 通配符统一语义

| 层级 | `*` 语义 | 实现 |
|------|---------|------|
| 功能权限 | `*` 在 permissions 集合 = 所有功能放行 | user_info_has_perm() 已支持 |
| Dimension Scope | scope_mode=\'all\' 或 dimension_values=\'*\' = 全量维度值 | expand_dimension_values() 查询所有 ID |
| Condition | condition=\'*\' = 无条件匹配（SQL 1=1） | evaluate() 直接返回 True |
| Owner | rule_type=\'owner\' + condition=\'*\' = 所有 owner 可访问 | 等价于 dimension `*` |

### 3.3 Owner 统一模型

rule_type=\'owner\' 的 condition 结构：

```json
{
    "owner_field": "owner_id",
    "fallback_field": "created_by",
    "chain_inheritance": "hierarchy_chain",
    "inherit_to_children": true
}
```

3 路径统一校验：直接 owner_id / fallback created_by / 沿 HIERARCHY_CHAIN 追 product.owner_id

附属资源自动继承：annotation（Composition）自动继承；relationship（Association）不继承。

### 3.4 PermissionResolver 统一 PDP

```python
class PermissionResolver:
    """统一权限决策点（PDP）- 5 维正交检查"""

    def check(self, user, action, resource_type, resource=None, resource_id=None):
        # Layer 1: Action (功能权限)
        # Layer 2: Field (字段级，M8)
        # Layer 3: Row (数据权限: dimension + condition)
        # Layer 4: Owner (owner exception)
        # Layer 5: Org (组织级约束，M11)
        ...
```

---

## 4. 详细方案

### 4.1 Phase 1: `*` 通配符支持（1-2 周）

1. 扩展 role_dimension_scopes.scope_mode 枚举增加 \'all\'
2. DimensionScopeEngine.expand_dimension_values 支持 `*`
3. ConditionEvaluator.evaluate 支持 `*`
4. 写路径拦截器同步支持
5. UI 增加"全部"选项
6. 审计日志记录 `*` 配置

### 4.2 Phase 2: Owner 统一模型（2-3 周）

1. data_permission_rules 增加 rule_type=\'owner\'
2. PermissionResolver 实现 check_owner()
3. 迁移 owner_chain_interceptor 逻辑
4. 附属资源自动继承
5. 统一读/写路径

### 4.3 Phase 3: 三层权限体系统一（3-4 周）

1. 创建 data_permission_rules 表
2. 迁移 role_dimension_scopes 数据
3. 迁移 permission_rules 数据
4. PermissionResolver 作为统一 PDP
5. 废弃旧表

### 4.4 Phase 4: Secure by Default 约束（1 周）

1. `*` 受 visibility scope 约束
2. `*` 受 org level 约束
3. `*` 受 field mask 约束
4. `*` 可被 Prohibition (M10) 覆盖

---

## 5. 数据库迁移

### 5.1 Stage A: 扩展 scope_mode 枚举（更新 schema yaml）
### 5.2 Stage B: 创建 data_permission_rules 表
### 5.3 Stage C: 数据迁移（role_dimension_scopes + permission_rules → data_permission_rules）
### 5.4 Stage D: 应用层切换（拦截器改造为 PEP）
### 5.5 Stage E: 旧表重命名（保留 1 版本周期）
### 5.6 Stage F: 旧表删除（稳定运行后）

回滚方案：每个 Stage 独立可回滚。

---

## 6. API 变更

### 6.1 权限配置 API 支持 `*`

```http
POST /api/v1/roles/{id}/dimension-scopes
{
    "dimension_code": "product",
    "scope_mode": "all",
    "dimension_values": "*"
}
```

### 6.2 权限检查 API 统一入口

```http
POST /api/v1/permissions/check
{
    "user_id": 123,
    "action": "crud_update",
    "resource_type": "product",
    "resource_id": 1
}
```

### 6.3 诊断 API 暴露 `*` 配置

```http
GET /api/v1/_diagnostics/wildcard
```

---

## 7. 测试计划

### 7.1 单元测试
- test_wildcard_dimension_scope.py
- test_wildcard_condition.py
- test_owner_unification.py
- test_permission_resolver.py

### 7.2 集成测试
- 端到端权限检查（5 维正交）
- `*` 配置 + visibility scope 约束
- `*` 配置 + Prohibition 覆盖

### 7.3 回归测试
- 现有功能权限 `*` 不受影响
- 现有 dimension scope 不受影响
- 现有 owner chain 检查不受影响

### 7.4 性能测试
- PermissionResolver 5 层检查 P99 < 5ms
- 1000 并发下 `*` 配置的性能

---

## 8. 实施计划

- Phase 1（1-2 周）: `*` 通配符支持
- Phase 2（2-3 周）: Owner 统一
- Phase 3（3-4 周）: 三层统一
- Phase 4（1 周）: 约束与边界

总工时: 7-10 周

---

## 9. 风险与缓解

### 9.1 `*` 配置错误导致权限泄漏
- 缓解: UI 二次确认、审计日志 severity=\'high\'、4 层 Secure by Default 约束

### 9.2 Owner 迁移期间读/写不一致
- 缓解: 双写、对比结果、稳定 1 周后切换

### 9.3 旧表迁移数据丢失
- 缓解: 迁移前备份、脚本幂等、一致性校验、旧表重命名保留 1 版本

### 9.4 性能回退
- 缓解: 三级缓存、批量预加载、性能基准测试

---

## 10. 验收标准

### 10.1 功能验收
- ✅ `*` 通配符在功能权限、Dimension Scope、Condition 三层均支持
- ✅ Owner 逻辑统一到 data_permission_rules 的 rule_type=\'owner\'
- ✅ data_permission_rules 表作为 SSOT
- ✅ PermissionResolver 作为统一 PDP
- ✅ 4 层 Secure by Default 约束生效

### 10.2 性能验收
- ✅ PermissionResolver 5 层检查 P99 < 5ms
- ✅ `*` 查询所有 ID < 50ms
- ✅ 1000 并发下无性能回退

### 10.3 安全验收
- ✅ `*` 配置触发审计日志
- ✅ `*` 受 4 层约束
- ✅ Prohibition 可覆盖 `*`
- ✅ 无权限泄漏

### 10.4 兼容性验收
- ✅ 现有功能权限 `*` 不受影响
- ✅ 现有 dimension scope（无 `*`）不受影响
- ✅ 现有 owner chain 检查不受影响
- ✅ 旧表迁移后数据一致

---

## 11. 参考

### 11.1 研究文档
- WILDCARD_SUPPORT_RESEARCH.md — `*` 通配符支持研究
- INDUSTRY_PERMISSION_RESEARCH_OVERVIEW.md §6.3.11 — Owner 机制统一模型
- INDUSTRY_PERMISSION_RESEARCH_OVERVIEW.md §6.4 — 9 机制 → 3 层统一模型

### 11.2 相关 Spec
- PERMISSION_TODOS.md P1.1 — 三层权限体系统一
- PERMISSION_TODOS.md P1.6 — Dimension Scope 和 Condition 支持 `*` 通配符
- spec-m11-rls-implementation.md v1.4.0 — M11 RLS 实现

### 11.3 代码文件
- meta/services/dimension_scope_engine.py
- meta/services/condition_evaluator.py
- meta/core/interceptors/permission_interceptor.py
- meta/core/interceptors/data_permission_interceptor.py
- meta/core/interceptors/write_scope_interceptor.py
- meta/core/interceptors/owner_chain_interceptor.py
- meta/services/chain_owner_resolver.py
- meta/schemas/role_dimension_scope.yaml
- meta/schemas/permission_rule.yaml
- meta/schemas/generated_schema.sql

### 11.4 行业参考
- AWS IAM — Resource: "*" / Action: "*" 语义
- SAP CAP — @restrict 声明式权限
- Salesforce — OWD + Profile + Permission Set
- SpiceDB — ReBAC 关系图权限
- Cedar — 策略引擎
- XACML — AnyResource / AnyAction

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-07-19 | AI Assistant | 创建 Spec，整合 P1.1 + P1.6 + 6.3.11 |
'''

# Write with UTF-8 encoding (explicit, no BOM)
target_file.write_text(content, encoding='utf-8')

# Verify by reading back
read_back = target_file.read_text(encoding='utf-8')
if read_back != content:
    print("ERROR: Content mismatch after write!", file=sys.stderr)
    sys.exit(1)

# Print success info
print("=" * 60)
print("File written successfully")
print("=" * 60)
print(f"Path: {target_file}")
print(f"Size: {target_file.stat().st_size} bytes")
print(f"Lines: {len(content.splitlines())}")
print(f"Verification: OK (content matches)")
print()
print("First 5 lines:")
for line in content.splitlines()[:5]:
    print(f"  {line}")
