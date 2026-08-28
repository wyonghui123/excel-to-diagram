# -*- coding: utf-8 -*-
"""
权限集一致性体检服务 (Permission Health Check)

[2026-08-28] 应用户需求实现"权限体检"，替代原「模拟预览」占位按钮。
对单个权限集执行一致性校验：

  C1 unreachable_perms   不可达功能权限：permission_set_permissions 已授予，但没有任何
                         已分配菜单（含非 sidebar 的 -list 页面）能提供入口，
                         且非维度范围派生 —— 用户无法通过 UI 使用该权限。
                         注意：v2 资源矩阵的直接授权属合法 manual_include
                         （effective = (auto_menu ∪ manual_include) - manual_exclude），
                         不可自动清理，仅提示确认。
  C2 empty_menus         空授权菜单：菜单已分配但一个权限都没授予
  C3 write_without_scope 有写权限但无数据范围：菜单授予 create/update/delete 等
                         写动作，但数据权限与维度范围均为空
  C4 scope_without_menu  范围配置了但菜单未分配：permission_set_data_permissions /
                         permission_set_dimension_scopes 声明了范围，却没有对应菜单分配
  C5 residual_excludes   残留排除记录：granted=0（Deny）行，但其权限代码不属于
                         任何已分配菜单 —— 编辑会话的残留（可清理）
  C6 super_permission    超级权限提示：持有 '*' 时三层校验失去意义，仅提示

数据口径与 role_menu_api._build_role_unified_data 保持一致（单一事实源 menus 表），
但预期权限计算包含非 sidebar 菜单（permission_set_menu_permissions 可含 -list 页面）。
"""

from typing import Any, Dict, List, Set

from meta.core.permission_label import get_permission_label

# 写动作集合（export 属读类，不计入 C3）
_WRITE_ACTIONS = {
    'create', 'update', 'delete', 'import',
    'assign', 'unassign', 'grant', 'revoke',
    'associate', 'dissociate',
}


def _safe_json_list(raw) -> list:
    import json
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _safe_json_dict(raw) -> dict:
    import json
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _expanded(code: str) -> str:
    """兼容 expanded 格式: scheduled_task:create -> scheduled_task:scheduled_task_create"""
    parts = code.split(':')
    if len(parts) == 2:
        return f"{parts[0]}:{parts[0]}_{parts[1]}"
    return code


def _fallback_label(code: str) -> str:
    """name=code 的英文记录兜底：从 MetaRegistry 生成 "对象中文名:动作中文名"

    [2026-08-28] 资源矩阵动态创建的权限 (如 enum_type:export) 在菜单初始化组
    无中文对应记录，label 会显示英文 code。此处对齐 role_menu_api
    _get_permission_label 的逻辑：BO meta action name → 标准动作 name → 原 code。
    [2026-08-28 重构] 实现抽取到 meta/Core/permission_label.py 公共 util
    （与 role_menu_api._get_permission_label 共用，消除双副本），此处仅委托。
    """
    return get_permission_label(code)


def _load_role_context(ds, permission_set_id: int):
    """加载体检所需的全部原始数据（口径对齐 _build_role_unified_data）"""
    # 含非 sidebar 菜单（-list 页面也在 permission_set_menu_permissions 中出现）
    cursor = ds.execute(
        "SELECT * FROM menus WHERE is_active = 1 "
        "AND menu_code != 'dashboard' ORDER BY sort_order"
    )
    columns = [desc[0] for desc in cursor.description]
    menus = [dict(zip(columns, row)) for row in cursor.fetchall()]

    cursor = ds.execute(
        "SELECT menu_code FROM permission_set_menu_permissions WHERE permission_set_id = ?", [permission_set_id]
    )
    assigned_menus = {row[0] for row in cursor.fetchall()}

    # granted=1 已授予功能权限 (含明细), granted=0 排除记录
    # [FIX 2026-08-28] row_id 必须取 rp.id (permission_set_permissions 行 id)，用于清理 DELETE；
    #   之前误用 p.id (permissions.id)，导致 DELETE 条件错位、清理假成功
    cursor = ds.execute(
        """SELECT p.id, p.code, p.name, rp.granted, rp.id
           FROM permissions p
           JOIN permission_set_permissions rp ON p.id = rp.permission_id
           WHERE rp.permission_set_id = ?""",
        [permission_set_id],
    )
    granted_rows: List[Dict[str, Any]] = []   # granted=1
    excluded_rows: List[Dict[str, Any]] = []  # granted=0
    for pid, code, name, granted, rp_id in cursor.fetchall():
        item = {'permission_id': pid, 'code': code, 'name': name, 'row_id': rp_id}
        if granted == 1 or granted is True:
            granted_rows.append(item)
        else:
            excluded_rows.append(item)

    cursor = ds.execute(
        "SELECT DISTINCT resource_type FROM permission_set_data_permissions WHERE permission_set_id = ?",
        [permission_set_id],
    )
    data_perm_types = {row[0] for row in cursor.fetchall()}

    cursor = ds.execute(
        "SELECT dimension_code FROM permission_set_dimension_scopes WHERE permission_set_id = ?",
        [permission_set_id],
    )
    dimension_codes = {row[0] for row in cursor.fetchall() if row[0]}

    return {
        'menus': menus,
        'assigned_menus': assigned_menus,
        'granted_rows': granted_rows,
        'excluded_rows': excluded_rows,
        'data_perm_types': data_perm_types,
        'dimension_codes': dimension_codes,
    }


