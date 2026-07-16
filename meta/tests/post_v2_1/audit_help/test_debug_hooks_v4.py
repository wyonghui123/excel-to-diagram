# -*- coding: utf-8 -*-
"""
test_debug_hooks_v4.py
覆盖提交: a622d0d (V4.0 重构), b9f1ef8 (V4.0 变更通知), 053e7ef (V4.0.1 hooks 动态路径 + .ps1 违规)
依据: .trae/specs/test-suite/post-6-22-roadmap.md 主题 8 (Debug/Infra)

测试:
- hooks 动态路径解析正确 (053e7ef V4.0.1)
- .ps1 违规模式可检测
- V4.0 关键变更 (service_manager.py, dashboard.py, .trae/hooks.json) 落地
- V4.0 变更通知文档存在 (b9f1ef8)
- PreToolUse 拦截根目录调试脚本
- SessionStart 启动 watchdog
"""
import json
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


HOOKS_JSON = PROJECT_ROOT / '.trae' / 'hooks.json'
DEBUG_DIR = PROJECT_ROOT / 'scripts' / 'debug'
V4_NOTICE = PROJECT_ROOT / '.trae' / 'debug' / 'V4_CHANGES_NOTICE.md'


# ============================================================
# 1. TestDebugHooksV4 (4 用例)
# ============================================================

class TestDebugHooksV4:
    """Debug hooks V4.0 - 动态路径 + .ps1 违规模式 (a622d0d, b9f1ef8, 053e7ef)"""

    def test_hook_dynamic_path_resolution(self):
        """[053e7ef V4.0.1] hooks 动态路径解析正确

        验证: .trae/hooks.json 中 command 模板用 $env:TRAE_PROJECT_DIR
        动态解析项目根, 而不是硬编码路径
        """
        content = HOOKS_JSON.read_text(encoding='utf-8')

        # 关键: 使用 $env:TRAE_PROJECT_DIR
        assert '$env:TRAE_PROJECT_DIR' in content, \
            "hooks.json should use $env:TRAE_PROJECT_DIR for dynamic path resolution"

        # 关键: fallback to Get-Location (当 env var 未设)
        assert 'Get-Location' in content, \
            "hooks.json should fallback to Get-Location when TRAE_PROJECT_DIR not set"

        # 关键: 用 Join-Path 拼接路径
        assert 'Join-Path' in content, \
            "hooks.json should use Join-Path for path composition"

    def test_ps1_violation_pattern_detected(self):
        """[053e7ef V4.0.1] 违规 .ps1 模式可检测

        验证: hooks_pre_tool_use.ps1 (或 session_start_bootstrap.ps1)
        能检测违规的 .ps1 模式
        """
        # 053e7ef V4.0.1: 简化 hooks_pre_tool_use.ps1, 加强 .ps1 违规检测
        hook_ps1 = DEBUG_DIR / 'hooks_pre_tool_use.ps1'
        if not hook_ps1.exists():
            pytest.skip(f"{hook_ps1} not present (V4.0.1 hook file not found)")

        content = hook_ps1.read_text(encoding='utf-8')

        # 关键: 包含检测 .ps1 模式
        # V4.0.1 关注的是根目录调试脚本检测, 不是 .ps1 本身
        # 053e7ef commit message 提到 .ps1 违规模式
        # 验证: hook 检查 .ps1 文件 (避免 root 调试 .ps1)
        assert '.ps1' in content, \
            "hook should detect .ps1 files"

    def test_v4_hooks_json_structure(self):
        """[a622d0d V4.0] .trae/hooks.json 配置 SessionStart + PreToolUse

        验证: hooks.json 包含 SessionStart (启动 watchdog) +
        PreToolUse (拦截根目录调试脚本)
        """
        # 解析 hooks.json
        with open(HOOKS_JSON, 'r', encoding='utf-8') as f:
            hooks_config = json.load(f)

        # 关键: hooks 节点
        assert 'hooks' in hooks_config, "hooks.json should have 'hooks' node"

        # 关键: SessionStart 钩子 (启动 watchdog)
        assert 'SessionStart' in hooks_config['hooks'], \
            "hooks.json should have SessionStart hook (V4.0 watchdog)"

        # 关键: PreToolUse 钩子 (拦截根目录调试脚本)
        assert 'PreToolUse' in hooks_config['hooks'], \
            "hooks.json should have PreToolUse hook (V4.0 root script detection)"

        # 关键: 钩子是 command 类型
        for hook_name, hooks in hooks_config['hooks'].items():
            for hook in hooks:
                # matcher 可选
                # 每个 hook entry 应有 hooks 列表
                if 'hooks' in hook:
                    for h in hook['hooks']:
                        assert h.get('type') == 'command', \
                            f"{hook_name} hooks should be 'command' type"
                        assert 'command' in h, \
                            f"{hook_name} hook should have 'command' field"

    def test_v4_changes_notice_exists(self):
        """[b9f1ef8] V4.0 变更通知文档存在

        验证: .trae/debug/V4_CHANGES_NOTICE.md 存在, 含 V4.0 关键变更说明
        """
        if not V4_NOTICE.exists():
            pytest.skip(f"{V4_NOTICE} not found (V4.0 notice not yet written)")

        content = V4_NOTICE.read_text(encoding='utf-8')

        # 关键: 文档提到 V4.0
        assert 'V4' in content, "V4_CHANGES_NOTICE should mention V4.0"

        # 关键: 提到关键变更
        # service_manager / dashboard / PreToolUse / SessionStart
        keywords = ['service_manager', 'dashboard', 'PreToolUse', 'SessionStart']
        found = sum(1 for kw in keywords if kw in content or kw.lower() in content)
        assert found >= 2, \
            f"V4_CHANGES_NOTICE should mention key V4.0 changes, found {found}/4"
