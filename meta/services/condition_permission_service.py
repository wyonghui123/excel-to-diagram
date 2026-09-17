# -*- coding: utf-8 -*-
"""
条件型权限服务

Oracle 风格混合权限模型 + 用友BIP特性：
- 条件型权限规则（替代实例型 resource_id）
- Owner 自动权限
- 禁止权优先原则
- 向下继承（天然实现）
- 向上传播
- 员工数据权限模板
- 分析型权限扩展
"""

import json
import logging
import os
import re
from typing import Dict, List, Any, Optional, Tuple
from meta.services.condition_evaluator import ConditionEvaluator
from meta.services.permission_dimension_engine import (
    RESOURCE_TABLE_MAP as _DIM_TABLES,
    CODE_FIELD_MAP as _DIM_CODE_FIELDS,
)

logger = logging.getLogger(__name__)


RESOURCE_TABLE_MAP = {
    'product': 'products',
    'version': 'versions',
    'domain': 'domains',
    'sub_domain': 'sub_domains',
    'service_module': 'service_modules',
    'business_object': 'business_objects',
    # [Spec 19 M2 2026-09-05] 组织管理委托授权：组织/用户纳入资源矩阵
    # 语义：行级规则 = 管理（manage）该行对应组织子树/子树内用户，非普通读写
    'org': 'orgs',
    'user': 'users',
}

CHILD_TYPE_MAP = {
    'product': ['version'],
    'version': ['domain'],
    'domain': ['sub_domain'],
    'sub_domain': ['service_module'],
    'service_module': ['business_object'],
    # [Spec 19 M2] org 自引用（parent_id），user 无子类型不参与继承
    'org': ['org'],
}

PARENT_FIELD_MAP = {
    'version': 'product_id',
    'domain': 'version_id',
    'sub_domain': 'domain_id',
    'service_module': 'sub_domain_id',
    'business_object': 'service_module_id',
    # [Spec 19 M2] org 自引用父字段；user 无父字段（用户行范围由所属组织解析）
    'org': 'parent_id',
}

LEVEL_ORDER = {'none': 0, 'read': 1, 'write': 2, 'admin': 3}

# [Spec 19 M2 FR-002 2026-09-05] org/user 行级规则禁止 '*' 通配：
#   '*' 在 OrgAdminScopeService 中解释为全组织管理范围（= 无限制委托），
#   仅允许全局管理员内置角色（'*' 功能码）持有，绝不通过规则表授予。
#   命中即拒绝保存（400），绝不静默降级。
WILDCARD_FORBIDDEN_RTS = {'org', 'user'}


# ============================================================================
# [Spec 20 Task 9-B 2026-09-11] 条件规则业务键锚点展开
#
# 背景: ConditionRuleBuilder FK picker 可产出业务键 code 值
#   ("domain_id IN (64, 'SCM')")。ConditionEvaluator per-record 求值
#   str(88) not in ['64','SCM'] → 锚点静默失效:
#   IN = fail-closed (选了全丢), NOT IN = fail-open (该排除的没排除)。
# 展开: rule-load 时把 code 解析为当刻 ID 快照 (与 dimension scope 锚点同源
#   _resolve_bizkeys), 展开 结果纯数字 → per-record 求值 / predicate_to_sql_where
#   两条执行路径同时修复。
#
# 语义约定 (对齐 Spec 20 §4.2 fail-closed):
#   - 开关 OFF 且条件含锚点 → 整条规则失效 ('1=0', 绝不回退 fail-open)
#   - 锚点 0 命中 → 该 token 丢弃 (等价于匹配空集, 保守不放大)
#     IN 全空 → '1=0'; NOT IN 全空 → 谓词恒真 → 删除
#   - field='code' 自引用: resource.code 字符串原生匹配 (天然跨版本动态), 不展开
#   - 顶级 OR / 嵌套括号条件: 保守跳过 (保持现状, 不引入语义漂移)
# ============================================================================

_RE_IN_PREDICATE = re.compile(r'^(\w+)\s+(NOT\s+IN|IN)\s*\(([^)]*)\)$', re.IGNORECASE)
_RE_CMP_PREDICATE = re.compile(r"^(\w+)\s*(=|!=)\s*'([^']*)'$")


def _is_numeric_token(token: str) -> bool:
    return bool(token) and token.lstrip('-').isdigit()


# ============================================================================
# [Spec 20 v5 字段即模式 2026-09-12] FK code 虚拟字段白名单
#
# 背景: version_code 等虚拟解析字段 (storage=virtual + redundancy.type=resolution)
#   此前被 get_resource_field_metadata 的 virtual 过滤拦截 → 条件字段无入口,
#   FK 业务键锚定只能内联在 FK id 字段的双 Tab (宽写回例外)。
#   白名单放行后: field=version_code → bizkey_only 直出目标对象业务键列表,
#   展开/求值时左值改写 version_code IN (...) → version_id IN (...)。
#
# 通用性: 判据全部来自 YAML semantics.redundancy 声明, 零命名约定推断/维度硬编码:
#   storage == virtual AND 字段名 *_code
#   AND redundancy.type == 'resolution'
#   AND redundancy.source_field 以 _id 结尾
#   AND (dim = source_field 去 _id) 已注册维度表 (锚定对象必须有业务键解析引擎)
# relationship.source_bo_code 被排除: dim='source_bo' 非注册维度。
# ============================================================================

_FK_CODE_FIELD_MAP_CACHE: Dict[str, Dict[str, Tuple[str, str]]] = {}


def _fk_code_field_map(resource_type: str) -> Dict[str, Tuple[str, str]]:
    """resource_type → {code_field: (dim, physical_fk_col)}；domain → {'version_code': ('version', 'version_id')}"""
    cached = _FK_CODE_FIELD_MAP_CACHE.get(resource_type)
    if cached is not None:
        return cached
    mapping: Dict[str, Tuple[str, str]] = {}
    try:
        from meta.core.models import registry, FieldStorage
        if not registry._initialized:
            schema_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas')
            if os.path.exists(schema_dir):
                registry.reload(schema_dir)
        meta_obj = registry.get(resource_type)
        if meta_obj:
            for field in meta_obj.fields:
                if field.storage != FieldStorage.VIRTUAL:
                    continue
                if not field.id.endswith('_code'):
                    continue
                red = (field.semantics.redundancy or {}) if field.semantics else {}
                if not isinstance(red, dict) or red.get('type') != 'resolution':
                    continue
                src = str(red.get('source_field') or '')
                if not src.endswith('_id'):
                    continue
                dim = src[:-3]
                if dim not in _DIM_TABLES:
                    continue
                mapping[field.id] = (dim, src)
    except Exception as e:
        logger.warning(f'[Spec20-FKCODE] field map build failed for {resource_type}: {e}')
    _FK_CODE_FIELD_MAP_CACHE[resource_type] = mapping
    return mapping


