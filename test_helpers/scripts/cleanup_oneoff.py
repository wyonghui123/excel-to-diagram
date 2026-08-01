"""
cleanup_oneoff.py — 清理被 chart_diag 取代的一次性 diag_/verify_ 脚本

[目的] test_helpers/scripts/ 下累积了 300+ 个一次性排查脚本, 命名混乱 (diag_*.py / verify_*.py /
   _diag_*.py / _verify_*.py 互相重叠). chart_diag.py 出现后, 这些脚本的功能已经被取代, 不再
   有维护价值.

[策略]
   1. **保留**: chart_diag.py 依赖的 + 通用基础设施 (端口清理 / 后端重启 / 临时登录状态检查)
   2. **归档**: 所有 *_2026_07_29.* (历史快照) + diag_* / verify_* 一次性脚本
   3. **删除**: 重复的 _diag_*.png 截图 (脚本运行残留)

[可恢复] 归档到 _archive_2026_08_01/ 目录, 不直接删除, 万一未来需要回看.

[用法]
   python test_helpers/scripts/cleanup_oneoff.py --dry-run   # 仅打印会做什么, 不执行
   python test_helpers/scripts/cleanup_oneoff.py             # 实际归档
"""
from __future__ import annotations
import sys
from pathlib import Path
import argparse

SCRIPTS_DIR = Path(__file__).resolve().parent
ARCHIVE_DIR = SCRIPTS_DIR / '_archive_2026_08_01'

# 必须保留 (基础设施 / 当前仍在使用)
KEEP_FILES = {
    # chart_diag 自身和输出
    'cleanup_oneoff.py',  # 自身
    # 端口清理小工具
    'check_3006.ps1', 'check_5000.ps1', 'check_listen.ps1', 'check_backend_port.ps1',
    'check_dev.ps1', 'check_port.ps1', 'check_3007.ps1',
    # 后端重启
    'restart_backend.ps1', 'run_vite_backend.ps1',
    # 临时诊断 (基础设施级, 偶尔会复用)
    'diag_login_state.py', 'diag_state.py',
    # 清理截图的辅助脚本
    'cleanup_screenshots.py',
    # AI agent 习惯临时放的 _diag_*.py 工具 (本次保留以避免误删)
    '_diag_archdata.py', '_diag_full.py', '_diag_btn.py', '_diag_version.py',
    '_diag_select_version.py', '_diag_select_fixed.py', '_diag_fetch_pv.py',
    '_find_archdata.py', '_find_bo.py', '_find_pid.py', '_find_pid2.py',
    '_check_port.py', '_prep.py', '_restore.py', '_verify_293c2aa.py',
}

# 归档规则 (按文件名前缀/后缀)
ARCHIVE_PATTERNS = [
    'diag_*.py',     # 一次性诊断
    'verify_*.py',   # 一次性验证
    'test_*.py',     # 一次性测试 (在 scripts/ 下, 不在 tests/e2e/ 下)
    '_diag_*.py',    # 临时调试脚本 (AI agent 创建)
    'deep_diag_*.py',
    'diagnose_*.py',
    'analyze_*.py',
    'mermaid_elk_*.py',
    'sel_test*.py',
    'quick_*.py',
    'find_*.py',
    'inspect_*.py',
    'dump_*.py',
    'audit_*.py',
    'reproduce_*.py',
    'force_*.py',
    'extract_*.py',
    'screenshot_*.py',
    'open_dropdown*.py',
    'direct_test_*.py',
    'ultimate_*.py',
    'final_*.py',
    'debug_*.py',    # 临时调试脚本
    'check_*.py',    # 一次性 check 脚本 (check_dev.ps1 / check_port.ps1 等保留)
    'check_*.bat',
    'curl_*.ps1',
    'probe_*.py',
    'verify_final*.json',
    'verify_final*report.json',
    'verify_*report.json',
    'verify_*result.json',
    'verify_*logs.py',
    'verify_*logs.txt',
    'verify_*probe.py',
    'verify_*deep_probe.py',
    'verify_*closed_loop*.py',
    'verify_*sm_disabled.png',
    'verify_*sm_drawer*.png',
    'verify_*sm_initial.png',
    'verify_*sm_rendered.png',
    'verify_*sm_after*.png',
    'verify_*sm_before*.png',
    'verify_*sm_closed_loop*.png',
    'verify_*sm_switched*.png',
    'verify_*bo_*.png',
    'verify_*final*.png',
    'verify_*drawer*.png',
    'verify_*_drawer*.png',
    'verify_*error.png',
    'verify_*_panel_*.png',
    'verify_*after_disable.png',
    'verify_*after_switch.png',
    'verify_*initial.png',
    'verify_*initial2.png',
    'verify_*scm_*.png',
    'verify_*font_*.png',
    'verify_*back.png',
    'verify_*plan*.png',
    'verify_v*.png',
    'verify_v*.json',
    'verify_v*.html',
    'verify_v*.txt',
    'verify_scm_*.png',
    'verify_bo_*.png',
    'verify_sm_*.png',
    '_dump_*.txt',   # 临时 dump 文件
    'sm_*_v4.txt',   # 临时 dump 文件
    'sm_*_2026_07_29.txt',
    'sm_*_2026_07_29.py',
    'mermaid_*_2026_07_29.txt',
    'AUTHORITATIVE_*.py',  # 命名歧义的归一 verify
    'diag_*.png',         # 临时截图
    'diag_*.log',         # 临时日志
    'diag_*result.json',  # 临时结果
    'sm_*.txt',           # 临时 dump
    'sm_*.json',
    'syncLayout_*.py',
    'syncLayout_*.png',
    'syncLayout_*.txt',
    'strict_*.py',
    'v9_*.png',
    'verify_final*_*.txt',
    'verify_final*_*.png',
    'verify_v5_*.log',
    'verify_v7_*.log',
    'verify_maxedges_*.png',
    'verify_maxedges_*.json',
    'verify_maxedges_*.py',
    'verify_maxedges_*.txt',
    'verify_maxedges_*.html',
    'verify_maxedges_*.log',
    'verify_embedded_*.py',
    'test_api*.ps1',
    'test_*.ps1',
    'test_*.js',
]

