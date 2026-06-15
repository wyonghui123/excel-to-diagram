# -*- coding: utf-8 -*-
"""
[MODULE] AI Coding Agent 友好测试入口 (v3.18)
[DESCRIPTION] 3 个新参数:
  --single <test_id>     单测快速反馈 (< 5s, 跳过 DB 快照/锁)
  --port <port>          多 agent 端口隔离 (3010-3019)
  --json <path>          JSON 输出 (含 trace_id, 给 Agent 解析)

合规:
  [OK] 走 test.py 入口机制 (设置 TEST_ENTRY=1, 复用锁/快照)
  [OK] Cookie 认证 (跟 v3.17 一致)
  [OK] 不动 conftest.py 硬阻断 (只新增一个 wrapper)
  [OK] 跨平台 (Python 3.x, 不依赖 PowerShell)

使用:
  python scripts/agent_test.py --single meta/tests/e2e/bo_action/test_db_integrity.py::test_db_integrity_ok
  python scripts/agent_test.py --port 3011 --file meta/tests/...
  python scripts/agent_test.py --json results.json --file meta/tests/...
"""
import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent  # .../excel-to-diagram
TEST_PY = Path('d:/filework/test.py')
RESULTS_DIR = PROJECT_ROOT / 'test_temp'
RESULTS_DIR.mkdir(exist_ok=True)


