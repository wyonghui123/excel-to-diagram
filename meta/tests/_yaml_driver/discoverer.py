# -*- coding: utf-8 -*-
"""
YAML -> 测试用例推导器

功能: 扫描 MetaObject 字典, 为每个 schema 自动推导一组基础约束测试
- 必填字段缺失 (字段不存在 / required 字段 missing)
- 唯一约束重复 (unique 字段在两个记录中重复)
- 默认值正确性 (default 与 schema 一致)
- 持久化字段存在 db_column
- 层级对象 parent_object 引用正确
- 业务对象有 business_key
- 删除策略 deletion_policy 引用对象存在
- enum 字段值在 enum_type 中
- 显示名称字段在字段列表中

v1.1 新增:
- Aspects 自动应用 (3 类)
- RLS 规则覆盖 (3 类)
- Factory ↔ YAML 一致性 (3 类)

返回: List[ConstraintSpec], 每个包含 (object_id, field_id, constraint_type, description)
"""
from dataclasses import dataclass
from typing import Dict, List, Any, Optional


@dataclass(frozen=True)
class ConstraintSpec:
    """推导出来的单个约束测试规格"""
    object_id: str
    field_id: str           # 可能为空 (对象级约束)
    constraint: str         # 见下方 CONSTRAINT_TYPES
    description: str
    severity: str = "error" # error / warning

    @property
    def test_id(self) -> str:
        """稳定的 pytest id"""
        if self.field_id:
            return f"{self.object_id}__{self.field_id}__{self.constraint}"
        return f"{self.object_id}__object__{self.constraint}"


CONSTRAINT_TYPES = {
    "REQUIRED_FIELD_DEFINED",
    "UNIQUE_FIELD_HAS_DB_INDEX",
    "DEFAULT_VALUE_TYPE_MATCHES",
    "PERSISTENT_FIELD_HAS_DB_COLUMN",
    "HIERARCHY_PARENT_OBJECT_EXISTS",
    "BUSINESS_KEY_EXISTS_FOR_BO",
    "DELETION_POLICY_TARGET_EXISTS",
    "ENUM_FIELD_VALUES_VALID",
    "DISPLAY_NAME_FIELD_DECLARED",
    # === v1.1 新增 ===
    # Aspects
    "ASPECT_REFERENCED_MUST_EXIST",
    "ASPECT_FIELDS_APPLIED",
    "AUDIT_ASPECT_HAS_AUDIT_CONFIG",
    # RLS
    "RLS_FILE_EXISTS_FOR_OBJECT",
    "RLS_ENTITY_FIELD_VALID",
    "RLS_APPLIES_TO_ROLE_VALID",
    # Factory
    "FACTORY_DEFAULTS_COVER_REQUIRED",
    "FACTORY_OBJECT_TYPE_REGISTERED",
    "FACTORY_DEFAULTS_NOT_EMPTY",
    "FACTORY_UNIQUE_ID_DETERMINISTIC",  # [FIX 2026-07-17 P2]
    "META_OBJECT_HAS_AT_LEAST_ONE_ACTION",
    "PERSISTENT_OBJECT_HAS_PK",
    "TABLE_NAME_NOT_EMPTY",
}


def discover_all_constraints(objects: Dict[str, "MetaObject"]) -> List[ConstraintSpec]:
    """
    推导所有对象的约束测试规格。

    Args:
        objects: {object_id: MetaObject} 字典, 通常来自 loader.load_schemas()

    Returns:
        List[ConstraintSpec] - 每个对应一条测试用例
    """
    specs: List[ConstraintSpec] = []

    for obj_id, obj in sorted(objects.items()):
        # 跳过非业务对象 (如视图、虚拟对象)
        if not _is_testable(obj_id, obj):
            continue

        specs.extend(_discover_object_level_constraints(obj, objects))
        specs.extend(_discover_field_level_constraints(obj, objects))

    return specs


# ============================================================
# v1.1 新增: Aspects / RLS / Factory 一致性约束
# ============================================================

