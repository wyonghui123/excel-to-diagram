"""
部署完成后自动清理 v33_pipeline — 阶段 6→7 衔接

包装 staging_deploy_orchestrator.py 或 hotfix_deploy.py。
部署成功调用 _v33_state.transition(..., DEPLOYED) 自动清理。
"""
import argparse, subprocess, sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _v33_state import transition


def run_deploy(deploy_cmd: list, cwd: str = None) -> bool:
    """运行部署命令，根据 exit code 决定是否调用 transition"""
    print(f'  [deploy] Running: {" ".join(deploy_cmd)}')
    env = os.environ.copy()
    env.setdefault('DEPLOY_AUTO_V33', '1')  # 防止递归
    r = subprocess.run(deploy_cmd, cwd=cwd, capture_output=True, text=True,
                       encoding='utf-8', env=env)
    if r.stdout:
        print('  --- stdout (last 50 lines) ---')
        for line in r.stdout.splitlines()[-50:]:
            print(f'    {line}')
    if r.stderr:
        print('  --- stderr (last 20 lines) ---')
        for line in r.stderr.splitlines()[-20:]:
            print(f'    {line}')
    return r.returncode == 0


def main():
    parser = argparse.ArgumentParser(description='部署 + 自动 v33_pipeline 清理')
    parser.add_argument('bug_id', help='BUG ID')
    parser.add_argument('--mode', choices=['staging', 'hotfix'], default='staging')
    parser.add_argument('--skip-deploy', action='store_true',
                       help='跳过实际部署，仅触发 v33_pipeline 清理 (用于 dry-run)')
    parser.add_argument('--note', default='', help='备注')
    parser.add_argument('--actor', default='deploy-agent', help='谁执行部署')
    args = parser.parse_args()

    # 1. 实际部署
    if not args.skip_deploy:
        deploy_cmd = ['python', r'D:\filework\worktrees\release-prep\tools\staging_deploy_orchestrator.py']
        if args.mode == 'hotfix':
            os.environ['DEPLOY_MODE'] = 'hotfix'
        ok = run_deploy(deploy_cmd)
        if not ok:
            print('  [ABORT] 部署失败, 不推进 v33_pipeline')
            return 1

    # 2. 自动推进 v33_pipeline
    ok = transition(args.bug_id, 'DEPLOYED', actor=args.actor, note=args.note or f'{args.mode} 部署完成')
    print(f'  {"✓" if ok else "✗"} {args.bug_id} -> DEPLOYED')
    print(f'  ⏭ last_deployed 已更新, HANDOVER STATUS 应改为 DEPLOYED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
