# -*- coding: utf-8 -*-
"""value_help 写入层校验 — 批量写入口拦截（C3 / P2-2 验收，2026-10-28）

覆盖范围
--------
1. `ManageService.batch_create` / `batch_update` 在落库前逐行校验 value_help：
   - all_or_none=True：任一行非法 ⇒ 整批拒绝，`errors` 带 `第 N 行` 定位，
     且 **executor 一次都不被调用**（不落库）。
   - all_or_none=False：非法行被跳过并计入 failed，合法行照常写入。
2. P2-2 验收：`sales_order.salesperson_id` 的判据来自 YAML（SSOT），
   停用的销售员应被拒。

为什么用假数据源
----------------
本文件只验证「判据接线」，不验证真实 SQL 方言；用内存假数据源可以
1) 不碰 architecture.db；2) 不触发 conftest 的 raw-SQL 整文件 skip。
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_ROOT)

from meta.core.action_executor import ActionResult
from meta.core.models import FieldType, MetaField, MetaObject, registry
from meta.core.models_value_help import (
    ValueHelpBehavior,
    ValueHelpConfig,
    ValueHelpSource,
)
from meta.core.value_help_accessor import validate_value_helps
from meta.core.yaml_loader import load_yaml_file
from meta.services.manage_service import ManageService

_SCHEMA_DIR = os.path.join(PROJECT_ROOT, 'meta', 'schemas')

TARGET_BO = 't10_wh_guard_uom'
GUARD_BO = 't10_wh_guard_item'


# ---------------------------------------------------------------- fake infra

class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _NullTransaction:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeDataSource:
    """固定 count 的假数据源。

    - count 给定时：任何查询都返回该 count；
    - valid_values 给定时：按查询参数首个值判断是否命中（用于构造 mixed 行）。
    """

    def __init__(self, count=0, valid_values=None):
        self.count = count
        self.valid_values = valid_values
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, list(params or [])))
        if self.valid_values is not None:
            first = (params or [None])[0]
            return _FakeCursor((1 if first in self.valid_values else 0,))
        return _FakeCursor((self.count,))

    def transaction(self):
        return _NullTransaction()


class _RecordingExecutor:
    """记录 execute 调用，默认成功。"""

    def __init__(self):
        self.calls = []

    def execute(self, meta_obj, action, data, skip_rules=False):
        self.calls.append((meta_obj.id, action, dict(data), skip_rules))
        return ActionResult(success=True)


def _make_service(ds, executor):
    """绕过 RuleEngine/ActionExecutor 构造（会触碰审计库），只注入被测依赖。"""
    service = ManageService.__new__(ManageService)
    service.data_source = ds
    service.executor = executor
    service.notification_service = None
    return service


# ---------------------------------------------------------------- fixtures

def _make_target_obj():
    return MetaObject(
        id=TARGET_BO,
        name='候选集',
        table_name=TARGET_BO,
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER, db_column='id'),
            MetaField(id='code', name='编码', field_type=FieldType.STRING, db_column='code'),
            MetaField(id='status', name='状态', field_type=FieldType.STRING, db_column='status'),
        ],
    )


def _make_guard_obj():
    vh = ValueHelpConfig(
        source=ValueHelpSource(
            type='bo',
            target_bo=TARGET_BO,
            value_field='code',
            value_filter={'status': 'active'},
        ),
        behavior=ValueHelpBehavior(validation=True),
    )
    return MetaObject(
        id=GUARD_BO,
        name='批量写校验对象',
        table_name=GUARD_BO,
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER, db_column='id'),
            MetaField(
                id='uom_code',
                name='计量单位',
                field_type=FieldType.STRING,
                db_column='uom_code',
                value_help=vh,
            ),
        ],
    )


@pytest.fixture(scope='module', autouse=True)
def register_test_objects():
    registry.register(_make_target_obj())
    registry.register(_make_guard_obj())
    yield


@pytest.fixture
def salesperson_registered():
    """P2-2 用例需要 target_bo=salesperson 可解析；用最小对象并复原注册表。"""
    previous = registry.get('salesperson')
    registry.register(MetaObject(
        id='salesperson',
        name='销售员',
        table_name='salesperson',
        fields=[
            MetaField(id='id', name='ID', field_type=FieldType.INTEGER, db_column='id'),
            MetaField(id='status', name='状态', field_type=FieldType.STRING, db_column='status'),
            MetaField(id='name', name='姓名', field_type=FieldType.STRING, db_column='name'),
        ],
    ))
    yield
    if previous is not None:
        registry.register(previous)
    else:
        registry.unregister('salesperson')


# ---------------------------------------------------------------- batch_create

class TestBatchCreateValueHelpGuard:

    def test_all_or_none_rejects_whole_batch_and_writes_nothing(self):
        ds = _FakeDataSource(count=0)
        executor = _RecordingExecutor()
        service = _make_service(ds, executor)

        result = service.batch_create(
            GUARD_BO,
            [{'id': 1, 'uom_code': 'BAD-1'}, {'id': 2, 'uom_code': 'BAD-2'}],
            all_or_none=True,
        )

        assert result.success_count == 0
        assert result.failed_count == 2
        assert executor.calls == [], '整批拒绝时不得调用 executor（不落库）'
        assert result.errors[0].startswith('第 1 行:')
        assert result.errors[1].startswith('第 2 行:')

    def test_all_or_none_passes_when_values_exist(self):
        ds = _FakeDataSource(count=1)
        executor = _RecordingExecutor()
        service = _make_service(ds, executor)

        result = service.batch_create(
            GUARD_BO,
            [{'id': 1, 'uom_code': 'GOOD-1'}, {'id': 2, 'uom_code': 'GOOD-2'}],
            all_or_none=True,
        )

        assert result.failed_count == 0
        assert result.success_count == 2
        assert [c[1] for c in executor.calls] == ['crud_create', 'crud_create']

    def test_non_all_or_none_skips_invalid_rows(self):
        ds = _FakeDataSource(valid_values={'GOOD-2'})
        executor = _RecordingExecutor()
        service = _make_service(ds, executor)

        result = service.batch_create(
            GUARD_BO,
            [{'id': 1, 'uom_code': 'BAD-1'}, {'id': 2, 'uom_code': 'GOOD-2'}],
            all_or_none=False,
        )

        assert result.success_count == 1
        assert result.failed_count == 1
        assert result.errors[0].startswith('第 1 行:')
        assert len(executor.calls) == 1
        assert executor.calls[0][2]['uom_code'] == 'GOOD-2'


# ---------------------------------------------------------------- batch_update

class TestBatchUpdateValueHelpGuard:

    def test_all_or_none_rejects_and_writes_nothing(self):
        ds = _FakeDataSource(count=0)
        executor = _RecordingExecutor()
        service = _make_service(ds, executor)

        result = service.batch_update(
            GUARD_BO,
            [{'id': 1, 'uom_code': 'BAD-1'}],
            all_or_none=True,
        )

        assert result.success_count == 0
        assert result.failed_count == 1
        assert executor.calls == [], '整批拒绝时不得调用 executor（不落库）'
        assert result.errors[0].startswith('第 1 行:')

    def test_non_all_or_none_skips_invalid_rows(self):
        ds = _FakeDataSource(valid_values={'GOOD-2'})
        executor = _RecordingExecutor()
        service = _make_service(ds, executor)

        result = service.batch_update(
            GUARD_BO,
            [{'id': 1, 'uom_code': 'BAD-1'}, {'id': 2, 'uom_code': 'GOOD-2'}],
            all_or_none=False,
        )

        assert result.success_count == 1
        assert result.failed_count == 1
        assert result.errors[0].startswith('第 1 行:')
        assert [c[1] for c in executor.calls] == ['crud_update']
        assert executor.calls[0][2]['id'] == 2


# ---------------------------------------------------------------- P2-2 验收

class TestSalesOrderSalespersonValueHelp:
    """salesperson_id 的判据只声明在 YAML；这里断言声明本身 + 执行效果。"""

    @staticmethod
    def _load_sales_order():
        return load_yaml_file(os.path.join(_SCHEMA_DIR, 'sales_order.yaml'))

    @staticmethod
    def _salesperson_field(meta_obj):
        return next(f for f in meta_obj.fields if f.id == 'salesperson_id')

    def test_yaml_declares_active_only_strict_judge(self):
        field = self._salesperson_field(self._load_sales_order())
        vh = field.value_help
        assert vh is not None
        assert vh.source.target_bo == 'salesperson'
        assert vh.source.value_field == 'id'
        assert vh.source.value_filter == {'status': 'active'}
        assert vh.behavior is not None and vh.behavior.validation is True
        assert vh.behavior.binding_strength == 'strict'

    def test_inactive_salesperson_rejected_by_yaml_judge(self, salesperson_registered):
        ds = _FakeDataSource(count=0)

        errors = validate_value_helps(
            ds, self._load_sales_order(), {'salesperson_id': 999}
        )

        assert len(errors) == 1
        assert '999' in errors[0]

    def test_active_salesperson_accepted(self, salesperson_registered):
        ds = _FakeDataSource(count=1)

        errors = validate_value_helps(
            ds, self._load_sales_order(), {'salesperson_id': 999}
        )

        assert errors == []


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
