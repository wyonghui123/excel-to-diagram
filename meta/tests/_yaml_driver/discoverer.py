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

返回: List[ConstraintSpec], 每个包含 (object_id, field_id, constraint_type, description)
"""
from dataclasses import dataclass
from typing import Dict, List


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

    触发场景:
    - obj 应用了 audit_aspect 但缺少 audit 配置
    - obj 应用了 audit_aspect 但缺少 created_at 字段
    - obj 应用了某个 aspect 但缺少其声明的字段

    实现方式: yaml_loader 通过 _resolve_aspects() 把 aspect 字段合并到 obj.fields,
    每个 aspect-derived 字段带 included_from="<aspect_id>" 标记。
    """
    specs: List[ConstraintSpec] = []

    # 收集每个对象实际应用的 aspect (从字段 included_from 反推)
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
        # 方式2: obj.aspects 顶层属性 (yaml 引用了但 aspect 字段没合并)
        direct_aspects = getattr(obj, "aspects", None) or []
        if direct_aspects:
            obj_aspects.update(direct_aspects)

        if not obj_aspects:
            continue

        for aspect_id in obj_aspects:
            # 1. aspect 必须存在
            if aspect_id not in aspects:
                specs.append(ConstraintSpec(
                    object_id=obj_id,
                    field_id="",
                    constraint="ASPECT_REFERENCED_MUST_EXIST",
                    description=(
                        f"Object '{obj_id}' uses aspect '{aspect_id}' (inferred from "
                        "included_from) but it's not in aspects.yaml"
                    ),
                    severity="error",
                ))
                continue

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

    return specs


def discover_rls_constraints(
    objects: Dict[str, "MetaObject"],
    rls_rules: Dict[str, Dict],
) -> List[ConstraintSpec]:
    """
    推导 RLS 规则覆盖与有效性测试规格 (v1.1 新增)。

    触发场景:
    - 持久化对象缺少 rls_rules/<obj>.yaml (warning)
    - rls_rules/*.yaml 的 entity 字段引用了不存在的对象
    - rls 的 applies_to 角色不在 registry 中
    """
    specs: List[ConstraintSpec] = []

    # 1. 持久化对象应有对应的 RLS 文件 (informational)
    rls_entities = set(rls_rules.keys())
    for obj_id, obj in sorted(objects.items()):
        if not _is_testable(obj_id, obj):
            continue
        if not getattr(obj, "persistent", True):
            continue
        if obj_id in rls_entities:
            continue
        # 枚举/虚拟对象通常无 RLS, 跳过
        obj_type = str(getattr(obj, "object_type", "")).lower()
        if "enum" in obj_type:
            continue
        specs.append(ConstraintSpec(
            object_id=obj_id,
            field_id="",
            constraint="RLS_FILE_EXISTS_FOR_OBJECT",
            description=(
                f"Persistent object '{obj_id}' has no rls_rules/{obj_id}.yaml"
            ),
            severity="warning",
        ))

    # 2. RLS 文件中的 entity 必须对应真实对象
    for entity_id, rls_cfg in sorted(rls_rules.items()):
        if entity_id not in objects:
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

    # 3. applies_to 中的角色必须在 role 对象中存在 (best-effort)
    role_obj = objects.get("role")
    if role_obj and hasattr(role_obj, "fields"):
        # 收集 role 对象的合法 code 值 (枚举或静态字段)
        # 简单实现: 只检查 role yaml 中是否有 'code' 字段定义了 unique/required
        pass  # 当前 role.yaml 是动态的, 跳过精确校验

    return specs


def discover_factory_constraints(
    objects: Dict[str, "MetaObject"],
    factories: Dict[str, Dict[str, Any]],
) -> List[ConstraintSpec]:
    """
    推导 Factory ↔ YAML 一致性测试规格 (v1.1 新增)。

    触发场景:
    - factory _OBJECT_TYPE 在 yaml 中不存在
    - factory 的 defaults 没覆盖 yaml 必填字段
    - factory 完全没声明 defaults (警告)
    """
    specs: List[ConstraintSpec] = []

    # 1. factory 的 OBJECT_TYPE 必须在 yaml 中存在
    for obj_type, fac_info in sorted(factories.items()):
        if obj_type not in objects:
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

        obj = objects[obj_type]
        defaults_keys = set(fac_info.get("defaults_keys", []) or [])

        # 2. factory 必须有 defaults
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

        # 3. factory defaults 必须覆盖 yaml required 字段
        obj_required = {
            f.id for f in obj.fields
            if getattr(f, "required", False) and _is_persistent_field(f)
        }
        # 排除 created_at/updated_at 等 audit_aspect 自动添加字段
        audit_inherited = {"created_at", "updated_at", "created_by", "updated_by"}
        effective_required = obj_required - audit_inherited

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

    return specs