def _anchor_target_of_field(field: str, resource_type: str) -> Optional[Tuple[str, str, bool]]:
    """条件字段 → (锚定维度, 物理左值列, 数字token是否按id)。无锚定语义返回 None。

    [Spec 20 v5] FK code 字段 (version_code): 值域纯业务键 → 数字 token 也按 code
    解析 (numeric_is_id=False), 展开输出左值改写为物理 FK 列 (version_id)。
    其余字段 numeric_is_id=True, 行为与旧逻辑完全一致。
    """
    fk = _fk_code_field_map(resource_type).get(field)
    if fk:
        return fk[0], fk[1], False
    if field == 'code':
        return None  # 字符串原生匹配, 保持跨版本动态
    if field == 'id':
        return (resource_type, 'id', True) if resource_type in _DIM_TABLES else None
    if field.endswith('_id'):
        dim = field[:-3]
        if dim in _DIM_TABLES:
            return dim, field, True
    return None


def _resolve_anchor_ids(ds, dim: str, anchors: List[str]) -> Dict[str, set]:
    """业务键 → 命中 ID 集合 (复用 dimension scope 引擎同源解析)"""
    if not anchors:
        return {}
    from meta.services.dimension_scope_engine import DimensionScopeEngine
    return DimensionScopeEngine(ds)._resolve_bizkeys(dim, anchors)


# [Spec 20 v2 2026-09-12] 锚点展开谓词注册表 — 单一调度点, 新增谓词只加一行:
#   - kind:     'in' (多值 IN/NOT IN) | 'cmp' (单值 =/!=, 展开后转 IN/NOT IN)
#   - regex:    匹配单谓词的命名捕获组 (field, op, value(s))
#   - tokens:   从 value(s) 提取 token 列表 (剥引号/逗号)
#   - empty_in: 锚点零命中时空集展开的目标操作符 ('1=0' / '1=1')
def _pred_in_tokens(part: str):
    m = _RE_IN_PREDICATE.match(part.strip())
    if not m:
        return None
    field, op, inner = m.group(1), m.group(2).upper(), m.group(3)
    toks = [t.strip().strip("'\"") for t in inner.split(',') if t.strip()]
    return field, op, toks


def _pred_cmp_tokens(part: str):
    m = _RE_CMP_PREDICATE.match(part.strip())
    if not m:
        return None
    field, op, val = m.group(1), m.group(2), m.group(3)
    toks = [val] if val else []
    # cmp 谓词展开后, = → IN / != → NOT IN (锚点零命中时反过来)
    target_op = 'IN' if op == '=' else 'NOT IN'
    return field, op, toks, target_op


ANCHOR_PREDICATE_HANDLERS = (
    {'name': 'in', 'match': _pred_in_tokens, 'empty_op_for': {'IN': '1=0', 'NOT IN': '1=1'}},
    {'name': 'cmp', 'match': _pred_cmp_tokens,
     'empty_op_for': {'=': '1=0', '!=': '1=1'}, 'target_op': True},
)


def _predicate_has_anchor(part: str, resource_type: str) -> bool:
    """单谓词是否含业务键锚点 token (用于 flag OFF fail-closed 判定)"""
    for h in ANCHOR_PREDICATE_HANDLERS:
        m = h['match'](part)
        if not m:
            continue
        field = m[0]
        toks = m[2]
        target = _anchor_target_of_field(field, resource_type)
        if not target:
            return False
        numeric_is_id = target[2]
        if not numeric_is_id:
            return bool(toks)  # FK code 字段: 值域纯业务键, 任意 token (含数字) 均为锚点
        return any(t for t in toks if not _is_numeric_token(t))
    return False


def _expand_anchor_predicate(part: str, resource_type: str, ds) -> str:
    """展开单谓词锚点。返回 '1=1' 表示恒真 (调用方删除该谓词)。"""
    part = part.strip()
    for h in ANCHOR_PREDICATE_HANDLERS:
        m = h['match'](part)
        if not m:
            continue
        if h['name'] == 'in':
            field, op, tokens = m
            target = _anchor_target_of_field(field, resource_type)
            if not target:
                return part
            dim, physical, numeric_is_id = target
            if not tokens:
                return part
            if numeric_is_id:
                numerics = [t for t in tokens if _is_numeric_token(t)]
                anchors = [t for t in tokens if not _is_numeric_token(t)]
            else:
                # [Spec 20 v5] FK code 字段: 值域纯业务键, 数字 token 也按 code 解析
                numerics = []
                anchors = list(tokens)
            if not anchors:
                return part  # 纯数字原样 (零开销快速路径)
            resolved = _resolve_anchor_ids(ds, dim, anchors)
            ids = {int(i) for c in anchors for i in resolved.get(c, set())}
            if numeric_is_id:
                ids |= {int(n) for n in numerics}
            if not ids:
                return h['empty_op_for'].get(op, '1=0')
            # 左值改写: version_code IN ('v01') → version_id IN (10, 20)
            return f"{physical} {op} ({', '.join(str(i) for i in sorted(ids))})"

        if h['name'] == 'cmp':
            field, op, tokens, target_op = m
            if not tokens:
                return part
            target = _anchor_target_of_field(field, resource_type)
            if not target:
                return part
            dim, physical, numeric_is_id = target
            if numeric_is_id and _is_numeric_token(tokens[0]):
                return part
            resolved = _resolve_anchor_ids(ds, dim, tokens)
            ids = {int(i) for i in resolved.get(tokens[0], set())}
            if not ids:
                return h['empty_op_for'].get(op, '1=0')
            return f"{physical} {target_op} ({', '.join(str(i) for i in sorted(ids))})"
    return part


def _expand_condition_anchors(ds, condition: str, resource_type: str) -> str:
    """条件表达式业务键锚点展开 (rule-load 时一次性执行)

    Args:
        ds:            数据源 (供 _resolve_bizkeys 查询)
        condition:     条件表达式, 如 "domain_id IN (64, 'SCM') AND status = 'active'"
        resource_type: 规则的资源类型 (id 自引用时锚定对象)

    Returns:
        展开后的纯数字表达式; 开关 OFF 且含锚点 → '1=0' (fail-closed)
    """
    if not condition or not condition.strip():
        return condition
    cond = condition.strip()
    if cond in ('*', '1=1', '1=0') or cond.startswith('{'):
        return cond
    if re.search(r'\s+OR\s+', cond, re.IGNORECASE):
        return cond  # 顶级 OR: 保守跳过

    parts = [p.strip() for p in re.split(r'\s+AND\s+', cond, flags=re.IGNORECASE) if p.strip()]
    if not any(_predicate_has_anchor(p, resource_type) for p in parts):
        return condition  # 无锚点原样返回 (零开销)

    from meta.services.dimension_scope_engine import DimensionScopeEngine
    if not DimensionScopeEngine._bizkey_enabled():
        logger.warning(
            '[Spec20-BIZKEY] flag OFF: condition rule with anchor tokens → inert (1=0), '
            f'resource_type={resource_type}, condition={condition[:120]}')
        return '1=0'

    out_parts = []
    for p in parts:
        expanded = _expand_anchor_predicate(p, resource_type, ds)
        if expanded == '1=1':
            continue  # 恒真谓词删除
        if expanded == '1=0':
            return '1=0'  # AND 短路
        out_parts.append(expanded)
    if not out_parts:
        return '1=1'
    return ' AND '.join(out_parts)


