# -*- coding: utf-8 -*-
"""
P2-Matrix-03 聚合 API 后端测试

覆盖（Spec 5.4.1 P2-Matrix-03 验收：/meta?role_id= 返回矩阵且来源 detail 正确）：
- ① 带 role_id → 200，返回 role_resource_action_matrix（columns/resources/sources_detail）
     + menu_permission_matrix（复用 role_menu_api._build_role_unified_data）
- ② 不带 role_id → 两个矩阵为 null（兼容旧行为）
- ③ sources_detail 来源语义合法（include/auto/derived/exclude）且三种以上真实来源齐全
- ④ exclude（Deny）合并优先级：临时插入 is_denied=1 规则 → 覆盖 include，cell 变
     exclude + granted=False（Spec 2.2：exclude > include > auto > derived）

通过 test.py 入口运行：
    python d:\filework\test.py --file d:\filework\excel-to-diagram\tests\integration\test_permission_dimension_meta_matrix.py
"""
import os
import sys
import sqlite3
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

os.environ.setdefault('TESTING', '1')

from flask import Flask
from meta.api.permission_dimension_api import permission_dimension_bp


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'meta', 'architecture.db')


class TestPermissionMetaMatrix(unittest.TestCase):
    """P2-Matrix-03 /meta?role_id= 矩阵聚合"""

    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.register_blueprint(permission_dimension_bp)
        cls.client = cls.app.test_client()
        cls.meta_url = '/api/v2/bo/permission_dimension/meta'

    def _db(self):
        return sqlite3.connect(DB_PATH)

    def _pick_role_with_sources(self):
        """找一个同时有 role_permissions + role_dimension_scopes + role_menu_permissions 的 role"""
        conn = self._db()
        c = conn.cursor()
        c.execute("""
            SELECT rp.role_id
            FROM role_permissions rp
            WHERE EXISTS (
                SELECT 1 FROM role_dimension_scopes rds WHERE rds.role_id = rp.role_id
            )
            AND EXISTS (
                SELECT 1 FROM role_menu_permissions rmp WHERE rmp.role_id = rp.role_id
            )
            LIMIT 1
        """)
        row = c.fetchone()
        conn.close()
        return row[0] if row else None

    def _find_include_cell(self, matrix):
        """从矩阵中找一个 source=include 且 granted=True 的 (resource_type, action)"""
        for r in matrix['resources']:
            for action, cell in r['cells'].items():
                if cell.get('source') == 'include' and cell.get('granted'):
                    return r['resource_type'], action
        return None, None

    # ---- ① 带 role_id → 两个矩阵齐全 ----

    def test_matrix_returned_with_role_id(self):
        """① /meta?role_id= → 200，返回资源矩阵 + 菜单矩阵 + 来源明细"""
        role_id = self._pick_role_with_sources()
        if not role_id:
            self.skipTest('数据库无同时命中 3 类来源的 role，跳过')
        resp = self.client.get(self.meta_url, query_string={'role_id': role_id})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()['data']

        matrix = data.get('role_resource_action_matrix')
        self.assertIsNotNone(matrix, 'role_resource_action_matrix 不应为 null')
        self.assertEqual(matrix.get('role_id'), role_id)
        self.assertIsInstance(matrix.get('columns'), list)
        self.assertGreater(len(matrix['columns']), 0)
        self.assertIsInstance(matrix.get('resources'), list)
        self.assertGreater(len(matrix['resources']), 0)
        self.assertIsInstance(matrix.get('sources_detail'), list)
        self.assertGreater(len(matrix['sources_detail']), 0)

        # 每行结构：resource_type / label / cells
        for row in matrix['resources']:
            self.assertIn('resource_type', row)
            self.assertIn('label', row)
            self.assertIn('cells', row)
            for action in matrix['columns']:
                cell = row['cells'].get(action)
                self.assertIsNotNone(cell, f"cells 缺列 {action}")
                self.assertIn('granted', cell)
                self.assertIn('source', cell)

        # 菜单矩阵复用 role_menu_api 纯函数
        self.assertIsNotNone(data.get('menu_permission_matrix'),
                             'menu_permission_matrix 不应为 null')

    # ---- ② 不带 role_id → null ----

    def test_matrix_null_without_role_id(self):
        """② 不带 role_id → 两个矩阵为 null（兼容旧行为）"""
        resp = self.client.get(self.meta_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()['data']
        self.assertIsNone(data.get('role_resource_action_matrix'))
        self.assertIsNone(data.get('menu_permission_matrix'))

    # ---- [P2-Matrix-01] 可授权动作清单（A5 灰化禁选依据） ----

    def test_resource_action_matrix_audit_log_restricted(self):
        """⑤ resource_action_matrix：audit_log 仅 [read,list,export]，无 create/update/delete"""
        resp = self.client.get(self.meta_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()['data']
        ram = data.get('resource_action_matrix')
        self.assertIsNotNone(ram, 'resource_action_matrix 不应为 null')
        self.assertIsInstance(ram, dict)
        # audit_log 是验收样例：不支持 create/update/delete
        self.assertEqual(ram.get('audit_log'), ['read', 'list', 'export'])
        for a in ('create', 'update', 'delete'):
            self.assertNotIn(a, ram.get('audit_log', []))

    def test_resource_action_matrix_actions_valid(self):
        """⑥ resource_action_matrix 每个 rt 的动作均为非空列表且 ∈ 已知动作集"""
        resp = self.client.get(self.meta_url)
        data = resp.get_json()['data']
        ram = data.get('resource_action_matrix')
        self.assertGreater(len(ram), 0)
        known = {'create', 'read', 'list', 'update', 'delete', 'export', 'manage'}
        for rt, actions in ram.items():
            self.assertIsInstance(actions, list, f'{rt}.actions 应为列表')
            self.assertGreater(len(actions), 0, f'{rt} 至少一个可授权动作')
            for a in actions:
                self.assertIn(a, known, f'{rt} 动作 {a} 不在已知动作集内')

    def test_matrix_columns_match_supported_union(self):
        """⑦ 角色矩阵动作列 = resource_action_matrix 所有 rt 动作并集

        注：Flask jsonify 默认 sort_keys=True，HTTP 响应中 dict 键按字母序，
        故此处用集合相等断言（列集合 = 并集，顺序无业务意义）。
        """
        role_id = self._pick_role_with_sources()
        if not role_id:
            self.skipTest('数据库无同时命中 3 类来源的 role，跳过')
        resp = self.client.get(self.meta_url, query_string={'role_id': role_id})
        data = resp.get_json()['data']
        matrix = data['role_resource_action_matrix']
        union = []
        for actions in data['resource_action_matrix'].values():
            for a in actions:
                if a not in union:
                    union.append(a)
        self.assertEqual(set(matrix['columns']), set(union))

    # ---- ③ 来源语义合法 + 多来源齐全 ----

    def test_sources_detail_valid_and_complete(self):
        """③ sources_detail 来源 ∈ 4 色语义，且 include/auto/derived 齐全"""
        role_id = self._pick_role_with_sources()
        if not role_id:
            self.skipTest('数据库无同时命中 3 类来源的 role，跳过')
        resp = self.client.get(self.meta_url, query_string={'role_id': role_id})
        detail = resp.get_json()['data']['role_resource_action_matrix']['sources_detail']

        valid_sources = {'include', 'auto', 'derived', 'exclude'}
        seen = set()
        for item in detail:
            self.assertIn(item['source'], valid_sources,
                          f"非法来源 {item['source']}")
            self.assertIn('resource_type', item)
            self.assertIn('action', item)
            self.assertIn('origin', item)
            seen.add(item['source'])

        # 真实库该角色必有 3 类来源（role_permissions / role_menu_permissions / role_dimension_scopes）
        for src in ('include', 'auto', 'derived'):
            self.assertIn(src, seen, f'来源 {src} 应存在（角色同时命中 3 类来源）')

    # ---- ④ exclude（Deny）合并优先级 ----

    def test_exclude_deny_overrides_include(self):
        """④ 临时插入 is_denied=1 → 覆盖 include：cell 变 exclude + granted=False"""
        role_id = self._pick_role_with_sources()
        if not role_id:
            self.skipTest('数据库无同时命中 3 类来源的 role，跳过')

        # 先取一个 include cell 作为被覆盖目标
        resp0 = self.client.get(self.meta_url, query_string={'role_id': role_id})
        matrix0 = resp0.get_json()['data']['role_resource_action_matrix']
        rt, action = self._find_include_cell(matrix0)
        if not rt:
            self.skipTest('该角色无 include cell 可覆盖，跳过')

        conn = self._db()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO data_permission_rules
                (role_id, rule_type, resource_type, permission_level, is_denied)
                VALUES (?, 'condition', ?, ?, 1)
            """, (role_id, rt, action))
            inserted_id = cursor.lastrowid
            conn.commit()
        finally:
            conn.close()

        try:
            resp1 = self.client.get(self.meta_url, query_string={'role_id': role_id})
            matrix1 = resp1.get_json()['data']['role_resource_action_matrix']

            # 该 cell 被 exclude 覆盖
            row1 = next(r for r in matrix1['resources'] if r['resource_type'] == rt)
            cell = row1['cells'][action]
            self.assertEqual(cell['source'], 'exclude', 'Deny 应覆盖 include')
            self.assertFalse(cell['granted'], 'exclude cell 不应 granted')

            # sources_detail 含该 deny 记录
            matched = [
                d for d in matrix1['sources_detail']
                if d['source'] == 'exclude' and d['resource_type'] == rt
                and d['action'] == action
            ]
            self.assertTrue(matched, 'sources_detail 应包含新插入的 exclude 记录')
        finally:
            conn = self._db()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM data_permission_rules WHERE id = ?", (inserted_id,))
            conn.commit()
            conn.close()


if __name__ == '__main__':
    unittest.main()
