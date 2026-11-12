# -*- coding: utf-8 -*-
"""规则挂起（holds）服务 —— spec-rule-model §10.4 A 纯派生方案的唯一入口。

口径:
  ① holds 是「是否被挂起」的唯一事实源；单据不落 hold_state 冗余列，
     状态由 ``EXISTS(holds WHERE released_at IS NULL)`` 派生。
  ② 释放 = UPDATE released_by / released_at，不删行（历史可追溯）。
  ③ 所有查询重复 ``released_at IS NULL``，才能命中部分索引 idx_holds_active；
     该谓词只在 ``_active_where()`` 写一次，禁止调用方手写 holds SQL。
  ④ apply 幂等：同一 (object_type, record_id, rule_key) 的 active 行由部分
     唯一索引 uq_holds_active 兜底，重复挂起视为无操作。
  ⑤ 本服务不管事务边界；写入方负责 ``with ds.transaction()``。
"""

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

TABLE = 'holds'
ACTIVE_PREDICATE = 'released_at IS NULL'


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class RuleHoldService:
    """挂起明细的写入 / 释放 / 查询；holds 的唯一写入口。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 统一查询构造器（active 谓词只在这里出现）
    # ------------------------------------------------------------------
    def _active_where(self, object_type: str, record_id: Any = None,
                      rule_key: Optional[str] = None) -> Any:
        clauses = ['object_type = ?', ACTIVE_PREDICATE]
        params: List[Any] = [object_type]
        if record_id is not None:
            clauses.append('record_id = ?')
            params.append(record_id)
        if rule_key is not None:
            clauses.append('rule_key = ?')
            params.append(rule_key)
        return ' AND '.join(clauses), params

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def apply(self, object_type: str, record_id: Any, rule_key: str,
              code: Optional[str] = None, reason: Optional[str] = None,
              applied_by: Optional[str] = None) -> bool:
        """挂起目标；已有同规则 active 行时不重复写。返回是否新建。"""
        if self.is_held(object_type, record_id, rule_key):
            return False
        try:
            self.ds.execute(
                'INSERT INTO %s (object_type, record_id, rule_key, code, '
                'reason, applied_by, applied_at) VALUES (?, ?, ?, ?, ?, ?, ?)'
                % TABLE,
                [object_type, record_id, rule_key, code, reason, applied_by,
                 _now()])
        except sqlite3.IntegrityError:
            # uq_holds_active 兜底：并发写同键时视为已挂起
            return False
        return True

    def release(self, object_type: str, record_id: Any = None,
                rule_key: Optional[str] = None,
                released_by: Optional[str] = None) -> int:
        """释放 active 行（UPDATE 不删行），返回释放条数。"""
        where, params = self._active_where(object_type, record_id, rule_key)
        cursor = self.ds.execute(
            'UPDATE %s SET released_by = ?, released_at = ? WHERE %s'
            % (TABLE, where),
            [released_by, _now()] + params)
        return getattr(cursor, 'rowcount', 0) or 0

    # ------------------------------------------------------------------
    # 查询（派生「是否被挂起」）
    # ------------------------------------------------------------------
    def is_held(self, object_type: str, record_id: Any,
                rule_key: Optional[str] = None) -> bool:
        where, params = self._active_where(object_type, record_id, rule_key)
        rows = self.ds.query(
            'SELECT 1 FROM %s WHERE %s LIMIT 1' % (TABLE, where), params)
        return bool(rows)

    def active_holds(self, object_type: str, record_id: Any,
                     rule_key: Optional[str] = None) -> List[Dict[str, Any]]:
        where, params = self._active_where(object_type, record_id, rule_key)
        return self.ds.query(
            'SELECT id, object_type, record_id, rule_key, code, reason, '
            'applied_by, applied_at FROM %s WHERE %s ORDER BY applied_at, id'
            % (TABLE, where), params)