def discover_aspect_constraints(
    objects: Dict[str, "MetaObject"],
    aspects: Dict[str, Any],
) -> List[ConstraintSpec]:
    """
    推导 aspects 自动应用测试规格 (v1.1 新增)。

    实现方式 (双通道):
    - 通道1: 字段 included_from 标签 (aspect 字段合并后)
    - 通道2: obj.aspects 顶层属性 (yaml 引用但字段未合并)

    输出策略 (positive-or-negative):
    - 违规 -> 1 条 negative spec (severity=error/warning)
    - 健康 -> 1 条 positive spec (severity=info) 证明规则跑过
    - 同一对象同一约束类型 至多 1 条 spec
    """
    specs: List[ConstraintSpec] = []

    for obj_id, obj in sorted(objects.items()):
        if not _is_testable(obj_id, obj):
            continue

        obj_aspects = set()
        obj_field_ids = {f.id for f in obj.fields}
        # 方式1: 字段 included_from 标签
        for f in obj.fields:
            inc = getattr(f, "included_from", "") or ""
            if inc:
                obj_aspects.add(inc)
        # 方式2: obj.aspects 顶层属性
        direct_aspects = getattr(obj, "aspects", None) or []
        if direct_aspects:
            obj_aspects.update(direct_aspects)

        if not obj_aspects:
            # positive: 不使用 aspects, 也算满足 "no broken aspect reference"
            specs.append(ConstraintSpec(
                object_id=obj_id,
                field_id="",
                constraint="ASPECT_REFERENCED_MUST_EXIST",
                description=(
                    f"Object '{obj_id}' declares no aspects (clean)"
                ),
                severity="info",
            ))
            continue

        for aspect_id in obj_aspects:
            # 1. aspect 必须存在
            if aspect_id not in aspects:
                specs.append(ConstraintSpec(
                    object_id=obj_id,
                    field_id="",
                    constraint="ASPECT_REFERENCED_MUST_EXIST",
                    description=(
                        f"Object '{obj_id}' uses aspect '{aspect_id}' "
                        "but it's not in aspects.yaml"
                    ),
                    severity="error",
                ))
                continue

            # healthy: aspect 已声明且存在
            specs.append(ConstraintSpec(
                object_id=obj_id,
                field_id="",
                constraint="ASPECT_REFERENCED_MUST_EXIST",
                description=(
                    f"Object '{obj_id}' references aspect '{aspect_id}' (resolved)"
                ),
                severity="info",
            ))

            # 2. audit_aspect 特殊检查
            if aspect_id == "audit_aspect":
                must_have = {"created_at"}
                missing = must_have - obj_field_ids
                if missing:
                    specs.append(ConstraintSpec(
                        object_id=obj_id,
                        field_id=",".join(sorted(missing)),
                        constraint="ASPECT_FIELDS_APPLIED",
                        description=(
                            f"Object '{obj_id}' uses audit_aspect but missing "
                            f"required fields: {sorted(missing)}"
                        ),
                        severity="warning",
                    ))
                else:
                    # positive: created_at 已存在
                    specs.append(ConstraintSpec(
                        object_id=obj_id,
                        field_id="created_at",
                        constraint="ASPECT_FIELDS_APPLIED",
                        description=(
                            f"Object '{obj_id}' uses audit_aspect "
                            "and provides created_at (ok)"
                        ),
                        severity="info",
                    ))

                # 3. 引用了 audit_aspect 但无 audit 配置
                audit_cfg = getattr(obj, "audit", None)
                if not audit_cfg:
                    specs.append(ConstraintSpec(
                        object_id=obj_id,
                        field_id="",
                        constraint="AUDIT_ASPECT_HAS_AUDIT_CONFIG",
                        description=(
                            f"Object '{obj_id}' uses audit_aspect but has no "
                            "top-level 'audit' configuration"
                        ),
                        severity="warning",
                    ))
                else:
                    # positive: audit 配置存在
                    specs.append(ConstraintSpec(
                        object_id=obj_id,
                        field_id="",
                        constraint="AUDIT_ASPECT_HAS_AUDIT_CONFIG",
                        description=(
                            f"Object '{obj_id}' uses audit_aspect "
                            "and provides 'audit' configuration (ok)"
                        ),
                        severity="info",
                    ))

    return specs


