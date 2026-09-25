# -*- coding: utf-8 -*-
"""[多产品平台·探针实测 1] per-app MigrationRunner 是否开箱可用

问题: 给"某个应用自己的业务库 + 该应用自己的 migrations 目录" new 一个
      `MigrationRunner`，能否正常工作？四个具体子问题:

1. `schema_migrations` 版本表是否自动建在**应用库**（而不是平台库）？
2. 幂等是否生效（同一迁移跑两次，第二次被跳过）？
3. `migrations_dir` 指向任意目录是否有效（读 apps/<app>/migrations 而非 meta/migrations）？
4. 有无隐藏的全局耦合（硬编码 meta/migrations / 平台库路径 / 全局单例）？

做法（不调用 create_app，纯数据源 + runner）:
  临时 app 库文件 → get_data_source('sqlite', database=...) →
  临时 migrations 目录放 1 个 .sql → MigrationRunner(ds, dir) → run_pending_migrations()。
  同时把 `SQLITE_DB_PATH` 指向另一个临时"平台库"文件，证明探针表**不落**平台库。

运行（铁律入口）:
  python d:\\filework\\test.py --file meta/tests/test_per_app_migration_runner_probe.py
"""
import os
import sqlite3

import pytest

from meta.core.datasource import get_data_source
from meta.core.db_path import get_meta_db_path
from meta.core.migration_runner import MigrationRunner

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS probe_t1 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT
);
"""
MIGRATION_NAME = "001_create_probe_t1.sql"


def _table_names(db_path) -> set:
    if not os.path.isfile(str(db_path)):
        return set()
    conn = sqlite3.connect(str(db_path))
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def _columns(db_path, table) -> set:
    conn = sqlite3.connect(str(db_path))
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _rows(db_path, sql, params=()):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


@pytest.fixture
def probe(tmp_path, monkeypatch):
    """隔离的临时平台库路径 + 应用库 + 应用 migrations 目录。"""
    platform_db = str(tmp_path / "platform_probe.db")
    # 让 get_meta_db_path() 指向一个**不存在的隔离文件** —— 证明探针表不落平台库
    monkeypatch.setenv("SQLITE_DB_PATH", platform_db)

    app_db = str(tmp_path / "app_a.db")
    migrations_dir = tmp_path / "app_migrations"
    migrations_dir.mkdir()
    (migrations_dir / MIGRATION_NAME).write_text(MIGRATION_SQL, encoding="utf-8")

    ds = get_data_source("sqlite", database=app_db)
    yield {
        "tmp": tmp_path,
        "platform_db": platform_db,
        "app_db": app_db,
        "migrations_dir": str(migrations_dir),
        "ds": ds,
    }


class TestPerAppMigrationRunner:

    def test_runner_uses_passed_dir_not_default_meta_dir(self, probe):
        """#3/#4 前置: 构造参数 migrations_dir 生效, 默认值是 meta/migrations。"""
        runner = MigrationRunner(probe["ds"], probe["migrations_dir"])
        assert runner.migrations_dir == probe["migrations_dir"], \
            "Migrations_dir 构造参数未生效"

        default_runner = MigrationRunner(probe["ds"])
        parts = os.path.normpath(default_runner.migrations_dir).split(os.sep)
        assert "meta" in parts and "apps" not in parts, \
            f"默认 migrations_dir 应指向平台的 meta/migrations, 实际 {default_runner.migrations_dir}"

    def test_version_table_and_lock_land_in_app_db(self, probe):
        """#1 核心: schema_migrations / migration_lock 建在**应用库**。"""
        runner = MigrationRunner(probe["ds"], probe["migrations_dir"])
        count = runner.run_pending_migrations()
        assert count == 1, f"应执行 1 个迁移, 实际 {count}"

        app_tables = _table_names(probe["app_db"])
        assert "probe_t1" in app_tables, f"业务表未建在应用库: {sorted(app_tables)}"
        assert "schema_migrations" in app_tables, \
            f"schema_migrations 未建在应用库: {sorted(app_tables)}"
        assert "migration_lock" in app_tables, "migration_lock 未建在应用库"

    def test_nothing_lands_in_platform_db(self, probe):
        """#1 反例: 平台库文件不存在 / 无探针表。"""
        runner = MigrationRunner(probe["ds"], probe["migrations_dir"])
        runner.run_pending_migrations()

        assert os.path.normcase(probe["app_db"]) != os.path.normcase(get_meta_db_path()), \
            "应用库与平台库解析成了同一文件"
        platform_tables = _table_names(get_meta_db_path())
        assert "probe_t1" not in platform_tables, "业务表泄漏进平台库"
        assert "schema_migrations" not in platform_tables, \
            f"schema_migrations 泄漏进平台库: {sorted(platform_tables)}"

    def test_idempotent_second_run_skipped(self, probe):
        """#2 幂等: 第二次跑同一迁移被跳过, 且只记录一行 SUCCESS。"""
        runner = MigrationRunner(probe["ds"], probe["migrations_dir"])
        assert runner.run_pending_migrations() == 1

        assert runner.is_migration_executed(MIGRATION_NAME), "首次执行后未登记为已执行"

        count2 = runner.run_pending_migrations()
        assert count2 == 0, f"第二次应跳过 (0), 实际 {count2}"

        rows = _rows(probe["app_db"],
                     "SELECT migration_name, status FROM schema_migrations")
        assert rows == [(MIGRATION_NAME, "SUCCESS")], \
            f"schema_migrations 记录异常 (应仅 1 行 SUCCESS, 无重复): {rows}"

    def test_state_is_per_db_no_global_coupling(self, probe, tmp_path):
        """#4 无全局耦合: 换一个应用库跑同一 migrations 目录 → 重新执行 (状态在库里, 非全局)。"""
        runner_a = MigrationRunner(probe["ds"], probe["migrations_dir"])
        assert runner_a.run_pending_migrations() == 1

        app_db_b = str(tmp_path / "app_b.db")
        ds_b = get_data_source("sqlite", database=app_db_b)
        runner_b = MigrationRunner(ds_b, probe["migrations_dir"])
        count_b = runner_b.run_pending_migrations()
        assert count_b == 1, \
            "另一个应用库应独立执行该迁移 (若为全局单例状态则会被跳过)"

        assert "schema_migrations" in _table_names(app_db_b), "app_b 版本表未建"
        # app_a 的备份落在 app_a.db 旁边 → 证明 runner 用的是自己的库路径, 非平台库
        baks = list(probe["tmp"].glob("app_a.db.bak.*"))
        assert baks, "未在应用库旁生成备份 → 说明备份未走应用库路径 (潜在串库)"

    def test_sql_migration_content_really_applied(self, probe):
        """内容落地: 应用库里的 probe_t1 列定义与迁移脚本一致。"""
        runner = MigrationRunner(probe["ds"], probe["migrations_dir"])
        runner.run_pending_migrations()
        assert _columns(probe["app_db"], "probe_t1") == {"id", "name"}