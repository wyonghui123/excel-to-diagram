# -*- coding: utf-8 -*-
"""项目结构基线服务（G15 ETO P2-2）

依据:
  docs/specs/spec-project-g15-eto-solution-2026-11-04.md §4.2（P2-2 项目结构基线指针表）

定位:
  只维护「指针 + 哈希」。表里不存 BOM 行，也不参与成本 / MRP；
  结构内容的事实源仍是 item_structures / item_structure_lines。

哈希口径（与表上真实列名逐字一致，禁止照抄过期列名）:
  头  : revision|base_qty|base_uom_id
  行  : 按 line_no 排序的
        component_item_id|qty_per|fixed_qty|scrap_rate|optional_flag|
        default_flag|default_qty|min_qty|max_qty|operation_seq|phantom_flag|
        substitute_group_code
  数值去尾零（1.0 与 1 等价）、布尔转 1/0、无值不拼；
  不拼行 id / 时间戳；整串 sha256 hex。

守卫:
  · 项目 design_mode 必须是 standard（engineered 项目拒绝）。
  · structure_id 非 0 时必须属同一 item_id / usage / alternative_no。
  · 同键 upsert 一条；无子表，禁止行级维护（note 不承载 BOM 行）。
"""
import hashlib
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

STRUCTURE_TABLE = 'item_structures'
LINE_TABLE = 'item_structure_lines'
BASELINE_TABLE = 'project_structure_baselines'

STATUS_OK = 'OK'
STATUS_DRIFT = 'DRIFT'
STATUS_STRUCTURE_MISSING = 'STRUCTURE_MISSING'

_DEFAULT_USAGE = 'production'

LINE_HASH_FIELDS: Tuple[str, ...] = (
    'component_item_id', 'qty_per', 'fixed_qty', 'scrap_rate',
    'optional_flag', 'default_flag', 'default_qty', 'min_qty', 'max_qty',
    'operation_seq', 'phantom_flag', 'substitute_group_code',
)
_NUMERIC_FIELDS = frozenset((
    'component_item_id', 'qty_per', 'fixed_qty', 'scrap_rate', 'default_qty',
    'min_qty', 'max_qty', 'operation_seq',
))
_FLAG_FIELDS = frozenset(('optional_flag', 'default_flag', 'phantom_flag'))


class ProjectStructureBaselineError(ValueError):
    """项目结构基线业务错误；`code` 即 rule 码，HTTP 统一 400。"""

    def __init__(self, code: str, message: str, field_name: str = '',
                 details: Optional[Dict[str, Any]] = None):
        super().__init__('[%s] %s' % (code, message))
        self.code = code
        self.rule = code
        self.message = message
        self.field_name = field_name
        self.details = details or {}
        self.http_status = 400

    def to_dict(self) -> Dict[str, Any]:
        return {'code': self.code, 'message': self.message,
                'field_name': self.field_name, 'details': self.details,
                'success': False}


# ─────────────────────────────────────────────────────────────────────────────
# 哈希格式化
# ─────────────────────────────────────────────────────────────────────────────

def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _format_text(value: Any) -> str:
    if _blank(value):
        return ''
    return str(value).strip()


def _format_number(value: Any) -> str:
    """数值去尾零：1.0 → 1、1.50 → 1.5；无法解析时按原文本（去空白）。"""
    if _blank(value):
        return ''
    try:
        dec = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return _format_text(value)
    if not dec.is_finite():
        return _format_text(value)
    text = format(dec.normalize(), 'f')
    return '0' if text in ('-0', '') else text


def _format_flag(value: Any) -> str:
    if _blank(value):
        return ''
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, (int, float, Decimal)):
        return '1' if value else '0'
    text = str(value).strip().lower()
    if text in ('1', 'true', 'yes', 'y'):
        return '1'
    return '0'


def _format_field(field: str, value: Any) -> str:
    if field in _FLAG_FIELDS:
        return _format_flag(value)
    if field in _NUMERIC_FIELDS:
        return _format_number(value)
    return _format_text(value)


def _line_text(line: Mapping[str, Any]) -> str:
    return '|'.join(_format_field(field, line.get(field))
                    for field in LINE_HASH_FIELDS)


def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if _blank(value):
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _to_date_text(value: Any) -> str:
    if value is None:
        return ''
    return str(value).strip()[:10]


def _now_text() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ─────────────────────────────────────────────────────────────────────────────
# 服务
# ─────────────────────────────────────────────────────────────────────────────