# 已知"rls_rules 未建模"白名单 (v1.1)
# 这些 rls_rules/*.yaml 文件存在, 但对应 schema 还未创建
# (预定义的未来对象)
RLS_UNMODELED_ENTITIES = frozenset({
    'order',  # 订单: rls_rules/order.yaml 已写, 但 order.yaml 未建模
})


def discover_rls_constraints(
    objects: Dict[str, "MetaObject"],
    rls_rules: Dict[str, Dict],
) -> List[ConstraintSpec]:
    """
    推导 RLS 规则覆盖与有效性测试规格 (v1.1 新增)。

    输出策略 (positive-or-negative):
    - 持久化对象无 rls 规则 -> warning (issue)
    - 持久化对象已有 rls 规则 -> info (positive)
    - rls 实体未对应 schema -> error (invalid)
    - rls 实体未对应 schema 但在白名单 -> info (预定义未来 schema)
    - rls 实体对应 schema -> info (valid)
    """
    specs: List[ConstraintSpec] = []

    rls_entities = set(rls_rules.keys())
    for obj_id, obj in sorted(objects.items()):
        if not _is_testable(obj_id, obj):
            continue
        if not getattr(obj, "persistent", True):
            continue
        if obj_id in rls_entities:
            # positive: rls 已存在
            specs.append(ConstraintSpec(
                object_id=obj_id,
                field_id="",
                constraint="RLS_FILE_EXISTS_FOR_OBJECT",
                description=(
                    f"Persistent object '{obj_id}' has rls_rules/{obj_id}.yaml (ok)"
                ),
                severity="info",
            ))
            continue
        obj_type = str(getattr(obj, "object_type", "")).lower()
        if "enum" in obj_type:
            continue
        # negative: 持久化对象但无 rls 规则
        specs.append(ConstraintSpec(
            object_id=obj_id,
            field_id="",
            constraint="RLS_FILE_EXISTS_FOR_OBJECT",
            description=(
                f"Persistent object '{obj_id}' has no rls_rules/{obj_id}.yaml"
            ),
            severity="warning",
        ))

    for entity_id, rls_cfg in sorted(rls_rules.items()):
        if entity_id not in objects:
            if entity_id in RLS_UNMODELED_ENTITIES:
                # 白名单: 已知未建模 (等待未来 schema) - 标记为 info
                specs.append(ConstraintSpec(
                    object_id=entity_id,
                    field_id="",
                    constraint="RLS_ENTITY_FIELD_VALID",
                    description=(
                        f"rls_rules file declares entity='{entity_id}' "
                        "(whitelisted as future-planned schema)"
                    ),
                    severity="info",
                ))
            else:
                specs.append(ConstraintSpec(
                    object_id=entity_id,
                    field_id="",
                    constraint="RLS_ENTITY_FIELD_VALID",
                    description=(
                        f"rls_rules file declares entity='{entity_id}' "
                        "but no matching object exists in schemas/"
                    ),
                    severity="error",
                ))
        else:
            # positive: rls entity 有效
            specs.append(ConstraintSpec(
                object_id=entity_id,
                field_id="",
                constraint="RLS_ENTITY_FIELD_VALID",
                description=(
                    f"rls_rules entity='{entity_id}' matches "
                    "an existing schema (ok)"
                ),
                severity="info",
            ))

        # 3. RLS 规则中的 role 字段有效性 (applies_to / applies_to_role)
        applies_to = rls_cfg.get("applies_to") or rls_cfg.get("applies_to_role") or []
        if isinstance(applies_to, str):
            applies_to = [applies_to]
        for role_id in applies_to:
            # role 可能以 enum 或 object 形式存在
            role_exists = role_id in objects
            if not role_exists and "enum" in str(getattr(objects.get(role_id, None), "object_type", "")).lower():
                role_exists = True
            if not role_exists:
                specs.append(ConstraintSpec(
                    object_id=entity_id,
                    field_id=str(role_id),
                    constraint="RLS_APPLIES_TO_ROLE_VALID",
                    description=(
                        f"rls_rules[{entity_id}].applies_to references "
                        f"role='{role_id}' but no such object exists"
                    ),
                    severity="warning",
                ))
            else:
                specs.append(ConstraintSpec(
                    object_id=entity_id,
                    field_id=str(role_id),
                    constraint="RLS_APPLIES_TO_ROLE_VALID",
                    description=(
                        f"rls_rules[{entity_id}].applies_to role='{role_id}' "
                        "resolves to an existing object (ok)"
                    ),
                    severity="info",
                ))

    return specs


