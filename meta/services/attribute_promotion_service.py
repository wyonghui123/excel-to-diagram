# -*- coding: utf-8 -*-
"""属性提升（attribute_promotion）服务 —— spec 2026-11-09 §9.3.6 / TBD-003。

把一个字典层扩展属性提升为业务表的物理列，使它可以参与索引 / 计算 /
审计键。采用**一次性切换（cutover）**而非长期双写：

    pending → column_created → backfilled → verified → active

口径（与 AttributeProvider 一致）:
  - 只有平台层定义（tenant_id = 0）允许提升：物理列在业务表上是全租户共享的，
    租户私有属性提列会造成跨租户覆盖。
  - 多值属性（multi_value_flag = 1）不能提升为单列。
  - ``verified`` 之前 Provider 仍读值表；``active`` 之后物理列成为唯一 owner，
    值表只读（AttributeValueService 拒写，rule = attribute_promoted）。
  - 回填只搬运值表里非空的单值；物理列类型由 data_type 映射。
  - 每日一致性校验 ``check_consistency`` 只报告差异，不自动回滚。
"""

import logging
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

PROMOTION_TABLE = 'attribute_promotion'

STATUS_PENDING = 'pending'
STATUS_COLUMN_CREATED = 'column_created'
STATUS_BACKFILLED = 'backfilled'
STATUS_VERIFIED = 'verified'
STATUS_ACTIVE = 'active'

STATUSES = (
    STATUS_PENDING, STATUS_COLUMN_CREATED, STATUS_BACKFILLED,
    STATUS_VERIFIED, STATUS_ACTIVE,
)

#: 状态机：只允许单向前进（回滚靠停用 / 新记录，不做原地倒退）
TRANSITIONS = {
    STATUS_PENDING: (STATUS_COLUMN_CREATED,),
    STATUS_COLUMN_CREATED: (STATUS_BACKFILLED,),
    STATUS_BACKFILLED: (STATUS_VERIFIED,),
    STATUS_VERIFIED: (STATUS_ACTIVE,),
    STATUS_ACTIVE: (),
}

SYNC_MODES = ('cutover', 'write_through')

#: data_type → 物理列 SQL 类型（SQLite 亲和类型）
COLUMN_TYPES = {
    'string': 'TEXT',
    'number': 'REAL',
    'integer': 'INTEGER',
    'boolean': 'INTEGER',
    'date': 'TEXT',
    'datetime': 'TEXT',
}

#: data_type → 值表承载列
VALUE_COLUMN_BY_TYPE = {
    'string': 'value_text',
    'number': 'value_number',
    'integer': 'value_number',
    'boolean': 'value_boolean',
    'date': 'value_date',
    'datetime': 'value_datetime',
}

#: 对象 → 值表 / 归属列（与 AttributeProvider.VALUE_TABLES 同源）
VALUE_TABLES: Dict[str, Dict[str, str]] = {
    'item': {'table': 'item_attribute_values', 'owner': 'item_id'},
    'party': {'table': 'party_attribute_values', 'owner': 'party_id'},
    'batch': {'table': 'batch_attribute_values', 'owner': 'batch_id'},
}

#: 对象 → 业务表（物理列落点候选；调用方仍须显式传 target_table）
DEFAULT_TARGET_TABLES = {
    'item': 'items',
    'party': 'parties',
    'batch': 'batches',
}

_SAFE_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

#: 已提升属性写入保护快照（测试 / 写路径高频调用，短 TTL 即可）
_PROMOTED_CACHE: Dict[tuple, tuple] = {}
_PROMOTED_LOCK = threading.Lock()
_PROMOTED_TTL_SECONDS = 10.0


class AttributePromotionError(ValueError):
    """属性提升不满足前置条件 / 状态机约束。"""

    def __init__(self, message: str, rule: str, field_name: str = ''):
        super().__init__(message)
        self.rule = rule
        self.field_name = field_name


