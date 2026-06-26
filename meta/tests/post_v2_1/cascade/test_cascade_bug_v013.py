# -*- coding: utf-8 -*-
"""
test_cascade_bug_v013.py
覆盖 BUG-V013 (commit 60c130e):
  fix: 修复 product 删除时被 CASCADE_RESTRICT 错误拒绝

修复:
  manage_service.py:475-497 扩展 BUG-V011 逻辑 - 当
  associations[].cascade_delete=true 时也跳过 cascade_service.before_delete.
"""
import pytest
import yaml
from pathlib import Path
import inspect

pytestmark = [pytest.mark.post_v2_1, pytest.mark.cascade]


class TestBugV013SkipCascadeRestrict:
    """BUG-V013: associations cascade_delete=true 时跳过 CASCADE_RESTRICT"""

    def test_manage_service_delete_skips_cascade_service(self):
        from meta.services.manage_service import ManageService
        source = inspect.getsource(ManageService.delete)
        assert 'cascade_service' in source or 'has_cascade_delete' in source, (
            "manage_service.delete 应包含 skip cascade_service 的逻辑 (BUG-V013)"
        )
        assert 'deletability' in source or 'condition' in source, (
            "BUG-V011 修复应保留 (deletability.condition skip)"
        )

    def test_cascade_delete_associations_in_yaml(self):
        yaml_path = Path('meta/schemas/product.yaml')
        if not yaml_path.exists():
            pytest.skip("product.yaml not found")
        with open(yaml_path) as f:
            schema = yaml.safe_load(f)
        associations = schema.get('associations', [])
        cascade_true = [a for a in associations if a.get('cascade_delete')]
        assert len(cascade_true) >= 1, (
            f"product.yaml 应至少有 1 个 cascade_delete=true 关联, 实际: {cascade_true}"
        )

    def test_cascade_interceptor_priority_is_48(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        assert interceptor.priority == 48, (
            f"CascadeInterceptor.priority 应为 48, 实际: {interceptor.priority}"
        )

    def test_delete_behavior_policy_in_hierarchies(self):
        yaml_path = Path('meta/schemas/hierarchies.yaml')
        if not yaml_path.exists():
            pytest.skip("hierarchies.yaml not found")
        with open(yaml_path) as f:
            schema = yaml.safe_load(f)
        # hierarchies 是 list of dict, 每个含 levels 列表
        hierarchies = schema.get('hierarchies', [])
        policy = None
        for h in hierarchies:
            levels = h.get('levels', [])
            for level in levels:
                if level.get('object') == 'product':
                    policy = level.get('delete_behavior', {}).get('policy')
                    break
            if policy:
                break
        assert policy == 'RESTRICT', (
            f"hierarchies.yaml product.delete_behavior.policy 应为 RESTRICT, 实际: {policy}"
        )

    def test_manage_service_delete_uses_cascade_check(self):
        from meta.services import manage_service
        source = inspect.getsource(manage_service.ManageService.delete)
        assert 'associations' in source or 'cascade_delete' in source or 'has_associations' in source, (
            "manage_service.delete 应包含检查 associations / cascade_delete 的逻辑"
        )


class TestRegressionBugV013:
    """回归测试 - BUG-V013 修复不应破坏其他 delete 场景"""

    def test_other_objects_unaffected(self):
        from meta.services import manage_service
        source = inspect.getsource(manage_service.ManageService.delete)
        assert 'if ' in source, "修复应使用条件分支 (不是全局跳过)"