class ProjectStructureBaselineService:
    """项目结构基线（指针 + 哈希）。查询方法可覆写，便于单测注入。"""

    def __init__(self, data_source=None):
        self._ds = data_source

    @property
    def ds(self):
        if self._ds is None:
            from meta.core.datasource import get_data_source
            from meta.core.db_path import get_meta_db_path
            self._ds = get_data_source(
                'sqlite', database=get_meta_db_path())
        return self._ds

    # ---------- 解析结构版本 ----------

    def resolve_structure(self, item_id: Any, usage: Any,
                          alternative_no: Any, structure_id: Any,
                          as_of: Any = None) -> Dict[str, Any]:
        """0 → 时点 active 版本；非 0 → 钉住版本（并校验业务键归属）。"""
        item_id = _to_int(item_id)
        if item_id is None:
            raise ProjectStructureBaselineError(
                'BASELINE_ITEM_REQUIRED', '缺少物料 item_id', 'item_id')
        usage = _format_text(usage) or _DEFAULT_USAGE
        alternative_no = _to_int(alternative_no, 1)
        pinned = _to_int(structure_id, 0) or 0
        as_of_text = _to_date_text(as_of) or date.today().isoformat()

        if pinned == 0:
            active = self._find_active_structure(
                item_id, usage, alternative_no, as_of_text)
            if not active:
                raise ProjectStructureBaselineError(
                    'BASELINE_STRUCTURE_MISSING',
                    '物料 %s 在 %s 没有生效结构版本（usage=%s, alt=%s）'
                    % (item_id, as_of_text, usage, alternative_no),
                    'structure_id')
            header = self._fetch_header(active.get('id'))
            if not header:
                raise ProjectStructureBaselineError(
                    'BASELINE_STRUCTURE_MISSING',
                    '生效结构 %s 读取失败' % active.get('id'), 'structure_id')
            return header

        header = self._fetch_header(pinned)
        if not header:
            raise ProjectStructureBaselineError(
                'BASELINE_STRUCTURE_MISMATCH',
                '钉住的结构 %s 不存在，或不属于该物料结构' % pinned,
                'structure_id')
        self._assert_same_key(header, item_id, usage, alternative_no)
        return header

    def compute_hash(self, structure: Mapping[str, Any]) -> str:
        """按口径对头 + 行求 sha256（行序无关、数值去尾零、布尔 1/0）。"""
        structure = structure or {}
        lines = structure.get('lines')
        if lines is None:
            structure_id = structure.get('id')
            lines = self._fetch_lines(structure_id) if structure_id else []
        header = '|'.join((
            _format_text(structure.get('revision')),
            _format_number(structure.get('base_qty')),
            _format_number(structure.get('base_uom_id')),
        ))
        keyed = [(_to_int(line.get('line_no'), 0) or 0, _line_text(line))
                 for line in (lines or [])]
        keyed.sort(key=lambda item: (item[0], item[1]))
        payload = '\n'.join([header] + [text for _no, text in keyed])
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    # ---------- 建基 / 漂移 / 刷新 ----------

    def create_or_update(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        """同键 upsert：project_id + item_id + usage + alternative_no。"""
        payload = payload or {}
        project_id = _to_int(payload.get('project_id'))
        item_id = _to_int(payload.get('item_id'))
        if project_id is None:
            raise ProjectStructureBaselineError(
                'BASELINE_PROJECT_REQUIRED', '缺少 project_id', 'project_id')
        if item_id is None:
            raise ProjectStructureBaselineError(
                'BASELINE_ITEM_REQUIRED', '缺少 item_id', 'item_id')
        usage = _format_text(payload.get('usage')) or _DEFAULT_USAGE
        alternative_no = _to_int(payload.get('alternative_no'), 1)
        structure_id = _to_int(payload.get('structure_id'), 0) or 0
        note = payload.get('note')

        self._assert_project_design_mode(project_id)
        structure = self.resolve_structure(
            item_id, usage, alternative_no, structure_id,
            payload.get('as_of'))
        baseline_hash = self.compute_hash(structure)
        captured_at = _now_text()

        existing = self.ds.query(
            'SELECT id, note FROM %s WHERE project_id = ? AND item_id = ? '
            'AND usage = ? AND alternative_no = ?' % BASELINE_TABLE,
            [project_id, item_id, usage, alternative_no])
        if existing:
            baseline_id = existing[0].get('id')
            columns = ['structure_id = ?', 'baseline_hash = ?',
                       'captured_at = ?']
            params: List[Any] = [structure_id, baseline_hash, captured_at]
            if not _blank(note):
                columns.append('note = ?')
                params.append(str(note).strip())
            self.ds.execute(
                'UPDATE %s SET %s WHERE id = ?'
                % (BASELINE_TABLE, ', '.join(columns)),
                params + [baseline_id])
        else:
            cur = self.ds.execute(
                'INSERT INTO %s (project_id, item_id, usage, alternative_no, '
                'structure_id, baseline_hash, captured_at, note) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)' % BASELINE_TABLE,
                [project_id, item_id, usage, alternative_no, structure_id,
                 baseline_hash, captured_at,
                 None if _blank(note) else str(note).strip()])
            baseline_id = getattr(cur, 'lastrowid', None)
            if baseline_id is None:
                rows = self.ds.query(
                    'SELECT id FROM %s WHERE project_id = ? AND item_id = ? '
                    'AND usage = ? AND alternative_no = ?' % BASELINE_TABLE,
                    [project_id, item_id, usage, alternative_no])
                baseline_id = rows[0].get('id') if rows else None
        self.ds.commit()
        return self._fetch_baseline(baseline_id)

    def check_drift(self, baseline_id: Any,
                    as_of: Any = None) -> Dict[str, Any]:
        """OK / DRIFT / STRUCTURE_MISSING（不抛异常，供 action 回执）。"""
        baseline = self._require_baseline(baseline_id)
        try:
            structure = self.resolve_structure(
                baseline.get('item_id'), baseline.get('usage'),
                baseline.get('alternative_no'), baseline.get('structure_id'),
                as_of)
        except ProjectStructureBaselineError as error:
            if error.code in ('BASELINE_STRUCTURE_MISSING',
                              'BASELINE_STRUCTURE_MISMATCH'):
                return self._drift_result(baseline, STATUS_STRUCTURE_MISSING,
                                          None, None)
            raise

        current_hash = self.compute_hash(structure)
        status = STATUS_OK if current_hash == baseline.get('baseline_hash') \
            else STATUS_DRIFT
        return self._drift_result(baseline, status, current_hash,
                                  structure.get('id'))

    def refresh(self, baseline_id: Any, note: Any = None,
                as_of: Any = None) -> Dict[str, Any]:
        """按当前解析到的结构重算哈希并回写基线（幂等）。"""
        baseline = self._require_baseline(baseline_id)
        structure = self.resolve_structure(
            baseline.get('item_id'), baseline.get('usage'),
            baseline.get('alternative_no'), baseline.get('structure_id'),
            as_of)
        baseline_hash = self.compute_hash(structure)
        captured_at = _now_text()
        columns = ['baseline_hash = ?', 'captured_at = ?']
        params: List[Any] = [baseline_hash, captured_at]
        if note is not None:
            columns.append('note = ?')
            params.append(None if _blank(note) else str(note).strip())
        self.ds.execute(
            'UPDATE %s SET %s WHERE id = ?'
            % (BASELINE_TABLE, ', '.join(columns)),
            params + [baseline.get('id')])
        self.ds.commit()
        return self._fetch_baseline(baseline.get('id'))

    # ---------- 查询（可覆写，便于单测注入）----------

    def _fetch_header(self, structure_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, item_id, usage, alternative_no, revision, status, '
            'base_qty, base_uom_id, valid_from, valid_to '
            'FROM %s WHERE id = ?' % STRUCTURE_TABLE, [structure_id])
        return rows[0] if rows else None

    def _fetch_lines(self, structure_id: Any) -> List[Dict[str, Any]]:
        columns = ', '.join(('line_no',) + LINE_HASH_FIELDS)
        rows = self.ds.query(
            'SELECT %s FROM %s WHERE structure_id = ? ORDER BY line_no'
            % (columns, LINE_TABLE), [structure_id])
        return rows or []

    def _fetch_baseline(self, baseline_id: Any) -> Optional[Dict[str, Any]]:
        rows = self.ds.query(
            'SELECT id, project_id, item_id, usage, alternative_no, '
            'structure_id, baseline_hash, captured_at, note '
            'FROM %s WHERE id = ?' % BASELINE_TABLE, [baseline_id])
        return rows[0] if rows else None

    def _require_baseline(self, baseline_id: Any) -> Dict[str, Any]:
        baseline = self._fetch_baseline(_to_int(baseline_id))
        if not baseline:
            raise ProjectStructureBaselineError(
                'BASELINE_NOT_FOUND', '项目结构基线不存在: %s' % baseline_id,
                'baseline_id')
        return baseline

    def _find_active_structure(self, item_id: Any, usage: Any,
                               alternative_no: Any,
                               as_of: str) -> Optional[Dict[str, Any]]:
        """复用选择服务的私有解析（`_covers` 字符串比较口径）；重叠原样抛出。"""
        from meta.services.item_structure_select_service import (
            ItemStructureSelectService,
        )
        selector = ItemStructureSelectService(self.ds)
        return selector._find_active_structure(
            item_id, usage, alternative_no, as_of)

    def _assert_project_design_mode(self, project_id: int) -> None:
        rows = self.ds.query(
            'SELECT design_mode FROM projects WHERE id = ?', [project_id])
        if not rows:
            raise ProjectStructureBaselineError(
                'BASELINE_PROJECT_NOT_FOUND', '项目不存在: %s' % project_id,
                'project_id')
        design_mode = _format_text(rows[0].get('design_mode')).lower() \
            or 'standard'
        if design_mode != 'standard':
            raise ProjectStructureBaselineError(
                'BASELINE_DESIGN_MODE_INVALID',
                '项目 %s 的 design_mode=%s，结构基线只允许 standard 项目'
                % (project_id, design_mode),
                'project_id', {'design_mode': design_mode})

    @staticmethod
    def _assert_same_key(header: Mapping[str, Any], item_id: int,
                         usage: str, alternative_no: int) -> None:
        same = (_to_int(header.get('item_id')) == item_id
                and _format_text(header.get('usage')) == usage
                and _to_int(header.get('alternative_no'), 1) == alternative_no)
        if not same:
            raise ProjectStructureBaselineError(
                'BASELINE_STRUCTURE_MISMATCH',
                '结构 %s 不属于 item_id=%s / usage=%s / alternative_no=%s'
                % (header.get('id'), item_id, usage, alternative_no),
                'structure_id', {
                    'structure_id': header.get('id'),
                    'item_id': header.get('item_id'),
                    'usage': header.get('usage'),
                    'alternative_no': header.get('alternative_no'),
                })

    @staticmethod
    def _drift_result(baseline: Mapping[str, Any], status: str,
                      current_hash: Optional[str],
                      structure_id: Optional[int]) -> Dict[str, Any]:
        return {
            'baseline_id': baseline.get('id'),
            'status': status,
            'structure_id': structure_id,
            'baseline_structure_id': baseline.get('structure_id'),
            'baseline_hash': baseline.get('baseline_hash'),
            'current_hash': current_hash,
            'captured_at': baseline.get('captured_at'),
        }


# ─────────────────────────────────────────────────────────────────────────────
# BO Action handlers
# ─────────────────────────────────────────────────────────────────────────────

def _get_ds():
    from meta.core.datasource import get_data_source
    from meta.core.db_path import get_meta_db_path
    return get_data_source('sqlite', database=get_meta_db_path())


def _baseline_id(params: Mapping[str, Any]) -> Any:
    params = params or {}
    value = params.get('baseline_id')
    if value in (None, ''):
        value = params.get('id')
    return value


def _fail(message: str, code: str) -> Dict[str, Any]:
    return {'success': False, 'data': None, 'message': message, 'code': code}


def check_drift_handler(params: Mapping[str, Any],
                        context=None) -> Dict[str, Any]:
    """BO Action：`project_structure_baseline.check_drift`。"""
    baseline_id = _baseline_id(params)
    if _blank(baseline_id):
        return _fail('缺少 baseline_id', 'INVALID_ARGUMENT')
    try:
        result = ProjectStructureBaselineService().check_drift(baseline_id)
    except ProjectStructureBaselineError as error:
        return _fail(error.message, error.code)
    except Exception as error:  # noqa: BLE001 - 统一转失败信封
        logger.exception('[project_structure_baseline] 漂移检查失败: %s', error)
        return _fail('漂移检查失败: %s' % error, 'BASELINE_CHECK_FAILED')
    return {
        'success': True,
        'data': result,
        'message': '漂移检查完成: %s' % result['status'],
    }


def refresh_handler(params: Mapping[str, Any],
                    context=None) -> Dict[str, Any]:
    """BO Action：`project_structure_baseline.refresh`（幂等）。"""
    baseline_id = _baseline_id(params)
    if _blank(baseline_id):
        return _fail('缺少 baseline_id', 'INVALID_ARGUMENT')
    note = (params or {}).get('note')
    try:
        result = ProjectStructureBaselineService().refresh(
            baseline_id, note=note)
    except ProjectStructureBaselineError as error:
        return _fail(error.message, error.code)
    except Exception as error:  # noqa: BLE001 - 统一转失败信封
        logger.exception('[project_structure_baseline] 刷新失败: %s', error)
        return _fail('刷新失败: %s' % error, 'BASELINE_REFRESH_FAILED')
    return {
        'success': True,
        'data': result,
        'message': '项目结构基线已刷新',
    }
