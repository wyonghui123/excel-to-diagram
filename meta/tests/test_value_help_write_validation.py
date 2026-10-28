# -*- coding: utf-8 -*-
"""value_help 写入层校验 — 读写两侧同一判据

覆盖 spec §3 D1（2026-10-28）：
- 校验开关走 `get_validation_flag`（behavior.validation，回落旧版顶层 validation）
- 查询键走 `source.value_field`（不再固定 `id`）
- 条件走 `source.value_filter`，与读侧共用 `parse_value_filter_conditions`

判据只在字段的 value_help 上声明一次；本测试断言的是
「下拉里能选到的 = 保存时能接受的」这一等价关系。
"""

import os
import sys

# conftest 的 raw SQL 门禁会整文件跳过（建表/播种需要 DDL+DML）；
# 按仓库既有惯例在导入期打开 escape hatch。
os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.models import MetaField, MetaObject, FieldType, registry
from meta.core.models_value_help import (
    ValueHelpBehavior,
    ValueHelpConfig,
    ValueHelpSource,
)
from meta.core.sql_adapters import SQLiteAdapter
from meta.core.table_name_validator import register_table_name
from meta.core.value_help_accessor import parse_value_filter_conditions
from meta.services.manage_service import ManageService


TARGET_BO = "t10_vh_uom"
ITEM_BO = "t10_vh_item"

# 候选集：id / code / status 三列，覆盖 active / inactive / frozen / closed / NULL / cancelled
UOM_ROWS = [
    (1, "UOM-1", "active"),
    (2, "UOM-2", "inactive"),
    (3, "UOM-3", "frozen"),
    (4, "UOM-4", "closed"),
    (5, "UOM-5", None),
    (6, "UOM-6", "cancelled"),
]


# ---- Fixtures ----

@pytest.fixture(scope="module")
def ds(tmp_path_factory):
    data_source = SQLiteAdapter()
    db_path = tmp_path_factory.mktemp("test_value_help_validation") / "test.db"
    data_source.connect(path=str(db_path))

    data_source.execute("""
        CREATE TABLE IF NOT EXISTS t10_vh_uom (
            id INTEGER PRIMARY KEY,
            code TEXT,
            status TEXT
        )
    """)
    register_table_name(TARGET_BO)

    target_obj = MetaObject(
        id=TARGET_BO,
        name="值帮助候选集",
        table_name=TARGET_BO,
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id"),
            MetaField(id="code", name="编码", field_type=FieldType.STRING, db_column="code"),
            MetaField(id="status", name="状态", field_type=FieldType.STRING, db_column="status"),
        ],
    )
    registry.register(target_obj)

    yield data_source
    data_source.disconnect()


@pytest.fixture(autouse=True)
def reset_rows(ds):
    ds.execute("DELETE FROM t10_vh_uom")
    for row in UOM_ROWS:
        ds.execute(
            "INSERT INTO t10_vh_uom (id, code, status) VALUES (?, ?, ?)",
            row,
        )


@pytest.fixture(scope="module")
def service(ds):
    return ManageService(ds)


# ---- Helpers ----

def _make_vh(
    value_field="code",
    value_filter=None,
    behavior_validation=True,
    legacy_validation=None,
    validation_message="",
):
    """构造 value_help 声明。

    behavior_validation=None → 不声明 behavior（走旧版顶层 validation 兼容位）
    """
    source = ValueHelpSource(
        type="bo",
        target_bo=TARGET_BO,
        value_field=value_field,
        value_filter=value_filter or {},
    )
    behavior = (
        ValueHelpBehavior(validation=behavior_validation)
        if behavior_validation is not None
        else None
    )
    vh = ValueHelpConfig(
        source=source,
        behavior=behavior,
        validation_message=validation_message,
    )
    if legacy_validation is not None:
        vh.validation = legacy_validation
    return vh


def _make_item_obj(value_help):
    return MetaObject(
        id=ITEM_BO,
        name="值帮助写校验对象",
        table_name=ITEM_BO,
        fields=[
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id"),
            MetaField(
                id="uom_code",
                name="计量单位",
                field_type=FieldType.STRING,
                db_column="uom_code",
                value_help=value_help,
            ),
        ],
    )


def _validate(service, vh, value):
    obj = _make_item_obj(vh)
    return service._validate_value_helps(obj, {"id": 100, "uom_code": value})