class AttributePromotionService:
    """属性提升的建列 / 回填 / 校验 / 切换。"""

    def __init__(self, data_source: Any):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 记录管理
    # ------------------------------------------------------------------
    def create(self, object_type: str, attribute_code: str,
               target_table: Optional[str] = None,
               target_column: Optional[str] = None,
               sync_mode: str = 'cutover') -> Dict[str, Any]:
        """登记一条提升记录（status = pending）。"""
        if object_type not in VALUE_TABLES:
            raise AttributePromotionError(
                f'对象类型 {object_type!r} 未注册值表，不能提升属性。',
                rule='promotion_object_unknown', field_name='object_type')
        if not _SAFE_IDENTIFIER.match(str(attribute_code or '')):
            raise AttributePromotionError(
                f'属性编码非法：{attribute_code!r}',
                rule='promotion_attribute_code_invalid',
                field_name='attribute_code')
        if sync_mode not in SYNC_MODES:
            raise AttributePromotionError(
                f'同步模式 {sync_mode!r} 不受支持：{SYNC_MODES}',
                rule='promotion_sync_mode_invalid', field_name='sync_mode')

        definition = self._definition(attribute_code)
        if definition is None:
            raise AttributePromotionError(
                f'属性定义不存在：{attribute_code}',
                rule='promotion_definition_missing',
                field_name='attribute_code')
        if _as_int(definition.get('tenant_id')) != 0:
            raise AttributePromotionError(
                '只有平台层属性（tenant_id = 0）可以提升为物理列；'
                '租户私有属性不进入业务表。',
                rule='promotion_platform_only', field_name='attribute_code')
        if _as_bool(definition.get('multi_value_flag')):
            raise AttributePromotionError(
                '多值属性不能提升为单个物理列。',
                rule='promotion_multi_value', field_name='attribute_code')
        if (definition.get('status') or 'active') != 'active':
            raise AttributePromotionError(
                '停用 / 废弃的属性不能提升。',
                rule='promotion_definition_inactive', field_name='attribute_code')

        table = str(target_table or DEFAULT_TARGET_TABLES[object_type])
        column = str(target_column or attribute_code)
        self._require_identifier(table, 'target_table')
        self._require_identifier(column, 'target_column')

        if self.get_by_code(object_type, attribute_code) is not None:
            raise AttributePromotionError(
                f'属性 {object_type}.{attribute_code} 已有提升记录。',
                rule='promotion_exists', field_name='attribute_code')

        now = _now()
        cursor = self.ds.execute(
            'INSERT INTO %s (object_type, attribute_code, target_table, '
            'target_column, data_type, sync_mode, status, backfilled_count, '
            'mismatch_count, created_at, updated_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)' % PROMOTION_TABLE,
            [object_type, attribute_code, table, column,
             definition.get('data_type') or 'string', sync_mode,
             STATUS_PENDING, now, now])
        self._commit()
        return self.get(cursor.lastrowid)

    def get(self, promotion_id: Any) -> Dict[str, Any]:
        rows = self.ds.query(
            'SELECT * FROM %s WHERE id = ? LIMIT 1' % PROMOTION_TABLE,
            [promotion_id]) or []
        if not rows:
            raise AttributePromotionError(
                f'提升记录 {promotion_id} 不存在。',
                rule='promotion_not_found', field_name='id')
        return rows[0]

    def get_by_code(self, object_type: str,
                    attribute_code: str) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT * FROM %s WHERE object_type = ? AND attribute_code = ? '
            'LIMIT 1' % PROMOTION_TABLE,
            [object_type, attribute_code]) or []
        return rows[0] if rows else None

    def list_by_status(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            rows = self.ds.query(
                'SELECT * FROM %s WHERE status = ? ORDER BY id' % PROMOTION_TABLE,
                [status]) or []
        else:
            rows = self.ds.query(
                'SELECT * FROM %s ORDER BY id' % PROMOTION_TABLE) or []
        return list(rows)

    def transition(self, promotion_id: Any, to_status: str) -> Dict[str, Any]:
        """状态机前进；非法跃迁直接拒绝。"""
        record = self.get(promotion_id)
        current = str(record.get('status') or STATUS_PENDING)
        if to_status not in STATUSES:
            raise AttributePromotionError(
                f'未知提升状态：{to_status!r}',
                rule='promotion_status_unknown', field_name='status')
        if to_status not in TRANSITIONS.get(current, ()):
            raise AttributePromotionError(
                f'提升状态不能从 {current} 跃迁到 {to_status}。',
                rule='promotion_transition_invalid', field_name='status')

        now = _now()
        self.ds.execute(
            'UPDATE %s SET status = ?, updated_at = ? WHERE id = ?'
            % PROMOTION_TABLE, [to_status, now, promotion_id])
        self._commit()
        return self.get(promotion_id)

    # ------------------------------------------------------------------
    # 同步动作
    # ------------------------------------------------------------------
    def create_column(self, promotion_id: Any) -> Dict[str, Any]:
        """建物理列（幂等）；完成后进入 column_created。"""
        record = self.get(promotion_id)
        self._require_status(record, STATUS_PENDING)
        table = str(record.get('target_table'))
        column = str(record.get('target_column'))
        self._require_identifier(table, 'target_table')
        self._require_identifier(column, 'target_column')

        existing = self._table_columns(table)
        if not existing:
            raise AttributePromotionError(
                f'目标业务表 {table} 不存在。',
                rule='promotion_target_table_missing', field_name='target_table')
        if column not in existing:
            column_type = COLUMN_TYPES.get(
                str(record.get('data_type') or 'string'), 'TEXT')
            self.ds.execute('ALTER TABLE %s ADD COLUMN %s %s'
                            % (table, column, column_type))
            self._commit()
            logger.info('[attribute_promotion] 建列 %s.%s (%s)',
                        table, column, column_type)
        return self.transition(promotion_id, STATUS_COLUMN_CREATED)

    def backfill(self, promotion_id: Any) -> Dict[str, Any]:
        """把值表非空值搬到物理列；完成后进入 backfilled。"""
        record = self.get(promotion_id)
        self._require_status(record, STATUS_COLUMN_CREATED)
        object_type = str(record.get('object_type'))
        if object_type not in VALUE_TABLES:
            raise AttributePromotionError(
                f'对象类型 {object_type!r} 未注册值表。',
                rule='promotion_object_unknown', field_name='object_type')

        cfg = VALUE_TABLES[object_type]
        value_column = VALUE_COLUMN_BY_TYPE.get(
            str(record.get('data_type') or 'string'), 'value_text')
        code = str(record.get('attribute_code'))
        if 'attr_code' in self._table_columns(cfg['table']):
            sql = ('SELECT %s AS owner_id, %s AS value FROM %s '
                   'WHERE attr_code = ? AND %s IS NOT NULL'
                   % (cfg['owner'], value_column, cfg['table'], value_column))
            params: Sequence[Any] = [code]
        else:
            sql = ('SELECT v.%s AS owner_id, v.%s AS value FROM %s v '
                   'JOIN attribute_definitions d ON d.id = v.attribute_id '
                   'WHERE d.code = ? AND d.tenant_id = 0 '
                   'AND v.%s IS NOT NULL ORDER BY v.%s, v.seq'
                   % (cfg['owner'], value_column, cfg['table'],
                      value_column, cfg['owner']))
            params = [code]
        rows = self.ds.query(sql, list(params)) or []

        table = str(record.get('target_table'))
        column = str(record.get('target_column'))
        updated = 0
        for row in rows:
            cursor = self.ds.execute(
                'UPDATE %s SET %s = ? WHERE id = ?' % (table, column),
                [row.get('value'), row.get('owner_id')])
            updated += max(cursor.rowcount or 0, 0)
        self._commit()
        self.ds.execute(
            'UPDATE %s SET backfilled_count = ?, updated_at = ? WHERE id = ?'
            % PROMOTION_TABLE, [updated, _now(), promotion_id])
        self._commit()
        logger.info('[attribute_promotion] 回填 %s.%s: %s 行',
                    object_type, code, updated)
        return self.transition(promotion_id, STATUS_BACKFILLED)

    def verify(self, promotion_id: Any) -> Dict[str, Any]:
        """对比值表与物理列；0 差异才允许进入 verified。"""
        record = self.get(promotion_id)
        self._require_status(record, STATUS_BACKFILLED)
        result = self._diff(record)
        self.ds.execute(
            'UPDATE %s SET mismatch_count = ?, last_checked_at = ?, '
            'updated_at = ? WHERE id = ?' % PROMOTION_TABLE,
            [result['mismatched'], _now(), _now(), promotion_id])
        self._commit()
        if result['mismatched']:
            return {
                'promotion_id': promotion_id,
                'status': STATUS_BACKFILLED,
                'checked': result['checked'],
                'mismatched': result['mismatched'],
                'diffs': result['diffs'],
            }
        record = self.transition(promotion_id, STATUS_VERIFIED)
        return {
            'promotion_id': promotion_id,
            'status': record['status'],
            'checked': result['checked'],
            'mismatched': 0,
            'diffs': [],
        }

    def activate(self, promotion_id: Any) -> Dict[str, Any]:
        """切换（cutover）：物理列成为唯一 owner，并失效 Provider 缓存。"""
        record = self.get(promotion_id)
        self._require_status(record, STATUS_VERIFIED)
        if _as_int(record.get('mismatch_count')) != 0:
            raise AttributePromotionError(
                '存在未消除的一致性差异，不能切换。',
                rule='promotion_mismatch_pending', field_name='status')

        now = _now()
        self.ds.execute(
            'UPDATE %s SET status = ?, activated_at = ?, updated_at = ? '
            'WHERE id = ?' % PROMOTION_TABLE,
            [STATUS_ACTIVE, now, now, promotion_id])
        self._commit()

        from meta.core.attribute_provider import AttributeProvider
        AttributeProvider.invalidate(
            object_type=str(record.get('object_type')),
            codes=[str(record.get('attribute_code'))])
        _invalidate_promoted_cache()
        logger.info('[attribute_promotion] 切换完成 %s.%s → %s.%s',
                    record.get('object_type'), record.get('attribute_code'),
                    record.get('target_table'), record.get('target_column'))
        return self.get(promotion_id)

    def check_consistency(self) -> List[Dict[str, Any]]:
        """每日一致性校验：逐条 active promotion 比对，不自动回滚。"""
        report: List[Dict[str, Any]] = []
        for record in self.list_by_status(STATUS_ACTIVE):
            result = self._diff(record)
            self.ds.execute(
                'UPDATE %s SET mismatch_count = ?, last_checked_at = ? '
                'WHERE id = ?' % PROMOTION_TABLE,
                [result['mismatched'], _now(), record.get('id')])
            self._commit()
            report.append({
                'promotion_id': record.get('id'),
                'object_type': record.get('object_type'),
                'attribute_code': record.get('attribute_code'),
                'checked': result['checked'],
                'mismatched': result['mismatched'],
                'diffs': result['diffs'],
            })
        return report

    # ------------------------------------------------------------------
    # 写保护查询（AttributeValueService 调用）
    # ------------------------------------------------------------------
    @staticmethod
    def active_codes(data_source: Any, object_type: str,
                     codes: Sequence[str]) -> set:
        """返回已 active 的属性编码集合；缺表 / 查询失败按未提升处理。"""
        code_list = [str(code) for code in codes if code]
        if not code_list:
            return set()
        key = (id(data_source), object_type, tuple(sorted(code_list)))
        now = _now_ts()
        with _PROMOTED_LOCK:
            cached = _PROMOTED_CACHE.get(key)
            if cached is not None and cached[0] > now:
                return set(cached[1])
        try:
            rows = data_source.query(
                'SELECT attribute_code FROM %s WHERE object_type = ? '
                "AND status = 'active' AND attribute_code IN (%s)"
                % (PROMOTION_TABLE, ','.join('?' for _ in code_list)),
                [object_type] + code_list) or []
        except Exception:  # promotion 表尚未创建
            return set()
        active = {str(row.get('attribute_code')) for row in rows}
        with _PROMOTED_LOCK:
            _PROMOTED_CACHE[key] = (now + _PROMOTED_TTL_SECONDS, frozenset(active))
        return active

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _diff(self, record: Dict[str, Any]) -> Dict[str, Any]:
        object_type = str(record.get('object_type'))
        cfg = VALUE_TABLES.get(object_type)
        if cfg is None:
            return {'checked': 0, 'mismatched': 0, 'diffs': []}
        code = str(record.get('attribute_code'))
        value_column = VALUE_COLUMN_BY_TYPE.get(
            str(record.get('data_type') or 'string'), 'value_text')
        if 'attr_code' in self._table_columns(cfg['table']):
            sql = ('SELECT %s AS owner_id, %s AS value FROM %s '
                   'WHERE attr_code = ? AND %s IS NOT NULL'
                   % (cfg['owner'], value_column, cfg['table'], value_column))
            params: List[Any] = [code]
        else:
            sql = ('SELECT v.%s AS owner_id, v.%s AS value FROM %s v '
                   'JOIN attribute_definitions d ON d.id = v.attribute_id '
                   'WHERE d.code = ? AND d.tenant_id = 0 '
                   'AND v.%s IS NOT NULL'
                   % (cfg['owner'], value_column, cfg['table'], value_column))
            params = [code]
        expected = {
            str(row.get('owner_id')): row.get('value')
            for row in (self.ds.query(sql, params) or [])
        }

        table = str(record.get('target_table'))
        column = str(record.get('target_column'))
        actual_rows = self.ds.query(
            'SELECT id AS owner_id, %s AS value FROM %s' % (column, table)) or []
        actual = {str(row.get('owner_id')): row.get('value')
                  for row in actual_rows}

        checked = 0
        mismatched = 0
        diffs: List[Dict[str, Any]] = []
        for owner_id in sorted(set(expected) | set(actual)):
            checked += 1
            if expected.get(owner_id) == actual.get(owner_id):
                continue
            mismatched += 1
            if len(diffs) < 50:
                diffs.append({
                    'owner_id': owner_id,
                    'expected': expected.get(owner_id),
                    'actual': actual.get(owner_id),
                })
        # 物理列有值而值表无对应行也算差异（防止切表后残留脏数据）
        return {'checked': checked, 'mismatched': mismatched, 'diffs': diffs}

    def _definition(self, code: str) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, tenant_id, code, data_type, multi_value_flag, status '
            'FROM attribute_definitions WHERE code = ? ORDER BY tenant_id '
            'LIMIT 1', [code]) or []
        return rows[0] if rows else None

    def _table_columns(self, table: str) -> frozenset:
        try:
            rows = self.ds.query('PRAGMA table_info(%s)' % table) or []
        except Exception:
            return frozenset()
        return frozenset(
            str(row.get('name')) for row in rows if row.get('name'))

    @staticmethod
    def _require_identifier(value: str, field_name: str) -> None:
        if not _SAFE_IDENTIFIER.match(value or ''):
            raise AttributePromotionError(
                f'{field_name} 不是合法标识符：{value!r}',
                rule='promotion_identifier_invalid', field_name=field_name)

    @staticmethod
    def _require_status(record: Dict[str, Any], expected: str) -> None:
        current = str(record.get('status') or STATUS_PENDING)
        if current != expected:
            raise AttributePromotionError(
                f'当前状态为 {current}，该操作要求 {expected}。',
                rule='promotion_status_conflict', field_name='status')

    def _commit(self) -> None:
        commit = getattr(self.ds, 'commit', None)
        if callable(commit):
            try:
                commit()
            except Exception:  # 连接池自行管理事务时忽略
                pass


def _invalidate_promoted_cache() -> None:
    with _PROMOTED_LOCK:
        _PROMOTED_CACHE.clear()


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _now_ts() -> float:
    return time.time()


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'y')
    return bool(value)
