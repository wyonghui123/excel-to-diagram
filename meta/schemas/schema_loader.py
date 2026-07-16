# -*- coding: utf-8 -*-
"""Schema 加载器 — 将 YAML 文件解析为 dict。"""

from meta.core.yaml_loader import load_yaml_file, parse_aspects_yaml


class SchemaLoader:

    def __init__(self, schema_dir: str):
        self._schema_dir = schema_dir
        self._aspects = None

    def load_schema(self, name: str) -> dict:
        file_path = f"{self._schema_dir}/{name}.yaml"
        if self._aspects is None:
            self._aspects = parse_aspects_yaml(self._schema_dir)
        meta = load_yaml_file(file_path, aspects_defs=self._aspects)
        if meta is None:
            return {}
        result = {
            'id': meta.id,
            # [FIX BUG-V051.2 2026-07-10 dev agent] 暴露 name, 兜底链路里 entityMeta.name 被使用
            'name': getattr(meta, 'name', ''),
            'table_name': meta.table_name,
            # [FIX BUG-V048 2026-07-06 dev agent] MetaObject 没有 label 字段, 用 name 兜底
            'label': getattr(meta, 'label', None) or getattr(meta, 'name', ''),
            'labels': getattr(meta, 'labels', {}),
            'description': getattr(meta, 'description', ''),
            # [FIX BUG-V051.2 2026-07-10 dev agent] 暴露 display_name_field
            # 原因: 前端 ObjectDetailPage.vue:291 等用 entityMeta.display_name_field
            #       决定详情页/列表显示哪个字段 (如 relationship 用 relation_desc 而非 code)
            'display_name_field': getattr(meta, 'display_name_field', None),
            # [FIX BUG-V051.2 2026-07-10 dev agent] 暴露 parent_object
            # 原因: 前端面包屑/树形结构根据 parent_object 决定父子关系
            'parent_object': getattr(meta, 'parent_object', None) or '',
            'fields': [],
            'actions': [],
            'associations': [],
            # [FIX BUG-V051 2026-07-10 dev agent] 暴露 aspects 字段供前端 DetailPage.hasAuditAspect 使用
            # 原因: 前端 DetailPage.vue:359-363 检查 entityMeta.aspects 是否含 'audit_aspect'
            #       决定是否注入 'history' (操作日志) section
            #       之前 load_schema 没把 aspects 加到 result, 前端永远拿到空 → 详情页"暂无变更记录"
            'aspects': list(getattr(meta, 'aspects', None) or []),
            # [FIX BUG-V051.2 2026-07-10 dev agent] 暴露 UI 配置, 前端 form/detail/list 渲染用
            'ui_view_config': _serialize_ui_view_config(getattr(meta, 'ui_view_config', None)),
            'ui_view_configs': _serialize_ui_view_configs(getattr(meta, 'ui_view_configs', None) or {}),
            # [FIX BUG-V051.2 2026-07-10 dev agent] 暴露删除/添加策略
            'deletability': _serialize_deletability(getattr(meta, 'deletability', None)),
            'addability': _serialize_addability(getattr(meta, 'addability', None)),
            # [FIX BUG-V051.2 2026-07-10 dev agent] 业务对象分类
            'bo_category': _enum_to_str(getattr(meta, 'bo_category', None)),
            'bo_sub_category': _enum_to_str(getattr(meta, 'bo_sub_category', None)),
            # [FIX BUG-V051.2 2026-07-10 dev agent] 视图/持久化标记
            'is_view': getattr(meta, 'is_view', False),
            'persistent': getattr(meta, 'persistent', True),
            # [FIX BUG-V051.2 2026-07-10 dev agent] KeyTemplate 编码规则
            'key_template': getattr(meta, 'key_template', None) or {},
            # [FIX BUG-V051.2 2026-07-10 dev agent] 级联选择
            'cascade_select': getattr(meta, 'cascade_select', None) or [],
        }
        for f in (meta.fields or []):
            result['fields'].append({
                'id': getattr(f, 'id', ''),
                'name': getattr(f, 'name', ''),
                'label': getattr(f, 'label', ''),
                'type': getattr(f, 'type', 'string'),
                'field_type': _enum_to_str(getattr(f, 'field_type', None)),
                'db_column': getattr(f, 'db_column', ''),
                # [FIX BUG-V051.2 2026-07-10 dev agent] 必填/唯一, 前端表单校验用
                'required': getattr(f, 'required', False),
                'unique': getattr(f, 'unique', False),
                # [FIX BUG-V051.2 2026-07-10 dev agent] 默认值, 前端初始化用
                'default': getattr(f, 'default', None),
                'description': getattr(f, 'description', ''),
                'computed': getattr(f, 'computed', False),
                'enum_type': getattr(f, 'enum_type', '') or None,
                # [FIX BUG-V051.2 2026-07-10 dev agent] 业务语义 (status, business_key, primary_name)
                # 原因: 前端 ObjectDetailPage.vue:230 等用 f.semantics?.status 查找状态字段
                'semantics': _serialize_semantics(getattr(f, 'semantics', None)),
                # [FIX BUG-V051.2 2026-07-10 dev agent] UI 渲染配置
                'ui': _serialize_field_ui(getattr(f, 'ui', None)),
                'permission': _serialize_field_permission(getattr(f, 'permission', None)),
            })
        for a in (meta.actions or []):
            result['actions'].append({
                'id': getattr(a, 'id', ''),
                'name': getattr(a, 'name', ''),
                'label': getattr(a, 'label', ''),
                'type': getattr(a, 'type', ''),
                # [FIX BUG-V051.2 2026-07-10 dev agent] HTTP method/path, 前端调用 API 用
                'method': getattr(a, 'method', ''),
                'path': getattr(a, 'path', ''),
                'description': getattr(a, 'description', ''),
            })
        # [FIX BUG-V051.2 2026-07-10 dev agent] 关联支持 dict (新格式) 和 list (旧格式) 两种存储
        assoc_list = _normalize_associations(getattr(meta, 'associations', None))
        for assoc in assoc_list:
            result['associations'].append({
                'id': getattr(assoc, 'id', None) or getattr(assoc, 'name', ''),
                'name': getattr(assoc, 'name', ''),
                'label': getattr(assoc, 'label', '') or getattr(assoc, 'name', ''),
                'relation_type': _enum_to_str(getattr(assoc, 'relation_type', None)),
                'target_object': getattr(assoc, 'target_object', '') or getattr(assoc, 'target_type', ''),
                'target_type': getattr(assoc, 'target_type', '') or getattr(assoc, 'target_object', ''),
                'source_field': getattr(assoc, 'source_field', ''),
                'target_field': getattr(assoc, 'target_field', 'id'),
                'cardinality': getattr(assoc, 'cardinality', '1:N'),
                'display_format': getattr(assoc, 'display_format', None),
                'cascade_delete': getattr(assoc, 'cascade_delete', False),
            })
        # [FIX BUG-V046 2026-07-04 dev agent] 暴露 audit.history 配置
        # 让前端 HistorySection 读取 audit.history.excluded_child_object_types
        # 并传给后端 audit_api
        audit_config = getattr(meta, 'audit', None)
        if audit_config is not None:
            history_config = getattr(audit_config, 'history', None)
            if history_config is not None:
                excluded = getattr(history_config, 'excluded_child_object_types', None) or []
                result['audit_history_excluded_child_object_types'] = list(excluded)
            # [FIX BUG-V051.2 2026-07-10 dev agent] 暴露 audit.enabled
            result['audit_enabled'] = getattr(audit_config, 'enabled', True)
        return result


