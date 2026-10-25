# -*- coding: utf-8 -*-
"""供应来源规则求值 / 校验服务（1:N 候选集合求解）。

为什么用服务而非 MetaRule 引擎
--------------------------------
规则引擎的 `default_by_priority` 只能从一组行里取**标量**默认值，
表达不了「先按作用域从 N 条分配（assignment）里挑一条，再从该规则
的 N 个来源行里按资格过滤、再排序取一条」的集合求解语义 —— 中间
结果天然是候选集而非单值，且每条被淘汰的来源行都需要把原因回传给
前端解释。故按能力独立成服务，schema / 迁移 / API / 拦截器由其他
任务负责。

五步口径来源
------------
docs/superpowers/specs/2026-10-24-sourcing-rule/spec.md

  ① 选规则          —— 作用域 + 有效期 + 用途匹配，specificity_rank → seq → id
  ② 解析供应方式    —— 物料级策略覆盖物料组级策略
  ③ 资格过滤        —— 类型引用 / 组织职能 / vendor 关系 / 跨法人 / 供应方式
  ④ 排序取源        —— fixed → rank → seq → id
  ⑤ 返回快照        —— 命中链 + explain，供前端逐步骤解释

所有查询均参数化；有效期统一按 `date` 口径比较；状态过滤一律要求
`active`（orgs 用 COALESCE(status,'active') 兜底空值）。
"""

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: 供应规则的两种用途；`all` 表示两种用途通用
USAGE_FULFILLMENT = 'fulfillment'
USAGE_PURCHASING = 'purchasing'
USAGES = frozenset({USAGE_FULFILLMENT, USAGE_PURCHASING})

#: 来源行类型
SOURCE_INTERNAL_ORG = 'internal_org'
SOURCE_PRODUCTION = 'production'
SOURCE_INTERNAL_LOCATION = 'internal_location'
SOURCE_SUPPLIER = 'supplier'

#: 供应方式策略
MODE_MAKE = 'make'
MODE_BUY = 'buy'
MODE_TRANSFER = 'transfer'

# 错误码（值统一以 SOURCING_ 开头，便于前端按前缀分流）
SOURCING_NO_ASSIGNMENT = 'SOURCING_NO_ASSIGNMENT'
SOURCING_ALL_LINES_INELIGIBLE = 'SOURCING_ALL_LINES_INELIGIBLE'
SOURCING_ASSIGNMENT_CONFLICT = 'SOURCING_ASSIGNMENT_CONFLICT'
SOURCING_CROSS_LEGAL_ENTITY = 'SOURCING_CROSS_LEGAL_ENTITY'
SOURCING_MODE_CONFLICT = 'SOURCING_MODE_CONFLICT'
SOURCING_SOURCE_REF_MISMATCH = 'SOURCING_SOURCE_REF_MISMATCH'
SOURCING_ALLOCATION_NOT_100 = 'SOURCING_ALLOCATION_NOT_100'
SOURCING_INVALID_PARAM = 'SOURCING_INVALID_PARAM'

# 短别名：与 spec 中的错误码名一一对应
NO_ASSIGNMENT = SOURCING_NO_ASSIGNMENT
ALL_LINES_INELIGIBLE = SOURCING_ALL_LINES_INELIGIBLE
ASSIGNMENT_CONFLICT = SOURCING_ASSIGNMENT_CONFLICT
CROSS_LEGAL_ENTITY = SOURCING_CROSS_LEGAL_ENTITY
MODE_CONFLICT = SOURCING_MODE_CONFLICT
SOURCE_REF_MISMATCH = SOURCING_SOURCE_REF_MISMATCH
ALLOCATION_NOT_100 = SOURCING_ALLOCATION_NOT_100
INVALID_PARAM = SOURCING_INVALID_PARAM

#: 分配未配置 specificity_rank 时参与排序的兜底值（防 NULL 排最前）
_RANK_FALLBACK = 999
#: 组织上溯找法人的最大层数（防 parent_id 成环时死循环）
_MAX_ORG_DEPTH = 50
#: 分摊比例合计的允许误差
_PCT_TOLERANCE = Decimal('0.01')


