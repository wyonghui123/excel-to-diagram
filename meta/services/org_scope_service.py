# -*- coding: utf-8 -*-
"""业务对象组织边界求值器（规格 24 §5）

单一真源：BO YAML 的 ``org_scope`` 声明。
读过滤、写校验、组织参照三处共用本服务的 visible_org_ids / 条件构造。
"""

import json
import logging
import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# 控制参数（规格 24 §7.1）
ORG_SCOPE_PARAM_CODE = 'org_scope_enforce'
ORG_SCOPE_OFF = 'off'
ORG_SCOPE_COMPAT = 'compat'
ORG_SCOPE_ENFORCE = 'enforce'
ORG_SCOPE_MODES = (ORG_SCOPE_OFF, ORG_SCOPE_COMPAT, ORG_SCOPE_ENFORCE)

_MODE_CACHE: Dict[int, Tuple[float, str]] = {}
_VISIBLE_CACHE: Dict[Tuple[int, int], Tuple[float, Set[int]]] = {}
_CACHE_TTL = 300.0
_CACHE_LOCK = threading.Lock()


def clear_org_scope_cache() -> None:
    """清空进程内缓存（组织树变更 / 测试用）"""
    with _CACHE_LOCK:
        _MODE_CACHE.clear()
        _VISIBLE_CACHE.clear()


def _row_get(row, key, index):
    """兼容 tuple / dict 行"""
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[index]
    except Exception:
        return None


