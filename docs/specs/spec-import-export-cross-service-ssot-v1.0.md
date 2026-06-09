# Spec: import_export_service 跨服务 SSOT 统一与安全修复

> **版本**: v1.0
> **日期**: 2026-06-08
> **状态**: Draft → Confirmed
> **范围**: import_export_service 与核心 BO 服务的重复逻辑统一 + 安全修复

---

## 1. Background & Objectives

### 1.1 Background

`import_export_service.py`（~4800 行，80+ 方法）与核心 BO 服务（query_service / manage_service / computation_service / cascade_service / EnrichmentEngine）存在大量重复逻辑和漂移：

- **安全风险**：直接 SQL 路径绕过权限/软删除过滤，可能导出用户无权查看或已删除的数据
- **行为不一致**：4 个导出入口使用不同排序机制；value_help 获取方式 3 处不一致；ENUM 验证 2 套实现
- **维护成本**：计算字段收集逻辑完全重复；父链遍历 4+2 处 inline；FK 显示名称 N+1 性能问题

### 1.2 Business Objectives

- 消除数据安全风险（P0：权限/软删除过滤缺失）
- 统一跨服务重复逻辑为 SSOT，降低维护成本和漂移风险
- 提升 FK 显示名称查询性能（N+1 → 批量）

### 1.3 User / Stakeholder Objectives

- AI Coding Agent：测试/调用更可预测，行为一致
- 后端开发者：修改一处逻辑即全局生效，无需同步多处
- 业务用户：导出数据不再包含已删除/无权记录

---

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|:---:|------|
| Business | Yes | 安全合规 + 维护成本降低 |
| User/Stakeholder | Yes | Agent/开发者/业务用户三方受益 |
| Solution | Yes | SSOT 提取 + 安全修复 |
| Functional | Yes | 12 项 FR |
| Nonfunctional | Yes | 性能、安全、可测试性 |
| External Interface | No | 无新增 API |
| Transition | Yes | 调用方迁移 |

---

## 3. Functional Requirements

### FR-001: 直接 SQL 路径添加软删除过滤

- **Description**: 系统必须在 `_query_direct_fk_child`、`_query_association_by_level`、`_query_association_by_version` 的直接 SQL 中加入软删除过滤条件，排除 `is_deleted = 1` 的记录。
- **Acceptance Criteria**:
  - 导出的子对象数据不包含已软删除的记录
  - 当 meta_obj 有 `soft_delete_field` 配置时，SQL 自动加入对应过滤条件
  - 无 soft_delete_field 的对象不受影响
- **Priority**: Must (P0 安全)
- **Type Mapping**: Functional / Solution
- **Source**: 跨服务分析 P0-1
- **Code Locations**:
  - `import_export_service.py:2900-2956` (_query_direct_fk_child)
  - `import_export_service.py:1842-1898` (_query_association_by_level)
  - `import_export_service.py:1918-1934` (_query_association_by_version)

### FR-002: 直接 SQL 路径添加数据权限过滤

- **Description**: 系统必须在直接 SQL 查询路径中加入数据权限过滤，确保导出数据不超出用户权限范围。
- **Acceptance Criteria**:
  - `_query_direct_fk_child` 查询结果受数据权限约束
  - 权限过滤逻辑与 query_service 的 `_apply_data_permission` 一致
  - 无权限配置时行为不变（全量导出）
- **Priority**: Must (P0 安全)
- **Type Mapping**: Functional / Solution
- **Source**: 跨服务分析 P0-1
- **Code Locations**:
  - `import_export_service.py:2900-2956` (_query_direct_fk_child)
  - `import_export_service.py:1842-1898` (_query_association_by_level)

### FR-003: `_find_by_id` 改用 `data_source.find_by_id`

- **Description**: 系统必须将 `_find_by_id`（L4783-4798）中的直接 SQL 改为 `data_source.find_by_id(meta_obj.table_name, record_id)`，与 manage_service 保持一致。
- **Acceptance Criteria**:
  - `_find_by_id` 不再包含手写 SQL
  - 行为与修改前完全一致
