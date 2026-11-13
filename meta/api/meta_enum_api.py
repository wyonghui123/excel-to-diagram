# -*- coding: utf-8 -*-
"""统一元数据端点（B2-1）

把前端散落的枚举/标签表收敛到后端单一来源：

- GET /api/v2/meta/enums/<name>               枚举下发（meta/schemas/*.yaml 或后端常量）
- GET /api/v2/meta/permission-matrix-schema   权限矩阵分组 schema
- GET /api/v2/meta/permission-meta            权限配置元数据（复用 /bo/permission_dimension/meta）

说明：
- 枚举来源优先级：显式 yaml 字段 → 后端常量 → 404 ENUM_NOT_FOUND（不返回前端猜测值）
- `permission_level` 目前是后端常量（data_permission.yaml 只有描述，无 enum_values）；
  `manage` 枚举归一本轮不处理（见 D-1 / TODO-1）。
"""

import logging
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app

from meta.api._response_contract import error_response, ok
from meta.api.auth_api import login_required
from meta.api.permission_dimension_api import (
    _ACTION_LABELS,
    _RESOURCE_TYPE_LABELS,
    _build_action_hints,
    _build_resource_action_matrix,
    _build_resource_hierarchy,
    _load_schema_yaml,
    _matrix_action_columns,
    get_permission_meta,
)

logger = logging.getLogger(__name__)

meta_enum_bp = Blueprint("meta_enum", __name__, url_prefix="/api/v2/meta")

# ==================== 权限等级（后端唯一来源） ====================
# 注意：当前授权引擎只使用 none/read/write/admin；manage 为历史枚举，
# 归一工作见 TODO-1（D-1 本轮跳过）。
PERMISSION_LEVELS: List[Dict[str, Any]] = [
    {"value": "none", "label": "无权限", "level": 0},
    {"value": "read", "label": "只读", "level": 1},
    {"value": "write", "label": "可编辑", "level": 2},
    {"value": "admin", "label": "完全管理", "level": 3},
]

# ==================== 动作分组 schema（原前端 permissionConstants.ts） ====================
ACTION_GROUP_SCHEMA: Dict[str, Any] = {
    "group_labels": {"view": "查看", "edit": "编辑", "manage": "管理"},
    "group_i18n_keys": {
        "view": "permission.group.view",
        "edit": "permission.group.edit",
        "manage": "permission.group.manage",
    },
    "group_dependencies": {"manage": ["edit"], "edit": ["view"], "view": []},
    "group_actions_map": {
        "view": ["read", "list"],
        "edit": ["read", "list", "create", "update"],
        "manage": ["read", "list", "create", "update", "delete"],
    },
    "standalone_actions": {
        "export": {"label": "导出", "description": "独立权限，不隐含 read"},
        "import": {"label": "导入", "description": "独立权限，不隐含 create"},
        "assign": {"label": "分配", "description": "关联操作（成员管理）"},
        "unassign": {"label": "取消分配", "description": "关联操作（成员管理）"},
        "associate": {"label": "关联", "description": "关联操作（关系建立）"},
        "dissociate": {"label": "取消关联", "description": "关联操作（关系解除）"},
        "grant": {"label": "授权", "description": "关联操作（权限授予）"},
        "revoke": {"label": "撤销", "description": "关联操作（权限撤销）"},
    },
}

# ==================== yaml 枚举来源 ====================
# name -> (schema 文件, 字段 id)；字段必须带 enum_values
ENUM_SOURCES: Dict[str, tuple] = {
    "audit_action": ("audit_log.yaml", "action"),
    "task_status": ("project_task.yaml", "status"),
    "task_priority": ("project_task.yaml", "priority"),
    "engineering_change_status": ("engineering_change.yaml", "status"),
    "change_request_status": ("change_request.yaml", "status"),
}


def _find_field(doc: Any, field_id: str) -> Optional[Dict[str, Any]]:
    """递归查找 yaml 中 id == field_id 的字段定义"""
    if isinstance(doc, dict):
        if doc.get("id") == field_id:
            return doc
        for value in doc.values():
            found = _find_field(value, field_id)
            if found:
                return found
    elif isinstance(doc, list):
        for item in doc:
            found = _find_field(item, field_id)
            if found:
                return found
    return None


