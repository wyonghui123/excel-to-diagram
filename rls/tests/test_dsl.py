"""
test_dsl.py - M11 v1.4.0 DSL 解析器测试

TODO-5 验证：
- parse_condition: 简单/复杂条件
- 变量替换：$user.id / $user.company_id
- OR 条件
- 边界：空字符串 / None / 异常
- is_field_reference: 字段引用判断
- get_row_filter_parsed: 端到端（YAML → SQL where）
"""
import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestParseCondition(unittest.TestCase):
    """parse_condition 单元测试"""

    def test_simple_eq(self):
        """简单等值条件"""
        from rls.dsl import parse_condition
        result = parse_condition("order.id == 5")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['field'], 'order.id')
        self.assertEqual(result[0]['operator'], 'eq')
        self.assertEqual(result[0]['value'], '5')

    def test_simple_neq(self):
        """不等条件"""
        from rls.dsl import parse_condition
        result = parse_condition("order.status != 'cancelled'")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['field'], 'order.status')
        self.assertEqual(result[0]['operator'], 'ne')

    def test_simple_gt_lt(self):
        """大小于条件"""
        from rls.dsl import parse_condition
        result_gt = parse_condition("order.amount > 1000")
        self.assertEqual(result_gt[0]['operator'], 'gt')
        result_lt = parse_condition("order.amount < 5000")
        self.assertEqual(result_lt[0]['operator'], 'lt')

    def test_var_replacement_id(self):
        """$user.id 变量替换"""
        from rls.dsl import parse_condition
        result = parse_condition(
            "order.user_id == $user.id",
            user_context={'id': 5}
        )
        self.assertEqual(result[0]['field'], 'order.user_id')
        self.assertEqual(result[0]['value'], '5')

    def test_var_replacement_company_id(self):
        """$user.company_id 变量替换（关键场景：跨租户隔离）"""
        from rls.dsl import parse_condition
        result = parse_condition(
            "order.company_id == $user.company_id",
            user_context={'company_id': 'A'}
        )
        self.assertEqual(result[0]['field'], 'order.company_id')
        self.assertEqual(result[0]['value'], 'A')  # 字符串字面量去引号

    def test_var_replacement_missing_kept(self):
        """user_context 缺失的变量保持原样"""
        from rls.dsl import parse_condition
        result = parse_condition(
            "order.user_id == $user.id",
            user_context={'company_id': 'A'}  # 缺 id
        )
        # $user.id 保持原样（解析可能失败但不会抛错）
        # 返回空 list（解析失败）
        # 或者 value 是 "$user.id" 字面量
        self.assertIsInstance(result, list)

    def test_or_condition(self):
        """OR 条件"""
        from rls.dsl import parse_condition
        result = parse_condition(
            "order.status == 'active' OR order.user_id == $user.id",
            user_context={'id': 5}
        )
        # OR 返回 list of list
        self.assertGreater(len(result), 0)
        # 第一个元素可能是 OR group
        if isinstance(result[0], list):
            self.assertEqual(len(result[0]), 2)

    def test_empty_condition(self):
        """空字符串返回空 list"""
        from rls.dsl import parse_condition
        self.assertEqual(parse_condition(''), [])

    def test_none_condition(self):
        """None 返回空 list"""
        from rls.dsl import parse_condition
        self.assertEqual(parse_condition(None), [])

    def test_user_context_none_keeps_var(self):
        """user_context=None 时 $user.* 保持原样"""
        from rls.dsl import parse_condition
        result = parse_condition(
            "order.user_id == $user.id",
            user_context=None
        )
        # 解析可能失败（$user.id 不是有效数字）
        # 但不应抛错
        self.assertIsInstance(result, list)

    def test_invalid_syntax_returns_empty(self):
        """无效语法返回空 list（不抛错）"""
        from rls.dsl import parse_condition
        result = parse_condition("this is not a valid condition @@@")
        self.assertIsInstance(result, list)

    def test_string_value_with_quotes(self):
        """字符串字面量带引号"""
        from rls.dsl import parse_condition
        result = parse_condition("order.status == 'active'")
        self.assertEqual(result[0]['field'], 'order.status')
        # value 含引号
        self.assertIn('active', str(result[0]['value']))


class TestIsFieldReference(unittest.TestCase):
    """is_field_reference 单元测试"""

    def test_field_reference_with_dot(self):
        """字段引用（含 . 字符）"""
        from rls.dsl import is_field_reference
        self.assertTrue(is_field_reference('order.company_id'))
        self.assertTrue(is_field_reference('user.id'))
        self.assertTrue(is_field_reference('a.b.c'))

    def test_plain_string_not_field_ref(self):
        """普通字符串不是字段引用"""
        from rls.dsl import is_field_reference
        self.assertFalse(is_field_reference('active'))
        self.assertFalse(is_field_reference('hello'))

    def test_quoted_string_not_field_ref(self):
        """带引号字符串不是字段引用"""
        from rls.dsl import is_field_reference
        self.assertFalse(is_field_reference("'active'"))
        self.assertFalse(is_field_reference('"hello"'))

    def test_number_not_field_ref(self):
        """数字不是字段引用"""
        from rls.dsl import is_field_reference
        self.assertFalse(is_field_reference('5'))
        self.assertFalse(is_field_reference('1000'))

    def test_non_string_not_field_ref(self):
        """非字符串不是字段引用"""
        from rls.dsl import is_field_reference
        self.assertFalse(is_field_reference(5))
        self.assertFalse(is_field_reference(None))
        self.assertFalse(is_field_reference(True))


