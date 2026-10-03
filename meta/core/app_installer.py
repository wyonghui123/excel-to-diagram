# -*- coding: utf-8 -*-
"""[多产品平台] 应用安装 / 卸载 / 登记（PoC 1 步骤 3 / 6）

职责:
- install_app():   解包 .bip → apps/<app_id>/ → 写 installed_apps 登记
- uninstall_app(): 清菜单 + 删登记 (+ 可选清理应用目录)
- list_installed() / get_installed(): 读登记表

边界:
- 本模块碰 DB（installed_apps / menus）, 但**不碰 Flask** → 可独立单测
- 应用菜单本身由启动期 register_apps() 生成（roadmap §6.6 双层菜单）,
  本模块只负责**登记**与**卸载清理**

已知缺口（Phase 1 未开始, 见 roadmap §10.2）:
- 应用 migrations/ 未执行 —— 依赖 §6.5.1 F2 多库路径入口
- 应用独立 DB 未启用 —— 当前应用表仍建在平台库

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md
  - §6.1  目录结构
  - §6.3  启动流程（Loader 查 installed_apps）
  - §10   PoC 1 步骤 3 / 6
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from meta.core.app_loader import AppManifestError, get_apps_root, load_manifest
from meta.core.app_package import (
    extract_package,
    read_bo_ids,
    read_package_manifest,
)

logger = logging.getLogger(__name__)

INSTALLED_APPS_TABLE = "installed_apps"

# 安装登记表 DDL —— 单一事实源:
#   meta/migrations/v090__create_installed_apps.py 直接引用本常量,
#   避免"迁移脚本 + 运行时 ensure"两处 DDL 漂移
INSTALLED_APPS_DDL = f"""
CREATE TABLE IF NOT EXISTS {INSTALLED_APPS_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id VARCHAR(40) NOT NULL UNIQUE,
    app_name VARCHAR(128) NOT NULL DEFAULT '',
    version VARCHAR(32) NOT NULL DEFAULT '',
    vendor VARCHAR(64) NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    permission_namespace VARCHAR(40) NOT NULL DEFAULT '',
    product_binding_mode VARCHAR(16) NOT NULL DEFAULT '',
    product_code VARCHAR(64) NOT NULL DEFAULT '',
    database_file VARCHAR(512) NOT NULL DEFAULT '',
    bo_ids TEXT NOT NULL DEFAULT '[]',
    menu_root_code VARCHAR(64) NOT NULL DEFAULT '',
    package_file VARCHAR(512) NOT NULL DEFAULT '',
    package_sha256 VARCHAR(64) NOT NULL DEFAULT '',
    app_dir VARCHAR(512) NOT NULL DEFAULT '',
    installed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

# 列顺序（INSERT / SELECT 共用, 防止两处漂移）
_COLUMNS = (
    "app_id", "app_name", "version", "vendor", "description",
    "permission_namespace", "product_binding_mode", "product_code",
    "database_file", "bo_ids", "menu_root_code",
    "package_file", "package_sha256", "app_dir",
)


class AppInstallError(RuntimeError):
    """安装 / 卸载失败。"""


def ensure_installed_apps_table(data_source) -> None:
    """确保 installed_apps 表存在（幂等）。"""
    data_source.execute(INSTALLED_APPS_DDL)


def _row_to_dict(row, description=None) -> Dict[str, Any]:
    keys = [d[0] for d in description] if description else list(_COLUMNS) + [
        "installed_at", "updated_at",
    ]
    record = dict(zip(keys, row))
    raw_bo_ids = record.get("bo_ids")
    if isinstance(raw_bo_ids, str):
        try:
            record["bo_ids"] = json.loads(raw_bo_ids)
        except json.JSONDecodeError:
            record["bo_ids"] = []
    return record


def get_installed(data_source, app_id: str) -> Optional[Dict[str, Any]]:
    """读单个应用的安装登记；未安装返回 None。"""
    ensure_installed_apps_table(data_source)
    cursor = data_source.execute(
        f"SELECT * FROM {INSTALLED_APPS_TABLE} WHERE app_id = ?", (app_id,)
    )
    row = cursor.fetchone()
    return _row_to_dict(row, cursor.description) if row else None


def list_installed(data_source) -> List[Dict[str, Any]]:
    """列出全部安装登记（按 app_id 排序）。"""
    ensure_installed_apps_table(data_source)
    cursor = data_source.execute(
        f"SELECT * FROM {INSTALLED_APPS_TABLE} ORDER BY app_id"
    )
    return [_row_to_dict(row, cursor.description) for row in cursor.fetchall()]


def _backup_dir(apps_root: Path, app_id: str) -> Path:
    """覆盖安装前把旧目录挪到这里。

    目录名以 `_` 开头 → app_loader.discover_apps() 会跳过, 不会当成应用。
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return apps_root / "_backup" / f"{app_id}-{stamp}"


def _upsert_record(data_source, record: Dict[str, Any]) -> None:
    columns = ", ".join(_COLUMNS)
    placeholders = ", ".join("?" for _ in _COLUMNS)
    updates = ", ".join(
        f"{col} = excluded.{col}" for col in _COLUMNS if col != "app_id"
    )
    values = [record.get(col, "") for col in _COLUMNS]
    data_source.execute(
        f"""INSERT INTO {INSTALLED_APPS_TABLE} ({columns}, updated_at)
        VALUES ({placeholders}, CURRENT_TIMESTAMP)
        ON CONFLICT(app_id) DO UPDATE SET {updates},
            updated_at = CURRENT_TIMESTAMP""",
        tuple(values),
    )


def _install_dependency_findings(manifest, apps_root: Path, data_source) -> list:
    """[S6 / G5] 安装期依赖校验：平台版本 + requires 的 BO / 规则。

    可用集合 = installed_apps 登记的 bo_ids ∪ 已安装应用 manifest 的声明并集
    （后者读不到时降级为仅用登记 bo_ids，规则依赖校验随之降级）。
    """
    from meta.core.app_dependency import collect_declared_ids, validate_dependencies
    from meta.core.app_loader import load_apps

    bo_ids: set = set()
    rule_ids: set = set()
    try:
        records = list_installed(data_source)
    except Exception as e:  # noqa: BLE001 - 登记表不可读不该阻断安装
        logger.debug("[AppInstaller] installed_apps 不可读 → 依赖校验降级: %s", e)
        records = []
    installed_ids = []
    for rec in records:
        bo_ids.update(rec.get("bo_ids") or [])
        if rec.get("app_id"):
            installed_ids.append(rec["app_id"])

    if installed_ids:
        try:
            declared_bos, rule_ids = collect_declared_ids(
                load_apps(installed_ids, apps_root))
            bo_ids |= declared_bos
        except Exception as e:  # noqa: BLE001 - manifest 加载失败 → 降级
            logger.debug(
                "[AppInstaller] 已安装应用 manifest 加载失败 → 规则依赖校验降级: %s", e)

    return validate_dependencies(
        manifest, available_bo_ids=bo_ids, available_rule_ids=rule_ids)


def install_app(
    bip_path: Path,
    apps_root: Optional[Path] = None,
    data_source=None,
    force: bool = False,
) -> Dict[str, Any]:
    """安装（或覆盖升级）一个应用包。

    Args:
        bip_path: .bip 包路径
        apps_root: 应用根目录, 默认 <repo>/apps
        data_source: 平台数据源
        force: 目标目录已存在时是否覆盖（覆盖前备份到 apps/_backup/）

    Returns:
        安装登记记录 dict（含 purged_backup 字段）
    """
    if data_source is None:
        raise AppInstallError("install_app 需要平台 data_source")

    bip_path = Path(bip_path)
    package_manifest = read_package_manifest(bip_path)
    app_id = package_manifest["app_id"]

    root = Path(apps_root) if apps_root else get_apps_root()
    target_dir = root / app_id

    backup_path = ""
    if target_dir.exists():
        if not force:
            raise AppInstallError(
                f"应用目录已存在: {target_dir}（覆盖请加 --force, "
                f"旧目录会备份到 {root / '_backup'}）"
            )
        backup = _backup_dir(root, app_id)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target_dir), str(backup))
        backup_path = str(backup)
        logger.info("[AppInstaller] 旧目录已备份: %s", backup_path)

    extract_package(bip_path, target_dir)

    # 解包后重新解析 app.yaml —— 既校验包内容自洽, 也防止 manifest.json 与
    # app.yaml 不一致（app.yaml 是唯一事实源）
    try:
        manifest = load_manifest(target_dir)
    except AppManifestError as e:
        raise AppInstallError(f"解包后的 app.yaml 校验失败: {e}") from e
    if manifest.app_id != app_id or manifest.version != package_manifest["version"]:
        raise AppInstallError(
            f"包内容不一致: manifest.json 声明 {app_id}@{package_manifest['version']}, "
            f"app.yaml 为 {manifest.app_id}@{manifest.version}"
        )

    # [S6 / G5] 依赖校验：平台版本 + requires 的 BO / 规则缺失 → 拒绝安装
    # （数据先解包再回滚成本高, 故在写登记前拦截; 失败时保留已解包目录,
    #   与"覆盖安装前已备份"的既有行为一致 —— 由调用方决定是否清理）
    findings = _install_dependency_findings(manifest, root, data_source)
    if findings:
        raise AppInstallError(
            f"应用 '{manifest.app_id}' 依赖校验失败: "
            + "; ".join(f"[{f.code}] {f.detail}" for f in findings)
        )

    mount = manifest.menu_portal_mount or {}
    record = {
        "app_id": manifest.app_id,
        "app_name": manifest.name,
        "version": manifest.version,
        "vendor": manifest.vendor,
        "description": manifest.description,
        "permission_namespace": manifest.permission_namespace,
        "product_binding_mode": (
            manifest.product_binding.mode if manifest.product_binding else ""
        ),
        "product_code": (
            manifest.product_binding.product_code if manifest.product_binding else ""
        ),
        "database_file": manifest.database_file,
        "bo_ids": json.dumps(read_bo_ids(manifest), ensure_ascii=False),
        "menu_root_code": (mount.get("code") or f"app_{manifest.app_id}").strip(),
        "package_file": bip_path.name,
        "package_sha256": "",
        "app_dir": str(target_dir),
    }
    record["package_sha256"] = _file_sha256(bip_path)

    ensure_installed_apps_table(data_source)
    _upsert_record(data_source, record)

    logger.info(
        "[AppInstaller] 已安装 app '%s'@%s → %s（BO: %s）",
        manifest.app_id, manifest.version, target_dir, record["bo_ids"],
    )
    result = dict(record)
    result["bo_ids"] = json.loads(record["bo_ids"])
    result["backup_path"] = backup_path
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _delete_app_menus(data_source, app_id: str, record: Dict[str, Any]) -> int:
    """删除应用根菜单 + 应用内菜单，返回删除行数。

    应用内菜单的定位靠 installed_apps.bo_ids —— 这样即使应用目录已被删除
    也能清干净（卸载顺序: 先清菜单, 再按策略处理文件）。
    """
    bo_ids = record.get("bo_ids") or []
    root_code = record.get("menu_root_code") or f"app_{app_id}"

    deleted = 0
    cursor = data_source.execute(
        "DELETE FROM menus WHERE menu_code = ?", (root_code,)
    )
    deleted += getattr(cursor, "rowcount", 0) or 0

    if bo_ids:
        placeholders = ",".join("?" for _ in bo_ids)
        cursor = data_source.execute(
            f"DELETE FROM menus WHERE primary_object_type IN ({placeholders})",
            tuple(bo_ids),
        )
        deleted += getattr(cursor, "rowcount", 0) or 0
    return deleted


def uninstall_app(
    app_id: str,
    apps_root: Optional[Path] = None,
    data_source=None,
    purge_files: bool = False,
) -> Dict[str, Any]:
    """卸载应用: 清菜单 → 删登记 →（可选）删应用目录。

    默认**保留**应用目录与已建表 —— 卸载只回收"可见性"与登记,
    避免误删业务数据（库表清理需显式 DBA 操作）。
    """
    if data_source is None:
        raise AppInstallError("uninstall_app 需要平台 data_source")

    record = get_installed(data_source, app_id)
    if record is None:
        raise AppInstallError(f"应用未安装: {app_id}")

    menus_deleted = _delete_app_menus(data_source, app_id, record)
    data_source.execute(
        f"DELETE FROM {INSTALLED_APPS_TABLE} WHERE app_id = ?", (app_id,)
    )

    purged_dir = ""
    if purge_files:
        root = Path(apps_root) if apps_root else get_apps_root()
        target_dir = root / app_id
        if target_dir.is_dir():
            shutil.rmtree(target_dir)
            purged_dir = str(target_dir)
            logger.info("[AppInstaller] 已删除应用目录: %s", purged_dir)

    logger.info(
        "[AppInstaller] 已卸载 app '%s': 清菜单 %s 条, 删除目录=%s",
        app_id, menus_deleted, purged_dir or "(保留)",
    )
    return {
        "app_id": app_id,
        "version": record.get("version", ""),
        "menus_deleted": menus_deleted,
        "purged_dir": purged_dir,
    }
