# -*- coding: utf-8 -*-
"""[多产品平台] 应用打包 CLI（PoC 1 步骤 2）

用法:
    python tools/build_app.py ./apps/hello_world
    python tools/build_app.py ./apps/hello_world -o dist

产出:
    dist/<app_id>-<version>.bip   （zip: manifest.json + app.yaml + schemas/... ）

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §10 PoC 1 步骤 2
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meta.core.app_package import AppPackageError, build_package, read_package_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description='把 apps/<app_id>/ 打成 .bip 应用包')
    parser.add_argument('app_dir', help='应用目录（须含 app.yaml）')
    parser.add_argument('-o', '--out-dir', default=None,
                        help='输出目录（默认 <repo>/dist）')
    args = parser.parse_args()

    try:
        bip_path = build_package(Path(args.app_dir), args.out_dir)
    except AppPackageError as e:
        print(f'[build_app] 打包失败: {e}')
        return 1

    manifest = read_package_manifest(bip_path)
    size_kb = bip_path.stat().st_size / 1024
    print(f'[build_app] 产出: {bip_path}  ({size_kb:.1f} KB)')
    print(f'[build_app] app={manifest["app_id"]} version={manifest["version"]} '
          f'format={manifest["format_version"]} BO={manifest["bo_ids"]}')
    print(f'[build_app] 含 {len(manifest["files"])} 个文件:')
    for entry in manifest['files']:
        print(f'    {entry["path"]}  ({entry["size"]} B, {entry["sha256"][:12]}…)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