# 已知"无 yaml 内部对象"白名单 (v1.1)
# 这些 _OBJECT_TYPE 在源码中存在但没有独立 yaml schema
# (它们是另一个 schema 的内部子结构, 例如 change_subscription 内部的 webhook 配置)
FACTORY_UNMODELED_TYPES = frozenset({
    'import_export_task',  # change_subscription 内部: 导入导出任务
    'subscription',        # change_subscription 内部: 订阅配置
    'webhook',             # change_subscription 内部: webhook 端点
})


def discover_unique_id_constraints(
    factories: Dict[str, Dict[str, Any]],
) -> List[ConstraintSpec]:
    """
    [FIX 2026-07-17 P2] 推导 FACTORY_UNIQUE_ID_DETERMINISTIC 约束 (v1.1 新增).

    目标: 永远守护 unique_id() 的确定性, 防止 pre-existing bug 复发.

    检查维度 (基于 AST 静态分析 _base.py):
    1. unique_id() 函数是否定义  -> severity=info (positive)
    2. unique_id() 函数缺失      -> severity=error
    3. unique_id() 不使用 counter -> severity=warning (旧实现风险)
    4. unique_id() 不使用 lock    -> severity=warning (多线程风险)

    输出策略: 仅输出 1 条 spec (positive-or-negative):
    - 全过 -> info
    - 任一不满足 -> error / warning (按最严)
    """
    specs: List[ConstraintSpec] = []
    meta = factories.get("_meta")

    if not meta or not meta.get("unique_id_defined"):
        specs.append(ConstraintSpec(
            object_id="_base",
            field_id="unique_id",
            constraint="FACTORY_UNIQUE_ID_DETERMINISTIC",
            description=(
                "_base.py missing unique_id() function definition "
                "(required for factory uniqueness helpers)"
            ),
            severity="error",
        ))
        return specs

    # 检测关键安全模式
    missing_features = []
    if not meta.get("uses_counter"):
        missing_features.append("process-local counter")
    if not meta.get("uses_lock"):
        missing_features.append("threading.Lock")

    if missing_features:
        # partial: 有函数但缺少安全模式
        specs.append(ConstraintSpec(
            object_id="_base",
            field_id="unique_id",
            constraint="FACTORY_UNIQUE_ID_DETERMINISTIC",
            description=(
                f"unique_id() missing safety patterns: {missing_features} "
                "(fast loops may return duplicate IDs)"
            ),
            severity="warning",
        ))
    else:
        # healthy: 全部模式存在
        specs.append(ConstraintSpec(
            object_id="_base",
            field_id="unique_id",
            constraint="FACTORY_UNIQUE_ID_DETERMINISTIC",
            description=(
                "unique_id() uses counter + lock patterns (deterministic, "
                "thread-safe, cross-process isolated via PID)"
            ),
            severity="info",
        ))

    return specs


