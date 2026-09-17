#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置文件自动备份工具 - v3.3 新增 (P0-S2)

在写入关键配置文件前自动备份, 保留最近 5 份。
损坏时可一键恢复。

用法:
  python scripts/_config_backup.py backup <file>      # 备份指定文件
  python scripts/_config_backup.py restore <file>     # 恢复最近一份
  python scripts/_config_backup.py list [file]        # 列出备份
  python scripts/_config_backup.py verify <file>      # 验证文件完整性

被保护的文件:
  - .coord/ports.json
  - .coord/paths.json
  - .agent-status.json
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _wt_service import load_paths


BACKUP_DIR_NAME = ".coord/backup"
MAX_BACKUPS = 5

# 被保护的关键文件列表 (相对于 D:\filework, 不是 main_repo)
PROTECTED_FILES = [
    ".coord/ports.json",
    ".coord/paths.json",
    ".agent-status.json",
]


def _backup_dir() -> Path:
    # 配置文件在 D:\filework 下, 不在 main_repo (excel-to-diagram) 下
    base = Path("D:/filework")
    bd = base / BACKUP_DIR_NAME
    bd.mkdir(parents=True, exist_ok=True)
    return bd


def _resolve_file(file_path: str) -> Path:
    """解析文件路径 (支持相对路径和绝对路径)"""
    p = Path(file_path)
    if p.is_absolute():
        return p
    # 配置文件相对于 D:\filework (项目根), 不是 main_repo
    base = Path("D:/filework")
    return base / file_path


def backup(file_path: str) -> Path | None:
    """备份指定文件, 返回备份文件路径

    策略:
      1. 读取原文件验证可解析 (JSON)
      2. 复制到 backup/ 目录, 文件名带时间戳
      3. 保留最近 MAX_BACKUPS 份
    """
    src = _resolve_file(file_path)
    if not src.exists():
        return None

    # 验证 JSON 可解析 (只对 .json 文件)
    if src.suffix == ".json":
        try:
            with open(src, "r", encoding="utf-8") as f:
                json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"  [WARN] {src.name} JSON 解析失败, 备份可能损坏: {e}")
            # 仍然备份 (用于诊断)

    # 生成备份文件名
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    backup_name = f"{src.stem}_{timestamp}{src.suffix}"
    backup_path = _backup_dir() / backup_name

    # 复制
    shutil.copy2(src, backup_path)

    # 清理旧备份 (保留最近 MAX_BACKUPS 份)
    pattern = f"{src.stem}_*{src.suffix}"
    backups = sorted(_backup_dir().glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[MAX_BACKUPS:]:
        old.unlink()

    return backup_path


def restore(file_path: str) -> bool:
    """从最近一份备份恢复"""
    dst = _resolve_file(file_path)
    pattern = f"{dst.stem}_*{dst.suffix}"
    backups = sorted(_backup_dir().glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    if not backups:
        print(f"  [ERROR] No backup found for {dst.name}")
        return False

    latest = backups[0]
    shutil.copy2(latest, dst)
    print(f"  [OK] Restored {dst.name} from {latest.name}")
    return True


def list_backups(file_path: str = None):
    """列出备份"""
    bd = _backup_dir()

    if file_path:
        src = _resolve_file(file_path)
        pattern = f"{src.stem}_*{src.suffix}"
        backups = sorted(bd.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        print(f"  Backups for {src.name}: {len(backups)}")
        for b in backups:
            size = b.stat().st_size
            mtime = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            print(f"    {b.name}  ({size} bytes, {mtime})")
    else:
        backups = sorted(bd.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        print(f"  Total backups: {len(backups)}")
        for b in backups:
            size = b.stat().st_size
            mtime = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            print(f"    {b.name}  ({size} bytes, {mtime})")


def verify(file_path: str) -> bool:
    """验证文件完整性 (JSON 可解析 + 非空)"""
    src = _resolve_file(file_path)
    if not src.exists():
        print(f"  [FAIL] File not found: {src}")
        return False

    if src.stat().st_size == 0:
        print(f"  [FAIL] File is empty: {src}")
        return False

    if src.suffix == ".json":
        try:
            with open(src, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not data:
                print(f"  [WARN] File is valid JSON but empty: {src}")
                return False
            print(f"  [OK] {src.name} is valid JSON ({src.stat().st_size} bytes)")
            return True
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"  [FAIL] {src.name} JSON parse error: {e}")
            return False

    print(f"  [OK] {src.name} exists ({src.stat().st_size} bytes)")
    return True


def backup_all_protected():
    """备份所有被保护文件"""
    print(f"  Backing up {len(PROTECTED_FILES)} protected files...")
    for f in PROTECTED_FILES:
        bp = backup(f)
        if bp:
            print(f"    [OK] {f} -> {bp.name}")
        else:
            print(f"    [SKIP] {f} not found")
    print(f"  Done")


def verify_all_protected():
    """验证所有被保护文件"""
    print(f"  Verifying {len(PROTECTED_FILES)} protected files...")
    all_ok = True
    for f in PROTECTED_FILES:
        if not verify(f):
            all_ok = False
    if all_ok:
        print(f"  [ALL OK] All protected files valid")
    else:
        print(f"  [FAIL] Some files corrupted, use 'restore' to recover")
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Config backup tool (v3.3 P0-S2)")
    parser.add_argument("command", choices=["backup", "restore", "list", "verify", "backup-all", "verify-all"])
    parser.add_argument("file", nargs="?", help="file path (relative to main_repo or absolute)")
    args = parser.parse_args()

    if args.command == "backup":
        if not args.file:
            print("Usage: _config_backup.py backup <file>")
            return 1
        bp = backup(args.file)
        if bp:
            print(f"  [OK] Backed up to {bp.name}")
        else:
            print(f"  [SKIP] File not found")
    elif args.command == "restore":
        if not args.file:
            print("Usage: _config_backup.py restore <file>")
            return 1
        return 0 if restore(args.file) else 1
    elif args.command == "list":
        list_backups(args.file)
    elif args.command == "verify":
        if not args.file:
            print("Usage: _config_backup.py verify <file>")
            return 1
        return 0 if verify(args.file) else 1
    elif args.command == "backup-all":
        backup_all_protected()
    elif args.command == "verify-all":
        return 0 if verify_all_protected() else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
