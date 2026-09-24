# -*- coding: utf-8 -*-
"""[多产品平台] 应用安装 / 卸载 / 列表 CLI（PoC 1 步骤 3 / 6）

用法:
    python tools/install_app.py install dist/hello_world-1.0.0.bip
    python tools/install_app.py install dist/hello_world-1.0.1.bip --force
    python tools/install_app.py uninstall hello_world [--purge-files]
    python tools/install_app.py list

平台库路径解析顺序: --db > 环境变量 SQLITE_DB_PATH > <repo>/meta/architecture.db
（与 meta/core/db_path.py 一致）

注意: 应用菜单的**生成**发生在启动期 register_apps()（roadmap §6.6），
      本 CLI 只写安装登记与卸载清理 —— 安装后需重启服务才看得到菜单。

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md §10 PoC 1 步骤 3 / 6
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meta.core.app_installer import (  # noqa: E402
    AppInstallError,
    install_app,
    list_installed,
    uninstall_app,
)
from meta.core.app_package import AppPackageError  # noqa: E402
from meta.core.datasource import get_data_source  # noqa: E402
from meta.core.db_path import get_meta_db_path  # noqa: E402


def _open_data_source(db_path: str):
    return get_data_source('sqlite', database=db_path)


def _cmd_install(args) -> int:
    ds = _open_data_source(args.db)
    try:
        record = install_app(
            Path(args.bip), apps_root=args.apps_root, data_source=ds, force=args.force,
        )
    finally:
        ds.disconnect()

    print(f'[install_app] 已安装 {record["app_id"]}@{record["version"]}')
    print(f'[install_app]   应用目录: {record["app_dir"]}')
    print(f'[install_app]   权限命名空间: {record["permission_namespace"]}  '
          f'产品绑定: {record["product_binding_mode"]}'
          f'{"/" + record["product_code"] if record["product_code"] else ""}')
    print(f'[install_app]   业务对象: {record["bo_ids"]}  '
          f'根菜单: {record["menu_root_code"]}')
    if record.get('backup_path'):
        print(f'[install_app]   旧目录已备份: {record["backup_path"]}')
    print('[install_app] 提示: 菜单在服务启动时生成 → 重启服务后可见')
    return 0


def _cmd_uninstall(args) -> int:
    ds = _open_data_source(args.db)
    try:
        result = uninstall_app(
            args.app_id, apps_root=args.apps_root, data_source=ds,
            purge_files=args.purge_files,
        )
    finally:
        ds.disconnect()

    print(f'[install_app] 已卸载 {result["app_id"]}@{result["version"]}')
    print(f'[install_app]   清理菜单: {result["menus_deleted"]} 条')
    print(f'[install_app]   应用目录: {result["purged_dir"] or "保留（加 --purge-files 删除）"}')
    print('[install_app] 注意: 已建业务表默认保留（避免误删数据），需清理请走 DBA 流程')
    return 0


def _cmd_list(args) -> int:
    ds = _open_data_source(args.db)
    try:
        records = list_installed(ds)
    finally:
        ds.disconnect()

    if not records:
        print('[install_app] 未安装任何应用')
        return 0
    print(f'[install_app] 已安装 {len(records)} 个应用:')
    for r in records:
        print(f'  - {r["app_id"]}@{r["version"]}  {r["app_name"]}  '
              f'BO={r["bo_ids"]}  安装于 {r["installed_at"]}')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='多产品平台应用安装工具')
    parser.add_argument('--db', default=None,
                        help='平台库路径（默认 SQLITE_DB_PATH 或 meta/architecture.db）')
    parser.add_argument('--apps-root', default=None, type=Path,
                        help='应用根目录（默认 <repo>/apps）')
    sub = parser.add_subparsers(dest='action', required=True)

    p_install = sub.add_parser('install', help='安装 / 覆盖升级应用包')
    p_install.add_argument('bip', help='.bip 包路径')
    p_install.add_argument('--force', action='store_true',
                           help='目标目录已存在时覆盖（旧目录备份到 apps/_backup/）')
    p_install.set_defaults(func=_cmd_install)

    p_uninstall = sub.add_parser('uninstall', help='卸载应用（清菜单 + 删登记）')
    p_uninstall.add_argument('app_id', help='应用 ID')
    p_uninstall.add_argument('--purge-files', action='store_true',
                             help='同时删除 apps/<app_id>/ 目录')
    p_uninstall.set_defaults(func=_cmd_uninstall)

    p_list = sub.add_parser('list', help='列出已安装应用')
    p_list.set_defaults(func=_cmd_list)

    args = parser.parse_args()
    if args.db is None:
        args.db = get_meta_db_path()
    print(f'[install_app] 平台库: {args.db}')

    try:
        return args.func(args)
    except (AppInstallError, AppPackageError) as e:
        print(f'[install_app] 失败: {e}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
