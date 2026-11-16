# -*- coding: utf-8 -*-
"""导入 staging 服务（M3）：原始行落库 + 行级错误 + 错误报告。

依据: docs/specs/spec-integration-module-2026-11-15.md
  §3 单一事实模型 / §4.2 import_staging_rows / §6 FR-4 ~ FR-6 / §10 AC-4

职责边界:
  · 只写 `import_staging_rows`（事实表），批次身份复用 `task_runs.id`（弱引用）；
  · 不建批次表、不落批量计数列 —— 批次汇总按 status 实时聚合；
  · 不改变 `import_cascade` 的既有结果语义：staging 失败只告警，不阻断导入；
  · 错误报告按批次号确定性命名，文件丢失可就地重建。

状态词表: pending / valid / invalid / imported / skipped
错误码词表: REQUIRED_MISSING / TYPE_MISMATCH / FK_NOT_FOUND /
            DUPLICATE_KEY / VALIDATION_FAILED / UNKNOWN
"""

from __future__ import annotations

import csv
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TABLE = 'import_staging_rows'

TTL_DAYS = 7
#: 原始行超过该长度只保留摘要（spec TBD-2）
RAW_PAYLOAD_LIMIT = 64 * 1024
PAYLOAD_PREVIEW_CHARS = 1024

STATUSES = ('pending', 'valid', 'invalid', 'imported', 'skipped')
ERROR_CODES = (
    'REQUIRED_MISSING', 'TYPE_MISMATCH', 'FK_NOT_FOUND',
    'DUPLICATE_KEY', 'VALIDATION_FAILED', 'UNKNOWN',
)

#: 错误信息 → 词表化错误码（顺序敏感：先匹配更具体的语义）
_CODE_HINTS = (
    (('不能为空', '必填', '缺少', 'required'), 'REQUIRED_MISSING'),
    (('已被', '重复', 'duplicate', '已存在'), 'DUPLICATE_KEY'),
    (('不存在', '未找到', '找不到', 'not found', '外键', '未匹配'), 'FK_NOT_FOUND'),
    (('类型', '格式', '非法值', '枚举', '超出范围', '不是合法'), 'TYPE_MISMATCH'),
    (('长度', '超长', '过长', '超过'), 'VALIDATION_FAILED'),
)

INSERT_SQL = (
    'INSERT INTO %s (batch_run_id, batch_no, object_type, row_no, '
    'raw_payload, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)' % TABLE
)


class ImportStagingError(ValueError):
    """staging 参数或批次状态非法（API 映射 400/410）。"""


def classify_error(message: Optional[str]) -> str:
    """把自由文本错误信息归一到词表错误码。"""
    text = (message or '').lower()
    if not text:
        return 'UNKNOWN'
    for hints, code in _CODE_HINTS:
        if any(hint.lower() in text for hint in hints):
            return code
    return 'VALIDATION_FAILED'


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, 'isoformat'):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def _payload_text(columns: List[str], values: List[Any]) -> str:
    payload = {str(col): val for col, val in zip(columns, values)}
    text = json.dumps(payload, ensure_ascii=False, default=_json_default)
    if len(text) <= RAW_PAYLOAD_LIMIT:
        return text
    return json.dumps({
        '_truncated': True,
        'size': len(text),
        'preview': text[:PAYLOAD_PREVIEW_CHARS],
    }, ensure_ascii=False)


