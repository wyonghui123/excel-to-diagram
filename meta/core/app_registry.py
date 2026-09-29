# -*- coding: utf-8 -*-
"""[多产品平台] 应用注册器（PoC 1 步骤 2）

职责: 把已加载的应用包注册到 Flask app
- schema: 累加注册到 YAML registry
- blueprint: 挂到 /api/v1/apps/<app_id>, 带路由冲突检测

分工:
- app_loader  : 解析 + 校验（不碰 Flask）
- app_registry: 注册（碰 Flask）

启用方式: 环境变量 ENABLED_APPS=hello_world,tms
  未设置 / 为空 → legacy 模式, 不加载任何应用（零行为变化）

对应方案: docs/platform/MULTI_PRODUCT_PLATFORM_ROADMAP.md
  - §6.3    启动流程
  - §6.4.1  生产路径二选一（本模块按"方案甲: 改 server.py"实现）
  - §6.7    路由命名空间
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import socket
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from meta.core.app_loader import AppManifest, get_apps_root, load_apps

logger = logging.getLogger(__name__)

# 启用应用的环境变量（逗号分隔）
ENV_ENABLED_APPS = "ENABLED_APPS"

# 应用 API 路由前缀模板（与 AppManifest.route_prefix 保持一致）
APP_API_PREFIX = "/api/v1/apps/"

# 平台通用 BO API 前缀（应用 BO 也由它提供 —— 路径里没有 app_id，见 §10.10）
BO_API_PREFIX = "/api/v2/bo/"


class AppRegistrationError(RuntimeError):
    """应用注册失败（blueprint 加载失败 / 路由冲突）。启动期快速失败。"""


# ─────────────────────────────────────────────────────────────────────────────
# [§6.5.3 改动 1] 请求 → 应用 归属索引（进程内，启动期由 register_apps 重建）
#
# 为什么需要它：应用 BO（如 `greeting`）经 `_register_app_schemas()` 进平台
# registry 后，由**平台通用 BO API** `/api/v2/bo/<object_type>` 提供 CRUD ——
# 该路径里没有 app_id。因此"应用 BO 请求属于哪个应用"只能靠注册期已知的
# bo → app 映射推断；仅按 URL 前缀绑定会让应用 BO 永远绑不上（§10.10）。
# ─────────────────────────────────────────────────────────────────────────────
_bo_to_app: Dict[str, str] = {}
_app_database_files: Dict[str, str] = {}

# ─────────────────────────────────────────────────────────────────────────────
# [A 可见性 2026-09-25] 本进程实际加载的应用（事实副本）
#
# 用途: ① `/health` 暴露（唯一存活的无鉴权探活点）；② 启动期落盘
# `runtime_apps.json` —— 让"这台服务器部署了哪些 app"在服务停止 / 日志滚动
# 之后依然可查。legacy 模式（未设置 ENABLED_APPS）恒为空列表 ⇒ 零行为变化。
# ─────────────────────────────────────────────────────────────────────────────
_loaded_manifests: List[AppManifest] = []

#: 启动期落盘文件名（与平台库同目录）
RUNTIME_APPS_FILENAME = "runtime_apps.json"


def get_loaded_apps() -> List[Dict[str, Any]]:
    """返回本进程已加载应用的序列化清单；legacy 模式为 []。"""
    return [
        {
            "id": m.app_id,
            "name": m.name,
            "version": m.version,
            "dir": str(m.app_dir),
            "route_prefix": m.route_prefix,
        }
        for m in _loaded_manifests
    ]


def write_runtime_apps_snapshot(db_path) -> Optional[str]:
    """把"本进程实际加载的应用"落盘到平台库同目录的 `runtime_apps.json`。

    这是**事实副本**（不是应然清单）：排查时可据此确认该服务器最后一次启动
    实际加载了哪些应用、从哪个 apps_root 加载、ENABLED_APPS 是什么。

    任何异常都只记 warning、返回 None —— 可见性功能绝不能阻断启动。
    """
    try:
        db_path = str(db_path)
        target_dir = Path(db_path).resolve().parent
        apps = get_loaded_apps()
        payload = {
            "service": "arch-data-manage-api",
            "mode": "enabled" if apps else "legacy",
            "enabled_apps": get_enabled_app_ids(),
            "apps": apps,
            "apps_root": str(get_apps_root()),
            "db_path": db_path,
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "written_at": datetime.now().isoformat(timespec="seconds"),
        }
        out = target_dir / RUNTIME_APPS_FILENAME
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(
            "[AppRegistry] %s 已落盘: mode=%s, enabled=%s, loaded=%s",
            out, payload["mode"], payload["enabled_apps"], [a["id"] for a in apps],
        )
        return str(out)
    except Exception as e:
        logger.warning("[AppRegistry] runtime_apps.json 落盘失败（不影响启动）: %s", e)
        return None


def get_app_id_for_bo(bo_id: str) -> Optional[str]:
    """返回某个 BO 所属的应用 ID；平台 BO 返回 None。"""
    return _bo_to_app.get(bo_id)


def get_app_database_file(app_id: str) -> str:
    """返回应用 `app.yaml` 声明的 `database.file`（未声明则空串）。"""
    return _app_database_files.get(app_id, "")


def parse_bo_object_type_from_path(path: str) -> Optional[str]:
    """从 `/api/v2/bo/<object_type>[/...]` 解析 object_type；非 BO 路由返回 None。

    解析结果**不可信**：调用方须再经 `get_app_id_for_bo` 判定是否属于某个应用
    —— 平台 BO（`product` / `version` / `architecture` 等）查不到映射，天然返回
    None，无需额外的保留字清单。
    """
    if not path:
        return None
    clean = path.split('?', 1)[0].split('#', 1)[0]
    if not clean.startswith(BO_API_PREFIX):
        return None
    remainder = clean[len(BO_API_PREFIX):]
    object_type = remainder.split('/', 1)[0]
    return object_type or None


def resolve_app_id_for_request(path: str) -> Optional[str]:
    """请求级归属解析（§6.5.3 改动 1 的入口）——返回 app_id 或 None。

    两条来源，按优先级：
    1. 应用自定义 API `/api/v1/apps/<app_id>/...` → 路径即归属
    2. 应用 BO 走平台通用 API `/api/v2/bo/<object_type>` → 靠注册期映射推断
    两者都不命中（平台请求）返回 None ⇒ 不绑定 ⇒ 走平台库。
    """
    app_id = parse_app_id_from_path(path)
    if app_id:
        return app_id
    object_type = parse_bo_object_type_from_path(path)
    if object_type:
        return _bo_to_app.get(object_type)
    return None


def reset_app_routing_index() -> None:
    """清空归属索引（仅供测试隔离使用；生产由 register_apps 启动期重建）。"""
    _bo_to_app.clear()
    _app_database_files.clear()
    del _loaded_manifests[:]


def get_enabled_app_ids() -> List[str]:
    """从环境变量读取启用的应用 ID 列表；未设置或为空返回 []。"""
    raw = os.environ.get(ENV_ENABLED_APPS, "") or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def parse_app_id_from_path(path: str) -> Optional[str]:
    """从请求路径解析应用 ID（§6.5 请求级数据源路由的入口）。

    只认应用 API 前缀 `/api/v1/apps/<app_id>[/...]`；平台路由返回 None
    （调用方据此不绑定 → 走平台库）。

    解析结果**不可信**：可能来自 URL，取值前须经 `get_app_db_path` 的安全校验。

    Examples:
        >>> parse_app_id_from_path('/api/v1/apps/hello_world/greetings')
        'hello_world'
        >>> parse_app_id_from_path('/api/v1/apps/hello_world')
        'hello_world'
        >>> parse_app_id_from_path('/api/v1/user') is None
        True
    """
    if not path:
        return None
    clean = path.split('?', 1)[0].split('#', 1)[0]
    if not clean.startswith(APP_API_PREFIX):
        return None
    remainder = clean[len(APP_API_PREFIX):]
    app_id = remainder.split('/', 1)[0]
    return app_id or None


def _load_module_from_path(path: Path, module_name: str):
    """按文件路径加载 Python 模块（应用 blueprint 不在包路径内）。"""
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise AppRegistrationError(f"无法加载模块: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_app_module(path: Path, module_name: str):
    """按文件路径加载应用内模块（公开入口，供事件 handler 加载复用）。"""
    return _load_module_from_path(path, module_name)


def _find_blueprints(module) -> list:
    """找出模块中定义的所有 Flask Blueprint 实例。"""
    from flask import Blueprint

    return [value for value in vars(module).values() if isinstance(value, Blueprint)]


def _route_signature(app) -> Dict[Tuple[str, str], str]:
    """(规则, 方法) → endpoint 的快照，用于路由冲突检测。"""
    signature: Dict[Tuple[str, str], str] = {}
    for rule in app.url_map.iter_rules():
        for method in rule.methods:
            signature[(rule.rule, method)] = rule.endpoint
    return signature


def _register_blueprints(app, manifest: AppManifest) -> int:
    """加载并注册某应用的 blueprints，返回注册的 blueprint 数。

    路由冲突时抛 AppRegistrationError（启动中止），避免运行期出现
    难以排查的路由覆盖。
    """
    prefix = manifest.route_prefix
    registered = 0

    for bp_path in manifest.blueprint_paths():
        module_name = f"app_bp_{manifest.app_id}_{bp_path.stem}"
        module = _load_module_from_path(bp_path, module_name)
        blueprints = _find_blueprints(module)
        if not blueprints:
            raise AppRegistrationError(
                f"app '{manifest.app_id}': {bp_path.name} 中未找到 Blueprint 实例"
            )

        for bp in blueprints:
            before = _route_signature(app)
            try:
                app.register_blueprint(bp, url_prefix=prefix)
            except Exception as e:  # noqa: BLE001 - 统一转成启动期错误
                raise AppRegistrationError(
                    f"app '{manifest.app_id}': blueprint '{bp.name}' 注册失败: {e}"
                ) from e

            after = _route_signature(app)
            conflicts = [
                key for key in after
                if key in before and before[key] != after[key]
            ]
            if conflicts:
                rule, method = conflicts[0]
                raise AppRegistrationError(
                    f"app '{manifest.app_id}': 路由冲突 {method} {rule} "
                    f"（平台已有 endpoint '{before[(rule, method)]}', "
                    f"应用为 '{after[(rule, method)]}'）"
                )
            registered += 1

    return registered


def _register_app_schemas(manifests: List[AppManifest]) -> Dict[str, List[str]]:
    """把应用 schema 目录累加注册到平台 YAML registry。

    Returns:
        {app_id: [应用**声明**的 BO id, ...]}
        用于后续"补建表"与"补菜单"——应用的 schema 是在平台建表/菜单流程
        之后才注册的, 因此需要单独补做（见 roadmap §10.2 缺口 A/B）。

    为什么用"声明"而非"本次新增"（与 L236 归属索引同一个坑）:
        `register_from_directory` 有**目录级缓存**，同一进程内第二次调用直接
        返回缓存、不产生新增 ⇒ 若按"新增"做补建表/补菜单，第二个 create_app()
        （多应用同启、测试、热重载）会**静默漏建表**，读写随即落到不存在的表。
        建表与菜单写入本身都是幂等的，按"声明"重放是安全的。
    """
    from meta.core.models import registry
    from meta.core.table_name_validator import invalidate_cache as invalidate_table_cache
    from meta.core.yaml_loader import load_yaml_directory, register_from_directory
    from meta.services.view_config_service import view_config_service

    declared_by_app: Dict[str, List[str]] = {}
    for manifest in manifests:
        schema_dir = manifest.app_dir / "schemas"
        if not schema_dir.is_dir():
            declared_by_app[manifest.app_id] = []
            continue

        before = set(registry.list_types())
        register_from_directory(str(schema_dir))
        added = sorted(set(registry.list_types()) - before)

        # [§6.5.3 改动 1] 登记 bo → app 归属：应用 BO 走平台通用 BO API，请求路径
        # 里没有 app_id，只能靠这份映射推断归属。**按应用声明的 schema 文件建立**
        # 而非"本次新增的 BO" —— register_from_directory 有目录级缓存，重复调用
        # 不产生新增，若按"新增"建映射会在 registry 已预热的场景下得到空映射，
        # 后果是应用请求静默读写平台库（数据错库）。
        declared = sorted(
            obj.id for obj in load_yaml_directory(str(schema_dir)) if obj is not None
        )
        for bo_id in declared:
            _bo_to_app[bo_id] = manifest.app_id

        # 补建表 / 补菜单同样按"声明"重放（幂等）—— 见函数 docstring
        declared_by_app[manifest.app_id] = declared

        logger.info(
            "[AppRegistry] app '%s': 注册 schema 目录 %s, 声明 BO: %s, 本次新增: %s",
            manifest.app_id, schema_dir, declared, added,
        )

    # 应用 schema 是新注册的, 必须失效两个缓存, 否则后续建表会被表名白名单拒绝:
    #   "Invalid table name: 'xxx'. Must be one of registered tables from YAML schemas."
    view_config_service.invalidate_cache()
    invalidate_table_cache()
    return declared_by_app


def _resolve_app_table_target(platform_data_source, manifest: AppManifest):
    """决定应用表建到哪个库（§6.5.3 改动 2）。

    `APP_DB_ROUTING=0`（默认）→ 平台库（现状，零行为变化）
    `APP_DB_ROUTING=1`        → 该应用自己的库

    刻意用 `open_app_data_source()` 而非 `bind_app_data_source()`：启动期没有
    请求上下文，绑定会把 app 数据源留在主线程 contextvars 上污染后续请求。
    """
    from meta.core.datasource import is_app_db_routing_enabled, open_app_data_source

    if not is_app_db_routing_enabled():
        return platform_data_source
    return open_app_data_source(manifest.app_id, manifest.database_file)


def _sync_app_tables(platform_data_source, manifest: AppManifest,
                     bo_ids: List[str]) -> int:
    """为应用的 BO 补建表。

    平台的建表流程（manage_api.init_services → sync_schema_from_meta）
    在 register_apps() 之前就已完成, 因此应用 BO 需在此补建。

    目标库由 `_resolve_app_table_target()` 决定（§6.5.3 改动 2）——**必须与
    改动 1（请求绑定）、改动 3（读取分流）同批开启**，否则会出现"表在 A 库、
    读写走 B 库"的不一致（§10.6 陷阱）。
    """
    if platform_data_source is None or not bo_ids:
        return 0

    target = _resolve_app_table_target(platform_data_source, manifest)
    if target is None:
        return 0

    from meta.core.models import registry
    from meta.core.schema_generator import sync_schema_from_meta

    meta_objects = []
    for bo_id in bo_ids:
        obj = registry.get(bo_id) if hasattr(registry, "get") else None
        if obj is not None:
            meta_objects.append(obj)
    if not meta_objects:
        return 0

    sync_schema_from_meta(target, meta_objects)
    logger.info(
        "[AppRegistry] app '%s': 建表目标 = %s",
        manifest.app_id, getattr(target, "_db_path", "<platform>"),
    )
    return len(meta_objects)


def _persist_app_menus(data_source, bo_ids: List[str]) -> int:
    """为应用的 BO 生成并写入菜单。

    必须 force=True —— menu_auto_generator._schema_mtime_changed() 只监视
    meta/schemas/, 不覆盖 apps/<app_id>/schemas/。
    """
    if data_source is None or not bo_ids:
        return 0

    from meta.services.menu_auto_generator import menu_auto_generator

    allowed = set(bo_ids)
    menus = [
        menu for menu in menu_auto_generator.generate_all()
        if menu.get("primary_object_type") in allowed
    ]
    if not menus:
        return 0
    return menu_auto_generator.persist_to_db(data_source, menus=menus, force=True)


def _ensure_app_root_menu(data_source, manifest: AppManifest) -> str:
    """按 app.yaml 的 menu.portal_mount 创建"应用根菜单"，返回其 menu_code。

    为什么必需（roadmap §6.6）:
        menu_auto_generator 写入的应用内菜单固定 show_in_sidebar=0,
        而菜单 API 只把 show_in_sidebar=1 的记录当顶层。
        因此应用内菜单**必须有父菜单**才可见 —— 本函数创建该父节点。
    """
    if data_source is None:
        return ""

    mount = manifest.menu_portal_mount or {}
    root_code = (mount.get("code") or f"app_{manifest.app_id}").strip()
    if not root_code:
        return ""

    # 声明的父菜单若不存在, 根菜单自己也会不可见 → 降级为顶层
    parent = (mount.get("parent") or "").strip()
    if parent:
        exists = data_source.execute(
            "SELECT 1 FROM menus WHERE menu_code = ? LIMIT 1", (parent,)
        ).fetchall()
        if not exists:
            logger.warning(
                "[AppRegistry] app '%s': portal_mount.parent '%s' 不存在 → 根菜单降级为顶层",
                manifest.app_id, parent,
            )
            parent = ""

    target_url = (mount.get("target_url") or "").strip()
    icon = (mount.get("icon") or "Box").strip()
    order = mount.get("order", 99)

    # show_in_sidebar=1 → 顶层可见；auto_generated=1 保持与自动菜单一致
    data_source.execute(
        """INSERT OR IGNORE INTO menus
        (menu_code, menu_name, menu_path, page_type, object_types,
         primary_object_type, bo_bindings, required_permissions,
         required_any_permission, data_permission_hint, page_config,
         parent_menu, icon, color, description, sort_order,
         is_active, show_in_sidebar, auto_generated)
        VALUES (?, ?, ?, '', '[]', '', '[]', '[]', 0, '{}', '{}', ?, ?, '', ?, ?, 1, 1, 1)""",
        (root_code, manifest.name, target_url, parent, icon,
         manifest.description, order),
    )
    # 幂等: 已存在时同步可变字段（改名/换图标/调顺序）
    data_source.execute(
        """UPDATE menus
           SET menu_name = ?, parent_menu = ?, icon = ?,
               sort_order = ?, menu_path = ?
         WHERE menu_code = ?""",
        (manifest.name, parent, icon, order, target_url, root_code),
    )
    return root_code


def _attach_app_menus_to_root(data_source, bo_ids: List[str], root_code: str) -> int:
    """把应用内菜单挂到应用根菜单下（否则它们因 show_in_sidebar=0 而不可见）。"""
    if data_source is None or not bo_ids or not root_code:
        return 0

    placeholders = ",".join("?" for _ in bo_ids)
    cursor = data_source.execute(
        f"UPDATE menus SET parent_menu = ? "
        f"WHERE primary_object_type IN ({placeholders})",
        (root_code, *bo_ids),
    )
    return getattr(cursor, "rowcount", 0) or len(bo_ids)


def _sync_app_permissions(data_source, bo_ids: List[str]) -> int:
    """为应用 BO 补写权限行（roadmap §6.5.2 缺口①）。

    为什么必需:
        平台的权限同步（server.py 的 init_auth_system → PermissionSyncService
        .sync_all()）跑在 register_apps() **之前**，且它是从**内存 registry** 推导
        权限码的 ⇒ 那一刻应用 BO 尚未注册，`permissions` 表永远不会有应用权限。
        后果：菜单 required_permissions 里的 `<bo>:<action>` 成了悬空权限，
        权限矩阵勾选应用菜单后"已同步 0 项功能权限"（实测见 §10.15）。

    Returns:
        本次新写入 `permissions` 表的权限码条数（幂等，重复启动返回 0）。

    为什么用 `PermissionSyncService(data_source)` 而非 `get_permission_sync_service()`:
        后者是模块级单例，init_auth 阶段可能已用**临时连接适配器**把它创建出来，
        该连接随后关闭 ⇒ 复用单例会静默丢弃写入。
    """
    if data_source is None or not bo_ids:
        return 0

    from meta.services.permission_sync_service import PermissionSyncService

    service = PermissionSyncService(data_source)
    created = 0
    for bo_id in bo_ids:
        result = service.sync_for_object(bo_id)
        created += len(result.get("created") or [])
    return created


def _aggregate_app_root_permissions(data_source, manifest: AppManifest,
                                    bo_ids: List[str], root_code: str) -> int:
    """把应用各 BO 的权限聚合到应用根菜单上（roadmap §6.5.2 缺口②）。

    为什么必需:
        应用内菜单由 menu_auto_generator 写入且固定 show_in_sidebar=0，而权限矩阵
        只把 show_in_sidebar=1 的菜单当授权单位 ⇒ 应用内菜单的 bo_bindings /
        required_permissions 读不到；应用根菜单虽可见却是个空壳
        （bindings=[] / reqperm=[]）⇒ 勾选应用菜单同步 0 项，权限矩阵里也看不到
        应用对象。本函数把各 BO 的声明**聚合写到根菜单**，对齐平台 hub 范式
        （如 arch-data 聚合 6 个 BO 的绑定）。

    为什么逐 BO 调 generate_object_list_menu，而不用 generate_multi_object_menu /
    _derive_bo_bindings(..., read_only=True):
        后者会把除首个以外的 BO 降级为只读（read_suffixes 只留 read/list/export），
        造成**少授权**。逐 BO 取全量绑定再合并去重才完整。

    刻意不动 page_type / object_types / primary_object_type:
        src/router/dynamicRoutes.js 会据 object_types 决定路由 props —— 改这三项
        会把应用 hub 变成对象列表页（§10.15 风险记录）。

    Returns:
        聚合后根菜单的权限码条数。
    """
    if data_source is None or not bo_ids or not root_code:
        return 0

    from meta.core.models import registry
    from meta.services.menu_auto_generator import menu_auto_generator

    bindings: List[dict] = []
    required: List[str] = []
    seen_bo_ids = set()
    seen_codes = set()
    resource_types: List[str] = []

    for bo_id in bo_ids:
        obj = registry.get(bo_id) if hasattr(registry, "get") else None
        if obj is None:
            continue
        menu = menu_auto_generator.generate_object_list_menu(obj)

        for binding in menu.get("bo_bindings") or []:
            binding_bo = binding.get("bo_id")
            if not binding_bo or binding_bo in seen_bo_ids:
                continue
            seen_bo_ids.add(binding_bo)
            bindings.append(binding)
            resource_types.append(binding_bo)

        for code in menu.get("required_permissions") or []:
            if code in seen_codes:
                continue
            seen_codes.add(code)
            required.append(code)

    if not required and not bindings:
        return 0

    hint = {
        "resource_types": resource_types,
        "message": f"建议分配{manifest.name}相关数据权限",
    }
    data_source.execute(
        """UPDATE menus
           SET bo_bindings = ?, required_permissions = ?, data_permission_hint = ?
           WHERE menu_code = ?""",
        (json.dumps(bindings, ensure_ascii=False),
         json.dumps(required, ensure_ascii=False),
         json.dumps(hint, ensure_ascii=False),
         root_code),
    )
    return len(required)


def _verify_installed(data_source, manifests: List[AppManifest]) -> None:
    """对照 installed_apps 登记做软校验（roadmap §6.3）——只告警, 不阻断启动。

    表不存在（未跑 v090 迁移的 legacy DB）属正常情况, 静默跳过。
    """
    if data_source is None:
        return
    try:
        rows = data_source.execute(
            "SELECT app_id, version FROM installed_apps"
        ).fetchall()
    except Exception:  # noqa: BLE001 - 表不存在即"未跑迁移", 不是错误
        logger.debug(
            "[AppRegistry] installed_apps 不可读（未跑 v090 迁移）→ 跳过安装校验"
        )
        return

    recorded = {row[0]: row[1] for row in rows}
    for manifest in manifests:
        installed_version = recorded.get(manifest.app_id)
        if installed_version is None:
            logger.warning(
                "[AppRegistry] app '%s' 已启用但无安装登记 → 请先执行 "
                "python tools/install_app.py install <package>.bip",
                manifest.app_id,
            )
        elif installed_version != manifest.version:
            logger.warning(
                "[AppRegistry] app '%s' 版本漂移: 安装登记 %s, 目录实际 %s "
                "→ 需重新安装（应用 migrations 尚未实现, 见 roadmap §6.3）",
                manifest.app_id, installed_version, manifest.version,
            )


def _register_event_contracts(manifests: List[AppManifest]) -> int:
    """登记 app.yaml 的 events 契约并做启动期校验（roadmap §6.14.4 ④）。

    Returns:
        登记的契约条数（publish + subscribe）

    Raises:
        EventContractError: 订阅了不存在的事件 / 来源应用未启用 / 缺幂等键
    """
    from meta.core.event_outbox import EventContractError, get_event_contract_registry

    registry = get_event_contract_registry()
    count = 0
    for manifest in manifests:
        for decl in manifest.events_publish:
            registry.register_publish(manifest.app_id, decl)
            count += 1
        for decl in manifest.events_subscribe:
            registry.register_subscribe(manifest.app_id, decl, str(manifest.app_dir))
            count += 1

    try:
        registry.validate([m.app_id for m in manifests])
    except EventContractError as e:
        raise AppRegistrationError(f"事件契约校验失败: {e}") from e
    return count


def _prepare_event_tables(manifests: List[AppManifest]) -> int:
    """为声明了 events 的应用准备 outbox / consumed_events 表。

    表位置与业务表一致（`resolve_event_data_source`）—— 这是 §6.14.4 ①
    "outbox 与业务写同库同事务"的前提。
    """
    from meta.core.event_consumer import ensure_consumed_table
    from meta.core.event_outbox import ensure_outbox_table, resolve_event_data_source

    prepared = 0
    for manifest in manifests:
        if not (manifest.events_publish or manifest.events_subscribe):
            continue
        data_source = resolve_event_data_source(manifest.app_id)
        ensure_outbox_table(data_source)
        ensure_consumed_table(data_source)
        prepared += 1
    return prepared


def _prepare_doc_flow(platform_data_source, manifests: List[AppManifest],
                      declared_by_app: Dict[str, List[str]]) -> int:
    """[DOC_FLOW Phase 1] 为声明 `doc_flow: enabled` 的应用准备派生基础设施。

    两件事（spec 2026-09-29 §3.2 / §5.3）：
    1. 边表建在**该应用业务表所在的库**（`_resolve_app_table_target` 同款裁定：
       routing off → 平台库 / routing on → 应用库）—— derive 必须"同库同事务"，
       边表与源/目标 BO 异库则事务不可达（F5 铁律，spec §2 关键边界）。
    2. 规则 upsert 到**平台库** doc_flow_rule（规则是跨应用管辖的元数据，§9.5）；
       upsert 只管声明字段、不覆盖 status 运行态（doc_flow_rule_store 模块注释）。

    启动期校验（快速失败）：
    - 规则的 source_bo / target_bo 必须是**本应用声明的 BO** —— 跨应用派生
      本质是 Phase 3 双记录镜像，Phase 1 直接在启动期拒绝（spec §2 裁定表）。
    - doc_flow 声明依赖 schema 注册（同库校验需要 BO 清单）→
      register_schemas=False 时启用 doc_flow 属配置错误。

    legacy 零行为变化：无任何应用声明 doc_flow 时**不做任何 DDL**
    （连平台库 doc_flow_rule 表都不建，验收项 §8.6"无 doc_flow 表"）。

    Returns:
        准备了边表的应用数（legacy / 未声明时为 0）。
    """
    doc_flow_apps = [m for m in manifests if m.doc_flow_enabled]
    if not doc_flow_apps or platform_data_source is None:
        return 0

    from meta.core.doc_flow_rule_store import (
        ensure_doc_flow_rule_table, upsert_rules,
    )
    from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables

    ensure_doc_flow_rule_table(platform_data_source)

    prepared = 0
    for manifest in doc_flow_apps:
        declared = declared_by_app.get(manifest.app_id) or []
        if not declared:
            raise AppRegistrationError(
                f"app '{manifest.app_id}': doc_flow.enabled 需要应用 schema 注册"
                "（register_schemas=True）—— 同库派生校验依赖本应用 BO 清单"
            )
        for rule in manifest.doc_flow_rules:
            missing = [
                bo for bo in (rule.source_bo, rule.target_bo)
                if bo not in declared
            ]
            if missing:
                raise AppRegistrationError(
                    f"app '{manifest.app_id}': doc_flow 规则 '{rule.rule_id}' "
                    f"引用了非本应用声明的 BO: {missing} —— Phase 1 仅支持"
                    f"同库派生（F5 事务不跨库，spec §2），跨应用派生归 Phase 3"
                )

        edge_ds = _resolve_app_table_target(platform_data_source, manifest)
        ensure_doc_flow_edge_tables(edge_ds)
        upsert_rules(
            platform_data_source,
            [r.to_store_dict() for r in manifest.doc_flow_rules],
        )
        logger.info(
            "[AppRegistry] app '%s': doc_flow 就绪（边表目标 = %s, 规则 %s 条）",
            manifest.app_id, getattr(edge_ds, "_db_path", "<platform>"),
            len(manifest.doc_flow_rules),
        )
        prepared += 1
    return prepared


def register_apps(
    app,
    app_ids: Optional[List[str]] = None,
    apps_root: Optional[Path] = None,
    register_schemas: bool = True,
    data_source=None,
) -> List[AppManifest]:
    """把启用的应用注册到 Flask app，返回已注册的 manifest 列表。

    Args:
        app: Flask 应用实例
        app_ids: 要加载的应用 ID 列表；None 时读环境变量 ENABLED_APPS
        apps_root: 应用包根目录；None 时用 <repo>/apps
        register_schemas: 是否注册应用 schema
        data_source: 平台数据源。提供时才会补建应用 BO 表、补生成应用菜单
            （两者在平台的启动流程中都早于本函数，见 roadmap §10.2）

    Returns:
        已注册的 AppManifest 列表（legacy 模式返回 []）
    """
    if app_ids is None:
        app_ids = get_enabled_app_ids()
    if not app_ids:
        logger.info("[AppRegistry] %s 未设置 → legacy 模式, 不加载应用", ENV_ENABLED_APPS)
        return []

    manifests = load_apps(list(app_ids), apps_root)
    # [§6.5.3 改动 1] 登记 app.yaml 的 database.file：请求绑定需用它解析应用库路径
    for manifest in manifests:
        _app_database_files[manifest.app_id] = manifest.database_file
    _verify_installed(data_source, manifests)

    declared_by_app: Dict[str, List[str]] = {}
    if register_schemas:
        declared_by_app = _register_app_schemas(manifests)

    for manifest in manifests:
        count = _register_blueprints(app, manifest)
        logger.info(
            "[AppRegistry] app '%s': 注册 %s 个 blueprint, 前缀 %s",
            manifest.app_id, count, manifest.route_prefix,
        )

    # [§6.14.4 ④] 事件契约：登记 + 启动期校验（订阅了不存在的事件即启动失败）
    # 契约登记与 data_source 无关（纯内存），因此放在建表/菜单补做之前
    contracts = _register_event_contracts(manifests)
    if contracts:
        logger.info("[AppRegistry] 事件契约 %s 条（publish + subscribe）", contracts)

    # 应用 schema 是在平台建表/菜单流程之后才注册的 → 需补做
    if register_schemas:
        for manifest in manifests:
            bo_ids = declared_by_app.get(manifest.app_id, [])
            if not bo_ids:
                continue
            tables = _sync_app_tables(data_source, manifest, bo_ids)
            menus = _persist_app_menus(data_source, bo_ids)
            # 顺序要求: 根菜单先存在, 才能把应用内菜单挂上去
            root_code = _ensure_app_root_menu(data_source, manifest)
            attached = _attach_app_menus_to_root(data_source, bo_ids, root_code)
            # [§6.5.2 缺口①] 应用权限行: 平台权限同步早于应用注册, 必须在此补写
            perms = _sync_app_permissions(data_source, bo_ids)
            # [§6.5.2 缺口②] 权限矩阵的授权单位是根菜单（应用内菜单 show_in_sidebar=0）
            root_perms = _aggregate_app_root_permissions(
                data_source, manifest, bo_ids, root_code
            )
            logger.info(
                "[AppRegistry] app '%s': 补建表 %s 个, 补菜单 %s 条, "
                "根菜单 '%s', 挂载 %s 条, 补权限 %s 条, 根菜单聚合 %s 条",
                manifest.app_id, tables, menus, root_code, attached,
                perms, root_perms,
            )

    # [§6.14.2] 事件表（outbox / consumed_events）：与业务表同库
    if data_source is not None:
        prepared = _prepare_event_tables(manifests)
        if prepared:
            logger.info("[AppRegistry] 事件表已就绪（%s 个应用）", prepared)

    # [DOC_FLOW Phase 1] 边表（随应用业务库）+ 规则注册（平台库）；未声明零 DDL
    if data_source is not None:
        doc_flow_prepared = _prepare_doc_flow(data_source, manifests, declared_by_app)
        if doc_flow_prepared:
            logger.info("[AppRegistry] doc_flow 已就绪（%s 个应用）", doc_flow_prepared)

    # [A 可见性 2026-09-25] 全部注册动作成功后才登记事实清单（供 /health 与落盘使用）
    _loaded_manifests[:] = manifests

    return manifests
