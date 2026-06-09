## 目录

1. [1. 背景与问题描述](#1-背景与问题描述)
2. [2. 代码结构分析](#2-代码结构分析)
3. [3. 拆分方案设计](#3-拆分方案设计)
4. [4. 逐行实现方案](#4-逐行实现方案)
5. [5. 实施步骤](#5-实施步骤)
6. [6. 测试覆盖](#6-测试覆盖)
7. [7. TBD 列表](#7-tbd-列表)
8. [8. 预期效果](#8-预期效果)

---
# Spec: `get_ui_config()` 方法拆分独立实现文档

> **版本**: v1.0
> **日期**: 2026-05-26
> **状态**: 待确认
> **来源**: FR-P2-001-5（Phase 3 仅剩延迟项）
> **关联**: [spec-phase3-architecture-optimization.md](./spec-phase3-architecture-optimization.md)

---

## 1. 背景与问题描述

### 1.1 现状

`get_ui_config()` 是 `BOFramework` 类中最大的单一方法，位于 [bo_framework.py:L339-L633](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L339-L633)，**约 295 行**。它负责将一个 `MetaObject` 转换为前端可消费的 JSON 配置字典，涵盖字段级别的 UI 属性、关联、动作、规则、授权等所有维度的信息。

### 1.2 为什么是延迟项

Phase 3 执行时，该方法被标记为延迟项，原因如下：

1. **体积大但功能内聚**：295 行集中在一个方法，但逻辑是线性的"逐字段→逐区块"提取
2. **耦合深度极高**：同时依赖 `BOFramework` 实例状态（`_display_name_service`）、全局 `registry`、`MetaObject` 内部字段、`models.py` 中的 5 个 dataclass
3. **拆分不当的后果严重**：这是前端 UI 渲染的核心数据源，任何拆分 bug 都会导致前端白屏
4. **独立分析窗口不足**：在批量执行 Phase 3 其他 9 项时，没有足够时间对该方法做彻底分析

本文档目的：对该方法进行逐行级别的耦合分析，产出可执行的拆分方案。

---

## 2. 代码结构分析

### 2.1 完整方法结构

```
get_ui_config(object_type, view_name) → dict  [~295 行]

Phase A: 缓存查找 (L340-L345, 6行)
 ├── cache_key = "{object_type}:{view_name}"
 ├── registry.get_ui_config(cache_key)  ← 读缓存
 └── if cached → return

Phase B: MetaObject 查找 + 头部信息 (L347-L360, 14行)
 ├── registry.get(object_type)  ← 全局注册表
 ├── config = { object_type, label, table_name, aspects }
 └── ui_view_config 注入

Phase C: 字段循环 (L362-L541, 180行) — 核心 ★
 ├── L365-367: 常量定义 (SYSTEM_FIELDS, DATETIME_TYPES, SENSITIVE_FIELDS)
 │
 ├── for f in meta_obj.fields:  ← 逐字段迭代
 │   ├── D1 (L370-L376): 基础字段信息 (id, name, type, required, unique)
 │   │
 │   ├── D2 (L378-L421): UI 配置双路处理 (dict vs dataclass)
 │   │   └── 40行 — visible/editable/readonly/hidden_* + widget/group/order/width
 │   │
 │   ├── D3 (L423-L426): 系统字段覆盖 (id, created_at, updated_at, ...)
 │   ├── D4 (L428-L433): DateTime 字段覆盖
 │   ├── D5 (L435-L439): 敏感字段隐藏
 │   │
 │   ├── D6 (L441-L498): 语义注解处理 (60行 ★★)
 │   │   ├── dict/dataclass 双路 dispatch
 │   │   ├── business_key, audit_field, immutable, readonly_always
 │   │   ├── parent_key, context_field, mandatory, display_name
 │   │   ├── virtual, search_help_for
 │   │   └── export_visible, import_visible
 │   │
 │   ├── D7 (L500-L503): 计算字段检测
 │   │
 │   ├── D8 (L505-L510): 可见性/可编辑性合成
 │   │
 │   ├── D9 (L512-L522): 枚举值处理（含 boolean → int 转换）
 │   │
 │   └── D10 (L524-L538): 约束 + value_help 注入
 │
 Phase D: 全局约束 (L543-L553, 11行)
 Phase E: 关联列表 (L554-L582, 29行)
 Phase F: 动作列表 (L584-L596, 13行)
 Phase G: 规则列表 (L598-L610, 13行)
 Phase H: 授权 + 导入导出 (L612-L618, 7行)
 Phase I: 显示名称 + 关系显示 + 缓存写入 (L620-L633, 14行)
```

### 2.2 依赖关系图

```
get_ui_config()
    │
    ├── 全局依赖 (无状态)
    │   ├── registry (MetaRegistry)  ← from meta.core.models
    │   │   ├── .get(object_type) → MetaObject
    │   │   ├── .get(target_type) → MetaObject (assoc loop)
    │   │   ├── .get_ui_config(key) → dict | None
    │   │   └── .set_ui_config(key, dict)
    │   │
    │   └── _registry (局部导入 L340)  ← 同一 registry 的别名
    │       ├── .get_ui_config(cache_key)
    │       └── .set_ui_config(cache_key, config)
    │
    ├── 实例依赖 (BOFramework state)
    │   ├── self._make_json_safe(obj)      ← @staticmethod，纯工具
    │   ├── self._value_help_to_dict(vh)   ← 仅依赖 ValueHelpConfig 类
    │   ├── self._display_name_service     ← ★ 重量级依赖
    │   │   ├── ._infer_display_name_field(meta_obj)
    │   │   └── .get_all_field_names(object_type)
    │   └── self._infer_navigation(assoc)  ← @staticmethod, 依赖 MetadataResolver
    │
    ├── MetaObject 内部字段 (getattr 访问 ~25 次)
    │   ├── meta_obj.id, .name, .table_name, .aspects
    │   ├── meta_obj.fields → [MetaField, ...]
    │   ├── meta_obj.ui_view_config
    │   ├── meta_obj.constraints, .associations, .actions, .rules
    │   ├── meta_obj.authorization, .import_export
    │   ├── meta_obj.display_name_field
    │   └── meta_obj.relations → [MetaRelation, ...]
    │
    └── MetaField 内部字段 (getattr 访问 ~18 次/field)
        ├── f.id, f.name, f.field_type, f.required, f.unique
        ├── f.ui (dict | UIAnnotation dataclass)
        ├── f.semantics (dict | SemanticAnnotation dataclass)
        ├── f.storage, f.computed, f.compute_expr
        ├── f.enum_values, f.constraints, f.value_help
        └── f.default
```

### 2.3 耦合热点分析

| 热点 | 位置 | 耦合类型 | 严重度 | 可提取性 |
|------|------|---------|:---:|:---:|
| `ui` 的 dict/dataclass 双路处理 | L390-L421 | 类型分支 | 🔴 高 | ✅ 可独立为 `_extract_field_ui` |
| `semantics` 的 dict/dataclass 双路处理 | L441-L498 | 类型分支 | 🔴 高 | ✅ 可独立为 `_extract_field_semantics` |
| `_display_name_service` 注入 | L620-L624 | 实例状态 | 🟠 中 | ⚠️ 需要依赖注入 |
| `registry` 全局单例 | L347/L565/L577 | 全局状态 | 🟡 低 | 已是全局，无需处理 |
| `_value_help_to_dict` 递归 | L538 | 内部方法 | 🟢 低 | ✅ 可移至独立模块 |
| 字段循环中的 6 阶段覆盖 | L423-L439 | 控制流 | 🟡 低 | ✅ 可提取为 `_apply_field_overrides` |

---

## 3. 拆分方案设计

### 3.1 目标架构

```
meta/core/
├── bo_framework.py              → BOFramework (现有，委托 Facade)
├── ui_config/
│   ├── __init__.py
│   ├── config_builder.py        ← UIConfigBuilder (核心协调器)
│   ├── field_extractor.py       ← FieldExtractor (字段级提取)
│   ├── association_extractor.py ← AssociationExtractor (关联提取)
│   ├── value_help_formatter.py  ← value_help_to_dict (值帮助格式化)
│   └── config_constants.py      ← 常量定义 (SYSTEM_FIELDS 等)
```

### 3.2 模块职责

#### 3.2.1 `config_constants.py` — 零依赖常量

```python
# 当前 L365-L367 的 3 个常量提升到模块级别
SYSTEM_FIELDS = frozenset({'id', 'created_at', 'updated_at', 'created_by', 'updated_by'})
DATETIME_TYPES = frozenset({'datetime', 'timestamp', 'date'})
SENSITIVE_FIELDS = frozenset({'password_hash', 'secret', 'token', 'api_key', 'password', 'pwd'})

# 新增：字段可见性默认值
DEFAULT_VISIBILITY = {
    'visible': True, 'editable': True, 'readonly': False,
    'hidden_in_detail': False, 'hidden_in_form': False, 'hidden_in_list': False,
}
```

**依赖**: 无
**行数**: ~15 行

#### 3.2.2 `field_extractor.py` — 单字段处理

```python
class FieldExtractor:
    """从 MetaField 提取前端 UI 字段配置"""
    
    @staticmethod
    def extract(field) -> dict:
        """主入口：单字段 → 字典"""
    
    @staticmethod
    def _extract_base(field) -> dict:
        """基础信息 (D1)"""
    
    @staticmethod
    def _extract_ui(field, base) -> dict:
        """UI 配置提取 (D2: dict/dataclass 双路)"""
    
    @staticmethod
    def _extract_semantics(field, base) -> dict:
        """语义注解提取 (D6: dict/dataclass 双路)"""
    
    @staticmethod
    def _apply_overrides(base, field_type_str):
        """系统字段/日期/敏感字段覆盖 (D3-D5)"""
```

**依赖**: `MetaField`, `config_constants`
**行数**: ~140 行（拆自当前 L370-L510，消除 ~40 行重复）

#### 3.2.3 `value_help_formatter.py` — 值帮助格式化

```python
def value_help_to_dict(vh) -> dict:
    """将 ValueHelpConfig 对象转为字典 (L766-L845)"""
```

**依赖**: `ValueHelpConfig` (from models)
**行数**: ~80 行（从 `bo_framework.py` 移出）

#### 3.2.4 `association_extractor.py` — 关联提取

```python
class AssociationExtractor:
    """从 MetaObject 提取关联配置"""
    
    @staticmethod
    def extract(meta_obj, registry, infer_navigation_fn) -> list:
        """主入口 (当前 L554-L582)"""
    
    @staticmethod  
    def _enrich_target_display(assoc, registry):
        """注入 target_display_name_field (L565-L568)"""
```

**依赖**: `MetaObject`, `MetaRegistry`
**行数**: ~35 行

#### 3.2.5 `config_builder.py` — 核心协调器

```python
class UIConfigBuilder:
    """UI 配置构建器 — get_ui_config 的新家"""
    
    def __init__(self, display_name_service):
        self._dns = display_name_service
        self._field_extractor = FieldExtractor()
        self._assoc_extractor = AssociationExtractor()
    
    def build(self, object_type, view_name=None) -> dict:
        """主入口 — 取代 get_ui_config"""
```

**依赖**: `FieldExtractor`, `AssociationExtractor`, `DisplayNameService`, `registry`
**行数**: ~80 行（仅协调逻辑）

---

## 4. 逐行实现方案

### 4.1 Step 1: 新建 `ui_config/` 目录（零风险，新增文件）

**新建 5+1 个文件**：

```
meta/core/ui_config/__init__.py
meta/core/ui_config/config_constants.py     (~15 行)
meta/core/ui_config/field_extractor.py      (~140 行)
meta/core/ui_config/value_help_formatter.py (~80 行)
meta/core/ui_config/association_extractor.py (~35 行)
meta/core/ui_config/config_builder.py       (~80 行)
```

### 4.2 Step 2: `config_builder.py` 主入口实现

```python
# meta/core/ui_config/config_builder.py

from meta.core.models import registry as _model_registry
from meta.core.ui_config.config_constants import (
    SYSTEM_FIELDS, DATETIME_TYPES, SENSITIVE_FIELDS,
)
from meta.core.ui_config.field_extractor import FieldExtractor
from meta.core.ui_config.association_extractor import AssociationExtractor
from meta.core.ui_config.value_help_formatter import value_help_to_dict


class UIConfigBuilder:

    def __init__(self, display_name_service):
        self._dns = display_name_service
        self._field_extractor = FieldExtractor()
        self._assoc_extractor = AssociationExtractor()

    def build(self, object_type, view_name=None):
        cache_key = f"{object_type}:{view_name or 'default'}"
        cached = _model_registry.get_ui_config(cache_key)
        if cached is not None:
            return cached

        meta_obj = _model_registry.get(object_type)
        if not meta_obj:
            return {}

        config = {
            'object_type': meta_obj.id,
            'label': meta_obj.name,
            'table_name': getattr(meta_obj, 'table_name', ''),
            'aspects': getattr(meta_obj, 'aspects', []) or [],
        }

        ui_view_config = getattr(meta_obj, 'ui_view_config', None)
        if ui_view_config:
            config['ui_view_config'] = _make_json_safe(ui_view_config)

        fields_info = []
        field_constraints = []

        for f in meta_obj.fields:
            field_info = self._field_extractor.extract(f)

            enum_values = getattr(f, 'enum_values', None)
            if enum_values and len(enum_values) > 0:
                normalized = _make_json_safe(enum_values)
                ft = field_info.get('type', 'string')
                if ft == 'boolean':
                    for opt in normalized:
                        raw = opt.get('value')
                        if isinstance(raw, bool):
                            opt['value'] = 1 if raw else 0
                        elif isinstance(raw, str) and raw.lower() in ('true', 'false'):
                            opt['value'] = 1 if raw.lower() == 'true' else 0
                field_info['enum_values'] = normalized

            constraints = getattr(f, 'constraints', None)
            if constraints:
                field_info['constraints'] = _make_json_safe(constraints)
                for c in constraints:
                    if isinstance(c, dict):
                        field_constraints.append({
                            'field': f.id, 'type': c.get('type'),
                            'params': c.get('params', {}),
                            'message': c.get('message', ''),
                        })

            vh = getattr(f, 'value_help', None)
            if vh:
                field_info['value_help'] = _make_json_safe(value_help_to_dict(vh))

            fields_info.append(field_info)

        config['fields'] = fields_info
        if field_constraints:
            config['fields'] = fields_info
            config['constraints'] = field_constraints

        self._inject_global_constraints(config, meta_obj)
        self._inject_associations(config, meta_obj)
        self._inject_actions(config, meta_obj)
        self._inject_rules(config, meta_obj)
        self._inject_meta(config, meta_obj)
        self._inject_display_names(config, object_type, meta_obj)

        _model_registry.set_ui_config(cache_key, config)
        return config

    def _inject_global_constraints(self, config, meta_obj):
        ...

    def _inject_associations(self, config, meta_obj):
        assoc_list = self._assoc_extractor.extract(
            meta_obj, _model_registry, _infer_navigation)
        if assoc_list:
            config['associations'] = assoc_list

    def _inject_actions(self, config, meta_obj):
        ...

    def _inject_rules(self, config, meta_obj):
        ...

    def _inject_meta(self, config, meta_obj):
        ...

    def _inject_display_names(self, config, object_type, meta_obj):
        dns = self._dns
        config['display_name_field'] = (
            meta_obj.display_name_field or dns._infer_display_name_field(meta_obj)
        )
        config['field_display_names'] = dns.get_all_field_names(object_type)
        relation_displays = {}
        for rel in meta_obj.relations:
            if rel.display_format:
                relation_displays[rel.id] = rel.display_format
        config['relation_displays'] = relation_displays
```

### 4.3 Step 3: `field_extractor.py` 详细实现

```python
# meta/core/ui_config/field_extractor.py

from meta.core.ui_config.config_constants import (
    SYSTEM_FIELDS, DATETIME_TYPES, SENSITIVE_FIELDS, DEFAULT_VISIBILITY,
)


class FieldExtractor:

    def extract(self, field):
        ft = field.field_type.value if (
            hasattr(field, 'field_type') and hasattr(field.field_type, 'value')
        ) else 'string'

        info = {
            'id': field.id,
            'name': field.name,
            'type': ft,
            'required': getattr(field, 'required', False),
            'unique': getattr(field, 'unique', False),
        }

        vis = dict(DEFAULT_VISIBILITY)
        self._extract_ui(field, info, vis)
        self._extract_semantics(field, info, vis)
        self._apply_overrides(field.id, ft, vis)

        if getattr(field, 'computed', False) or getattr(field, 'compute_expr', None):
            vis['readonly'] = True
            vis['editable'] = False
            info['computed'] = True

        info.update(vis)
        return info

    def _extract_ui(self, field, info, vis):
        ui = getattr(field, 'ui', None)
        if not ui:
            return

        if isinstance(ui, dict):
            for key in ('visible', 'editable', 'readonly',
                        'hidden_in_detail', 'hidden_in_form', 'hidden_in_list'):
                if key in ui:
                    vis[key] = ui[key]
            info['ui'] = ui
            for key in ('group', 'order', 'width', 'placeholder', 'hint', 'widget'):
                if key in ui:
                    info[key] = ui[key]
        elif hasattr(ui, 'visible'):
            vis['visible'] = ui.visible
            vis['editable'] = getattr(ui, 'editable', True)
            vis['readonly'] = getattr(ui, 'readonly', False)
            vis['hidden_in_detail'] = getattr(ui, 'hidden_in_detail', False)
            vis['hidden_in_form'] = getattr(ui, 'hidden_in_form', False)
            vis['hidden_in_list'] = getattr(ui, 'hidden_in_list', False)
            info['ui'] = _make_json_safe(ui)
            widget = getattr(ui, 'widget', None)
            if widget:
                info['widget'] = widget

    def _extract_semantics(self, field, info, vis):
        semantics = getattr(field, 'semantics', None)
        if not semantics:
            return

        is_dict = isinstance(semantics, dict)
        sdata = {}

        def _get(key, default=False):
            return semantics.get(key, default) if is_dict else getattr(semantics, key, default)

        mapping = [
            ('business_key',    'business_key',    None),
            ('audit_field',     None,              ('readonly', True, 'editable', False, 'visible', False)),
            ('immutable',       'immutable',        None),
            ('readonly_always', None,               ('readonly', True, 'editable', False)),
            ('parent_key',      'parent_key',       None),
            ('context_field',   'context_field',    None),
            ('mandatory',       'mandatory',        None),
            ('display_name',    'display_name',     None),
            ('virtual',         'virtual',          None),
        ]

        for sem_key, info_key, vis_override in mapping:
            if _get(sem_key):
                sdata[sem_key] = True
                if info_key:
                    info[info_key] = True
                if vis_override:
                    it = iter(vis_override)
                    for k, v in zip(it, it):
                        vis[k] = v

        sh_for = _get('search_help_for', None)
        if sh_for:
            sdata['search_help_for'] = sh_for

        # export_visible / import_visible
        if not is_dict:
            ev = getattr(semantics, 'export_visible', None)
            if ev is not None:
                info['export_visible'] = ev
            iv = getattr(semantics, 'import_visible', None)
            if iv is not None:
                info['import_visible'] = iv
        else:
            if semantics.get('export_visible') is True:
                info['export_visible'] = True
            if semantics.get('import_visible') is False:
                info['import_visible'] = False

        info['semantics'] = sdata

    def _apply_overrides(self, field_id, field_type_str, vis):
        if field_id in SYSTEM_FIELDS:
            vis['readonly'] = True
            vis['editable'] = False
            vis['hidden_in_form'] = True

        if field_type_str in DATETIME_TYPES and field_id in ('created_at', 'updated_at'):
            vis['readonly'] = True
            vis['editable'] = False

        if field_id in SENSITIVE_FIELDS:
            vis['visible'] = False
            vis['hidden_in_detail'] = True
            vis['hidden_in_form'] = True
            vis['hidden_in_list'] = True
```

**关键改进点**：
- `semantics` 的 14 个属性检查从 60 行 if/elif 链变为数据驱动的 `mapping` 表
- dict/dataclass 双路处理统一到 `_get(key, default)` 闭包
- `_apply_overrides` 独立为一个方法，逻辑集中在 12 行

### 4.4 Step 4: 兼容层（Backward-compat Facade）

`bo_framework.py` 的 `get_ui_config` 改为委托：

```python
# bo_framework.py 改造
from meta.core.ui_config.config_builder import UIConfigBuilder
from meta.core.ui_config.value_help_formatter import value_help_to_dict as _value_help_to_dict
from meta.core.ui_config.config_constants import SYSTEM_FIELDS  # 如需内联引用

class BOFramework:
    def __init__(self, data_source=None):
        ...
        self._ui_config_builder = UIConfigBuilder(self._display_name_service)

    def get_ui_config(self, object_type, view_name=None):
        return self._ui_config_builder.build(object_type, view_name)
```

- `_make_json_safe` 和 `_infer_navigation` 保留在 `BOFramework`（被其他方法使用）
- `_value_help_to_dict` 移至 `ui_config/value_help_formatter.py`，`BOFramework` 通过 from-import 保持兼容

---

## 5. 实施步骤

| 步骤 | 内容 | 风险 | 检查点 |
|:---:|------|:---:|------|
| **S1** | 新建 `config_constants.py` | 🟢 零 | `python -c "from meta.core.ui_config.config_constants import SYSTEM_FIELDS"` |
| **S2** | 新建 `value_help_formatter.py`（从 L766-L845 移出） | 🟢 零 | 现有 `ValueHelpConfig` 测试通过 |
| **S3** | 新建 `field_extractor.py` | 🟡 低 | `test_ui_config_enhanced.py` 全部通过 |
| **S4** | 新建 `association_extractor.py`（从 L554-L582 移出） | 🟡 低 | 同上 |
| **S5** | 新建 `config_builder.py`（主协调器） | 🟡 低 | 同上 |
| **S6** | `bo_framework.py` `get_ui_config()` 委托化 | 🟠 中 | 所有 UI config 相关测试 + API 集成测试 |
| **S7** | 清理 `bo_framework.py` 中的旧代码 | 🟢 零 | 删除 L339-L633 + L766-L845 |

### 5.1 回滚策略

- S1-S5：纯新建，无回滚需要
- S6：rollback 为 `bo_framework.py` 的单行 revert
- S7：git revert

---

## 6. 测试覆盖

### 6.1 现有测试（不改动）

| 测试文件 | 覆盖范围 | 用例数 |
|------|------|:---:|
| `test_ui_config_enhanced.py` | user/role/permission UI config 字段/约束/关联 | 8+ |
| `test_navigation.py` | `_infer_navigation` 逻辑 | 多个 |
| `test_bo_framework_display_name.py` | display_name 注入 | 多个 |
| `test_bo_framework_display_name_api.py` | API 层 display_name | 多个 |

### 6.2 新增单元测试

```python
# tests/test_ui_config_extractor.py

class TestFieldExtractor:
    def test_extract_basic_field(self): ...
    def test_extract_ui_dict_path(self): ...
    def test_extract_ui_dataclass_path(self): ...
    def test_extract_semantics_dict_path(self): ...
    def test_extract_semantics_dataclass_path(self): ...
    def test_system_field_overrides(self): ...
    def test_datetime_field_overrides(self): ...
    def test_sensitive_field_overrides(self): ...
    def test_computed_field(self): ...
    def test_enum_values_boolean_conversion(self): ...

class TestAssociationExtractor:
    def test_dict_associations(self): ...
    def test_list_associations(self): ...
    def test_target_display_name_injection(self): ...
```

**目标**：新增 13-15 个粒度测试，确保 `field_extractor.py` 和 `association_extractor.py` 行覆盖 > 95%。

---

## 7. TBD 列表

| ID | 项目 | 当前状态 | 决策 |
|------|------|------|------|
| TBD-UI-1 | `_make_json_safe` 是否移至 `ui_config/` 目录 | `BOFramework` 中还有其他 4 个调用方 | 保留在 BOFramework（static method） |
| TBD-UI-2 | `_infer_navigation` 是否移至 `ui_config/` 目录 | `BOFramework` 中还有独立调用 | 保留在 BOFramework（static method） |
| TBD-UI-3 | 枚举值的 boolean→int 转换是否应放在 `field_extractor` 中 | 当前在 config_builder 主循环 | 可移至 `FieldExtractor._normalize_enum_values()` |
| TBD-UI-4 | `SENSITIVE_FIELDS` 硬编码是否需要 YAML 配置化 | 当前硬编码 7 个字段名 | 后续需求，非本次拆分范围 |

---

## 8. 预期效果

| 指标 | 当前 | 目标 | 说明 |
|------|:---:|:---:|------|
| `get_ui_config()` 行数 | 295 | 6（委托） | L339-L633 → 1 行 `self._ui_config_builder.build(...)` |
| `BOFramework` 类行数 | ~900 | ~650 | -250 行 |
| `ui_config/` 模块行数 | 0 | ~350 | 5 个文件，单一职责 |
| 字段提取可测试性 | 仅集成测试 | 独立单元测试 | 15+ 个新测试 |
| semantics 处理复杂度 | 60行 if/elif | 12行 数据驱动 | mapping 表消除全部分支 |
| 现有测试回归 | — | 0 | 所有现有 UI config 测试不变 |

---

> **文档状态**: 独立详细实现文档，基于逐行代码分析。待确认后可指导 S1-S7 实施。
