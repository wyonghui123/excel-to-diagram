# -*- coding: utf-8 -*-
"""[多产品平台·探针实测 2] APP_DB_ROUTING=0 下, 两应用同名/同表 BO 会不会真撞表

问题: 默认关闭分流时, 两个应用包各自定义一个**同名 BO**（或不同 BO 名但同
      `table_name`），平台建表时会发生什么？三选一:
        A. 报错 / 启动失败
        B. 静默覆盖或共用一张表
        C. 各自建不同名的表（有前缀 / 命名空间）

本文件用**临时应用包 + 真实 register_apps + 真实平台库**做最小复现, 两个场景:

  场景 diff_id: 两个 BO id 不同, 但 `table_name` 相同 (= `probe_items_shared`)
                → 观察是否共用同一物理表 / 是否合并列
  场景 same_id : 两个 BO **id 完全相同** (= `probe_dup_bo`) 且 table_name 相同
                → 观察注册表行为 + 最终表结构

`table_name` 直接来自 schema YAML 的 `table_name:` 字段（见
`meta/core/yaml_loader.py` 的 `table_name=data.get("table_name", "")`），
`meta/core/app_registry.py::_sync_app_tables()` 不派生任何应用前缀。

运行（铁律入口）:
  python d:\\filework\\test.py --file meta/tests/test_app_table_name_collision_probe.py
"""
import os
import sqlite3
import warnings

import pytest

SHARED_TABLE = "probe_items_shared"
DUP_TABLE = "probe_dup_table"


def _app_yaml(app_id, schema_rel):
    return f"""app:
  id: {app_id}
  name: Probe {app_id}
  version: 1.0.0
  description: table-name collision probe
  schemas:
    - {schema_rel}
  blueprints:
    - blueprints/health.py
  permission_namespace: {app_id}
  database:
    file: data/{app_id}.db
"""


def _schema_yaml(bo_id, table_name, extra_field):
    return f"""id: {bo_id}
name: Probe {bo_id}
table_name: {table_name}
description: collision probe bo
semantics:
  meaning: probe
  category: business_entity
  business_key: [code]
fields:
  - id: id
    name: ID
    type: integer
    db_column: id
    required: true
    unique: true
  - id: code
    name: Code
    type: string
    db_column: code
    required: true
    max_length: 50
  - id: {extra_field}
    name: {extra_field}
    type: string
    db_column: {extra_field}
"""


def _blueprint_src(app_id):
    return f'''# -*- coding: utf-8 -*-
from flask import Blueprint

bp = Blueprint("{app_id}_bp", __name__)


@bp.get("/health")
def health():
    return {{"ok": True, "app": "{app_id}"}}
'''


def _write_app(root, app_id, bo_id, table_name, extra_field, schema_filename):
    app_dir = root / app_id
    (app_dir / "schemas").mkdir(parents=True)
    (app_dir / "blueprints").mkdir(parents=True)
    (app_dir / "app.yaml").write_text(
        _app_yaml(app_id, f"schemas/{schema_filename}"), encoding="utf-8")
    (app_dir / "schemas" / schema_filename).write_text(
        _schema_yaml(bo_id, table_name, extra_field), encoding="utf-8")
    (app_dir / "blueprints" / "health.py").write_text(
        _blueprint_src(app_id), encoding="utf-8")


def _table_names(db_path) -> set:
    if not os.path.isfile(str(db_path)):
        return set()
    conn = sqlite3.connect(str(db_path))
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def _table_count(db_path, table) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table,)).fetchone()[0]
    finally:
        conn.close()


def _columns(db_path, table) -> set:
    conn = sqlite3.connect(str(db_path))
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _keep_env(keys):
    return {k: os.environ.get(k) for k in keys}