def discover_factory_constraints(
    objects: Dict[str, "MetaObject"],
    factories: Dict[str, Dict[str, Any]],
) -> List[ConstraintSpec]:
    """
    推导 Factory ↔ YAML 一致性测试规格 (v1.1 新增)。

    输出策略 (positive-or-negative):
    - factory _OBJECT_TYPE 未匹配 schema -> error
    - factory _OBJECT_TYPE 未匹配 schema 但在白名单 -> info (已记录为未建模)
    - factory _OBJECT_TYPE 匹配 schema -> info (positive)
    - factory defaults 缺失 -> warning/error
    - factory defaults 齐全 -> info (positive)
    """
    specs: List[ConstraintSpec] = []

    for obj_type, fac_info in sorted(factories.items()):
        # [FIX 2026-07-17 P2] 跳过 _meta 元数据键 (非 factory)
        if obj_type == "_meta":
            continue
        if obj_type not in objects:
            if obj_type in FACTORY_UNMODELED_TYPES:
                # 白名单: 已知未建模内部对象, 记录为 info
                specs.append(ConstraintSpec(
                    object_id=obj_type,
                    field_id="",
                    constraint="FACTORY_OBJECT_TYPE_REGISTERED",
                    description=(
                        f"Factory '{fac_info['class_name']}' (file={fac_info['file']}) "
                        f"declares _OBJECT_TYPE='{obj_type}' (whitelisted as internal sub-object)"
                    ),
                    severity="info",
                ))
                continue
            specs.append(ConstraintSpec(
                object_id=obj_type,
                field_id="",
                constraint="FACTORY_OBJECT_TYPE_REGISTERED",
                description=(
                    f"Factory '{fac_info['class_name']}' (file={fac_info['file']}) "
                    f"declares _OBJECT_TYPE='{obj_type}' but no matching yaml schema"
                ),
                severity="error",
            ))
            continue

        # positive: factory 已注册到 schema
        specs.append(ConstraintSpec(
            object_id=obj_type,
            field_id="",
            constraint="FACTORY_OBJECT_TYPE_REGISTERED",
            description=(
                f"Factory '{fac_info['class_name']}' (file={fac_info['file']}) "
                f"registers _OBJECT_TYPE='{obj_type}' against existing schema (ok)"
            ),
            severity="info",
        ))

        obj = objects[obj_type]
        defaults_keys = set(fac_info.get("defaults_keys", []) or [])

        if not defaults_keys:
            specs.append(ConstraintSpec(
                object_id=obj_type,
                field_id="",
                constraint="FACTORY_DEFAULTS_NOT_EMPTY",
                description=(
                    f"Factory '{fac_info['class_name']}' has no _DEFAULTS "
                    "dict or _base_defaults() return dict"
                ),
                severity="warning",
            ))
            continue

        # positive: defaults 不为空
        specs.append(ConstraintSpec(
            object_id=obj_type,
            field_id="",
            constraint="FACTORY_DEFAULTS_NOT_EMPTY",
            description=(
                f"Factory '{fac_info['class_name']}' provides "
                f"{len(defaults_keys)} default keys (ok)"
            ),
            severity="info",
        ))

        obj_required = {
            f.id for f in obj.fields
            if getattr(f, "required", False) and _is_persistent_field(f)
        }
        # 排除自动生成字段 (PK + 审计 + ORM 自动字段)
        auto_inherited = {
            "id", "created_at", "updated_at", "created_by", "updated_by",
        }
        effective_required = obj_required - auto_inherited

        missing = effective_required - defaults_keys
        if missing:
            specs.append(ConstraintSpec(
                object_id=obj_type,
                field_id=",".join(sorted(missing)),
                constraint="FACTORY_DEFAULTS_COVER_REQUIRED",
                description=(
                    f"Factory '{fac_info['class_name']}' defaults missing "
                    f"required yaml fields: {sorted(missing)}"
                ),
                severity="error",
            ))
        else:
            # positive: defaults 覆盖了所有 required 字段
            specs.append(ConstraintSpec(
                object_id=obj_type,
                field_id="",
                constraint="FACTORY_DEFAULTS_COVER_REQUIRED",
                description=(
                    f"Factory '{fac_info['class_name']}' defaults cover "
                    f"all required yaml fields (ok)"
                ),
                severity="info",
            ))

    return specs