class OrgScopeService:
    """组织可见集与 BO 归属组织判定"""

    def __init__(self, data_source, mode: Optional[str] = None):
        self._ds = data_source
        self._mode_override = mode

    # ------------------------------------------------------------------
    # 开关
    # ------------------------------------------------------------------
    def mode(self) -> str:
        """三态开关：off | compat | enforce（默认 off）"""
        if self._mode_override:
            return self._mode_override
        key = id(self._ds)
        now = time.time()
        cached = _MODE_CACHE.get(key)
        if cached and now - cached[0] < 60.0:
            return cached[1]
        value = ORG_SCOPE_OFF
        try:
            cursor = self._ds.execute(
                "SELECT default_value FROM control_parameter_defs WHERE code = ? LIMIT 1",
                [ORG_SCOPE_PARAM_CODE],
            )
            row = cursor.fetchone()
            if row is not None:
                raw = _row_get(row, 'default_value', 0)
                if isinstance(raw, str) and raw.strip().lower() in ORG_SCOPE_MODES:
                    value = raw.strip().lower()
        except Exception as exc:
            logger.debug('org_scope mode lookup failed: %s', exc)
        _MODE_CACHE[key] = (now, value)
        return value

    # ------------------------------------------------------------------
    # 可见组织集
    # ------------------------------------------------------------------
    def visible_org_ids(self, user_id: Optional[int], is_admin: bool = False) -> Optional[Set[int]]:
        """用户可见组织集；None = 全量（管理员豁免）"""
        if is_admin:
            return None
        if user_id is None:
            return set()

        key = (id(self._ds), int(user_id))
        now = time.time()
        with _CACHE_LOCK:
            cached = _VISIBLE_CACHE.get(key)
            if cached and now - cached[0] < _CACHE_TTL:
                return set(cached[1])

        include, exclude = self._permission_scope_values(user_id)
        primary = self._primary_org_id(user_id)
        if primary:
            include.add(primary)

        # include/exclude 已在取值时按 inherit_children 展开子树（规格 §5.1）
        visible = include - exclude

        with _CACHE_LOCK:
            _VISIBLE_CACHE[key] = (now, set(visible))
        return visible

    def visible_org_ids_for_function(
        self, user_id: Optional[int], function_type: Optional[str] = None,
        is_admin: bool = False,
    ) -> Optional[Set[int]]:
        """组织参照用：visible ∩ 指定职能（T6）"""
        visible = self.visible_org_ids(user_id, is_admin=is_admin)
        if visible is None or not function_type:
            return visible
        if not visible:
            return set()
        ids = sorted(visible)
        placeholders = ','.join('?' * len(ids))
        try:
            rows = self._ds.execute(
                f"SELECT DISTINCT org_id FROM org_functions "
                f"WHERE function_type = ? AND org_id IN ({placeholders})",
                [function_type] + ids,
            ).fetchall()
        except Exception as exc:
            logger.debug('org function filter failed: %s', exc)
            return visible
        return {int(_row_get(r, 'org_id', 0)) for r in rows}

    def expand_subtree(self, org_ids: Iterable[int]) -> Set[int]:
        """递归展开组织子树（orgs.parent_id，防环，最大深度 10）"""
        roots = {int(v) for v in org_ids if v is not None}
        if not roots:
            return set()

        ids = sorted(roots)
        placeholders = ','.join('?' * len(ids))
        sql = f"""
            WITH RECURSIVE subtree(id, depth) AS (
                SELECT id, 0 FROM orgs WHERE id IN ({placeholders})
                UNION
                SELECT o.id, s.depth + 1
                FROM orgs o JOIN subtree s ON o.parent_id = s.id
                WHERE s.depth < 10
            )
            SELECT DISTINCT id FROM subtree
        """
        try:
            rows = self._ds.execute(sql, ids).fetchall()
            result = {int(_row_get(r, 'id', 0)) for r in rows}
            return result or roots
        except Exception as exc:
            logger.debug('expand_subtree failed: %s', exc)
            return roots

    # ------------------------------------------------------------------
    # 读条件
    # ------------------------------------------------------------------
    def build_read_conditions(self, meta_obj, visible: Optional[Set[int]]) -> List[Dict[str, Any]]:
        """按 org_scope 声明构造查询条件（raw expr）"""
        decl = getattr(meta_obj, 'org_scope', None) or {}
        if not decl or visible is None:
            return []
        mode = decl.get('mode')
        if mode == 'global':
            return []
        if not visible:
            return [{'type': 'raw', 'expr': '1=0', 'params': []}]

        ids_sql = ','.join(str(int(v)) for v in sorted(visible))
        if mode == 'direct':
            return [{'type': 'raw', 'expr': f"{decl['field']} IN ({ids_sql})", 'params': []}]
        if mode == 'dual':
            return [{'type': 'raw', 'expr': (
                f"({decl['from_field']} IN ({ids_sql}) OR {decl['to_field']} IN ({ids_sql}))"
            ), 'params': []}]
        if mode == 'chain':
            host = self._get_object(decl.get('host'))
            if host is None:
                return [{'type': 'raw', 'expr': '1=0', 'params': []}]
            inner = self._chain_inner_expr(host, visible, 'h0', 0)
            if not inner:
                return [{'type': 'raw', 'expr': '1=0', 'params': []}]
            table = getattr(host, 'table_name', '') or ''
            return [{'type': 'raw', 'expr': (
                f"EXISTS (SELECT 1 FROM {table} h0 "
                f"WHERE h0.id = {decl['via']} AND {inner})"
            ), 'params': []}]
        return []

    def _chain_inner_expr(self, host, visible: Set[int], alias: str, depth: int) -> str:
        """宿主对象的归属组织表达式（支持嵌套 chain）"""
        if depth > 5:
            return ''
        decl = getattr(host, 'org_scope', None) or {}
        if not decl:
            return ''
        mode = decl.get('mode')
        ids_sql = ','.join(str(int(v)) for v in sorted(visible))
        if mode == 'direct':
            return f"{alias}.{decl['field']} IN ({ids_sql})"
        if mode == 'dual':
            return (
                f"({alias}.{decl['from_field']} IN ({ids_sql}) "
                f"OR {alias}.{decl['to_field']} IN ({ids_sql}))"
            )
        if mode == 'chain':
            next_host = self._get_object(decl.get('host'))
            if next_host is None:
                return ''
            next_alias = f'h{depth + 1}'
            inner = self._chain_inner_expr(next_host, visible, next_alias, depth + 1)
            if not inner:
                return ''
            table = getattr(next_host, 'table_name', '') or ''
            return (
                f"EXISTS (SELECT 1 FROM {table} {next_alias} "
                f"WHERE {next_alias}.id = {alias}.{decl['via']} AND {inner})"
            )
        return ''

    # ------------------------------------------------------------------
    # 写校验
    # ------------------------------------------------------------------
    def record_org_ids(self, meta_obj, record: Dict[str, Any]) -> Optional[Set[int]]:
        """记录的 owning org 集合；None = 无法判定（缺字段 / 宿主不存在）"""
        if not record:
            return None
        decl = getattr(meta_obj, 'org_scope', None) or {}
        mode = decl.get('mode')
        if mode == 'direct':
            return self._as_ids(record.get(decl.get('field')))
        if mode == 'dual':
            values = self._as_ids(record.get(decl.get('from_field')))
            values |= self._as_ids(record.get(decl.get('to_field')))
            return values or None
        if mode == 'chain':
            host = self._get_object(decl.get('host'))
            if host is None:
                return None
            via_value = record.get(decl.get('via'))
            if via_value is None:
                return None
            host_record = self._fetch_row(getattr(host, 'table_name', ''), via_value)
            if host_record is None:
                return None
            return self.record_org_ids(host, host_record)
        return None

    def is_writable(self, meta_obj, record: Dict[str, Any], visible: Optional[Set[int]]) -> bool:
        """记录是否在可见组织范围内（None = 管理员/未启用 → 放行）"""
        if visible is None:
            return True
        decl = getattr(meta_obj, 'org_scope', None) or {}
        if not decl or decl.get('mode') == 'global':
            return True
        if not (decl.get('write_check', True)):
            return True
        org_ids = self.record_org_ids(meta_obj, record)
        if org_ids is None:
            # 无法判定归属时按可见性放行（缺字段由模型必填校验负责）
            return True
        return org_ids.issubset(visible)

    def check_function(self, record_org_ids: Optional[Set[int]], function_type: Optional[str]) -> Optional[int]:
        """owning org 是否具备职能；返回缺失职能的组织 ID（None = 通过）"""
        if not function_type or not record_org_ids:
            return None
        ids = sorted(record_org_ids)
        placeholders = ','.join('?' * len(ids))
        try:
            rows = self._ds.execute(
                f"SELECT DISTINCT org_id FROM org_functions "
                f"WHERE function_type = ? AND org_id IN ({placeholders})",
                [function_type] + ids,
            ).fetchall()
        except Exception as exc:
            logger.debug('check_function failed: %s', exc)
            return None
        enabled = {int(_row_get(r, 'org_id', 0)) for r in rows}
        for org_id in ids:
            if org_id not in enabled:
                return org_id
        return None

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _permission_scope_values(self, user_id: int) -> Tuple[Set[int], Set[int]]:
        """权限集组织范围：返回 (include, exclude) 原始值（未展开子树）"""
        permission_set_ids = self._user_permission_set_ids(user_id)
        if not permission_set_ids:
            return set(), set()
        placeholders = ','.join('?' * len(permission_set_ids))
        try:
            rows = self._ds.execute(
                f"SELECT dimension_values, scope_mode, inherit_children "
                f"FROM permission_set_dimension_scopes "
                f"WHERE dimension_code = 'org' AND permission_set_id IN ({placeholders})",
                list(permission_set_ids),
            ).fetchall()
        except Exception as exc:
            logger.debug('permission_set_dimension_scopes lookup failed: %s', exc)
            return set(), set()

        include: Set[int] = set()
        exclude: Set[int] = set()
        for row in rows:
            values = self._parse_dimension_values(_row_get(row, 'dimension_values', 0))
            scope_mode = (_row_get(row, 'scope_mode', 1) or 'include')
            inherit = _row_get(row, 'inherit_children', 2)
            if inherit is None or bool(inherit):
                values = self.expand_subtree(values)
            target = exclude if str(scope_mode).lower() == 'exclude' else include
            target.update(values)
        return include, exclude

    def _user_permission_set_ids(self, user_id: int) -> List[int]:
        """用户有效权限集 = user_permission_sets ∪ 有效组织上的 org_permission_sets"""
        ids: Set[int] = set()
        try:
            rows = self._ds.execute(
                "SELECT DISTINCT permission_set_id FROM user_permission_sets WHERE user_id = ?",
                [user_id],
            ).fetchall()
            ids.update(int(_row_get(r, 'permission_set_id', 0)) for r in rows)
        except Exception as exc:
            logger.debug('user_permission_sets lookup failed: %s', exc)

        try:
            from meta.services.org_service import OrgService
            org_ids = OrgService(self._ds).get_user_effective_org_ids(user_id)
        except Exception as exc:
            logger.debug('effective org lookup failed: %s', exc)
            org_ids = []
        if org_ids:
            placeholders = ','.join('?' * len(org_ids))
            try:
                rows = self._ds.execute(
                    f"SELECT DISTINCT permission_set_id FROM org_permission_sets "
                    f"WHERE org_id IN ({placeholders})",
                    list(org_ids),
                ).fetchall()
                ids.update(int(_row_get(r, 'permission_set_id', 0)) for r in rows)
            except Exception as exc:
                logger.debug('org_permission_sets lookup failed: %s', exc)
        return sorted(v for v in ids if v)

    def _primary_org_id(self, user_id: int) -> Optional[int]:
        try:
            row = self._ds.execute(
                "SELECT primary_org_id FROM users WHERE id = ?", [user_id]
            ).fetchone()
        except Exception:
            return None
        if row is None:
            return None
        value = _row_get(row, 'primary_org_id', 0)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _fetch_row(self, table: str, record_id: Any) -> Optional[Dict[str, Any]]:
        if not table:
            return None
        try:
            cursor = self._ds.execute(f"SELECT * FROM {table} WHERE id = ?", [record_id])
            row = cursor.fetchone()
        except Exception as exc:
            logger.debug('_fetch_row %s failed: %s', table, exc)
            return None
        if row is None:
            return None
        if isinstance(row, dict):
            return dict(row)
        description = getattr(cursor, 'description', None) or []
        return {col[0]: row[idx] for idx, col in enumerate(description)}

    @staticmethod
    def _get_object(bo_id: Optional[str]):
        if not bo_id:
            return None
        try:
            from meta.core.models import registry
            return registry.get(bo_id)
        except Exception:
            return None

    @staticmethod
    def _parse_dimension_values(raw) -> Set[int]:
        if raw is None:
            return set()
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = [raw]
        if isinstance(raw, dict):
            raw = raw.get('include') or raw.get('values') or []
        if not isinstance(raw, (list, tuple, set)):
            raw = [raw]
        result: Set[int] = set()
        for item in raw:
            if isinstance(item, dict):
                item = item.get('value', item.get('id'))
            try:
                if item is not None:
                    result.add(int(item))
            except (TypeError, ValueError):
                continue
        return result

    @staticmethod
    def _as_ids(value) -> Set[int]:
        if value is None:
            return set()
        if isinstance(value, (list, tuple, set)):
            result: Set[int] = set()
            for item in value:
                try:
                    result.add(int(item))
                except (TypeError, ValueError):
                    continue
            return result
        try:
            return {int(value)}
        except (TypeError, ValueError):
            return set()
