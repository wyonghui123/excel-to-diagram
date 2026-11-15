# -*- coding: utf-8 -*-
"""打印平台数据访问层（`print_templates` / `print_bindings` / `print_runs`）。

依据: docs/specs/spec-print-platform-2026-11-15.md §4 / D-PR-04 / D-PR-05 / D-PR-09
职责:
  · 只读写三张打印表；不渲染、不校验模板、不判权限（分别属 M2 / M3 / M4）；
  · `print_runs` 只追加，业务字段永不变更；run 生命周期只允许 running→终态；
  · 归档 PDF 存附件平台，本层只记/读 `attachment_id` 指针。

纪律:
  · 打印次数 / 最近打印时间 / 已打份数全部从 `print_runs` 派生，不回写业务表（D-PR-09）；
  · 重打复用归档字节（D-PR-08），因此本层不提供「重新渲染并覆盖」的写路径。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

TEMPLATE_TABLE = 'print_templates'
BINDING_TABLE = 'print_bindings'
RUN_TABLE = 'print_runs'

#: `print_templates.status` 合法取值（spec §4.1）
TEMPLATE_STATUSES = frozenset({'draft', 'active', 'archived', 'stale'})

#: `print_runs.trigger` 合法取值（spec §4.3）
RUN_TRIGGERS = frozenset({'preview', 'print', 'download', 'batch', 'reprint'})

#: `print_runs.status` 合法取值（spec §4.3）
RUN_STATUSES = frozenset({'running', 'succeeded', 'failed'})

#: `print_runs.watermark` 合法取值（存码不存文案，spec §4.3）
WATERMARKS = frozenset({'NONE', 'PREVIEW', 'DRAFT', 'REPRINT'})

_data_source = None


# ------------------------------------------------------------------ datasource

def init_print_repository(data_source) -> None:
    global _data_source
    _data_source = data_source


def _ds():
    global _data_source
    if _data_source is None:
        from meta.core.datasource import get_platform_data_source
        _data_source = get_platform_data_source()
    return _data_source


# ---------------------------------------------------------------------- helpers

def _now() -> str:
    return datetime.now().isoformat()


def _rows(cursor) -> List[Dict[str, Any]]:
    if cursor is None:
        return []
    rows = cursor.fetchall()
    cols = [d[0] for d in (cursor.description or [])]
    return [dict(zip(cols, row)) for row in rows]


def _one(cursor) -> Optional[Dict[str, Any]]:
    rows = _rows(cursor)
    return rows[0] if rows else None


# --------------------------------------------------------------------- 模板

def get_template(template_id: int) -> Optional[Dict[str, Any]]:
    return _one(_ds().execute(
        'SELECT * FROM %s WHERE id = ?' % TEMPLATE_TABLE, (template_id,)))


def list_templates(bo_code: Optional[str] = None,
                   type_code: Optional[str] = None,
                   status: Optional[str] = None) -> List[Dict[str, Any]]:
    """按接入点筛模板；`type_code=None` 不过滤，`type_code=''` 只看全类型共用。"""
    sql = 'SELECT * FROM %s WHERE 1 = 1' % TEMPLATE_TABLE
    params: List[Any] = []
    if bo_code is not None:
        sql += ' AND bo_code = ?'
        params.append(bo_code)
    if type_code is not None:
        sql += ' AND type_code = ?'
        params.append(type_code)
    if status is not None:
        sql += ' AND status = ?'
        params.append(status)
    sql += ' ORDER BY bo_code, type_code, code, version DESC'
    return _rows(_ds().execute(sql, tuple(params)))


def find_template(bo_code: str, type_code: str, code: str,
                  version: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """模板族定位；`version=None` 取该族最高版本。"""
    if version is None:
        return _one(_ds().execute(
            'SELECT * FROM %s WHERE bo_code = ? AND type_code = ? AND code = ? '
            'ORDER BY version DESC LIMIT 1' % TEMPLATE_TABLE,
            (bo_code, type_code, code)))
    return _one(_ds().execute(
        'SELECT * FROM %s WHERE bo_code = ? AND type_code = ? AND code = ? '
        'AND version = ?' % TEMPLATE_TABLE,
        (bo_code, type_code, code, version)))


def next_version(bo_code: str, type_code: str, code: str) -> int:
    row = _one(_ds().execute(
        'SELECT COALESCE(MAX(version), 0) AS v FROM %s '
        'WHERE bo_code = ? AND type_code = ? AND code = ?' % TEMPLATE_TABLE,
        (bo_code, type_code, code)))
    return int(row['v'] if row else 0) + 1


def insert_template(data: Dict[str, Any]) -> int:
    cursor = _ds().execute(
        'INSERT INTO %s (bo_code, type_code, code, name, version, status, html, '
        'css, variables_json, paper_size, orientation, margin_top, margin_right, '
        'margin_bottom, margin_left, scope_type, scope_id, effective_from, '
        'effective_to, created_by, created_at, published_at, archived_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
        % TEMPLATE_TABLE,
        (data['bo_code'], data.get('type_code') or '', data['code'], data['name'],
         int(data['version']), data['status'], data['html'], data.get('css') or '',
         data['variables_json'], data.get('paper_size') or 'A4',
         data.get('orientation') or 'portrait',
         float(data.get('margin_top', 10)), float(data.get('margin_right', 10)),
         float(data.get('margin_bottom', 10)), float(data.get('margin_left', 10)),
         data.get('scope_type') or 'system', data.get('scope_id'),
         data.get('effective_from'), data.get('effective_to'),
         data['created_by'], data.get('created_at') or _now(),
         data.get('published_at'), data.get('archived_at')))
    return cursor.lastrowid


def update_template_content(template_id: int, data: Dict[str, Any]) -> None:
    """仅 draft 可改内容（发布后只能新建版本，D-PR-05）。"""
    _ds().execute(
        'UPDATE %s SET name = ?, html = ?, css = ?, variables_json = ?, '
        'paper_size = ?, orientation = ?, margin_top = ?, margin_right = ?, '
        'margin_bottom = ?, margin_left = ?, effective_from = ?, effective_to = ? '
        "WHERE id = ? AND status = 'draft'" % TEMPLATE_TABLE,
        (data['name'], data['html'], data.get('css') or '',
         data['variables_json'], data.get('paper_size') or 'A4',
         data.get('orientation') or 'portrait',
         float(data.get('margin_top', 10)), float(data.get('margin_right', 10)),
         float(data.get('margin_bottom', 10)), float(data.get('margin_left', 10)),
         data.get('effective_from'), data.get('effective_to'), template_id))


def set_template_status(template_id: int, status: str) -> None:
    """状态流转（draft → active → archived / stale）。"""
    if status not in TEMPLATE_STATUSES:
        raise ValueError('非法模板状态: %r' % status)
    now = _now()
    if status == 'active':
        _ds().execute(
            'UPDATE %s SET status = ?, published_at = COALESCE(published_at, ?) '
            'WHERE id = ?' % TEMPLATE_TABLE, (status, now, template_id))
        return
    if status == 'archived':
        _ds().execute(
            'UPDATE %s SET status = ?, archived_at = ? WHERE id = ?'
            % TEMPLATE_TABLE, (status, now, template_id))
        return
    _ds().execute('UPDATE %s SET status = ? WHERE id = ?' % TEMPLATE_TABLE,
                  (status, template_id))


def supersede_active(bo_code: str, type_code: str, code: str,
                     keep_template_id: int) -> None:
    """同一模板族只保留一个 active 版本（发布新版本时把旧 active 置 archived）。"""
    _ds().execute(
        "UPDATE %s SET status = 'archived', archived_at = ? "
        "WHERE bo_code = ? AND type_code = ? AND code = ? "
        "AND status = 'active' AND id <> ?" % TEMPLATE_TABLE,
        (_now(), bo_code, type_code, code, keep_template_id))


# --------------------------------------------------------------------- 绑定

def get_binding(binding_id: int) -> Optional[Dict[str, Any]]:
    return _one(_ds().execute(
        'SELECT * FROM %s WHERE id = ?' % BINDING_TABLE, (binding_id,)))


def candidate_bindings(bo_code: str, type_code: str = '',
                       scope_type: Optional[str] = None,
                       scope_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """候选绑定：类型精确绑定优先于 BO 级默认（`type_code=''`），同层按 priority 升序。

    条件匹配（`condition_json` 对单据字段求值）属服务层，本层不做（D-PR-11）。
    """
    sql = ('SELECT * FROM %s WHERE bo_code = ? AND is_active = 1 '
           'AND type_code IN (?, \'\')' % BINDING_TABLE)
    params: List[Any] = [bo_code, type_code or '']
    if scope_type is not None:
        sql += ' AND (scope_type = ? OR scope_type = \'system\')'
        params.append(scope_type)
    if scope_id is not None:
        sql += ' AND (scope_id = ? OR scope_id IS NULL)'
        params.append(scope_id)
    sql += ' ORDER BY (type_code = ?) DESC, priority ASC, id ASC'
    params.append(type_code or '')
    return _rows(_ds().execute(sql, tuple(params)))


def list_bindings(bo_code: str, type_code: Optional[str] = None,
                  active_only: bool = True) -> List[Dict[str, Any]]:
    sql = 'SELECT * FROM %s WHERE bo_code = ?' % BINDING_TABLE
    params: List[Any] = [bo_code]
    if type_code is not None:
        sql += ' AND type_code = ?'
        params.append(type_code)
    if active_only:
        sql += ' AND is_active = 1'
    sql += ' ORDER BY type_code, priority ASC, id ASC'
    return _rows(_ds().execute(sql, tuple(params)))


def insert_binding(data: Dict[str, Any]) -> int:
    now = data.get('created_at') or _now()
    cursor = _ds().execute(
        'INSERT INTO %s (bo_code, type_code, scope_type, scope_id, '
        'condition_json, priority, template_id, is_default, is_active, '
        'created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
        % BINDING_TABLE,
        (data['bo_code'], data.get('type_code') or '',
         data.get('scope_type') or 'system', data.get('scope_id'),
         data.get('condition_json') or '{}', int(data.get('priority', 100)),
         int(data['template_id']), int(data.get('is_default', 0)),
         int(data.get('is_active', 1)), now, data.get('updated_at') or now))
    return cursor.lastrowid


def update_binding(binding_id: int, data: Dict[str, Any]) -> None:
    _ds().execute(
        'UPDATE %s SET condition_json = ?, priority = ?, template_id = ?, '
        'is_default = ?, is_active = ?, scope_type = ?, scope_id = ?, '
        'updated_at = ? WHERE id = ?' % BINDING_TABLE,
        (data.get('condition_json') or '{}', int(data.get('priority', 100)),
         int(data['template_id']), int(data.get('is_default', 0)),
         int(data.get('is_active', 1)), data.get('scope_type') or 'system',
         data.get('scope_id'), data.get('updated_at') or _now(), binding_id))


def deactivate_binding(binding_id: int) -> None:
    """下架而非物理删除（可幂等重放、可复原）。"""
    _ds().execute(
        'UPDATE %s SET is_active = 0, updated_at = ? WHERE id = ?'
        % BINDING_TABLE, (_now(), binding_id))


# --------------------------------------------------------------------- 打印记录

def insert_run(data: Dict[str, Any]) -> int:
    cursor = _ds().execute(
        'INSERT INTO %s (bo_code, type_code, doc_id, doc_no, doc_rev, '
        'template_id, template_version, trigger, is_formal, is_reprint, '
        'print_seq, watermark, attachment_id, payload_hash, job_run_id, '
        'status, error_code, error_message, operator_id, operator_name, '
        'created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '
        '?, ?, ?, ?, ?, ?)' % RUN_TABLE,
        (data['bo_code'], data.get('type_code') or '', str(data['doc_id']),
         data.get('doc_no'), data.get('doc_rev'), int(data['template_id']),
         int(data['template_version']), data['trigger'],
         int(data.get('is_formal', 0)), int(data.get('is_reprint', 0)),
         int(data.get('print_seq', 0)), data.get('watermark') or 'NONE',
         data.get('attachment_id'), data.get('payload_hash'),
         data.get('job_run_id'), data.get('status') or 'running',
         data.get('error_code'), data.get('error_message'),
         str(data['operator_id']), data['operator_name'],
         data.get('created_at') or _now()))
    return cursor.lastrowid


def finish_run(run_id: int, status: str,
               attachment_id: Optional[int] = None,
               payload_hash: Optional[str] = None,
               error_code: Optional[str] = None,
               error_message: Optional[str] = None) -> None:
    """run 生命周期收尾：只允许从 running 走向终态。"""
    if status not in RUN_STATUSES or status == 'running':
        raise ValueError('非法 run 终态: %r' % status)
    _ds().execute(
        'UPDATE %s SET status = ?, attachment_id = COALESCE(?, attachment_id), '
        'payload_hash = COALESCE(?, payload_hash), error_code = ?, '
        "error_message = ? WHERE id = ? AND status = 'running'" % RUN_TABLE,
        (status, attachment_id, payload_hash, error_code, error_message, run_id))


def get_run(run_id: int) -> Optional[Dict[str, Any]]:
    return _one(_ds().execute(
        'SELECT * FROM %s WHERE id = ?' % RUN_TABLE, (run_id,)))


def list_runs(bo_code: str, doc_id: Optional[str] = None,
              limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    sql = 'SELECT * FROM %s WHERE bo_code = ?' % RUN_TABLE
    params: List[Any] = [bo_code]
    if doc_id is not None:
        sql += ' AND doc_id = ?'
        params.append(str(doc_id))
    sql += ' ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?'
    params.extend([int(limit), int(offset)])
    return _rows(_ds().execute(sql, tuple(params)))


def last_formal_run(bo_code: str, doc_id: str) -> Optional[Dict[str, Any]]:
    """最近一次成功归档的正式件（重打复用其字节，D-PR-08）。"""
    return _one(_ds().execute(
        'SELECT * FROM %s WHERE bo_code = ? AND doc_id = ? AND is_formal = 1 '
        "AND status = 'succeeded' AND attachment_id IS NOT NULL "
        'ORDER BY print_seq DESC, id DESC LIMIT 1' % RUN_TABLE,
        (bo_code, str(doc_id))))


def next_print_seq(bo_code: str, doc_id: str) -> int:
    row = _one(_ds().execute(
        'SELECT COALESCE(MAX(print_seq), 0) AS s FROM %s '
        'WHERE bo_code = ? AND doc_id = ? AND is_formal = 1' % RUN_TABLE,
        (bo_code, str(doc_id))))
    return int(row['s'] if row else 0) + 1


def print_stats(bo_code: str, doc_id: str) -> Dict[str, int]:
    """打印次数派生（D-PR-09）：正式份数 / 全部次数 / 重打次数。"""
    row = _one(_ds().execute(
        'SELECT COUNT(*) AS total, '
        'COALESCE(SUM(is_formal), 0) AS formal, '
        'COALESCE(SUM(is_reprint), 0) AS reprint '
        "FROM %s WHERE bo_code = ? AND doc_id = ? AND status = 'succeeded'"
        % RUN_TABLE, (bo_code, str(doc_id))))
    if not row:
        return {'total': 0, 'formal': 0, 'reprint': 0}
    return {'total': int(row['total'] or 0),
            'formal': int(row['formal'] or 0),
            'reprint': int(row['reprint'] or 0)}