- **Priority**: Must (P0 漂移风险)
- **Type Mapping**: Functional / Solution
- **Source**: 跨服务分析 P0-2
- **Code Locations**:
  - `import_export_service.py:4783-4798` (_find_by_id)
  - `manage_service.py:376,411` (find_by_id 对比参照)

### FR-004: 导入验证补充 addability 检查

- **Description**: 系统必须在 `_validate_sheets` 中增加 `manage_service.check_can_add` 检查，避免预览通过但执行时被 addability 拒绝。
- **Acceptance Criteria**:
  - 预览阶段即能发现 addability 不允许新增的记录
  - 错误信息明确提示 addability 规则原因
  - 无 addability 配置的对象行为不变
- **Priority**: Must (P0 正确性)
- **Type Mapping**: Functional / Solution
- **Source**: 跨服务分析 P0-3
- **Code Locations**:
  - `import_export_service.py:3751-4154` (_validate_sheets)
  - `manage_service.py:310-334` (create 中的 addability 检查)

### FR-005: 计算字段收集逻辑提取为 computation_service SSOT

- **Description**: 系统必须将 `import_export_service._compute_list_computed_fields_for_export`（L1490-1512）和 `query_service._compute_list_computed_fields`（L559-583）的重复逻辑提取到 `computation_service.collect_computed_columns(meta_obj)` 静态方法。
- **Acceptance Criteria**:
  - `computation_service` 新增 `collect_computed_columns(meta_obj) -> List[Dict]` 方法
  - `import_export_service` 和 `query_service` 均调用此方法
  - 原有两处方法标记 deprecated 或删除
  - 行为与修改前完全一致
- **Priority**: Should (P1)
- **Type Mapping**: Functional / Solution
- **Source**: 跨服务分析 P1-4
- **Code Locations**:
  - `import_export_service.py:1490-1512` (_compute_list_computed_fields_for_export)
  - `query_service.py:559-583` (_compute_list_computed_fields)
  - `computation_service.py` (新增方法)

### FR-006: ENUM 解析提取为 `meta/core/enum_resolver.py` SSOT

- **Description**: 系统必须将 ENUM 值解析逻辑统一到 `meta/core/enum_resolver.py` 模块，提供 `get_enum_map(meta_field, data_source) -> Dict[str, str]` 和 `validate_enum_value(enum_type_id, code, data_source) -> bool` 两个核心函数。
- **Acceptance Criteria**:
  - 新模块 `meta/core/enum_resolver.py` 包含 `get_enum_map`、`validate_enum_value`、`get_enum_type_id`
  - `import_export_service._get_enum_value_map_from_value_help` 改为调用 `enum_resolver.get_enum_map`
  - `import_export_service._validate_enum_value` 改为调用 `enum_resolver.validate_enum_value`
  - `import_export_service._get_enum_type_id_from_value_help` 改为调用 `enum_resolver.get_enum_type_id`
  - 行为与修改前完全一致
- **Priority**: Should (P1)
- **Type Mapping**: Functional / Solution
- **Source**: 跨服务分析 P1-5
- **Code Locations**:
  - `import_export_service.py:356-377` (_get_enum_value_map_from_value_help)
  - `import_export_service.py:379-388` (_get_enum_type_id_from_value_help)
  - `import_export_service.py:4156-4176` (_validate_enum_value)

### FR-007: value_help 获取提取为 `meta/core/value_help_accessor.py` SSOT

- **Description**: 系统必须将 value_help 获取逻辑统一到 `meta/core/value_help_accessor.py` 模块，提供 `get_value_help(meta_field) -> Optional[ValueHelpConfig]` 函数，统一 `field.value_help` → `field.ui.value_help` 的 fallback 链。
- **Acceptance Criteria**:
  - 新模块 `meta/core/value_help_accessor.py` 包含 `get_value_help` 函数
  - `import_export_service._get_value_help` 改为调用 `value_help_accessor.get_value_help`
  - `manage_service._validate_value_helps` 改为调用 `value_help_accessor.get_value_help`
  - `EnrichmentEngine.enrich_fk_display_names` 改为调用 `value_help_accessor.get_value_help`
  - 三处行为统一为：先 `field.value_help`，fallback `field.ui.value_help`