def _restore_env(previous):
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(scope="module")
def collision_env(tmp_path_factory):
    """APP_DB_ROUTING=0 + 隔离平台库；全文件唯一一次 create_app（legacy 模式）。"""
    keys = ("SQLITE_DB_PATH", "SQLITE_DB_DIR", "APP_DB_ROUTING", "ENABLED_APPS")
    previous = _keep_env(keys)

    db_dir = tmp_path_factory.mktemp("collision_db")
    app_root = tmp_path_factory.mktemp("collision_apps")
    data_dir = tmp_path_factory.mktemp("collision_data")
    platform_db = str(db_dir / "architecture.db")

    os.environ["SQLITE_DB_PATH"] = platform_db
    os.environ["SQLITE_DB_DIR"] = str(data_dir)
    os.environ["APP_DB_ROUTING"] = "0"
    os.environ["ENABLED_APPS"] = ""          # legacy 启动, 平台表先就位

    # 场景 diff_id: 不同 BO id / 同一 table_name
    _write_app(app_root, "probea", "probe_item_a", SHARED_TABLE, "only_a", "item_a.yaml")
    _write_app(app_root, "probeb", "probe_item_b", SHARED_TABLE, "only_b", "item_b.yaml")
    # 场景 same_id: 相同 BO id / 同一 table_name
    _write_app(app_root, "probex", "probe_dup_bo", DUP_TABLE, "only_x", "dup_x.yaml")
    _write_app(app_root, "probey", "probe_dup_bo", DUP_TABLE, "only_y", "dup_y.yaml")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from meta.server import create_app
        app = create_app()
    app.config["TESTING"] = True

    from meta.core.event_outbox import stop_event_dispatcher
    stop_event_dispatcher()

    from meta.core.app_registry import register_apps
    from meta.core.datasource import get_data_source
    from meta.core.models import registry

    data_source = get_data_source("sqlite", database=platform_db)

    errors = {}
    for label, app_ids in (("diff_id", ["probea", "probeb"]),
                           ("same_id", ["probex", "probey"])):
        try:
            register_apps(app, app_ids=app_ids, apps_root=app_root,
                          data_source=data_source)
            errors[label] = None
        except Exception as exc:  # noqa: BLE001 - 探针: 记录任何异常原文
            errors[label] = f"{type(exc).__name__}: {exc}"

    try:
        yield {
            "app": app,
            "platform_db": platform_db,
            "data_dir": data_dir,
            "app_root": app_root,
            "errors": errors,
            "registry": registry,
        }
    finally:
        _restore_env(previous)


class TestDiffBoIdSameTableName:

    def test_no_error_raised(self, collision_env):
        """A 选项排除: register_apps 未报错（无表名冲突检测）。"""
        assert collision_env["errors"]["diff_id"] is None, \
            f"register_apps 抛异常: {collision_env['errors']['diff_id']}"

    def test_single_shared_physical_table(self, collision_env):
        """B 选项: 两个不同 BO 落到**同一张物理表**（只有 1 个对象）。"""
        db = collision_env["platform_db"]
        assert _table_count(db, SHARED_TABLE) == 1, \
            "同名 table_name 应仅建出 1 张表"
        assert SHARED_TABLE in _table_names(db)

    def test_columns_merged_into_one_table(self, collision_env):
        """共用证据: 两个应用各自独有的列被并进同一张表（无隔离）。"""
        cols = _columns(collision_env["platform_db"], SHARED_TABLE)
        assert "only_a" in cols and "only_b" in cols, \
            f"两个 BO 的独有列未合并到同表 (实际列: {sorted(cols)})"

    def test_no_prefixed_namespace_tables(self, collision_env):
        """C 选项排除: 不存在任何带应用前缀的同名表。"""
        tables = _table_names(collision_env["platform_db"])
        prefixed = [t for t in tables
                    if t.endswith(SHARED_TABLE) and t != SHARED_TABLE]
        assert not prefixed, f"出现疑似命名空间表: {prefixed}"


class TestSameBoId:

    def test_no_error_raised(self, collision_env):
        """同名 BO id 也未报错（注册表静默覆盖, 见下）。"""
        assert collision_env["errors"]["same_id"] is None, \
            f"register_apps 抛异常: {collision_env['errors']['same_id']}"

    def test_registry_silently_overwritten(self, collision_env):
        """同名 BO id: registry 只保留后注册的一方（silent overwrite）。"""
        obj = collision_env["registry"].get("probe_dup_bo")
        assert obj is not None, "同名 BO 未注册"
        field_ids = {f.id for f in obj.fields}
        assert "only_y" in field_ids and "only_x" not in field_ids, \
            f"registry 应被后注册的 probey 覆盖, 实际字段: {sorted(field_ids)}"

    def test_single_table_keeps_last_writer_columns(self, collision_env):
        """同名 BO: 最终表只含后一方列（only_x 丢失）→ 静默覆盖, 非报错。"""
        db = collision_env["platform_db"]
        assert _table_count(db, DUP_TABLE) == 1
        cols = _columns(db, DUP_TABLE)
        assert "only_y" in cols, f"表应含后注册方列 only_y: {sorted(cols)}"
        assert "only_x" not in cols, f"先注册方列 only_x 应被覆盖丢失: {sorted(cols)}"


class TestRoutingOffNoAppDbs:

    def test_app_dbs_not_created(self, collision_env):
        """APP_DB_ROUTING=0: 未创建任何应用库文件（表都落平台库）。"""
        data_dir = collision_env["data_dir"]
        created = [p.name for p in data_dir.glob("*.db")] if data_dir.is_dir() else []
        assert not created, f"分流关闭时不应创建应用库: {created}"