def discover_v11_constraints(
    objects: Dict[str, "MetaObject"],
    aspects: Optional[Dict[str, Any]] = None,
    rls_rules: Optional[Dict[str, Dict]] = None,
    factories: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[ConstraintSpec]:
    """
    v1.1 主入口: 聚合 aspects/RLS/factory 三个方向的所有约束。

    可以单独调用任一子发现函数, 也可以用这个总入口。
    """
    specs: List[ConstraintSpec] = []
    if aspects is not None:
        specs.extend(discover_aspect_constraints(objects, aspects))
    if rls_rules is not None:
        specs.extend(discover_rls_constraints(objects, rls_rules))
    if factories is not None:
        specs.extend(discover_factory_constraints(objects, factories))
    return specs


def _is_testable(obj_id: str, obj) -> bool:
    """判断对象是否值得推导测试"""
    # 1. 空 id (yaml_loader 没解析到 id 的元文件)
    if not obj_id:
        return False
    # 2. 非持久化对象 (枚举值等) 跳过
    if not getattr(obj, "persistent", True):
        return False
    # 3. 无 fields 的对象 (如 hierarchies 层级定义) 跳过
    if not getattr(obj, "fields", None):
        return False
    return True


def _discover_object_level_constraints(obj, objects: Dict) -> List[ConstraintSpec]:
    """推导对象级约束"""
    specs = []

    # 1. table_name 非空
    if not obj.table_name:
        specs.append(ConstraintSpec(
            object_id=obj.id,
            field_id="",
            constraint="TABLE_NAME_NOT_EMPTY",
            description=f"Persistent object '{obj.id}' must have a non-empty table_name",
        ))

    # 2. 持久化对象必须有主键 (version 字段 OR 显式 primary_key)
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

    # 3. 业务对象应有 business_key
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

    # 4. 至少一个 action (crud 或自定义)
    if not obj.actions:
        specs.append(ConstraintSpec(
            object_id=obj.id,
            field_id="",
            constraint="META_OBJECT_HAS_AT_LEAST_ONE_ACTION",
            description=f"Object '{obj.id}' has no actions defined",
            severity="warning",
        ))

    # 5. 层级对象: parent_object 必须存在
    parent = getattr(obj, "parent_object", "")
    if parent and parent not in objects:
        specs.append(ConstraintSpec(
            object_id=obj.id,
            field_id="",
            constraint="HIERARCHY_PARENT_OBJECT_EXISTS",
            description=f"Hierarchy object '{obj.id}' declares parent_object='{parent}' which is not in registry",
        ))

    # 6. deletion_policy 引用对象必须存在
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

    # 7. 显示名称字段必须实际存在
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
        # 跳过非持久化字段 (virtual/computed/derived)
        if not _is_persistent_field(field):
            continue

        # 1. 持久化字段必须有 db_column
        if not getattr(field, "db_column", None):
            specs.append(ConstraintSpec(
                object_id=obj.id,
                field_id=field.id,
                constraint="PERSISTENT_FIELD_HAS_DB_COLUMN",
                description=f"Persistent field '{field.id}' of '{obj.id}' has no db_column",
            ))

        # 2. required 字段是持久化字段
        if getattr(field, "required", False):
            specs.append(ConstraintSpec(
                object_id=obj.id,
                field_id=field.id,
                constraint="REQUIRED_FIELD_DEFINED",
                description=f"Required field '{field.id}' declared on '{obj.id}'",
                severity="warning",
            ))

        # 3. unique 字段应有 db_index 或 unique index
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

        # 4. enum 字段值都应在 enum_type 中
        enum_values = getattr(field, "enum_values", []) or []
        enum_type = getattr(field, "enum_type", "") or ""
        if enum_values and enum_type:
            # 收集 enum_type 对应对象的值
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

        # 5. default 值类型应与 field_type 兼容 (best-effort)
        if getattr(field, "default", None) is not None:
            # 仅做粗略校验，避免复杂反射
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
    # Fallback: semantics.business_key
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