- **Priority**: Should (P1)
- **Type Mapping**: Functional / Solution
- **Source**: 跨服务分析 P1-6
- **Code Locations**:
  - `import_export_service.py:2598-2613` (_get_value_help)
  - `manage_service.py:154-180` (_validate_value_helps)
  - `enrichment_engine.py:449-453` (inline value_help 获取)

### FR-008: 层级排序统一到 cascade_service

- **Description**: 系统必须将 `_sort_by_hierarchy`（L1698-1734）移入 `CascadeService`，替代 `get_type_order`，支持子集排序 + child_sections 依赖。4 个导出/导入入口统一调用 cascade_service。
- **Acceptance Criteria**:
  - `CascadeService` 新增 `sort_by_hierarchy(object_types: List[str]) -> List[str]` 类方法
  - `import_export_service._sort_by_hierarchy` 标记 deprecated，委托 cascade_service
  - `export_template` / `export_selected_types` 改用 `CascadeService.sort_by_hierarchy`
  - `export_cascade` / `import_cascade` 改用 `CascadeService.sort_by_hierarchy`
  - Sheet 顺序从 YAML 声明顺序变为拓扑排序顺序（用户已确认可接受）
- **Priority**: Should (P1)
- **Type Mapping**: Functional / Solution
- **Source**: 跨服务分析 P1-7
- **Code Locations**:
  - `import_export_service.py:1698-1734` (_sort_by_hierarchy)
  - `import_export_service.py:503` (export_template 用 get_type_order)
  - `import_export_service.py:694` (export_selected_types 用 get_type_order)
  - `import_export_service.py:1093` (export_cascade 用 _sort_by_hierarchy)
  - `import_export_service.py:3646` (import_cascade 用 _sort_by_hierarchy)
  - `cascade_service.py:95-97` (get_type_order)

### FR-009: 父链遍历统一使用 `_iter_parent_chain`

- **Description**: 系统必须将 `_build_parent_fk_columns`（L1525）和 `_get_export_headers`（L3258）中的 inline while 循环改为使用已有的 `_iter_parent_chain` helper。
- **Acceptance Criteria**:
  - `_build_parent_fk_columns` 使用 `_iter_parent_chain` 遍历父链
  - `_get_export_headers` 使用 `_iter_parent_chain` 遍历父链
  - 行为与修改前完全一致
- **Priority**: Should (P1)
- **Type Mapping**: Functional / Solution
- **Source**: 跨服务分析 P1-8
- **Code Locations**:
  - `import_export_service.py:1525` (_build_parent_fk_columns inline while)
  - `import_export_service.py:3258` (_get_export_headers inline while)
  - `import_export_service.py:2741+` (_iter_parent_chain SSOT helper)

### FR-010: FK 显示名称批量查询优化

- **Description**: 系统必须将 `_build_bo_display_maps`（L2523-2570）和 `_get_bo_display_map_from_value_help`（L390-428）的逐条 `BOEngine.get_record(rid)` 查询改为批量 SQL `WHERE id IN (...)`，与 EnrichmentEngine 对齐。
- **Acceptance Criteria**:
  - `_build_bo_display_maps` 使用批量 SQL 查询，不再逐条调用 BOEngine
  - `_get_bo_display_map_from_value_help` 使用批量 SQL 查询
  - 缺失记录的处理方式：跳过（与当前逐条查询时 `except: continue` 行为一致）
  - 性能提升：N 条 FK 值从 N 次 SQL 降为 1 次
- **Priority**: Should (P1)
- **Type Mapping**: Functional / Solution / Nonfunctional (性能)
- **Source**: 跨服务分析 P1-9
- **Code Locations**:
  - `import_export_service.py:2523-2570` (_build_bo_display_maps 逐条)
  - `import_export_service.py:390-428` (_get_bo_display_map_from_value_help 逐条)
  - `enrichment_engine.py:481-484` (批量 SQL 参照)