def _normalize_enum_values(enum_values: List[Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for item in enum_values or []:
        if isinstance(item, str):
            items.append({"value": item, "label": item})
            continue
        if not isinstance(item, dict):
            continue
        value = item.get("value", item.get("id"))
        if value is None:
            continue
        entry: Dict[str, Any] = {
            "value": value,
            "label": item.get("label") or item.get("display_name") or value,
        }
        for extra in ("color", "category", "description"):
            if item.get(extra) is not None:
                entry[extra] = item[extra]
        items.append(entry)
    return items


def _load_yaml_enum(filename: str, field_id: str) -> Optional[List[Dict[str, Any]]]:
    doc = _load_schema_yaml(filename)
    field = _find_field(doc, field_id)
    if not field:
        logger.warning("[meta/enums] %s 中未找到字段 %s", filename, field_id)
        return None
    enum_values = field.get("enum_values")
    if not enum_values and field.get("enum_type_id"):
        logger.warning(
            "[meta/enums] %s.%s 使用 enum_type_id=%s，请使用 enum/options 端点",
            filename,
            field_id,
            field.get("enum_type_id"),
        )
        return None
    return _normalize_enum_values(enum_values or [])


def _load_hierarchy_levels() -> List[Dict[str, Any]]:
    """层级枚举：来自 hierarchies.yaml 的 levels（SSOT）"""
    doc = _load_schema_yaml("hierarchies.yaml")
    hierarchies = doc.get("hierarchies", []) if isinstance(doc, dict) else []
    if not hierarchies:
        return []
    target = next((h for h in hierarchies if h.get("id") == "biz_hierarchy"), hierarchies[0])
    items: List[Dict[str, Any]] = []
    for level in target.get("levels", []) or []:
        obj = level.get("object")
        if not obj:
            continue
        items.append(
            {
                "value": obj,
                "label": level.get("display_name") or obj,
                "level": int(level.get("level", len(items))) + 1,
                "parent": level.get("parent_object"),
            }
        )
    return items


def resolve_enum(name: str) -> Optional[List[Dict[str, Any]]]:
    """解析枚举；未知枚举返回 None（fail-closed，不猜）"""
    if name == "permission_level":
        return [dict(item) for item in PERMISSION_LEVELS]
    if name == "hierarchy_level":
        return _load_hierarchy_levels()
    source = ENUM_SOURCES.get(name)
    if source:
        return _load_yaml_enum(*source)
    return None


@meta_enum_bp.route("/enums/<name>", methods=["GET"])
@login_required
def get_enum(name: str):
    try:
        items = resolve_enum(name)
        if items is None:
            return error_response(f"ENUM_NOT_FOUND: {name}", status=404)
        return ok({"name": name, "items": items})
    except Exception as exc:  # noqa: BLE001
        logger.error("[meta/enums] 下发 %s 失败: %s", name, exc)
        return error_response("EVAL_FAILED: enum resolve failed", status=500)


@meta_enum_bp.route("/permission-matrix-schema", methods=["GET"])
@login_required
def get_permission_matrix_schema():
    try:
        payload = dict(ACTION_GROUP_SCHEMA)
        payload.update(
            {
                "action_labels": dict(_ACTION_LABELS),
                "resource_labels": dict(_RESOURCE_TYPE_LABELS),
                "action_columns": _matrix_action_columns(),
                "resource_action_matrix": _build_resource_action_matrix(),
                "action_hints": _build_action_hints(),
                "resource_hierarchy": _build_resource_hierarchy(),
            }
        )
        return ok(payload)
    except Exception as exc:  # noqa: BLE001
        logger.error("[meta/permission-matrix-schema] 构建失败: %s", exc)
        return error_response("EVAL_FAILED: matrix schema build failed", status=500)


SELECTION_DEFAULT_LIMIT = 5000
SELECTION_HARD_LIMIT = 100000


@meta_enum_bp.route("/selection-limit", methods=["GET"])
@login_required
def get_selection_limit():
    """[B2-5] 选择数量上限由后端配置下发（忽略 URL 覆盖）。"""
    raw = current_app.config.get("MAX_SELECTION_LIMIT", SELECTION_DEFAULT_LIMIT)
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        limit = SELECTION_DEFAULT_LIMIT
    limit = max(1, min(SELECTION_HARD_LIMIT, limit))

    raw_threshold = current_app.config.get("SELECTION_WARNING_THRESHOLD", 0.8)
    try:
        threshold = float(raw_threshold)
    except (TypeError, ValueError):
        threshold = 0.8

    return ok({
        "max_count": limit,
        "warning_threshold": threshold,
        "hard_limit": SELECTION_HARD_LIMIT,
    })


@meta_enum_bp.route("/permission-meta", methods=["GET"])
@login_required
def get_meta_permission_meta():
    """别名：与 /bo/permission_dimension/meta 共用同一实现（单一来源）"""
    return get_permission_meta()