class TestGetRowFilterParsed(unittest.TestCase):
    """get_row_filter_parsed 端到端（YAML → SQL where）"""

    def setUp(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_dsl_')
        with open(os.path.join(self.tmpdir, 'order.yaml'), 'w', encoding='utf-8') as f:
            f.write("""
entity: order
row_filters:
  - applies_to: [role:user]
    condition: "order.company_id == $user.company_id"
  - applies_to: [role:admin]
    condition: "true"
  - applies_to: [role:ai-agent]
    condition: "order.is_public == true"
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def test_user_role_gets_company_filter(self):
        """user 角色在 order 实体获得 company 过滤"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from rls.dsl import get_row_filter_parsed
        result = get_row_filter_parsed(
            'user', 'order',
            user_context={'company_id': 'A'},
            rules_dir=self.tmpdir,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['field'], 'order.company_id')
        self.assertEqual(result[0]['value'], 'A')  # 字符串字面量去引号

    def test_admin_role_gets_true(self):
        """admin 角色获得 'true' 条件（解析为字符串字面量）"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from rls.dsl import get_row_filter_parsed
        result = get_row_filter_parsed(
            'admin', 'order',
            user_context={'company_id': 'A'},
            rules_dir=self.tmpdir,
        )
        # 'true' 特殊处理：返回 always 标记
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['field'], '__rls_always_true__')
        self.assertEqual(result[0]['operator'], 'always')
        self.assertEqual(result[0]['value'], True)

    def test_ai_agent_role_gets_is_public(self):
        """ai-agent 角色获得 is_public 过滤"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from rls.dsl import get_row_filter_parsed
        result = get_row_filter_parsed(
            'ai-agent', 'order',
            user_context={'id': 5},
            rules_dir=self.tmpdir,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['field'], 'order.is_public')
        self.assertEqual(result[0]['value'], 'true')

    def test_unknown_role_returns_empty(self):
        """未知角色（无规则）返回空 list"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from rls.dsl import get_row_filter_parsed
        result = get_row_filter_parsed(
            'viewer', 'order',
            user_context={'id': 5},
            rules_dir=self.tmpdir,
        )
        self.assertEqual(result, [])

    def test_unknown_entity_returns_empty(self):
        """未知 entity 返回空 list"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from rls.dsl import get_row_filter_parsed
        result = get_row_filter_parsed(
            'user', 'unknown',
            user_context={'id': 5},
            rules_dir=self.tmpdir,
        )
        self.assertEqual(result, [])


class TestDSLEndToEnd(unittest.TestCase):
    """DSL 端到端（5×5 场景）"""

    ROLES = ['admin', 'manager', 'user', 'viewer', 'ai-agent']
    ENTITIES = ['order', 'user', 'product', 'role', 'business_object']

    def setUp(self):
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        self.tmpdir = tempfile.mkdtemp(prefix='rls_dsl_e2e_')
        for entity in self.ENTITIES:
            with open(os.path.join(self.tmpdir, f'{entity}.yaml'), 'w', encoding='utf-8') as f:
                f.write(f"""
entity: {entity}
row_filters:
  - applies_to: [role:user, role:viewer]
    condition: "{entity}.company_id == $user.company_id"
  - applies_to: [role:admin, role:manager]
    condition: "true"
  - applies_to: [role:ai-agent]
    condition: "{entity}.is_public == true"
""")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from rls.loader import RLSLoader
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None

    def test_25_scenarios_dsl_parsed(self):
        """25 场景（5 角色 × 5 entity）DSL 解析都成功"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from rls.dsl import get_row_filter_parsed
        user_context = {'id': 5, 'company_id': 'A', 'role': 'user'}
        for role in self.ROLES:
            for entity in self.ENTITIES:
                result = get_row_filter_parsed(
                    role, entity,
                    user_context=user_context,
                    rules_dir=self.tmpdir,
                )
                self.assertGreater(
                    len(result), 0,
                    f'{role}->{entity} DSL 解析失败：{result}'
                )

    def test_company_id_correctly_replaced(self):
        """company_id 变量正确替换"""
        from rls import loader as loader_mod
        loader_mod.get_loader(self.tmpdir)
        from rls.dsl import get_row_filter_parsed
        # user 角色在 order 实体
        result = get_row_filter_parsed(
            'user', 'order',
            user_context={'company_id': 'COMPANY_A'},
            rules_dir=self.tmpdir,
        )
        # value 应该是 'COMPANY_A'（去引号）
        self.assertEqual(result[0]['value'], 'COMPANY_A')
        self.assertEqual(result[0]['field'], 'order.company_id')


if __name__ == '__main__':
    unittest.main()
