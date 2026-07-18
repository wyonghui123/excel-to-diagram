"""
BaseRegressionTestCase - 回归测试基类 (Phase 7 重构)

提供:
- bug_id 标记 (用于 pytest -m)
- fixed_in_version 记录
- 统一的 fix verification 流程
"""
import pytest


class BaseRegressionTestCase:
    """
    回归测试基类

    子类设置:
        bug_id = 'V020'             # BUG 编号
        bug_title = 'description'   # BUG 简述
        fixed_in_version = '3.18.0' # 修复版本

    自动生成 pytest mark:
        @pytest.mark.regression
        @pytest.mark.bug_V020
    """

    bug_id: str = None
    bug_title: str = ''
    fixed_in_version: str = ''

    @pytest.fixture(autouse=True)
    def _setup_regression_meta(self, request):
        """附加 BUG 元信息到测试节点"""
        if self.bug_id:
            # 允许用 -m 'regression' 或 -m 'bug_V020' 过滤
            bug_marker = getattr(pytest.mark, f'bug_{self.bug_id.lower().replace(".", "_")}')
            request.node.add_marker(pytest.mark.regression)
            request.node.add_marker(bug_marker)

    def verify_fix(self, check_fn, description: str = ''):
        """统一的 fix verification 助手"""
        try:
            result = check_fn()
            assert result, f"BUG-{self.bug_id} fix verification failed: {description}"
            return True
        except AssertionError as e:
            pytest.fail(f"BUG-{self.bug_id} REGRESSED: {e}")


# ==================== Pytest Markers 注册 ====================
# 在 conftest.py 的 pytest_configure 中应添加:
#   "regression": "BUG regression test",
#   "bug_v020", "bug_v021", ... "bug_v027", "bug_v038"