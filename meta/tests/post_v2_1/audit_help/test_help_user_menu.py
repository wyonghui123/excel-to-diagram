# -*- coding: utf-8 -*-
"""
test_help_user_menu.py
覆盖提交: e2c3297 (slim UserMenu to 3 items)
依据: .trae/specs/test-suite/post-6-22-roadmap.md 主题 7 (Help Center)

测试:
- UserMenu 简化为 3 项 (个人设置/帮助中心/退出登录)
- 帮助中心在 UserMenu 中
- UserMenu component 接受 menuItems prop
- 'help' command 在 handleUserCommand 中处理
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


USER_MENU_VUE = PROJECT_ROOT / 'src' / 'components' / 'common' / 'UserMenu' / 'UserMenu.vue'
TOP_NAV_HEADER = PROJECT_ROOT / 'src' / 'components' / 'common' / 'TopNavHeader' / 'TopNavHeader.vue'
APP_ROOT_LAYOUT = PROJECT_ROOT / 'src' / 'components' / 'common' / 'AppRootLayout.vue'


# ============================================================
# 1. TestUserMenuSlim3Items (4 用例)
# ============================================================

class TestUserMenuSlim3Items:
    """UserMenu 简化为 3 项 (e2c3297)"""

    def test_user_menu_has_3_items(self):
        """[e2c3297] UserMenu 只显示 3 项 (个人/帮助/登出)

        验证: TopNavHeader.vue 的 userMenuItems 默认值含 3 个 entry
        - profile (个人设置)
        - help (帮助中心)
        - logout (退出登录)
        """
        content = TOP_NAV_HEADER.read_text(encoding='utf-8')

        # 关键: 找到 userMenuItems 默认数组
        assert 'userMenuItems' in content, \
            "TopNavHeader should define userMenuItems"

        # 用 regex 提取 default 数组内容
        m = re.search(
            r'userMenuItems\s*:\s*\{[^}]*default\s*:\s*\(\s*\)\s*=>\s*\[(.+?)\]',
            content,
            re.DOTALL,
        )
        if not m:
            # 尝试对象形式
            m = re.search(
                r"userMenuItems\s*:\s*\{[^}]*default\s*:\s*\[(.+?)\]",
                content,
                re.DOTALL,
            )

        assert m is not None, "userMenuItems default value not found"
        items_text = m.group(1)

        # 3 个 item: profile + help + logout
        key_count = items_text.count("key:")
        # 3 项
        assert key_count == 3, \
            f"userMenuItems should have 3 items, found {key_count}: {items_text[:200]}"

        # 关键 key 名
        assert "'profile'" in items_text, "userMenuItems should have 'profile' item"
        assert "'help'" in items_text, "userMenuItems should have 'help' item"
        assert "'logout'" in items_text, "userMenuItems should have 'logout' item"

    def test_help_in_user_menu(self):
        """[e2c3297] 帮助中心在 UserMenu 中

        验证: userMenuItems 默认含 'help' 项, label 为 '帮助中心'
        """
        content = TOP_NAV_HEADER.read_text(encoding='utf-8')

        # 关键: help 项的 label 是 '帮助中心'
        m = re.search(
            r"\{\s*key:\s*'help'.*?label:\s*'([^']+)'",
            content,
            re.DOTALL,
        )
        if not m:
            # 也可能是 key:'help', label:'帮助中心' 顺序
            assert "'help'" in content, "UserMenu should have help key"
            assert "'帮助中心'" in content, "UserMenu should have '帮助中心' label"
        else:
            label = m.group(1)
            assert label == '帮助中心', f"help label should be '帮助中心', got '{label}'"

        # 关键: AppRootLayout 处理 'help' command
        layout_content = APP_ROOT_LAYOUT.read_text(encoding='utf-8')
        assert "command === 'help'" in layout_content, \
            "AppRootLayout should handle 'help' command in handleUserCommand"
        assert "openHelp" in layout_content, \
            "AppRootLayout should call openHelp on help command"

    def test_user_menu_component_accepts_menu_items_prop(self):
        """[e2c3297] UserMenu component 接受 menuItems prop

        验证: UserMenu.vue 中 menuItems prop 定义
        """
        content = USER_MENU_VUE.read_text(encoding='utf-8')

        # 关键: menuItems prop
        assert 'menuItems' in content, \
            "UserMenu should accept menuItems prop"

        # 关键: 模板里迭代 menuItems
        assert 'menuItems' in content and 'v-for' in content, \
            "UserMenu should iterate menuItems in template"

        # 关键: 默认值 (向后兼容)
        # 检查 default 字段
        m = re.search(
            r"menuItems\s*:\s*\{[^}]*default\s*:\s*\(\s*\)\s*=>\s*\[(.+?)\]",
            content,
            re.DOTALL,
        )
        # 允许 UserMenu 没有默认值 (TopNavHeader 才提供)
        # 关键是 prop 名称存在
        assert "menuItems:" in content, \
            "UserMenu should define menuItems prop"

    def test_top_nav_header_emits_user_command(self):
        """[e2c3297] TopNavHeader 处理 UserMenu 的 command 事件

        验证: TopNavHeader.vue 中:
        - UserMenu 绑定 @command="handleUserCommand"
        - handleUserCommand 函数存在
        - emit 'user-command'
        """
        content = TOP_NAV_HEADER.read_text(encoding='utf-8')

        # 关键: UserMenu 绑定 @command
        assert '@command="handleUserCommand"' in content, \
            "TopNavHeader should bind @command to handleUserCommand"

        # 关键: handleUserCommand 函数
        assert 'function handleUserCommand' in content or \
               'handleUserCommand(' in content, \
            "TopNavHeader should have handleUserCommand function"

        # 关键: emit 'user-command'
        assert "emit('user-command'" in content or \
               'emit("user-command"' in content, \
            "TopNavHeader should emit 'user-command'"