class SourcingError(ValueError):
    """供应来源求值 / 校验失败。`code` 供前端做错误分流。"""

    def __init__(self, code: str, message: str, hint: str | None = None,
                 status_code: int = 422, extra: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status_code = status_code
        self.extra = extra or {}

    def to_dict(self) -> dict:
        """输出给 API 的结构：固定三键 + extra 合并（extra 不覆盖三键）。"""
        data = {
            'code': self.code,
            'message': self.message,
            'hint': self.hint,
        }
        for key, value in self.extra.items():
            data.setdefault(key, value)
        return data


# ---------------------------------------------------------------------------
# 模块私有辅助：日期 / 数值 / 空值口径
# ---------------------------------------------------------------------------

def _is_blank(value: Any) -> bool:
    """空值口径：None 与纯空白字符串都视为「未设置」。"""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _parse_date(value: Any) -> Optional[date]:
    """把库内 DATETIME 文本 / date / datetime 解析成 date，失败返回 None。

    库内可能存 `2026-10-24` 或 `2026-10-24 00:00:00`，故统一只取
    前 10 位的 `YYYY-MM-DD` 部分。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _covers(start: Any, end: Any, day: date) -> bool:
    """有效期判定：start 空 = 不限起，end 空 = 不限止。

    任一端存在但无法解析 → 视为「不覆盖」并告警（脏数据不应被当成
    无限有效期，否则会把已失效的规则错误地当成可用）。
    """
    if not _is_blank(start):
        start_date = _parse_date(start)
        if start_date is None:
            logger.warning('[sourcing] 有效期开始无法解析: %r', start)
            return False
        if day < start_date:
            return False
    if not _is_blank(end):
        end_date = _parse_date(end)
        if end_date is None:
            logger.warning('[sourcing] 有效期结束无法解析: %r', end)
            return False
        if day > end_date:
            return False
    return True


def _truthy(value: Any) -> bool:
    """SQLite 的布尔列读回来可能是 0/1、'0'/'1' 或 None。"""
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value)


def _sort_num(value: Any, fallback: float) -> float:
    """排序用数值：NULL / 非数字一律落到 fallback（排在最后）。"""
    if _is_blank(value):
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _same_id(left: Any, right: Any) -> bool:
    """id 比较：DB 整型与入参可能类型不同，统一按字符串比。"""
    return str(left) == str(right)


def _to_decimal(value: Any) -> Decimal:
    """数值转 Decimal；无法解析时返回 0（校验不因此中断）。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        logger.warning('[sourcing] 分摊比例无法解析，按 0 计: %r', value)
        return Decimal('0')


def _is_active(value: Any) -> bool:
    """状态判定：空值按 active 兜底（orgs.status 存量数据可能为空）。"""
    if _is_blank(value):
        return True
    return str(value).strip().lower() == 'active'


def _require_int(value: Any, label: str) -> int:
    """必填整型参数；bool 是 int 子类，需显式排除。"""
    if value is None or _is_blank(value):
        raise SourcingError(
            SOURCING_INVALID_PARAM, f'{label} 必填', status_code=400,
        )
    if isinstance(value, bool) or not isinstance(value, int):
        raise SourcingError(
            SOURCING_INVALID_PARAM, f'{label} 必须是整数: {value!r}',
            status_code=400,
        )
    return value


def _optional_int(value: Any, label: str) -> Optional[int]:
    """选填整型参数；未给则返回 None。"""
    if value is None or _is_blank(value):
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SourcingError(
            SOURCING_INVALID_PARAM, f'{label} 必须是整数: {value!r}',
            status_code=400,
        )
    return value


def _parse_input_date(value: Any) -> date:
    """入参日期：未给 → 今天；给了但解析不了 → 400。"""
    if value is None:
        return date.today()
    parsed = _parse_date(value)
    if parsed is None:
        raise SourcingError(
            SOURCING_INVALID_PARAM, f'date 无法解析: {value!r}',
            hint='日期格式应为 YYYY-MM-DD', status_code=400,
        )
    return parsed


class SourcingResolver:
    """按五步口径求解「某物料在某目的组织下应由谁供应」。

    覆写 `_fetch_*` 可注入测试数据；`data_source` 未注入时懒取平台库。
    """

    ASSIGNMENT_SQL = """SELECT a.id, a.rule_id, a.scope_type, a.scope_ref_id, a.dest_org_id, a.dest_location_id,
       a.specificity_rank, a.seq AS assign_seq, a.effectivity_start, a.effectivity_end,
       r.code AS rule_code, r.rule_usage, r.status AS rule_status,
       r.effectivity_start AS rule_start, r.effectivity_end AS rule_end
FROM sourcing_rule_assignments a
JOIN sourcing_rules r ON r.id = a.rule_id
WHERE a.status = 'active' AND r.status = 'active'"""

    def __init__(self, data_source=None):
        self._ds = data_source
        self._org_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._org_func_cache: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        self._legal_entity_cache: Dict[str, Optional[Any]] = {}

    @property
    def ds(self):
        """懒取默认数据源（避免 import 期连库）。"""
        if self._ds is None:
            from meta.core.db_path import get_meta_db_path
            from meta.core.datasource import get_data_source
            self._ds = get_data_source('sqlite', database=get_meta_db_path())
        return self._ds

    # ------------------------------------------------------------------
    # 对外入口：求值
    # ------------------------------------------------------------------

    def resolve(self, spec: dict) -> dict:
        """求解供应来源。

        spec:
            item_id          必填 int
            dest_org_id      必填 int
            usage            必填，fulfillment / purchasing
            date             选填 YYYY-MM-DD，默认今天
            dest_location_id 选填 int

        Returns:
            命中快照（见模块 docstring）。

        Raises:
            SourcingError: 参数非法(400) / 无分配 / 全部来源不合格 / 供应方式冲突
        """
        if not isinstance(spec, dict):
            raise SourcingError(
                SOURCING_INVALID_PARAM, 'spec 必须是对象', status_code=400,
            )

        item_id = _require_int(spec.get('item_id'), 'item_id')
        dest_org_id = _require_int(spec.get('dest_org_id'), 'dest_org_id')
        usage = spec.get('usage')
        if not isinstance(usage, str) or usage not in USAGES:
            raise SourcingError(
                SOURCING_INVALID_PARAM,
                f'usage 非法: {usage!r}；可选 fulfillment / purchasing',
                status_code=400,
            )
        eval_date = _parse_input_date(spec.get('date'))
        dest_location_id = _optional_int(
            spec.get('dest_location_id'), 'dest_location_id'
        )

        self._reset_caches()

        item = self._first(
            'SELECT id, item_group_id FROM items WHERE id = ?', [item_id]
        )
        if item is None:
            raise SourcingError(
                SOURCING_INVALID_PARAM, f'物料 #{item_id} 不存在',
                hint='物料不存在', status_code=400,
            )
        item_group_id = item.get('item_group_id')

        # ② 先解析供应方式：③ 的候选约束要用它；无分配时也要把它带回错误里
        mode = self._resolve_mode(item_id, item_group_id, dest_org_id)

        # ① 选规则
        matched = self._select_assignments(
            item_id, item_group_id, dest_org_id, dest_location_id,
            usage, eval_date,
        )
        if not matched:
            hint = (f'已解析供应方式为 {mode}，但未配置具体来源规则'
                    if mode else '未解析到供应方式，也未配置来源规则')
            raise SourcingError(
                SOURCING_NO_ASSIGNMENT, '没有命中的供应来源规则',
                hint=hint, extra={'supply_mode': mode},
            )

        assignment = matched[0]
        rule_id = assignment.get('rule_id')

        # ③ 资格过滤
        lines = self._rows(
            'SELECT * FROM sourcing_rule_lines WHERE rule_id = ? ORDER BY id',
            [rule_id],
        )
        kept, dropped = [], []
        for line in lines:
            reason = self._line_reason(line, mode, eval_date, dest_org_id)
            if reason is None:
                kept.append(line)
            else:
                dropped.append({'line_id': line.get('id'), 'reason': reason})
        kept_ids = [line.get('id') for line in kept]

        explain = [
            {
                'step': 'assignment',
                'hit': self._assignment_view(assignment),
                'candidates': [
                    self._assignment_view(c) for c in matched[:10]
                ],
            },
            {
                'step': 'line_filter',
                'kept': kept_ids,
                'dropped': dropped,
            },
        ]

        if not kept:
            # 全部因供应方式不匹配 → 单独错误码，便于前端提示「改供应方式」
            if dropped and all(
                    d['reason'] == 'mode_mismatch' for d in dropped):
                raise SourcingError(
                    SOURCING_MODE_CONFLICT,
                    f'供应方式 {mode} 与规则全部来源类型都不匹配'
                    '（make→生产 / buy→供应商 / transfer→内部调拨）',
                    hint='请调整供应方式策略或补充对应类型的来源行',
                    extra={'supply_mode': mode, 'explain': explain},
                )
            # 明确禁止回退到第二候选：更粗的规则不代表同一业务事实
            raise SourcingError(
                SOURCING_ALL_LINES_INELIGIBLE,
                f'规则 {assignment.get("rule_code") or rule_id} 没有任何可用来源',
                hint='命中的规则没有任何可用来源；不会回退到更粗规则',
                extra={'explain': explain},
            )

        # ④ 排序取源
        kept.sort(key=lambda line: (
            -int(_truthy(line.get('fixed'))),
            _sort_num(line.get('rank'), _RANK_FALLBACK),
            _sort_num(line.get('seq'), _RANK_FALLBACK),
            _sort_num(line.get('id'), 999999),
        ))
        pick = kept[0]

        # ⑤ 返回快照
        explain.append({
            'step': 'line_pick',
            'line_id': pick.get('id'),
            'fixed': _truthy(pick.get('fixed')),
            'rank': pick.get('rank'),
        })

        return {
            'resolved': True,
            'rule_id': rule_id,
            'rule_code': assignment.get('rule_code'),
            'assignment_id': assignment.get('id'),
            'specificity_rank': assignment.get('specificity_rank'),
            'line_id': pick.get('id'),
            'rank': pick.get('rank'),
            'source_type': pick.get('source_type'),
            'source_org_id': pick.get('source_org_id'),
            'source_location_id': pick.get('source_location_id'),
            'supplier_party_id': pick.get('supplier_party_id'),
            'supply_mode': mode,
            'usage': usage,
            'evaluated_at': datetime.now().isoformat(timespec='seconds'),
            'explain': explain,
        }

    # ------------------------------------------------------------------
    # 对外入口：规则校验
    # ------------------------------------------------------------------

    def validate_rule(self, rule_id: int) -> Optional[dict]:
        """校验一条供应规则的配置完整性。

        规则不存在 → None（由 API 转 404）。校验项全部收集、互不中断：

        1. 按 rank 分组的分摊比例合计必须为 100（blocked 行同样占位）
        2. 来源类型与引用字段一致
        3. internal_org→inventory / production→manufacturing / supplier→vendor
        4. 作用域合法（global 无引用；item/item_group 引用存在）
        5. active 分配的作用域键唯一

        空规则（line_count = 0）不算错误 —— 是否允许空白由激活守卫负责。
        """
        self._reset_caches()
        rule = self._first('SELECT * FROM sourcing_rules WHERE id = ?', [rule_id])
        if rule is None:
            return None

        lines = self._rows(
            'SELECT * FROM sourcing_rule_lines WHERE rule_id = ? ORDER BY id',
            [rule_id],
        )
        assignments = self._rows(
            'SELECT * FROM sourcing_rule_assignments WHERE rule_id = ? ORDER BY id',
            [rule_id],
        )
        active_assignments = [
            a for a in assignments
            if (a.get('status') or '').strip().lower() == 'active'
        ]

        errors: List[Dict[str, Any]] = []
        conflicts: List[Dict[str, Any]] = []

        # 1) rank 合计
        rank_totals: Dict[Any, Decimal] = {}
        for line in lines:
            rank_totals.setdefault(line.get('rank'), Decimal('0'))
            rank_totals[line.get('rank')] += _to_decimal(line.get('allocation_pct'))

        ranks = []
        for rank_key in sorted(rank_totals, key=lambda r: _sort_num(r, _RANK_FALLBACK)):
            total = rank_totals[rank_key].quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            rank_ok = abs(total - Decimal('100')) <= _PCT_TOLERANCE
            ranks.append({
                'rank': rank_key,
                'total': float(total),
                'ok': rank_ok,
            })
            if not rank_ok:
                errors.append({
                    'code': SOURCING_ALLOCATION_NOT_100,
                    'message': f'rank {rank_key} 的分摊比例合计为 {total}，应等于 100',
                    'hint': '同一 rank 下所有来源行（含 blocked）的 allocation_pct 必须合计 100',
                })

        # 2) 类型—引用一致（与 ③ 的 missing_source_ref 同口径）
        for line in lines:
            source_type = (line.get('source_type') or '').strip()
            ref_field = {
                SOURCE_INTERNAL_ORG: 'source_org_id',
                SOURCE_PRODUCTION: 'source_org_id',
                SOURCE_INTERNAL_LOCATION: 'source_location_id',
                SOURCE_SUPPLIER: 'supplier_party_id',
            }.get(source_type)
            if ref_field is None or _is_blank(line.get(ref_field)):
                errors.append({
                    'code': SOURCING_SOURCE_REF_MISMATCH,
                    'message': f'行 #{line.get("id")} 的来源类型 {source_type!r} '
                               f'与引用字段不一致或引用为空',
                    'hint': 'internal_org/production 填 source_org_id；'
                            'internal_location 填 source_location_id；'
                            'supplier 填 supplier_party_id',
                })

        # 3) 职能 / vendor 关系（配置校验不看有效期，仅看是否存在）
        for line in lines:
            source_type = (line.get('source_type') or '').strip()
            if source_type in (SOURCE_INTERNAL_ORG, SOURCE_PRODUCTION):
                org_id = line.get('source_org_id')
                if _is_blank(org_id):
                    continue  # 已在 2) 报过
                ftype = ('inventory' if source_type == SOURCE_INTERNAL_ORG
                         else 'manufacturing')
                if not self._org_has_function(org_id, ftype, None):
                    errors.append({
                        'code': SOURCING_SOURCE_REF_MISMATCH,
                        'message': f'行 #{line.get("id")} 的组织 #{org_id} '
                                   f'缺少 {ftype} 职能',
                        'hint': f'请先为该组织维护 {ftype} 职能',
                    })
            elif source_type == SOURCE_SUPPLIER:
                party_id = line.get('supplier_party_id')
                if _is_blank(party_id):
                    continue
                if not self._vendor_relation_exists(party_id):
                    errors.append({
                        'code': SOURCING_SOURCE_REF_MISMATCH,
                        'message': f'行 #{line.get("id")} 的供应商 #{party_id} '
                                   f'缺少有效的 vendor 关系',
                        'hint': '请先维护该往来方的 vendor 关系',
                    })

        # 4) 作用域合法
        for assignment in active_assignments:
            scope_type = (assignment.get('scope_type') or '').strip()
            ref_id = assignment.get('scope_ref_id')
            if scope_type == 'global':
                if not _is_blank(ref_id):
                    errors.append({
                        'code': SOURCING_SOURCE_REF_MISMATCH,
                        'message': f'分配 #{assignment.get("id")} 的 global 作用域'
                                   f'不应带 scope_ref_id（当前 {ref_id!r}）',
                        'hint': 'global 作用域的 scope_ref_id 必须为空',
                    })
            elif scope_type in ('item', 'item_group'):
                if _is_blank(ref_id):
                    errors.append({
                        'code': SOURCING_SOURCE_REF_MISMATCH,
                        'message': f'分配 #{assignment.get("id")} 的 {scope_type} '
                                   f'作用域缺少 scope_ref_id',
                        'hint': 'item / item_group 作用域必须指定引用对象',
                    })
                    continue
                table = 'items' if scope_type == 'item' else 'item_groups'
                if self._first(
                        f'SELECT id FROM {table} WHERE id = ?', [ref_id]) is None:
                    errors.append({
                        'code': SOURCING_SOURCE_REF_MISMATCH,
                        'message': f'分配 #{assignment.get("id")} 引用的 {scope_type} '
                                   f'#{ref_id} 不存在',
                        'hint': f'scope_ref_id 必须指向已存在的 {table} 记录',
                    })

        # 5) active 分配唯一键冲突
        buckets: Dict[Tuple[Any, Any, Any, Any], List[Dict[str, Any]]] = {}
        for assignment in active_assignments:
            key = (
                (assignment.get('scope_type') or '').strip(),
                assignment.get('scope_ref_id') if assignment.get('scope_ref_id') is not None else 0,
                assignment.get('dest_org_id') if assignment.get('dest_org_id') is not None else 0,
                assignment.get('dest_location_id') if assignment.get('dest_location_id') is not None else 0,
            )
            buckets.setdefault(key, []).append(assignment)
        for key, group in buckets.items():
            if len(group) > 1:
                conflicts.append({
                    'scope_type': key[0],
                    'scope_ref_id': key[1],
                    'dest_org_id': key[2],
                    'dest_location_id': key[3],
                })
                ids = ', '.join(f'#{a.get("id")}' for a in group)
                errors.append({
                    'code': SOURCING_ASSIGNMENT_CONFLICT,
                    'message': f'作用域 (scope_type={key[0]}, scope_ref_id={key[1]}, '
                               f'dest_org_id={key[2]}, dest_location_id={key[3]}) '
                               f'存在 {len(group)} 条 active 分配：{ids}',
                    'hint': '同一作用域键只能有一条 active 分配，请停用多余分配',
                })

        return {
            'ok': len(errors) == 0,
            'rule_id': rule_id,
            'line_count': len(lines),
            'assignment_count': len(assignments),
            'ranks': ranks,
            'conflicts': conflicts,
            'errors': errors,
        }

    # ------------------------------------------------------------------
    # ① 选规则
    # ------------------------------------------------------------------

    def _select_assignments(self, item_id: int, item_group_id: Any,
                            dest_org_id: int, dest_location_id: Optional[int],
                            usage: str, eval_date: date) -> List[Dict[str, Any]]:
        """取候选分配并按 (specificity_rank, seq, id) 排序。

        SQL 只做 active 过滤（便于 explain 时能指出「SQL 没筛业务条件」），
        业务条件在 Python 侧过滤，逐条可解释。
        """
        candidates = self._rows(self.ASSIGNMENT_SQL, [])
        matched = []
        for cand in candidates:
            # 分配与规则的有效期都必须覆盖求值日期
            if not _covers(cand.get('effectivity_start'),
                           cand.get('effectivity_end'), eval_date):
                continue
            if not _covers(cand.get('rule_start'),
                           cand.get('rule_end'), eval_date):
                continue
            if (cand.get('rule_usage') or '').strip() not in (usage, 'all'):
                continue

            scope_type = (cand.get('scope_type') or '').strip()
            ref_id = cand.get('scope_ref_id')
            if scope_type == 'item':
                if not _same_id(ref_id, item_id):
                    continue
            elif scope_type == 'item_group':
                if _is_blank(item_group_id) or not _same_id(ref_id, item_group_id):
                    continue
            elif scope_type != 'global':
                continue

            if not _is_blank(cand.get('dest_org_id')) \
                    and not _same_id(cand.get('dest_org_id'), dest_org_id):
                continue

            # 入参没给目的位置时，限定位置的分配一律不匹配
            if not _is_blank(cand.get('dest_location_id')):
                if _is_blank(dest_location_id) or not _same_id(
                        cand.get('dest_location_id'), dest_location_id):
                    continue

            matched.append(cand)

        matched.sort(key=lambda cand: (
            _sort_num(cand.get('specificity_rank'), _RANK_FALLBACK),
            _sort_num(cand.get('assign_seq'), _RANK_FALLBACK),
            _sort_num(cand.get('id'), 999999),
        ))
        return matched

    @staticmethod
    def _assignment_view(cand: Dict[str, Any]) -> Dict[str, Any]:
        """候选 / 命中的可读视图（explain 用）。"""
        return {
            'assignment_id': cand.get('id'),
            'rule_id': cand.get('rule_id'),
            'rule_code': cand.get('rule_code'),
            'scope_type': cand.get('scope_type'),
            'scope_ref_id': cand.get('scope_ref_id'),
            'dest_org_id': cand.get('dest_org_id'),
            'dest_location_id': cand.get('dest_location_id'),
            'specificity_rank': cand.get('specificity_rank'),
            'assign_seq': cand.get('assign_seq'),
        }

    # ------------------------------------------------------------------
    # ② 供应方式策略
    # ------------------------------------------------------------------

    def _resolve_mode(self, item_id: int, item_group_id: Any,
                      dest_org_id: int) -> Optional[str]:
        """解析供应方式：物料级策略覆盖物料组级策略。"""
        rows = self._rows(
            'SELECT id, item_id, item_group_id, org_id, mode, status '
            "FROM sourcing_mode_policies WHERE status = 'active' AND org_id = ?",
            [dest_org_id],
        )
        item_mode = None
        group_mode = None
        for row in rows:
            mode = (row.get('mode') or '').strip().lower() or None
            if row.get('item_id') is not None and _same_id(
                    row.get('item_id'), item_id):
                item_mode = mode
            elif row.get('item_id') is None and not _is_blank(item_group_id) \
                    and not _is_blank(row.get('item_group_id')) \
                    and _same_id(row.get('item_group_id'), item_group_id):
                group_mode = mode
        return item_mode if item_mode is not None else group_mode

    # ------------------------------------------------------------------
    # ③ 资格过滤
    # ------------------------------------------------------------------

    def _line_reason(self, line: Dict[str, Any], mode: Optional[str],
                     eval_date: date, dest_org_id: int) -> Optional[str]:
        """判定一条来源行是否可用；可用返回 None，否则返回淘汰原因。"""
        if _truthy(line.get('blocked')):
            return 'blocked'
        if not _covers(line.get('effectivity_start'),
                       line.get('effectivity_end'), eval_date):
            return 'line_expired'

        source_type = (line.get('source_type') or '').strip()

        if source_type in (SOURCE_INTERNAL_ORG, SOURCE_PRODUCTION):
            org_id = line.get('source_org_id')
            if _is_blank(org_id):
                return 'missing_source_ref'
            org = self._fetch_org(org_id)
            if org is None or not _is_active(org.get('status')):
                return 'org_not_found'
            function_type = ('inventory' if source_type == SOURCE_INTERNAL_ORG
                             else 'manufacturing')
            if not self._org_has_function(org_id, function_type, eval_date):
                return ('org_not_inventory'
                        if source_type == SOURCE_INTERNAL_ORG
                        else 'org_not_manufacturing')
            # 跨法人只对内部组织判定；位置表没有 org 关联列，一期跳过
            if source_type == SOURCE_INTERNAL_ORG:
                source_le = self._resolve_legal_entity(org_id)
                dest_le = self._resolve_legal_entity(dest_org_id)
                if source_le is None or dest_le is None:
                    # TR-003 降级口径：解析不到法人时不阻断，仅告警
                    logger.warning(
                        '[sourcing] 法人无法解析，按降级口径放行: '
                        'source_org=%s dest_org=%s', org_id, dest_org_id,
                    )
                elif not _same_id(source_le, dest_le):
                    return 'cross_legal_entity'

        elif source_type == SOURCE_INTERNAL_LOCATION:
            location_id = line.get('source_location_id')
            if _is_blank(location_id):
                return 'missing_source_ref'
            if self._first('SELECT id FROM locations WHERE id = ?',
                           [location_id]) is None:
                return 'missing_source_ref'

        elif source_type == SOURCE_SUPPLIER:
            party_id = line.get('supplier_party_id')
            if _is_blank(party_id):
                return 'missing_source_ref'
            if not self._vendor_relation_exists(party_id):
                return 'supplier_not_vendor'

        else:
            return 'missing_source_ref'

        # 供应方式约束最后判定：全部淘汰时才能可靠区分 MODE_CONFLICT
        if mode == MODE_MAKE and source_type != SOURCE_PRODUCTION:
            return 'mode_mismatch'
        if mode == MODE_BUY and source_type != SOURCE_SUPPLIER:
            return 'mode_mismatch'
        if mode == MODE_TRANSFER and source_type not in (
                SOURCE_INTERNAL_ORG, SOURCE_INTERNAL_LOCATION):
            return 'mode_mismatch'
        return None

    # ------------------------------------------------------------------
    # 查询（带请求内缓存，可覆写注入测试数据）
    # ------------------------------------------------------------------

    def _reset_caches(self) -> None:
        self._org_cache.clear()
        self._org_func_cache.clear()
        self._legal_entity_cache.clear()

    def _rows(self, sql: str, params: Optional[list]) -> List[Dict[str, Any]]:
        cursor = self.ds.execute(sql, list(params or []))
        rows = cursor.fetchall()
        columns = [desc[0] for desc in (cursor.description or [])]
        return [dict(zip(columns, row)) for row in rows]

    def _first(self, sql: str, params: Optional[list]) -> Optional[Dict[str, Any]]:
        rows = self._rows(sql, params)
        return rows[0] if rows else None

    def _fetch_org(self, org_id: Any) -> Optional[Dict[str, Any]]:
        key = str(org_id)
        if key not in self._org_cache:
            self._org_cache[key] = self._first(
                'SELECT id, parent_id, status FROM orgs WHERE id = ?', [org_id]
            )
        return self._org_cache[key]

    def _org_has_function(self, org_id: Any, function_type: str,
                          day: Optional[date]) -> bool:
        """组织是否具备某职能；给了日期则要求该职能在当日有效。"""
        key = (str(org_id), function_type)
        if key not in self._org_func_cache:
            self._org_func_cache[key] = self._rows(
                'SELECT effective_from, effective_to FROM org_functions '
                'WHERE org_id = ? AND function_type = ?',
                [org_id, function_type],
            )
        rows = self._org_func_cache[key]
        if day is None:
            return bool(rows)
        return any(
            _covers(row.get('effective_from'), row.get('effective_to'), day)
            for row in rows
        )

    def _resolve_legal_entity(self, org_id: Any) -> Optional[Any]:
        """沿 parent_id 上溯，返回首个具备 legal_entity 职能的组织 id。

        自身有该职能即返回自身；上溯最多 50 层（防成环）。
        解析不到返回 None，由调用方按 TR-003 降级处理。
        """
        key = str(org_id)
        if key in self._legal_entity_cache:
            return self._legal_entity_cache[key]

        visited = set()
        current = org_id
        depth = 0
        found = None
        while current is not None and depth < _MAX_ORG_DEPTH:
            marker = str(current)
            if marker in visited:
                break
            visited.add(marker)
            org = self._fetch_org(current)
            if org is None:
                break
            if self._org_has_function(current, 'legal_entity', None):
                found = current
                break
            current = org.get('parent_id')
            depth += 1

        self._legal_entity_cache[key] = found
        return found

    def _vendor_relation_exists(self, party_id: Any) -> bool:
        """往来方是否存在有效的 vendor 关系（同一条关系行匹配任一侧即可）。"""
        row = self._first(
            "SELECT COUNT(*) AS cnt FROM party_relations "
            "WHERE role = 'vendor' AND COALESCE(status, 'active') = 'active' "
            "AND (party1_id = ? OR party2_id = ?)",
            [party_id, party_id],
        )
        try:
            return int(row.get('cnt') or 0) > 0 if row else False
        except (TypeError, ValueError):
            return False
