"""
test_key_template_interceptor_rel.py
[NEW 2026-06-10] BUG-1 回归测试

BUG 描述：
  关系（relationship）创建时，key template pattern 形如
  `{source_code}-{target_code}-{SEQ:2}`，但 interceptor 解析
  source_code/target_code 时，base_type='source'/'target'，
  对应的物理表是 business_objects，导致解析失败，code 生成
  成 "--02"（只有分隔符 + 序号）。

修复：
  1. 兼容 `source_bo_id` / `target_bo_id` 字段（替换 `_code` 后再加 `_bo_id`）
  2. 对 source_bo_id/target_bo_id 强制查 business_objects 表

覆盖矩阵（8 个用例）：

  基本解析
   1. test_resolve_source_code_from_business_objects
   2. test_resolve_target_code_from_business_objects
   3. test_resolve_both_source_and_target

  端到端 code 生成
   4. test_relationship_code_ends_with_sequence
   5. test_relationship_sequence_increments_per_pair
   6. test_relationship_priority_value_unchanged

  边界
   7. test_relationship_skips_when_code_provided
   8. test_relationship_skips_when_bo_id_invalid
"""

import pytest
import os
import tempfile

from meta.core.datasource import get_data_source
from meta.core.models import MetaObject
from meta.core.action_context import ActionContext
from meta.core.key_template_engine import KeyTemplateEngine
from meta.core.interceptors.key_template_interceptor import KeyTemplateInterceptor


pytestmark = pytest.mark.unit


