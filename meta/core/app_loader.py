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

#: 事件触发点（roadmap §6.14.3）；与平台 action 常量的对应关系见
#: `meta/core/event_outbox.py` 的 ACTION_TO_TRIGGER
EVENT_TRIGGERS = ("after_create", "after_update", "after_delete")


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
class EventPublishDecl:
    """发布声明（roadmap §6.14.3）。

    ```yaml
    events:
      publish:
        - name: outbound_completed
          entity: outbound_order      # 本应用的 BO id
          trigger: after_update
          condition: "status == 'shipped'"   # 可选
          payload: [order_no, quantity]      # 只带必要字段
    ```
    """

    name: str
    entity: str
    trigger: str
    condition: str = ""
    payload: List[str] = field(default_factory=list)


@dataclass
class EventSubscribeDecl:
    """订阅声明（roadmap §6.14.3）。

    ```yaml
    events:
      subscribe:
        - name: outbound_completed
          from: warehouse                    # 来源应用（启动期校验必须存在发布方）
          handler: blueprints/handlers/on_outbound_completed.py
          idempotency_key: "order_no"        # 去重依据（at-least-once，硬要求）
    ```
    """

    name: str
    source_app: str
    handler: str
    idempotency_key: str


@dataclass
class DocFlowRuleDecl:
    """单据流派生规则声明（DOC_FLOW Phase 1，spec 2026-09-29 §5.3）。

    ```yaml
    doc_flow:
      enabled: true
      rules:
        - rule_id: demo-sales-to-delivery-v1
          source_bo: demo_sales_order
          target_bo: demo_delivery
    ```

    Phase 1 边界：source_bo / target_bo 必须是**本应用声明的 BO**（同库才能
    同事务派生，F5 铁律）——该约束在启动期 `_prepare_doc_flow` 校验。

    Phase 2 增补（spec 2026-09-29-doc-flow-phase2-spec.md §4.1/§5）：
    - `field_map`：字段映射表 `{"源字段": "目标字段"}`；空 = 同名直拷
    - `split_key`：分单键字段名数组；空 = 每行自成一组（1 源行 = 1 目标单）
    - `target_line_bo`：明细行 BO ID；空 = 单表模式（Phase 1 行为）
    - `head_fk_field`：明细行指向单头的外键字段；空 = 走约定解析
    """

    rule_id: str
    source_bo: str
    target_bo: str
    source_qty_field: str = "quantity"   # Σ 校验读源行数量的字段名
    pool: str = "default"                # 消耗池（§6.5，Phase 1 单池够用）
    check_hook: str = ""                 # Phase 1 留空列位（Phase 2 三段式）
    map_hook: str = ""                   # Phase 1 留空：空 = 默认映射
    create_hook: str = ""                # Phase 1 留空列位
    field_map: Dict[str, str] = field(default_factory=dict)   # 源字段 → 目标字段
    split_key: List[str] = field(default_factory=list)        # 分单键字段名
    target_line_bo: str = ""             # 明细行 BO；空 = 单表模式
    head_fk_field: str = ""              # 明细行→单头 外键字段（显式声明优先）

    def to_store_dict(self) -> Dict[str, Any]:
        """转成 doc_flow_rule_store.upsert_rules 需要的字典。"""
        return {
            "rule_id": self.rule_id,
            "source_bo": self.source_bo,
            "target_bo": self.target_bo,
            "source_qty_field": self.source_qty_field,
            "pool": self.pool,
            "check_hook": self.check_hook,
            "map_hook": self.map_hook,
            "create_hook": self.create_hook,
            "field_map": dict(self.field_map),
            "split_key": list(self.split_key),
            "target_line_bo": self.target_line_bo,
            "head_fk_field": self.head_fk_field,
        }


@dataclass
class RequiresDecl:
    """应用声明的外部依赖（S6 / G5 安装期校验，roadmap §五 S6）。

    未声明 = 旧行为（零影响）。只声明应用**无法自带**的依赖（他应用的 BO /
    规则 / 列版本）；自有 schema 的 BO 无需声明（校验时自动并入）。
    """

    bo: List[str] = field(default_factory=list)
    rules: List[str] = field(default_factory=list)
    column_version: str = ""   # 预留：schema hash 机制未落地，本版仅登记不校验


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
    events_publish: List[EventPublishDecl] = field(default_factory=list)
    events_subscribe: List[EventSubscribeDecl] = field(default_factory=list)
    # [DOC_FLOW Phase 1] 单据流派生资格化声明（spec 2026-09-29 §5.3）
    doc_flow_enabled: bool = False
    doc_flow_rules: List[DocFlowRuleDecl] = field(default_factory=list)
    # [S6 / G5] 外部依赖声明（未声明 = None → 零校验、零影响）
    requires: Optional[RequiresDecl] = None

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