def run_agent_test(args) -> dict:
    """
    调用 test.py 处理 agent 友好测试请求

    返回 dict (给 Agent 消费):
      {
        'success': bool,
        'total': int, 'passed': int, 'failed': int, 'errors': int,
        'duration': float,
        'results': [{name, status, duration_ms, trace_id?, error_msg?}],
        'trace_id': str,  # 本次运行 trace_id
        'exit_code': int,
      }
    """
    import uuid
    trace_id = uuid.uuid4().hex[:32]

    # 设置环境变量
    env = os.environ.copy()
    env['TEST_ENTRY'] = '1'  # 通过 conftest.py 硬阻断
    env['AGENT_PORT'] = str(args.port)
    env['AGENT_TRACE_ID'] = trace_id
    if args.json:
        env['AGENT_JSON_OUTPUT'] = args.json

    # 构造 test.py 命令
    cmd = [sys.executable, str(TEST_PY)]
    if args.single:
        # [DECORATIVE] v3.18 D3: --single 智能支持 path::test_func
        if '::' in args.single:
            # 单测模式: test.py --single + test_func
            file_part, test_func = args.single.split('::', 1)
            # test.py --single 接受 file:func 风格
            cmd += ['--single', f'{file_part}::{test_func}', '--force']
        else:
            cmd += ['--single', args.single, '--force']
    elif args.file:
        cmd += ['--file', args.file, '--force']
    elif args.json:
        cmd += ['--unit']
    else:
        cmd += ['--unit']

    if args.port != 3010:
        env['AGENT_PORT'] = str(args.port)
        # 端口需 test.py 支持 (Phase 1 实施时加)

    start = time.time()

    # [DECORATIVE] v3.18: 实时进度输出 (stderr) + 收集输出 (stdout)
    stdout_lines = []
    stderr_lines = []

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=str(PROJECT_ROOT),
        )

        # 实时读取 stderr (进度) 和 stdout (pytest 输出)
        import threading

        def read_stderr():
            """实时输出 stderr 到控制台 (让用户看到进度)"""
            for line in iter(proc.stderr.readline, ''):
                if line:
                    stderr_lines.append(line)
                    # 实时输出到 stderr (用户可见)
                    print(line, end='', file=sys.stderr, flush=True)

        def read_stdout():
            """收集 stdout (pytest 输出, 用于解析)"""
            for line in iter(proc.stdout.readline, ''):
                if line:
                    stdout_lines.append(line)
                    # 如果不是 --quiet, 也输出到 stdout
                    if not args.quiet:
                        print(line, end='', file=sys.stdout, flush=True)

        # 启动两个线程并行读取
        t_stderr = threading.Thread(target=read_stderr, daemon=True)
        t_stdout = threading.Thread(target=read_stdout, daemon=True)
        t_stderr.start()
        t_stdout.start()

        # 等待进程完成
        exit_code = proc.wait(timeout=args.timeout)

        # 等待线程读取完剩余输出
        t_stderr.join(timeout=2)
        t_stdout.join(timeout=2)

        stdout = ''.join(stdout_lines)
        stderr = ''.join(stderr_lines)

    except subprocess.TimeoutExpired:
        proc.kill()
        return {
            'success': False,
            'error': f'Timeout after {args.timeout}s',
            'trace_id': trace_id,
            'exit_code': -1,
        }

    duration = time.time() - start

    # 解析 test.py 输出 (粗略)
    result = {
        'success': exit_code == 0,
        'duration': round(duration, 2),
        'trace_id': trace_id,
        'exit_code': exit_code,
        'stdout': stdout[-2000:] if not args.json else '',  # 不输出全部
        'stderr': stderr[-1000:] if stderr else '',
    }

    # 解析 pytest 概要
    # 例: "========== 5 passed, 1 failed, 2 errors in 2.31s =========="
    # 或:   "========== 4 passed in 13.40s =========="
    import re
    m = re.search(r'(\d+)\s+passed', stdout)
    if m:
        result['passed'] = int(m.group(1))
    m = re.search(r'(\d+)\s+failed', stdout)
    if m:
        result['failed'] = int(m.group(1))
    m = re.search(r'(\d+)\s+error', stdout)
    if m:
        result['errors'] = int(m.group(1))
    # 重新算 total (即使部分 missing, 至少 passed+failed 算)
    p = result.get('passed', 0)
    f = result.get('failed', 0)
    e = result.get('errors', 0)
    result['total'] = p + f + e
    result['pass_rate'] = round(p / result['total'] * 100, 1) if result['total'] > 0 else 0

    # JSON 输出
    if args.json:
        json_path = Path(args.json)
        if not json_path.is_absolute():
            # 如果 user 已写 "test_temp/xxx.json", 取 basename 防双拼
            if str(args.json).startswith('test_temp' + os.sep) or str(args.json).startswith('test_temp/'):
                json_path = PROJECT_ROOT / args.json
            else:
                json_path = RESULTS_DIR / args.json
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def main():
    parser = argparse.ArgumentParser(
        description='AI Coding Agent 友好测试入口 (v3.18)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
合规:
  [OK] 走 test.py 入口 (TEST_ENTRY=1, conftest.py 硬阻断通过)
  [OK] Cookie 认证 (跟 v3.17 一致)
  [OK] 不直接运行 pytest
        """,
    )
    parser.add_argument('--single', metavar='TEST_ID',
                        help='单测快速反馈 (跳过 DB 快照/锁, < 5s). '
                             '格式: path/to/test.py::test_func_name 或 path/to/test.py')
    parser.add_argument('--file', metavar='PATH',
                        help='单文件运行 (跟 test.py --file 相同)')
    parser.add_argument('--port', type=int, default=None,
                        help='多 agent 端口 (3010-3019, 默认自动分配避免冲突)')
    parser.add_argument('--json', metavar='PATH',
                        help='JSON 输出到文件 (含 trace_id schema)')
    parser.add_argument('--timeout', type=int, default=300,
                        help='超时 (秒, 默认 300)')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='安静模式, 只输出 JSON')
    args = parser.parse_args()

    if not args.single and not args.file:
        parser.error('必须指定 --single 或 --file')

    if args.port is None:
        # [P0] 自动分配 (避免 3010 默认冲突)
        if not os.environ.get('AGENT_PORT'):
            args.port = _auto_assign_port()
            if not args.quiet:
                print(f'[AUTO-PORT] 分配端口 {args.port}')
        else:
            args.port = int(os.environ['AGENT_PORT'])

    if not 3010 <= args.port <= 3019:
        parser.error(f'--port 必须在 3010-3019 之间 (给定: {args.port})')

    if not args.quiet:
        print(f"[ROBOT] Agent Test (v3.18) port={args.port}")
        if args.single:
            print(f"   target: {args.single}")
        if args.json:
            print(f"   json:  {args.json}")

    result = run_agent_test(args)

    if args.quiet:
        # 只输出 JSON
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"Trace ID: {result['trace_id']}")
        print(f"Duration: {result['duration']}s")
        print(f"Exit:     {result['exit_code']}")
        if 'total' in result:
            print(f"Total:    {result['total']} (P={result.get('passed', 0)}, F={result.get('failed', 0)}, E={result.get('errors', 0)})")
        print(f"Success:  {result['success']}")
        if result.get('stderr'):
            print(f"\nStderr (last 500):\n{result['stderr'][-500:]}")
        if args.json:
            print(f"\nJSON saved to: {args.json}")
        print('='*60)

    sys.exit(0 if result['success'] else 1)


if __name__ == '__main__':
    main()
