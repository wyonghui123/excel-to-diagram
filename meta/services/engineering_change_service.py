# -*- coding: utf-8 -*-
"""G4 工程 BOM 消费方：工程变更单服务（Engineering Change Management, ECM）

依据:
  docs/specs/spec-project-g4-engineering-bom-2026-11-03.md
    §5 对象模型 / §6 核心流程与关键规则 / §9 迁移 / §11 验收
  §13 Q1–Q5 决策（表头不落结构 id、P1 单 target、不接 workflow、审批 + apply 分离）

【本文件守什么】
  EC-1 diff_structures：按 component_item_id + substitute_group_code + operation_seq
        对账工程 BOM 与生产 BOM，实时计算不落表；同键多行 → ambiguous，不自动决定。
  EC-2 create_change：5 条创建校验 + P1「同一变更单 target_structure_id 必须相同」
        + 创建时 revision 快照（供 apply 防并发改版）。
  EC-3 状态机：draft → in_review → approved → applied；rejected / cancelled 终态。
        权限与前置校验在服务层强制，不依赖通用 BO 状态机。
  EC-4 apply：不新建结构版本、不改 item_structures.revision；modify = 关旧 + 从来源
        工程行复制插新；add = 复制插新；remove = 只关旧。整段显式事务，失败回滚。
        applied 重复调用幂等返回。
  EC-5 where_used：只读 where-used 影响预览（受影响父项结构 + 在途工单），不写任何表。
  EC-6 所有动作写 change_events 审计（操作人 / 时间 / 前后状态），fail-open 不阻断业务。

事务边界:
  本服务自行开事务（`with self.ds.transaction()`）；调用方再包一层也无害（嵌套空转）。
"""
import json
import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from meta.services.item_structure_explode_service import _covers

logger = logging.getLogger(__name__)

HEADER_TABLE = 'engineering_changes'
LINE_TABLE = 'engineering_change_lines'

STATUS_DRAFT = 'draft'
STATUS_IN_REVIEW = 'in_review'
STATUS_APPROVED = 'approved'
STATUS_APPLIED = 'applied'
STATUS_REJECTED = 'rejected'
STATUS_CANCELLED = 'cancelled'
STATUSES = (STATUS_DRAFT, STATUS_IN_REVIEW, STATUS_APPROVED, STATUS_APPLIED,
            STATUS_REJECTED, STATUS_CANCELLED)

CHANGE_TYPES = ('new', 'revise', 'obsolete')
LINE_TYPES = ('add', 'modify', 'remove')

USAGE_PRODUCTION = 'production'
USAGE_ENGINEERING = 'engineering'

IN_FLIGHT_EXCLUDED_STATUSES = ('Closed', 'Cancelled')

# apply 时从来源工程结构行复制到目标生产结构行的字段（structure_id / line_no /
# valid_from / 审计列单独处理）
COPY_LINE_FIELDS = (
    'component_item_id', 'qty_per', 'fixed_qty', 'scrap_rate', 'optional_flag',
    'default_flag', 'default_qty', 'min_qty', 'max_qty', 'valid_to',
    'operation_seq', 'phantom_flag', 'substitute_group_code',
    'included_in_base_price', 'bom_price', 'note',
)

# diff 判定「修改」的比较字段
DIFF_COMPARE_FIELDS = ('qty_per', 'fixed_qty', 'valid_to', 'optional_flag')