def _expected_codes_for_assigned_menus(ctx) -> Set[str]:
    """已分配菜单"应拥有"的权限代码全集（含 bo_bindings 派生与 expanded 兼容格式）"""
    expected: Set[str] = set()
    for menu in ctx['menus']:
        if menu['menu_code'] not in ctx['assigned_menus']:
            continue
        for p in _safe_json_list(menu.get('required_permissions')):
            expected.add(p)
            expected.add(_expanded(p))
        for binding in _safe_json_list(menu.get('bo_bindings')):
            bo_id = binding.get('bo_id')
            if not bo_id:
                continue
            for action in (binding.get('include_actions') or []):
                if action == 'list':
                    continue
                derived = f"{bo_id}:{action}"
                expected.add(derived)
                expected.add(_expanded(derived))
    return expected


def _dimension_expected_codes(ctx) -> Set[str]:
    """维度范围运行时派生的权限代码（derived: {dim}:read + expanded + association 跟随端点）"""
    expected: Set[str] = set()
    for dim in ctx['dimension_codes']:
        expected.add(f"{dim}:read")
        expected.add(_expanded(f"{dim}:read"))
    return expected


def run_permission_set_consistency_audit(ds, permission_set_id: int) -> Dict[str, Any]:
    """执行 6 项体检，返回 {ok, issues[], summary}"""
    ctx = _load_role_context(ds, permission_set_id)
    issues: List[Dict[str, Any]] = []

    def _add(check_id, severity, title, description, items, fixable=False):
        if not items:
            return
        issues.append({
            'check': check_id,
            'severity': severity,      # error | warning | info
            'title': title,
            'description': description,
            'count': len(items),
            'items': items,
            'fixable': fixable,
        })

    has_super = any(r['code'] == '*' for r in ctx['granted_rows'])

    if has_super:
        _add('super_permission', 'info', '持有超级权限',
             '该角色拥有 "*" 超级权限，所有菜单/功能/数据权限校验均被绕过。'
             '如需精细化管控请先移除超级权限。', [{
                 'code': '*',
                 'label': '超级权限 (*)',
             }])
        # 超级权限下其他检查无意义，直接返回
        return {
            'ok': len(issues) == 0,
            'permission_set_id': permission_set_id,
            'issues': issues,
            'summary': {
                'total_issues': len(issues),
                'errors': 0,
                'warnings': 0,
                'infos': len(issues),
                'has_super': True,
                'checked_menus': 0,
                'granted_perms': 1,
            },
        }

    expected = _expected_codes_for_assigned_menus(ctx)
    dim_expected = _dimension_expected_codes(ctx)
    dim_codes = ctx['dimension_codes']

    # ---- C1 不可达功能权限 ----
    # v2 资源矩阵的直接授权是合法 manual_include，不可判定为"孤儿"自动清理；
    # 但若资源没有任何已分配菜单提供入口，则该权限在 UI 上不可达，仅提示。
    unreachable_items = []
    assigned_prefixes: Set[str] = set()
    for menu in ctx['menus']:
        if menu['menu_code'] not in ctx['assigned_menus']:
            continue
        for p in _safe_json_list(menu.get('required_permissions')):
            assigned_prefixes.add(str(p).split(':')[0])
        for binding in _safe_json_list(menu.get('bo_bindings')):
            if binding.get('bo_id'):
                assigned_prefixes.add(binding['bo_id'])
        hint = _safe_json_dict(menu.get('data_permission_hint'))
        for rt in (hint.get('resource_types') or []):
            assigned_prefixes.add(rt)
        if menu.get('primary_object_type'):
            assigned_prefixes.add(menu['primary_object_type'])
    assigned_prefixes |= dim_codes

    # [2026-08-28] 语义聚合去重：permissions 表存在两组同语义记录
    #   菜单初始化组: enum_type:enum_type_read (name=枚举类型查询)
    #   资源矩阵组:   enum_type:read (name=code，英文)
    # 两组同时被授予且不可达时列表会重复显示，按 (资源类型, 标准化动作)
    # 分组合并，每组优先保留中文名称记录。
    semantic_groups: Dict[Any, List[Dict[str, Any]]] = {}
    for row in ctx['granted_rows']:
        code = row['code']
        if code == '*':
            continue
        prefix = code.split(':')[0]
        if prefix in assigned_prefixes:
            continue
        # 维度派生 read / association 跟随端点
        if code in dim_expected:
            continue
        parts = code.split(':', 1)
        if len(parts) == 2:
            rt, action = parts
            # 标准化 action: enum_type_read -> read
            std_action = action[len(rt) + 1:] if action.startswith(rt + '_') else action
            key = (rt, std_action)
        else:
            key = (code, '')  # 非法 code 格式，独立成组保留原始记录
        semantic_groups.setdefault(key, []).append(row)

    for rows in semantic_groups.values():
        # 优先选择有中文 name（name 与 code 不同）的记录
        preferred = next(
            (r for r in rows if r['name'] and r['name'] != r['code']),
            rows[0],
        )
        # name=code（英文记录）时从 MetaRegistry 兜底生成中文标签
        label = preferred['name'] or preferred['code']
        if label == preferred['code']:
            label = _fallback_label(preferred['code'])
        unreachable_items.append({'code': preferred['code'], 'label': label})
    _add('unreachable_perms', 'warning', '不可达功能权限',
         '以下功能权限已授予，但没有任何已分配菜单提供使用入口'
         '（勾掉菜单后权限仍保留，或资源矩阵直接授权了无入口的资源）。'
         '请确认是否需要：分配对应菜单，或移除这些权限。',
         unreachable_items)

    # ---- C2 空授权菜单 ----
    empty_items = []
    for menu in ctx['menus']:
        if menu['menu_code'] not in ctx['assigned_menus']:
            continue
        req_perms = _safe_json_list(menu.get('required_permissions'))
        bo_bindings = _safe_json_list(menu.get('bo_bindings'))
        if not req_perms and not bo_bindings:
            continue  # 菜单本身不要求权限（如目录节点），不算问题
        granted_codes = {r['code'] for r in ctx['granted_rows']}
        has_any = any(
            p in granted_codes or _expanded(p) in granted_codes for p in req_perms
        )
        if not has_any:
            # bo_bindings 派生权限也查一遍
            has_any = any(
                f"{b.get('bo_id')}:{a}" in granted_codes
                for b in bo_bindings
                for a in (b.get('include_actions') or [])
            )
        if not has_any:
            empty_items.append({
                'menu_code': menu['menu_code'],
                'label': menu.get('menu_name') or menu['menu_code'],
            })
    _add('empty_menus', 'warning', '空授权菜单',
         '以下菜单已分配给角色，但没有任何已授予的功能权限，用户进入菜单后'
         '将看到无权限/空数据。请分配权限或取消勾选菜单。',
         empty_items)

    # ---- C3 有写权限但无数据范围 ----
    write_items = []
    for menu in ctx['menus']:
        if menu['menu_code'] not in ctx['assigned_menus']:
            continue
        granted_codes = {r['code'] for r in ctx['granted_rows']}
        req_perms = _safe_json_list(menu.get('required_permissions'))
        bo_bindings = _safe_json_list(menu.get('bo_bindings'))
        all_codes = set(req_perms)
        for b in bo_bindings:
            for a in (b.get('include_actions') or []):
                all_codes.add(f"{b.get('bo_id')}:{a}")
        write_codes = {
            c for c in all_codes
            if c.split(':')[-1] in _WRITE_ACTIONS
            and (c in granted_codes or _expanded(c) in granted_codes)
        }
        if not write_codes:
            continue
        hint = _safe_json_dict(menu.get('data_permission_hint'))
        hint_types = set(hint.get('resource_types') or [])
        # 有行级数据权限 / 维度范围覆盖 → 视为已配置范围
        has_scope = bool(hint_types & ctx['data_perm_types'])
        has_scope = has_scope or bool(hint_types & dim_codes)
        has_scope = has_scope or any(
            b.get('bo_id') in dim_codes for b in bo_bindings
        )
        if not has_scope:
            write_items.append({
                'menu_code': menu['menu_code'],
                'label': menu.get('menu_name') or menu['menu_code'],
                'write_codes': sorted(write_codes),
            })
    _add('write_without_scope', 'warning', '写权限无数据范围',
         '以下菜单授予了写动作（创建/更新/删除等），但未配置任何数据范围'
         '（行级数据权限与维度范围均为空），写操作将作用于全部数据或被拒绝，'
         '请确认是否符合预期。',
         write_items)

    # ---- C4a 行级数据范围配置了但相关菜单未分配 ----
    orphan_scope_items = []
    for rt in ctx['data_perm_types']:
        related_assigned = False
        for menu in ctx['menus']:
            if menu['menu_code'] not in ctx['assigned_menus']:
                continue
            hint = _safe_json_dict(menu.get('data_permission_hint'))
            if rt in (hint.get('resource_types') or []):
                related_assigned = True
                break
        if not related_assigned:
            orphan_scope_items.append({'resource_type': rt, 'label': rt})
    _add('scope_without_menu', 'info', '数据范围无关联菜单',
         '以下资源类型配置了行级数据范围，但没有已分配菜单引用它'
         '（可能是菜单取消勾选后的残留）。',
         orphan_scope_items)

    # ---- C4b 维度范围配置了但相关菜单未分配 ----
    orphan_dim_items = []
    for dim in dim_codes:
        related_assigned = False
        for menu in ctx['menus']:
            if menu['menu_code'] not in ctx['assigned_menus']:
                continue
            hint = _safe_json_dict(menu.get('data_permission_hint'))
            hint_types = set(hint.get('resource_types') or [])
            bo_ids = {b.get('bo_id') for b in _safe_json_list(menu.get('bo_bindings'))}
            req_prefixes = {str(p).split(':')[0]
                            for p in _safe_json_list(menu.get('required_permissions'))}
            if dim in hint_types or dim in bo_ids or dim in req_prefixes \
                    or dim == menu.get('primary_object_type'):
                related_assigned = True
                break
        if not related_assigned:
            orphan_dim_items.append({'dimension_code': dim, 'label': dim})
    if orphan_dim_items:
        issues.append({
            'check': 'dimension_scope_without_menu',
            'severity': 'info',
            'title': '维度范围无关联菜单',
            'description': '以下维度配置了维度范围，但没有已分配菜单引用它'
                           '（派生的 read 权限实际不可达）。',
            'count': len(orphan_dim_items),
            'items': orphan_dim_items,
            'fixable': False,
        })

    # ---- C5 残留排除记录 ----
    residual_excludes = []
    for row in ctx['excluded_rows']:
        if row['code'] in expected:
            continue  # 已分配菜单的显式 Deny，属正常业务语义
        residual_excludes.append({'code': row['code'], 'label': row['name'] or row['code']})
    _add('residual_excludes', 'info', '残留排除记录',
         '以下"排除(Deny)"记录对应的权限已不属于任何已分配菜单，'
         '为编辑会话残留，可在「一键清理」中移除。',
         residual_excludes, fixable=True)

    error_count = sum(1 for i in issues if i['severity'] == 'error')
    warning_count = sum(1 for i in issues if i['severity'] == 'warning')
    info_count = sum(1 for i in issues if i['severity'] == 'info')

    return {
        'ok': len(issues) == 0,
        'permission_set_id': permission_set_id,
        'issues': issues,
        'summary': {
            'total_issues': len(issues),
            'errors': error_count,
            'warnings': warning_count,
            'infos': info_count,
            'has_super': False,
            'checked_menus': len(ctx['assigned_menus']),
            'granted_perms': len(ctx['granted_rows']),
        },
    }


def cleanup_role_permission_residue(ds, permission_set_id: int) -> Dict[str, Any]:
    """一键清理：仅删除 C5 残留排除记录（granted=0 且不属于任何已分配菜单）

    [安全边界] v2 资源矩阵的直接授权是合法 manual_include，
    granted=1 的权限行一律不动，避免误删用户的手动授权。
    返回删除明细。
    """
    ctx = _load_role_context(ds, permission_set_id)
    expected = _expected_codes_for_assigned_menus(ctx)

    deleted_excludes: List[str] = []

    for row in ctx['excluded_rows']:
        if row['code'] in expected:
            continue
        ds.execute("DELETE FROM permission_set_permissions WHERE id = ?", [row['row_id']])
        deleted_excludes.append(row['code'])

    return {
        'deleted_orphan_perms': [],  # [安全] 不自动删除授权行，字段保留兼容前端
        'deleted_residual_excludes': deleted_excludes,
        'deleted_count': len(deleted_excludes),
    }
