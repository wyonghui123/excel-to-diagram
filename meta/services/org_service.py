# -*- coding: utf-8 -*-
"""
组织服务

提供组织的业务方法（成员管理、层级查询、委托授权、权限聚合、迁移）。
主表 CRUD 已 Sunset（P8 2026-06-05），由 BO 框架 v2/bo/org 端点提供。

v1.4 P8 Sunset 后保留 13 个业务方法：
  - get_org_by_code (唯一主表方法，被业务方法间接调用)
  - get_org_members / get_user_orgs / add_member / remove_member / is_member / is_org_manager
  - get_child_orgs / get_all_descendant_orgs / get_all_ancestor_orgs / get_org_tree
  - get_managed_orgs / can_manage_user / get_manageable_users
  - get_org_permission_sets / add_org_permission_set / remove_org_permission_set / set_org_permission_sets / get_permission_sets_not_in_org
  - get_user_effective_data_permissions_via_orgs
  - migrate_org_data_permissions_to_roles

v1.4 P8 已删除 5 个 @deprecated 主表 CRUD 方法：
  - get_all_groups / get_group / create_group / update_group / delete_group
"""

from typing import List, Dict, Any, Optional


# [2026-08-30 权限预览] 数据权限资源类型 → 物理表，用于把 `id IN (...)` 解析成资源名
PREVIEW_RESOURCE_TABLE_MAP = {
    'product': 'products',
    'version': 'versions',
    'domain': 'domains',
    'sub_domain': 'sub_domains',
    'service_module': 'service_modules',
    'business_object': 'business_objects',
}
# [2026-08-30 权限预览] 权限级别中文化（read/write/admin/none）
PREVIEW_LEVEL_ZH = {
    'read': '只读',
    'write': '编辑',
    'admin': '管理',
    'none': '无',
}


