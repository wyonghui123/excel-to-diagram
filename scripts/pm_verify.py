"""
PM 验证脚本 — 阶段 6

PM 在 release-prep (3006/3011) 上人工验证后，运行本脚本：
  python scripts/pm_verify.py V046 --note "已验证业务流 OK"

脚本会调用 _v33_state.transition() 推进 V046 从 CHERRY_PICKED -> PM_VERIFIED。
"""
import argparse, sys, urllib.request, urllib.error, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _v33_state import transition


def smoke_health(host: str, port: int, path: str = '/api/v1/health', timeout: int = 8) -> tuple:
    url = f'http://{host}:{port}{path}'
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (r.status, '')
    except urllib.error.HTTPError as e:
        return (e.code, str(e))
    except Exception as e:
        return (-1, str(e))


def health_check(host: str, port: int, retries: int = 3) -> bool:
    for i in range(retries):
        code, _ = smoke_health(host, port)
        print(f'    [health] attempt {i+1}: code={code}')
        if code == 200:
            return True
        time.sleep(2)
    return False


def main():
    parser = argparse.ArgumentParser(description='PM 验证 (v3.3 阶段 6)')
    parser.add_argument('bug_id', help='BUG ID (e.g. V046)')
    parser.add_argument('--note', default='', help='验证备注')
    parser.add_argument('--skip-health', action='store_true', help='跳过健康检查')
    parser.add_argument('--host', default='localhost', help='后端 host')
    parser.add_argument('--port', type=int, default=3011, help='后端 port (release-prep 默认 3011)')
    args = parser.parse_args()

    # 1. 健康检查
    if not args.skip_health:
        print(f'  [health] Checking http://{args.host}:{args.port}/api/v1/health...')
        if not health_check(args.host, args.port):
            print(f'  [WARN] 健康检查未通过 (release-prep 3011), 但仍可签字 (PM 决策)')
            resp = input('  是否继续? [y/N]: ').strip().lower()
            if resp != 'y':
                print('  已取消')
                return 1

    # 2. 推进状态机
    ok = transition(args.bug_id, 'PM_VERIFIED', actor='pm', note=args.note or 'PM 验证通过')
    if ok:
        print(f'  ✓ {args.bug_id} -> PM_VERIFIED (PM 已签字, 进入 deploy_pending)')
        print(f'  ⏭ 下一步: 协调智能体 trigger staging_deploy_orchestrator.py')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
