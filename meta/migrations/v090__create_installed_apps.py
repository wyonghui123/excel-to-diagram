# -*- coding: utf-8 -*-
"""[v090 2026-09-24] 多产品平台: 新建 installed_apps 应用安装登记表

背景 (docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md):
  §1.3  App Instance（某个部署实例内被加载的某个应用）此前无任何持久记录。
  §6.3  启动流程要求 Loader 查 installed_apps 判断"是否已装 / 版本是否变化"。
  §10   PoC 1 步骤 3 通过标准: 安装后 installed_apps 出现记录。

策略 (CREATE-only, 幂等):
  1. CREATE TABLE IF NOT EXISTS installed_apps (...)
  2. 已存在则原样保留（不 ALTER、不 DROP、不动数据）

DDL 单一事实源:
  表结构常量定义在 meta/core/app_installer.py 的 INSTALLED_APPS_DDL ——
  运行时 ensure_installed_apps_table() 与本迁移共用同一份 DDL, 防止漂移。

不动:
  - menus（应用根菜单由启动期 register_apps() 生成, 不属于本迁移职责）
  - 任何既有表

幂等性:
  - CREATE TABLE IF NOT EXISTS 天然幂等
  - verify: installed_apps 存在且列清单与 DDL 一致

downgrade:
  支持 —— DROP TABLE IF EXISTS installed_apps（仅登记信息, 可重装恢复）
"""
import sqlite3
import sys
from pathlib import Path

# 允许以 `python meta/migrations/v090__create_installed_apps.py` 直接执行
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from meta.core.app_installer import INSTALLED_APPS_DDL, INSTALLED_APPS_TABLE  # noqa: E402

# verify 用: 期望列（与 INSTALLED_APPS_DDL 对应）
EXPECTED_COLUMNS = (
    "id", "app_id", "app_name", "version", "vendor", "description",
    "permission_namespace", "product_binding_mode", "product_code",
    "database_file", "bo_ids", "menu_root_code",
    "package_file", "package_sha256", "app_dir",
    "installed_at", "updated_at",
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """[v090 CREATE] 幂等创建 installed_apps 表。"""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v090] DB 不存在: {db_path}')
        return False

    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        existed = _table_exists(conn, INSTALLED_APPS_TABLE)
        conn.executescript(INSTALLED_APPS_DDL)
        conn.commit()
        if existed:
            rows = conn.execute(
                f'SELECT COUNT(*) FROM {INSTALLED_APPS_TABLE}'
            ).fetchone()[0]
            print(f'[v090] {INSTALLED_APPS_TABLE} 已存在 (rows={rows}) → 保留不动')
        else:
            print(f'[v090] 已创建 {INSTALLED_APPS_TABLE}')
        return True
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """[v090 verify] installed_apps 存在且列清单完整。"""
    db_path = Path(db_path)
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, INSTALLED_APPS_TABLE):
            print(f'[v090 verify] FAIL: {INSTALLED_APPS_TABLE} 不存在')
            return False
        actual = tuple(r[1] for r in conn.execute(
            f'PRAGMA table_info({INSTALLED_APPS_TABLE})'
        ).fetchall())
        missing = [c for c in EXPECTED_COLUMNS if c not in actual]
        if missing:
            print(f'[v090 verify] FAIL: 缺列 {missing}')
            return False
        print(f'[v090 verify] OK: {INSTALLED_APPS_TABLE} 列完整 ({len(actual)} 列)')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """[v090 downgrade] DROP installed_apps（仅登记信息, 可重装恢复）。"""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v090] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        conn.execute(f'DROP TABLE IF EXISTS {INSTALLED_APPS_TABLE}')
        conn.commit()
        print(f'[v090] 已 DROP {INSTALLED_APPS_TABLE}')
        return True
    finally:
        conn.close()


if __name__ == '__main__':
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(get_meta_db_path())
    print(f'[v090] migrating {db}')
    ok = migrate(db)
    print(f'[v090] migrate: {"OK" if ok else "FAIL"}')
    v = verify(db)
    print(f'[v090] verify: {"PASS" if v else "FAIL"}')
    sys.exit(0 if (ok and v) else 1)