def _parse_events(raw: Dict[str, Any]) -> tuple:
    """解析并校验 `events.publish` / `events.subscribe`（roadmap §6.14.3）。

    命名冲突（同一事件被同一应用既发布又订阅）属于配置错误，直接失败。

    Returns:
        (publish_decls, subscribe_decls)
    """
    node = raw.get("events")
    if node is None:
        return [], []
    if not isinstance(node, dict):
        raise AppManifestError("events 需为对象（含 publish / subscribe）")

    publishes: List[EventPublishDecl] = []
    for index, item in enumerate(_dict_list(node, "publish")):
        ctx = f"events.publish[{index}]"
        decl = EventPublishDecl(
            name=_require_str(item, "name", ctx),
            entity=_require_str(item, "entity", ctx),
            trigger=_require_str(item, "trigger", ctx),
            condition=_optional_str(item, "condition"),
            payload=_str_list(item, "payload"),
        )
        if decl.trigger not in EVENT_TRIGGERS:
            raise AppManifestError(
                f"{ctx}: trigger 必须为 {EVENT_TRIGGERS} 之一, 实际为 '{decl.trigger}'"
            )
        if not decl.payload:
            raise AppManifestError(
                f"{ctx}: payload 需声明至少一个字段（跨应用写只带必要字段, §6.14.3）"
            )
        publishes.append(decl)

    subscribes: List[EventSubscribeDecl] = []
    for index, item in enumerate(_dict_list(node, "subscribe")):
        ctx = f"events.subscribe[{index}]"
        subscribes.append(EventSubscribeDecl(
            name=_require_str(item, "name", ctx),
            source_app=_require_str(item, "from", ctx),
            handler=_require_str(item, "handler", ctx),
            idempotency_key=_require_str(item, "idempotency_key", ctx),
        ))

    duplicated = {p.name for p in publishes} & {s.name for s in subscribes}
    if duplicated:
        raise AppManifestError(
            f"同一应用不能既发布又订阅同一事件: {sorted(duplicated)}"
            "（跨应用事件是应用间机制, §6.14）"
        )
    return publishes, subscribes


def _parse_requires(raw: Dict[str, Any]) -> Optional[RequiresDecl]:
    """解析 `requires` 依赖声明段（S6 / G5）；未声明返回 None。

    Raises:
        AppManifestError: 结构非法
    """
    node = raw.get("requires")
    if node is None:
        return None
    if not isinstance(node, dict):
        raise AppManifestError("requires 需为对象（含 bo / rules / column_version）")
    return RequiresDecl(
        bo=_str_list(node, "bo"),
        rules=_str_list(node, "rules"),
        column_version=_optional_str(node, "column_version"),
    )


def _parse_doc_flow(raw: Dict[str, Any], app_id: str) -> tuple:
    """解析并校验 `doc_flow` 资格化声明（DOC_FLOW Phase 1，spec §5.3）。

    Returns:
        (enabled, rules)

    Raises:
        AppManifestError: 结构非法 / 必填缺失 / rule_id 重复
    """
    node = raw.get("doc_flow")
    if node is None:
        return False, []
    if not isinstance(node, dict):
        raise AppManifestError("doc_flow 需为对象（含 enabled / rules）")

    enabled = node.get("enabled", False)
    if not isinstance(enabled, bool):
        raise AppManifestError(f"app '{app_id}': doc_flow.enabled 需为布尔值")

    rules: List[DocFlowRuleDecl] = []
    seen_rule_ids = set()
    for index, item in enumerate(_dict_list(node, "rules")):
        ctx = f"doc_flow.rules[{index}]"
        decl = DocFlowRuleDecl(
            rule_id=_require_str(item, "rule_id", ctx),
            source_bo=_require_str(item, "source_bo", ctx),
            target_bo=_require_str(item, "target_bo", ctx),
            source_qty_field=_optional_str(item, "source_qty_field") or "quantity",
            pool=_optional_str(item, "pool") or "default",
            check_hook=_optional_str(item, "check_hook"),
            map_hook=_optional_str(item, "map_hook"),
            create_hook=_optional_str(item, "create_hook"),
            field_map=_parse_field_map(item, ctx),
            split_key=_parse_split_key(item, ctx),
            target_line_bo=_optional_str(item, "target_line_bo"),
            head_fk_field=_optional_str(item, "head_fk_field"),
        )
        if decl.rule_id in seen_rule_ids:
            raise AppManifestError(
                f"app '{app_id}': {ctx} rule_id '{decl.rule_id}' 重复"
                "（规则 ID 全局唯一，换版 = 新 ID，spec §9.5）"
            )
        seen_rule_ids.add(decl.rule_id)
        rules.append(decl)

    # enabled: true 但未声明任何规则 → 合法（只资格化建表，暂不注册规则）
    return enabled, rules


def _parse_field_map(item: Dict[str, Any], ctx: str) -> Dict[str, str]:
    """解析 field_map（源字段 → 目标字段）；缺省 = 空 dict（同名直拷）。"""
    value = item.get("field_map")
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AppManifestError(f"{ctx} field_map 需为映射对象（源字段: 目标字段）")
    result: Dict[str, str] = {}
    for src, tgt in value.items():
        if not isinstance(src, str) or not isinstance(tgt, str) or not src or not tgt:
            raise AppManifestError(
                f"{ctx} field_map 的键与值均需为非空字符串（实际: {src!r} → {tgt!r}）"
            )
        result[src] = tgt
    return result


def _parse_split_key(item: Dict[str, Any], ctx: str) -> List[str]:
    """解析 split_key（分单键字段名数组）；缺省 = 空 list（每行自成一组）。"""
    value = item.get("split_key")
    if value is None:
        return []
    if not isinstance(value, list) or not all(
            isinstance(v, str) and v for v in value):
        raise AppManifestError(
            f"{ctx} split_key 需为非空字符串数组（分单键字段名）"
        )
    return list(value)


def _dict_list(raw: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    value = raw.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise AppManifestError(f"'{key}' 需为对象列表")
    return value


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

    events_publish, events_subscribe = _parse_events(raw)
    _check_files_exist(
        app_dir, [s.handler for s in events_subscribe], "events.subscribe.handler"
    )

    doc_flow_enabled, doc_flow_rules = _parse_doc_flow(raw, app_id)

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
        events_publish=events_publish,
        events_subscribe=events_subscribe,
        doc_flow_enabled=doc_flow_enabled,
        doc_flow_rules=doc_flow_rules,
        requires=_parse_requires(raw),
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
