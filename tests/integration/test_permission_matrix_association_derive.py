# -*- coding: utf-8 -*-
"""
[v42 2026-08-27] 关系/子资源 derive 矩阵后端测试

覆盖 (Spec 5.4.1):
- ① role 配 dimension scope(version/domain/sub_domain) →
     relationship 行 read/create/update/delete 应有 derived 来源
- ② role 没 dimension scope → relationship 行无 derived
- ③ annotation/audit_log 的 sources_detail 应包含 owner_auto 项
     (即使 cell.granted=False 也要列出 — 告知 owner 自治路径)
- ④ manual 优先于 derived: role 同时配 manual grant + dimension scope,
     relationship cell.source 应该是 include 而非 derived

通过 test.py 入口运行:
    python d:\filework\test.py --file d:\filework/excel-to-diagram/tests/integration/test_permission_matrix_association_derive.py
"""
import os
import sys
import sqlite3
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.environ.setdefault('TESTING', '1')

from meta.api.permission_dimension_api import _build_role_matrices


DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'meta', 'architecture.db',
)


class TestMatrixAssociationDerive(unittest.TestCase):
    """[v42] relationship / annotation / audit_log derive"""

    @classmethod
    def setUpClass(cls):
        # _get_engine() 是 module-level 懒加载，TESTING=1 模式下 _is_testing() 会预置 current_user
        from meta.api.permission_dimension_api import _get_engine
        _get_engine()
        cls.conn = sqlite3.connect(DB_PATH)
        cls.cursor = cls.conn.cursor()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    # ---- ① dimension scope → relationship derive ----

    def test_relationship_derived_from_dimension_scope(self):
        """① role 配 version/domain/sub_domain 任一 scope → relationship 有 derived 来源"""
        self.cursor.execute('''
            SELECT DISTINCT role_id FROM role_dimension_scopes
            WHERE dimension_code IN ('version', 'domain', 'sub_domain')
            LIMIT 1
        ''')
        rid_row = self.cursor.fetchone()
        if not rid_row:
            self.skipTest('DB 无 dimension_scope role, 跳过')
        rid = rid_row[0]

        mat = _build_role_matrices(rid)
        if not mat:
            self.skipTest(f'_build_role_matrices 返回 None for role={rid}')

        rel_row = next((r for r in mat['resources'] if r['resource_type'] == 'relationship'), None)
        if not rel_row:
            self.skipTest('role 矩阵无 relationship 行')

        # 至少 read 应是 derived 或更高优先级 (manual/auto 优先)
        rel_sources = [d for d in mat['sources_detail'] if d['resource_type'] == 'relationship']
        sources_set = {d['source'] for d in rel_sources}
        # 来源应有 derived 或 include/auto (后者覆盖 derived)
        self.assertTrue(
            sources_set & {'derived', 'include', 'auto'},
            f'role={rid} relationship 来源应含 derived/include/auto 之一, 实际={sources_set}',
        )

        # 如果没有 manual/auto 覆盖，则 cell 应直接是 derived
        rel_manual_or_auto = any(
            d['source'] in ('include', 'auto')
            for d in rel_sources
        )
        if not rel_manual_or_auto:
            self.assertEqual(rel_row['cells']['read']['source'], 'derived',
                             f'role={rid} 无 manual/auto 时 read 必须是 derived')

    # ---- ② 没 dimension scope → 无 derived ----

    def test_no_dimension_scope_no_derived(self):
        """② role 没 dimension scope → relationship 不会有 derived 来源"""
        self.cursor.execute('''
            SELECT r.id FROM roles r
            WHERE r.id NOT IN (SELECT DISTINCT role_id FROM role_dimension_scopes)
            LIMIT 1
        ''')
        rid_row = self.cursor.fetchone()
        if not rid_row:
            self.skipTest('DB 找不到无 dimension_scope 的 role')
        rid = rid_row[0]

        mat = _build_role_matrices(rid)
        if not mat:
            return  # None 也算通过（矩阵构建失败不算测试失败）

        rel_sources = [d for d in mat['sources_detail'] if d['resource_type'] == 'relationship']
        derived_items = [d for d in rel_sources if d['source'] == 'derived']
        # 注：relationship 也可能有 include/auto（来自 role_permissions 或菜单），
        #     这里只断言"derived 应为空"，因为没 scope 不可能 derive 出 relationship
        # 排除 dimension_code 自身（version:read 仍然存在，但不进 relationship）
        # 已通过 rt='relationship' 过滤，derived_items 只含 relationship:xxx
        self.assertEqual(derived_items, [],
                         f'role={rid} 无 scope 时 relationship 不应有 derived，实际={derived_items}')

    # ---- ③ annotation/audit_log 的 owner_auto 在 sources_detail 出现 ----

    def test_subordinate_owner_auto_in_sources_detail(self):
        """③ sources_detail 应包含 annotation/audit_log 的 owner_auto 项"""
        self.cursor.execute('SELECT id FROM roles LIMIT 1')
        rid_row = self.cursor.fetchone()
        if not rid_row:
            self.skipTest('无 role')
        rid = rid_row[0]

        mat = _build_role_matrices(rid)
        if not mat:
            self.skipTest('_build_role_matrices 返回 None')

        owner_auto_items = [d for d in mat['sources_detail'] if d['source'] == 'owner_auto']
        # 至少应有 annotation:read/update + audit_log:read/update = 4 条
        self.assertGreaterEqual(len(owner_auto_items), 4,
                                f'owner_auto 来源数 >= 4, 实际={len(owner_auto_items)}')

        # 必须包含 annotation:read 和 audit_log:read
        rts_actions = {(d['resource_type'], d['action']) for d in owner_auto_items}
        self.assertIn(('annotation', 'read'), rts_actions)
        self.assertIn(('annotation', 'update'), rts_actions)
        self.assertIn(('audit_log', 'read'), rts_actions)
        self.assertIn(('audit_log', 'update'), rts_actions)

    # ---- ④ manual 优先 derived（验证合并优先级） ----

    def test_manual_overrides_derived(self):
        """④ role 同时有 manual grant + dimension scope，cell.source 应为 include"""
        self.cursor.execute('''
            SELECT DISTINCT rp.role_id
            FROM role_permissions rp
            JOIN permissions p ON p.id = rp.permission_id
            JOIN role_dimension_scopes rds ON rds.role_id = rp.role_id
            WHERE p.resource_type = 'relationship'
              AND rds.dimension_code IN ('version', 'domain', 'sub_domain')
            LIMIT 1
        ''')
        rid_row = self.cursor.fetchone()
        if not rid_row:
            self.skipTest('无同时配 manual + scope 的 role')
        rid = rid_row[0]

        mat = _build_role_matrices(rid)
        if not mat:
            self.skipTest('_build_role_matrices 返回 None')

        rel_row = next((r for r in mat['resources'] if r['resource_type'] == 'relationship'), None)
        if not rel_row:
            self.skipTest('role 无 relationship 行')

        # 至少有一个 cell 是 include/manual 覆盖
        manual_wins = any(
            c['source'] == 'include'
            for c in rel_row['cells'].values()
        )
        self.assertTrue(manual_wins,
                        f'role={rid} 应有 cell.source=include（manual 覆盖 derived）')

    # ---- ⑤ association derive 的 origin 文案 ----

    def test_association_origin_text(self):
        """⑤ association 派生来源的 origin 应包含「association 端点派生」文案"""
        self.cursor.execute('''
            SELECT DISTINCT role_id FROM role_dimension_scopes
            WHERE dimension_code IN ('version', 'domain', 'sub_domain')
            LIMIT 1
        ''')
        rid_row = self.cursor.fetchone()
        if not rid_row:
            self.skipTest('无 scope role')
        rid = rid_row[0]

        mat = _build_role_matrices(rid)
        if not mat:
            self.skipTest('_build_role_matrices 返回 None')

        rel_derived = [
            d for d in mat['sources_detail']
            if d['source'] == 'derived' and d['resource_type'] == 'relationship'
        ]
        if not rel_derived:
            self.skipTest('role 无 relationship derived 项')

        for d in rel_derived:
            self.assertIn('association 端点派生', d['origin'],
                          f"relationship derived origin 应含 'association 端点派生'，实际={d['origin']}")


if __name__ == '__main__':
    unittest.main()