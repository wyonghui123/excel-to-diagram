# -*- coding: utf-8 -*-
"""作业定义序列服务 —— 路线分支 / 并行 / 替代的图校验与只读展开（P5）。

依据: docs/specs/spec-routing-process-manufacturing-benchmark-2026-11-01.md §12.2–§12.4
      docs/specs/p5-routing-branch-parallel-batch-selection/spec.md §5.1

口径:
  · std 为基线；alternative 必须成对 branch/return；parallel 只需 branch。
  · branch/return 不是外键，服务层校验其存在于同定义的 active std 工序。
  · 写入路径硬失败；`validate_sequence_graph` 为只读巡检，返回全部告警不抛错。
  · G1 存量多 std 与 G12 批量区间未覆盖 active PV 只告警。
  · `expand_sequences` 不做 PV 选择：调用方先解析 PV → definition_id。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TABLE = 'work_definition_sequences'
OPERATION_TABLE = 'work_definition_operations'
PRODUCTION_VERSION_TABLE = 'production_versions'

SEQ_STD = 'std'
SEQ_PARALLEL = 'parallel'
SEQ_ALTERNATIVE = 'alternative'
SEQ_TYPES = (SEQ_STD, SEQ_PARALLEL, SEQ_ALTERNATIVE)

OPERATION_ACTIVE = 'active'


class WorkDefinitionSequenceError(Exception):
    """序列图校验错误（拦截器转为 ValidationFailedError）。"""

    def __init__(self, message: str, field_name: Optional[str] = None,
                 rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _as_int(value: Any) -> Optional[int]:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ''


class WorkDefinitionSequenceService:
    """序列图校验与只读展开。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 写入校验
    # ------------------------------------------------------------------
    def validate_sequence(self, payload: Dict[str, Any],
                          existing: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """校验序列创建 / 更新，返回告警列表；硬错误抛 WorkDefinitionSequenceError。"""
        patch = dict(payload or {})
        old = dict(existing or {})
        merged = dict(old)
        merged.update(patch)
        sequence_id = _as_int(old.get('id'))
        if sequence_id is None:
            sequence_id = _as_int(merged.get('id'))
        row = self._normalize_sequence(merged)
        if sequence_id is not None:
            row['id'] = sequence_id

        definition_id = _as_int(row.get('definition_id'))
        if definition_id is None:
            raise WorkDefinitionSequenceError(
                '序列必须指定作业定义。', field_name='definition_id',
                rule='SEQUENCE_DEFINITION_REQUIRED')

        warnings: List[Dict[str, Any]] = []
        self._validate_row(row, strict=True, warnings=warnings)

        sequences = self._load_sequences(definition_id)
        if sequence_id is not None:
            sequences = [s for s in sequences if _as_int(s.get('id')) != sequence_id]
        sequences.append(row)
        operations = self._load_operations(definition_id)
        self._check_graph(definition_id, sequences, operations, strict=True,
                          warnings=warnings)
        return warnings

    def validate_sequence_graph(self, definition_id: Any) -> List[Dict[str, Any]]:
        """只读巡检：返回全部规则问题，不抛错。"""
        definition_id = _as_int(definition_id)
        if definition_id is None:
            return []
        sequences = self._load_sequences(definition_id)
        operations = self._load_operations(definition_id)
        warnings: List[Dict[str, Any]] = []
        for row in sequences:
            self._validate_row(row, strict=False, warnings=warnings)
        self._check_graph(definition_id, sequences, operations, strict=False,
                          warnings=warnings)
        return warnings

    def validate_operation(self, payload: Dict[str, Any],
                           existing: Optional[Dict[str, Any]] = None) -> None:
        """工序写入校验：G11 边界工序号变更；非 std 序列内工序号不得压边界。"""
        patch = dict(payload or {})
        old = dict(existing or {})
        merged = dict(old)
        merged.update(patch)

        definition_id = _as_int(merged.get('definition_id'))
        seq = _as_int(merged.get('seq'))
        if definition_id is None:
            raise WorkDefinitionSequenceError(
                '工序必须指定作业定义。', field_name='definition_id',
                rule='OPERATION_DEFINITION_REQUIRED')
        if seq is None or seq < 1:
            raise WorkDefinitionSequenceError(
                '工序号必须为正整数。', field_name='seq',
                rule='OPERATION_SEQ_INVALID')

        old_seq = _as_int(old.get('seq'))
        sequences = self._load_sequences(definition_id)
        if old_seq is not None and seq != old_seq:
            referenced = [
                s for s in sequences
                if _as_int(s.get('branch_operation_seq')) == old_seq
                or _as_int(s.get('return_operation_seq')) == old_seq
            ]
            if referenced:
                raise WorkDefinitionSequenceError(
                    f'工序号 {old_seq} 已被序列分支/返回引用，不能直接改号。',
                    field_name='seq', rule='SEQUENCE_BOUNDARY_OPERATION_REFERENCED')

        sequence_id = _as_int(merged.get('sequence_id'))
        if sequence_id is None:
            return
        sequence = next(
            (s for s in sequences if _as_int(s.get('id')) == sequence_id), None)
        if sequence is None:
            raise WorkDefinitionSequenceError(
                '工序所属序列不属于该作业定义。', field_name='sequence_id',
                rule='SEQUENCE_NOT_FOUND')
        seq_type = _text(sequence.get('seq_type')).lower() or SEQ_STD
        if seq_type == SEQ_STD:
            return
        branch = _as_int(sequence.get('branch_operation_seq'))
        ret = _as_int(sequence.get('return_operation_seq'))
        if seq == branch or (ret is not None and seq == ret):
            raise WorkDefinitionSequenceError(
                f'工序号 {seq} 不能占用序列的分支/返回工序号。',
                field_name='seq', rule='SEQUENCE_OPERATION_CONFLICTS_BOUNDARY')

    # ------------------------------------------------------------------
    # 只读展开
    # ------------------------------------------------------------------
    def expand_sequences(self, definition_id: Any,
                         lot_qty: Optional[float] = None) -> Dict[str, List[Dict[str, Any]]]:
        """按分支/并行/替代展开标准路线；返回 operations + decisions。"""
        definition_id = _as_int(definition_id)
        if definition_id is None:
            return {'operations': [], 'decisions': []}
        sequences = self._load_sequences(definition_id)
        operations = self._load_operations(definition_id)

        std_ids = {_as_int(s.get('id')) for s in sequences
                   if _text(s.get('seq_type')).lower() == SEQ_STD}
        std_ops = [
            op for op in operations
            if _text(op.get('status')).lower() == OPERATION_ACTIVE
            and (_as_int(op.get('sequence_id')) is None
                 or _as_int(op.get('sequence_id')) in std_ids)
        ]
        std_ops.sort(key=lambda op: _as_int(op.get('seq')) or 0)

        alt_by_branch: Dict[int, List[Dict[str, Any]]] = {}
        par_by_branch: Dict[int, List[Dict[str, Any]]] = {}
        ops_by_sequence: Dict[int, List[Dict[str, Any]]] = {}
        for sequence in sequences:
            seq_type = _text(sequence.get('seq_type')).lower() or SEQ_STD
            branch = _as_int(sequence.get('branch_operation_seq'))
            if seq_type == SEQ_ALTERNATIVE and branch is not None:
                alt_by_branch.setdefault(branch, []).append(sequence)
            elif seq_type == SEQ_PARALLEL and branch is not None:
                par_by_branch.setdefault(branch, []).append(sequence)
            seq_id = _as_int(sequence.get('id'))
            if seq_id is not None:
                ops_by_sequence[seq_id] = sorted(
                    [op for op in operations
                     if _as_int(op.get('sequence_id')) == seq_id
                     and _text(op.get('status')).lower() == OPERATION_ACTIVE],
                    key=lambda op: _as_int(op.get('seq')) or 0)
        for bucket in alt_by_branch.values():
            bucket.sort(key=lambda s: (_as_int(s.get('priority')) or 1,
                                       _as_int(s.get('id')) or 0))
        for bucket in par_by_branch.values():
            bucket.sort(key=lambda s: (_as_int(s.get('seq_no')) or 0,
                                       _as_int(s.get('id')) or 0))

        expanded: List[Dict[str, Any]] = []
        decisions: List[Dict[str, Any]] = []

        def _emit_ops(sequence: Dict[str, Any], source: str) -> None:
            seq_id = _as_int(sequence.get('id'))
            for op in ops_by_sequence.get(seq_id, []):
                expanded.append({
                    'seq': _as_int(op.get('seq')),
                    'source': source,
                    'sequence_id': seq_id,
                    'operation_seq': _as_int(op.get('seq')),
                })

        index = 0
        while index < len(std_ops):
            op = std_ops[index]
            branch = _as_int(op.get('seq'))
            expanded.append({
                'seq': branch,
                'source': SEQ_STD,
                'sequence_id': _as_int(op.get('sequence_id')),
                'operation_seq': branch,
            })

            chosen = self._pick_alternative(
                alt_by_branch.get(branch, []), lot_qty)
            if chosen is not None:
                ret = _as_int(chosen.get('return_operation_seq'))
                _emit_ops(chosen, SEQ_ALTERNATIVE)
                decisions.append({
                    'rule': 'ROUTE_ALTERNATIVE_SELECTED',
                    'branch': branch,
                    'return': ret,
                    'sequence_id': _as_int(chosen.get('id')),
                    'priority': _as_int(chosen.get('priority')) or 1,
                })
                index += 1
                while (index < len(std_ops)
                       and (_as_int(std_ops[index].get('seq')) or 0) < (ret or 0)):
                    index += 1
                continue
            if alt_by_branch.get(branch):
                decisions.append({
                    'rule': 'ROUTE_FALLBACK_STD',
                    'branch': branch,
                })

            for parallel in par_by_branch.get(branch, []):
                _emit_ops(parallel, SEQ_PARALLEL)
            index += 1

        return {'operations': expanded, 'decisions': decisions}

    # ------------------------------------------------------------------
    # 规则实现
    # ------------------------------------------------------------------
    def _validate_row(self, row: Dict[str, Any], strict: bool,
                      warnings: List[Dict[str, Any]]) -> None:
        seq_type = _text(row.get('seq_type')).lower() or SEQ_STD
        if seq_type not in SEQ_TYPES:
            self._issue(strict, warnings, 'SEQUENCE_TYPE_INVALID',
                        f'未知序列类型：{seq_type}', 'seq_type',
                        _as_int(row.get('id')))
        seq_no = _as_int(row.get('seq_no'))
        if seq_no is None or seq_no < 1:
            self._issue(strict, warnings, 'SEQUENCE_NO_INVALID',
                        '序列号必须为正整数。', 'seq_no', _as_int(row.get('id')))
        priority = _as_int(row.get('priority'))
        if priority is None:
            row['priority'] = 1
            priority = 1
        if priority < 1:
            self._issue(strict, warnings, 'SEQUENCE_PRIORITY_INVALID',
                        '优先级必须 ≥ 1。', 'priority', _as_int(row.get('id')))

        branch = _as_int(row.get('branch_operation_seq'))
        ret = _as_int(row.get('return_operation_seq'))
        lot_min = _as_float(row.get('lot_min'))
        lot_max = _as_float(row.get('lot_max'))
        for name, value in (('branch_operation_seq', branch),
                            ('return_operation_seq', ret)):
            if value is not None and value < 1:
                self._issue(strict, warnings, 'SEQUENCE_BOUNDARY_INVALID',
                            f'{name} 必须为正整数。', name,
                            _as_int(row.get('id')))
        if lot_min is not None and lot_min < 0:
            self._issue(strict, warnings, 'SEQUENCE_LOT_MIN_NEGATIVE',
                        '批量下限不能为负数。', 'lot_min', _as_int(row.get('id')))
        if lot_min is not None and lot_max is not None and lot_max <= lot_min:
            self._issue(strict, warnings, 'SEQUENCE_LOT_RANGE_INVALID',
                        '批量上限必须大于下限。', 'lot_max', _as_int(row.get('id')))

        if seq_type == SEQ_STD:
            if branch is not None or ret is not None:
                self._issue(strict, warnings, 'SEQUENCE_STD_HAS_BRANCH',
                            '标准序列不能设置分支/返回工序。', 'branch_operation_seq',
                            _as_int(row.get('id')))
        elif seq_type == SEQ_PARALLEL:
            if branch is None:
                self._issue(strict, warnings, 'SEQUENCE_PARALLEL_BRANCH_REQUIRED',
                            '并行序列必须指定分支工序。', 'branch_operation_seq',
                            _as_int(row.get('id')))
            if branch is not None and ret is not None and ret <= branch:
                self._issue(strict, warnings, 'SEQUENCE_RETURN_NOT_AFTER_BRANCH',
                            '返回工序必须大于分支工序。', 'return_operation_seq',
                            _as_int(row.get('id')))
        elif seq_type == SEQ_ALTERNATIVE:
            if branch is None or ret is None:
                self._issue(strict, warnings, 'SEQUENCE_ALTERNATIVE_BOUNDARY_REQUIRED',
                            '替代序列必须同时指定分支与返回工序。',
                            'branch_operation_seq', _as_int(row.get('id')))
            elif ret <= branch:
                self._issue(strict, warnings, 'SEQUENCE_BOUNDARY_INVALID',
                            '返回工序必须大于分支工序。', 'return_operation_seq',
                            _as_int(row.get('id')))

    def _check_graph(self, definition_id: int, sequences: List[Dict[str, Any]],
                     operations: List[Dict[str, Any]], strict: bool,
                     warnings: List[Dict[str, Any]]) -> None:
        std_sequences = [s for s in sequences
                         if (_text(s.get('seq_type')).lower() or SEQ_STD) == SEQ_STD]
        if len(std_sequences) > 1:
            self._issue(strict, warnings, 'MULTIPLE_STD_SEQUENCE',
                        '同一定义存在多条标准序列。', 'seq_type', None)
        std_ids = {_as_int(s.get('id')) for s in std_sequences}
        std_ops = [
            op for op in operations
            if _text(op.get('status')).lower() == OPERATION_ACTIVE
            and (_as_int(op.get('sequence_id')) is None
                 or _as_int(op.get('sequence_id')) in std_ids)
        ]
        std_numbers = {_as_int(op.get('seq')) for op in std_ops}

        non_std = [s for s in sequences
                   if (_text(s.get('seq_type')).lower() or SEQ_STD) != SEQ_STD]
        for sequence in non_std:
            seq_id = _as_int(sequence.get('id'))
            branch = _as_int(sequence.get('branch_operation_seq'))
            ret = _as_int(sequence.get('return_operation_seq'))
            if branch is not None and branch not in std_numbers:
                self._issue(strict, warnings, 'SEQUENCE_BRANCH_NOT_IN_STD',
                            f'分支工序 {branch} 不在标准序列的生效工序内。',
                            'branch_operation_seq', seq_id)
            if ret is not None and ret not in std_numbers:
                self._issue(strict, warnings, 'SEQUENCE_RETURN_NOT_IN_STD',
                            f'返回工序 {ret} 不在标准序列的生效工序内。',
                            'return_operation_seq', seq_id)

            # 新建序列尚无 id：工序不可能提前挂到它，跳过 assigned 检查
            assigned = [] if seq_id is None else [
                op for op in operations
                if _as_int(op.get('sequence_id')) == seq_id]
            if not assigned:
                # G10 只在只读巡检告警：UI 先建序列再挂工序，写入时不能因此阻断
                if not strict:
                    self._issue(False, warnings, 'SEQUENCE_NO_OPERATION',
                                '非标准序列必须至少挂一条工序。', 'sequence_id', seq_id)
            seen: set = set()
            for op in assigned:
                seq = _as_int(op.get('seq'))
                if seq in seen:
                    self._issue(strict, warnings, 'SEQUENCE_OPERATION_SEQ_DUPLICATE',
                                f'序列内工序号 {seq} 重复。', 'seq', seq_id)
                seen.add(seq)
                if seq == branch or (ret is not None and seq == ret):
                    self._issue(strict, warnings,
                                'SEQUENCE_OPERATION_CONFLICTS_BOUNDARY',
                                f'工序号 {seq} 不能占用本序列的分支/返回工序号。',
                                'seq', seq_id)

        # G6：同 branch 的替代序列 priority 不得重复
        by_branch: Dict[int, Dict[int, Dict[str, Any]]] = {}
        for sequence in sequences:
            if (_text(sequence.get('seq_type')).lower() != SEQ_ALTERNATIVE):
                continue
            branch = _as_int(sequence.get('branch_operation_seq'))
            if branch is None:
                continue
            priority = _as_int(sequence.get('priority')) or 1
            bucket = by_branch.setdefault(branch, {})
            if priority in bucket:
                self._issue(strict, warnings,
                            'SEQUENCE_BRANCH_PRIORITY_DUPLICATE',
                            f'分支 {branch} 下替代序列优先级 {priority} 重复。',
                            'priority', _as_int(sequence.get('id')))
            bucket[priority] = sequence

        # G8：branch → return 连边成环
        edges: Dict[int, set] = {}
        for sequence in non_std:
            branch = _as_int(sequence.get('branch_operation_seq'))
            ret = _as_int(sequence.get('return_operation_seq'))
            if branch is not None and ret is not None:
                edges.setdefault(branch, set()).add(ret)

        def _cycle(node: int, path: set) -> bool:
            if node in path:
                return True
            for nxt in edges.get(node, ()):
                if _cycle(nxt, path | {node}):
                    return True
            return False

        if any(_cycle(start, set()) for start in list(edges.keys())):
            self._issue(strict, warnings, 'SEQUENCE_GRAPH_CYCLE',
                        '序列分支/返回连接成环。', 'branch_operation_seq', None)

        # G9：任何 branch/return 工序号只能属于 std
        boundaries = set()
        for sequence in non_std:
            branch = _as_int(sequence.get('branch_operation_seq'))
            ret = _as_int(sequence.get('return_operation_seq'))
            if branch is not None:
                boundaries.add(branch)
            if ret is not None:
                boundaries.add(ret)
        for op in operations:
            seq = _as_int(op.get('seq'))
            seq_id = _as_int(op.get('sequence_id'))
            if (seq in boundaries and seq_id is not None
                    and seq_id not in std_ids):
                self._issue(strict, warnings, 'SEQUENCE_BOUNDARY_OPERATION_NOT_STD',
                            f'边界工序 {seq} 被挂到非标准序列。', 'sequence_id', seq_id)

        # G12：批量区间必须覆盖至少一个 active PV 区间（仅告警）
        self._check_lot_coverage(definition_id, sequences, warnings)

    def _check_lot_coverage(self, definition_id: int,
                            sequences: List[Dict[str, Any]],
                            warnings: List[Dict[str, Any]]) -> None:
        pvs = [pv for pv in self._load_production_versions(definition_id)
               if _text(pv.get('status')).lower() == OPERATION_ACTIVE]
        if not pvs:
            return
        for sequence in sequences:
            lot_min = _as_float(sequence.get('lot_min'))
            lot_max = _as_float(sequence.get('lot_max'))
            if lot_min is None and lot_max is None:
                continue
            covered = any(
                self._interval_intersects(
                    lot_min, lot_max,
                    _as_float(pv.get('lot_min')), _as_float(pv.get('lot_max')))
                for pv in pvs)
            if not covered:
                warnings.append({
                    'rule': 'SEQUENCE_LOT_NOT_COVERED',
                    'message': (
                        f'序列批量区间 [{lot_min if lot_min is not None else "-∞"}, '
                        f'{lot_max if lot_max is not None else "+∞"}] '
                        '与所有生效生产版本区间不相交。'),
                    'field_name': 'lot_min',
                    'sequence_id': _as_int(sequence.get('id')),
                })

    @staticmethod
    def _interval_intersects(a_min: Optional[float], a_max: Optional[float],
                             b_min: Optional[float], b_max: Optional[float]) -> bool:
        lower = max(
            a_min if a_min is not None else float('-inf'),
            b_min if b_min is not None else float('-inf'))
        upper = min(
            a_max if a_max is not None else float('inf'),
            b_max if b_max is not None else float('inf'))
        return lower <= upper

    def _pick_alternative(self, candidates: List[Dict[str, Any]],
                          lot_qty: Optional[float]) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None
        if lot_qty is None:
            return candidates[0]
        try:
            qty = float(lot_qty)
        except (TypeError, ValueError):
            return candidates[0]
        for sequence in candidates:
            lot_min = _as_float(sequence.get('lot_min'))
            lot_max = _as_float(sequence.get('lot_max'))
            if lot_min is not None and qty < lot_min:
                continue
            if lot_max is not None and qty > lot_max:
                continue
            return sequence
        return None

    def _issue(self, strict: bool, warnings: List[Dict[str, Any]],
               rule: str, message: str, field_name: Optional[str],
               sequence_id: Optional[int]) -> None:
        if strict:
            raise WorkDefinitionSequenceError(
                message, field_name=field_name, rule=rule)
        item = {
            'rule': rule,
            'message': message,
            'field_name': field_name,
        }
        if sequence_id is not None:
            item['sequence_id'] = sequence_id
        warnings.append(item)

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_sequence(row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(row)
        normalized['seq_no'] = _as_int(row.get('seq_no'))
        normalized['branch_operation_seq'] = _as_int(
            row.get('branch_operation_seq'))
        normalized['return_operation_seq'] = _as_int(
            row.get('return_operation_seq'))
        normalized['lot_min'] = _as_float(row.get('lot_min'))
        normalized['lot_max'] = _as_float(row.get('lot_max'))
        priority = _as_int(row.get('priority'))
        normalized['priority'] = priority if priority is not None else 1
        normalized['seq_type'] = _text(row.get('seq_type')).lower() or SEQ_STD
        return normalized

    def _load_sequences(self, definition_id: int) -> List[Dict[str, Any]]:
        rows = self._query(
            f'SELECT * FROM {TABLE} WHERE definition_id = ? ORDER BY seq_no, id',
            [definition_id])
        return [self._normalize_sequence(row) for row in rows]

    def _load_operations(self, definition_id: int) -> List[Dict[str, Any]]:
        return self._query(
            f'SELECT * FROM {OPERATION_TABLE} WHERE definition_id = ? '
            'ORDER BY seq, id', [definition_id])

    def _load_production_versions(self, definition_id: int) -> List[Dict[str, Any]]:
        return self._query(
            f'SELECT * FROM {PRODUCTION_VERSION_TABLE} '
            'WHERE work_definition_id = ?', [definition_id])

    def _query(self, sql: str, params) -> List[Dict[str, Any]]:
        if self.ds is None:
            return []
        return self.ds.query(sql, list(params)) or []