### FR-011: `MetaObject.get_business_key_fields` 组合键支持

- **Description**: 系统必须在 `MetaObject` 上新增 `get_business_key_fields() -> List[MetaField]` 方法，返回所有非 virtual 的 business_key 字段。原 `get_business_key_field()` 标记 deprecated。
- **Acceptance Criteria**:
  - `MetaObject` 新增 `get_business_key_fields()` 方法
  - `import_export_service._get_business_key_fields` 改为调用 `meta_obj.get_business_key_fields()`
  - 原 `get_business_key_field()` 标记 deprecated 但保留
- **Priority**: Could (P2)
- **Type Mapping**: Functional / Solution
- **Source**: 跨服务分析 P2-10
- **Code Locations**:
  - `models.py:1043-1048` (get_business_key_field 单字段)
  - `import_export_service.py:4642-4654` (_get_business_key_fields 多字段)

### FR-012: 直接 SQL 路径添加默认排序

- **Description**: 系统必须在 `_query_direct_fk_child` 和 `_query_association_by_level` 的直接 SQL 中添加 `ORDER BY c.id ASC` 默认排序，确保导出数据顺序确定。
- **Acceptance Criteria**:
  - `_query_direct_fk_child` SQL 末尾包含 `ORDER BY c.id ASC`
  - `_query_association_by_level` SQL 末尾包含 `ORDER BY r.id ASC`
  - 导出数据顺序稳定可预测
- **Priority**: Could (P2)
- **Type Mapping**: Functional
- **Source**: 跨服务分析 P2
- **Code Locations**:
  - `import_export_service.py:2926-2934` (_query_direct_fk_child SQL)
  - `import_export_service.py:1859-1863` (_query_association_by_level SQL)

---

## 4. Nonfunctional Requirements

### NFR-001: 安全性

- **Description**: 导出数据不得包含用户无权查看或已软删除的记录
- **Measurement**: 以受限用户导出，验证结果不含越权/已删除记录
- **Priority**: Must
- **Source**: FR-001, FR-002

### NFR-002: 性能

- **Description**: FK 显示名称查询从 N+1 优化为批量，单次导出中 N 条 FK 值仅 1 次 SQL
- **Measurement**: 对比优化前后导出耗时，FK 密集型场景应有可测量改善
- **Priority**: Should
- **Source**: FR-010

### NFR-003: 行为一致性

- **Description**: SSOT 提取后所有调用方行为与修改前完全一致（除用户已确认的排序变化 FR-008）
- **Measurement**: 每项 FR 的回归测试通过
- **Priority**: Must
- **Source**: 所有 FR

### NFR-004: 可测试性

- **Description**: 新增 SSOT 模块（enum_resolver / value_help_accessor / computation_service.collect_computed_columns / cascade_service.sort_by_hierarchy）必须有独立单元测试
- **Measurement**: 每个新模块/方法至少 3 个测试用例（正常/边界/异常）
- **Priority**: Should
- **Source**: 所有 P1 FR

---

## 5. External Interface Requirements

无新增外部接口。所有变更为内部重构。

---

## 6. Transition Requirements

### TR-001: 调用方迁移

- **Description**: 3 个外部调用方需迁移到新 SSOT 模块：
  1. `manage_service._validate_value_helps` → `value_help_accessor.get_value_help`
  2. `EnrichmentEngine.enrich_fk_display_names` → `value_help_accessor.get_value_help`
  3. `query_service._compute_list_computed_fields` → `computation_service.collect_computed_columns`
- **Strategy**: 逐个迁移，每个迁移后运行回归测试确认
- **Rollback Plan**: 保留原方法标记 deprecated，回滚时恢复调用即可
- **Source**: FR-005, FR-007

### TR-002: 排序行为变更