def check_condition_wildcard(resource_type, condition) -> Optional[str]:
    """校验 org/user 行级条件禁用 '*' 通配。返回错误消息（None=通过）。"""
    if resource_type in WILDCARD_FORBIDDEN_RTS and (condition or '').strip() == '*':
        return (
            f"资源类型 {resource_type} 的数据范围条件禁止 '*' 通配"
            "（通配 = 全部组织管理权，仅限全局管理员内置权限），请绑定具体组织节点"
        )
    return None

# [2026-08-27] 系统基线字段（隐式安全基线，不暴露为逐条业务条件）
#   - owner_id (FK→user): 数据归属，由系统层保证（product chain 追溯 owner）
#   - visibility (string 枚举): 按角色可见等级放行，映射维护在角色模板层
#   语义跨所有资源一致，不适合重复配置（防重复配置/语义漂移/越权校验）。
#   命中即静默跳过，不出现在条件字段下拉与高级模式字段参考。
BASELINE_FIELDS_EXCLUDED = {'owner_id', 'visibility'}


class ConditionPermissionService:
    """条件型权限服务"""

    def __init__(self, data_source):
        self.ds = data_source
        self.evaluator = ConditionEvaluator()

    def check_permission(
        self,
        user_id: int,
        resource_type: str,
        resource_id: int,
        action: str = 'read'
    ) -> Dict[str, Any]:
        """
        条件型权限检查主入口

        优先级：
        1. Owner 权限（最高优先级）
        2. 禁止权限（用友BIP禁止权优先原则）
        3. 条件型权限规则
        4. 向上传播权限
        """
        required_level = self._action_to_level(action)

        if self._is_owner(user_id, resource_type, resource_id):
            return {
                'allowed': True,
                'permission_level': 'admin',
                'source': 'owner',
                'matched_condition': None,
            }

        if self._check_denied_rules(user_id, resource_type, resource_id):
            return {
                'allowed': False,
                'permission_level': 'none',
                'source': 'denied',
                'matched_condition': None,
            }

        condition_result = self._check_condition_rules(user_id, resource_type, resource_id, required_level)
        if condition_result['allowed']:
            return condition_result

        parent_result = self._check_parent_visibility(user_id, resource_type, resource_id)
        if parent_result['allowed']:
            return parent_result

        return {
            'allowed': False,
            'permission_level': 'none',
            'source': None,
            'matched_condition': None,
        }

    def get_effective_permission_level(
        self,
        user_id: int,
        resource_type: str,
        resource_id: int
    ) -> str:
        """兼容接口：获取有效权限级别"""
        result = self.check_permission(user_id, resource_type, resource_id, 'read')
        return result['permission_level']

    def get_authorized_resource_ids(
        self,
        user_id: int,
        resource_type: str,
        action: str = 'read'
    ) -> Optional[List[int]]:
        """
        获取用户有权访问的资源ID列表

        Returns:
            None: 无限制（有通配符权限）
            []: 无权限
            [id1, id2, ...]: 限定范围
        """
        required_level = self._action_to_level(action)
        rules = self._get_user_rules(user_id, resource_type)

        if not rules:
            return []

        where_clauses = []
        for rule in rules:
            if rule.get('is_denied'):
                continue
            if LEVEL_ORDER.get(rule['permission_level'], 0) < LEVEL_ORDER.get(required_level, 0):
                continue

            sql_where = self.evaluator.predicate_to_sql_where(rule['condition'])
            if sql_where:
                where_clauses.append(f"({sql_where})")

        if not where_clauses:
            return []

        table_name = RESOURCE_TABLE_MAP.get(resource_type)
        if not table_name:
            return None

        combined = ' OR '.join(where_clauses)
        try:
            cursor = self.ds.execute(f"SELECT id FROM {table_name} WHERE {combined}")
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []

    # ========== CRUD (legacy permission_rules 表) ==========

    def create_rule(self, data: Dict[str, Any]) -> Optional[int]:
        """创建权限规则"""
        try:
            analysis_mode = data.get('analysis_mode')
            if isinstance(analysis_mode, dict):
                analysis_mode = json.dumps(analysis_mode, ensure_ascii=False)

            cursor = self.ds.execute(
                """INSERT INTO permission_rules
                   (permission_set_id, resource_type, condition, permission_level, is_denied,
                    inherit_to_children, propagate_to_parents, analysis_mode, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    data['permission_set_id'],
                    data['resource_type'],
                    data['condition'],
                    data.get('permission_level', 'read'),
                    1 if data.get('is_denied') else 0,
                    1 if data.get('inherit_to_children', True) else 0,
                    1 if data.get('propagate_to_parents', True) else 0,
                    analysis_mode,
                    data.get('created_by'),
                ]
            )
            return cursor.lastrowid
        except Exception as e:
            print(f"Error creating permission rule: {e}")
            return None

    def update_rule(self, rule_id: int, data: Dict[str, Any]) -> bool:
        """更新权限规则"""
        try:
            sets = []
            params = []
            for field in ['condition', 'permission_level', 'is_denied', 'inherit_to_children',
                          'propagate_to_parents', 'analysis_mode']:
                if field in data:
                    val = data[field]
                    if field == 'is_denied':
                        val = 1 if val else 0
                    elif field == 'inherit_to_children':
                        val = 1 if val else 0
                    elif field == 'propagate_to_parents':
                        val = 1 if val else 0
                    elif field == 'analysis_mode' and isinstance(val, dict):
                        val = json.dumps(val, ensure_ascii=False)
                    sets.append(f"{field} = ?")
                    params.append(val)

            if not sets:
                return True

            sets.append("updated_at = CURRENT_TIMESTAMP")
            params.append(rule_id)
            self.ds.execute(
                f"UPDATE permission_rules SET {', '.join(sets)} WHERE rowid = ?",
                params
            )
            return True
        except Exception as e:
            print(f"Error updating permission rule: {e}")
            return False

    def delete_rule(self, rule_id: int) -> bool:
        """删除权限规则"""
        try:
            self.ds.execute("DELETE FROM permission_rules WHERE rowid = ?", [rule_id])
            return True
        except Exception:
            return False

    def get_rules_by_role(self, permission_set_id: int, resource_type: Optional[str] = None) -> List[Dict]:
        """获取角色的权限规则"""
        if resource_type:
            cursor = self.ds.execute(
                "SELECT rowid AS id, * FROM permission_rules WHERE permission_set_id = ? AND resource_type = ? ORDER BY resource_type",
                [permission_set_id, resource_type]
            )
        else:
            cursor = self.ds.execute(
                "SELECT rowid AS id, * FROM permission_rules WHERE permission_set_id = ? ORDER BY resource_type",
                [permission_set_id]
            )
        rules = self._rows_to_dicts(cursor)
        
        # 为每条规则生成友好显示
        for rule in rules:
            rule['friendly_condition'] = self._generate_friendly_condition(rule.get('condition', ''))
        
        return rules

    def get_all_rules(self, resource_type: Optional[str] = None) -> List[Dict]:
        """获取所有权限规则"""
        if resource_type:
            cursor = self.ds.execute(
                "SELECT rowid AS id, * FROM permission_rules WHERE resource_type = ? ORDER BY permission_set_id, rowid",
                [resource_type]
            )
        else:
            cursor = self.ds.execute(
                "SELECT rowid AS id, * FROM permission_rules ORDER BY permission_set_id, resource_type, rowid"
            )
        rules = self._rows_to_dicts(cursor)
        
        # 为每条规则生成友好显示
        for rule in rules:
            rule['friendly_condition'] = self._generate_friendly_condition(rule.get('condition', ''))
        
        return rules

    # ========== Unified CRUD (data_permission_rules 统一表, P11 Phase 11) ==========
    # rule_type 枚举: condition | dimension | owner | visibility | prohibition
    # Spec: spec-permission-system-unification-2026-07-19 §3.5 / §8.3 P3-T1 / §8.11 P11

    VALID_RULE_TYPES = {'condition', 'dimension', 'owner', 'visibility', 'prohibition'}

    def _ensure_unified_table(self):
        """[P11] 确保 data_permission_rules 表存在 (lazy init, 幂等).

        Phase 3 schema 定义了该表, 但部分测试 DB / 旧实例可能未应用 generated_schema.sql.
        本方法在首次访问时自动建表, 避免迁移脚本依赖.
        """
        try:
            self.ds.execute("""
                CREATE TABLE IF NOT EXISTS data_permission_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    permission_set_id INTEGER NOT NULL,
                    rule_type VARCHAR(50) NOT NULL DEFAULT 'condition',
                    resource_type VARCHAR(200),
                    dimension_code VARCHAR(200),
                    condition TEXT,
                    condition_display TEXT,
                    scope_mode VARCHAR(50) DEFAULT 'include',
                    permission_level VARCHAR(50) DEFAULT 'read',
                    is_denied INTEGER DEFAULT 0,
                    inherit_to_children INTEGER DEFAULT 1,
                    propagate_to_parents INTEGER DEFAULT 0,
                    expires_at VARCHAR(50),
                    source_table VARCHAR(100),
                    source_id INTEGER,
                    created_at VARCHAR(200),
                    updated_at VARCHAR(200)
                )
            """)
            # [v56 2026-08-27] 已存在的表补列（幂等）：人类可读条件描述
            try:
                self.ds.execute(
                    "ALTER TABLE data_permission_rules ADD COLUMN condition_display TEXT"
                )
            except Exception:
                pass  # 列已存在
            # [2026-09-14 prod 彩排修正] 存量表补 expires_at（Spec 19 M2 委托有效期），
            # 与 v084 迁移对齐；lazy create 新表 DDL 已含该列，ALTER 仅对存量表生效
            try:
                self.ds.execute(
                    "ALTER TABLE data_permission_rules ADD COLUMN expires_at VARCHAR(50)"
                )
            except Exception:
                pass  # 列已存在
        except Exception as e:
            print(f"[P11] _ensure_unified_table (ignore if exists): {e}")

    def create_unified_rule(self, data: Dict[str, Any]) -> Optional[int]:
        """[P11] 创建统一权限规则 (写入 data_permission_rules 表)

        支持 rule_type 字段区分 5 种规则类型, 默认 'condition' (向后兼容).
        """
        try:
            self._ensure_unified_table()
            # [Spec 19 M2 FR-002] org/user 行禁 '*' 通配（防全组织管理权经规则表泄漏）
            wildcard_err = check_condition_wildcard(
                data.get('resource_type'), data.get('condition'))
            if wildcard_err:
                print(f"[Spec19 FR-002] {wildcard_err}")
                return None
            rule_type = data.get('rule_type', 'condition')
            if rule_type not in self.VALID_RULE_TYPES:
                rule_type = 'condition'

            cursor = self.ds.execute(
                """INSERT INTO data_permission_rules
                   (permission_set_id, rule_type, resource_type, dimension_code, condition,
                    condition_display,
                    scope_mode, permission_level, is_denied,
                    inherit_to_children, propagate_to_parents, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                [
                    data['permission_set_id'],
                    rule_type,
                    data.get('resource_type'),
                    data.get('dimension_code'),
                    data.get('condition'),
                    data.get('condition_display'),
                    data.get('scope_mode', 'include'),
                    data.get('permission_level', 'read'),
                    1 if data.get('is_denied') else 0,
                    1 if data.get('inherit_to_children', True) else 0,
                    1 if data.get('propagate_to_parents', False) else 0,
                ]
            )
            return cursor.lastrowid
        except Exception as e:
            print(f"[P11] Error creating unified permission rule: {e}")
            return None

    def get_unified_rules_by_role(
        self,
        permission_set_id: int,
        rule_type: Optional[str] = None,
    ) -> List[Dict]:
        """[P11] 获取角色的统一权限规则 (从 data_permission_rules 表)

        Args:
            permission_set_id: 角色 ID
            rule_type: 可选, 按规则类型过滤 (condition/dimension/owner/visibility/prohibition)
        """
        self._ensure_unified_table()
        if rule_type:
            cursor = self.ds.execute(
                """SELECT * FROM data_permission_rules
                   WHERE permission_set_id = ? AND rule_type = ?
                   ORDER BY id""",
                [permission_set_id, rule_type]
            )
        else:
            cursor = self.ds.execute(
                """SELECT * FROM data_permission_rules
                   WHERE permission_set_id = ?
                   ORDER BY rule_type, id""",
                [permission_set_id]
            )
        rules = self._rows_to_dicts(cursor)
        # 补齐 friendly_condition (复用现有逻辑)
        for rule in rules:
            rule['friendly_condition'] = self._generate_friendly_condition(
                rule.get('condition', '') or ''
            )
        return rules

    def get_all_unified_rules(
        self,
        rule_type: Optional[str] = None,
    ) -> List[Dict]:
        """[P11] 获取所有统一权限规则 (从 data_permission_rules 表)"""
        self._ensure_unified_table()
        if rule_type:
            cursor = self.ds.execute(
                """SELECT * FROM data_permission_rules
                   WHERE rule_type = ?
                   ORDER BY permission_set_id, id""",
                [rule_type]
            )
        else:
            cursor = self.ds.execute(
                """SELECT * FROM data_permission_rules
                   ORDER BY permission_set_id, rule_type, id"""
            )
        rules = self._rows_to_dicts(cursor)
        for rule in rules:
            rule['friendly_condition'] = self._generate_friendly_condition(
                rule.get('condition', '') or ''
            )
        return rules

    def update_unified_rule(self, rule_id: int, data: Dict[str, Any]) -> bool:
        """[v48 2026-08-27] 更新统一权限规则 (写 data_permission_rules 表)

        背景：v2 PUT 端点此前调用 update_rule()，其 SQL 指向 legacy 表
        permission_rules，而列表查询读 data_permission_rules —— 导致
        "变更配置条件保存后刷新仍是旧值"（更新根本没落到统一表）。

        安全限定：data 中若带 permission_set_id / resource_type / rule_type，
        会作为 WHERE 条件二次校验，防止 id 跨表误更新。
        """
        self._ensure_unified_table()
        try:
            # [Spec 19 M2 FR-002] org/user 行禁 '*' 通配。
            # update 载荷可能不带 resource_type → 按 rule_id 回查统一表补齐。
            if 'condition' in data:
                rt = data.get('resource_type')
                if rt not in WILDCARD_FORBIDDEN_RTS:
                    try:
                        row = self.ds.execute(
                            "SELECT resource_type FROM data_permission_rules WHERE id = ?",
                            [rule_id],
                        ).fetchone()
                        rt = row[0] if row else None
                    except Exception:
                        rt = None
                wildcard_err = check_condition_wildcard(rt, data.get('condition'))
                if wildcard_err:
                    print(f"[Spec19 FR-002] {wildcard_err}")
                    return False
            sets = []
            params = []
            for field in ['condition', 'condition_display', 'permission_level', 'is_denied',
                            'inherit_to_children', 'propagate_to_parents', 'scope_mode']:
                if field in data:
                    val = data[field]
                    if field in ('is_denied', 'inherit_to_children', 'propagate_to_parents'):
                        val = 1 if val else 0
                    sets.append(f"{field} = ?")
                    params.append(val)
            if not sets:
                return True
            sets.append("updated_at = CURRENT_TIMESTAMP")
            where = ["id = ?"]
            params.append(rule_id)
            # 安全限定条件（调用方传了才校验）
            for wf in ['permission_set_id', 'resource_type', 'rule_type']:
                if data.get(wf) not in (None, ''):
                    where.append(f"{wf} = ?")
                    params.append(data[wf])
            cursor = self.ds.execute(
                f"UPDATE data_permission_rules SET {', '.join(sets)} WHERE {' AND '.join(where)}",
                params
            )
            # [v48] rowcount=0 表示该 id 不在统一表（legacy 数据）→ 返回 False 让调用方回退
            try:
                return (cursor.rowcount or 0) > 0
            except Exception:
                return True
        except Exception as e:
            print(f"[v48] Error updating unified permission rule: {e}")
            return False

    def delete_unified_rule(self, rule_id: int) -> bool:
        """[P11] 删除统一权限规则"""
        self._ensure_unified_table()
        try:
            self.ds.execute(
                "DELETE FROM data_permission_rules WHERE id = ?",
                [rule_id]
            )
            return True
        except Exception:
            return False

    def _get_dimension_field_map(self) -> Dict[str, Dict]:
        """获取维度字段到维度信息的映射（从 hierarchies.yaml）"""
        import os
        import yaml
        schema_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas')
        hierarchies_path = os.path.join(schema_dir, 'hierarchies.yaml')

        result = {}
        if os.path.exists(hierarchies_path):
            try:
                with open(hierarchies_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    for dim in data.get('dimensions', []):
                        obj = dim.get('object', '')
                        filter_param = dim.get('filter_param', '')
                        if obj and filter_param:
                            result[filter_param] = {
                                'code': dim.get('id'),
                                'name': dim.get('name'),
                                'field': filter_param
                            }
            except Exception as e:
                print(f"[Warning] Failed to load hierarchies.yaml: {e}")

        return result

    def _generate_friendly_condition(self, condition: str) -> str:
        """将技术条件表达式转换为用户友好的显示"""
        if not condition:
            return ''

        # 获取维度映射
        dim_map = self._get_dimension_field_map()

        # 第一步：替换字段名为维度名称
        result = condition
        for field, dim_info in dim_map.items():
            dim_name = dim_info.get('name', field)
            result = result.replace(field, dim_name)

        # 第二步：先替换操作符为中文化（这样后续才能正确匹配）
        result = result.replace(' = ', ' 等于 ')
        result = result.replace(' != ', ' 不等于 ')
        result = result.replace(' IN ', ' 包含于 ')
        result = result.replace(' AND ', ' 且 ')
        result = result.replace(' OR ', ' 或 ')

        # 第三步：解析并替换ID值为业务名称（现在可以匹配中文操作符了）
        import re
        patterns = [
            r'(\S+)\s+等于\s+(\d+)',           # 单值等于
            r'(\S+)\s+不等于\s+(\d+)',          # 单值不等于
            r'(\S+)\s+包含于\s+\(([^)]+)\)',    # 多值包含于
        ]

        for pattern in patterns:
            matches = re.findall(pattern, result)
            for match in matches:
                if len(match) == 2:
                    dim_name, value_or_values = match
                    field = self._find_field_by_dim_name(dim_name, dim_map)

                    # 判断是单值还是多值
                    # "包含于"总是多值（即使只有一个值），"等于/不等于"是单值
                    is_in_condition = '包含于' in result[result.find(dim_name):result.find(dim_name)+20]

                    if is_in_condition and field:
                        # 多值处理（IN条件）
                        values = [v.strip() for v in value_or_values.split(',')]
                        display_names = []
                        for v in values:
                            if v.strip().isdigit():
                                name = self._get_display_name_for_id(field, int(v.strip()))
                                display_names.append(name if name else v.strip())
                            else:
                                display_names.append(v.strip())
                        if display_names:
                            new_values = ', '.join(display_names)
                            result = re.sub(
                                rf'{re.escape(dim_name)}\s+包含于\s+\([^)]+\)',
                                f'{dim_name} 包含于 ({new_values})',
                                result,
                                count=1
                            )
                    elif field and value_or_values.isdigit():
                        # 单值处理（=/!= 条件）
                        display_name = self._get_display_name_for_id(field, int(value_or_values))
                        if display_name:
                            result = re.sub(
                                rf'{re.escape(dim_name)}\s+等于\s+{value_or_values}',
                                f'{dim_name} 等于 {display_name}',
                                result
                            )
                            result = re.sub(
                                rf'{re.escape(dim_name)}\s+不等于\s+{value_or_values}',
                                f'{dim_name} 不等于 {display_name}',
                                result
                            )

        return result

    def _find_field_by_dim_name(self, dim_name: str, dim_map: Dict) -> Optional[str]:
        """根据维度名称查找对应的技术字段名"""
        for field, info in dim_map.items():
            if info.get('name') == dim_name:
                return field
        return None

    def _get_display_name_for_id(self, field: str, value_id: int) -> Optional[str]:
        """根据字段名和ID值查询对应的业务显示名称"""
        try:
            # 根据字段名推断关联的表和显示字段
            table_mapping = {
                'version_id': ('versions', 'name'),
                'domain_id': ('domains', 'domain_name'),
                'sub_domain_id': ('sub_domains', 'sub_domain_name'),
                'product_id': ('products', 'product_name'),
                'service_module_id': ('service_modules', 'module_name'),
                'business_object_id': ('business_objects', 'object_name'),
                'organization_id': ('organizations', 'org_name'),
                'department_id': ('departments', 'dept_name'),
                'employee_id': ('employees', 'employee_name'),
            }

            if field in table_mapping:
                table_name, display_col = table_mapping[field]
                cursor = self.ds.execute(
                    f"SELECT {display_col} FROM {table_name} WHERE id = ?",
                    [value_id]
                )
                row = cursor.fetchone()
                if row and row[0]:
                    return str(row[0])
                else:
                    # 尝试使用 code 字段
                    cursor = self.ds.execute(
                        f"SELECT code FROM {table_name} WHERE id = ?",
                        [value_id]
                    )
                    row = cursor.fetchone()
                    if row and row[0]:
                        return str(row[0])

            return None
        except Exception as e:
            print(f"[Warning] Failed to get display name for {field}={value_id}: {e}")
            return None

    def get_rule(self, rule_id: int) -> Optional[Dict]:
        """获取单条权限规则"""
        cursor = self.ds.execute("SELECT rowid AS id, * FROM permission_rules WHERE rowid = ?", [rule_id])
        rows = self._rows_to_dicts(cursor)
        return rows[0] if rows else None

    def preview_matching_resources(self, condition: str, resource_type: str) -> Dict[str, Any]:
        """预览条件匹配的资源

        [2026-08-28 v61] 返回结构增加 total（全表数量）用于对比视角；
        错误显性化：条件解析 / SQL 失败必须通过 error 字段传给前端，
        不能伪装成「匹配 0 个资源」误导用户。
        """
        table_name = RESOURCE_TABLE_MAP.get(resource_type)
        if not table_name:
            return {'count': 0, 'total': 0, 'resources': [], 'error': f'未知的资源类型: {resource_type}'}

        sql_where = self.evaluator.predicate_to_sql_where(condition)
        if not sql_where:
            return {'count': 0, 'total': 0, 'resources': [], 'error': '条件表达式无法解析为有效的查询'}

        try:
            total_cursor = self.ds.execute(f"SELECT COUNT(*) FROM {table_name}")
            total = total_cursor.fetchone()[0]

            cursor = self.ds.execute(f"SELECT id, name, code FROM {table_name} WHERE {sql_where} LIMIT 100")
            resources = [{'id': r[0], 'name': r[1], 'code': r[2]} for r in cursor.fetchall()]

            count_cursor = self.ds.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {sql_where}")
            count = count_cursor.fetchone()[0]

            return {'count': count, 'total': total, 'resources': resources}
        except Exception as e:
            return {'count': 0, 'total': 0, 'resources': [], 'error': str(e)}

    def get_resource_field_metadata(self, resource_type: str) -> List[Dict]:
        """
        获取资源类型的字段元数据（用于自定义条件的字段Value Help）

        从Schema元数据返回字段列表，包含relation和display_field信息
        """
        try:
            from meta.core.models import registry, FieldStorage

            # 确保registry已加载
            if not registry._initialized:
                schema_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas')
                if os.path.exists(schema_dir):
                    registry.reload(schema_dir)

            meta_obj = registry.get(resource_type)
            if not meta_obj:
                return []

            fields = []
            fk_code_map = _fk_code_field_map(resource_type)
            for field in meta_obj.fields:
                # [Spec 20 v5 字段即模式] FK code 虚拟字段白名单放行:
                #   virtual resolution 解析字段 (version_code) 获得 FK code 双信号
                #   + relation_object=锚定维度, 前端 bizkey_only 直出目标对象业务键列表。
                #   其余 virtual 字段 (computed/显示名/统计) 保持跳过。
                if field.storage == FieldStorage.VIRTUAL:
                    fk = fk_code_map.get(field.id)
                    if not fk:
                        continue
                    dim = fk[0]
                    fields.append({
                        'id': field.id,
                        'name': field.name or field.id,
                        'db_column': field.db_column or field.id,
                        'field_type': field.field_type.value,
                        'description': field.description or '',
                        'relation_object': dim,
                        'display_field': '',
                        'is_foreign_key': True,
                        'is_business_key': True,
                        'is_enum': False,
                        'enum_values': None,
                        'enum_ref': None,
                        'anchor_semantics': 'bizkey',
                    })
                    continue

                # [2026-08-27] 跳过系统基线字段（owner_id / visibility）
                #   隐式安全基线由系统层保证，不暴露为逐条业务条件
                if field.db_column in BASELINE_FIELDS_EXCLUDED:
                    continue

                field_info = {
                    'id': field.id,
                    'name': field.name or field.id,
                    'db_column': field.db_column,
                    'field_type': field.field_type.value,
                    'description': field.description or '',
                    'relation_object': field.ui.relation if field.ui else '',
                    'display_field': field.ui.display_field if field.ui else '',
                    'is_foreign_key': False,
                    # [v18 2026-08-26] 业务主键标志：标识「资源自身的 ID / 编码」字段
                    #   - 用于在 Rule Builder 中触发 self-reference picker
                    #   - 数据源：YAML field.semantics.business_key == true
                    #   - 头部产品对照：
                    #   - SAP: Authorization Object 的「自身字段」也支持 F4 Search Help（按 Object 自身取候选）
                    #   - Salesforce: Lookup Dialog 返回 Id，default field 是 Id (业务键)
                    'is_business_key': False,
                    # [v21 2026-08-26] 枚举标志：标识「枚举 / boolean 字段」走枚举 picker
                    #   - 数据源：YAML field.enum_values（固定枚举）或 field.semantics.enum_ref（引用枚举类型）
                    #   - 头部产品对照：SAP Authorization Field 单值域（Fixed Value）也支持 F4
                    'is_enum': False,
                    'enum_values': None,  # list[{value, label, color}], 或 None
                    'enum_ref': None,      # str: enum_type_id（引用枚举类型）, 或 None
                    # [Spec 20 v5 字段即模式] 值域语义信号 (通用性核心):
                    #   'instance' = 实例锚定 · 快照 (技术主键 / FK 实例选择)
                    #   'bizkey'   = 业务键锚定 · 动态 (self-ref code / FK code)
                    #   None       = 普通属性条件
                    # 前端字段分组 / 对偶 hint / placeholder / 保存契约全部由它派生
                    'anchor_semantics': None,
                }

                # 判断是否为外键
                if field.ui and field.ui.relation:
                    field_info['is_foreign_key'] = True
                if field.semantics and field.semantics.analytics:
                    analytics = field.semantics.analytics
                    if isinstance(analytics, dict):
                        if analytics.get('type') == 'foreign_key':
                            field_info['is_foreign_key'] = True
                            if analytics.get('display_name') and not field_info.get('name'):
                                field_info['name'] = analytics['display_name']

                # [v18 2026-08-26] 检测业务主键字段：
                #   优先从 semantics.business_key 读取（YAML 显式声明）
                #   兜底：db_column == 'code'（多数资源的业务编码字段）
                #   不强制要求 id 字段必为业务主键（id 是技术主键，由 ui.visible=false 隐藏）
                semantics = field.semantics
                if semantics and getattr(semantics, 'business_key', False):
                    field_info['is_business_key'] = True
                elif field.db_column == 'code' and not field_info['is_business_key']:
                    # 兜底：YAML 未声明 business_key 时，code 字段默认视为业务主键
                    field_info['is_business_key'] = True

                # [v21 2026-08-26] 检测枚举字段：
                #   - 固定枚举：YAML field.enum_values 列出所有选项（如 boolean「是/否」、status「启用/禁用」）
                #     实际是 List[Dict]，每个 dict 含 value/label/color 键
                #   - 引用枚举：YAML field.semantics.enum_ref 指向一个枚举类型（如 visibility、priority）
                #   - 检测到任一来源 → is_enum=true，前端 Rule Builder 用 picker（不是 el-input 文本）
                enum_values_raw = getattr(field, 'enum_values', None)
                if enum_values_raw:
                    field_info['is_enum'] = True
                    # [v21 FIX 2026-08-26] enum_values 是 List[Dict]（不是对象列表），统一转为 {value, label, color}
                    normalized = []
                    for ev in enum_values_raw:
                        if isinstance(ev, dict):
                            normalized.append({
                                'value': str(ev.get('value', ev.get('label', ''))),
                                'label': ev.get('label', str(ev.get('value', ''))),
                                'color': ev.get('color'),
                            })
                    if normalized:
                        field_info['enum_values'] = normalized
                elif semantics and getattr(semantics, 'enum_ref', None):
                    field_info['is_enum'] = True
                    field_info['enum_ref'] = semantics.enum_ref

                # [Spec 20 v5 字段即模式] 值域语义信号判定 (FK 优先 → 技术主键 → 业务键)
                if field_info['is_foreign_key']:
                    field_info['anchor_semantics'] = 'instance'   # FK id: 选目标对象实例 (快照)
                elif field.db_column == 'id':
                    field_info['anchor_semantics'] = 'instance'   # 技术主键: 选资源自身实例 (快照)
                elif field_info['is_business_key']:
                    field_info['anchor_semantics'] = 'bizkey'     # 业务键: 动态锚定

                fields.append(field_info)

            return fields
        except Exception as e:
            print(f"Error loading field metadata for {resource_type}: {e}")
            return []

    # ========== 员工数据权限 ==========

    def get_employee_data_scopes(self) -> List[Dict]:
        """获取员工数据权限范围列表"""
        cursor = self.ds.execute("SELECT * FROM employee_data_scopes ORDER BY id")
        return self._rows_to_dicts(cursor)

    def resolve_employee_scope_condition(
        self, user_id: int, scope_code: str
    ) -> Optional[str]:
        """解析员工数据权限范围条件"""
        cursor = self.ds.execute(
            "SELECT condition_template FROM employee_data_scopes WHERE code = ?",
            [scope_code]
        )
        row = cursor.fetchone()
        if not row:
            return None

        template = row[0]

        user_info = self._get_user_org_info(user_id)

        params = {
            'user_id': user_id,
            'user_department_id': user_info.get('department_id', 0),
            'user_department_tree': user_info.get('department_tree', [0]),
            'user_organization_id': user_info.get('organization_id', 0),
        }

        return self.evaluator.resolve_template(template, params)

    # ========== 条件引用实例检测 ==========

    def check_rule_references_resource(
        self, resource_type: str, resource_id: int
    ) -> List[Dict]:
        """检查是否有权限规则引用了指定资源"""
        affected = []
        cursor = self.ds.execute(
            "SELECT rowid AS id, permission_set_id, resource_type, condition, permission_level, is_denied FROM permission_rules"
        )
        rules = self._rows_to_dicts(cursor)

        for rule in rules:
            refs = self.evaluator.detect_instance_references(rule['condition'])
            for ref in refs:
                if ref['field'] == 'id' and ref['value'] == resource_id and rule['resource_type'] == resource_type:
                    affected.append(rule)
                elif ref['resource_type'] == resource_type and ref['value'] == resource_id:
                    affected.append(rule)

        return affected

    # ========== 内部方法 ==========

    def _is_owner(self, user_id: int, resource_type: str, resource_id: int) -> bool:
        """检查用户是否是资源的所有者

        [FIX BUG-V010 2026-06-26] 兼容 V1.1.4 owner refactor
        背景: V1.1.4 后 owner_id 字段统一在 product 表, 子对象表 (version/domain/
              sub_domain/service_module/business_object) 已删除 owner_id 列
        修复: 通过 product chain 追溯 owner, 不再直接查子对象表的 owner_id
        案例: TEST333 是 product SDLKFJL 的 owner, 删除其下 version 失败
              原因: 原 _is_owner 查 versions.owner_id, 列不存在, 异常被吞
        """
        table_name = RESOURCE_TABLE_MAP.get(resource_type)
        if not table_name:
            return False

        # product: 直接查 owner_id
        if resource_type == 'product':
            try:
                cursor = self.ds.execute(
                    f"SELECT owner_id FROM {table_name} WHERE id = ?",
                    [resource_id]
                )
                row = cursor.fetchone()
                return row and row[0] == user_id
            except Exception:
                return False

        # 子对象: 通过 product chain 追溯 owner
        # [FIX BUG-V010] 不用 created_by (V1.1 后 user 也变了), 也不用 owner_id (列已删)
        chain_sql_map = {
            'version': f"""
                SELECT p.owner_id FROM {table_name} t
                JOIN products p ON t.product_id = p.id
                WHERE t.id = ?
            """,
            'domain': f"""
                SELECT p.owner_id FROM {table_name} t
                JOIN versions v ON t.version_id = v.id
                JOIN products p ON v.product_id = p.id
                WHERE t.id = ?
            """,
            'sub_domain': f"""
                SELECT p.owner_id FROM {table_name} t
                JOIN domains d ON t.domain_id = d.id
                JOIN versions v ON d.version_id = v.id
                JOIN products p ON v.product_id = p.id
                WHERE t.id = ?
            """,
            'service_module': f"""
                SELECT p.owner_id FROM {table_name} t
                JOIN sub_domains sd ON t.sub_domain_id = sd.id
                JOIN domains d ON sd.domain_id = d.id
                JOIN versions v ON d.version_id = v.id
                JOIN products p ON v.product_id = p.id
                WHERE t.id = ?
            """,
            'business_object': f"""
                SELECT p.owner_id FROM {table_name} t
                JOIN service_modules sm ON t.service_module_id = sm.id
                JOIN sub_domains sd ON sm.sub_domain_id = sd.id
                JOIN domains d ON sd.domain_id = d.id
                JOIN versions v ON d.version_id = v.id
                JOIN products p ON v.product_id = p.id
                WHERE t.id = ?
            """,
        }
        sql = chain_sql_map.get(resource_type)
        if not sql:
            return False
        try:
            cursor = self.ds.execute(sql, [resource_id])
            row = cursor.fetchone()
            return row and row[0] == user_id
        except Exception:
            return False

    def _check_denied_rules(self, user_id: int, resource_type: str, resource_id: int) -> bool:
        """检查禁止权限（用友BIP禁止权优先原则）"""
        rules = self._get_user_rules(user_id, resource_type)
        resource = self._get_resource_detail(resource_type, resource_id)
        if not resource:
            return False

        for rule in rules:
            if not rule.get('is_denied'):
                continue
            if self.evaluator.evaluate(rule['condition'], resource):
                return True

        return False

    def _check_condition_rules(
        self, user_id: int, resource_type: str, resource_id: int, required_level: str,
        require_propagate: bool = False
    ) -> Dict[str, Any]:
        """检查条件型权限规则

        [2026-09-05 继承方向修复] require_propagate=True 时只认 propagate_to_parents=1
        的规则（供向上传播检查使用），不再无条件把子级权限传播给父级。
        """
        rules = self._get_user_rules(user_id, resource_type)
        resource = self._get_resource_detail(resource_type, resource_id)
        if not resource:
            return {'allowed': False}

        best_level = 'none'
        best_rule = None

        for rule in rules:
            if rule.get('is_denied'):
                continue
            # [2026-09-05 继承方向修复] 向上传播检查：规则未开启 propagate_to_parents → 跳过
            if require_propagate and not rule.get('propagate_to_parents'):
                continue
            if not rule.get('inherit_to_children', True):
                if str(resource.get('id')) not in rule['condition']:
                    continue

            if self.evaluator.evaluate(rule['condition'], resource):
                rule_level = rule.get('permission_level', 'read')
                if LEVEL_ORDER.get(rule_level, 0) > LEVEL_ORDER.get(best_level, 0):
                    best_level = rule_level
                    best_rule = rule

        if LEVEL_ORDER.get(best_level, 0) >= LEVEL_ORDER.get(required_level, 0):
            return {
                'allowed': True,
                'permission_level': best_level,
                'source': 'condition',
                'matched_condition': best_rule['condition'] if best_rule else None,
            }

        return {'allowed': False}

    def _check_parent_visibility(
        self, user_id: int, resource_type: str, resource_id: int
    ) -> Dict[str, Any]:
        """检查向上传播权限（子级权限提供父级只读可见性）

        [2026-09-05 假开关修复] 仅当子级命中规则 propagate_to_parents=1 时才传播。
        此前无条件遍历子资源检查权限 → 配置弹窗的「向上传播」开关形同虚设。
        """
        child_types = CHILD_TYPE_MAP.get(resource_type, [])

        for child_type in child_types:
            child_table = RESOURCE_TABLE_MAP.get(child_type)
            if not child_table:
                continue

            parent_field = PARENT_FIELD_MAP.get(child_type)
            if not parent_field:
                continue

            try:
                cursor = self.ds.execute(
                    f"SELECT id FROM {child_table} WHERE {parent_field} = ? LIMIT 1",
                    [resource_id]
                )
                child_row = cursor.fetchone()
                if not child_row:
                    continue

                child_id = child_row[0]
                # require_propagate=True: 只认显式开启向上传播的子级规则
                child_result = self._check_condition_rules(
                    user_id, child_type, child_id, 'read', require_propagate=True
                )
                if child_result['allowed']:
                    return {
                        'allowed': True,
                        'permission_level': 'read',
                        'source': 'upward_propagation',
                        'matched_condition': child_result.get('matched_condition'),
                        'propagated_from': f"{child_type}#{child_id}",
                    }
            except Exception:
                continue

        return {'allowed': False}

    def _get_user_rules(self, user_id: int, resource_type: str) -> List[Dict]:
        """获取用户的条件型权限规则（含祖先组织继承）

        [2026-09-05 继承方向修复] 主来源切换为 data_permission_rules 统一表
        （ConditionRuleDialog 实际写入，含 inherit_to_children / propagate_to_parents）。
        旧实现读 legacy permission_rules：本地库该表无 permission_set_id 列，
        JOIN 恒抛异常 → 条件规则在执行层从未生效（假开关的根因之一）。
        legacy 表仅作回退兜底；两表都失败时返回 []（降级为无规则，不阻断）。
        """
        from meta.services.org_service import OrgService
        org_ids = OrgService(self.ds).get_user_effective_org_ids(user_id)
        if not org_ids:
            return []
        placeholders = ','.join('?' * len(org_ids))
        # 主来源: 统一表（只取 condition/prohibition 两类；owner/visibility/dimension 有各自通道）
        try:
            cursor = self.ds.execute(f"""
                SELECT pr.id, pr.* FROM data_permission_rules pr
                INNER JOIN org_permission_sets gr ON pr.permission_set_id = gr.permission_set_id
                WHERE gr.org_id IN ({placeholders}) AND pr.resource_type = ?
                  AND pr.rule_type IN ('condition', 'prohibition')
                  AND pr.condition IS NOT NULL AND pr.condition != ''
                ORDER BY pr.is_denied DESC, pr.id
            """, org_ids + [resource_type])
            return self._expand_rule_anchors(self._rows_to_dicts(cursor), resource_type)
        except Exception:
            pass
        # 回退: legacy 表
        try:
            cursor = self.ds.execute(f"""
                SELECT pr.rowid AS id, pr.* FROM permission_rules pr
                INNER JOIN org_permission_sets gr ON pr.permission_set_id = gr.permission_set_id
                WHERE gr.org_id IN ({placeholders}) AND pr.resource_type = ?
                ORDER BY pr.is_denied DESC, pr.rowid
            """, org_ids + [resource_type])
            return self._expand_rule_anchors(self._rows_to_dicts(cursor), resource_type)
        except Exception:
            return []

    def _expand_rule_anchors(self, rules: List[Dict], resource_type: str) -> List[Dict]:
        """[Spec 20 Task 9-B] rule-load 时业务键锚点展开

        统一落点: 覆盖 check_permission per-record 求值 / get_authorized_resource_ids
        SQL 派生 / preview_matching_resources 全部下游。展开失败 → 原样保留
        (per-record 对 code token 天然 fail-closed, 不放大权限)。
        """
        for r in rules:
            cond = r.get('condition')
            if not cond or cond.strip() in ('*', ''):
                continue
            try:
                r['condition'] = _expand_condition_anchors(self.ds, cond, resource_type)
            except Exception as e:
                logger.warning(
                    f'[Spec20-BIZKEY] expand failed, keep raw: rule_id={r.get("id")}, {e}')
        return rules

    def _get_resource_detail(self, resource_type: str, resource_id: int) -> Optional[Dict]:
        """获取资源详情"""
        table_name = RESOURCE_TABLE_MAP.get(resource_type)
        if not table_name:
            return None

        try:
            cursor = self.ds.execute(f"SELECT * FROM {table_name} WHERE id = ?", [resource_id])
            rows = self._rows_to_dicts(cursor)
            return rows[0] if rows else None
        except Exception:
            return None

    def _get_user_org_info(self, user_id: int) -> Dict:
        """获取用户的组织信息"""
        info = {}
        try:
            cursor = self.ds.execute(
                "SELECT department_id, organization_id FROM users WHERE id = ?",
                [user_id]
            )
            row = cursor.fetchone()
            if row:
                info['department_id'] = row[0]
                info['organization_id'] = row[1]

            if info.get('department_id'):
                dept_cursor = self.ds.execute(
                    "SELECT id FROM departments WHERE id = ? OR parent_id = ?",
                    [info['department_id'], info['department_id']]
                )
                info['department_tree'] = [r[0] for r in dept_cursor.fetchall()]
        except Exception:
            pass
        return info

    def _action_to_level(self, action: str) -> str:
        """将操作映射到权限级别"""
        mapping = {
            'read': 'read',
            'view': 'read',
            'reference': 'read',
            'export': 'read',
            'create': 'write',
            'update': 'write',
            'write': 'write',
            'delete': 'admin',
            'admin': 'admin',
            'manage': 'admin',
        }
        return mapping.get(action, 'read')

    def _rows_to_dicts(self, cursor) -> List[Dict]:
        """将查询结果转为字典列表"""
        if cursor.description is None:
            return []
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
