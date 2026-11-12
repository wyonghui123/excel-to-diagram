# -*- coding: utf-8 -*-
"""
test_help_drawer_iframe.py
覆盖: HelpCenterDrawer P3 简化版 (2026-06-30)
依据: .trae/specs/test-suite/post-6-22-roadmap.md 主题 7 (Help Center)

P3 变更 (取代 eefed84 的 iframe embed):
- 删除 iframe / <docs/user-guide/index.html> 嵌入, 改用 HelpAccordion 组件
- 删除 "章节手册" tab: 只保留 "操作场景"
- 新增最大化/还原按钮
- 新增 initialStep prop: 由父组件从 URL (?help=&step=) 解析传入

测试:
- 抽屉内嵌 HelpAccordion (不再有 iframe)
- initialStep prop + Escape 键处理
- 最大化/还原逻辑
- 抽屉开关正常 (modelValue 双向绑定)
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
    """HelpCenterDrawer P3 - HelpAccordion 内嵌 (取代 P1 的 iframe)"""

    def test_iframe_loads_user_guide(self):
        """[P3 2026-06-30] 抽屉正文改为 HelpAccordion, 不再嵌入 iframe

        验证: HelpCenterDrawer.vue 使用 HelpAccordion, 且无 iframe 残留
        """
        content = HELP_DRAWER_VUE.read_text(encoding='utf-8')

        # 关键: 使用 HelpAccordion 渲染操作场景
        assert '<HelpAccordion' in content, \
            "HelpCenterDrawer should embed HelpAccordion component"
        assert ':scenario-id="scenarioId"' in content, \
            "HelpAccordion should receive scenarioId"

        # 关键: iframe 方案已在 P3 移除
        assert '<iframe' not in content, \
            "P3 removed iframe embed in favor of HelpAccordion"
        assert '/docs/user-guide/index.html' not in content, \
            "P3 removed hardcoded user-guide url"

    def test_iframe_sandbox_attribute(self):
        """[P3 2026-06-30] initialStep prop 承载 URL ?help=&step= 解析结果

        验证: initialStep prop 定义 (父组件从 URL 解析后传入) + Escape 键处理
        """
        content = HELP_DRAWER_VUE.read_text(encoding='utf-8')

        # 关键: initialStep prop (默认 null = 不指定)
        assert 'initialStep' in content, \
            "Drawer should accept initialStep prop from URL parsing"
        assert 'default: null' in content, \
            "initialStep default should be null"

        # 关键: Escape 键关闭 / 先还原最大化
        assert 'handleKeydown' in content, \
            "Drawer should handle keyboard events"
        assert "e.key === 'Escape'" in content or 'e.key==="Escape"' in content, \
            "Escape should close drawer (or restore first)"

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
        """[P3 2026-06-30] 最大化/还原 + Escape 降级关闭

        验证: isMaximized 状态 + toggleMaximize + Escape 先还原再关闭
        """
        content = HELP_DRAWER_VUE.read_text(encoding='utf-8')

        # 关键: 最大化状态
        assert 'isMaximized' in content, \
            "Drawer should track isMaximized state"

        # 关键: 最大化切换函数
        assert 'function toggleMaximize' in content, \
            "Drawer should have toggleMaximize function"

        # 关键: 最大化时的样式类
        assert 'is-maximized' in content, \
            "Maximized state should apply is-maximized class"

        # 关键: Escape 先还原最大化, 再关闭
        assert 'isMaximized.value = false' in content, \
            "Escape should restore before closing"

    def test_help_drawer_default_width(self):
        """[eefed84] 默认宽度 880px (可读 docs 布局)

        验证: HelpCenterDrawer.vue 中 width prop 默认 880
        """
        content = HELP_DRAWER_VUE.read_text(encoding='utf-8')

        # 关键: width 默认值 880 (eefed84 引入)
        assert 'default: 880' in content or 'default:880' in content, \
            "HelpCenterDrawer default width should be 880 (eefed84)"

    def test_help_drawer_test_spec_exists(self):
        """[P3 2026-06-30] 已有测试规范 (HelpCenterDrawer.spec.js) 通过

        验证: __tests__/HelpCenterDrawer.spec.js 存在并含 5+ 用例
        """
        assert HELP_DRAWER_SPEC.exists(), \
            f"HelpCenterDrawer.spec.js should exist at {HELP_DRAWER_SPEC}"

        content = HELP_DRAWER_SPEC.read_text(encoding='utf-8')

        # 关键: 测试用例
        test_count = content.count("it(")
        assert test_count >= 5, \
            f"HelpCenterDrawer.spec.js should have at least 5 tests, found {test_count}"

        # 关键: P3 关键场景覆盖
        lowered = content.lower()
        assert 'helpaccordion' in lowered, \
            "tests should cover HelpAccordion rendering"
        assert 'maximize' in lowered or '最大化' in content, \
            "tests should cover maximize/restore"
        assert 'step=' in content, \
            "tests should cover URL ?step= auto expand"