# ────────────────────────────────────────────
# [FIX BUG-V051.2 2026-07-10 dev agent] 字段级序列化辅助
# 原因: MetaObject/MetaField 等 dataclass 包含 enum 类型, JSON 序列化时
#       str() 包装 enum; 用 getattr 防御性兜底, 缺字段不崩
# ────────────────────────────────────────────

def _enum_to_str(value):
    """把 enum 转为字符串, 其它原样返回 (None 保持 None)"""
    if value is None:
        return None
    if hasattr(value, 'name') and hasattr(value, 'value'):
        return str(value.name) if isinstance(value.name, str) else str(value.value)
    return value


def _normalize_associations(associations):
    """[FIX BUG-V051.2] 兼容 associations 为 dict 或 list"""
    if associations is None:
        return []
    if isinstance(associations, dict):
        result = []
        for name, defn in associations.items():
            if isinstance(defn, dict):
                # dict 形式: {name, target_type, source_field, ...}
                if 'name' not in defn:
                    defn = {**defn, 'name': name}
                result.append(defn)
            else:
                # dataclass 形式
                result.append(defn)
        return result
    return list(associations)


def _serialize_semantics(semantics) -> dict:
    """[FIX BUG-V051.2] SemanticAnnotation → dict"""
    if semantics is None:
        return {}
    result = {}
    for attr in ('primary_key', 'business_key', 'primary_name', 'status',
                 'foreign_key', 'hierarchical', 'unique_scope', 'name',
                 'description', 'created_at', 'updated_at', 'owner',
                 'searchable', 'sortable', 'filterable'):
        try:
            val = getattr(semantics, attr, None)
        except AttributeError:
            continue
        if val is not None and val is not False:
            result[attr] = val
    return result


