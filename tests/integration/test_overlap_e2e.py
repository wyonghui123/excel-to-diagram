# -*- coding: utf-8 -*-
r"""
M3.1 集成测试 — 重复配置警告端到端

测试覆盖：
1. 检测器端到端
2. API 端点注册（不需要服务运行）
3. 前端 composable 语法检查
4. 前端组件语法检查

通过 test.py 入口运行：
    python d:\filework\test.py --file d:\filework\excel-to-diagram\tests\integration\test_overlap_e2e.py
"""
import sys
import os
import json
import sqlite3
import unittest
import re

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.feature_flags import set_flag, clear_cache
from meta.core.dim_scope_overlap_detector import get_overlap_detector


class TestOverlapE2E(unittest.TestCase):
    """重复配置警告端到端集成测试"""

    TEST_ROLE_ID = 995

    @classmethod
    def setUpClass(cls):
        cls.detector = get_overlap_detector()
        cls._setup_test_data()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_test_data()

    @classmethod
    def _setup_test_data(cls):
        conn = sqlite3.connect(cls.detector._db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM roles WHERE id = 995 LIMIT 1")
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO roles (id, name, code, description, is_system)
                VALUES (995, 'E2E Overlap Test', 'e2e_overlap', 'E2E test', 0)
            """)
        cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 995")
        cursor.execute("DELETE FROM permission_rules WHERE role_id = 995")

        # Section 1: domain=[1, 2, 3, 4]
        cursor.execute("""
            INSERT INTO role_dimension_scopes
            (role_id, dimension_code, dimension_values, inherit_children, scope_mode, bo_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (995, 'domain', json.dumps([1, 2, 3, 4]), 1, 'include', None))

        # Section 3: 配 2 条 rule 模拟重叠场景
        cursor.execute("""
            INSERT INTO permission_rules
            (role_id, resource_type, condition, permission_level, is_denied,
             inherit_to_children, propagate_to_parents, analysis_mode,
             created_at, created_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, datetime('now'))
        """, (
            995, 'domain',
            json.dumps({'field': 'domain', 'operator': 'in', 'value': [2, 3, 5]}),
            'read', 0, 1, 0, 'value', 1,
        ))
        cursor.execute("""
            INSERT INTO permission_rules
            (role_id, resource_type, condition, permission_level, is_denied,
             inherit_to_children, propagate_to_parents, analysis_mode,
             created_at, created_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, datetime('now'))
        """, (
            995, 'domain',
            json.dumps({'field': 'domain', 'operator': 'eq', 'value': 3}),
            'read', 0, 1, 0, 'value', 1,
        ))
        conn.commit()
        conn.close()

    @classmethod
    def _cleanup_test_data(cls):
        conn = sqlite3.connect(cls.detector._db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 995")
        cursor.execute("DELETE FROM permission_rules WHERE role_id = 995")
        cursor.execute("DELETE FROM roles WHERE id = 995")
        conn.commit()
        conn.close()

    def setUp(self):
        clear_cache()
        set_flag('ENABLE_DUP_CONFIG_WARNING', True)

    # ---- 端到端检测流程 ----

    def test_01_e2e_detect_overlaps(self):
        """测试：端到端检测重叠"""
        overlaps = self.detector.detect_overlaps(995)
        self.assertEqual(len(overlaps), 1)
        overlap = overlaps[0]
        self.assertEqual(overlap['field'], 'domain')
        # 2 条 rule 都重叠
        self.assertEqual(overlap['count'], 2)

    def test_02_e2e_intersection_values(self):
        """测试：交集值正确"""
        overlaps = self.detector.detect_overlaps(995)
        overlap = overlaps[0]
        intersections = sorted([
            r['intersection'] for r in overlap['rules']
        ])
        # 2, 3 都在 [1,2,3,4] ∩ [2,3,5] = [2,3]
        # 3 在 [1,2,3,4] ∩ [3] = [3]
        self.assertIn([2, 3], intersections)
        self.assertIn([3], intersections)

    def test_03_e2e_summary(self):
        """测试：摘要接口数据正确"""
        summary = self.detector.get_overlap_summary(995)
        self.assertTrue(summary['has_overlap'])
        self.assertEqual(summary['count'], 1)
        self.assertIn('domain', summary['fields'])

    # ---- API 端点注册 ----

    def test_04_api_blueprint_registered(self):
        """测试：overlap_bp 已在 server.py 注册"""
        with open('d:/filework/excel-to-diagram/meta/server.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证 import
        self.assertIn(
            "from meta.api.overlap_api import overlap_bp",
            content,
            "overlap_bp 未在 server.py 中 import"
        )
        # 验证 register
        self.assertIn(
            "app.register_blueprint(overlap_bp)",
            content,
            "overlap_bp 未在 server.py 中注册"
        )

    def test_05_api_endpoints_defined(self):
        """测试：API 端点定义完整"""
        with open('d:/filework/excel-to-diagram/meta/api/overlap_api.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证端点
        self.assertIn(
            "<int:role_id>/overlaps",
            content,
            "GET /overlaps 端点缺失"
        )
        self.assertIn(
            "<int:role_id>/overlaps/summary",
            content,
            "GET /overlaps/summary 端点缺失"
        )

    # ---- 前端 composable ----

    def test_06_useoverlaps_exists(self):
        """测试：useOverlaps composable 文件存在"""
        path = 'd:/filework/excel-to-diagram/src/composables/useOverlaps.ts'
        self.assertTrue(os.path.exists(path), f"文件不存在: {path}")

    def test_07_useoverlaps_syntax(self):
        """测试：useOverlaps 语法检查"""
        path = 'd:/filework/excel-to-diagram/src/composables/useOverlaps.ts'
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证 export
        self.assertIn("export function useOverlaps", content)
        # 验证 import
        self.assertIn("import { ref } from 'vue'", content)
        # 验证主要方法
        for method in ['loadOverlaps', 'loadSummary', 'hasOverlap',
                       'getOverlapForField', 'getOverlapHint']:
            self.assertIn(method, content, f"方法 {method} 缺失")

    def test_08_overlapwarning_component_exists(self):
        """测试：OverlapWarning 组件文件存在"""
        path = 'd:/filework/excel-to-diagram/src/views/SystemManagement/components/OverlapWarning.vue'
        self.assertTrue(os.path.exists(path), f"文件不存在: {path}")

    def test_09_overlapwarning_syntax(self):
        """测试：OverlapWarning 组件语法检查"""
        path = 'd:/filework/excel-to-diagram/src/views/SystemManagement/components/OverlapWarning.vue'
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 验证 template
        self.assertIn("<template>", content)
        self.assertIn("</template>", content)
        # 验证 script
        self.assertIn("<script", content)
        # 验证 style
        self.assertIn("<style", content)
        # 验证 YonDesign 规范（使用 CSS 变量）
        self.assertIn("var(--color-", content, "未使用 CSS 变量")
        # 验证无硬编码颜色
        self.assertNotRegex(content, r'#[0-9a-fA-F]{6}', "包含硬编码颜色")

    def test_10_no_hardcoded_colors_in_components(self):
        """测试：所有相关组件无硬编码颜色"""
        files = [
            'd:/filework/excel-to-diagram/src/composables/useOverlaps.ts',
            'd:/filework/excel-to-diagram/src/views/SystemManagement/components/OverlapWarning.vue',
        ]
        for f in files:
            with open(f, 'r', encoding='utf-8') as fp:
                content = fp.read()
            # 检查硬编码颜色（但允许纯数字）
            hex_pattern = re.compile(r'#[0-9a-fA-F]{3,8}')
            matches = hex_pattern.findall(content)
            for m in matches:
                # 排除正常用例（如 i18n key 中含 #）
                # 简单粗暴：跳过在字符串中的 # 后跟 6 位 hex
                if re.match(r'^#[0-9a-fA-F]{6}$', m):
                    self.fail(f"{f} 含硬编码颜色: {m}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
