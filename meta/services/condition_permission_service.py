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

    # ========== CRUD ==========

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
        """预览条件匹配的资源"""
        table_name = RESOURCE_TABLE_MAP.get(resource_type)
        if not table_name:
            return {'count': 0, 'resources': []}

        sql_where = self.evaluator.predicate_to_sql_where(condition)
        if not sql_where:
            return {'count': 0, 'resources': []}

        try:
            cursor = self.ds.execute(f"SELECT id, name, code FROM {table_name} WHERE {sql_where} LIMIT 100")
            resources = [{'id': r[0], 'name': r[1], 'code': r[2]} for r in cursor.fetchall()]

            count_cursor = self.ds.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {sql_where}")
            count = count_cursor.fetchone()[0]

            return {'count': count, 'resources': resources}
        except Exception as e:
            return {'count': 0, 'resources': [], 'error': str(e)}

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

                field_info = {
                    'id': field.id,
                    'name': field.name or field.id,
                    'db_column': field.db_column,
                    'field_type': field.field_type.value,
                    'description': field.description or '',
                    'relation_object': field.ui.relation if field.ui else '',
                    'display_field': field.ui.display_field if field.ui else '',
                    'is_foreign_key': False,
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
        """检查用户是否是资源的所有者"""
        table_name = RESOURCE_TABLE_MAP.get(resource_type)
        if not table_name:
            return False

        try:
            cursor = self.ds.execute(
                f"SELECT created_by, owner_id FROM {table_name} WHERE id = ?",
                [resource_id]
            )
            row = cursor.fetchone()
            if row:
                created_by, owner_id = row
                return user_id == created_by or user_id == owner_id
        except Exception:
            pass
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