def _serialize_field_ui(ui) -> dict:
    """[FIX BUG-V051.2] UIAnnotation → dict"""
    if ui is None:
        return {}
    result = {}
    for attr in ('visible', 'editable', 'required', 'show_in_list',
                 'show_in_detail', 'show_in_form', 'hidden_in_form',
                 'read_only', 'placeholder', 'help_text', 'width',
                 'widget', 'group', 'tab', 'section', 'order',
                 'formatter', 'parser', 'icon', 'color'):
        try:
            val = getattr(ui, attr, None)
        except AttributeError:
            continue
        if val is not None:
            result[attr] = val
    return result


def _serialize_field_permission(perm) -> dict:
    """[FIX BUG-V051.2] PermissionAnnotation → dict"""
    if perm is None:
        return {}
    result = {}
    for attr in ('read', 'write', 'create', 'delete', 'export', 'roles'):
        try:
            val = getattr(perm, attr, None)
        except AttributeError:
            continue
        if val is not None:
            result[attr] = val
    return result


def _serialize_ui_view_config(cfg) -> dict:
    """[FIX BUG-V051.2] UIViewConfig → dict"""
    if cfg is None:
        return {}
    result = {}
    for view_name in ('list', 'detail', 'form'):
        sub = getattr(cfg, view_name, None)
        if sub is None:
            continue
        if hasattr(sub, '__dict__'):
            result[view_name] = dict(sub.__dict__) if sub.__dict__ else None
        elif isinstance(sub, dict):
            result[view_name] = sub
        else:
            result[view_name] = sub
    return result


def _serialize_ui_view_configs(cfgs) -> dict:
    """[FIX BUG-V051.2] 多视图配置"""
    return {name: _serialize_ui_view_config(cfg) for name, cfg in (cfgs or {}).items()}


def _serialize_deletability(cfg) -> dict:
    """[FIX BUG-V051.2] DeletabilityConfig → dict"""
    if cfg is None:
        return {}
    return {
        'condition': getattr(cfg, 'condition', ''),
        'message': getattr(cfg, 'message', ''),
    }


def _serialize_addability(cfg) -> dict:
    """[FIX BUG-V051.2] AddabilityConfig → dict"""
    if cfg is None:
        return {}
    return {
        'condition': getattr(cfg, 'condition', ''),
        'message': getattr(cfg, 'message', ''),
    }
