# -*- coding: utf-8 -*-
"""
条件型权限服务

Oracle 风格混合权限模型 + 用友BIP特性：
- 条件型权限规则（替代实例型 resource_id）
- Owner 自动权限
- 禁止权优先原则
- 向下继承（天然实现）
- 向上传播
- 员工数据权限模板
- 分析型权限扩展
"""

import json
import os
from typing import Dict, List, Any, Optional, Tuple
from meta.services.condition_evaluator import ConditionEvaluator


RESOURCE_TABLE_MAP = {
    'product': 'products',
    'version': 'versions',
    'domain': 'domains',
    'sub_domain': 'sub_domains',
    'service_module': 'service_modules',
    'business_object': 'business_objects',
}

CHILD_TYPE_MAP = {
    'product': ['version'],
    'version': ['domain'],
    'domain': ['sub_domain'],
    'sub_domain': ['service_module'],
    'service_module': ['business_object'],
}

PARENT_FIELD_MAP = {
    'version': 'product_id',
    'domain': 'version_id',
    'sub_domain': 'domain_id',
    'service_module': 'sub_domain_id',
    'business_object': 'service_module_id',
}

LEVEL_ORDER = {'none': 0, 'read': 1, 'write': 2, 'admin': 3}

# [2026-08-27] 系统基线字段（隐式安全基线，不暴露为逐条业务条件）
#   - owner_id (FK→user): 数据归属，由系统层保证（product chain 追溯 owner）
#   - visibility (string 枚举): 按角色可见等级放行，映射维护在角色模板层
#   语义跨所有资源一致，不适合重复配置（防重复配置/语义漂移/越权校验）。
#   命中即静默跳过，不出现在条件字段下拉与高级模式字段参考。
BASELINE_FIELDS_EXCLUDED = {'owner_id', 'visibility'}


