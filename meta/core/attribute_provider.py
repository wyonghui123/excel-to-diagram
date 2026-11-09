# -*- coding: utf-8 -*-
"""扩展属性唯一读取入口（spec 2026-11-09 FR-006 / FR-007 / FR-009 / FR-011）。

调用方（规则表达式、trace、可配置变量清单）只通过本模块读取扩展属性，
禁止各自拼 SQL。职责：

- 对象 → 值表映射（item / party / batch），兼容两套物理表形状：
  * item_attribute_values：无 tenant_id，有 attr_code / 可空 attribute_id / org_id
  * party/batch_attribute_values：有 tenant_id / attribute_id / seq，无 attr_code
- 定义按「平台层 + 本租户层、租户优先」合并，只认 active；
  revision 作为 definition_version 供 trace 回放。
- 缺失 / 停用统一返回 ``source='missing'``，**不抛异常**，表达式按 None 参与比较。
- 进程级 TTL 缓存 + 显式失效 ``AttributeProvider.invalidate``：
  AttributeValueService 写入完成、定义停用 / 提升后必须调用。
- 请求级 memo：单次 ``resolve`` 内对同一 (对象, 编码) 只查一次库。

口径说明：平台无通用 app 上下文，缓存键保留 ``app_id`` 占位（默认空串），
由调用方按需传入；租户默认 0（平台层）。
"""

import copy
import logging
import re
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

SOURCE_VALUE = 'value'
SOURCE_DEFAULT = 'default'      # P1 预留：默认值来源，当前不产生
SOURCE_MISSING = 'missing'

STATUS_ACTIVE = 'active'
STATUS_MISSING = 'missing'

#: 值列（一行只有一列非空，见 attribute_value_service.VALUE_COLUMNS）
VALUE_COLUMNS = (
    'value_text', 'value_number', 'value_boolean',
    'value_date', 'value_datetime',
)

#: 对象 → 值表 / 归属列（与 AttributeValueService 子类同源）
VALUE_TABLES: Dict[str, Dict[str, str]] = {
    'item': {'table': 'item_attribute_values', 'owner': 'item_id'},
    'party': {'table': 'party_attribute_values', 'owner': 'party_id'},
    'batch': {'table': 'batch_attribute_values', 'owner': 'batch_id'},
}

DEFAULT_TTL_SECONDS = 60.0
_MAX_CACHE_ENTRIES = 512

#: key = (ds_token, app_id, tenant_id, object_type, ids, codes, org_id)
_CACHE: 'OrderedDict[Tuple, Tuple[float, Dict[str, Any]]]' = OrderedDict()
_CACHE_LOCK = threading.Lock()
#: (ds_token, table) → 列名集合；表结构不随运行期变化，长 TTL 即可
_COLUMNS_CACHE: Dict[Tuple[int, str], Tuple[float, frozenset]] = {}

#: promotion 落表后的物理列查询只接受安全标识符（防注入）
_SAFE_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


# ----------------------------------------------------------------------
# 缓存
# ----------------------------------------------------------------------
def _cache_get(key: Tuple) -> Optional[Dict[str, Any]]:
    now = time.time()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at <= now:
            _CACHE.pop(key, None)
            return None
        _CACHE.move_to_end(key)
        return value


def _cache_put(key: Tuple, value: Dict[str, Any]) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.time() + DEFAULT_TTL_SECONDS, value)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _MAX_CACHE_ENTRIES:
            _CACHE.popitem(last=False)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _value_of(row: Dict[str, Any]) -> Any:
    for column in VALUE_COLUMNS:
        if row.get(column) is not None:
            return row.get(column)
    return None


def _missing_entry(code: str, *, status: str = STATUS_MISSING,
                   definition: Optional[Dict[str, Any]] = None,
                   definition_id: Any = None) -> Dict[str, Any]:
    return {
        'code': code,
        'value': None,
        'source': SOURCE_MISSING,
        'status': status,
        'definition_id': definition.get('id') if definition else definition_id,
        'definition_version': (definition or {}).get('revision'),
    }