- **Description**: `export_template` / `export_selected_types` 的 Sheet 顺序从 YAML 声明顺序变为拓扑排序顺序
- **Strategy**: 用户已确认可接受，无需额外迁移
- **Rollback Plan**: 保留 `get_type_order` 方法，紧急回滚时恢复调用
- **Source**: FR-008

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- 新增模块放在 `meta/core/` 下（纯工具函数，无服务依赖）
- `enum_resolver` 和 `value_help_accessor` 需要 `data_source` 参数（不能模块级持有）
- `cascade_service.sort_by_hierarchy` 为类方法，不依赖实例状态
- 所有修改必须通过 `python d:\filework\test.py` 入口验证

### 7.2 Business Constraints

- 导出数据不再包含已软删除记录（用户已确认符合业务预期）
- Sheet 顺序变更（用户已确认可接受）

### 7.3 Assumptions

- `data_source.find_by_id` 接口签名与 `_find_by_id` 当前行为兼容 — Source: Verified
- `EnrichmentEngine` 改用 `value_help_accessor.get_value_help` 后，fallback 到 `field.ui.value_help` 不会引入新问题 — Source: Assumed（需测试验证）
- `manage_service.check_can_add` 可在 `_validate_sheets` 上下文中调用 — Source: Assumed（需验证参数兼容性）

---

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|------|-----------|--------|------|
| FR-001 | 直接 SQL 软删除过滤 | Must | 安全：导出已删除数据 |
| FR-002 | 直接 SQL 权限过滤 | Must | 安全：导出越权数据 |
| FR-003 | `_find_by_id` 改用 data_source | Must | SQL 漂移风险 |
| FR-004 | 导入验证 addability 检查 | Must | 正确性：预览/执行不一致 |
| FR-005 | 计算字段收集 SSOT | Should | 重复消除 |
| FR-006 | ENUM 解析 SSOT | Should | 重复消除 |
| FR-007 | value_help 获取 SSOT | Should | 不一致修复 |
| FR-008 | 层级排序 SSOT | Should | 重复消除 + 行为统一 |
| FR-009 | 父链遍历统一 | Should | 重复消除 |
| FR-010 | FK 显示批量查询 | Should | 性能 N+1 |
| FR-011 | business_key 组合键 | Could | 设计缺陷修复 |
| FR-012 | 直接 SQL 默认排序 | Could | 数据质量 |

**Suggested Milestones**:
- **Milestone 1 (P0)**: FR-001 ~ FR-004，安全/正确性修复
- **Milestone 2 (P1)**: FR-005 ~ FR-010，SSOT 提取 + 性能优化
- **Milestone 3 (P2)**: FR-011 ~ FR-012，设计改进

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- **Current Architecture**: import_export_service 独立实现查询/验证/排序/ENUM/FK 逻辑，与核心 BO 服务存在 12 处重复/漂移
- **Current Issues**:
  1. 直接 SQL 路径绕过权限/软删除（安全）
  2. 4 处重复计算字段收集逻辑
  3. 3 处不一致 value_help 获取
  4. 2 套排序机制并存
  5. FK 显示名称 N+1 性能问题
  6. 父链遍历 4+2 处 inline
- **Relevant Code Paths**:
  - `import_export_service.py:2900-2956` (_query_direct_fk_child)
  - `import_export_service.py:1842-1934` (_query_association_*)
  - `import_export_service.py:1490-1512` (_compute_list_computed_fields_for_export)
  - `import_export_service.py:356-377` (_get_enum_value_map_from_value_help)
  - `import_export_service.py:2598-2613` (_get_value_help)
  - `import_export_service.py:2523-2570` (_build_bo_display_maps)
  - `import_export_service.py:1698-1734` (_sort_by_hierarchy)
  - `import_export_service.py:4783-4798` (_find_by_id)
  - `query_service.py:559-583` (_compute_list_computed_fields)
  - `cascade_service.py:95-97` (get_type_order)
  - `enrichment_engine.py:449-453` (value_help 获取)
  - `manage_service.py:154-180` (_validate_value_helps)

### 9.2 Target State

- **Proposed Architecture**:
  - 新增 2 个核心工具模块：`meta/core/enum_resolver.py`、`meta/core/value_help_accessor.py`
  - 增强 2 个现有服务：`computation_service` 新增 `collect_computed_columns`、`cascade_service` 新增 `sort_by_hierarchy`
  - 增强 1 个模型：`MetaObject` 新增 `get_business_key_fields`
  - import_export_service 的直接 SQL 路径补全安全过滤 + 默认排序
  - 所有调用方统一使用 SSOT

