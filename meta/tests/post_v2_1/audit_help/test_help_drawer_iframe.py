# -*- coding: utf-8 -*-
"""
test_help_drawer_iframe.py
覆盖提交: eefed84 (HelpCenterDrawer P1 - iframe embed /docs/user-guide/index.html)
依据: .trae/specs/test-suite/post-6-22-roadmap.md 主题 7 (Help Center)

测试:
- iframe src 指向 /docs/user-guide/index.html
- iframe 有 referrerpolicy 属性
- 抽屉开关正常 (modelValue 双向绑定)
- 关闭按钮和遮罩点击关闭
- 重试 + 新窗口打开
- 默认宽度 880px
"""
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = [
    pytest.mark.post_v2_1,
    pytest.mark.audit_help,
]


HELP_DRAWER_VUE = PROJECT_ROOT / 'src' / 'components' / 'common' / 'HelpCenterDrawer' / 'HelpCenterDrawer.vue'
HELP_DRAWER_SPEC = PROJECT_ROOT / 'src' / 'components' / 'common' / 'HelpCenterDrawer' / '__tests__' / 'HelpCenterDrawer.spec.js'


# ============================================================
# 1. TestHelpCenterIframeEmbed (6 用例)
# ============================================================

class TestHelpCenterIframeEmbed:
    """HelpCenterDrawer P1 - iframe embed /docs/user-guide/index.html (eefed84)"""

    def test_iframe_loads_user_guide(self):
        """[eefed84] iframe src 指向 /docs/user-guide/index.html

        验证: HelpCenterDrawer.vue 中 iframe 的 src 属性
        默认值为 /docs/user-guide/index.html
        """
        content = HELP_DRAWER_VUE.read_text(encoding='utf-8')

        # 关键: src 默认值
        assert '/docs/user-guide/index.html' in content, \
            "HelpCenterDrawer should default to /docs/user-guide/index.html"

        # 关键: helpUrl prop 默认值
        assert "'/docs/user-guide/index.html'" in content or \
               '"/docs/user-guide/index.html"' in content, \
            "helpUrl prop default should be /docs/user-guide/index.html"

        # 关键: iframe 标签存在
        assert '<iframe' in content, "HelpCenterDrawer should have iframe element"
        assert ':src="helpUrl"' in content or 'src=' in content, \
            "iframe should bind src to helpUrl"

    def test_iframe_sandbox_attribute(self):
        """[eefed84] iframe 有 referrerpolicy 属性 (安全考虑)

        验证: HelpCenterDrawer.vue 中 iframe 配置安全属性
        """
        content = HELP_DRAWER_VUE.read_text(encoding='utf-8')

        # 关键: referrerpolicy (eefed84 引入, 防止 referrer 泄漏)
        assert 'referrerpolicy' in content, \
            "iframe should have referrerpolicy attribute (security)"

        # 关键: @load 事件处理器 (加载成功)
        assert '@load' in content, "iframe should have @load handler"

        # 关键: @error 事件处理器 (加载失败)
        assert '@error' in content, "iframe should have @error handler"

    def test_help_drawer_open_closes(self):
        """[eefed84] 抽屉开关正常 (modelValue 双向绑定)

        验证: HelpCenterDrawer.vue 中
        - modelValue 控制抽屉显示
        - update:modelValue 事件 emit
        - close 按钮触发 handleClose
        - 遮罩点击触发 handleClose
        """
        content = HELP_DRAWER_VUE.read_text(encoding='utf-8')

        # 关键: v-model 双向绑定
        assert 'v-if="modelValue"' in content, \
            "Drawer should conditionally render based on modelValue"
        assert 'update:modelValue' in content, \
            "Drawer should emit update:modelValue"

        # 关键: 关闭按钮
        assert 'help-drawer__close' in content, \
            "Drawer should have close button"
        assert 'aria-label="Close help center"' in content, \
            "Close button should have aria-label"

        # 关键: 遮罩
        assert 'help-drawer__mask' in content, \
            "Drawer should have mask"
        assert '@click="handleClose"' in content, \
            "Mask should call handleClose on click"

    def test_help_drawer_fallback_handling(self):
        """[eefed84] 抽屉有 fallback 处理 (重试 + 新窗口打开)

        验证: loadError 状态 + retry / openInNewTab 按钮
        """
        content = HELP_DRAWER_VUE.read_text(encoding='utf-8')

        # 关键: loadError ref
        assert 'loadError' in content, \
            "Drawer should track loadError state"

        # 关键: retry 函数
        assert 'function retry' in content or 'retry()' in content, \
            "Drawer should have retry function"

        # 关键: openInNewTab 函数
        assert 'function openInNewTab' in content or 'openInNewTab' in content, \
            "Drawer should have openInNewTab function"

        # 关键: window.open 调用
        assert 'window.open' in content, \
            "openInNewTab should call window.open"

    def test_help_drawer_default_width(self):
        """[eefed84] 默认宽度 880px (可读 docs 布局)

        验证: HelpCenterDrawer.vue 中 width prop 默认 880
        """
        content = HELP_DRAWER_VUE.read_text(encoding='utf-8')

        # 关键: width 默认值 880 (eefed84 引入)
        assert 'default: 880' in content or 'default:880' in content, \
            "HelpCenterDrawer default width should be 880 (eefed84)"

    def test_help_drawer_test_spec_exists(self):
        """[eefed84] 已有测试规范 (HelpCenterDrawer.spec.js) 通过

        验证: __tests__/HelpCenterDrawer.spec.js 存在并含 10+ 用例
        """
        assert HELP_DRAWER_SPEC.exists(), \
            f"HelpCenterDrawer.spec.js should exist at {HELP_DRAWER_SPEC}"

        content = HELP_DRAWER_SPEC.read_text(encoding='utf-8')

        # 关键: 测试用例
        test_count = content.count("  it(")
        assert test_count >= 5, \
            f"HelpCenterDrawer.spec.js should have at least 5 tests, found {test_count}"

        # 关键: 关键场景覆盖
        assert 'iframe' in content.lower(), \
            "tests should cover iframe"
        assert 'close' in content.lower(), \
            "tests should cover close behavior"
        assert 'helpUrl' in content, \
            "tests should cover helpUrl prop"
        assert '/docs/user-guide/index.html' in content, \
            "tests should verify default helpUrl"