def _empty_entry(code: str,
                 definition: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """已求值但无值行：定义 active → missing；定义停用 → inactive。"""
    if definition is None:
        return _missing_entry(code)
    status = str(definition.get('status') or STATUS_ACTIVE)
    if status != STATUS_ACTIVE:
        return _missing_entry(code, status=status, definition=definition)
    return {
        'code': code,
        'value': None,
        'source': SOURCE_MISSING,
        'status': STATUS_ACTIVE,
        'definition_id': definition.get('id'),
        'definition_version': definition.get('revision'),
    }


class AttributeProvider:
    """扩展属性读取器；同一 data_source 建议复用实例。"""

    def __init__(self, data_source: Any, *, tenant_id: int = 0,
                 app_id: str = ''):
        self.ds = data_source
        self.tenant_id = _as_int(tenant_id)
        self.app_id = app_id or ''

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def resolve(self, object_type: str, object_ids: Iterable[Any],
                codes: Iterable[str], *, tenant_id: Optional[int] = None,
                app_id: Optional[str] = None,
                org_id: Optional[int] = None) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """批量读取扩展属性。

        Returns:
            ``{str(owner_id): {code: entry}}``；entry 固定含
            ``code/value/source/status/definition_id/definition_version``。
            未知对象、缺表、无定义一律返回 missing，不抛异常。
        """
        tenant = self.tenant_id if tenant_id is None else _as_int(tenant_id)
        app = self.app_id if app_id is None else (app_id or '')
        ids = tuple(dict.fromkeys(
            str(oid) for oid in object_ids if oid is not None))
        code_list = tuple(dict.fromkeys(
            str(code) for code in codes if code))
        empty = {
            oid: {code: _missing_entry(code) for code in code_list}
            for oid in ids
        }
        if not ids or not code_list:
            return empty
        if VALUE_TABLES.get(object_type) is None or self.ds is None:
            return empty

        key = (id(self.ds), app, tenant, object_type, ids, code_list, org_id)
        cached = _cache_get(key)
        if cached is not None:
            return copy.deepcopy(cached)

        try:
            computed = self._load(
                object_type, ids, code_list, tenant, org_id)
        except Exception as exc:  # 属性读取失败不得打断规则求值
            logger.warning('[attribute_provider] 读取失败 %s: %s',
                           object_type, exc)
            computed = empty
        _cache_put(key, computed)
        return copy.deepcopy(computed)

    def resolve_one(self, object_type: str, object_id: Any, code: str,
                    **kwargs) -> Dict[str, Any]:
        entry = self.resolve(object_type, [object_id], [code], **kwargs)
        return entry.get(str(object_id), {}).get(code) or _missing_entry(code)

    def available_variables(self, bo_id: str, *,
                            tenant_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """可配置变量清单：对象级 scope + active + descriptive/analytic。

        返回项含 ``code/label/data_type/scope_level``（另附 attribute_id /
        tenant_id），供视图下拉与规则编辑器使用；缺表返回空清单。
        """
        tenant = self.tenant_id if tenant_id is None else _as_int(tenant_id)
        if self.ds is None:
            return []
        sql = (
            'SELECT d.id AS attribute_id, d.code, d.name AS label, '
            'd.data_type, d.usage_class, d.tenant_id, s.scope_type '
            'FROM attribute_scopes s '
            'JOIN attribute_definitions d ON d.id = s.attribute_id '
            "WHERE s.scope_type = 'object' AND s.scope_ref = ? "
            "AND s.status = 'active' AND d.status = 'active' "
            "AND d.usage_class IN ('descriptive', 'analytic') "
            'AND s.tenant_id IN (0, ?) AND d.tenant_id IN (0, ?) '
            'ORDER BY s.seq, d.code, d.tenant_id'
        )
        try:
            rows = self.ds.query(sql, [bo_id, tenant, tenant]) or []
        except Exception as exc:
            logger.warning('[attribute_provider] 变量清单读取失败 %s: %s',
                           bo_id, exc)
            return []

        # 同 code 平台层与租户层并存时，租户层优先（列表顺序已按 tenant_id 升序，
        # 平台层 0 在前，故后者覆盖前者）
        resolved: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            resolved[str(row.get('code'))] = {
                'attribute_id': row.get('attribute_id'),
                'code': row.get('code'),
                'label': row.get('label'),
                'data_type': row.get('data_type'),
                'scope_level': row.get('scope_type') or 'object',
                'tenant_id': row.get('tenant_id'),
            }
        return sorted(resolved.values(), key=lambda item: str(item['code']))

    # ------------------------------------------------------------------
    # 失效（写入 / 定义变更后调用）
    # ------------------------------------------------------------------
    @staticmethod
    def invalidate(object_type: Optional[str] = None,
                   object_ids: Optional[Iterable[Any]] = None,
                   codes: Optional[Iterable[str]] = None) -> int:
        """清除匹配的缓存条目；无参清空全部。返回清除条数。"""
        code_set = {str(code) for code in codes} if codes else None
        id_set = ({str(oid) for oid in object_ids}
                  if object_ids is not None else None)
        with _CACHE_LOCK:
            keys = [
                key for key in _CACHE
                if (object_type is None or key[3] == object_type)
                and (id_set is None or id_set & set(key[4]))
                and (code_set is None or code_set & set(key[5]))
            ]
            for key in keys:
                _CACHE.pop(key, None)
        return len(keys)

    # ------------------------------------------------------------------
    # 载入
    # ------------------------------------------------------------------
    def _load(self, object_type: str, ids: Tuple[str, ...],
              codes: Tuple[str, ...], tenant: int,
              org_id: Optional[int]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        cfg = VALUE_TABLES[object_type]
        definitions = self._load_definitions(tenant, codes)
        columns = self._table_columns(cfg['table'])
        if not columns:
            return {oid: {code: _missing_entry(code) for code in codes}
                    for oid in ids}

        defs_by_code = {
            code: row for code, row in definitions.items()
            if (row.get('status') or STATUS_ACTIVE) == STATUS_ACTIVE
        }
        result = {
            oid: {code: _empty_entry(code, definitions.get(code))
                  for code in codes}
            for oid in ids
        }
        if not defs_by_code:
            return result

        rows = self._load_rows(
            cfg, columns, ids, tuple(defs_by_code), tenant, org_id)
        for row in rows:
            oid = str(row.get('owner_id'))
            code = str(row.get('code'))
            target = result.get(oid, {}).get(code)
            if target is None or target['source'] == SOURCE_VALUE:
                continue
            definition = defs_by_code.get(code)
            if row.get('attribute_id') is not None and definition is not None:
                if _as_int(row.get('attribute_id'), -1) != _as_int(
                        definition.get('id'), -2):
                    continue
            value = _value_of(row)
            if value is None:
                continue
            target.update({
                'value': value,
                'source': SOURCE_VALUE,
                'status': STATUS_ACTIVE,
                'definition_id': (definition or {}).get('id',
                                                        row.get('attribute_id')),
                'definition_version': (definition or {}).get('revision'),
            })
        self._load_promoted(object_type, ids, codes, result)
        return result

    def _load_promoted(self, object_type: str, ids: Tuple[str, ...],
                       codes: Tuple[str, ...],
                       result: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
        """已 active 的 promotion：物理列成为唯一 owner（TBD-003 cutover）。

        切表后即使物理列为 NULL 也不再回落值表；未 active 的 promotion 不参与
        （verified 前 Provider 仍读值表）。
        """
        placeholders = ','.join('?' for _ in codes)
        try:
            rows = self.ds.query(
                'SELECT attribute_code, target_table, target_column '
                "FROM attribute_promotion WHERE object_type = ? "
                "AND status = 'active' AND attribute_code IN (%s)" % placeholders,
                [object_type] + list(codes)) or []
        except Exception:
            # promotion 表尚未创建时按未提升处理
            return
        if not rows:
            return

        id_marks = ','.join('?' for _ in ids)
        for promo in rows:
            code = str(promo.get('attribute_code'))
            table = str(promo.get('target_table') or '')
            column = str(promo.get('target_column') or '')
            if not (_SAFE_IDENTIFIER.match(table)
                    and _SAFE_IDENTIFIER.match(column)):
                logger.warning('[attribute_provider] promotion 标识符非法: %r.%r',
                               table, column)
                continue
            try:
                values = self.ds.query(
                    'SELECT id AS owner_id, %s AS value FROM %s '
                    'WHERE id IN (%s)' % (column, table, id_marks),
                    list(ids)) or []
            except Exception as exc:
                logger.warning('[attribute_provider] 已提升属性读取失败 %s.%s: %s',
                               table, column, exc)
                continue
            found = {str(row.get('owner_id')): row.get('value')
                     for row in values}
            for oid, code_map in result.items():
                entry = code_map.get(code)
                if entry is None:
                    continue
                value = found.get(oid)
                entry.update({
                    'value': value,
                    'source': SOURCE_VALUE if value is not None else SOURCE_MISSING,
                })

    def _load_definitions(self, tenant: int,
                          codes: Tuple[str, ...]) -> Dict[str, Dict[str, Any]]:
        placeholders = ','.join('?' for _ in codes)
        sql = (
            'SELECT id, tenant_id, code, name, data_type, status, revision '
            'FROM attribute_definitions '
            'WHERE code IN (%s) AND tenant_id IN (0, ?)' % placeholders
        )
        try:
            rows = self.ds.query(sql, list(codes) + [tenant]) or []
        except Exception as exc:
            logger.warning('[attribute_provider] 属性定义读取失败: %s', exc)
            return {}

        # 平台层（0）在前、租户层在后 → 同 code 时后写覆盖 = 租户优先
        ordered = sorted(rows, key=lambda row: 0 if _as_int(
            row.get('tenant_id')) == 0 else 1)
        return {str(row.get('code')): row for row in ordered}

    def _load_rows(self, cfg: Dict[str, str], columns: Iterable[str],
                   ids: Tuple[str, ...], codes: Tuple[str, ...],
                   tenant: int, org_id: Optional[int]) -> List[Dict[str, Any]]:
        table = cfg['table']
        owner = cfg['owner']
        columns = set(columns)
        id_marks = ','.join('?' for _ in ids)
        code_marks = ','.join('?' for _ in codes)
        select_values = ', '.join('v.%s' % column for column in VALUE_COLUMNS)

        if 'attr_code' in columns:
            # item 形状：无 tenant_id，编码在值行上
            if org_id is None:
                order = 'v.%s, (v.org_id IS NOT NULL), v.id' % owner
                params: List[Any] = list(ids) + list(codes)
            else:
                order = ('v.%s, CASE WHEN v.org_id = ? THEN 0 '
                         'WHEN v.org_id IS NULL THEN 1 ELSE 2 END, v.id' % owner)
                # 占位符顺序：WHERE ids → WHERE codes → ORDER BY org
                params = list(ids) + list(codes) + [org_id]
            sql = (
                'SELECT v.%s AS owner_id, v.attr_code AS code, v.attribute_id, '
                '%s FROM %s v '
                'WHERE v.%s IN (%s) AND v.attr_code IN (%s) '
                'ORDER BY %s' % (
                    owner, select_values, table, owner, id_marks, code_marks,
                    order)
            )
        else:
            # party/batch 形状：编码在定义上，值行带 tenant_id / seq
            sql = (
                'SELECT v.%s AS owner_id, d.code AS code, v.attribute_id, '
                '%s FROM %s v '
                'JOIN attribute_definitions d ON d.id = v.attribute_id '
                'WHERE v.%s IN (%s) AND d.code IN (%s) '
                "AND d.status = 'active' AND d.tenant_id IN (0, ?) "
                'AND v.tenant_id IN (0, ?) '
                'ORDER BY v.%s, d.code, v.seq, v.id' % (
                    owner, select_values, table, owner, id_marks, code_marks,
                    owner)
            )
            params = list(ids) + list(codes) + [tenant, tenant]

        return self.ds.query(sql, params) or []

    def _table_columns(self, table: str) -> frozenset:
        key = (id(self.ds), table)
        now = time.time()
        cached = _COLUMNS_CACHE.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]
        try:
            rows = self.ds.query('PRAGMA table_info(%s)' % table) or []
        except Exception as exc:
            logger.warning('[attribute_provider] 表结构读取失败 %s: %s',
                           table, exc)
            return frozenset()
        columns = frozenset(
            str(row.get('name')) for row in rows if row.get('name'))
        _COLUMNS_CACHE[key] = (now + 300.0, columns)
        return columns


class AttributeProxy(dict):
    """表达式里的惰性属性代理（``attrs.code`` / ``attrs['code']``）。

    子类 dict 是为了复用 SafeExpressionEvaluator 的 ``value.get(attr)`` 分支；
    每次读取按需调用 Provider 并把访问记录交给 RuleContext（未引用的变量
    不进入 trace 快照）。
    """

    def __init__(self, provider: Optional[AttributeProvider],
                 object_type: str, owner_id: Any,
                 collector: Any = None, path_prefix: str = 'attrs'):
        super().__init__()
        self._provider = provider
        self._object_type = object_type
        self._owner_id = owner_id
        self._collector = collector
        self._path_prefix = path_prefix

    def _lookup(self, code: str) -> Dict[str, Any]:
        entry = None
        if self._provider is not None and self._owner_id is not None:
            entry = self._provider.resolve_one(
                self._object_type, self._owner_id, code)
        if entry is None:
            entry = _missing_entry(code)
        if self._collector is not None:
            path = '%s.%s' % (self._path_prefix, code)
            self._collector.record_attribute_access(path, entry)
        return entry

    def get(self, code: str, default: Any = None) -> Any:
        if not isinstance(code, str):
            return default
        value = self._lookup(code).get('value')
        return default if value is None else value

    def __getitem__(self, code: str) -> Any:
        if not isinstance(code, str):
            return None
        return self._lookup(code).get('value')