- **Key Changes**:
  1. 安全修复：3 个直接 SQL 方法加软删除/权限过滤
  2. SSOT 提取：6 处重复逻辑统一
  3. 性能优化：FK 显示名称 N+1 → 批量
  4. 模型增强：组合键支持

### 9.3 Detailed Design

#### 9.3.1 新增模块：`meta/core/enum_resolver.py`

```python
"""ENUM 值解析 SSOT

统一 import_export_service / enum_api / annotation_routes_api 中的枚举查询逻辑。
依赖：data_source（通过参数传入，不持有实例状态）
"""
from typing import Dict, Optional, Any

def get_enum_map(meta_field, data_source) -> Optional[Dict[str, str]]:
    """获取字段的枚举映射 {code: name}

    优先级：field.enum_values（静态） → value_help.source.enum_type_id（DB 查询）
    """
    # 1. 先查静态 enum_values
    static_enum = getattr(meta_field, 'enum_values', None)
    if static_enum:
        return {v.get('value'): v.get('label', v.get('name', ''))
                for v in static_enum if isinstance(v, dict)}

    # 2. 再查 value_help → DB
    from meta.core.value_help_accessor import get_value_help
    vh = get_value_help(meta_field)
    if not vh:
        return None
    source = getattr(vh, 'source', None)
    if not source or getattr(source, 'type', None) != 'enum':
        return None
    enum_type_id = getattr(source, 'enum_type_id', None)
    if not enum_type_id:
        return None

    try:
        sql = "SELECT code, name FROM enum_values WHERE enum_type_id = ? AND is_active = 1 ORDER BY sort_order"
        cursor = data_source.execute(sql, [enum_type_id])
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows} if rows else None
    except Exception:
        return None

def get_enum_type_id(meta_field) -> Optional[str]:
    """获取字段的 enum_type_id"""
    from meta.core.value_help_accessor import get_value_help
    vh = get_value_help(meta_field)
    if not vh:
        return None
    source = getattr(vh, 'source', None)
    if not source or getattr(source, 'type', None) != 'enum':
        return None
    return getattr(source, 'enum_type_id', None)

def validate_enum_value(enum_type_id: str, code: str, data_source) -> bool:
    """验证枚举值是否有效"""
    try:
        sql = "SELECT COUNT(*) FROM enum_values WHERE enum_type_id = ? AND code = ? AND is_active = 1"
        cursor = data_source.execute(sql, [enum_type_id, code])
        result = cursor.fetchone()
        return result[0] > 0 if result else False
    except Exception:
        return True  # 验证失败时默认通过（与现有行为一致）
```

#### 9.3.2 新增模块：`meta/core/value_help_accessor.py`

```python
"""value_help 获取 SSOT

统一 import_export_service / manage_service / EnrichmentEngine 中的 value_help 获取逻辑。
优先级：field.value_help → field.ui.value_help（fallback）
"""

def get_value_help(meta_field):
    """统一获取字段的 value_help 配置

    优先级：
    1. field.value_help（字段级定义）
    2. field.ui.value_help（UI 级定义，fallback）

    Returns:
        Optional[ValueHelpConfig]
    """
    vh = getattr(meta_field, 'value_help', None)
    if not vh:
        ui = getattr(meta_field, 'ui', None)
        if ui:
            vh = getattr(ui, 'value_help', None)
    return vh
```

#### 9.3.3 增强 `computation_service`：`collect_computed_columns`

在 `computation_service.py` 新增静态方法：