class ImportStagingService:
    """导入暂存账本读写。"""

    def __init__(self, data_source, export_root: Optional[str] = None):
        self.ds = data_source
        self.export_root = export_root or os.path.join(
            os.getcwd(), 'exports', 'import')

    # ---------------------------------------------------------------- 批次
    def new_batch_no(self) -> str:
        return 'STG-%s-%s' % (
            datetime.now().strftime('%Y%m%d-%H%M%S'),
            uuid.uuid4().hex[:6].upper(),
        )

    def stage_workbook(self, batch_no: str, file_path: str,
                       sheets: List[Dict[str, Any]],
                       batch_run_id: Optional[int] = None) -> Dict[str, Any]:
        """按 sheet 清单把 Excel 原始行落 staging。

        `sheets` 复用 import_cascade 已解析出的结构（name / object_type /
        columns），避免二次推断对象类型。
        """
        if not batch_no:
            raise ImportStagingError('batch_no 不能为空')
        if not sheets:
            return {'batch_no': batch_no, 'staged_rows': 0, 'by_object_type': {}}
        if not file_path or not os.path.exists(file_path):
            raise ImportStagingError('文件不存在: %s' % file_path)

        from openpyxl import load_workbook

        workbook = load_workbook(file_path, read_only=True, data_only=True)
        by_type: Dict[str, int] = {}
        created_at = _now()
        rows_to_insert: List[Tuple] = []
        try:
            for sheet in sheets:
                name = sheet.get('name')
                object_type = sheet.get('object_type')
                columns = list(sheet.get('columns') or [])
                if not name or not object_type or name not in workbook.sheetnames:
                    continue
                worksheet = workbook[name]
                count = 0
                # 表头在第 1 行，数据从第 2 行开始；row_no 直接可跳 Excel 行
                for row_no, row in enumerate(
                        worksheet.iter_rows(min_row=2, values_only=True), start=2):
                    values = list(row)
                    if all(v is None or (isinstance(v, str) and not v.strip())
                           for v in values):
                        continue
                    rows_to_insert.append((
                        batch_run_id, batch_no, object_type, row_no,
                        _payload_text(columns, values), 'pending', created_at,
                    ))
                    count += 1
                by_type[object_type] = by_type.get(object_type, 0) + count
        finally:
            try:
                workbook.close()
            except Exception:
                pass

        if rows_to_insert:
            self.ds.begin_transaction()
            try:
                for params in rows_to_insert:
                    self.ds.execute(INSERT_SQL, params)
                self.ds.commit()
            except Exception:
                self.ds.rollback()
                raise

        logger.info('[Staging] batch=%s rows=%d types=%d',
                    batch_no, len(rows_to_insert), len(by_type))
        return {
            'batch_no': batch_no,
            'staged_rows': len(rows_to_insert),
            'by_object_type': by_type,
        }

    # ---------------------------------------------------------------- 回写
    def apply_preview(self, batch_no: str, validation: Dict[str, Any],
                      sheets: Optional[List[Dict[str, Any]]] = None) -> int:
        """预览结果回写：仅把校验报错的行置 invalid，其余保持 pending。

        预览阶段没有逐行业务校验结果（`_validate_sheets` 只给汇总），
        因此不对未报错行做任何状态假设。
        """
        errors = list((validation or {}).get('errors') or [])
        if not errors:
            return 0
        # 校验错误里的 `sheet` 是 Excel sheet 名，需要映射回 object_type
        sheet_to_type = {
            s.get('name'): s.get('object_type') for s in (sheets or [])
            if s.get('name') and s.get('object_type')
        }
        marked = 0
        for item in errors:
            sheet_name = item.get('sheet')
            object_type = sheet_to_type.get(sheet_name) or sheet_name
            row_no = item.get('row')
            if not object_type or row_no is None:
                continue
            message = item.get('error') or item.get('message') or ''
            marked += self._mark_row(
                batch_no, object_type, row_no, 'invalid',
                error_field=item.get('field'),
                error_code=classify_error(message),
                error_message=message,
            )
        return marked

    def apply_result(self, batch_no: str, results: Dict[str, Any]) -> int:
        """执行结果回写：errors → invalid / skipped_items → skipped。

        成功明细在 `_import_sheet` 内部按 `_MAX_DETAIL` 截断，不能逐行对齐，
        故剩余 pending 行按该类型是否出现失败处理：
        无失败 → imported；有失败 → valid（已处理但无法逐行确认）。
        """
        marked = 0
        for object_type, sheet_result in (results or {}).items():
            if not isinstance(sheet_result, dict):
                continue
            for item in sheet_result.get('errors') or []:
                row_no = item.get('row')
                if row_no is None:
                    continue
                message = item.get('message') or item.get('error') or ''
                marked += self._mark_row(
                    batch_no, object_type, row_no, 'invalid',
                    error_field=item.get('field'),
                    error_code=classify_error(message),
                    error_message=message,
                )
            for item in sheet_result.get('skipped_items') or []:
                row_no = item.get('row')
                if row_no is None:
                    continue
                marked += self._mark_row(
                    batch_no, object_type, row_no, 'skipped',
                    error_field=None,
                    error_code=None,
                    error_message=item.get('reason'),
                )
            remaining_status = (
                'imported' if int(sheet_result.get('failed') or 0) == 0 else 'valid')
            self.ds.execute(
                'UPDATE %s SET status = ? WHERE batch_no = ? '
                "AND object_type = ? AND status = 'pending'" % TABLE,
                (remaining_status, batch_no, object_type))
            marked += 1
        return marked

    def _mark_row(self, batch_no: str, object_type: str, row_no: int,
                  status: str, error_field: Optional[str],
                  error_code: Optional[str],
                  error_message: Optional[str]) -> int:
        if status not in STATUSES:
            raise ImportStagingError('非法状态: %s' % status)
        cursor = self.ds.execute(
            'UPDATE %s SET status = ?, error_field = ?, error_code = ?, '
            'error_message = ? WHERE batch_no = ? AND object_type = ? '
            'AND row_no = ?' % TABLE,
            (status, error_field, error_code, error_message,
             batch_no, object_type, row_no))
        return int(getattr(cursor, 'rowcount', 0) or 0)

    # ---------------------------------------------------------------- 查询
    def summary(self, batch_no: str) -> Dict[str, Any]:
        """批次汇总：按 status 实时聚合 + TTL。"""
        cursor = self.ds.execute(
            'SELECT status, COUNT(*) FROM %s WHERE batch_no = ? '
            'GROUP BY status' % TABLE, (batch_no,))
        counts = {status: 0 for status in STATUSES}
        total = 0
        for status, count in cursor.fetchall():
            counts[status] = int(count)
            total += int(count)
        info = self.batch_info(batch_no)
        ready = counts['invalid'] > 0 and not (
            info.get('expired') if info else False)
        return {
            'batch_no': batch_no,
            'total': total,
            'by_status': counts,
            'invalid': counts['invalid'],
            'created_at': info.get('created_at') if info else None,
            'expires_at': info.get('expires_at') if info else None,
            'expired': bool(info.get('expired')) if info else False,
            'error_report_ready': ready,
            'error_report_url': (
                '/api/v2/integrations/imports/%s/error-report' % batch_no
            ) if ready else None,
        }

    def list_batches(self, object_type: Optional[str] = None,
                     page: int = 1, page_size: int = 20
                     ) -> Tuple[List[Dict[str, Any]], int]:
        """批次列表（FR-7 运行面入口）：按 batch_no 聚合，最新在前。

        不建批次表 —— 批次身份由 staging 行反向聚合（与 `summary` 同一口径）。
        """
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 200))

        where, params = '', []
        if object_type:
            where = ' WHERE object_type = ?'
            params.append(object_type)

        total_row = self.ds.execute(
            'SELECT COUNT(DISTINCT batch_no) FROM %s%s' % (TABLE, where),
            tuple(params)).fetchone()
        total = int(total_row[0]) if total_row else 0

        cursor = self.ds.execute(
            'SELECT batch_no, MAX(batch_run_id), MIN(created_at), COUNT(*), '
            "SUM(CASE WHEN status = 'invalid' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN status = 'imported' THEN 1 ELSE 0 END) "
            'FROM %s%s GROUP BY batch_no ORDER BY MIN(created_at) DESC, '
            'batch_no DESC LIMIT ? OFFSET ?' % (TABLE, where),
            tuple(params) + (page_size, (page - 1) * page_size))

        now = datetime.now()
        items: List[Dict[str, Any]] = []
        for (batch_no, batch_run_id, created_at, row_total,
             invalid, pending, imported) in cursor.fetchall():
            created_text = str(created_at)
            try:
                created_dt = datetime.fromisoformat(created_text)
            except ValueError:
                created_dt = now
            expires_dt = created_dt + timedelta(days=TTL_DAYS)
            items.append({
                'batch_no': batch_no,
                'batch_run_id': batch_run_id,
                'created_at': created_text,
                'expires_at': expires_dt.isoformat(timespec='seconds'),
                'ttl_days': TTL_DAYS,
                'expired': now > expires_dt,
                'total': int(row_total),
                'invalid': int(invalid),
                'pending': int(pending),
                'imported': int(imported),
            })
        return items, total

    def batch_info(self, batch_no: str) -> Optional[Dict[str, Any]]:
        cursor = self.ds.execute(
            'SELECT MIN(created_at), MAX(batch_run_id) FROM %s WHERE batch_no = ?'
            % TABLE, (batch_no,))
        row = cursor.fetchone()
        if not row or not row[0]:
            return None
        created_at = str(row[0])
        try:
            created_dt = datetime.fromisoformat(created_at)
        except ValueError:
            created_dt = datetime.now()
        expires_dt = created_dt + timedelta(days=TTL_DAYS)
        return {
            'batch_no': batch_no,
            'batch_run_id': row[1],
            'created_at': created_at,
            'expires_at': expires_dt.isoformat(timespec='seconds'),
            'ttl_days': TTL_DAYS,
            'expired': datetime.now() > expires_dt,
        }

    def list_rows(self, batch_no: str, status: Optional[str] = None,
                  error_code: Optional[str] = None,
                  object_type: Optional[str] = None,
                  page: int = 1, page_size: int = 50
                  ) -> Tuple[List[Dict[str, Any]], int]:
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 200))

        where = ['batch_no = ?']
        params: List[Any] = [batch_no]
        if status:
            where.append('status = ?')
            params.append(status)
        if error_code:
            where.append('error_code = ?')
            params.append(error_code)
        if object_type:
            where.append('object_type = ?')
            params.append(object_type)
        clause = ' WHERE ' + ' AND '.join(where)

        total_row = self.ds.execute(
            'SELECT COUNT(*) FROM %s%s' % (TABLE, clause),
            tuple(params)).fetchone()
        total = int(total_row[0]) if total_row else 0

        cursor = self.ds.execute(
            'SELECT id, batch_run_id, batch_no, object_type, row_no, status, '
            'error_field, error_code, error_message, target_record_id, '
            'created_at FROM %s%s ORDER BY object_type, row_no '
            'LIMIT ? OFFSET ?' % (TABLE, clause),
            tuple(params) + (page_size, (page - 1) * page_size))
        columns = [desc[0] for desc in cursor.description]
        items = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return items, total

    def get_row(self, batch_no: str, object_type: str, row_no: int
                ) -> Optional[Dict[str, Any]]:
        cursor = self.ds.execute(
            'SELECT * FROM %s WHERE batch_no = ? AND object_type = ? '
            'AND row_no = ?' % TABLE, (batch_no, object_type, int(row_no)))
        row = cursor.fetchone()
        if not row:
            return None
        columns = [desc[0] for desc in cursor.description]
        item = dict(zip(columns, row))
        item['raw_payload'] = self._decode_payload(item.get('raw_payload'))
        return item

    # ---------------------------------------------------------------- 错误报告
    def write_error_report(self, batch_no: str) -> str:
        """生成批次错误报告 CSV（UTF-8 BOM，可直接 Excel 打开）。"""
        cursor = self.ds.execute(
            'SELECT object_type, row_no, error_field, error_code, '
            "error_message FROM %s WHERE batch_no = ? AND status = 'invalid' "
            'ORDER BY object_type, row_no' % TABLE, (batch_no,))
        rows = cursor.fetchall()
        if not rows:
            return ''

        os.makedirs(self.export_root, exist_ok=True)
        path = self.error_report_path(batch_no)
        with open(path, 'w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.writer(handle)
            writer.writerow(['目标对象', '行号', '错误字段', '错误码', '错误信息'])
            for row in rows:
                writer.writerow([
                    '' if value is None else value for value in row
                ])
        logger.info('[Staging] 错误报告已生成: %s (%d 行)', path, len(rows))
        return path

    def error_report_path(self, batch_no: str) -> str:
        return os.path.join(self.export_root, 'error_report_%s.csv' % batch_no)

    def error_report(self, batch_no: str) -> str:
        """读取错误报告；文件缺失时按 staging 行就地重建。"""
        path = self.error_report_path(batch_no)
        if os.path.exists(path):
            return path
        return self.write_error_report(batch_no)

    # ---------------------------------------------------------------- 内部
    @staticmethod
    def _decode_payload(value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value