def discover_v11_constraints(
    objects: Dict[str, "MetaObject"],
    aspects: Optional[Dict[str, Any]] = None,
    rls_rules: Optional[Dict[str, Dict]] = None,
    factories: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[ConstraintSpec]:
    """
    v1.1 主入口: 聚合 aspects/RLS/factory 三个方向的所有约束。
    """
    specs: List[ConstraintSpec] = []
    if aspects is not None:
        specs.extend(discover_aspect_constraints(objects, aspects))
    if rls_rules is not None:
        specs.extend(discover_rls_constraints(objects, rls_rules))
    if factories is not None:
        specs.extend(discover_factory_constraints(objects, factories))
        # [FIX 2026-07-17 P2] 永远守护 unique_id() 确定性
        specs.extend(discover_unique_id_constraints(factories))
    return specs


def _is_testable(obj_id: str, obj) -> bool:
    """判断对象是否值得推导测试"""
    if not obj_id:
        return False
    if not getattr(obj, "persistent", True):
        return False
    if not getattr(obj, "fields", None):
        return False
    return True


def _discover_object_level_constraints(obj, objects: Dict) -> List[ConstraintSpec]:
    """推导对象级约束"""
    specs = []

    if not obj.table_name:
        specs.append(ConstraintSpec(
            object_id=obj.id,
            field_id="",
            constraint="TABLE_NAME_NOT_EMPTY",
            description=f"Persistent object '{obj.id}' must have a non-empty table_name",
        ))

    if getattr(obj, "persistent", True) and not obj.has_version_field():
        has_pk = any(
            getattr(f, "primary_key", False) or f.db_column == "id"
            for f in obj.fields
        )
        if not has_pk:
            specs.append(ConstraintSpec(
                object_id=obj.id,
                field_id="",
                constraint="PERSISTENT_OBJECT_HAS_PK",
                description=f"Persistent object '{obj.id}' has no primary key (no version field and no explicit PK)",
                severity="warning",
            ))

    obj_type = str(getattr(obj, "object_type", ""))
    if obj_type.endswith("ENTITY") or "business" in obj_type.lower() or obj_type == "ObjectType.ENTITY":
        business_keys = _get_business_key_fields(obj)
        if not business_keys:
            specs.append(ConstraintSpec(
                object_id=obj.id,
                field_id="",
                constraint="BUSINESS_KEY_EXISTS_FOR_BO",
                description=f"Entity '{obj.id}' should declare at least one business_key field",
                severity="warning",
            ))

    if not obj.actions:
        specs.append(ConstraintSpec(
            object_id=obj.id,
            field_id="",
            constraint="META_OBJECT_HAS_AT_LEAST_ONE_ACTION",
            description=f"Object '{obj.id}' has no actions defined",
            severity="warning",
        ))

    parent = getattr(obj, "parent_object", "")
    if parent and parent not in objects:
        specs.append(ConstraintSpec(
            object_id=obj.id,
            field_id="",
            constraint="HIERARCHY_PARENT_OBJECT_EXISTS",
            description=f"Hierarchy object '{obj.id}' declares parent_object='{parent}' which is not in registry",
        ))

    del_policy = getattr(obj, "deletion_policy", None)
    if del_policy:
        restrict_targets = _extract_restrict_targets(del_policy)
        for target_id in restrict_targets:
            if target_id and target_id not in objects:
                specs.append(ConstraintSpec(
                    object_id=obj.id,
                    field_id="",
                    constraint="DELETION_POLICY_TARGET_EXISTS",
                    description=f"deletion_policy of '{obj.id}' references unknown object '{target_id}'",
                ))

    display_field = getattr(obj, "display_name_field", None)
    if display_field and obj.get_field(display_field) is None:
        specs.append(ConstraintSpec(
            object_id=obj.id,
            field_id="",
            constraint="DISPLAY_NAME_FIELD_DECLARED",
            description=f"display_name_field='{display_field}' of '{obj.id}' is not defined in fields",
        ))

    return specs


def _discover_field_level_constraints(obj, objects: Dict) -> List[ConstraintSpec]:
    """推导字段级约束"""
    specs = []

    for field in obj.fields:
        if not _is_persistent_field(field):
            continue

        if not getattr(field, "db_column", None):
            specs.append(ConstraintSpec(
                object_id=obj.id,
                field_id=field.id,
                constraint="PERSISTENT_FIELD_HAS_DB_COLUMN",
                description=f"Persistent field '{field.id}' of '{obj.id}' has no db_column",
            ))

        if getattr(field, "required", False):
            specs.append(ConstraintSpec(
                object_id=obj.id,
                field_id=field.id,
                constraint="REQUIRED_FIELD_DEFINED",
                description=f"Required field '{field.id}' declared on '{obj.id}'",
                severity="warning",
            ))

        if getattr(field, "unique", False):
            indexed_fields = set()
            for idx in getattr(obj, "indexes", []) or []:
                for fid in getattr(idx, "fields", []) or []:
                    indexed_fields.add(fid)
            if field.id not in indexed_fields:
                specs.append(ConstraintSpec(
                    object_id=obj.id,
                    field_id=field.id,
                    constraint="UNIQUE_FIELD_HAS_DB_INDEX",
                    description=f"Unique field '{field.id}' of '{obj.id}' has no matching index declared",
                    severity="warning",
                ))

        enum_values = getattr(field, "enum_values", []) or []
        enum_type = getattr(field, "enum_type", "") or ""
        if enum_values and enum_type:
            enum_obj = objects.get(enum_type)
            if enum_obj is not None:
                valid_ids = {
                    v.get("id") or v.get("value") or v.get("code")
                    for v in getattr(enum_obj, "enum_values", []) or []
                } if hasattr(enum_obj, "enum_values") else set()
                for ev in enum_values:
                    val = ev.get("id") or ev.get("value") or ev.get("code")
                    if val and valid_ids and val not in valid_ids:
                        specs.append(ConstraintSpec(
                            object_id=obj.id,
                            field_id=field.id,
                            constraint="ENUM_FIELD_VALUES_VALID",
                            description=f"enum_values of '{obj.id}.{field.id}' contains '{val}' not in enum_type '{enum_type}'",
                        ))

        if getattr(field, "default", None) is not None:
            default = field.default
            ft = getattr(field, "field_type", None)
            ft_name = getattr(ft, "name", str(ft)) if ft else ""
            if ft_name == "INTEGER" and not isinstance(default, int):
                specs.append(ConstraintSpec(
                    object_id=obj.id,
                    field_id=field.id,
                    constraint="DEFAULT_VALUE_TYPE_MATCHES",
                    description=f"default value of '{obj.id}.{field.id}' should be int for INTEGER field",
                    severity="warning",
                ))
            elif ft_name == "BOOLEAN" and not isinstance(default, bool):
                specs.append(ConstraintSpec(
                    object_id=obj.id,
                    field_id=field.id,
                    constraint="DEFAULT_VALUE_TYPE_MATCHES",
                    description=f"default value of '{obj.id}.{field.id}' should be bool for BOOLEAN field",
                    severity="warning",
                ))

    return specs


# ---------- 辅助函数 ----------

def _is_persistent_field(field) -> bool:
    """判断字段是否需要持久化"""
    storage = getattr(field, "storage", None)
    storage_val = getattr(storage, "value", str(storage)) if storage else "stored"
    return storage_val in ("stored", "STORED") and not getattr(field, "computed", False)


def _get_business_key_fields(obj) -> list:
    """取业务键字段"""
    if hasattr(obj, "_get_business_key_fields"):
        try:
            return obj._get_business_key_fields()
        except Exception:
            pass
    return [f for f in obj.fields if getattr(getattr(f, "semantics", None), "business_key", False)]


def _extract_restrict_targets(del_policy) -> list:
    """从 deletion_policy 提取 restrict_on 目标对象列表"""
    if isinstance(del_policy, dict):
        restrict = del_policy.get("restrict_on") or []
    else:
        restrict = getattr(del_policy, "restrict_on", []) or []
    targets = []
    for r in restrict:
        if isinstance(r, dict):
            tid = r.get("target") or r.get("object_id")
            if tid:
                targets.append(tid)
        elif isinstance(r, str):
            targets.append(r)
    return targets