class OrgService:
    def __init__(self, ds):
        self.ds = ds

    def _rows_to_dicts(self, cursor) -> List[Dict[str, Any]]:
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def _get_object(self, object_id: int) -> Optional[Dict[str, Any]]:
        """获取对象数据（用于审计日志）

        P8 Sunset: get_group 已删除，这里使用 BO 框架的查询
        但保留方法签名（兼容可能的 @audit_log 装饰器使用）
        """
        cursor = self.ds.execute(
            "SELECT * FROM orgs WHERE id = ?", [object_id]
        )
        rows = self._rows_to_dicts(cursor)
        return rows[0] if rows else None

    # ========== 组织 CRUD ==========
    # v1.4 P8 Sunset (2026-06-05): 5 个 @deprecated 主表 CRUD 方法已删除
    # 替代方案：
    #   - get_all_groups/get_group: BO 框架 v2/bo/org 端点
    #   - create_group/update_group: BO 框架 v2/bo/org POST/PUT
    #   - delete_group: DeletionService (meta/services/deletion_service.py)

    def get_org_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """根据编码获取组织

        P8 保留：被业务方法 get_managed_orgs 等间接使用
        """
        cursor = self.ds.execute(
            "SELECT * FROM orgs WHERE code = ?", [code]
        )
        rows = self._rows_to_dicts(cursor)
        return rows[0] if rows else None

    # ========== 成员管理 ==========

    def get_org_members(self, org_id: int) -> List[Dict[str, Any]]:
        """获取组织成员"""
        cursor = self.ds.execute(
            """SELECT m.*, u.username, u.display_name, u.email
               FROM org_members m
               LEFT JOIN users u ON m.user_id = u.id
               WHERE m.org_id = ?
               ORDER BY m.is_manager DESC, u.username""",
            [org_id]
        )
        return self._rows_to_dicts(cursor)

    def get_user_orgs(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户所属的组织"""
        cursor = self.ds.execute(
            """SELECT g.*, m.is_manager
               FROM org_members m
               LEFT JOIN orgs g ON m.org_id = g.id
               WHERE m.user_id = ?
               ORDER BY g.name""",
            [user_id]
        )
        return self._rows_to_dicts(cursor)

    def get_user_effective_org_ids(self, user_id: int) -> List[int]:
        """获取用户的有效组织 ID 集合 = 任职全部 org（org_members）∪ 各 org 祖先链（含自身）

        [最小范围 · 组织架构继承] 支撑"父组织挂权限集 → 子组织成员沿祖先链自动获得权限"。
        所有"用户 → 权限集/权限"的口径（功能权限、菜单、数据权限）都应改用本方法返回的
        org ID 集合做 `gr.org_id IN (...)` 过滤，替代原来"仅查直属 org_members.org_id"。
        """
        cursor = self.ds.execute(
            "SELECT DISTINCT org_id FROM org_members WHERE user_id = ?",
            [user_id]
        )
        direct_ids = [row[0] for row in cursor.fetchall()]
        effective = set(direct_ids)
        for org_id in direct_ids:
            effective.update(self.get_all_ancestor_orgs(org_id))
        return sorted(effective)

    def get_org_subtree_user_ids(self, org_id: int) -> List[int]:
        """获取组织自身 + 全部子孙组织的成员用户 ID（权限变更后用于失效令牌 bump）"""
        org_ids = [org_id] + self.get_all_descendant_orgs(org_id)
        if not org_ids:
            return []
        placeholders = ','.join('?' * len(org_ids))
        cursor = self.ds.execute(
            f"SELECT DISTINCT user_id FROM org_members WHERE org_id IN ({placeholders})",
            org_ids
        )
        return [row[0] for row in cursor.fetchall()]

    def add_member(self, org_id: int, user_id: int, is_manager: bool = False) -> bool:
        """添加成员到组织"""
        try:
            self.ds.execute(
                """INSERT OR REPLACE INTO org_members (user_id, org_id, is_manager)
                   VALUES (?, ?, ?)""",
                [user_id, org_id, 1 if is_manager else 0]
            )
            return True
        except Exception:
            return False

    def remove_member(self, org_id: int, user_id: int) -> bool:
        """从组织移除成员"""
        try:
            self.ds.execute(
                "DELETE FROM org_members WHERE org_id = ? AND user_id = ?",
                [org_id, user_id]
            )
            return True
        except Exception:
            return False

    def is_member(self, org_id: int, user_id: int) -> bool:
        """检查用户是否为组成员"""
        cursor = self.ds.execute(
            "SELECT 1 FROM org_members WHERE org_id = ? AND user_id = ?",
            [org_id, user_id]
        )
        return cursor.fetchone() is not None

    def is_org_manager(self, org_id: int, user_id: int) -> bool:
        """检查用户是否为组管理员"""
        cursor = self.ds.execute(
            "SELECT is_manager FROM org_members WHERE org_id = ? AND user_id = ?",
            [org_id, user_id]
        )
        row = cursor.fetchone()
        return row and row[0] == 1

    # ========== 层级查询 ==========

    def get_child_orgs(self, org_id: int) -> List[Dict[str, Any]]:
        """获取子组织"""
        cursor = self.ds.execute(
            "SELECT * FROM orgs WHERE parent_id = ? ORDER BY name",
            [org_id]
        )
        return self._rows_to_dicts(cursor)

    def get_all_descendant_orgs(self, org_id: int) -> List[int]:
        """获取所有子孙组织ID（递归）"""
        descendants = []
        children = self.get_child_orgs(org_id)
        for child in children:
            descendants.append(child['id'])
            descendants.extend(self.get_all_descendant_orgs(child['id']))
        return descendants

    def get_all_ancestor_orgs(self, org_id: int) -> List[int]:
        """获取所有祖先组织ID（递归）

        P10 修复: 添加循环检测，防止数据库被破坏（自引用/环路）时栈溢出
        """
        ancestors = []
        visited = set()
        # P9 修复: get_group 已 Sunset，使用 _get_object 代替
        current_id = org_id
        while current_id is not None:
            if current_id in visited:
                # 检测到循环，停止防止栈溢出
                break
            visited.add(current_id)
            group = self._get_object(current_id)
            if not group:
                break
            parent_id = group.get('parent_id')
            if parent_id is None:
                break
            ancestors.append(parent_id)
            current_id = parent_id
        return ancestors

    def get_org_tree(self) -> List[Dict[str, Any]]:
        """获取组织树形结构

        P9 修复: get_all_groups 已 Sunset，使用 SQL 直接查询代替
        """
        cursor = self.ds.execute(
            "SELECT id, name, code, parent_id, manager_id, description, created_at "
            "FROM orgs ORDER BY parent_id, name"
        )
        all_groups = self._rows_to_dicts(cursor)
        group_map = {g['id']: g for g in all_groups}
        
        for group in all_groups:
            group['children'] = []
        
        roots = []
        for group in all_groups:
            parent_id = group.get('parent_id')
            if parent_id and parent_id in group_map:
                group_map[parent_id]['children'].append(group)
            else:
                roots.append(group)
        
        return roots

    # ========== 委托管理 ==========

    def get_managed_orgs(self, user_id: int) -> List[int]:
        """获取用户可管理的组织ID列表"""
        managed = set()
        
        # 1. 用户是组管理员的组
        cursor = self.ds.execute(
            "SELECT org_id FROM org_members WHERE user_id = ? AND is_manager = 1",
            [user_id]
        )
        for row in cursor.fetchall():
            managed.add(row[0])
            # 包含所有子孙组
            managed.update(self.get_all_descendant_orgs(row[0]))
        
        # 2. 用户是组 manager_id 的组
        cursor = self.ds.execute(
            "SELECT id FROM orgs WHERE manager_id = ?", [user_id]
        )
        for row in cursor.fetchall():
            managed.add(row[0])
            managed.update(self.get_all_descendant_orgs(row[0]))
        
        return list(managed)

    def can_manage_user(self, operator_id: int, target_id: int, has_all_permission: bool = False) -> bool:
        """检查操作者是否有权管理目标用户"""
        if has_all_permission:
            return True
        
        managed_groups = set(self.get_managed_orgs(operator_id))
        if not managed_groups:
            return False
        
        target_groups = set()
        cursor = self.ds.execute(
            "SELECT org_id FROM org_members WHERE user_id = ?", [target_id]
        )
        for row in cursor.fetchall():
            target_groups.add(row[0])
        
        return bool(managed_groups & target_groups)

    def get_manageable_users(self, operator_id: int, has_all_permission: bool = False) -> List[int]:
        """获取操作者可管理的用户ID列表"""
        if has_all_permission:
            cursor = self.ds.execute("SELECT id FROM users WHERE status = 'active'")
            return [row[0] for row in cursor.fetchall()]

        managed_groups = self.get_managed_orgs(operator_id)
        if not managed_groups:
            return []

        placeholders = ','.join(['?' for _ in managed_groups])
        cursor = self.ds.execute(
            f"SELECT DISTINCT user_id FROM org_members WHERE org_id IN ({placeholders})",
            managed_groups
        )
        return [row[0] for row in cursor.fetchall()]

    # ========== 组织-角色关联（核心重构：组织通过角色获得数据权限） ==========

    def get_org_permission_sets(self, org_id: int) -> List[Dict[str, Any]]:
        """获取组织关联的角色列表"""
        cursor = self.ds.execute(
            """SELECT gr.id, gr.permission_set_id, r.code, r.name, r.description, r.priority, r.is_system,
                      gr.created_at
               FROM org_permission_sets gr
               INNER JOIN permission_sets r ON gr.permission_set_id = r.id
               WHERE gr.org_id = ?
               ORDER BY r.priority DESC, r.name""",
            [org_id]
        )
        return self._rows_to_dicts(cursor)

    def add_org_permission_set(self, org_id: int, permission_set_id: int, created_by: int = None) -> bool:
        """为组织添加角色关联"""
        try:
            self.ds.execute(
                """INSERT OR IGNORE INTO org_permission_sets (org_id, permission_set_id, created_by)
                   VALUES (?, ?, ?)""",
                [org_id, permission_set_id, created_by]
            )
            return True
        except Exception:
            return False

    def remove_org_permission_set(self, org_id: int, permission_set_id: int) -> bool:
        """移除组织的角色关联"""
        try:
            self.ds.execute(
                "DELETE FROM org_permission_sets WHERE org_id = ? AND permission_set_id = ?",
                [org_id, permission_set_id]
            )
            return True
        except Exception:
            return False

    def set_org_permission_sets(self, org_id: int, role_ids: List[int], created_by: int = None) -> bool:
        """批量设置组织角色（全量替换）"""
        try:
            self.ds.execute("DELETE FROM org_permission_sets WHERE org_id = ?", [org_id])
            for permission_set_id in role_ids:
                self.ds.execute(
                    "INSERT INTO org_permission_sets (org_id, permission_set_id, created_by) VALUES (?, ?, ?)",
                    [org_id, permission_set_id, created_by]
                )
            return True
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False

    def get_permission_sets_not_in_org(self, org_id: int) -> List[Dict[str, Any]]:
        """获取未关联到该组织的角色列表"""
        cursor = self.ds.execute(
            """SELECT id, code, name, description, priority, is_system
               FROM permission_sets
               WHERE id NOT IN (SELECT permission_set_id FROM org_permission_sets WHERE org_id = ?)
               ORDER BY priority DESC, name""",
            [org_id]
        )
        return self._rows_to_dicts(cursor)

    def get_user_effective_data_permissions_via_orgs(self, user_id: int) -> List[Dict[str, Any]]:
        """
        获取用户通过 组织→角色 链路获得的间接数据权限

        重构后的权限解析路径：
        User → UserGroup → Role → DataPermission
        [最小范围] 用户有效组织含祖先链，父组织挂权限集 → 子成员一并继承
        """
        org_ids = self.get_user_effective_org_ids(user_id)
        if not org_ids:
            return []
        placeholders = ','.join('?' * len(org_ids))
        cursor = self.ds.execute(f"""
            SELECT DISTINCT rdp.* FROM permission_set_data_permissions rdp
            INNER JOIN org_permission_sets gr ON rdp.permission_set_id = gr.permission_set_id
            WHERE gr.org_id IN ({placeholders})
            ORDER BY rdp.resource_type, rdp.resource_id
        """, org_ids)
        return self._rows_to_dicts(cursor)

    # ========== 权限预览聚合内核（org/user 共用） ==========

    def get_org_name(self, org_id: int) -> str:
        """取组织名称（缺失返回空串）"""
        cursor = self.ds.execute("SELECT name FROM orgs WHERE id = ?", [org_id])
        row = cursor.fetchone()
        return row[0] if row else ''

    def _ancestor_chain(self, org_id: int) -> List[Dict[str, Any]]:
        """构造 [本org, 父, 祖父...] 链，relation 标 direct/inherited，depth 根=0 向上递增。

        沿用 get_all_ancestor_orgs 的循环防护。
        """
        chain = [{'org_id': org_id, 'relation': 'direct', 'depth': 0}]
        for depth, aid in enumerate(self.get_all_ancestor_orgs(org_id), start=1):
            chain.append({'org_id': aid, 'relation': 'inherited', 'depth': depth})
        return chain

    def _get_set_permissions(self, ps_id: int) -> List[Dict[str, Any]]:
        """权限集内权限明细（含 granted=false 用于"排除"标注）"""
        cursor = self.ds.execute(
            """SELECT p.id AS permission_id, p.code AS permission_code,
                      p.name AS permission_name, psp.granted AS granted
               FROM permission_set_permissions psp
               INNER JOIN permissions p ON psp.permission_id = p.id
               WHERE psp.permission_set_id = ?
               ORDER BY p.code""",
            [ps_id]
        )
        return self._rows_to_dicts(cursor)

    def _get_org_permission_sets(self, org_id: int) -> List[Dict[str, Any]]:
        """获取组织关联权限集（预览专用，只取现存列）。

        不复用 get_org_permission_sets：该共享方法仍引用 Spec16 迁移已删除的 r.priority 列，
        此处仅选取 permission_sets 现存的 code/name/description/is_system。
        """
        cursor = self.ds.execute(
            """SELECT r.id AS permission_set_id, r.code, r.name, r.description, r.is_system
               FROM org_permission_sets gr
               INNER JOIN permission_sets r ON gr.permission_set_id = r.id
               WHERE gr.org_id = ?
               ORDER BY r.name""",
            [org_id]
        )
        return self._rows_to_dicts(cursor)

    def _resolve_resource_names(self, resource_type: str, ids: List[str]) -> List[str]:
        """把 `id IN (n1, n2...)` 的 ID 列表解析成资源名称（用于权限预览中文化）。"""
        table = PREVIEW_RESOURCE_TABLE_MAP.get(resource_type)
        if not table:
            return []
        id_list = [x.strip().strip("'\"") for x in ids if x.strip()]
        num_list = [x for x in id_list if x.isdigit()]
        if not num_list:
            return []
        placeholders = ','.join('?' * len(num_list))
        try:
            cursor = self.ds.execute(
                f"SELECT name FROM {table} WHERE id IN ({placeholders})",
                [int(x) for x in num_list]
            )
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []

    def _humanize_condition(self, resource_type: str, condition: str) -> str:
        """把数据范围条件表达式转成人类可读中文描述，避免英文/JSON 裸显。

        示例:
          '*' 或 ''          -> '全部数据'
          owner_id = ${user.id} -> '仅本人创建的数据'
          status = "active"      -> '状态为 active'
          version_id = 1         -> '版本 ID = 1'
          id IN (16, 17)         -> '仅以下资源：<资源名...>' (解析成名称)
          {"domain_id": 1}       -> '域 ID = 1' (JSON 容错)
        """
        if condition is None:
            return ''
        c = str(condition).strip()
        if c in ('', '*', '{}'):
            return '全部数据'
        # JSON 容错: {"field": val} 或 {"field=val"} 形态
        if c.startswith('{') and c.endswith('}'):
            inner = c[1:-1].strip()
            if ':' in inner:
                k, v = inner.split(':', 1)
                return f'{k.strip()} = {v.strip().strip(chr(34))}'
            return inner.strip()
        # [2026-08-30] id IN (...) → 解析成资源名称（picker 常用）
        if c.startswith('id '):
            import re
            m = re.match(r'^id\s+IN\s*\(([^)]*)\)\s*$', c, re.IGNORECASE)
            if m:
                ids = [x.strip().strip("'\"") for x in m.group(1).split(',') if x.strip()]
                names = self._resolve_resource_names(resource_type, ids)
                if names:
                    return '仅以下资源：' + '、'.join(names)
                return '仅以下资源（ID）：' + '、'.join(ids)
        # 常见 owner 语义
        if 'owner_id =' in c and '${user.id}' in c:
            return '仅本人创建的数据'
        if 'owner_id =' in c:
            return f'仅本人创建的数据 ({c})'
        # 通用: condition -> 中文
        kw_map = {
            'status =': '状态为',
            'is_active': '启用',
            'version_id =': '版本 ID =',
            'domain_id =': '域 ID =',
            'domain_code =': '域编码 =',
            'parent_id =': '上级 ID =',
            'org_id =': '组织 ID =',
            '=': '等于',
        }
        # 首先生成替换表达式
        replaced = c
        for src, zh in kw_map.items():
            if src in replaced:
                replaced = replaced.replace(src, zh)
                break
        return replaced

    def _humanize_resource_type(self, resource_type: str) -> str:
        mapping = {
            '*': '全部资源',
            'product': '产品',
            'version': '版本',
            'domain': '领域',
            'sub_domain': '子领域',
            'business_object': '业务对象',
            'service_module': '服务模块',
            'user': '用户',
            'org': '组织',
            'role': '角色',
        }
        return mapping.get(resource_type, resource_type)

    def get_permission_preview(self, identity_type: str, identity_id: int) -> Dict[str, Any]:
        """权限预览聚合内核：返回 org 或 user 的有效权限全集（含继承与来源）。

        复用主张：org/user 两入口共享本方法，仅根集合来源不同：
        - org  : 根 = [org_id]，链 = _ancestor_chain（本组织优先，取最深 depth 小者）
        - user : 根 = get_user_effective_org_ids（直属+祖先，天然去重，跨 root 用 sources 平铺）
        只读聚合，无任何全量回退。
        """
        if identity_type == 'org':
            chain = self._ancestor_chain(identity_id)
            root_org_ids = [identity_id]
        elif identity_type == 'user':
            root_org_ids = self.get_user_effective_org_ids(identity_id)
            chain = [{'org_id': oid, 'relation': 'direct', 'depth': 0} for oid in root_org_ids]
        else:
            raise ValueError(f"unknown identity_type: {identity_type}")

        identity_name = self.get_org_name(identity_id) if identity_type == 'org' else ''

        ps_map = {}     # ps_id -> merged permission_set
        dp_map = {}     # (resource_type, resource_id, level) -> merged data_permission

        for node in chain:
            org_id = node['org_id']
            org_name = self.get_org_name(org_id)
            for ps in self._get_org_permission_sets(org_id):
                ps_id = ps['permission_set_id']
                src = {'org_id': org_id, 'org_name': org_name, 'relation': node['relation']}
                merged = ps_map.get(ps_id)
                if merged is None:
                    ps_map[ps_id] = {
                        'permission_set_id': ps_id,
                        'permission_set_code': ps.get('code'),
                        'permission_set_name': ps.get('name'),
                        'description': ps.get('description'),
                        'is_system': bool(ps.get('is_system')),
                        'granted': True,
                        '_depth': node['depth'],
                        'source_orgs': [src],
                        'permissions': self._get_set_permissions(ps_id),
                    }
                else:
                    # org 单根链：仅当更浅（depth 更小）时替换为最深层来源
                    if identity_type == 'org' and node['depth'] < merged['_depth']:
                        merged['_depth'] = node['depth']
                        merged['source_orgs'] = [src]
                        merged['permissions'] = self._get_set_permissions(ps_id)
                    # user 多根：平铺 sources
                    if identity_type == 'user' and src not in merged['source_orgs']:
                        merged['source_orgs'].append(src)

        # 数据权限聚合：跨有效权限集去重。
        # [FIX 2026-08-30] 权限集"数据范围/数据权限"实际写入 permission_rules (条件式, condition 字段)；
        # 旧表 permission_set_data_permissions (resource_id 式) 仅作兼容兜底。
        for node in chain:
            org_id = node['org_id']
            org_name = self.get_org_name(org_id)
            for ps in self._get_org_permission_sets(org_id):
                ps_id = ps['permission_set_id']
                ps_name = ps.get('name') or ps.get('code')
                src = {
                    'org_id': org_id,
                    'org_name': org_name,
                    'permission_set_name': ps_name,
                }
                # 主来源：data_permission_rules (统一权限规则, P11 表, 含中文 condition_display)
                # [FIX 2026-08-30 v2] 之前误读 permission_rules(旧/测试表, 无 condition_display, 有大量脏数据),
                #   导致数据权限为空/英文表达式。改读前端 ConditionRuleDialog 实际写入的 data_permission_rules。
                cursor = self.ds.execute(
                    """SELECT resource_type, condition, condition_display, permission_level, inherit_to_children
                       FROM data_permission_rules
                       WHERE permission_set_id = ?
                         AND (is_denied IS NULL OR is_denied = 0)
                       ORDER BY resource_type, condition""",
                    [ps_id]
                )
                rules = self._rows_to_dicts(cursor)
                for row in rules:
                    condition = row.get('condition') or ''
                    # [FIX 2026-08-30] 优先展示中文可读表达式 condition_display，避免英文/JSON 条件裸显
                    display = row.get('condition_display') or self._humanize_condition(row['resource_type'], condition)
                    rt = self._humanize_resource_type(row['resource_type'])
                    key = ('cond', rt, display, row['permission_level'])
                    if key not in dp_map:
                        dp_map[key] = {
                            'kind': 'condition',
                            'resource_type': rt,
                            'resource_id': display,   # 展示位：中文可读表达式，fallback 到 condition
                            'permission_level': row['permission_level'],
                            'permission_level_display': PREVIEW_LEVEL_ZH.get(row['permission_level'], row['permission_level']),
                            'inherit_to_children': bool(row.get('inherit_to_children')),
                            'sources': [src],
                        }
                    elif src not in dp_map[key]['sources']:
                        dp_map[key]['sources'].append(src)

                # 兼容兜底：旧表 permission_set_data_permissions (resource_id 式)，仅在无条件规则时读取
                if not rules:
                    cursor2 = self.ds.execute(
                        """SELECT resource_type, resource_id, permission_level, inherit_to_children
                           FROM permission_set_data_permissions
                           WHERE permission_set_id = ?
                           ORDER BY resource_type, resource_id""",
                        [ps_id]
                    )
                    for row in self._rows_to_dicts(cursor2):
                        key = ('res_id', row['resource_type'], row['resource_id'], row['permission_level'])
                        if key not in dp_map:
                            dp_map[key] = {
                                'kind': 'resource_id',
                                'resource_type': row['resource_type'],
                                'resource_id': row['resource_id'],
                                'permission_level': row['permission_level'],
                                'permission_level_display': PREVIEW_LEVEL_ZH.get(row['permission_level'], row['permission_level']),
                                'inherit_to_children': bool(row.get('inherit_to_children')),
                                'sources': [src],
                            }
                        elif src not in dp_map[key]['sources']:
                            dp_map[key]['sources'].append(src)

        permission_sets = [ps_map[k] for k in sorted(ps_map)]
        for ps in permission_sets:
            ps.pop('_depth', None)

        return {
            'identity_type': identity_type,
            'identity_id': identity_id,
            'identity_name': identity_name,
            'root_orgs': [{'org_id': oid, 'org_name': self.get_org_name(oid)} for oid in root_org_ids],
            'summary': {
                'permission_set_count': len(permission_sets),
                'source_org_count': len({s['org_id'] for ps in permission_sets for s in ps['source_orgs']}),
                'direct_count': sum(
                    1 for ps in permission_sets
                    if any(s['relation'] == 'direct' for s in ps['source_orgs'])
                ),
                'inherited_count': len(permission_sets) - sum(
                    1 for ps in permission_sets
                    if any(s['relation'] == 'direct' for s in ps['source_orgs'])
                ),
            },
            'permission_sets': permission_sets,
            'data_permissions': list(dp_map.values()),
        }

    # [2026-08-30 融合权限配置] 来源优先级：exclude(拒绝) > include(手动) > auto(菜单) > derived(维度) > owner_auto
    _FUSED_SRC_RANK = {
        'exclude': 5,
        'include': 4,
        'auto': 3,
        'manual': 3,
        'derived': 2,
        'owner_auto': 1,
    }

    def _fused_merge_cell(self, cur, new):
        """合并单个 (resource_type, action) 单元格：
        - 任一权限集 exclude（Deny 优先）→ 整体拒绝
        - 否则任一权限集授予 → granted=True，source 取优先级最高者
        """
        if new.get('source') == 'exclude':
            return {'granted': False, 'source': 'exclude'}
        if cur is None:
            return dict(new)
        if cur.get('source') == 'exclude':
            return cur
        if cur.get('granted') or new.get('granted'):
            a_rank = self._FUSED_SRC_RANK.get(new.get('source', ''), 0)
            b_rank = self._FUSED_SRC_RANK.get(cur.get('source', ''), 0)
            src = new.get('source') if a_rank > b_rank else cur.get('source')
            return {'granted': True, 'source': src}
        return cur

    def _build_ps_data_scope(self, ps) -> Dict[str, Dict[str, Any]]:
        """单个权限集的数据范围（按 resource_type 聚合），供融合矩阵聚类拆行 + 行级展示。

        返回 { resource_type: { __configured, __expression, __expression_display, __rules } }
        __rules 每条含 condition / condition_display / permission_level 等，均中文可读。
        """
        ps_id = ps['permission_set_id']
        ps_name = ps.get('permission_set_name') or ps.get('permission_set_code')
        org_names = sorted({s.get('org_name') for s in ps.get('source_orgs', []) if s.get('org_name')})
        scope: Dict[str, Dict[str, Any]] = {}

        cursor = self.ds.execute(
            """SELECT resource_type, condition, condition_display, permission_level, inherit_to_children
               FROM data_permission_rules
               WHERE permission_set_id = ?
                 AND (is_denied IS NULL OR is_denied = 0)
               ORDER BY resource_type, condition""",
            [ps_id],
        )
        rules = self._rows_to_dicts(cursor)
        if not rules:
            # 兼容兜底：旧表 resource_id 式
            cursor2 = self.ds.execute(
                """SELECT resource_type, resource_id, permission_level, inherit_to_children
                   FROM permission_set_data_permissions
                   WHERE permission_set_id = ?
                   ORDER BY resource_type, resource_id""",
                [ps_id],
            )
            for row in self._rows_to_dicts(cursor2):
                rt = row['resource_type']
                names = self._resolve_resource_names(rt, [str(row['resource_id'])]) or [str(row['resource_id'])]
                display = '仅以下资源：' + '、'.join(names)
                entry = scope.setdefault(rt, {'__configured': False, '__expressions': [], '__displays': [], '__rules': []})
                entry['__configured'] = True
                if display not in entry['__expressions']:
                    entry['__expressions'].append(display)
                entry['__displays'].append(display)
                # [2026-08-30 元数据驱动] 结构化值名（前端按钮摘要直接用，不解析 display 字符串）
                entry.setdefault('__value_names', [])
                for n in names:
                    if n not in entry['__value_names']:
                        entry['__value_names'].append(n)
                entry['__rules'].append({
                    'condition': '',
                    'condition_display': display,
                    'permission_level': row.get('permission_level'),
                    'permission_level_display': PREVIEW_LEVEL_ZH.get(row.get('permission_level'), row.get('permission_level')),
                    'inherit_to_children': bool(row.get('inherit_to_children')),
                    'source_orgs': org_names,
                    'source_permission_set': ps_name,
                })
            for rt, e in scope.items():
                e['__expression'] = ' AND '.join(e['__expressions'])
                e['__expression_display'] = '；'.join(e['__displays'] or e['__expressions'])
                e['__scope_value_names'] = e.pop('__value_names', [])
                e.pop('__expressions', None)
                e.pop('__displays', None)
            return scope

        for row in rules:
            rt = row['resource_type']
            condition = (row.get('condition') or '').strip()
            display = row.get('condition_display') or self._humanize_condition(rt, condition)
            entry = scope.setdefault(rt, {'__configured': False, '__expressions': [], '__displays': [], '__rules': [], '__value_names': []})
            entry['__configured'] = True
            # [FIX 2026-08-30] __expression 必须存「可反解析的技术表达式」：
            #   此前误把中文 display（如「仅以下资源：供应链云」）存入 __expression，
            #   导致权限预览「查看条件」弹窗 parseConditionToRuleRows 解析失败，
            #   回退高级模式 → 字段/操作符/值全部空白（看不到 names）。
            #   无真实表达式（condition 为空，如「全部数据」）时用 display 兜底，
            #   保持 __configured 状态可被前端识别（按钮不退回「未配置」）。
            expr = condition if condition else display
            if expr not in entry['__expressions']:
                entry['__expressions'].append(expr)
            if display and display not in entry['__displays']:
                entry['__displays'].append(display)
            # [2026-08-30 元数据驱动] 结构化值名：从 id IN (...) 解析出值名列表
            #   （前端按钮摘要直接消费，不再正则解析 display 中文文案）
            import re as _re
            vm = _re.match(r'^id\s+IN\s*\(([^)]*)\)\s*$', condition, _re.IGNORECASE) if condition else None
            if vm:
                ids = [x.strip().strip("'\"") for x in vm.group(1).split(',') if x.strip()]
                names = self._resolve_resource_names(rt, ids) or []
                for n in names:
                    if n not in entry['__value_names']:
                        entry['__value_names'].append(n)
            entry['__rules'].append({
                'condition': condition,
                'condition_display': display,
                'permission_level': row.get('permission_level'),
                'permission_level_display': PREVIEW_LEVEL_ZH.get(row.get('permission_level'), row.get('permission_level')),
                'inherit_to_children': bool(row.get('inherit_to_children')),
                'source_orgs': org_names,
                'source_permission_set': ps_name,
            })
        for rt, e in scope.items():
            e['__expression'] = ' AND '.join(e['__expressions'])
            e['__expression_display'] = '；'.join(e['__displays'] or e['__expressions'])
            e['__scope_value_names'] = e.pop('__value_names', [])
            e.pop('__expressions', None)
            e.pop('__displays', None)
        return scope

    def get_fused_permission_config(self, identity_type: str, identity_id: int) -> Dict[str, Any]:
        """融合权限配置快照：把 org/user 下所有有效权限集合并为「完整的一份」——
        菜单权限并集 + 资源×功能权限矩阵并集（含数据范围列）+ 数据范围并集。

        供「权限预览」tab 以单份权限配置形态展示（复用菜单树/矩阵组件，全中文）。
        只读聚合，无任何全量回退。
        """
        preview = self.get_permission_preview(identity_type, identity_id)
        ps_list = preview.get('permission_sets') or []
        ps_ids = [ps['permission_set_id'] for ps in ps_list]

        # ============ 1. 菜单权限并集（assigned / granted 取并集） ============
        from meta.api.permission_set_menu_api import _build_role_unified_data, _derive_bo_permission_groups
        menus_by_code: Dict[str, Dict[str, Any]] = {}
        menu_ps_sources: Dict[str, List[str]] = {}  # menu_code -> 来源权限集名（assigned 的 ps）
        for ps in ps_list:
            ps_id = ps['permission_set_id']
            ps_name = ps.get('permission_set_name') or ps.get('permission_set_code') or f'权限集{ps_id}'
            ud = _build_role_unified_data(ps_id)
            if not ud or not ud.get('menus'):
                continue
            for m in ud['menus']:
                code = m.get('menu_code')
                if not code:
                    continue
                # [2026-08-30] 记录来源权限集（仅已分配的 ps），供只读态菜单展示来源
                if m.get('assigned') and ps_name not in menu_ps_sources.setdefault(code, []):
                    menu_ps_sources[code].append(ps_name)
                base = menus_by_code.get(code)
                if base is None:
                    base = dict(m)
                    base['required_permissions'] = [dict(p) for p in (m.get('required_permissions') or [])]
                    base['data_scope'] = [
                        {**rt, 'permissions': [dict(p) for p in (rt.get('permissions') or [])]}
                        for rt in (m.get('data_scope') or [])
                    ]
                    menus_by_code[code] = base
                    continue
                base['assigned'] = bool(base.get('assigned')) or bool(m.get('assigned'))
                # required_permissions 按 code 合并 granted
                perm_map = {p['code']: p for p in base['required_permissions']}
                for p in (m.get('required_permissions') or []):
                    cur = perm_map.get(p['code'])
                    if cur is None:
                        cp = dict(p)
                        base['required_permissions'].append(cp)
                        perm_map[p['code']] = cp
                    elif p.get('granted') and not cur.get('granted'):
                        cur['granted'] = True
                        cur['source'] = p.get('source') or 'auto'
                # data_scope 按 resource_type 合并（去重 resource_id）
                scope_map = {rt.get('resource_type'): rt for rt in base['data_scope']}
                for rt in (m.get('data_scope') or []):
                    cur = scope_map.get(rt.get('resource_type'))
                    if cur is None:
                        base['data_scope'].append({**rt, 'permissions': [dict(p) for p in (rt.get('permissions') or [])]})
                    else:
                        rids = {p.get('resource_id') for p in cur['permissions']}
                        for p in rt.get('permissions') or []:
                            if p.get('resource_id') not in rids:
                                cur['permissions'].append(dict(p))
                                rids.add(p.get('resource_id'))
        # 合并后按已分配的 required_permissions 重新推导 bo_permission_groups
        menus = []
        for code in menus_by_code:
            base = menus_by_code[code]
            base['bo_permission_groups'] = _derive_bo_permission_groups(
                base.get('bo_bindings'), base['required_permissions'], base.get('assigned', False)
            )
            base['has_data_scope'] = any(rt.get('permissions') for rt in base.get('data_scope') or [])
            base['source_ps_names'] = menu_ps_sources.get(code, [])  # [2026-08-30] 只读态来源权限集
            menus.append(base)

        # ============ 2. 资源×功能权限矩阵并集（聚类合并） ============
        # [FIX 2026-08-30] _build_role_matrices 依赖 permission_dimension_api 模块级 _data_source，
        #   从 service 直接调用时可能未初始化（返回 None），需先 _get_engine() 完成初始化。
        from meta.api import permission_dimension_api as _pda
        from meta.api.permission_dimension_api import _build_role_matrices
        if not _pda._data_source:
            _pda._get_engine()
        columns = _pda._matrix_action_columns()

        # 2.0 预取每个权限集的数据范围（按 resource_type），用于聚类拆行 + 行级 row_scope
        ps_scope: Dict[int, Dict[str, Dict[str, Any]]] = {
            ps['permission_set_id']: self._build_ps_data_scope(ps) for ps in ps_list
        }

        # 2.1 收集每个权限集对每个资源类型的行
        per_rt: Dict[str, List[Dict[str, Any]]] = {}
        row_label: Dict[str, str] = {}
        row_order: List[str] = []
        row_seen = set()
        for ps in ps_list:
            ps_id = ps['permission_set_id']
            ps_name = ps.get('permission_set_name') or ps.get('permission_set_code')
            rm = _build_role_matrices(ps_id, columns=columns)
            if not rm:
                continue
            for row in rm.get('resources', []):
                rt = row.get('resource_type')
                if not rt:
                    continue
                if rt not in row_seen:
                    row_seen.add(rt)
                    row_order.append(rt)
                    row_label[rt] = row.get('label', rt)
                cells = {}
                for action, cell in (row.get('cells') or {}).items():
                    if not cell or not cell.get('source'):
                        continue
                    cells[action] = {'granted': bool(cell.get('granted')), 'source': cell.get('source', '')}
                per_rt.setdefault(rt, []).append({'ps_id': ps_id, 'ps_name': ps_name, 'cells': cells})

        # 2.2 聚类：功能权限模式 + 数据范围模式均相同的行合并；
        #     任一不同（功能权限不同 / 数据权限不同）→ 拆成多行同资源展示，不强行并成一行。
        def _row_sig(cells, scope_entry):
            granted = tuple(sorted((a, bool(c.get('granted'))) for a, c in cells.items()))
            return (granted, (scope_entry or {}).get('__expression') or '')

        resources = []
        for rt in row_order:
            groups: Dict[tuple, Dict[str, Any]] = {}
            group_order: List[tuple] = []
            for entry in per_rt.get(rt, []):
                scope_entry = (ps_scope.get(entry['ps_id']) or {}).get(rt)
                sig = _row_sig(entry['cells'], scope_entry)
                if sig not in groups:
                    groups[sig] = {
                        'resource_type': rt,
                        'label': row_label.get(rt, rt),
                        'cells': {a: dict(c) for a, c in entry['cells'].items()},
                        'row_scope': scope_entry or None,
                        'ps_names': [entry['ps_name']],
                    }
                    group_order.append(sig)
                else:
                    g = groups[sig]
                    if entry['ps_name'] not in g['ps_names']:
                        g['ps_names'].append(entry['ps_name'])
                    for a, c in entry['cells'].items():
                        cur = g['cells'].get(a)
                        g['cells'][a] = cur if cur is None else self._fused_merge_cell(cur, c)
            for sig in group_order:
                g = groups[sig]
                actions = set(columns)
                actions.update(g['cells'].keys())
                g['cells'] = {
                    a: {'granted': bool(c and c.get('granted')), 'source': (c or {}).get('source', '')}
                    for a, c in ((a, g['cells'].get(a)) for a in actions)
                }
                resources.append(g)

        # 2.2.5 覆盖消解（effective permission 语义）：
        #   拆行后，若某行 A 被同资源的另一行 B 完全覆盖（功能 granted 子集 + 数据范围包含），
        #   则 A 不带来任何增量权限 → 隐藏 A，只保留覆盖面最大的行。
        #   [2026-08-30] 对齐 Salesforce Permission Set / AWS IAM effective permission 语义：
        #     权限有效值 = 所有来源并集，被完全覆盖的授权不产生增量，不应以独立行展示。
        def _scope_covers(super_scope, sub_scope) -> bool:
            """sub_scope 是否 ⊆ super_scope（None=无限制=全集；有限制时仅表达式相同才判包含，保守避免误伤）"""
            ss = (super_scope or {}).get('__expression')
            ts = (sub_scope or {}).get('__expression')
            if ts is None:
                return ss is None
            if ss is None:
                return True
            return ss == ts

        def _row_covers(super_row, sub_row) -> bool:
            """super_row 是否覆盖 sub_row：sub 每个 granted 动作在 super 中也 granted，且 sub 范围 ⊆ super 范围"""
            sc, tc = super_row.get('cells', {}), sub_row.get('cells', {})
            for a, c in tc.items():
                if c.get('granted') and not (sc.get(a) or {}).get('granted'):
                    return False
            return _scope_covers(super_row.get('row_scope'), sub_row.get('row_scope'))

        resources = [
            row for row in resources
            if not any(
                other is not row
                and other.get('resource_type') == row.get('resource_type')
                and _row_covers(other, row)
                for other in resources
            )
        ]

        # 2.3 sources_detail（合并去重）
        sources_detail = []
        source_seen = set()
        for ps in ps_list:
            rm = _build_role_matrices(ps['permission_set_id'], columns=columns)
            if not rm:
                continue
            for sd in rm.get('sources_detail', []):
                dedupe = (sd.get('resource_type'), sd.get('action'), sd.get('source'))
                if dedupe not in source_seen:
                    source_seen.add(dedupe)
                    sources_detail.append(sd)
        fused_matrix = {
            'permission_set_ids': [ps['permission_set_id'] for ps in ps_list],
            'columns': columns,
            'resources': resources,
            'sources_detail': sources_detail,
        }

        # ============ 3. 数据范围聚合（scope_matrix，按 rt 并集，供矩阵「数据范围」列兼容回退） ============
        scope_matrix: Dict[str, Dict[str, Any]] = {}
        for ps in ps_list:
            for rt, e in (ps_scope.get(ps['permission_set_id']) or {}).items():
                entry = scope_matrix.setdefault(rt, {'__configured': False, '__expressions': [], '__displays': [], '__rules': [], '__value_names': []})
                entry['__configured'] = True
                expr = e.get('__expression')
                if expr and expr not in entry['__expressions']:
                    entry['__expressions'].append(expr)
                disp = e.get('__expression_display')
                if disp and disp not in entry['__displays']:
                    entry['__displays'].append(disp)
                # [2026-08-30 元数据驱动] 搬运结构化值名（前端按钮摘要消费，不解析 display 字符串）
                for n in e.get('__scope_value_names', []):
                    if n not in entry['__value_names']:
                        entry['__value_names'].append(n)
                for r in e.get('__rules', []):
                    entry['__rules'].append(dict(r))
        for rt, e in scope_matrix.items():
            e['__expression'] = ' AND '.join(e['__expressions'])
            e['__expression_display'] = '；'.join(e['__displays'] or e['__expressions'])
            e['__scope_value_names'] = e.pop('__value_names', [])
            e.pop('__expressions', None)
            e.pop('__displays', None)

        # ============ 4. 继承链（org 沿祖先链 / user 多根平铺） ============
        # [2026-08-30] 供前端按「本组织 → 各级父组织」分组展示来源权限集（对象 merge pattern 的应用）
        if identity_type == 'org':
            org_chain = [
                {
                    'org_id': n['org_id'],
                    'org_name': self.get_org_name(n['org_id']),
                    'relation': n['relation'],
                    'depth': n['depth'],
                }
                for n in self._ancestor_chain(identity_id)
            ]
        else:
            org_chain = [
                {'org_id': r['org_id'], 'org_name': r['org_name'], 'relation': 'direct', 'depth': 0}
                for r in (preview.get('root_orgs') or [])
            ]

        return {
            'identity_type': identity_type,
            'identity_id': identity_id,
            'summary': preview.get('summary'),
            'org_chain': org_chain,
            'permission_sets': [{
                'permission_set_id': ps['permission_set_id'],
                'permission_set_code': ps.get('permission_set_code'),
                'permission_set_name': ps.get('permission_set_name'),
                'is_system': ps.get('is_system'),
                # [2026-08-30] 透传来源组织（org_name/relation），供汇总区继承链分组
                'source_orgs': ps.get('source_orgs') or [],
            } for ps in ps_list],
            'menus': menus,
            'role_resource_action_matrix': fused_matrix,
            'scope_matrix': scope_matrix,
        }

    def migrate_org_data_permissions_to_roles(self):
        """
        将旧的 org_data_permissions 迁移到基于角色的模型

        策略：为每个有直接数据权限的组织创建对应的迁移角色，
        并将原数据权限转移到该角色上。
        """
        cursor = self.ds.execute(
            "SELECT DISTINCT org_id FROM org_data_permissions WHERE is_deprecated = 1 OR is_deprecated IS NULL"
        )
        groups_with_perms = [row[0] for row in cursor.fetchall()]

        migrated_count = 0
        for org_id in groups_with_perms:
            # P9 修复: get_group 已 Sunset，使用 _get_object 代替
            group = self._get_object(org_id)
            if not group:
                continue

            migration_role_code = f"migrated_{group['code']}"
            migration_role_name = f"[迁移] {group['name']} 数据权限"

            existing = self.ds.execute(
                "SELECT id FROM permission_sets WHERE code = ?", [migration_role_code]
            ).fetchone()

            if not existing:
                self.ds.execute(
                    """INSERT INTO permission_sets (code, name, description, is_system, priority)
                       VALUES (?, ?, ?, 0, 0)""",
                    [migration_role_code, migration_role_name,
                     f"从组织 '{group['name']}' 的直接数据权限自动迁移生成，请手动整理"]
                )
                permission_set_id = self.ds.execute("SELECT last_insert_rowid()").fetchone()[0]

                self.ds.execute(
                    "INSERT OR IGNORE INTO org_permission_sets (org_id, permission_set_id) VALUES (?, ?)",
                    [org_id, permission_set_id]
                )

                perms_cursor = self.ds.execute(
                    "SELECT * FROM org_data_permissions WHERE org_id = ?",
                    [org_id]
                )
                columns = [desc[0] for desc in perms_cursor.description]
                for row in perms_cursor.fetchall():
                    perm = dict(zip(columns, row))
                    self.ds.execute(
                        """INSERT OR REPLACE INTO permission_set_data_permissions
                           (permission_set_id, resource_type, resource_id, permission_level, inherit_to_children)
                           VALUES (?, ?, ?, ?, ?)""",
                        [permission_set_id, perm['resource_type'], perm['resource_id'],
                         perm['permission_level'], perm.get('inherit_to_children', 1)]
                    )

                migrated_count += 1

        return migrated_count
