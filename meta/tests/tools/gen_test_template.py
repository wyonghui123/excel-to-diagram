# -*- coding: utf-8 -*-
"""
[MODULE] D.1 Test 模板生成器 (v3.18)
[DESCRIPTION] 从 action_id 自动生成 test 模板, AI Coding Agent 直接套用

使用:
  python -m meta.tests.tools.gen_test_template <action_id> [--out <path>]
  # 或
  python meta/tests/tools/gen_test_template.py user.get_current

合规:
  [OK] 走 test.py 入口 (CONSOLE_SCRIPT 入口, 不绕开铁律)
  [OK] 用 cookie 认证 (跟 v3.17 + SESSION_REMINDER 一致)
  [OK] 复用 v3.17 bo_action_server_check fixture
"""
import os
import sys
import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # .../excel-to-diagram
sys.path.insert(0, str(PROJECT_ROOT))


# [DECORATIVE] v3.18: 模板用 {action_id} 风格占位符, 避免 f-string 冲突
TEMPLATE = """# -*- coding: utf-8 -*-
\"\"\"
[MODULE] 测试 {action_id} (v3.18 自动生成, D.1)
[DESCRIPTION] AI Coding Agent 写的测试模板

[DECORATIVE] 修改点:
1. 改 action_id (已填)
2. 填 prepare_data (可选)
3. 调 assertions (默认 smoke)
4. 加更多 edge cases

跑:
  python d:\\\\filework\\\\test.py --single meta/tests/e2e/bo_action/test_{file_stem}.py
\"\"\"
import time
import os
import sys

# admin_token 路径在 conftest.py 已配 (走 sys.path)
from admin_token import call_action


def test_{action_id_under}_happy_path(bo_action_server_check, admin_cookie):
    \"\"\"[DECORATIVE] 正常路径: {action_id} 应成功\"\"\"
    _, b = call_action('{action_id}', {{}}, cookie=admin_cookie)
    assert isinstance(b, dict)
    # 大部分 action success=True 或 200, 部分可能 404 等
    # 实际 assertion 跟 action 行为相关, 由 Agent 调整
    assert 'success' in b or 'error' in b, (
        f"{{action_id}} 应有 success/error 字段, 实际: {{b}}"
    )


def test_{action_id_under}_permission_denied(bo_action_server_check):
    \"\"\"[DECORATIVE] 无 token 应 401/403\"\"\"
    import http.client
    import json
    conn = http.client.HTTPConnection(
        'localhost', int(os.environ.get('AGENT_PORT', 3010)), timeout=10
    )
    body = json.dumps({{}}).encode('utf-8')
    conn.request('POST', '/api/v2/action/{action_id}', body=body, headers={{
        'Content-Type': 'application/json',
        'Content-Length': str(len(body)),
    }})
    r = conn.getresponse()
    r.read()
    conn.close()
    assert r.status in [401, 403], (
        f"无 token 应 401/403, 实际: {{r.status}}"
    )


def test_{action_id_under}_invalid_input(bo_action_server_check, admin_cookie):
    \"\"\"[DECORATIVE] 无效输入应 graceful 失败\"\"\"
    _, b = call_action('{action_id}', {{'__invalid__': True}}, cookie=admin_cookie)
    # 不期望崩溃
    assert isinstance(b, dict), f"响应应是 dict, 实际: {{type(b)}}"
    assert 'success' in b, f"响应应含 success 字段, 实际 keys: {{b.keys()}}"
"""


def main():
    parser = argparse.ArgumentParser(
        description='AI Coding Agent 测试模板生成器 (v3.18)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python meta/tests/tools/gen_test_template.py user.get_current",
    )
    parser.add_argument('action_id', help='如 user.get_current')
    parser.add_argument('--out', '-o', help='输出文件路径, 默认 meta/tests/e2e/bo_action/test_<action>.py')
    args = parser.parse_args()

    # action_id 转 file_stem (user.get_current → user_get_current)
    file_stem = args.action_id.replace('.', '_')
    action_id_under = file_stem  # 用于函数名

    if not args.out:
        args.out = f'meta/tests/e2e/bo_action/test_{file_stem}.py'

    content = TEMPLATE.format(
        action_id=args.action_id,
        action_id_under=action_id_under,
        file_stem=file_stem,
    )

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = PROJECT_ROOT / out_path

    if out_path.exists():
        print(f'[WARNING]  File exists: {out_path}')
        ans = input('Overwrite? (y/N): ')
        if ans.lower() != 'y':
            print('Aborted.')
            sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding='utf-8')
    print(f'[OK] Template written: {out_path}')
    print(f'\n[DECORATIVE] 跑测试:')
    print(f'  python d:\\\\filework\\\\test.py --single {args.out}')


if __name__ == '__main__':
    main()
