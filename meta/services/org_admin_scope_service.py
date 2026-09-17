# -*- coding: utf-8 -*-
"""
组织委托管理范围解析服务（Spec 19 M2：FR-004 / FR-009 双钥匙核心）

模型（与 Spec 19 §2/§4 一致）：
    委托授权 = 功能权限（钥匙一，PermissionInterceptor / 端点装饰器）
             × 行级范围（钥匙二，本服务动态解析）

数据载体（不新建独立委托表，复用资源矩阵）：
    user → (org_members) → org → (org_permission_sets) → permission_set
         → (data_permission_rules, resource_type='org', rule_type='condition')
         → condition = 'id = <org_id>' / 'id IN (...)' / '*'

动态范围解析（FR-009，不物化静态清单）：
    绑定组织 X ⇒ 可管理范围 = {X} ∪ descendants(X)（查询时实时展开），
    组织树调整后范围自动跟随，无需重算。

语义约定：
    - condition='*'（通配符）：全组织范围 —— 仅全局管理员权限集允许存在，
      受托管理员侧遇到 '*' 按通配放行（其权限集由全局管理员配置，配置即授权）。
    - user 资源无独立行级条件：可管理用户 = 可管理组织子树 ∩ org_members 归属。
    - 本服务只回答「范围内 / 范围外」，功能码校验不在本服务职责内（双钥匙各自独立）。
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# condition 解析：id = 15 / id IN (15, 16) / id in(15)
_EQ_RE = re.compile(r'\bid\s*=\s*(\d+)\b', re.IGNORECASE)
_IN_RE = re.compile(r'\bid\s+IN\s*\(([^)]*)\)', re.IGNORECASE)


class OrgAdminScopeService:
    """组织委托管理行级范围解析（钥匙二）"""

    def __init__(self, data_source):
        self.ds = data_source

    # ---------- 权限集聚合 ----------

    def _get_user_permission_set_ids(self, user_id: int) -> List[int]:
        from meta.services.permission_service import PermissionService
        rows = PermissionService(self.ds).get_user_permission_sets(user_id)
        return [r['id'] for r in rows]

    # ---------- 规则解析 ----------

    def get_delegated_org_rules(self, user_id: int) -> Dict:
        """聚合用户全部权限集的 org 行级规则。

        Returns:
            {
              'wildcard': bool,          # 任一规则为 '*'
              'root_ids': set[int],      # 绑定组织根 id 集合（condition 中解析的 id）
              'rules': list[dict],       # 原始规则（审计/展示用）
            }
        """
        ps_ids = self._get_user_permission_set_ids(user_id)
        result = {'wildcard': False, 'root_ids': set(), 'rules': []}
        if not ps_ids:
            return result

        placeholders = ','.join('?' * len(ps_ids))
        try:
            cursor = self.ds.execute(
                f"""SELECT id, permission_set_id, condition, permission_level
                    FROM data_permission_rules
                    WHERE resource_type = 'org'
                      AND rule_type = 'condition'
                      AND COALESCE(is_denied, 0) = 0
                      AND permission_set_id IN ({placeholders})""",
                ps_ids,
            )
            rules = cursor.fetchall()
        except Exception:
            # 表未建（lazy init 未触发）等情况：按无委托处理，但必须留下排查痕迹
            logger.warning(
                'get_delegated_org_rules: data_permission_rules 查询失败（按无委托处理）',
                exc_info=True,
            )
            return result

        for row in rules:
            rule_id, ps_id, condition, level = row[0], row[1], row[2], row[3]
            cond = (condition or '').strip()
            entry = {'id': rule_id, 'permission_set_id': ps_id,
                     'condition': cond, 'permission_level': level}
            result['rules'].append(entry)
            if not cond or cond == '*':
                result['wildcard'] = True
                continue
            for m in _EQ_RE.finditer(cond):
                result['root_ids'].add(int(m.group(1)))
            for m in _IN_RE.finditer(cond):
                for tok in m.group(1).split(','):
                    tok = tok.strip().strip("'\"")
                    if tok.isdigit():
                        result['root_ids'].add(int(tok))
        return result

    # ---------- 范围展开（动态，防环） ----------

    def expand_org_scope(self, root_ids: set) -> set:
        """绑定根集合 → 全管理范围（含各根的子孙，实时展开，循环防护）"""
        scope = set()
        for root_id in root_ids:
            if root_id in scope:
                continue
            scope.add(root_id)
            # 迭代式 BFS 展开子孙（避免深树递归），visited 防环
            frontier = [root_id]
            visited = {root_id}
            while frontier:
                current = frontier.pop()
                try:
                    cursor = self.ds.execute(
                        "SELECT id FROM orgs WHERE parent_id = ?", [current]
                    )
                    children = [r[0] for r in cursor.fetchall()]
                except Exception:
                    children = []
                for child in children:
                    if child not in visited:
                        visited.add(child)
                        scope.add(child)
                        frontier.append(child)
        return scope

    def get_manageable_org_ids(self, user_id: int) -> Optional[set]:
        """用户的可管理组织全集。

        Returns:
            None  —— 通配（'*'，全组织）
            set() —— 无委托（非受托管理员）
            set   —— 具体范围
        """
        rules = self.get_delegated_org_rules(user_id)
        if rules['wildcard']:
            return None
        return self.expand_org_scope(rules['root_ids'])

    # ---------- 校验入口 ----------

    def check_org_scope(self, user_id: int, target_org_id: Optional[int],
                        action: str = 'update') -> Tuple[bool, str]:
        """校验对目标组织的操作是否在其受托范围内。

        FR-004 语义：绑定 X ⇒ 可管理 X 子树。目标组织的祖先链（含自身）
        命中任一绑定根即在范围内（target ∈ descendants(X) ∪ {X}）。
        通配 = 全范围。target_org_id 为空仅通配可通过（根级操作）。
        """
        rules = self.get_delegated_org_rules(user_id)
        if not rules['wildcard'] and not rules['root_ids']:
            return False, '无组织管理委托'
        if rules['wildcard']:
            return True, 'wildcard'

        if target_org_id is None:
            return False, '根级操作需绑定具体组织或全局管理员'

        # 沿祖先链向上找绑定根（含自身）——比展开全子孙更省
        current, visited = target_org_id, set()
        while current is not None:
            if current in rules['root_ids']:
                return True, f'org#{current} 在绑定子树内'
            if current in visited:
                break  # 环防护
            visited.add(current)
            try:
                row = self.ds.execute(
                    "SELECT parent_id FROM orgs WHERE id = ?", [current]
                ).fetchone()
            except Exception:
                return False, f'目标组织 #{target_org_id} 不存在'
            current = row[0] if row else None
        return False, f'组织 #{target_org_id} 不在任何受托子树内 (action={action})'

    def check_user_scope(self, user_id: int, target_user_id: int,
                         action: str = 'update') -> Tuple[bool, str]:
        """校验对目标用户的管理是否在受托范围内。

        FR-004 语义：可管理用户 = 可管理组织范围 ∩ 用户归属组织。
        """
        rules = self.get_delegated_org_rules(user_id)
        if not rules['wildcard'] and not rules['root_ids']:
            return False, '无组织管理委托'
        if rules['wildcard']:
            return True, 'wildcard'

        scope = self.expand_org_scope(rules['root_ids'])
        try:
            cursor = self.ds.execute(
                "SELECT org_id FROM org_members WHERE user_id = ?", [target_user_id]
            )
            memberships = {r[0] for r in cursor.fetchall()}
        except Exception:
            return False, f'目标用户 #{target_user_id} 组织归属查询失败'

        if memberships & scope:
            hit = sorted(memberships & scope)[0]
            return True, f'用户归属 org#{hit} 在受托范围内'
        return False, f'用户 #{target_user_id} 不在受托组织范围内 (action={action})'

    # ---------- 创建类操作的范围目标 ----------

    @staticmethod
    def extract_org_ids_from_params(params: Dict) -> List[int]:
        """从写路径 params 中提取涉及的组织 id（create/update 挂载点）。

        兼容字段名：parent_id / org_id / org_ids / group_ids
        """
        ids: List[int] = []
        if not isinstance(params, dict):
            return ids
        for key in ('parent_id', 'org_id'):
            v = params.get(key)
            if isinstance(v, int):
                ids.append(v)
        for key in ('org_ids', 'group_ids'):
            v = params.get(key)
            if isinstance(v, (list, tuple)):
                ids.extend(x for x in v if isinstance(x, int))
        return ids
