# -*- coding: utf-8 -*-
"""通用任务取人器（Task Assignee Resolver）—— spec §9.5

职责：把一个「参与者声明」（`approval_policy_steps` 的 `approver_type` +
`approver_ref` + `routing_json`）解析成候选用户名单。

口径
----
- `candidates` 一律是 `users.username` 字符串，与 `tasks.executor_candidates`
  和 `task_participations.participant` 同一身份口径；
- 只回答「可能是谁」；「能不能做」仍由权限判定（`{bo}:approve` / `task:handle`，
  D-AP-06：resolver 不替代、也不被权限替代）；
- 空池必须带 `reason`（`no_member` / `no_such_role` / `missing_manager` /
  `level_exhausted` / `unsupported_approver_type`），供前端展示
  「为什么一个人都没有」，不再静默返回 `[]`；
- 禁止 N+1：汇报线/组织解析一次批量拉取后在内存遍历（spec R14）。
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

logger = logging.getLogger(__name__)

#: 空池原因（spec §9.5-2）
REASON_NO_MEMBER = 'no_member'
REASON_NO_SUCH_ROLE = 'no_such_role'
REASON_MISSING_MANAGER = 'missing_manager'
REASON_LEVEL_EXHAUSTED = 'level_exhausted'
REASON_UNSUPPORTED = 'unsupported_approver_type'
REASON_NO_DATA_SOURCE = 'no_data_source'

#: 汇报线默认上溯跳数（0 = 到顶；spec §9.3：`levels` 缺省/`null` 即到顶）
DEFAULT_LEVELS = 0


@dataclass
class Resolution:
    """一次取人的结果（与 `rule_predicate.PredicateResult` 的解释结构同构）。"""

    candidates: List[str] = field(default_factory=list)
    explain: List[Dict[str, Any]] = field(default_factory=list)
    source: str = ''
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'candidates': list(self.candidates),
            'explain': list(self.explain),
            'source': self.source,
            'reason': self.reason,
        }


_RESOLVERS: Dict[str, Callable[..., Resolution]] = {}


def register(approver_type: str) -> Callable:
    """注册取人算子（单职责、可扩展）。"""
    key = str(approver_type).strip().lower()

    def decorator(func: Callable[..., Resolution]) -> Callable[..., Resolution]:
        _RESOLVERS[key] = func
        return func

    return decorator


def supported_types() -> List[str]:
    return sorted(_RESOLVERS)


def resolve(participant: Mapping[str, Any],
            ctx: Mapping[str, Any]) -> Resolution:
    """`participant` = 步骤声明；`ctx` 见 spec §9.5（含 `data_source`）。"""
    participant = participant or {}
    ctx = ctx or {}
    approver_type = str(participant.get('approver_type') or 'user').strip().lower()
    data_source = ctx.get('data_source')
    handler = _RESOLVERS.get(approver_type)
    if handler is None:
        return Resolution(
            explain=[_evidence('approver_type', 'in', supported_types(),
                               approver_type, False)],
            source=approver_type, reason=REASON_UNSUPPORTED)
    if data_source is None:
        return Resolution(
            explain=[_evidence('data_source', 'exists', 'DataSource',
                               None, False)],
            source=approver_type, reason=REASON_NO_DATA_SOURCE)
    return handler(participant, ctx, data_source)


# ─────────────────────────────────────────────────────────────────────────────
# user / role / group / org / position / job_level
# ─────────────────────────────────────────────────────────────────────────────

@register('user')
def _resolve_user(participant, ctx, ds) -> Resolution:
    """指定成员：`approver_ref` 逗号/数组名单（现行为不变）。"""
    refs = _split_ref(participant.get('approver_ref'))
    candidates = sorted(set(refs))
    return Resolution(
        candidates,
        [_evidence('approver_ref', 'in', refs, candidates, bool(candidates))],
        'approver_ref',
        None if candidates else REASON_NO_MEMBER)


@register('role')
def _resolve_role(participant, ctx, ds) -> Resolution:
    """权限角色：`permission_sets.code` → `user_permission_sets` → 用户。"""
    codes = _split_ref(participant.get('approver_ref'))
    if not codes:
        return Resolution(
            explain=[_evidence('approver_ref', 'exists', None, None, False)],
            source='user_permission_sets', reason=REASON_NO_MEMBER)
    rows = _query(
        ds,
        'SELECT DISTINCT u.username AS username FROM users u '
        'JOIN user_permission_sets ups ON ups.user_id = u.id '
        'JOIN permission_sets ps ON ps.id = ups.permission_set_id '
        "WHERE ps.code IN ({0}) AND COALESCE(u.status, 'active') = 'active' "
        'ORDER BY u.username'.format(_placeholders(codes)), codes)
    candidates = [r['username'] for r in rows if r.get('username')]
    if candidates:
        return Resolution(
            candidates,
            [_evidence('role_code', 'in', codes, candidates, True)],
            'user_permission_sets')
    known = _query(
        ds, 'SELECT code FROM permission_sets WHERE code IN ({0})'.format(
            _placeholders(codes)), codes)
    reason = REASON_NO_MEMBER if known else REASON_NO_SUCH_ROLE
    return Resolution(
        explain=[_evidence('role_code', 'in', codes,
                           [r.get('code') for r in known], False)],
        source='user_permission_sets', reason=reason)


@register('group')
def _resolve_group(participant, ctx, ds) -> Resolution:
    """业务编组：`orgs.code` → `org_members` → 用户（不含子组织）。"""
    refs = _split_ref(participant.get('approver_ref'))
    if not refs:
        return Resolution(
            explain=[_evidence('approver_ref', 'exists', None, None, False)],
            source='org_members', reason=REASON_NO_MEMBER)
    rows = _query(
        ds,
        'SELECT DISTINCT u.username AS username FROM orgs o '
        'JOIN org_members m ON m.org_id = o.id '
        'JOIN users u ON u.id = m.user_id '
        "WHERE o.code IN ({0}) AND COALESCE(u.status, 'active') = 'active' "
        'ORDER BY u.username'.format(_placeholders(refs)), refs)
    candidates = [r['username'] for r in rows if r.get('username')]
    return Resolution(
        candidates,
        [_evidence('group_code', 'in', refs, candidates, bool(candidates))],
        'org_members',
        None if candidates else REASON_NO_MEMBER)


@register('org')
def _resolve_org(participant, ctx, ds) -> Resolution:
    """组织维度：`routing_json.org_scope ∈ self | descendants`。"""
    refs = _split_ref(participant.get('approver_ref'))
    routing = _routing(participant)
    scope = str(routing.get('org_scope') or 'self').strip().lower()
    if not refs:
        return Resolution(
            explain=[_evidence('approver_ref', 'exists', None, None, False)],
            source='org_members', reason=REASON_NO_MEMBER)
    params = list(refs) + list(refs)  # code 与 id 两处占位
    match = 'o.code IN ({0}) OR CAST(o.id AS TEXT) IN ({0})'.format(
        _placeholders(refs))
    if scope == 'descendants':
        sql = (
            'WITH RECURSIVE scope_orgs(id) AS ('
            ' SELECT id FROM orgs WHERE ' + match.replace('o.', '') + ' UNION '
            ' SELECT child.id FROM orgs child '
            ' JOIN scope_orgs parent ON child.parent_id = parent.id'
            ') '
            'SELECT DISTINCT u.username AS username FROM scope_orgs s '
            'JOIN org_members m ON m.org_id = s.id '
            'JOIN users u ON u.id = m.user_id '
            "WHERE COALESCE(u.status, 'active') = 'active' "
            'ORDER BY u.username')
    else:
        sql = (
            'SELECT DISTINCT u.username AS username FROM orgs o '
            'JOIN org_members m ON m.org_id = o.id '
            'JOIN users u ON u.id = m.user_id '
            'WHERE (' + match + ') '
            "AND COALESCE(u.status, 'active') = 'active' "
            'ORDER BY u.username')
    rows = _query(ds, sql, params)
    candidates = [r['username'] for r in rows if r.get('username')]
    return Resolution(
        candidates,
        [_evidence('org_scope', 'eq', scope, refs, bool(candidates))],
        'org_members',
        None if candidates else REASON_NO_MEMBER)


@register('position')
def _resolve_position(participant, ctx, ds) -> Resolution:
    """岗位持有人：`employees.position`（首期岗位为自由文本，无岗位主数据）。"""
    refs = _split_ref(participant.get('approver_ref'))
    if not refs:
        return Resolution(
            explain=[_evidence('approver_ref', 'exists', None, None, False)],
            source='employees.position', reason=REASON_NO_MEMBER)
    rows = _query(
        ds,
        'SELECT DISTINCT u.username AS username FROM employees e '
        'JOIN users u ON u.id = e.user_id '
        "WHERE e.position IN ({0}) AND COALESCE(e.status, 'active') = 'active' "
        "AND COALESCE(u.status, 'active') = 'active' "
        'ORDER BY u.username'.format(_placeholders(refs)), refs)
    candidates = [r['username'] for r in rows if r.get('username')]
    return Resolution(
        candidates,
        [_evidence('position', 'in', refs, candidates, bool(candidates))],
        'employees.position',
        None if candidates else REASON_NO_MEMBER)


@register('job_level')
def _resolve_job_level(participant, ctx, ds) -> Resolution:
    """职级：`employees.job_grade` 精确命中（`routing_json.min_job_level` 则按 ≥）。"""
    refs = _split_ref(participant.get('approver_ref'))
    routing = _routing(participant)
    min_level = _int(routing.get('min_job_level'))
    rows = _query(
        ds,
        'SELECT e.job_grade AS job_grade, u.username AS username '
        'FROM employees e JOIN users u ON u.id = e.user_id '
        "WHERE COALESCE(e.status, 'active') = 'active' "
        "AND COALESCE(u.status, 'active') = 'active' "
        'ORDER BY u.username')
    candidates: List[str] = []
    for row in rows:
        grade = _int(row.get('job_grade'))
        if min_level is not None:
            passed = grade is not None and grade >= min_level
        else:
            passed = row.get('job_grade') in refs
        if passed and row.get('username'):
            candidates.append(row['username'])
    expected = min_level if min_level is not None else refs
    op = 'ge' if min_level is not None else 'in'
    return Resolution(
        candidates,
        [_evidence('job_grade', op, expected, candidates, bool(candidates))],
        'employees.job_grade',
        None if candidates else REASON_NO_MEMBER)


# ─────────────────────────────────────────────────────────────────────────────
# manager / manager_chain / position_hierarchy
# ─────────────────────────────────────────────────────────────────────────────

@register('manager')
def _resolve_manager(participant, ctx, ds) -> Resolution:
    """直属主管（一跳）：`employees.manager_employee_id`。"""
    employees = _employee_snapshot(ds)
    start = _initiator_employee_id(ctx, ds, employees)
    if not start:
        return Resolution(
            explain=[_evidence('employee', 'exists', ctx.get('initiator'),
                               None, False)],
            source='manager_employee_id', reason=REASON_MISSING_MANAGER)
    manager_id = _manager_of(employees, start)
    if not manager_id:
        return Resolution(
            explain=[_evidence('manager_employee_id', 'exists', start,
                               None, False)],
            source='manager_employee_id', reason=REASON_MISSING_MANAGER)
    candidates = _usernames_of(ds, [_user_id_of(employees, manager_id)])
    return Resolution(
        candidates,
        [_evidence('manager_employee_id', 'eq', start, manager_id,
                   bool(candidates))],
        'manager_employee_id',
        None if candidates else REASON_MISSING_MANAGER)


@register('manager_chain')
def _resolve_manager_chain(participant, ctx, ds) -> Resolution:
    """多级上溯：`levels` 跳 + `min_job_level` 跳级 + `top_worker_id` 哨兵。"""
    routing = _routing(participant)
    return _walk_chain(
        ctx, ds, routing=routing,
        levels=_levels(routing),
        min_job_level=_int(routing.get('min_job_level')),
        top_worker_id=routing.get('top_worker_id'),
        positions=None,
        include=_include(routing),
        source='manager_chain')


@register('position_hierarchy')
def _resolve_position_hierarchy(participant, ctx, ds) -> Resolution:
    """岗位层级链：沿汇报线上溯，只保留命中目标岗位（`approver_ref`）的节点。"""
    routing = _routing(participant)
    positions = _split_ref(participant.get('approver_ref'))
    return _walk_chain(
        ctx, ds, routing=routing,
        levels=_levels(routing),
        min_job_level=_int(routing.get('min_job_level')),
        top_worker_id=routing.get('top_worker_id'),
        positions=positions,
        include=_include(routing),
        source='position_hierarchy')


def _walk_chain(ctx, ds, *, routing: Mapping[str, Any], levels: int,
                min_job_level: Optional[int], top_worker_id: Any,
                positions: Optional[List[str]], include: List[str],
                source: str) -> Resolution:
    """汇报线遍历：一次批量拉 employee + user，内存上溯（R14 无 N+1）。

    起点由 `approval_chain_of`（起始主体 employee / position / org）与
    `start_with`（manager / self / position / 指定 user）决定，缺省沿用
    「发起人的直属主管，一跳」。
    """
    employees = _employee_snapshot(ds)
    explain: List[Dict[str, Any]] = []
    roots, include_roots, root_reason = _chain_roots(
        ctx, ds, employees, routing, positions, explain)
    if not roots:
        if not explain:
            explain.append(_evidence('employee', 'exists',
                                     ctx.get('initiator'), None, False))
        return Resolution(explain=explain, source=source,
                          reason=root_reason or REASON_MISSING_MANAGER)

    members: List[Mapping[str, Any]] = []
    if include_roots:
        members.extend(employees[str(root)] for root in roots
                       if str(root) in employees)
    top_hit = False
    end_reason: Optional[str] = None
    for root in roots:
        walked, hit, reason = _walk_up(
            employees, root, levels=levels, min_job_level=min_job_level,
            top_worker_id=top_worker_id, positions=positions, explain=explain)
        members.extend(walked)
        top_hit = top_hit or hit
        end_reason = reason or end_reason

    user_ids = [_user_id_of(employees, m.get('id')) for m in members]
    candidates = _usernames_of(ds, user_ids)
    candidates = _with_initiator(candidates, include, ctx)
    reason = None if (candidates or top_hit) else (end_reason or REASON_LEVEL_EXHAUSTED)
    return Resolution(candidates, explain, source, reason)


def _walk_up(employees: Dict[str, Any], start: Any, *, levels: int,
             min_job_level: Optional[int], top_worker_id: Any,
             positions: Optional[List[str]],
             explain: List[Dict[str, Any]]) -> tuple:
    """自 `start` 沿 `manager_employee_id` 上溯，返回 (成员, 是否命中哨兵, 终止原因)。"""
    members: List[Mapping[str, Any]] = []
    hops = 0
    current = start
    end_reason: Optional[str] = None
    while True:
        manager_id = _manager_of(employees, current)
        if not manager_id:
            end_reason = REASON_LEVEL_EXHAUSTED if members else REASON_MISSING_MANAGER
            break
        hops += 1
        manager = employees.get(str(manager_id))
        if not manager:
            explain.append(_evidence('manager_employee_id', 'eq', current,
                                     manager_id, False))
            end_reason = REASON_MISSING_MANAGER
            break
        explain.append(_evidence('manager_employee_id', 'eq', current,
                                 manager_id, True))
        keep = True
        if positions and str(manager.get('position') or '') not in positions:
            keep = False
            explain.append(_evidence('position', 'in', positions,
                                     manager.get('position'), False))
        if min_job_level is not None:
            grade = _int(manager.get('job_grade'))
            passed = grade is not None and grade >= min_job_level
            explain.append(_evidence('job_grade', 'ge', min_job_level,
                                     manager.get('job_grade'), passed))
            keep = keep and passed
        if keep:
            members.append(manager)
        if top_worker_id not in (None, '') and str(manager_id) == str(top_worker_id):
            return members, True, end_reason
        if levels > 0 and hops >= levels:
            end_reason = REASON_LEVEL_EXHAUSTED
            break
        current = manager_id
    return members, False, end_reason


#: `start_with` 关键字（其余值按「指定 user」处理，spec §9.3）
_START_WITH_KEYWORDS = ('', 'manager', 'self', 'position')


def _chain_roots(ctx: Mapping[str, Any], ds, employees: Dict[str, Any],
                 routing: Mapping[str, Any], positions: Optional[List[str]],
                 explain: List[Dict[str, Any]]) -> tuple:
    """解析链起点：返回 (roots, 是否含起点本人, 空池原因)。"""
    start = _initiator_employee_id(ctx, ds, employees)
    if not start:
        return [], False, REASON_MISSING_MANAGER
    chain_of = str(routing.get('approval_chain_of') or 'employee').strip().lower()
    start_with = str(routing.get('start_with') or 'manager').strip().lower()
    roots: List[Any] = [start]
    include_roots = False
    reason: Optional[str] = None

    if chain_of == 'org':
        managers = _org_manager_employee_ids(ds, employees, start)
        explain.append(_evidence('approval_chain_of', 'eq', 'org', managers,
                                 bool(managers)))
        if managers:
            roots, include_roots = managers, True
    elif chain_of == 'position':
        # 岗位节点由该岗位持有人代表（employees.position 为自由文本，无岗位主数据）
        explain.append(_evidence('approval_chain_of', 'eq', 'position',
                                 (employees.get(str(start)) or {}).get('position'),
                                 True))
        include_roots = True
    elif chain_of not in ('', 'employee'):
        explain.append(_evidence('approval_chain_of', 'in',
                                 ['employee', 'position', 'org'], chain_of, False))

    if start_with == 'position' and positions:
        roots = [eid for eid, row in employees.items()
                 if str(row.get('position') or '') in positions]
        include_roots = True
        reason = None if roots else REASON_NO_MEMBER
    elif start_with not in _START_WITH_KEYWORDS:
        employee_id = _employee_id_of_user(ds, employees, start_with)
        explain.append(_evidence('start_with', 'eq', start_with, employee_id,
                                 employee_id is not None))
        if employee_id is not None:
            roots, include_roots = [employee_id], True
        else:
            roots, reason = [], REASON_MISSING_MANAGER
    elif start_with in ('self', 'position'):
        include_roots = True
    return roots, include_roots, reason


def _org_manager_employee_ids(ds, employees: Dict[str, Any],
                              employee_id: Any) -> List[str]:
    """`approval_chain_of='org'` 起点：发起人所在组织的负责人（`org_members.is_manager`）。"""
    org_id = (employees.get(str(employee_id)) or {}).get('org_id')
    if org_id in (None, ''):
        return []
    rows = _query(ds, 'SELECT user_id FROM org_members '
                      'WHERE org_id = ? AND COALESCE(is_manager, 0) = 1',
                  [org_id])
    user_ids = {str(r.get('user_id')) for r in rows if r.get('user_id') is not None}
    if not user_ids:
        return []
    return [eid for eid, row in employees.items()
            if str(row.get('user_id')) in user_ids]


def _employee_id_of_user(ds, employees: Dict[str, Any], username: str) -> Any:
    """`start_with='<username>'` 起点：该用户的 employee 节点。"""
    rows = _query(ds, 'SELECT id FROM users WHERE username = ? LIMIT 1',
                  [username])
    if not rows:
        return None
    user_id = str(rows[0].get('id'))
    for eid, row in employees.items():
        if str(row.get('user_id')) == user_id:
            return eid
    return None


# ─────────────────────────────────────────────────────────────────────────────
# expression / initiator_choice
# ─────────────────────────────────────────────────────────────────────────────

@register('expression')
def _resolve_expression(participant, ctx, ds) -> Resolution:
    """表达式取人：复用 `rule_predicate`，对员工记录求值（不新写求值器）。"""
    from meta.core import rule_predicate

    routing = _routing(participant)
    node = routing.get('expression')
    if node in (None, '', {}):
        return Resolution(
            explain=[_evidence('expression', 'exists', None, None, False)],
            source='rule_predicate', reason=REASON_NO_MEMBER)
    employees = _employee_snapshot(ds)
    matched_user_ids: List[Any] = []
    explain: List[Dict[str, Any]] = []
    for employee in employees.values():
        result = rule_predicate.evaluate(employee, node)
        explain.extend(result.explain or [])
        if result.passed:
            matched_user_ids.append(_user_id_of(employees, employee.get('id')))
    candidates = _usernames_of(ds, matched_user_ids)
    return Resolution(candidates, explain, 'rule_predicate',
                      None if candidates else REASON_NO_MEMBER)


@register('initiator_choice')
def _resolve_initiator_choice(participant, ctx, ds) -> Resolution:
    """发起人自选：读提交时的 `inputs.approver_selection`（服务端已校验范围）。"""
    record = ctx.get('record') or {}
    raw = (ctx.get('approver_selection')
           or record.get('approver_selection')
           or (ctx.get('policy_snapshot') or {}).get('approver_selection'))
    candidates = sorted(set(_split_ref(raw)))
    return Resolution(
        candidates,
        [_evidence('approver_selection', 'in', candidates, candidates,
                   bool(candidates))],
        'inputs.approver_selection',
        None if candidates else REASON_NO_MEMBER)


# ─────────────────────────────────────────────────────────────────────────────
# 内部工具
# ─────────────────────────────────────────────────────────────────────────────

def _query(data_source, sql: str, params: Optional[Iterable] = None) -> List[Dict[str, Any]]:
    """查询失败（表未建 / 测试替身缺表）按空集处理，不阻断建任务。"""
    try:
        return list(data_source.query(sql, list(params or [])))
    except Exception:  # noqa: BLE001
        logger.debug('[Resolver] 查询跳过：%s', sql, exc_info=True)
        return []


def _placeholders(values) -> str:
    return ', '.join('?' * len(values))


def _split_ref(ref: Any) -> List[str]:
    if ref is None:
        return []
    raw = ref if isinstance(ref, (list, tuple, set)) else str(ref).split(',')
    return [str(x).strip() for x in raw if str(x or '').strip()]


def _routing(participant: Mapping[str, Any]) -> Dict[str, Any]:
    raw = participant.get('routing_json')
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _include(routing: Mapping[str, Any]) -> List[str]:
    """`include` 节点：`requester`/`self` 计为候选人；`skip_empty` 是遍历语义
    （过滤不阻塞上溯，已由 `_walk_up` 天然满足），此处只透传。"""
    raw = routing.get('include')
    return [str(x).strip().lower() for x in _split_ref(raw)]


def _levels(routing: Mapping[str, Any]) -> int:
    """`levels`：`N` 上溯 N 跳；`0`/`null`/缺省 = 到顶（spec §9.3）。"""
    value = routing.get('levels')
    if value in (None, ''):
        return DEFAULT_LEVELS
    parsed = _int(value)
    return DEFAULT_LEVELS if parsed is None else max(parsed, 0)


def _int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return None


def _evidence(field_name: str, op: str, expected: Any, actual: Any,
              passed: bool) -> Dict[str, Any]:
    """与 `rule_predicate` 同构的解释项（field / op / expected / actual / passed）。"""
    return {'field': field_name, 'op': op, 'expected': expected,
            'actual': actual, 'passed': bool(passed)}


def _employee_snapshot(ds) -> Dict[str, Dict[str, Any]]:
    rows = _query(
        ds,
        'SELECT id, user_id, manager_employee_id, job_grade, position, '
        "org_id FROM employees WHERE COALESCE(status, 'active') = 'active'")
    return {str(r.get('id')): dict(r) for r in rows if r.get('id') is not None}


def _initiator_employee_id(ctx: Mapping[str, Any], ds,
                           employees: Optional[Dict[str, Any]] = None) -> Any:
    explicit = ctx.get('employee_id')
    if explicit not in (None, ''):
        return explicit
    username = ctx.get('initiator')
    if not username:
        return None
    if employees is None:
        employees = _employee_snapshot(ds)
    rows = _query(
        ds,
        'SELECT e.id AS id FROM employees e JOIN users u ON u.id = e.user_id '
        "WHERE u.username = ? AND COALESCE(e.status, 'active') = 'active' "
        'LIMIT 1', [username])
    if rows:
        return rows[0].get('id')
    # 兜底：发起人本身就是 employee id / employee_no
    for key, row in employees.items():
        if str(row.get('id')) == str(username):
            return row.get('id')
    return None


def _manager_of(employees: Dict[str, Any], employee_id: Any) -> Any:
    row = employees.get(str(employee_id))
    if not row:
        return None
    return row.get('manager_employee_id')


def _user_id_of(employees: Dict[str, Any], employee_id: Any) -> Any:
    row = employees.get(str(employee_id)) or {}
    return row.get('user_id')


def _usernames_of(ds, user_ids: Iterable) -> List[str]:
    ids = [i for i in {str(x) for x in user_ids if x not in (None, '')}]
    if not ids:
        return []
    rows = _query(
        ds,
        "SELECT id, username FROM users WHERE CAST(id AS TEXT) IN ({0}) "
        "AND COALESCE(status, 'active') = 'active' "
        'ORDER BY username'.format(_placeholders(ids)), ids)
    return [r['username'] for r in rows if r.get('username')]


def _with_initiator(candidates: List[str], include: List[str],
                    ctx: Mapping[str, Any]) -> List[str]:
    initiator = str(ctx.get('initiator') or '').strip()
    if initiator and ('requester' in include or 'self' in include):
        return sorted(set(candidates) | {initiator})
    return sorted(set(candidates))