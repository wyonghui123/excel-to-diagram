# -*- coding: utf-8 -*-
"""跨归属冲突探针: 注册期 fail fast，且失败前未创建物理表

背景: `meta/core/app_registry.py::_register_app_schemas()` 在补建表
      (`_sync_app_tables`) 之前调用 `_assert_app_registration_safe()`。
      跨归属的 BO id 重复、或 `table_name` 重复，都会在**注册期**抛
      `AppRegistrationError`（fail fast）；由于异常发生在 DDL 之前，
      物理表不会被创建（不会出现静默合列/丢列）。

本文件用**临时应用包 + 真实 register_apps + 真实平台库**做最小复现，两个场景:

  场景 diff_id: 两个 BO id 不同, 但 `table_name` 相同 (= `probe_items_shared`)
                → 注册期拒绝，报 `table_name ... 跨归属重复`
  场景 same_id : 两个 BO **id 完全相同** (= `probe_dup_bo`) 且 table_name 相同
                → 注册期拒绝，报 `BO id 'probe_dup_bo' 跨归属重复`

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
    """不同 BO id / 同名 table_name → 注册期拒绝"""

    def test_registration_rejected(self, collision_env):
        """fail fast: 注册期抛 AppRegistrationError（表名跨归属重复）"""
        error = collision_env["errors"]["diff_id"]
        assert error is not None, "同名 table_name 应在注册期被拒绝"
        assert 'AppRegistrationError' in error, error
        assert SHARED_TABLE in error, error

    def test_table_not_created_before_fail(self, collision_env):
        """失败发生在 DDL 之前: 平台库里不应出现该物理表"""
        assert SHARED_TABLE not in _table_names(collision_env["platform_db"])


class TestSameBoId:
    """相同 BO id → 注册期拒绝"""

    def test_registration_rejected(self, collision_env):
        """fail fast: 注册期抛 AppRegistrationError（BO id 跨归属重复）"""
        error = collision_env["errors"]["same_id"]
        assert error is not None, "重复 BO id 应在注册期被拒绝"
        assert 'AppRegistrationError' in error, error
        assert 'probe_dup_bo' in error, error

    def test_table_not_created_before_fail(self, collision_env):
        """失败发生在 DDL 之前: 平台库里不应出现该物理表"""
        assert DUP_TABLE not in _table_names(collision_env["platform_db"])


class TestRoutingOffNoAppDbs:

    def test_app_dbs_not_created(self, collision_env):
        """APP_DB_ROUTING=0: 未创建任何应用库文件（表都落平台库）。"""
        data_dir = collision_env["data_dir"]
        created = [p.name for p in data_dir.glob("*.db")] if data_dir.is_dir() else []
        assert not created, f"分流关闭时不应创建应用库: {created}"