```python
@staticmethod
def collect_computed_columns(meta_obj) -> list:
    """SSOT: 从 ui_view_config + rules 收集计算列配置

    统一 import_export_service._compute_list_computed_fields_for_export
    和 query_service._compute_list_computed_fields 的重复逻辑。
    """
    ui_computed_columns = []
    if hasattr(meta_obj, 'ui_view_config') and meta_obj.ui_view_config:
        list_config = getattr(meta_obj.ui_view_config, 'list', None)
        if list_config and hasattr(list_config, 'columns'):
            ui_computed_columns = [
                {'key': col.key, 'computation': getattr(col, 'computation', None)}
                for col in list_config.columns
                if getattr(col, 'computed', False) and getattr(col, 'computation', None)
            ]

    rule_computed = computation_service.get_computed_columns_from_rules(meta_obj.id)
    return computation_service.merge_computed_columns(ui_computed_columns, rule_computed)
```

调用方变更：
- `import_export_service._compute_list_computed_fields_for_export` → 调用 `computation_service.collect_computed_columns(meta_obj)` + `computation_service.compute_batch(...)`
- `query_service._compute_list_computed_fields` → 同上

#### 9.3.4 增强 `cascade_service`：`sort_by_hierarchy`

将 `_sort_by_hierarchy`（L1698-1734）移入 `CascadeService`：

```python
@classmethod
def sort_by_hierarchy(cls, object_types: List[str]) -> List[str]:
    """按层级拓扑排序（父对象在前，子对象在后）

    排序规则：
    1. parent_object 关系：子对象依赖父对象
    2. child_sections 关系：子对象依赖其所有父对象

    替代 get_type_order()，支持任意类型子集排序。
    """
    from meta.core.models import registry

    graph = {ot: [] for ot in object_types}

    for ot in object_types:
        obj = registry.get(ot)
        if obj and obj.parent_object and obj.parent_object in object_types:
            graph[ot] = [obj.parent_object]

    # child_sections 依赖
    for ot in object_types:
        obj = registry.get(ot)
        if obj and hasattr(obj, 'child_sections') and obj.child_sections:
            for section in obj.child_sections:
                section_type = getattr(section, 'object_type', None)
                if section_type and section_type in object_types and section_type != ot:
                    if ot not in graph[section_type]:
                        graph[section_type].append(ot)

    result = []
    visited = set()

    def visit(node):
        if node in visited:
            return
        visited.add(node)
        for parent in graph.get(node, []):
            visit(parent)
        result.append(node)

    for ot in object_types:
        visit(ot)

    return result
```

调用方变更：
- `import_export_service._sort_by_hierarchy` → 委托 `CascadeService.sort_by_hierarchy`
- `export_template` / `export_selected_types` 中 `get_type_order()` → `CascadeService.sort_by_hierarchy(all_types)`

#### 9.3.5 安全修复：直接 SQL 路径

**`_query_direct_fk_child`** 修改：

```python
# Before:
sql = (f"SELECT c.* FROM {child_table} c "
       f"INNER JOIN {parent_table} p ON c.{parent_fk_field} = p.id "
       f"WHERE p.version_id = ?")

# After:
soft_delete_filter = ""
if any(f.id == 'is_deleted' for f in parent_meta.fields):
    soft_delete_filter = " AND (p.is_deleted IS NULL OR p.is_deleted = 0)"

sql = (f"SELECT c.* FROM {child_table} c "
       f"INNER JOIN {parent_table} p ON c.{parent_fk_field} = p.id "
       f"WHERE p.version_id = ?{soft_delete_filter} "
       f"ORDER BY c.id ASC")
```

同理修改 `_query_association_by_level` 和 `_query_association_by_version`。

#### 9.3.6 `_find_by_id` 修复

```python
# Before:
sql = "SELECT * FROM {0} WHERE id = ?".format(table_name)
cursor = self.data_source.execute(sql, (record_id,))

# After:
return self.data_source.find_by_id(table_name, record_id)
```

#### 9.3.7 FK 显示名称批量查询

**`_build_bo_display_maps`** 修改：

```python
# Before: 逐条 BOEngine.get_record(rid)
for rid in record_ids:
    rec = engine.get_record(rid)
    display_map[rid] = str(rec.get(vh_info['display_field'], ''))

# After: 批量 SQL
target_table = target_meta.table_name or vh_info['target_bo'] + 's'
placeholders = ','.join(['?'] * len(record_ids))
sql = f"SELECT id, {vh_info['display_field']} FROM {target_table} WHERE id IN ({placeholders})"
cursor = self.data_source.execute(sql, list(record_ids))
for row in cursor.fetchall():
    display_map[row[0]] = str(row[1]) if row[1] else ''
```