class EngineeringChangeError(Exception):
    """工程变更领域错误（API 层按 rule 映射 HTTP 状态码）。"""

    def __init__(self, message: str, rule: str,
                 field_name: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.rule = rule
        self.field_name = field_name
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {'rule': self.rule, 'field_name': self.field_name,
                'message': self.message, 'details': self.details}


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _text(value: Any) -> str:
    return '' if value is None else str(value).strip()


def _date_text(value: Any) -> str:
    """统一成 YYYY-MM-DD；空值返回 ''。"""
    if value is None or value == '':
        return ''
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()[:10]


def _parse_day(value: Any) -> date:
    text = _date_text(value)
    if not text:
        raise EngineeringChangeError('生效日不能为空', 'EC_EFFECTIVE_DATE_INVALID',
                                     'effective_date')
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except ValueError:
        raise EngineeringChangeError(
            f'生效日格式非法（需 YYYY-MM-DD）: {value}', 'EC_EFFECTIVE_DATE_INVALID',
            'effective_date')


def _num(value: Any) -> Optional[float]:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _match_key(component_item_id: Any, substitute_group_code: Any,
               operation_seq: Any) -> str:
    return '%s|%s|%s' % (_text(component_item_id), _text(substitute_group_code),
                         _text(operation_seq))


def _key_of(line: Dict[str, Any]) -> Tuple[str, str, str]:
    return (_text(line.get('component_item_id')),
            _text(line.get('substitute_group_code')),
            _text(line.get('operation_seq')))


def _normalize(value: Any) -> Any:
    """diff 比较归一：None / '' / 0 的表示差异不产生假阳。"""
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return float(value)
    return str(value).strip()


def _prev_day(day: date) -> str:
    return (day - timedelta(days=1)).isoformat()


class EngineeringChangeService:
    """工程变更单服务。所有写方法自行开事务。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ==================================================================
    # 事务 / 基础查询
    # ==================================================================
    @contextmanager
    def _transaction(self):
        tx = getattr(self.ds, 'transaction', None)
        if tx is None:
            yield
            return
        with tx():
            yield

    def _fetch_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[Dict]:
        rows = self.ds.query(sql, list(params))
        return rows[0] if rows else None

    def _fetch_all(self, sql: str, params: Iterable[Any] = ()) -> List[Dict]:
        return self.ds.query(sql, list(params))

    def _insert(self, table: str, row: Dict[str, Any]) -> int:
        columns = list(row.keys())
        sql = 'INSERT INTO %s (%s) VALUES (%s)' % (
            table, ', '.join(columns), ', '.join('?' * len(columns)))
        cursor = self.ds.execute(sql, [row[c] for c in columns])
        return int(getattr(cursor, 'lastrowid', 0) or 0)

    def _load_structure(self, structure_id: Any, usage: Optional[str] = None,
                        required: bool = True) -> Optional[Dict]:
        if _blank(structure_id):
            if required:
                raise EngineeringChangeError('结构 id 不能为空',
                                             'EC_STRUCTURE_NOT_FOUND')
            return None
        row = self._fetch_one(
            'SELECT id, item_id, usage, alternative_no, revision, status, '
            'valid_from, valid_to, base_qty FROM item_structures WHERE id = ?',
            [structure_id])
        if not row:
            if required:
                raise EngineeringChangeError(
                    f'结构不存在: {structure_id}', 'EC_STRUCTURE_NOT_FOUND',
                    details={'structure_id': structure_id})
            return None
        if usage and _text(row.get('usage')) != usage:
            raise EngineeringChangeError(
                f'结构 {structure_id} 用途为 {row.get("usage")}，期望 {usage}',
                'EC_STRUCTURE_USAGE_INVALID',
                details={'structure_id': structure_id,
                         'actual_usage': row.get('usage'),
                         'expected_usage': usage})
        return row

    def _load_structure_line(self, line_id: Any, structure_id: Any,
                             rule: str, required: bool = True) -> Optional[Dict]:
        if _blank(line_id) or _blank(structure_id):
            if required:
                raise EngineeringChangeError(
                    '结构行 id / 所属结构不能为空', rule,
                    details={'structure_line_id': line_id,
                             'structure_id': structure_id})
            return None
        row = self._fetch_one(
            'SELECT * FROM item_structure_lines WHERE id = ? AND structure_id = ?',
            [line_id, structure_id])
        if not row:
            if required:
                raise EngineeringChangeError(
                    f'结构行 {line_id} 不属于结构 {structure_id}', rule,
                    details={'structure_line_id': line_id,
                             'structure_id': structure_id})
            return None
        return row

    def _load_change(self, change_id: Any) -> Dict:
        row = self._fetch_one(
            'SELECT * FROM %s WHERE id = ?' % HEADER_TABLE, [change_id])
        if not row:
            raise EngineeringChangeError(
                f'工程变更单不存在: {change_id}', 'EC_NOT_FOUND',
                details={'change_id': change_id})
        return row

    def _load_lines(self, change_id: Any) -> List[Dict]:
        return self._fetch_all(
            'SELECT * FROM %s WHERE change_id = ? ORDER BY line_no' % LINE_TABLE,
            [change_id])

    # ==================================================================
    # 审计（change_events；fail-open）
    # ==================================================================
    def _audit(self, change_id: Any, action: str, actor: Optional[str],
               old_status: Optional[str], new_status: Optional[str],
               note: Optional[str] = None) -> None:
        try:
            payload = {
                'actor': actor,
                'action': action,
                'note': note,
                'old_status': old_status,
                'new_status': new_status,
            }
            self._insert('change_events', {
                'object_type': 'engineering_change',
                'object_id': int(change_id),
                'event_type': 'state_change',
                'changed_fields': json.dumps(['status'], ensure_ascii=False),
                'old_values': json.dumps({'status': old_status},
                                         ensure_ascii=False),
                'new_values': json.dumps({'status': new_status},
                                         ensure_ascii=False),
                'payload': json.dumps(payload, ensure_ascii=False),
                'status': 'pending',
                'created_at': _now(),
            })
        except Exception as e:  # 事件底座不可用时审计不阻断业务
            logger.warning('[engineering_change] 写入 change_event 失败: %s', e)

    # ==================================================================
    # EC-1 diff_structures（只读，不落表）
    # ==================================================================
    def diff_structures(self, source_structure_id: Any,
                        target_structure_id: Any,
                        as_of: Optional[Any] = None) -> Dict[str, Any]:
        """对账工程 BOM（source）与生产 BOM（target），返回差异行。

        · 仅 usage=engineering 的 source 与 usage=production 的 target 有意义；
          任一结构不存在 / 用途不符 / status≠active → 领域错误。
        · 行生效窗口用 explode 的 `_covers`（包含端点）。
        · 匹配键 component_item_id + substitute_group_code + operation_seq；
          任一侧同键多行 → ambiguous，该键不产出 add/modify/remove。
        · 差异实时计算，不写任何表。
        """
        as_of_text = _date_text(as_of) or date.today().isoformat()
        source = self._load_structure(source_structure_id, USAGE_ENGINEERING)
        target = self._load_structure(target_structure_id, USAGE_PRODUCTION)
        for label, struct in (('来源工程结构', source), ('目标生产结构', target)):
            if _text(struct.get('status')) != 'active':
                raise EngineeringChangeError(
                    f'{label} {struct.get("id")} 非 active（当前 {struct.get("status")}）',
                    'EC_STRUCTURE_INACTIVE',
                    details={'structure_id': struct.get('id'),
                             'status': struct.get('status')})

        source_lines = [
            row for row in self._fetch_all(
                'SELECT * FROM item_structure_lines WHERE structure_id = ? '
                'ORDER BY line_no', [source['id']])
            if _covers(as_of_text, row.get('valid_from'), row.get('valid_to'))
        ]
        target_lines = [
            row for row in self._fetch_all(
                'SELECT * FROM item_structure_lines WHERE structure_id = ? '
                'ORDER BY line_no', [target['id']])
            if _covers(as_of_text, row.get('valid_from'), row.get('valid_to'))
        ]

        source_by_key: Dict[Tuple[str, str, str], List[Dict]] = {}
        target_by_key: Dict[Tuple[str, str, str], List[Dict]] = {}
        for row in source_lines:
            source_by_key.setdefault(_key_of(row), []).append(row)
        for row in target_lines:
            target_by_key.setdefault(_key_of(row), []).append(row)

        rows: List[Dict[str, Any]] = []
        ambiguous: List[Dict[str, Any]] = []
        for key in sorted(set(source_by_key) | set(target_by_key)):
            src_group = source_by_key.get(key, [])
            tgt_group = target_by_key.get(key, [])
            if len(src_group) > 1 or len(tgt_group) > 1:
                ambiguous.append({
                    'match_key': _match_key(*key),
                    'component_item_id': src_group[0].get('component_item_id')
                    if src_group else tgt_group[0].get('component_item_id'),
                    'source_line_ids': [r.get('id') for r in src_group],
                    'target_line_ids': [r.get('id') for r in tgt_group],
                    'message': '同一匹配键在单侧出现多行，需人工确认',
                })
                continue

            src = src_group[0] if src_group else None
            tgt = tgt_group[0] if tgt_group else None
            if src and not tgt:
                rows.append(self._diff_row('add', key, src, tgt,
                                           source, target))
            elif tgt and not src:
                rows.append(self._diff_row('remove', key, src, tgt,
                                           source, target))
            elif src and tgt and self._has_diff(src, tgt):
                rows.append(self._diff_row('modify', key, src, tgt,
                                           source, target))

        rows.sort(key=lambda r: (r['_sort_line_no'], r['match_key']))
        for row in rows:
            row.pop('_sort_line_no', None)

        summary = {'add': 0, 'modify': 0, 'remove': 0}
        for row in rows:
            summary[row['line_type']] += 1
        return {
            'source_structure_id': source['id'],
            'target_structure_id': target['id'],
            'source_revision': source.get('revision'),
            'target_revision': target.get('revision'),
            'as_of': as_of_text,
            'rows': rows,
            'ambiguous': ambiguous,
            'summary': summary,
        }

    @staticmethod
    def _has_diff(source_line: Dict, target_line: Dict) -> bool:
        for field in DIFF_COMPARE_FIELDS:
            if _normalize(source_line.get(field)) != _normalize(target_line.get(field)):
                return True
        return False

    @staticmethod
    def _diff_row(line_type: str, key: Tuple[str, str, str],
                  source_line: Optional[Dict], target_line: Optional[Dict],
                  source_struct: Dict, target_struct: Dict) -> Dict[str, Any]:
        primary = source_line or target_line or {}
        component = primary.get('component_item_id')
        sort_line_no = (target_line or source_line or {}).get('line_no') or 0
        return {
            'line_type': line_type,
            'match_key': _match_key(*key),
            'component_item_id': component,
            'substitute_group_code': primary.get('substitute_group_code'),
            'operation_seq': primary.get('operation_seq'),
            'target_structure_id': target_struct['id'],
            'source_structure_id': source_struct['id'],
            'source_structure_line_id': source_line.get('id') if source_line else None,
            'structure_line_id': target_line.get('id') if target_line else None,
            'old_qty_per': target_line.get('qty_per') if target_line else None,
            'new_qty_per': source_line.get('qty_per') if source_line else None,
            'old_valid_to': target_line.get('valid_to') if target_line else None,
            'new_valid_to': source_line.get('valid_to') if source_line else None,
            'note': '',
            'old': dict(target_line) if target_line else None,
            'new': dict(source_line) if source_line else None,
            '_sort_line_no': sort_line_no,
        }

    # ==================================================================
    # EC-2 create_change
    # ==================================================================
    def create_change(self, *, change_type: Any, title: Any, reason: Any,
                      effective_date: Any, lines: List[Dict[str, Any]],
                      project_id: Any = None,
                      actor: Optional[str] = None) -> Dict[str, Any]:
        if _text(change_type) not in CHANGE_TYPES:
            raise EngineeringChangeError(
                f'变更类型非法: {change_type}（允许 {"/".join(CHANGE_TYPES)}）',
                'EC_CHANGE_TYPE_INVALID', 'change_type')
        if _blank(title):
            raise EngineeringChangeError('变更标题不能为空', 'EC_TITLE_REQUIRED',
                                         'title')
        if not lines:
            raise EngineeringChangeError('变更单至少需要 1 条明细',
                                         'EC_LINES_REQUIRED', 'lines')

        eff_day = _parse_day(effective_date)
        if eff_day < date.today():
            raise EngineeringChangeError(
                f'生效日 {eff_day.isoformat()} 早于今天', 'EC_EFFECTIVE_DATE_INVALID',
                'effective_date')

        if project_id not in (None, ''):
            if not self._fetch_one('SELECT id FROM projects WHERE id = ?',
                                   [project_id]):
                raise EngineeringChangeError(
                    f'项目不存在: {project_id}', 'EC_PROJECT_NOT_FOUND',
                    'project_id')

        # 结构 / 行缓存，避免重复查询
        struct_cache: Dict[Any, Dict] = {}
        line_cache: Dict[Tuple[Any, Any], Dict] = {}

        def get_struct(sid: Any, usage: str) -> Dict:
            key = (sid, usage)
            if key not in struct_cache:
                struct_cache[key] = self._load_structure(sid, usage)
            return struct_cache[key]

        def get_line(lid: Any, sid: Any, rule: str) -> Dict:
            key = (lid, sid)
            if key not in line_cache:
                line_cache[key] = self._load_structure_line(lid, sid, rule)
            return line_cache[key]

        prepared: List[Dict[str, Any]] = []
        target_ids = set()
        for index, raw in enumerate(lines, start=1):
            line_type = _text(raw.get('line_type')).lower()
            if line_type not in LINE_TYPES:
                raise EngineeringChangeError(
                    f'明细第 {index} 行动作非法: {raw.get("line_type")}',
                    'EC_LINE_INVALID', 'line_type')
            component_item_id = raw.get('component_item_id')
            if _blank(component_item_id):
                raise EngineeringChangeError(
                    f'明细第 {index} 行 component_item_id 必填',
                    'EC_LINE_INVALID', 'component_item_id')

            target = get_struct(raw.get('target_structure_id'), USAGE_PRODUCTION)
            target_ids.add(target['id'])
            source = None
            source_line = None
            target_line = None

            if line_type in ('add', 'modify'):
                source = get_struct(raw.get('source_structure_id'),
                                    USAGE_ENGINEERING)
                if _text(source.get('item_id')) != _text(target.get('item_id')):
                    raise EngineeringChangeError(
                        f'明细第 {index} 行来源工程结构 {source.get("id")} 与目标'
                        f'生产结构 {target.get("id")} 物料不一致',
                        'EC_STRUCTURE_ITEM_MISMATCH',
                        details={'source_item_id': source.get('item_id'),
                                 'target_item_id': target.get('item_id')})
                source_line = get_line(raw.get('source_structure_line_id'),
                                       source['id'], 'EC_SOURCE_LINE_INVALID')
            elif _blank(raw.get('source_structure_id')):
                source = None
            else:
                source = get_struct(raw.get('source_structure_id'),
                                    USAGE_ENGINEERING)
                if raw.get('source_structure_line_id') not in (None, ''):
                    source_line = get_line(raw.get('source_structure_line_id'),
                                           source['id'], 'EC_SOURCE_LINE_INVALID')

            if line_type == 'add':
                if raw.get('structure_line_id') not in (None, ''):
                    raise EngineeringChangeError(
                        f'明细第 {index} 行 add 不得携带 structure_line_id',
                        'EC_LINE_INVALID', 'structure_line_id')
            else:
                target_line = get_line(raw.get('structure_line_id'), target['id'],
                                       'EC_TARGET_LINE_INVALID')

            key_source = source_line or target_line or {}
            match_key = _text(raw.get('match_key')) or _match_key(
                component_item_id, key_source.get('substitute_group_code'),
                key_source.get('operation_seq'))

            prepared.append({
                'line_no': index,
                'line_type': line_type,
                'target_structure_id': target['id'],
                'source_structure_id': source['id'] if source else None,
                'source_structure_line_id': source_line.get('id')
                if source_line else None,
                'structure_line_id': target_line.get('id')
                if target_line else None,
                'component_item_id': component_item_id,
                'match_key': match_key,
                'target_revision': _text(target.get('revision')),
                'source_revision': _text(source.get('revision')) if source else None,
                'old_qty_per': raw.get('old_qty_per', target_line.get('qty_per')
                                       if target_line else None),
                'new_qty_per': raw.get('new_qty_per', source_line.get('qty_per')
                                       if source_line else None),
                'old_valid_to': raw.get('old_valid_to', target_line.get('valid_to')
                                        if target_line else None),
                'new_valid_to': raw.get('new_valid_to', source_line.get('valid_to')
                                        if source_line else None),
                'note': raw.get('note'),
            })

        if len(target_ids) > 1:
            raise EngineeringChangeError(
                'P1 限制：同一变更单所有明细的 target_structure_id 必须相同',
                'EC_TARGET_STRUCTURE_MISMATCH',
                details={'target_structure_ids': sorted(target_ids)})

        now = _now()
        actor = _text(actor) or None
        with self._transaction():
            change_no = self._next_change_no()
            change_id = self._insert(HEADER_TABLE, {
                'change_no': change_no,
                'title': _text(title),
                'change_type': _text(change_type),
                'project_id': project_id if project_id not in (None, '') else None,
                'reason': reason,
                'effective_date': eff_day.isoformat(),
                'status': STATUS_DRAFT,
                'applied_at': None,
                'applied_by': None,
                'created_at': now,
                'updated_at': now,
                'created_by': actor,
                'updated_by': actor,
            })
            for row in prepared:
                row.update({'change_id': change_id, 'created_at': now,
                            'updated_at': now, 'created_by': actor,
                            'updated_by': actor})
                self._insert(LINE_TABLE, row)
            self._audit(change_id, 'create', actor, None, STATUS_DRAFT)
        return self.get_change(change_id)

    def _next_change_no(self) -> str:
        prefix = 'EC-%s-' % datetime.now().strftime('%Y%m')
        row = self._fetch_one(
            'SELECT change_no FROM %s WHERE change_no LIKE ? '
            'ORDER BY change_no DESC LIMIT 1' % HEADER_TABLE,
            [prefix + '%'])
        seq = 1
        if row and row.get('change_no'):
            try:
                seq = int(str(row['change_no']).rsplit('-', 1)[-1]) + 1
            except ValueError:
                seq = 1
        return '%s%04d' % (prefix, seq)

    # ==================================================================
    # 查询
    # ==================================================================
    def get_change(self, change_id: Any) -> Dict[str, Any]:
        head = self._load_change(change_id)
        lines = self._load_lines(change_id)
        target_structure_id = lines[0]['target_structure_id'] if lines else None
        item_id = None
        if target_structure_id:
            struct = self._fetch_one(
                'SELECT item_id FROM item_structures WHERE id = ?',
                [target_structure_id])
            item_id = struct.get('item_id') if struct else None
        result = dict(head)
        result['target_structure_id'] = target_structure_id
        result['item_id'] = item_id
        result['lines'] = lines
        return result

    def list_changes(self, *, status: Optional[str] = None,
                     item_id: Optional[Any] = None,
                     project_id: Optional[Any] = None,
                     page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        page = max(int(page or 1), 1)
        page_size = min(max(int(page_size or 20), 1), 200)
        where: List[str] = []
        params: List[Any] = []
        if not _blank(status):
            where.append('ec.status = ?')
            params.append(_text(status))
        if not _blank(project_id):
            where.append('ec.project_id = ?')
            params.append(project_id)
        if not _blank(item_id):
            where.append(
                'EXISTS (SELECT 1 FROM %s l JOIN item_structures s '
                'ON s.id = l.target_structure_id WHERE l.change_id = ec.id '
                'AND s.item_id = ?)' % LINE_TABLE)
            params.append(item_id)
        where_sql = (' WHERE ' + ' AND '.join(where)) if where else ''

        total_row = self._fetch_one(
            'SELECT COUNT(*) AS total FROM %s ec%s' % (HEADER_TABLE, where_sql),
            params)
        rows = self._fetch_all(
            'SELECT ec.*, '
            '(SELECT l.target_structure_id FROM %s l WHERE l.change_id = ec.id '
            ' ORDER BY l.line_no LIMIT 1) AS target_structure_id, '
            '(SELECT s.item_id FROM item_structures s WHERE s.id = '
            ' (SELECT l.target_structure_id FROM %s l WHERE l.change_id = ec.id '
            '  ORDER BY l.line_no LIMIT 1)) AS item_id, '
            '(SELECT COUNT(*) FROM %s l WHERE l.change_id = ec.id) AS line_count '
            'FROM %s ec%s ORDER BY ec.created_at DESC, ec.id DESC LIMIT ? OFFSET ?'
            % (LINE_TABLE, LINE_TABLE, LINE_TABLE, HEADER_TABLE, where_sql),
            params + [page_size, (page - 1) * page_size])
        self._enrich_list_rows(rows)
        return {'items': rows, 'total': int((total_row or {}).get('total') or 0),
                'page': page, 'page_size': page_size}

    def _enrich_list_rows(self, rows: List[Dict]) -> None:
        """补列表展示所需的物料 / 项目名称（批量查询，避免 N+1）。"""
        item_ids = sorted({row['item_id'] for row in rows
                           if row.get('item_id')})
        project_ids = sorted({row['project_id'] for row in rows
                              if row.get('project_id')})
        items: Dict[Any, Dict] = {}
        projects: Dict[Any, Dict] = {}
        if item_ids:
            mark = ','.join('?' * len(item_ids))
            items = {r['id']: r for r in self._fetch_all(
                'SELECT id, code, name FROM items WHERE id IN (%s)' % mark,
                item_ids)}
        if project_ids:
            mark = ','.join('?' * len(project_ids))
            projects = {r['id']: r for r in self._fetch_all(
                'SELECT id, project_no, name FROM projects WHERE id IN (%s)'
                % mark, project_ids)}
        for row in rows:
            item = items.get(row.get('item_id')) or {}
            project = projects.get(row.get('project_id')) or {}
            row['item_no'] = item.get('code')
            row['item_name'] = item.get('name')
            row['project_no'] = project.get('project_no')
            row['project_name'] = project.get('name')

    # ==================================================================
    # EC-3 状态迁移（服务层强制权限/前置校验；权限由 API 层装饰器保证）
    # ==================================================================
    def submit(self, change_id: Any, actor: Optional[str] = None,
               note: Optional[str] = None) -> Dict[str, Any]:
        change = self._load_change(change_id)
        if _text(change.get('status')) != STATUS_DRAFT:
            raise EngineeringChangeError(
                f'仅草稿可提交评审，当前状态 {change.get("status")}',
                'EC_STATE_INVALID', 'status',
                {'current_status': change.get('status'), 'allowed_from': ['draft']})
        lines = self._load_lines(change_id)
        if not lines:
            raise EngineeringChangeError('变更单至少需要 1 条明细',
                                         'EC_LINES_REQUIRED', 'lines')
        return self._transition(change, STATUS_IN_REVIEW, 'submit', actor, note)

    def approve(self, change_id: Any, actor: Optional[str] = None,
                comment: Optional[str] = None) -> Dict[str, Any]:
        change = self._load_change(change_id)
        if _text(change.get('status')) != STATUS_IN_REVIEW:
            raise EngineeringChangeError(
                f'仅评审中可批准，当前状态 {change.get("status")}',
                'EC_STATE_INVALID', 'status',
                {'current_status': change.get('status'),
                 'allowed_from': ['in_review']})
        lines = self._load_lines(change_id)
        if not lines:
            raise EngineeringChangeError('变更单至少需要 1 条明细',
                                         'EC_LINES_REQUIRED', 'lines')
        self._assert_lines_intact(lines)
        return self._transition(change, STATUS_APPROVED, 'approve', actor, comment)

    def reject(self, change_id: Any, reason: Any,
               actor: Optional[str] = None) -> Dict[str, Any]:
        change = self._load_change(change_id)
        if _text(change.get('status')) != STATUS_IN_REVIEW:
            raise EngineeringChangeError(
                f'仅评审中可驳回，当前状态 {change.get("status")}',
                'EC_STATE_INVALID', 'status',
                {'current_status': change.get('status'),
                 'allowed_from': ['in_review']})
        if _blank(reason):
            raise EngineeringChangeError('驳回必须填写原因',
                                         'EC_REJECT_REASON_REQUIRED', 'reason')
        return self._transition(change, STATUS_REJECTED, 'reject', actor,
                                _text(reason))

    def cancel(self, change_id: Any, actor: Optional[str] = None,
               reason: Optional[str] = None) -> Dict[str, Any]:
        change = self._load_change(change_id)
        current = _text(change.get('status'))
        if current not in (STATUS_DRAFT, STATUS_IN_REVIEW, STATUS_APPROVED):
            raise EngineeringChangeError(
                f'当前状态 {current} 不可取消', 'EC_STATE_INVALID', 'status',
                {'current_status': current,
                 'allowed_from': [STATUS_DRAFT, STATUS_IN_REVIEW, STATUS_APPROVED]})
        return self._transition(change, STATUS_CANCELLED, 'cancel', actor,
                                _text(reason) or None)

    def _transition(self, change: Dict, to_status: str, action: str,
                    actor: Optional[str], note: Optional[str]) -> Dict[str, Any]:
        from_status = _text(change.get('status'))
        now = _now()
        with self._transaction():
            updated = self.ds.execute(
                'UPDATE %s SET status = ?, updated_at = ?, updated_by = ? '
                'WHERE id = ? AND status = ?' % HEADER_TABLE,
                [to_status, now, _text(actor) or None, change['id'], from_status])
            if getattr(updated, 'rowcount', 0) == 0:
                raise EngineeringChangeError(
                    '状态已被并发修改，请刷新后重试', 'EC_STATE_INVALID', 'status',
                    {'expected_status': from_status})
            self._audit(change['id'], action, actor, from_status, to_status, note)
        return self.get_change(change['id'])

    def _assert_lines_intact(self, lines: List[Dict]) -> None:
        """审批 / 应用前置：明细完整 + 结构未被并发改版（spec §6.4-2）。"""
        for line in lines:
            target = self._load_structure(line.get('target_structure_id'),
                                          USAGE_PRODUCTION)
            stored_target_rev = line.get('target_revision')
            if stored_target_rev is not None and \
                    _text(stored_target_rev) != _text(target.get('revision')):
                raise EngineeringChangeError(
                    '目标生产结构在变更单创建后被并发改版',
                    'EC_REVISION_DRIFT', 'target_revision',
                    {'structure_id': target.get('id'),
                     'expected_revision': stored_target_rev,
                     'actual_revision': target.get('revision')})

            if line.get('source_structure_id') not in (None, ''):
                source = self._load_structure(line.get('source_structure_id'),
                                              USAGE_ENGINEERING)
                stored_source_rev = line.get('source_revision')
                if stored_source_rev is not None and \
                        _text(stored_source_rev) != _text(source.get('revision')):
                    raise EngineeringChangeError(
                        '来源工程结构在变更单创建后被并发改版',
                        'EC_REVISION_DRIFT', 'source_revision',
                        {'structure_id': source.get('id'),
                         'expected_revision': stored_source_rev,
                         'actual_revision': source.get('revision')})

            line_type = line.get('line_type')
            if line_type in ('add', 'modify'):
                self._load_structure_line(
                    line.get('source_structure_line_id'),
                    line.get('source_structure_id'), 'EC_SOURCE_LINE_INVALID')
            if line_type in ('modify', 'remove'):
                self._load_structure_line(
                    line.get('structure_line_id'),
                    line.get('target_structure_id'), 'EC_TARGET_LINE_INVALID')

    # ==================================================================
    # EC-4 apply（显式事务；不建版本、不改 revision）
    # ==================================================================
    def apply(self, change_id: Any, actor: Optional[str] = None) -> Dict[str, Any]:
        change = self._load_change(change_id)
        current = _text(change.get('status'))

        # 幂等：已应用直接返回，不重复写结构行 / 审计
        if current == STATUS_APPLIED:
            return self._apply_result(change, already_applied=True)

        if current != STATUS_APPROVED:
            raise EngineeringChangeError(
                f'仅已批准可应用，当前状态 {current}', 'EC_STATE_INVALID', 'status',
                {'current_status': current, 'allowed_from': [STATUS_APPROVED]})

        eff_day = _parse_day(change.get('effective_date'))

        lines = self._load_lines(change_id)
        if not lines:
            raise EngineeringChangeError('变更单至少需要 1 条明细',
                                         'EC_LINES_REQUIRED', 'lines')
        self._assert_lines_intact(lines)
        self._assert_no_competing_approved(change, lines)

        now = _now()
        actor = _text(actor) or None
        applied_lines = 0
        with self._transaction():
            # 先抢占状态（条件更新），防止两个线程同时 apply 同一张单
            claim = self.ds.execute(
                'UPDATE %s SET status = ?, applied_at = ?, applied_by = ?, '
                'updated_at = ?, updated_by = ? WHERE id = ? AND status = ?'
                % HEADER_TABLE,
                [STATUS_APPLIED, now, actor, now, actor, change['id'],
                 STATUS_APPROVED])
            if getattr(claim, 'rowcount', 0) == 0:
                head = self._load_change(change_id)
                if _text(head.get('status')) == STATUS_APPLIED:
                    return self._apply_result(head, already_applied=True)
                raise EngineeringChangeError(
                    '变更单状态已被并发修改，应用中止', 'EC_STATE_INVALID', 'status',
                    {'current_status': head.get('status')})

            next_line_no = self._max_line_no(lines[0]['target_structure_id'])
            for line in lines:
                line_type = line['line_type']
                if line_type in ('add', 'modify'):
                    source_line = self._load_structure_line(
                        line.get('source_structure_line_id'),
                        line.get('source_structure_id'), 'EC_SOURCE_LINE_INVALID')
                if line_type == 'add':
                    next_line_no += 1
                    self._insert_copied_line(
                        source_line, line['target_structure_id'], next_line_no,
                        eff_day, now, actor)
                elif line_type == 'modify':
                    old_line = self._load_structure_line(
                        line.get('structure_line_id'),
                        line.get('target_structure_id'), 'EC_TARGET_LINE_INVALID')
                    self._close_line(old_line['id'], eff_day, now, actor)
                    # (structure_id, line_no) 唯一：新行取新的行号，不复用旧行号
                    next_line_no += 1
                    self._insert_copied_line(
                        source_line, line['target_structure_id'], next_line_no,
                        eff_day, now, actor)
                else:  # remove
                    old_line = self._load_structure_line(
                        line.get('structure_line_id'),
                        line.get('target_structure_id'), 'EC_TARGET_LINE_INVALID')
                    self._close_line(old_line['id'], eff_day, now, actor)
                applied_lines += 1

            self._audit(change['id'], 'apply', actor, STATUS_APPROVED,
                        STATUS_APPLIED)

        result = self._apply_result(change, already_applied=False)
        result['applied_lines'] = applied_lines
        return result

    def _apply_result(self, change: Dict, already_applied: bool) -> Dict[str, Any]:
        head = self._load_change(change['id'])
        return {
            'id': head['id'],
            'change_no': head.get('change_no'),
            'status': head.get('status'),
            'effective_date': head.get('effective_date'),
            'applied_at': head.get('applied_at'),
            'applied_by': head.get('applied_by'),
            'already_applied': already_applied,
            'revision_unchanged': True,
        }

    def _assert_no_competing_approved(self, change: Dict,
                                      lines: List[Dict]) -> None:
        target_ids = {line['target_structure_id'] for line in lines}
        for target_id in target_ids:
            rows = self._fetch_all(
                'SELECT DISTINCT ec.id, ec.change_no FROM %s ec '
                'JOIN %s l ON l.change_id = ec.id '
                'WHERE ec.status = ? AND ec.id <> ? AND l.target_structure_id = ?'
                % (HEADER_TABLE, LINE_TABLE),
                [STATUS_APPROVED, change['id'], target_id])
            if rows:
                raise EngineeringChangeError(
                    '同一目标结构存在另一张已批准未应用的变更单，禁止重复应用',
                    'EC_CONFLICT_APPROVED', 'target_structure_id',
                    {'target_structure_id': target_id,
                     'conflicting_change_ids': [r['id'] for r in rows]})

    def _max_line_no(self, structure_id: Any) -> int:
        row = self._fetch_one(
            'SELECT MAX(line_no) AS max_no FROM item_structure_lines '
            'WHERE structure_id = ?', [structure_id])
        return int((row or {}).get('max_no') or 0)

    def _close_line(self, line_id: Any, eff_day: date, now: str,
                    actor: Optional[str]) -> None:
        self.ds.execute(
            'UPDATE item_structure_lines SET valid_to = ?, updated_at = ?, '
            'updated_by = ? WHERE id = ?',
            [_prev_day(eff_day), now, actor, line_id])

    def _insert_copied_line(self, source_line: Dict, target_structure_id: Any,
                            line_no: int, eff_day: date, now: str,
                            actor: Optional[str]) -> int:
        row = {
            'structure_id': target_structure_id,
            'line_no': line_no,
            'valid_from': eff_day.isoformat(),
            'created_at': now,
            'created_by': actor,
            'updated_at': now,
            'updated_by': actor,
        }
        for field in COPY_LINE_FIELDS:
            row[field] = source_line.get(field)
        return self._insert('item_structure_lines', row)

    # ==================================================================
    # EC-5 where_used（只读影响预览）
    # ==================================================================
    def where_used(self, change_id: Any) -> Dict[str, Any]:
        """只读：受影响父项结构 + 在途工单；本方法只执行 SELECT，不写任何表。"""
        head = self._load_change(change_id)
        lines = self._load_lines(change_id)
        component_ids = sorted({line['component_item_id'] for line in lines
                                if line.get('component_item_id') is not None})
        target_ids = sorted({line['target_structure_id'] for line in lines
                             if line.get('target_structure_id') is not None})
        source_ids = sorted({line['source_structure_id'] for line in lines
                             if line.get('source_structure_id') is not None})
        if not component_ids:
            return {'change_id': head['id'], 'affected_component_item_ids': [],
                    'parent_structures': [], 'work_orders': [],
                    'read_only': True}

        placeholders = ','.join('?' * len(component_ids))
        parent_sql = (
            'SELECT s.id AS structure_id, s.item_id, s.usage, s.revision, '
            's.status, s.valid_from, s.valid_to, l.id AS structure_line_id, '
            'l.line_no, l.component_item_id, l.qty_per '
            'FROM item_structure_lines l JOIN item_structures s '
            'ON s.id = l.structure_id WHERE l.component_item_id IN (%s)'
            % placeholders)
        parent_params: List[Any] = list(component_ids)
        excluded_ids = sorted(set(target_ids) | set(source_ids))
        if excluded_ids:
            parent_sql += ' AND s.id NOT IN (%s)' % ','.join('?' * len(excluded_ids))
            parent_params.extend(excluded_ids)
        parent_structures = self._fetch_all(parent_sql, parent_params)

        work_orders = self._fetch_all(
            'SELECT DISTINCT w.id AS work_order_id, w.work_order_no, w.status, '
            'w.created_at FROM work_orders w '
            'JOIN work_order_components c ON c.work_order_id = w.id '
            'WHERE c.component_item_id IN (%s) AND w.status NOT IN (%s)'
            % (placeholders, ','.join('?' * len(IN_FLIGHT_EXCLUDED_STATUSES))),
            component_ids + list(IN_FLIGHT_EXCLUDED_STATUSES))
        work_order_components = []
        if work_orders:
            wo_ids = [w['work_order_id'] for w in work_orders]
            work_order_components = self._fetch_all(
                'SELECT work_order_id, id AS component_row_id, structure_line_id, '
                'component_item_id, line_no, qty_per, qty_required '
                'FROM work_order_components WHERE work_order_id IN (%s) '
                'AND component_item_id IN (%s)'
                % (','.join('?' * len(wo_ids)), placeholders),
                wo_ids + component_ids)
        for wo in work_orders:
            wo['components'] = [
                c for c in work_order_components
                if c.get('work_order_id') == wo['work_order_id']
            ]

        return {
            'change_id': head['id'],
            'target_structure_ids': target_ids,
            'affected_component_item_ids': component_ids,
            'parent_structures': parent_structures,
            'work_orders': work_orders,
            'read_only': True,
        }
