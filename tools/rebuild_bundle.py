#!/usr/bin/env python3
"""
rebuild_bundle.py - 重建 _deploy_bundle/ 目录

自动从 tools/ 收集所有部署脚本 + 用户提供的 zip，
输出一个 _deploy_bundle/ 目录，直接 MobaXterm SFTP 拖到 /tmp/ 即可部署。

用法:
  python tools/rebuild_bundle.py                                  # 用 deploy-v*.zip (最新)
  python tools/rebuild_bundle.py --zip deploy-v20260703_002.zip   # 指定 zip
  python tools/rebuild_bundle.py --output my_bundle               # 自定义输出目录
  python tools/rebuild_bundle.py --clean                          # 只清空
  python tools/rebuild_bundle.py --list                           # 只列出 zip
"""
import os
import sys
import shutil
import argparse
import re
import time
from pathlib import Path
from typing import List, Optional

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"


def find_latest_zip(repo_root: Path) -> Optional[Path]:
    """找最新的 deploy-v<date>_<seq>.zip"""
    zips = sorted(repo_root.glob("deploy-v*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return zips[0] if zips else None


def list_zips(repo_root: Path) -> List[Path]:
    """列出所有 deploy-v*.zip"""
    return sorted(repo_root.glob("deploy-v*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)


def main():
    parser = argparse.ArgumentParser(description="重建 _deploy_bundle/")
    parser.add_argument("--zip", help="zip 路径 (默认: 最新 deploy-v*.zip)")
    parser.add_argument("--output", default="_deploy_bundle", help="输出目录 (默认 _deploy_bundle)")
    parser.add_argument("--clean", action="store_true", help="只清空输出目录")
    parser.add_argument("--list", action="store_true", help="只列出 deploy-v*.zip")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    tools_dir = repo_root / "tools"

    if args.list:
        print(f"{CYAN}可用的 deploy-v*.zip:{NC}")
        for z in list_zips(repo_root):
            print(f"  {z.name}  ({z.stat().st_size:,} bytes)")
        return 0

    # 决定 zip
    zip_path = None
    if args.zip:
        zip_path = repo_root / args.zip if not os.path.isabs(args.zip) else Path(args.zip)
    else:
        zip_path = find_latest_zip(repo_root)

    if zip_path and not zip_path.exists():
        print(f"{RED}zip 不存在: {zip_path}{NC}")
        return 1

    # 输出目录
    bundle = repo_root / args.output
    print(f"{CYAN}输出目录: {bundle}{NC}")

    # 清空
    if bundle.exists():
        if args.clean:
            print(f"  {YELLOW}--clean 模式, 只清空{NC}")
            shutil.rmtree(bundle)
            bundle.mkdir()
            return 0
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)

    # 1. 复制 zip
    if zip_path:
        shutil.copy(zip_path, bundle / zip_path.name)
        print(f"  {GREEN}+{NC} {zip_path.name}  ({zip_path.stat().st_size:,} bytes)")

    # 2. 复制 deploy 工具
    deploy_tools = [
        "deploy.sh",
        "precheck.sh",
        "smoke_test.sh",
        "rollback.sh",
        "unified_server.py",
    ]
    for fname in deploy_tools:
        src = tools_dir / fname
        if src.exists():
            shutil.copy(src, bundle / fname)
            print(f"  {GREEN}+{NC} {fname}  ({src.stat().st_size:,} bytes)")
        else:
            print(f"  {RED}缺{NC} {src}")

    # 3. 复制 lib/
    src_lib = tools_dir / "lib"
    if src_lib.exists():
        shutil.copytree(src_lib, bundle / "lib")
        print(f"  {GREEN}+{NC} lib/  (整个目录)")
    else:
        print(f"  {RED}缺{NC} lib/")

    # 4. 写 README
    if zip_path:
        version_match = re.search(r'deploy-(v\d{8}_\d+)\.zip', zip_path.name)
        version = version_match.group(1) if version_match else "vXXXX"
    else:
        version = "vXXXX"

    readme = f"""# _deploy_bundle/

一键部署包 (MobaXterm SFTP 拖到 /tmp/)

## 上传
MobaXterm SFTP: 拖 _deploy_bundle/ → 远端 /tmp/

## 部署
bash /tmp/_deploy_bundle/deploy.sh --version {version} --port 5001

## 回滚
bash /tmp/_deploy_bundle/rollback.sh --to <v> --port <p>

## 文件清单
- deploy.sh            部署入口 (含 precheck + smoke)
- precheck.sh          部署前 7 项检查
- smoke_test.sh        部署后 5 项真实功能测试
- rollback.sh          通用回滚
- unified_server.py    静态文件 + API 代理
- lib/common.sh        共享库
- {zip_path.name if zip_path else 'no zip'}  代码包
- README.txt           本文件

生成时间: {time.strftime("%Y-%m-%d %H:%M:%S")}
"""
    (bundle / "README.txt").write_text(readme, encoding="utf-8")
    print(f"  {GREEN}+{NC} README.txt")

    # 5. 总大小
    total_size = sum(f.stat().st_size for f in bundle.glob("**/*") if f.is_file())
    print(f"\n{GREEN}Bundle 大小: {total_size:,} bytes ({total_size/1024/1024:.2f} MB){NC}")
    print(f"{CYAN}路径: {bundle}{NC}")
    print()
    print(f"{YELLOW}下一步:{NC}")
    print(f"  1. MobaXterm SFTP: 拖 {bundle.name}/ 目录 → 远端 /tmp/")
    print(f"  2. 堡垒机 SSH 进 172.20.59.7")
    print(f"  3. 跑: bash /tmp/_deploy_bundle/deploy.sh --version {version} --port 5001")
    return 0


if __name__ == "__main__":
    sys.exit(main())
