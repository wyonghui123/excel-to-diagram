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


def md5_file(path: Path) -> str:
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def check_bundle_vs_remote(bundle: Optional[Path], remote: str):
    """本地 vs 远端 bundle 对比 (输出本地 MD5, 让用户到远端对比)"""
    if not bundle or not bundle.exists():
        print(f"{RED}本地 bundle 不存在, 先跑: python tools/rebuild_bundle.py{NC}")
        return 1

    print(f"{CYAN}=== 本地 vs 远端 bundle 对比 ==={NC}\n")
    print(f"本地 bundle: {bundle.resolve()}")
    print()

    # 计算本地所有文件 MD5
    local_files = sorted([f for f in bundle.glob("**/*") if f.is_file()])
    print(f"{CYAN}本地文件 (用于远端对比):{NC}")
    for f in local_files:
        rel = f.relative_to(bundle)
        m = md5_file(f)
        print(f"  md5sum /tmp/deploy_bundle/{rel}     # {m}")
    print()
    print(f"{YELLOW}到远端堡垒机跑以下命令对比:{NC}")
    print(f"  ssh {remote}")
    print(f"  cd /tmp/deploy_bundle/")
    print(r"  for f in $(find . -type f); do md5sum $f; done")
    print()
    print(f"{YELLOW}或者 (Windows 用户, 用 MobaXterm SFTP 拖新 bundle 覆盖后):{NC}")
    print(f"  python tools/rebuild_bundle.py  # 重新生成")
    print(f"  MobaXterm SFTP: 拖 deploy_bundle/ → 远端 /tmp/")
    return 0


def main():
    parser = argparse.ArgumentParser(description="重建 deploy_bundle/ (SFTP 一键上传到远端)")
    parser.add_argument("--zip", help="zip 路径 (默认: 最新 deploy-v*.zip)")
    parser.add_argument("--output", default="deploy_bundle", help="输出目录 (默认 deploy_bundle, 无下划线避免 IDE 隐藏)")
    parser.add_argument("--clean", action="store_true", help="只清空输出目录")
    parser.add_argument("--list", action="store_true", help="只列出 deploy-v*.zip")
    parser.add_argument("--check", action="store_true", help="本地 vs 远端 bundle 版本对比 (需 --remote)")
    parser.add_argument("--remote", help="远端 SSH (user@host) 用于 --check")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    tools_dir = repo_root / "tools"

    if args.list:
        print(f"{CYAN}可用的 deploy-v*.zip:{NC}")
        for z in list_zips(repo_root):
            print(f"  {z.name}  ({z.stat().st_size:,} bytes)")
        return 0

    if args.check:
        if not args.remote:
            print(f"{RED}--check 需要 --remote user@host{NC}")
            return 1
        # 比较本地 vs 远端 bundle 版本
        return check_bundle_vs_remote(bundle if bundle.exists() else None, args.remote)

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
        "diagnose.sh",
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

    # [CHG 2026-07-06] 修 bundle 内所有 .sh 的 CRLF → LF
    # 背景: Windows git checkout 自动 LF → CRLF, yonaa Linux bash 解析失败
    sh_count = 0
    for sh_file in bundle.rglob('*.sh'):
        data = sh_file.read_bytes()
        if b'\r\n' in data:
            sh_file.write_bytes(data.replace(b'\r\n', b'\n'))
            sh_count += 1
    if sh_count > 0:
        print(f"  {GREEN}+{NC} 修 CRLF → LF: {sh_count} 个 .sh 文件")

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
    file_count = sum(1 for f in bundle.glob("**/*") if f.is_file())
    print(f"\n{GREEN}Bundle 大小: {total_size:,} bytes ({total_size/1024/1024:.2f} MB){NC}")
    print(f"{CYAN}路径: {bundle}{NC}")
    print(f"{CYAN}文件数: {file_count}{NC}")
    print()
    print(f"{YELLOW}完整文件清单 (强制刷新 IDE/Explorer 缓存后可见):{NC}")
    for f in sorted(bundle.glob("**/*")):
        if f.is_file():
            rel = f.relative_to(bundle)
            size = f.stat().st_size
            print(f"  {rel}  ({size:,} bytes)")
    print()
    print(f"{YELLOW}下一步:{NC}")
    print(f"  1. MobaXterm SFTP: 拖 {bundle.name}/ 目录 → 远端 /tmp/")
    print(f"  2. 堡垒机 SSH 进 172.20.59.7")
    print(f"  3. 跑: bash /tmp/{bundle.name}/deploy.sh --version {version} --port 5001")
    print()
    if file_count < 9:
        print(f"{RED}⚠️  警告: 文件数 {file_count} < 9, 可能有文件丢失!{NC}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
