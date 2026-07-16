#!/usr/bin/env python3
"""
fix_crlf_in_bundle.py - 修 deploy_bundle/ 内所有 .sh 的 CRLF → LF

[CHG 2026-07-06] V007.21 部署教训:
  - Windows git checkout 自动把 LF → CRLF
  - Windows PS 写文件时也可能带 CRLF
  - yonaa Linux bash 解析 CRLF 会失败 ($'\r': command not found)
  - 必须部署前在本地修, 不依赖 yonaa sed

用法:
  python tools/fix_crlf_in_bundle.py                    # 修 deploy_bundle/
  python tools/fix_crlf_in_bundle.py path/to/bundle     # 修指定目录
"""
import os, sys
from pathlib import Path


def fix_crlf_in_dir(root: Path) -> tuple:
    """修 root 下所有 .sh 文件的 CRLF → LF

    Returns: (total, fixed, already_lf)
    """
    sh_files = list(root.rglob('*.sh'))
    total = len(sh_files)
    fixed = 0
    already_lf = 0
    for f in sh_files:
        data = f.read_bytes()
        if b'\r\n' in data:
            new_data = data.replace(b'\r\n', b'\n')
            f.write_bytes(new_data)
            fixed += 1
            rel = f.relative_to(root)
            print(f'  [FIX] {rel}')
        else:
            already_lf += 1
    return total, fixed, already_lf


def main():
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    else:
        # 默认 deploy_bundle/
        root = Path(__file__).resolve().parent.parent / 'deploy_bundle'

    if not root.exists():
        print(f'[FAIL] 目录不存在: {root}')
        sys.exit(1)

    print(f'[INFO] 修 CRLF → LF in: {root}')
    total, fixed, already_lf = fix_crlf_in_dir(root)
    print()
    print(f'[OK] {total} .sh 文件, {fixed} 个修了 CRLF, {already_lf} 个已是 LF')
    if fixed > 0:
        print('[PASS] deploy_bundle/ 现在所有 .sh 均为 LF, 可直接 SFTP 到 yonaa')


if __name__ == '__main__':
    main()