class ConditionPermissionService:
    """条件型权限服务"""

    def __init__(self, data_source):
        self.ds = data_source
        self.evaluator = ConditionEvaluator()

    def check_permission(
        self,
        user_id: int,
        resource_type: str,
        resource_id: int,
        action: str = 'read'
    ) -> Dict[str, Any]:
        """
        条件型权限检查主入口

        优先级：
        1. Owner 权限（最高优先级）
        2. 禁止权限（用友BIP禁止权优先原则）
        3. 条件型权限规则
        4. 向上传播权限
        """
        required_level = self._action_to_level(action)

        if self._is_owner(user_id, resource_type, resource_id):
            return {
                'allowed': True,
                'permission_level': 'admin',
                'source': 'owner',
                'matched_condition': None,
            }

        if self._check_denied_rules(user_id, resource_type, resource_id):
            return {
                'allowed': False,
                'permission_level': 'none',
                'source': 'denied',
                'matched_condition': None,
            }

        condition_result = self._check_condition_rules(user_id, resource_type, resource_id, required_level)
        if condition_result['allowed']:
            return condition_result

        parent_result = self._check_parent_visibility(user_id, resource_type, resource_id)
        if parent_result['allowed']:
            return parent_result

        return {
            'allowed': False,
            'permission_level': 'none',
            'source': None,
            'matched_condition': None,
        }

    def get_effective_permission_level(
        self,
        user_id: int,
        resource_type: str,
        resource_id: int
    ) -> str:
        """兼容接口：获取有效权限级别"""
        result = self.check_permission(user_id, resource_type, resource_id, 'read')
        return result['permission_level']

    def get_authorized_resource_ids(
        self,
        user_id: int,
        resource_type: str,
        action: str = 'read'
    ) -> Optional[List[int]]:
        """
        获取用户有权访问的资源ID列表

        Returns:
            None: 无限制（有通配符权限）
            []: 无权限
            [id1, id2, ...]: 限定范围
        """
        required_level = self._action_to_level(action)
        rules = self._get_user_rules(user_id, resource_type)

        if not rules:
            return []

        where_clauses = []
        for rule in rules:
            if rule.get('is_denied'):
                continue
            if LEVEL_ORDER.get(rule['permission_level'], 0) < LEVEL_ORDER.get(required_level, 0):
                continue

            sql_where = self.evaluator.predicate_to_sql_where(rule['condition'])
            if sql_where:
                where_clauses.append(f"({sql_where})")

        if not where_clauses:
            return []

        table_name = RESOURCE_TABLE_MAP.get(resource_type)
        if not table_name:
            return None

        combined = ' OR '.join(where_clauses)
        try:
            cursor = self.ds.execute(f"SELECT id FROM {table_name} WHERE {combined}")
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []

    # ========== CRUD (legacy permission_rules 表) ==========

    def create_rule(self, data: Dict[str, Any]) -> Optional[int]:
        """创建权限规则"""
        try:
            analysis_mode = data.get('analysis_mode')
            if isinstance(analysis_mode, dict):
                analysis_mode = json.dumps(analysis_mode, ensure_ascii=False)

            cursor = self.ds.execute(
                """INSERT INTO permission_rules
                   (role_id, resource_type, condition, permission_level, is_denied,
                    inherit_to_children, propagate_to_parents, analysis_mode, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    data['role_id'],
                    data['resource_type'],
                    data['condition'],
                    data.get('permission_level', 'read'),
                    1 if data.get('is_denied') else 0,
                    1 if data.get('inherit_to_children', True) else 0,
                    1 if data.get('propagate_to_parents', True) else 0,
                    analysis_mode,
                    data.get('created_by'),
                ]
            )
            return cursor.lastrowid
        except Exception as e:
            print(f"Error creating permission rule: {e}")
            return None

    def update_rule(self, rule_id: int, data: Dict[str, Any]) -> bool:
        """更新权限规则"""
        try:
            sets = []
            params = []
            for field in ['condition', 'permission_level', 'is_denied', 'inherit_to_children',
                          'propagate_to_parents', 'analysis_mode']:
                if field in data:
                    val = data[field]
                    if field == 'is_denied':
                        val = 1 if val else 0
                    elif field == 'inherit_to_children':
                        val = 1 if val else 0
                    elif field == 'propagate_to_parents':
                        val = 1 if val else 0
                    elif field == 'analysis_mode' and isinstance(val, dict):
                        val = json.dumps(val, ensure_ascii=False)
                    sets.append(f"{field} = ?")
                    params.append(val)

            if not sets:
                return True

            sets.append("updated_at = CURRENT_TIMESTAMP")
            params.append(rule_id)
            self.ds.execute(
                f"UPDATE permission_rules SET {', '.join(sets)} WHERE rowid = ?",
                params
            )
            return True
        except Exception as e:
            print(f"Error updating permission rule: {e}")
            return False

    def delete_rule(self, rule_id: int) -> bool:
        """删除权限规则"""
        try:
            self.ds.execute("DELETE FROM permission_rules WHERE rowid = ?", [rule_id])
            return True
        except Exception:
            return False

    def get_rules_by_role(self, role_id: int, resource_type: Optional[str] = None) -> List[Dict]:
        """获取角色的权限规则"""
        if resource_type:
            cursor = self.ds.execute(
                "SELECT rowid AS id, * FROM permission_rules WHERE role_id = ? AND resource_type = ? ORDER BY resource_type",
                [role_id, resource_type]
            )
        else:
            cursor = self.ds.execute(
                "SELECT rowid AS id, * FROM permission_rules WHERE role_id = ? ORDER BY resource_type",
                [role_id]
            )
        rules = self._rows_to_dicts(cursor)
        
        # 为每条规则生成友好显示
        for rule in rules:
            rule['friendly_condition'] = self._generate_friendly_condition(rule.get('condition', ''))
        
        return rules

    def get_all_rules(self, resource_type: Optional[str] = None) -> List[Dict]:
        """获取所有权限规则"""
        if resource_type:
            cursor = self.ds.execute(
                "SELECT rowid AS id, * FROM permission_rules WHERE resource_type = ? ORDER BY role_id, rowid",
                [resource_type]
            )
        else:
            cursor = self.ds.execute(
                "SELECT rowid AS id, * FROM permission_rules ORDER BY role_id, resource_type, rowid"
            )
        rules = self._rows_to_dicts(cursor)
        
        # 为每条规则生成友好显示
        for rule in rules:
            rule['friendly_condition'] = self._generate_friendly_condition(rule.get('condition', ''))
        
        return rules

    # ========== Unified CRUD (data_permission_rules 统一表, P11 Phase 11) ==========
    # rule_type 枚举: condition | dimension | owner | visibility | prohibition
    # Spec: spec-permission-system-unification-2026-07-19 §3.5 / §8.3 P3-T1 / §8.11 P11

    VALID_RULE_TYPES = {'condition', 'dimension', 'owner', 'visibility', 'prohibition'}

    def _ensure_unified_table(self):
        """[P11] 确保 data_permission_rules 表存在 (lazy init, 幂等).

        Phase 3 schema 定义了该表, 但部分测试 DB / 旧实例可能未应用 generated_schema.sql.
        本方法在首次访问时自动建表, 避免迁移脚本依赖.
        """
        try:
            self.ds.execute("""
                CREATE TABLE IF NOT EXISTS data_permission_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role_id INTEGER NOT NULL,
                    rule_type VARCHAR(50) NOT NULL DEFAULT 'condition',
                    resource_type VARCHAR(200),
                    dimension_code VARCHAR(200),
                    condition TEXT,
                    condition_display TEXT,
                    scope_mode VARCHAR(50) DEFAULT 'include',
                    permission_level VARCHAR(50) DEFAULT 'read',
                    is_denied INTEGER DEFAULT 0,
                    inherit_to_children INTEGER DEFAULT 1,
                    propagate_to_parents INTEGER DEFAULT 0,
                    source_table VARCHAR(100),
                    source_id INTEGER,
                    created_at VARCHAR(200),
                    updated_at VARCHAR(200)
                )
            """)
            # [v56 2026-08-27] 已存在的表补列（幂等）：人类可读条件描述
            try:
                self.ds.execute(
                    "ALTER TABLE data_permission_rules ADD COLUMN condition_display TEXT"
                )
            except Exception:
                pass  # 列已存在
        except Exception as e:
            print(f"[P11] _ensure_unified_table (ignore if exists): {e}")

    def create_unified_rule(self, data: Dict[str, Any]) -> Optional[int]:
        """[P11] 创建统一权限规则 (写入 data_permission_rules 表)

        支持 rule_type 字段区分 5 种规则类型, 默认 'condition' (向后兼容).
        """
        try:
            self._ensure_unified_table()
            rule_type = data.get('rule_type', 'condition')
            if rule_type not in self.VALID_RULE_TYPES:
                rule_type = 'condition'

            cursor = self.ds.execute(
                """INSERT INTO data_permission_rules
                   (role_id, rule_type, resource_type, dimension_code, condition,
                    condition_display,
                    scope_mode, permission_level, is_denied,
                    inherit_to_children, propagate_to_parents, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                [
                    data['role_id'],
                    rule_type,
                    data.get('resource_type'),
                    data.get('dimension_code'),
                    data.get('condition'),
                    data.get('condition_display'),
                    data.get('scope_mode', 'include'),
                    data.get('permission_level', 'read'),
                    1 if data.get('is_denied') else 0,
                    1 if data.get('inherit_to_children', True) else 0,
                    1 if data.get('propagate_to_parents', False) else 0,
                ]
            )
            return cursor.lastrowid
        except Exception as e:
            print(f"[P11] Error creating unified permission rule: {e}")
            return None

    def get_unified_rules_by_role(
        self,
        role_id: int,
        rule_type: Optional[str] = None,
    ) -> List[Dict]:
        """[P11] 获取角色的统一权限规则 (从 data_permission_rules 表)

        Args:
            role_id: 角色 ID
            rule_type: 可选, 按规则类型过滤 (condition/dimension/owner/visibility/prohibition)
        """
        self._ensure_unified_table()
        if rule_type:
            cursor = self.ds.execute(
                """SELECT * FROM data_permission_rules
                   WHERE role_id = ? AND rule_type = ?
                   ORDER BY id""",
                [role_id, rule_type]
            )
        else:
            cursor = self.ds.execute(
                """SELECT * FROM data_permission_rules
                   WHERE role_id = ?
                   ORDER BY rule_type, id""",
                [role_id]
            )
        rules = self._rows_to_dicts(cursor)
        # 补齐 friendly_condition (复用现有逻辑)
        for rule in rules:
            rule['friendly_condition'] = self._generate_friendly_condition(
                rule.get('condition', '') or ''
            )
        return rules

    def get_all_unified_rules(
        self,
        rule_type: Optional[str] = None,
    ) -> List[Dict]:
        """[P11] 获取所有统一权限规则 (从 data_permission_rules 表)"""
        self._ensure_unified_table()
        if rule_type:
            cursor = self.ds.execute(
                """SELECT * FROM data_permission_rules
                   WHERE rule_type = ?
                   ORDER BY role_id, id""",
                [rule_type]
            )
        else:
            cursor = self.ds.execute(
                """SELECT * FROM data_permission_rules
                   ORDER BY role_id, rule_type, id"""
            )
        rules = self._rows_to_dicts(cursor)
        for rule in rules:
            rule['friendly_condition'] = self._generate_friendly_condition(
                rule.get('condition', '') or ''
            )
        return rules

    def update_unified_rule(self, rule_id: int, data: Dict[str, Any]) -> bool:
        """[v48 2026-08-27] 更新统一权限规则 (写 data_permission_rules 表)

        背景：v2 PUT 端点此前调用 update_rule()，其 SQL 指向 legacy 表
        permission_rules，而列表查询读 data_permission_rules —— 导致
        "变更配置条件保存后刷新仍是旧值"（更新根本没落到统一表）。

        安全限定：data 中若带 role_id / resource_type / rule_type，
        会作为 WHERE 条件二次校验，防止 id 跨表误更新。
        """
        self._ensure_unified_table()
        try:
            sets = []
            params = []
            for field in ['condition', 'condition_display', 'permission_level', 'is_denied',
                            'inherit_to_children', 'propagate_to_parents', 'scope_mode']:
                if field in data:
                    val = data[field]
                    if field in ('is_denied', 'inherit_to_children', 'propagate_to_parents'):
                        val = 1 if val else 0
                    sets.append(f"{field} = ?")
                    params.append(val)
            if not sets:
                return True
            sets.append("updated_at = CURRENT_TIMESTAMP")
            where = ["id = ?"]
            params.append(rule_id)
            # 安全限定条件（调用方传了才校验）
            for wf in ['role_id', 'resource_type', 'rule_type']:
                if data.get(wf) not in (None, ''):
                    where.append(f"{wf} = ?")
                    params.append(data[wf])
            cursor = self.ds.execute(
                f"UPDATE data_permission_rules SET {', '.join(sets)} WHERE {' AND '.join(where)}",
                params
            )
            # [v48] rowcount=0 表示该 id 不在统一表（legacy 数据）→ 返回 False 让调用方回退
            try:
                return (cursor.rowcount or 0) > 0
            except Exception:
                return True
        except Exception as e:
            print(f"[v48] Error updating unified permission rule: {e}")
            return False

    def delete_unified_rule(self, rule_id: int) -> bool:
        """[P11] 删除统一权限规则"""
        self._ensure_unified_table()
        try:
            self.ds.execute(
                "DELETE FROM data_permission_rules WHERE id = ?",
                [rule_id]
            )
            return True
        except Exception:
            return False

    def _get_dimension_field_map(self) -> Dict[str, Dict]:
        """获取维度字段到维度信息的映射（从 hierarchies.yaml）"""
        import os
        import yaml
        schema_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas')
        hierarchies_path = os.path.join(schema_dir, 'hierarchies.yaml')

        result = {}
        if os.path.exists(hierarchies_path):
            try:
                with open(hierarchies_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    for dim in data.get('dimensions', []):
                        obj = dim.get('object', '')
                        filter_param = dim.get('filter_param', '')
                        if obj and filter_param:
                            result[filter_param] = {
                                'code': dim.get('id'),
                                'name': dim.get('name'),
                                'field': filter_param
                            }
            except Exception as e:
                print(f"[Warning] Failed to load hierarchies.yaml: {e}")

        return result

    def _generate_friendly_condition(self, condition: str) -> str:
        """将技术条件表达式转换为用户友好的显示"""
        if not condition:
            return ''

        # 获取维度映射
        dim_map = self._get_dimension_field_map()

        # 第一步：替换字段名为维度名称
        result = condition
        for field, dim_info in dim_map.items():
            dim_name = dim_info.get('name', field)
            result = result.replace(field, dim_name)

        # 第二步：先替换操作符为中文化（这样后续才能正确匹配）
        result = result.replace(' = ', ' 等于 ')
        result = result.replace(' != ', ' 不等于 ')
        result = result.replace(' IN ', ' 包含于 ')
        result = result.replace(' AND ', ' 且 ')
        result = result.replace(' OR ', ' 或 ')

        # 第三步：解析并替换ID值为业务名称（现在可以匹配中文操作符了）
        import re
        patterns = [
            r'(\S+)\s+等于\s+(\d+)',           # 单值等于
            r'(\S+)\s+不等于\s+(\d+)',          # 单值不等于
            r'(\S+)\s+包含于\s+\(([^)]+)\)',    # 多值包含于
        ]

        for pattern in patterns:
            matches = re.findall(pattern, result)
            for match in matches:
                if len(match) == 2:
                    dim_name, value_or_values = match
                    field = self._find_field_by_dim_name(dim_name, dim_map)

                    # 判断是单值还是多值
                    # "包含于"总是多值（即使只有一个值），"等于/不等于"是单值
                    is_in_condition = '包含于' in result[result.find(dim_name):result.find(dim_name)+20]

                    if is_in_condition and field:
                        # 多值处理（IN条件）
                        values = [v.strip() for v in value_or_values.split(',')]
                        display_names = []
                        for v in values:
                            if v.strip().isdigit():
                                name = self._get_display_name_for_id(field, int(v.strip()))
                                display_names.append(name if name else v.strip())
                            else:
                                display_names.append(v.strip())
                        if display_names:
                            new_values = ', '.join(display_names)
                            result = re.sub(
                                rf'{re.escape(dim_name)}\s+包含于\s+\([^)]+\)',
                                f'{dim_name} 包含于 ({new_values})',
                                result,
                                count=1
                            )
                    elif field and value_or_values.isdigit():
                        # 单值处理（=/!= 条件）
                        display_name = self._get_display_name_for_id(field, int(value_or_values))
                        if display_name:
                            result = re.sub(
                                rf'{re.escape(dim_name)}\s+等于\s+{value_or_values}',
                                f'{dim_name} 等于 {display_name}',
                                result
                            )
                            result = re.sub(
                                rf'{re.escape(dim_name)}\s+不等于\s+{value_or_values}',
                                f'{dim_name} 不等于 {display_name}',
                                result
                            )

        return result

    def _find_field_by_dim_name(self, dim_name: str, dim_map: Dict) -> Optional[str]:
        """根据维度名称查找对应的技术字段名"""
        for field, info in dim_map.items():
            if info.get('name') == dim_name:
                return field
        return None

    def _get_display_name_for_id(self, field: str, value_id: int) -> Optional[str]:
        """根据字段名和ID值查询对应的业务显示名称"""
        try:
            # 根据字段名推断关联的表和显示字段
            table_mapping = {
                'version_id': ('versions', 'name'),
                'domain_id': ('domains', 'domain_name'),
                'sub_domain_id': ('sub_domains', 'sub_domain_name'),
                'product_id': ('products', 'product_name'),
                'service_module_id': ('service_modules', 'module_name'),
                'business_object_id': ('business_objects', 'object_name'),
                'organization_id': ('organizations', 'org_name'),
                'department_id': ('departments', 'dept_name'),
                'employee_id': ('employees', 'employee_name'),
            }

            if field in table_mapping:
                table_name, display_col = table_mapping[field]
                cursor = self.ds.execute(
                    f"SELECT {display_col} FROM {table_name} WHERE id = ?",
                    [value_id]
                )
                row = cursor.fetchone()
                if row and row[0]:
                    return str(row[0])
                else:
                    # 尝试使用 code 字段
                    cursor = self.ds.execute(
                        f"SELECT code FROM {table_name} WHERE id = ?",
                        [value_id]
                    )
                    row = cursor.fetchone()
                    if row and row[0]:
                        return str(row[0])

            return None
        except Exception as e:
            print(f"[Warning] Failed to get display name for {field}={value_id}: {e}")
            return None

    def get_rule(self, rule_id: int) -> Optional[Dict]:
        """获取单条权限规则"""
        cursor = self.ds.execute("SELECT rowid AS id, * FROM permission_rules WHERE rowid = ?", [rule_id])
        rows = self._rows_to_dicts(cursor)
        return rows[0] if rows else None

    def preview_matching_resources(self, condition: str, resource_type: str) -> Dict[str, Any]:
        """预览条件匹配的资源

        [2026-08-28 v61] 返回结构增加 total（全表数量）用于对比视角；
        错误显性化：条件解析 / SQL 失败必须通过 error 字段传给前端，
        不能伪装成「匹配 0 个资源」误导用户。
        """
        table_name = RESOURCE_TABLE_MAP.get(resource_type)
        if not table_name:
            return {'count': 0, 'total': 0, 'resources': [], 'error': f'未知的资源类型: {resource_type}'}

        sql_where = self.evaluator.predicate_to_sql_where(condition)
        if not sql_where:
            return {'count': 0, 'total': 0, 'resources': [], 'error': '条件表达式无法解析为有效的查询'}

        try:
            total_cursor = self.ds.execute(f"SELECT COUNT(*) FROM {table_name}")
            total = total_cursor.fetchone()[0]

            cursor = self.ds.execute(f"SELECT id, name, code FROM {table_name} WHERE {sql_where} LIMIT 100")
            resources = [{'id': r[0], 'name': r[1], 'code': r[2]} for r in cursor.fetchall()]

            count_cursor = self.ds.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {sql_where}")
            count = count_cursor.fetchone()[0]

            return {'count': count, 'total': total, 'resources': resources}
        except Exception as e:
            return {'count': 0, 'total': 0, 'resources': [], 'error': str(e)}

    def get_resource_field_metadata(self, resource_type: str) -> List[Dict]:
        """
        获取资源类型的字段元数据（用于自定义条件的字段Value Help）

        从Schema元数据返回字段列表，包含relation和display_field信息
        """
        try:
            from meta.core.models import registry, FieldStorage

            # 确保registry已加载
            if not registry._initialized:
                schema_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas')
                if os.path.exists(schema_dir):
                    registry.reload(schema_dir)

            meta_obj = registry.get(resource_type)
            if not meta_obj:
                return []

            fields = []
            for field in meta_obj.fields:
                # 跳过虚拟字段
                if field.storage == FieldStorage.VIRTUAL:
                    continue

                # [2026-08-27] 跳过系统基线字段（owner_id / visibility）
                #   隐式安全基线由系统层保证，不暴露为逐条业务条件
                if field.db_column in BASELINE_FIELDS_EXCLUDED:
                    continue

                field_info = {
                    'id': field.id,
                    'name': field.name or field.id,
                    'db_column': field.db_column,
                    'field_type': field.field_type.value,
                    'description': field.description or '',
                    'relation_object': field.ui.relation if field.ui else '',
                    'display_field': field.ui.display_field if field.ui else '',
                    'is_foreign_key': False,
                    # [v18 2026-08-26] 业务主键标志：标识「资源自身的 ID / 编码」字段
                    #   - 用于在 Rule Builder 中触发 self-reference picker
                    #   - 数据源：YAML field.semantics.business_key == true
                    #   - 头部产品对照：
                    #   - SAP: Authorization Object 的「自身字段」也支持 F4 Search Help（按 Object 自身取候选）
                    #   - Salesforce: Lookup Dialog 返回 Id，default field 是 Id (业务键)
                    'is_business_key': False,
                    # [v21 2026-08-26] 枚举标志：标识「枚举 / boolean 字段」走枚举 picker
                    #   - 数据源：YAML field.enum_values（固定枚举）或 field.semantics.enum_ref（引用枚举类型）
                    #   - 头部产品对照：SAP Authorization Field 单值域（Fixed Value）也支持 F4
                    'is_enum': False,
                    'enum_values': None,  # list[{value, label, color}], 或 None
                    'enum_ref': None,      # str: enum_type_id（引用枚举类型）, 或 None
                }

                # 判断是否为外键
                if field.ui and field.ui.relation:
                    field_info['is_foreign_key'] = True
                if field.semantics and field.semantics.analytics:
                    analytics = field.semantics.analytics
                    if isinstance(analytics, dict):
                        if analytics.get('type') == 'foreign_key':
                            field_info['is_foreign_key'] = True
                            if analytics.get('display_name') and not field_info.get('name'):
                                field_info['name'] = analytics['display_name']

                # [v18 2026-08-26] 检测业务主键字段：
                #   优先从 semantics.business_key 读取（YAML 显式声明）
                #   兜底：db_column == 'code'（多数资源的业务编码字段）
                #   不强制要求 id 字段必为业务主键（id 是技术主键，由 ui.visible=false 隐藏）
                semantics = field.semantics
                if semantics and getattr(semantics, 'business_key', False):
                    field_info['is_business_key'] = True
                elif field.db_column == 'code' and not field_info['is_business_key']:
                    # 兜底：YAML 未声明 business_key 时，code 字段默认视为业务主键
                    field_info['is_business_key'] = True

                # [v21 2026-08-26] 检测枚举字段：
                #   - 固定枚举：YAML field.enum_values 列出所有选项（如 boolean「是/否」、status「启用/禁用」）
                #     实际是 List[Dict]，每个 dict 含 value/label/color 键
                #   - 引用枚举：YAML field.semantics.enum_ref 指向一个枚举类型（如 visibility、priority）
                #   - 检测到任一来源 → is_enum=true，前端 Rule Builder 用 picker（不是 el-input 文本）
                enum_values_raw = getattr(field, 'enum_values', None)
                if enum_values_raw:
                    field_info['is_enum'] = True
                    # [v21 FIX 2026-08-26] enum_values 是 List[Dict]（不是对象列表），统一转为 {value, label, color}
                    normalized = []
                    for ev in enum_values_raw:
                        if isinstance(ev, dict):
                            normalized.append({
                                'value': str(ev.get('value', ev.get('label', ''))),
                                'label': ev.get('label', str(ev.get('value', ''))),
                                'color': ev.get('color'),
                            })
                    if normalized:
                        field_info['enum_values'] = normalized
                elif semantics and getattr(semantics, 'enum_ref', None):
                    field_info['is_enum'] = True
                    field_info['enum_ref'] = semantics.enum_ref

                fields.append(field_info)

            return fields
        except Exception as e:
            print(f"Error loading field metadata for {resource_type}: {e}")
            return []

    # ========== 员工数据权限 ==========

    def get_employee_data_scopes(self) -> List[Dict]:
        """获取员工数据权限范围列表"""
        cursor = self.ds.execute("SELECT * FROM employee_data_scopes ORDER BY id")
        return self._rows_to_dicts(cursor)

    def resolve_employee_scope_condition(
        self, user_id: int, scope_code: str
    ) -> Optional[str]:
        """解析员工数据权限范围条件"""
        cursor = self.ds.execute(
            "SELECT condition_template FROM employee_data_scopes WHERE code = ?",
            [scope_code]
        )
        row = cursor.fetchone()
        if not row:
            return None

        template = row[0]

        user_info = self._get_user_org_info(user_id)

        params = {
            'user_id': user_id,
            'user_department_id': user_info.get('department_id', 0),
            'user_department_tree': user_info.get('department_tree', [0]),
            'user_organization_id': user_info.get('organization_id', 0),
        }

        return self.evaluator.resolve_template(template, params)

    # ========== 条件引用实例检测 ==========

    def check_rule_references_resource(
        self, resource_type: str, resource_id: int
    ) -> List[Dict]:
        """检查是否有权限规则引用了指定资源"""
        affected = []
        cursor = self.ds.execute(
            "SELECT rowid AS id, role_id, resource_type, condition, permission_level, is_denied FROM permission_rules"
        )
        rules = self._rows_to_dicts(cursor)

        for rule in rules:
            refs = self.evaluator.detect_instance_references(rule['condition'])
            for ref in refs:
                if ref['field'] == 'id' and ref['value'] == resource_id and rule['resource_type'] == resource_type:
                    affected.append(rule)
                elif ref['resource_type'] == resource_type and ref['value'] == resource_id:
                    affected.append(rule)

        return affected

    # ========== 内部方法 ==========

    def _is_owner(self, user_id: int, resource_type: str, resource_id: int) -> bool:
        """检查用户是否是资源的所有者

        [FIX BUG-V010 2026-06-26] 兼容 V1.1.4 owner refactor
        背景: V1.1.4 后 owner_id 字段统一在 product 表, 子对象表 (version/domain/
              sub_domain/service_module/business_object) 已删除 owner_id 列
        修复: 通过 product chain 追溯 owner, 不再直接查子对象表的 owner_id
        案例: TEST333 是 product SDLKFJL 的 owner, 删除其下 version 失败
              原因: 原 _is_owner 查 versions.owner_id, 列不存在, 异常被吞
        """
        table_name = RESOURCE_TABLE_MAP.get(resource_type)
        if not table_name:
            return False

        # product: 直接查 owner_id
        if resource_type == 'product':
            try:
                cursor = self.ds.execute(
                    f"SELECT owner_id FROM {table_name} WHERE id = ?",
                    [resource_id]
                )
                row = cursor.fetchone()
                return row and row[0] == user_id
            except Exception:
                return False

        # 子对象: 通过 product chain 追溯 owner
        # [FIX BUG-V010] 不用 created_by (V1.1 后 user 也变了), 也不用 owner_id (列已删)
        chain_sql_map = {
            'version': f"""
                SELECT p.owner_id FROM {table_name} t
                JOIN products p ON t.product_id = p.id
                WHERE t.id = ?
            """,
            'domain': f"""
                SELECT p.owner_id FROM {table_name} t
                JOIN versions v ON t.version_id = v.id
                JOIN products p ON v.product_id = p.id
                WHERE t.id = ?
            """,
            'sub_domain': f"""
                SELECT p.owner_id FROM {table_name} t
                JOIN domains d ON t.domain_id = d.id
                JOIN versions v ON d.version_id = v.id
                JOIN products p ON v.product_id = p.id
                WHERE t.id = ?
            """,
            'service_module': f"""
                SELECT p.owner_id FROM {table_name} t
                JOIN sub_domains sd ON t.sub_domain_id = sd.id
                JOIN domains d ON sd.domain_id = d.id
                JOIN versions v ON d.version_id = v.id
                JOIN products p ON v.product_id = p.id
                WHERE t.id = ?
            """,
            'business_object': f"""
                SELECT p.owner_id FROM {table_name} t
                JOIN service_modules sm ON t.service_module_id = sm.id
                JOIN sub_domains sd ON sm.sub_domain_id = sd.id
                JOIN domains d ON sd.domain_id = d.id
                JOIN versions v ON d.version_id = v.id
                JOIN products p ON v.product_id = p.id
                WHERE t.id = ?
            """,
        }
        sql = chain_sql_map.get(resource_type)
        if not sql:
            return False
        try:
            cursor = self.ds.execute(sql, [resource_id])
            row = cursor.fetchone()
            return row and row[0] == user_id
        except Exception:
            return False

    def _check_denied_rules(self, user_id: int, resource_type: str, resource_id: int) -> bool:
        """检查禁止权限（用友BIP禁止权优先原则）"""
        rules = self._get_user_rules(user_id, resource_type)
        resource = self._get_resource_detail(resource_type, resource_id)
        if not resource:
            return False

        for rule in rules:
            if not rule.get('is_denied'):
                continue
            if self.evaluator.evaluate(rule['condition'], resource):
                return True

        return False

    def _check_condition_rules(
        self, user_id: int, resource_type: str, resource_id: int, required_level: str
    ) -> Dict[str, Any]:
        """检查条件型权限规则"""
        rules = self._get_user_rules(user_id, resource_type)
        resource = self._get_resource_detail(resource_type, resource_id)
        if not resource:
            return {'allowed': False}

        best_level = 'none'
        best_rule = None

        for rule in rules:
            if rule.get('is_denied'):
                continue
            if not rule.get('inherit_to_children', True):
                if str(resource.get('id')) not in rule['condition']:
                    continue

            if self.evaluator.evaluate(rule['condition'], resource):
                rule_level = rule.get('permission_level', 'read')
                if LEVEL_ORDER.get(rule_level, 0) > LEVEL_ORDER.get(best_level, 0):
                    best_level = rule_level
                    best_rule = rule

        if LEVEL_ORDER.get(best_level, 0) >= LEVEL_ORDER.get(required_level, 0):
            return {
                'allowed': True,
                'permission_level': best_level,
                'source': 'condition',
                'matched_condition': best_rule['condition'] if best_rule else None,
            }

        return {'allowed': False}

    def _check_parent_visibility(
        self, user_id: int, resource_type: str, resource_id: int
    ) -> Dict[str, Any]:
        """检查向上传播权限（子级权限提供父级只读可见性）"""
        child_types = CHILD_TYPE_MAP.get(resource_type, [])

        for child_type in child_types:
            child_table = RESOURCE_TABLE_MAP.get(child_type)
            if not child_table:
                continue

            parent_field = PARENT_FIELD_MAP.get(child_type)
            if not parent_field:
                continue

            try:
                cursor = self.ds.execute(
                    f"SELECT id FROM {child_table} WHERE {parent_field} = ? LIMIT 1",
                    [resource_id]
                )
                child_row = cursor.fetchone()
                if not child_row:
                    continue

                child_id = child_row[0]
                child_result = self._check_condition_rules(user_id, child_type, child_id, 'read')
                if child_result['allowed']:
                    return {
                        'allowed': True,
                        'permission_level': 'read',
                        'source': 'upward_propagation',
                        'matched_condition': child_result.get('matched_condition'),
                        'propagated_from': f"{child_type}#{child_id}",
                    }
            except Exception:
                continue

        return {'allowed': False}

    def _get_user_rules(self, user_id: int, resource_type: str) -> List[Dict]:
        """获取用户的条件型权限规则"""
        cursor = self.ds.execute("""
            SELECT pr.rowid AS id, pr.* FROM permission_rules pr
            INNER JOIN group_roles gr ON pr.role_id = gr.role_id
            INNER JOIN user_group_members ugm ON gr.group_id = ugm.group_id
            WHERE ugm.user_id = ? AND pr.resource_type = ?
            ORDER BY pr.is_denied DESC, pr.rowid
        """, [user_id, resource_type])
        return self._rows_to_dicts(cursor)

    def _get_resource_detail(self, resource_type: str, resource_id: int) -> Optional[Dict]:
        """获取资源详情"""
        table_name = RESOURCE_TABLE_MAP.get(resource_type)
        if not table_name:
            return None

        try:
            cursor = self.ds.execute(f"SELECT * FROM {table_name} WHERE id = ?", [resource_id])
            rows = self._rows_to_dicts(cursor)
            return rows[0] if rows else None
        except Exception:
            return None

    def _get_user_org_info(self, user_id: int) -> Dict:
        """获取用户的组织信息"""
        info = {}
        try:
            cursor = self.ds.execute(
                "SELECT department_id, organization_id FROM users WHERE id = ?",
                [user_id]
            )
            row = cursor.fetchone()
            if row:
                info['department_id'] = row[0]
                info['organization_id'] = row[1]

            if info.get('department_id'):
                dept_cursor = self.ds.execute(
                    "SELECT id FROM departments WHERE id = ? OR parent_id = ?",
                    [info['department_id'], info['department_id']]
                )
                info['department_tree'] = [r[0] for r in dept_cursor.fetchall()]
        except Exception:
            pass
        return info

    def _action_to_level(self, action: str) -> str:
        """将操作映射到权限级别"""
        mapping = {
            'read': 'read',
            'view': 'read',
            'reference': 'read',
            'export': 'read',
            'create': 'write',
            'update': 'write',
            'write': 'write',
            'delete': 'admin',
            'admin': 'admin',
            'manage': 'admin',
        }
        return mapping.get(action, 'read')

    def _rows_to_dicts(self, cursor) -> List[Dict]:
        """将查询结果转为字典列表"""
        if cursor.description is None:
            return []
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
