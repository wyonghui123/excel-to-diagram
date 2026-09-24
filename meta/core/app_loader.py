# -*- coding: utf-8 -*-
"""
[多产品平台] 应用包加载器（PoC 1）

职责:
- 解析 apps/<app_id>/app.yaml 描述符 → AppManifest
- 校验必填字段、命名规范、路径存在性
- 扫描 apps/ 根目录, 发现所有应用包

设计约束:
- 本模块只做"解析 + 校验", 不做 Flask 注册 / DB 写入
  (注册与写入由 ApplicationBuilder.with_app() 承担, 见 roadmap §6.4)
- 不依赖任何平台重模块, 保证可独立单测、启动期快速失败

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md
  - §6.2  app.yaml 描述符规范
  - §6.5.1 F2  应用库路径
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# 应用 ID 规范: 小写字母开头, 仅含小写字母/数字/下划线
# 该 ID 会同时用作: 目录名 / 路由前缀 / DB 文件名 / 权限命名空间前缀
APP_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,39}$")

# 产品绑定模式 (roadmap §6.2)
PRODUCT_BINDING_MODES = ("fixed", "multi")

# 应用包内约定的子目录
SUBDIR_SCHEMAS = "schemas"
SUBDIR_BLUEPRINTS = "blueprints"
SUBDIR_COMPONENTS = "components"
SUBDIR_MIGRATIONS = "migrations"

MANIFEST_FILENAME = "app.yaml"


class AppManifestError(ValueError):
    """app.yaml 缺失、格式错误或校验失败。启动期快速失败用。"""


@dataclass
class ProductBinding:
    """应用与 platform.db 中 product 记录的绑定关系。

    mode='fixed': 应用与 product 1:1, 需 product_code
    mode='multi': 应用服务多条产品线, product 由客户自建
    """

    mode: str
    product_code: str = ""


@dataclass
class AppManifest:
    """app.yaml 的解析结果（不可变视图）。"""

    app_id: str
    name: str
    version: str
    app_dir: Path
    description: str = ""
    vendor: str = ""
    platform_min_version: str = ""
    platform_max_version: str = ""
    schemas: List[str] = field(default_factory=list)
    blueprints: List[str] = field(default_factory=list)
    components: List[str] = field(default_factory=list)
    migrations_dir: str = ""
    menu_internal_root: str = ""
    menu_portal_mount: Dict[str, Any] = field(default_factory=dict)
    permission_namespace: str = ""
    product_binding: Optional[ProductBinding] = None
    database_file: str = ""
    allowed_platform_modules: List[str] = field(default_factory=list)

    @property
    def route_prefix(self) -> str:
        """应用 API 路由前缀（roadmap §6.7）。"""
        return f"/api/v1/apps/{self.app_id}"

    @property
    def frontend_prefix(self) -> str:
        """应用前端路由前缀（roadmap §6.7）。"""
        return f"/app/{self.app_id}"

    def schema_paths(self) -> List[Path]:
        """应用 schema 文件的绝对路径列表。"""
        return [self.app_dir / p for p in self.schemas]

    def blueprint_paths(self) -> List[Path]:
        """应用 blueprint 文件的绝对路径列表。"""
        return [self.app_dir / p for p in self.blueprints]


def get_apps_root() -> Path:
    """应用包根目录: <repo>/apps。"""
    return Path(__file__).resolve().parents[2] / "apps"


def _require_str(raw: Dict[str, Any], key: str, ctx: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AppManifestError(f"{ctx}: 缺少必填字段 '{key}'（需为非空字符串）")
    return value.strip()


def _optional_str(raw: Dict[str, Any], key: str, default: str = "") -> str:
    value = raw.get(key)
    return value.strip() if isinstance(value, str) else default


def _str_list(raw: Dict[str, Any], key: str) -> List[str]:
    value = raw.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise AppManifestError(f"字段 '{key}' 需为字符串列表")
    return [v.strip() for v in value]


def _parse_product_binding(raw: Dict[str, Any], app_id: str) -> Optional[ProductBinding]:
    """解析并校验 product_binding（roadmap §6.2 的三条不变量之一）。"""
    node = raw.get("product_binding")
    if node is None:
        return None
    if not isinstance(node, dict):
        raise AppManifestError("product_binding 需为对象")

    mode = _optional_str(node, "mode")
    if mode not in PRODUCT_BINDING_MODES:
        raise AppManifestError(
            f"product_binding.mode 必须为 {PRODUCT_BINDING_MODES} 之一, 实际为 '{mode}'"
        )

    product_code = _optional_str(node, "product_code")
    if mode == "fixed" and not product_code:
        raise AppManifestError(
            f"app '{app_id}': product_binding.mode='fixed' 时必须提供 product_code"
        )
    return ProductBinding(mode=mode, product_code=product_code)


def _check_files_exist(app_dir: Path, rel_paths: List[str], kind: str) -> None:
    """校验 app.yaml 中声明的文件真实存在（启动期快速失败）。"""
    for rel in rel_paths:
        if not (app_dir / rel).is_file():
            raise AppManifestError(
                f"app '{app_dir.name}': {kind} 声明的文件不存在: {rel}"
            )


def load_manifest(app_dir: Path) -> AppManifest:
    """解析单个应用包的 app.yaml。

    Args:
        app_dir: 应用包目录（应含 app.yaml）

    Raises:
        AppManifestError: 文件缺失 / YAML 非法 / 校验不通过
    """
    app_dir = Path(app_dir)
    manifest_path = app_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise AppManifestError(f"未找到描述符: {manifest_path}")

    try:
        raw_all = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise AppManifestError(f"{manifest_path} YAML 解析失败: {e}") from e

    if not isinstance(raw_all, dict) or not isinstance(raw_all.get("app"), dict):
        raise AppManifestError(f"{manifest_path} 顶层需为 'app:' 对象")
    raw = raw_all["app"]

    app_id = _require_str(raw, "id", str(manifest_path))
    if not APP_ID_PATTERN.match(app_id):
        raise AppManifestError(
            f"app.id '{app_id}' 不符合规范 {APP_ID_PATTERN.pattern}"
            "（小写字母开头, 仅含小写字母/数字/下划线, 2-40 位）"
        )
    if app_id != app_dir.name:
        raise AppManifestError(
            f"app.id '{app_id}' 与目录名 '{app_dir.name}' 不一致"
            "（app_id 同时用作目录名/路由前缀/DB 文件名, 必须一致）"
        )

    namespace = _optional_str(raw, "permission_namespace") or app_id
    if namespace != app_id:
        raise AppManifestError(
            f"permission_namespace '{namespace}' 必须等于 app.id '{app_id}'"
            "（保证权限点前缀与路由前缀一致, roadmap §6.6）"
        )

    platform = raw.get("platform") or {}
    if not isinstance(platform, dict):
        raise AppManifestError("platform 需为对象")

    menu = raw.get("menu") or {}
    if not isinstance(menu, dict):
        raise AppManifestError("menu 需为对象")

    database = raw.get("database") or {}
    if not isinstance(database, dict):
        raise AppManifestError("database 需为对象")

    schemas = _str_list(raw, "schemas")
    blueprints = _str_list(raw, "blueprints")
    components = _str_list(raw, "components")

    migrations_dir = ""
    migrations_node = raw.get("migrations")
    if isinstance(migrations_node, dict):
        migrations_dir = _optional_str(migrations_node, "directory")
    elif isinstance(migrations_node, str):
        migrations_dir = migrations_node.strip()

    # 文件存在性校验
    _check_files_exist(app_dir, schemas, "schemas")
    _check_files_exist(app_dir, blueprints, "blueprints")
    _check_files_exist(app_dir, components, "components")

    return AppManifest(
        app_id=app_id,
        name=_require_str(raw, "name", str(manifest_path)),
        version=_require_str(raw, "version", str(manifest_path)),
        app_dir=app_dir,
        description=_optional_str(raw, "description"),
        vendor=_optional_str(raw, "vendor"),
        platform_min_version=_optional_str(platform, "min_version"),
        platform_max_version=_optional_str(platform, "max_version"),
        schemas=schemas,
        blueprints=blueprints,
        components=components,
        migrations_dir=migrations_dir,
        menu_internal_root=_optional_str(menu, "internal_root"),
        menu_portal_mount=menu.get("portal_mount") or {},
        permission_namespace=namespace,
        product_binding=_parse_product_binding(raw, app_id),
        database_file=_optional_str(database, "file"),
        allowed_platform_modules=_str_list(raw, "allowed_platform_modules"),
    )


def discover_apps(apps_root: Optional[Path] = None) -> Dict[str, AppManifest]:
    """扫描应用根目录, 返回 {app_id: AppManifest}。

    跳过下划线开头的目录（如 _template）与非目录项。
    """
    root = Path(apps_root) if apps_root else get_apps_root()
    manifests: Dict[str, AppManifest] = {}
    if not root.is_dir():
        return manifests

    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if not (child / MANIFEST_FILENAME).is_file():
            continue
        manifest = load_manifest(child)
        if manifest.app_id in manifests:
            raise AppManifestError(f"应用 ID 重复: {manifest.app_id}")
        manifests[manifest.app_id] = manifest
    return manifests


def load_apps(app_ids: List[str], apps_root: Optional[Path] = None) -> List[AppManifest]:
    """按 ID 列表加载应用包, 任一缺失即报错（供 --apps 启动参数使用）。"""
    available = discover_apps(apps_root)
    missing = [a for a in app_ids if a not in available]
    if missing:
        raise AppManifestError(
            f"未找到应用: {missing}; 可用应用: {sorted(available)}"
        )
    return [available[a] for a in app_ids]
