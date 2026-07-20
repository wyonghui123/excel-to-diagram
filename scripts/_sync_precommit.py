"""
将主仓库的 pre-commit hook + .pre-commit-config.yaml 同步到所有 worktree

原因：worktree 默认没有 .git/hooks/pre-commit，导致 wt 内 commit 跳过所有质量检查
风险：CRLF/Encoding/spec.md 白名单等检查全部失效
解决：每个 wt 的 .git/worktrees/<name>/hooks/pre-commit 在创建时调用本脚本

用法：
  python scripts/_sync_precommit.py              # 同步全部 wt
  python scripts/_sync_precommit.py <wt-name>   # 同步指定 wt
  python scripts/_sync_precommit.py --install   # 同时安装 pre-commit framework
"""
import subprocess, shutil, sys
from pathlib import Path

REPO = Path(r'D:\filework\excel-to-diagram')
WT_BASE = Path(r'D:\filework\worktrees')

HOOK_SOURCE = REPO / '.git/hooks/pre-commit'
CONFIG_SOURCE = REPO / '.pre-commit-config.yaml'


def install_one(wt_path: Path) -> tuple:
    """把 pre-commit hook + config 复制到指定 wt"""
    git_file = wt_path / '.git'
    if not git_file.exists():
        return (False, 'no .git')

    # 读取 .git 文件内容，找到真实的 gitdir
    # 格式: gitdir: D:\filework\excel-to-diagram\.git\worktrees\<name>
    try:
        git_dir_line = git_file.read_text(encoding='utf-8').strip()
    except Exception:
        git_dir_line = git_file.read_text(encoding='utf-8', errors='replace').strip()

    if not git_dir_line.startswith('gitdir:'):
        return (False, '.git is not a worktree pointer file')

    real_git = Path(git_dir_line[len('gitdir:'):].strip())
    if not real_git.exists():
        return (False, f'real git dir not found: {real_git}')

    results = []

    # 1. 复制 pre-commit hook
    if HOOK_SOURCE.exists():
        tgt = real_git / 'hooks' / 'pre-commit'
        tgt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(HOOK_SOURCE, tgt)
        tgt.chmod(0o755)
        results.append(('hook', tgt.stat().st_size))
    else:
        results.append(('hook', 'MISSING'))

    # 2. 复制 .pre-commit-config.yaml（如果 wt 没有）
    if CONFIG_SOURCE.exists():
        tgt = wt_path / '.pre-commit-config.yaml'
        if not tgt.exists():
            shutil.copy(CONFIG_SOURCE, tgt)
        results.append(('config', tgt.stat().st_size))

    return (True, results)


def install_all():
    """同步到所有 worktree"""
    if not WT_BASE.exists():
        print('  [ERROR] worktree_base not found')
        return

    # 列出所有 wt（来自 git worktree list）
    r = subprocess.run(['git', '-C', str(REPO), 'worktree', 'list'],
                       capture_output=True, text=True, encoding='utf-8')
    syncs = []
    skip_count = 0
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # 格式: <path> <hash> [branch]
        parts = line.split()
        if not parts:
            continue
        wt_path = Path(parts[0])
        if REPO.resolve() == wt_path.resolve():
            continue  # 跳过主仓库
        if 'phase13' in str(wt_path).lower():
            skip_count += 1
            continue  # phase13 是活跃 agent, 不动
        ok, info = install_one(wt_path)
        marker = 'OK' if ok else 'X'
        print(f'  [{marker}] {wt_path.name:30} -> {info}')
        if ok:
            syncs.append(wt_path.name)

    print(f'\n=== 同步结果 ===')
    print(f'  成功: {len(syncs)} 个 wt')
    print(f'  跳过: {skip_count} 个 (phase13 不动)')


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('wt_name', nargs='?', help='指定 wt 名称, 不传则全部')
    p.add_argument('--install', action='store_true', help='同时安装 pre-commit framework')
    args = p.parse_args()

    if args.wt_name:
        wt_path = WT_BASE / args.wt_name
        ok, info = install_one(wt_path)
        print(f'  [{"OK" if ok else "X"}] {args.wt_name}: {info}')
    else:
        install_all()


if __name__ == '__main__':
    main()