同理修改 `_get_bo_display_map_from_value_help`。

#### 9.3.8 `MetaObject.get_business_key_fields`

```python
def get_business_key_fields(self) -> List['MetaField']:
    """获取所有业务键字段（支持组合键）"""
    return [
        f for f in self.fields
        if getattr(f.semantics, 'business_key', False)
        and f.storage.value != 'virtual'
        and not getattr(f.semantics, 'virtual', False)
    ]
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| A: 直接 SQL 加过滤条件 | 最小改动，不影响现有架构 | 权限过滤逻辑需手动同步 query_service | **Selected** (P0 快速修复) |
| B: 直接 SQL 路径改为 query_service.search() | 自动获得权限/软删除/排序/计算字段 | 需构造 SearchRequest，association 查询无法表达 | Rejected (association 路径太特殊) |
| C: enum_resolver 放在 meta/services/ | 与其他服务同级 | 依赖方向不清晰（core 更合适） | Rejected |
| D: 保留 get_type_order 不动 | 零风险 | 4 个入口行为不一致 | Rejected (用户已确认可接受变化) |

### 9.5 Implementation & Migration Plan

**Implementation Order**:

1. **Milestone 1 (P0)**: FR-001 ~ FR-004
   - Step 1: `_query_direct_fk_child` 加软删除过滤 + 默认排序
   - Step 2: `_query_association_by_level` / `_query_association_by_version` 同上
   - Step 3: `_find_by_id` 改用 `data_source.find_by_id`
   - Step 4: `_validate_sheets` 增加 addability 检查
   - Step 5: 回归测试

2. **Milestone 2 (P1)**: FR-005 ~ FR-010
   - Step 1: 创建 `meta/core/value_help_accessor.py`（被其他 SSOT 依赖）
   - Step 2: 创建 `meta/core/enum_resolver.py`（依赖 value_help_accessor）
   - Step 3: `computation_service.collect_computed_columns` + 迁移调用方
   - Step 4: `cascade_service.sort_by_hierarchy` + 迁移调用方
   - Step 5: 父链遍历统一用 `_iter_parent_chain`
   - Step 6: FK 显示名称批量查询优化
   - Step 7: 回归测试

3. **Milestone 3 (P2)**: FR-011 ~ FR-012
   - Step 1: `MetaObject.get_business_key_fields`
   - Step 2: 直接 SQL 默认排序（如 Milestone 1 未覆盖）

**Risk Mitigation**:
- 每步修改后立即运行 `python d:\filework\test.py --single <test>` 验证
- 保留原方法标记 deprecated，不立即删除
- EnrichmentEngine 改用 value_help_accessor 后可能发现之前未覆盖的 value_help 场景 → 增加单元测试覆盖

**Testing Strategy**:
- Unit tests: 每个新模块/方法至少 3 个用例（正常/边界/异常）
- Integration tests: `python d:\filework\test.py --failed` 回归
- E2E tests: 导出级联 → 导入级联 完整流程验证

**Rollback Plan**:
- 每步 git commit，回滚到上一步即可
- deprecated 方法保留，紧急时恢复调用

---

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|------|------|-------------------|-----------|
| TBD-1 | `_validate_sheets` 调用 `check_can_add` 的参数兼容性 | 需确认 manage_service.check_can_add 的签名和调用方式 | 实现时读取 manage_service 源码确认 |
| TBD-2 | 权限过滤在直接 SQL 中的实现方式 | 需确认 `_apply_data_permission` 返回的过滤条件能否转为 SQL WHERE | 实现时读取 query_service 源码确认 |
| TBD-3 | `cascade_service.sort_by_hierarchy` 中 child_sections 的获取方式 | 需确认 registry 中 MetaObject 的 child_sections 属性结构 | 实现时读取 models.py 确认 |