# 历史快照 (按日期后缀)
HISTORICAL_SUFFIXES = ['_2026_07_29']


def should_keep(filename: str) -> bool:
    return filename in KEEP_FILES


def should_archive(filename: str) -> bool:
    """按通配符模式判断是否归档"""
    import fnmatch
    name = filename.lower()
    if any(fnmatch.fnmatch(name, p) for p in ARCHIVE_PATTERNS):
        return True
    for suf in HISTORICAL_SUFFIXES:
        if name.endswith(suf.lower() + '.py') or name.endswith(suf.lower() + '.png') \
           or name.endswith(suf.lower() + '.html') or name.endswith(suf.lower() + '.json') \
           or name.endswith(suf.lower() + '.txt'):
            return True
    return False


def is_garbage_screenshot(filename: str) -> bool:
    """判断是否重复的截图垃圾 (脚本运行残留, 非用户场景截图)"""
    name = filename.lower()
    return (
        name.startswith('_diag_') and name.endswith('.png')
    ) or (
        name.startswith('_clicked_') and name.endswith('.png')
    ) or (
        name.startswith('_user_viewport_') and name.endswith('.png')
    )


def main(dry_run: bool = False):
    if not ARCHIVE_DIR.exists() and not dry_run:
        ARCHIVE_DIR.mkdir()
        print(f'[cleanup] 创建归档目录: {ARCHIVE_DIR}')

    archived = []
    deleted = []
    kept = []

    for path in sorted(SCRIPTS_DIR.iterdir()):
        if path.name == ARCHIVE_DIR.name:
            continue
        if path.name == Path(__file__).name:
            continue
        if not path.is_file():
            continue

        fname = path.name

        # 必须保留
        if should_keep(fname):
            kept.append(fname)
            continue

        # 垃圾截图直接删
        if is_garbage_screenshot(fname):
            if dry_run:
                print(f'  [DELETE] {fname}')
            else:
                path.unlink()
            deleted.append(fname)
            continue

        # 其他归档
        if should_archive(fname):
            dest = ARCHIVE_DIR / fname
            if dry_run:
                print(f'  [ARCHIVE] {fname}')
            else:
                if dest.exists():
                    dest.unlink()
                path.rename(dest)
            archived.append(fname)
            continue

        # 不在规则内的: 保留 (避免误删)
        kept.append(fname)

    print(f'\n=== cleanup summary ===')
    print(f'  kept: {len(kept)} files')
    print(f'  archived: {len(archived)} files')
    print(f'  deleted: {len(deleted)} files')
    if dry_run:
        print('\n(DRY RUN — 无实际修改, 加 --execute 真正执行)')

    return {
        'kept': kept,
        'archived': archived,
        'deleted': deleted
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='仅打印不执行 (默认)')
    parser.add_argument('--execute', dest='dry_run', action='store_false',
                        help='真正执行')
    args = parser.parse_args()
    main(dry_run=args.dry_run)