# ---- 声明解析（辅助函数单测） ----

class TestParseValueFilterConditions:
    """value_filter 后缀 → 操作符 的唯一解释点"""

    def test_suffix_operators(self):
        conditions = parse_value_filter_conditions({
            "a__in": "x,y",
            "b__notin": "m,n",
            "c__like": "%foo%",
            "d__gte": 10,
            "e__lte": 20,
        })
        assert ("a", "in", ["x", "y"]) in conditions
        assert ("b", "not_in", ["m", "n"]) in conditions
        assert ("c", "like", "%foo%") in conditions
        assert ("d", "ge", 10) in conditions
        assert ("e", "le", 20) in conditions

    def test_plain_key_is_eq_and_none_is_is_null(self):
        conditions = parse_value_filter_conditions({"status": "active", "deleted_at": None})
        assert ("status", "eq", "active") in conditions
        assert ("deleted_at", "is_null", None) in conditions

    def test_list_value_for_in(self):
        conditions = parse_value_filter_conditions({"status__in": ["active", "frozen"]})
        assert conditions == [("status", "in", ["active", "frozen"])]


# ---- 写侧校验：按 value_field + value_filter 查询 ----

class TestValueHelpWriteValidation:

    def test_active_value_accepted(self, service):
        vh = _make_vh(value_filter={"status": "active"})
        assert _validate(service, vh, "UOM-1") == []

    def test_inactive_value_rejected_by_filter(self, service):
        vh = _make_vh(value_filter={"status": "active"})
        errors = _validate(service, vh, "UOM-2")
        assert len(errors) == 1
        assert "UOM-2" in errors[0]

    def test_queries_value_field_not_id(self, service):
        """候选集收窄到 status=active，只剩 id=1/code=UOM-1 一行。

        FK 存的是 code（非 id）：传 id 命中的值 '2' 不应被接受，
        传 code 命中的值 'UOM-1' 才应被接受 —— 证明按 value_field 查。
        """
        vh = _make_vh(value_field="code", value_filter={"status": "active"})
        assert _validate(service, vh, "UOM-1") == []
        assert len(_validate(service, vh, "2")) == 1

    def test_in_filter(self, service):
        vh = _make_vh(value_filter={"status__in": "active,frozen"})
        assert _validate(service, vh, "UOM-1") == []
        assert _validate(service, vh, "UOM-3") == []
        assert len(_validate(service, vh, "UOM-2")) == 1
        assert len(_validate(service, vh, "UOM-4")) == 1

    def test_not_in_filter(self, service):
        vh = _make_vh(value_filter={"status__notin": "closed,cancelled"})
        assert _validate(service, vh, "UOM-1") == []
        assert _validate(service, vh, "UOM-3") == []
        assert len(_validate(service, vh, "UOM-4")) == 1
        assert len(_validate(service, vh, "UOM-6")) == 1

    def test_is_null_filter(self, service):
        vh = _make_vh(value_filter={"status": None})
        assert _validate(service, vh, "UOM-5") == []
        assert len(_validate(service, vh, "UOM-1")) == 1

    def test_validation_message_used(self, service):
        vh = _make_vh(
            value_filter={"status": "active"},
            validation_message="该计量单位已停用，不能选择",
        )
        errors = _validate(service, vh, "UOM-2")
        assert errors == ["该计量单位已停用，不能选择"]

    def test_legacy_top_level_validation_still_works(self, service):
        """未声明 behavior 时，回落旧版顶层 validation=True（兼容位）"""
        vh = _make_vh(
            value_filter={"status": "active"},
            behavior_validation=None,
            legacy_validation=True,
        )
        assert len(_validate(service, vh, "UOM-2")) == 1

    def test_both_switches_off_skips_validation(self, service):
        vh = _make_vh(
            value_filter={"status": "active"},
            behavior_validation=False,
            legacy_validation=False,
        )
        assert _validate(service, vh, "UOM-2") == []

    def test_empty_value_skipped(self, service):
        vh = _make_vh(value_filter={"status": "active"})
        obj = _make_item_obj(vh)
        assert service._validate_value_helps(obj, {"id": 100, "uom_code": ""}) == []
        assert service._validate_value_helps(obj, {"id": 100, "uom_code": None}) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