class TestRelationshipKeyTemplate:
    """BUG-1 回归测试：REL key template 解析 source_bo_id/target_bo_id"""

    def setup_method(self):
        self.db_path = os.path.join(tempfile.gettempdir(), f"test_kt_rel_{os.getpid()}_{id(self)}.db")
        self.ds = get_data_source("sqlite", database=self.db_path)

        # 🆕 准备 business_objects 表（REL 的 source/target 引用此表）
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS business_objects (
                id INTEGER PRIMARY KEY,
                code TEXT,
                name TEXT
            )
        """)
        self.ds.execute("""
            INSERT INTO business_objects (id, code, name) VALUES
                (10, 'BO_A', 'BO A'),
                (20, 'BO_B', 'BO B'),
                (30, 'BO_C', 'BO C')
        """)
        self.ds.commit()

        # 准备 relationships 表（让 interceptor 识别为物理表）
        self.ds.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY,
                code TEXT,
                name TEXT,
                source_bo_id INTEGER,
                target_bo_id INTEGER
            )
        """)
        self.ds.commit()

        self.engine = KeyTemplateEngine(self.ds)
        self.interceptor = KeyTemplateInterceptor(engine=self.engine)

    def teardown_method(self):
        try:
            self.ds.disconnect()
            os.unlink(self.db_path)
        except Exception:
            pass

    def _make_rel_context(self, params):
        """构造 relationship 的 MetaObject（key_template: {source_code}-{target_code}-{SEQ:2}）"""
        meta_object = MetaObject(
            id="relationship",
            name="relationship",
            table_name="relationships",
            key_template={
                "enabled": True,
                "auto_suggest": True,
                "pattern": "{source_code}-{target_code}-{SEQ:2}",
                "segments": [
                    {"type": "parent_field", "source": "source_code"},
                    {"type": "separator", "value": "-"},
                    {"type": "parent_field", "source": "target_code"},
                    {"type": "separator", "value": "-"},
                    {
                        "type": "sequence",
                        "name": "rel_seq",
                        "scope": "source_bo_id,target_bo_id",  # pair 级别
                        "auto_detect": False,
                        "padding": 2,
                        "start": 1,
                    },
                ],
            },
        )
        return ActionContext(
            meta_object=meta_object,
            action="crud_create",
            params=dict(params),
            data_source=self.ds,
        )

    # ===== 解析层 =====

    def test_resolve_source_code_from_business_objects(self):
        """source_code 解析自 business_objects.code (by source_bo_id)"""
        ctx = self._make_rel_context({
            "name": "Rel1",
            "source_bo_id": 10,
            "target_bo_id": 20,
        })
        self.interceptor.before_action(ctx)
        # BUG-1 修复后应正确解析 source_code=BO_A, target_code=BO_B
        assert ctx.params["code"] is not None, "code 未生成"
        code = ctx.params["code"]
        # 不应该是 '--02'（修复前症状）
        assert not code.startswith("--"), f"BUG-1 复发：code={code}"
        assert "BO_A" in code, f"source_code 未解析：{code}"
        assert "BO_B" in code, f"target_code 未解析：{code}"

    def test_resolve_target_code_from_business_objects(self):
        """target_code 解析自 business_objects.code (by target_bo_id)"""
        ctx = self._make_rel_context({
            "name": "Rel2",
            "source_bo_id": 10,
            "target_bo_id": 30,  # BO_C
        })
        self.interceptor.before_action(ctx)
        code = ctx.params.get("code", "")
        assert "BO_C" in code, f"target_code=BO_C 未解析：{code}"
        assert "BO_A" in code, f"source_code=BO_A 未解析：{code}"

    def test_resolve_both_source_and_target(self):
        """source + target 同时解析"""
        ctx = self._make_rel_context({
            "name": "Rel3",
            "source_bo_id": 20,  # BO_B
            "target_bo_id": 30,  # BO_C
        })
        self.interceptor.before_action(ctx)
        code = ctx.params.get("code", "")
        # 预期：BO_B-BO_C-01
        assert code.startswith("BO_B-BO_C-"), f"code 模式错误：{code}"
        # 序号以 01 结尾
        assert code.endswith("01"), f"序号起始应为 01：{code}"

    # ===== 端到端 =====

    def test_relationship_code_ends_with_sequence(self):
        """完整 code 格式：{source_code}-{target_code}-{SEQ:2}"""
        ctx = self._make_rel_context({
            "name": "Rel4",
            "source_bo_id": 10,
            "target_bo_id": 20,
        })
        self.interceptor.before_action(ctx)
        code = ctx.params.get("code", "")
        # 期望：BO_A-BO_B-01
        assert code == "BO_A-BO_B-01", f"完整 code 不匹配：{code}"

    def test_relationship_sequence_increments_per_pair(self):
        """同一对 (source, target) 创建多次，序列递增"""
        # 第一次
        ctx1 = self._make_rel_context({
            "name": "Rel5a",
            "source_bo_id": 10,
            "target_bo_id": 20,
        })
        self.interceptor.before_action(ctx1)
        # 第二次（同对）
        ctx2 = self._make_rel_context({
            "name": "Rel5b",
            "source_bo_id": 10,
            "target_bo_id": 20,
        })
        self.interceptor.before_action(ctx2)
        # 第三次
        ctx3 = self._make_rel_context({
            "name": "Rel5c",
            "source_bo_id": 10,
            "target_bo_id": 20,
        })
        self.interceptor.before_action(ctx3)

        code1 = ctx1.params.get("code", "")
        code2 = ctx2.params.get("code", "")
        code3 = ctx3.params.get("code", "")
        assert code1.endswith("01"), f"第1次应为 01：{code1}"
        assert code2.endswith("02"), f"第2次应为 02：{code2}"
        assert code3.endswith("03"), f"第3次应为 03：{code3}"

    def test_relationship_priority_value_unchanged(self):
        """BUG-1 修复不应影响 interceptor.priority"""
        assert self.interceptor.priority == 45

    # ===== 边界 =====

    def test_relationship_skips_when_code_provided(self):
        """用户提供了 code 时，interceptor 不覆盖"""
        ctx = self._make_rel_context({
            "name": "Rel6",
            "source_bo_id": 10,
            "target_bo_id": 20,
            "code": "MY_CUSTOM_REL",
        })
        self.interceptor.before_action(ctx)
        assert ctx.params["code"] == "MY_CUSTOM_REL"

    def test_relationship_skips_when_bo_id_invalid(self):
        """source_bo_id 无效时，interceptor 不抛异常且不生成 code"""
        # source_bo_id=999 不存在
        ctx = self._make_rel_context({
            "name": "Rel7",
            "source_bo_id": 999,
            "target_bo_id": 20,
        })
        # 不应抛异常
        self.interceptor.before_action(ctx)
        # [UPDATED 2026-06-11] parent_field 无法解析时，engine 返回 None，
        # interceptor 不设置 code → params 中不应有 code 字段
        # 原断言：assert "code" in ctx.params（允许空值）
        # 新断言：code 不存在于 params（未设置 = 不生成裸序列号）
        # 这比之前更安全：前端收到 422 而非脏 code
        assert ctx.params.get("code") is None or ctx.params.get("code") == "", (
            f"bo_id 无效时不应生成 code，实际: {ctx.params.get('code')}"
        )
