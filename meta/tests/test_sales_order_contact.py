# -*- coding: utf-8 -*-
"""销售订单联系人（W1-C）：引用 + 确认时快照并置 / 冻结 / 改客户清空 / 审计排除

依据: docs/superpowers/specs/2026-10-27-sales-order-contact-spec.md
      §3 FR-001~FR-010 / §9.3 详细设计 / §9.5.4 验收清单

【本文件守什么】
  1. 声明层：三字段存在且口径正确（单值 / party 引用 / 候选限 person+active）
  2. 声明层：审计 create / update / delete **三处**均排除两张联系人快照列
  3. 声明层：表单「客户与组织」段含联系人输入位；独立快照段；列表含联系人姓名列
  4. 快照回填：正常 / 无 person_profile / 无手机号 / 未指定 / 非确认态 / 重复确认 / 查库异常
  5. 冻结：离开草稿后快照只读；确认动作可回填不可清空
  6. 改客户即清空：草稿期清空三列；非草稿不清空（冻结优先）
  7. 拦截器接线：清空先于快照（清空后无联系人可快照）

快照用例用真实 SQLite（临时文件 + yaml 真建表），让 LEFT JOIN 语义被真正执行。
"""
import inspect
import logging
import os
import sqlite3
import sys

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core.datasource import get_data_source  # noqa: E402
from meta.core.interceptors.audit_interceptor import AuditInterceptor  # noqa: E402
from meta.core.interceptors.sales_order_guard_interceptor import (  # noqa: E402
    SalesOrderGuardInterceptor,
)
from meta.core.models import registry  # noqa: E402
from meta.core.schema_generator import SchemaGenerator  # noqa: E402
from meta.services.sales_order_guard_service import (  # noqa: E402
    SalesOrderGuardError,
    SalesOrderGuardService,
)
from meta.tests.factories._pricing_p2_helpers import create_tables, seed_row  # noqa: E402

SCHEMA_DIR = os.path.join(ROOT, "meta", "schemas")

pytestmark = pytest.mark.unit

CONTACT_FIELDS = ("contact_party_id", "contact_name_text", "contact_phone_text")
SNAPSHOT_FIELDS = ("contact_name_text", "contact_phone_text")


def _load_raw(bo_id):
    with open(os.path.join(SCHEMA_DIR, bo_id + ".yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _field(schema, field_id):
    for f in schema.get("fields") or []:
        if f.get("id") == field_id:
            return f
    return None


def _reload_quietly():
    logging.disable(logging.CRITICAL)
    try:
        registry.reload(SCHEMA_DIR)
    finally:
        logging.disable(logging.NOTSET)


class _BrokenDS:
    """读侧异常：守卫必须 fail-open。"""

    def query(self, sql, params=None):
        raise RuntimeError('boom')


@pytest.fixture()
def make_service(tmp_path):
    """造 parties / person_profiles 库并返回守卫服务。

    `people` 每项形如 {'id': 1, 'name': '张三', 'mobile': '138...', 'party_type': 'person'}
    `mobile` 为 None 表示不建 person_profiles 档案。
    """
    opened = []

    def _factory(people=()):
        path = tmp_path / ('contact_%d.db' % len(opened))
        conn = sqlite3.connect(str(path))
        create_tables(conn, ['party', 'person_profile'])
        for p in people:
            seed_row(conn, 'parties', id=p['id'], code='P%d' % p['id'],
                     name=p['name'], party_type=p.get('party_type', 'person'),
                     status=p.get('status', 'active'))
            if p.get('mobile') is not None:
                seed_row(conn, 'person_profiles', party_id=p['id'],
                         mobile=p['mobile'], email=p.get('email'))
        conn.commit()
        conn.close()
        ds = get_data_source('sqlite', database=str(path))
        opened.append(ds)
        return SalesOrderGuardService(ds)

    yield _factory
    for ds in opened:
        ds.disconnect()


# ─────────────────────────────────────────────────────────────────────────────
# 声明层
# ─────────────────────────────────────────────────────────────────────────────

class TestDeclaration:

    def test_three_fields_exist_and_nullable(self):
        raw = _load_raw("sales_order")
        for fid in CONTACT_FIELDS:
            field = _field(raw, fid)
            assert field is not None, "缺少字段 {0}".format(fid)
            assert field.get("nullable") is True, fid
            assert field["db_column"] == fid

    def test_contact_party_id_is_single_value_party_reference(self):
        field = _field(_load_raw("sales_order"), "contact_party_id")
        assert field["type"] == "integer"
        assert field["ui"]["relation"] == "party"
        assert field["ui"]["multiple"] is False
        vh = field["value_help"]
        assert vh["source"]["type"] == "bo"
        assert vh["source"]["target_bo"] == "party"
        assert vh["source"]["value_field"] == "id"
        assert vh["source"]["display_field"] == "name"
        assert vh["behavior"]["multiple"] is False
        assert vh["behavior"]["validation"] is True

    def test_candidate_set_filtered_to_active_person(self):
        """候选集 = 全库自然人（status=active 且 party_type=person）。"""
        field = _field(_load_raw("sales_order"), "contact_party_id")
        assert field["value_help"]["source"]["value_filter"] == {
            "status": "active", "party_type": "person"}

    def test_value_filter_keys_are_db_columns(self):
        """value_filter 的 key 走 `_get_db_column` 映射 ⇒ 必须 field id == db_column。"""
        party = _load_raw("party")
        for key in ("status", "party_type"):
            field = _field(party, key)
            assert field is not None, key
            assert field["db_column"] == key, \
                "value_filter key {0} 与 db_column 不一致，过滤将失效".format(key)

    def test_snapshot_columns_length_and_widget(self):
        raw = _load_raw("sales_order")
        name = _field(raw, "contact_name_text")
        phone = _field(raw, "contact_phone_text")
        assert name["type"] == "string"
        assert name["ui"]["widget"] == "input"
        assert phone["type"] == "string"
        assert phone["max_length"] == 32
        assert phone["ui"]["widget"] == "input"

    def test_audit_excludes_snapshot_columns_in_all_three_actions(self):
        """FR-007：create / update / delete 三处均须显式 exclude。"""
        audit = _load_raw("sales_order")["audit"]
        for action in ("create", "update", "delete"):
            exclude = audit[action].get("exclude") or []
            for fid in SNAPSHOT_FIELDS:
                assert fid in exclude, \
                    "audit.{0} 未排除 {1}".format(action, fid)

    def test_form_exposes_contact_input_and_snapshot_section(self):
        ui = _load_raw("sales_order")["ui_view_config"]
        sections = ui["form"]["sections"]
        org_section = next(s for s in sections if s["title"] == "客户与组织")
        org_fields = [f for c in org_section["columns"] for f in c["fields"]]
        assert "contact_party_id" in org_fields
        # 编排无重复、无遗漏：原 salesperson_id / territory_id 仍在
        assert "salesperson_id" in org_fields
        assert "territory_id" in org_fields
        assert len(org_fields) == len(set(org_fields)), "客户与组织段字段重复"
        snap_section = next(
            (s for s in sections if s["title"] == "联系人快照（确认时写入）"), None)
        assert snap_section is not None, "缺联系人快照段"
        snap_fields = [f for c in snap_section["columns"] for f in c["fields"]]
        assert sorted(snap_fields) == sorted(SNAPSHOT_FIELDS)

    def test_list_exposes_contact_name_column(self):
        ui = _load_raw("sales_order")["ui_view_config"]
        columns = [c["field"] for c in ui["list"]["columns"]]
        assert "contact_name_text" in columns

    def test_generated_ddl_has_three_columns(self):
        _reload_quietly()
        sql = SchemaGenerator("sqlite").generate_create_table(
            registry.get("sales_order"))
        for fid in CONTACT_FIELDS:
            assert fid in sql

    def test_audit_fields_to_log_excludes_snapshot_columns(self):
        """用真实审计实现验证三档字段集均不含两张快照列（不只查 YAML 声明）。"""
        _reload_quietly()
        mo = registry.get("sales_order")
        interceptor = AuditInterceptor()
        for action, old, new in (
            ('crud_create', {}, {'contact_name_text': '张三',
                                 'contact_phone_text': '13800000000'}),
            ('crud_update', {'contact_name_text': '张三',
                             'contact_phone_text': '13800000000'},
             {'contact_name_text': '李四',
              'contact_phone_text': '13900000000'}),
            ('crud_delete', {}, {}),
        ):
            cfg = mo.audit.get_action_config(action)
            fields = interceptor._get_fields_to_log(mo, old, new, cfg)
            for fid in SNAPSHOT_FIELDS:
                assert fid not in fields, \
                    "审计 {0} 档字段集仍含 {1}".format(action, fid)


# ─────────────────────────────────────────────────────────────────────────────
# 快照回填（R-CNT-3）
# ─────────────────────────────────────────────────────────────────────────────

class TestContactSnapshot:

    def _confirm(self, svc, contact_party_id, old=None):
        return svc.snapshot_contact_text(
            {"status": "confirmed", "contact_party_id": contact_party_id},
            old or {"status": "submitted"})

    def test_writes_name_and_mobile(self, make_service):
        svc = make_service([{'id': 7, 'name': '张三', 'mobile': '13800000000'}])
        assert self._confirm(svc, 7) == {
            "contact_name_text": "张三", "contact_phone_text": "13800000000"}

    def test_no_person_profile_writes_name_only(self, make_service):
        svc = make_service([{'id': 7, 'name': '张三', 'mobile': None}])
        assert self._confirm(svc, 7) == {"contact_name_text": "张三"}

    def test_blank_mobile_writes_name_only(self, make_service):
        svc = make_service([{'id': 7, 'name': '张三', 'mobile': ''}])
        assert self._confirm(svc, 7) == {"contact_name_text": "张三"}

    def test_no_contact_returns_empty(self, make_service):
        svc = make_service([{'id': 7, 'name': '张三', 'mobile': '13800000000'}])
        assert self._confirm(svc, None) == {}
        assert self._confirm(svc, 999) == {}

    def test_not_confirmed_returns_empty(self, make_service):
        svc = make_service([{'id': 7, 'name': '张三', 'mobile': '13800000000'}])
        assert svc.snapshot_contact_text(
            {"status": "draft", "contact_party_id": 7},
            {"status": "submitted"}) == {}

    def test_repeat_confirm_does_not_overwrite(self, make_service):
        svc = make_service([{'id': 7, 'name': '张三', 'mobile': '13800000000'}])
        assert svc.snapshot_contact_text(
            {"status": "confirmed", "contact_party_id": 7},
            {"status": "confirmed"}) == {}

    def test_read_failure_fails_open(self):
        svc = SalesOrderGuardService(_BrokenDS())
        assert svc.snapshot_contact_text(
            {"status": "confirmed", "contact_party_id": 7},
            {"status": "submitted"}) == {}

    def test_source_is_person_profile_mobile(self):
        """电话来源唯一为 person_profiles.mobile（parties 无联系方式列）。"""
        src = inspect.getsource(SalesOrderGuardService._load_contact)
        assert "person_profiles" in src
        assert "pp.mobile" in src
        assert "pp.email" not in src


# ─────────────────────────────────────────────────────────────────────────────
# 快照冻结（R-CNT-1 / R-CNT-2）
# ─────────────────────────────────────────────────────────────────────────────

class TestContactSnapshotLocked:

    def _validate(self, data, old):
        SalesOrderGuardService(_BrokenDS()).validate_order_write(
            data, old_data=old, is_create=False)

    def test_submitted_rejects_snapshot_change(self):
        with pytest.raises(SalesOrderGuardError) as exc:
            self._validate({"contact_name_text": "李四"},
                           {"status": "submitted",
                            "contact_name_text": "张三"})
        assert exc.value.rule == 'contact_snapshot_locked'
        assert exc.value.field_name == 'contact_name_text'

    def test_confirmed_rejects_snapshot_change(self):
        with pytest.raises(SalesOrderGuardError) as exc:
            self._validate({"contact_phone_text": "13900000000"},
                           {"status": "confirmed",
                            "contact_phone_text": "13800000000"})
        assert exc.value.rule == 'contact_snapshot_locked'

    def test_draft_allows_snapshot_change(self):
        self._validate({"contact_name_text": "李四"},
                       {"status": "draft", "contact_name_text": "张三"})

    def test_confirming_with_non_blank_snapshot_allowed(self):
        self._validate({"status": "confirmed", "contact_name_text": "张三"},
                       {"status": "submitted", "contact_name_text": None})

    def test_confirming_clearing_snapshot_rejected(self):
        with pytest.raises(SalesOrderGuardError) as exc:
            self._validate({"status": "confirmed", "contact_name_text": None},
                           {"status": "submitted",
                            "contact_name_text": "张三"})
        assert exc.value.rule == 'contact_snapshot_locked'

    def test_same_value_allowed(self):
        self._validate({"contact_name_text": "张三"},
                       {"status": "confirmed", "contact_name_text": "张三"})


# ─────────────────────────────────────────────────────────────────────────────
# 改客户即清空（R-CNT-4）
# ─────────────────────────────────────────────────────────────────────────────

class TestContactClearOnCustomerChange:

    def _clear(self, data, old):
        return SalesOrderGuardService(_BrokenDS()).contact_clear_on_customer_change(
            data, old_data=old)

    def test_draft_customer_change_clears_three_columns(self):
        cleared = self._clear(
            {"customer_account_id": 2, "contact_party_id": 7,
             "contact_name_text": "张三", "contact_phone_text": "13800000000"},
            {"status": "draft", "customer_account_id": 1,
             "contact_party_id": 7, "contact_name_text": "张三",
             "contact_phone_text": "13800000000"})
        assert cleared == {
            "contact_party_id": None,
            "contact_name_text": None,
            "contact_phone_text": None}

    def test_draft_customer_unchanged_keeps_columns(self):
        assert self._clear(
            {"customer_account_id": 1, "contact_party_id": 7},
            {"status": "draft", "customer_account_id": 1,
             "contact_party_id": 7}) == {}

    def test_non_draft_customer_change_does_not_clear(self):
        """冻结优先：已离开草稿的订单不清空（NFR-004）。"""
        assert self._clear(
            {"customer_account_id": 2, "contact_party_id": 7},
            {"status": "submitted", "customer_account_id": 1,
             "contact_party_id": 7}) == {}

    def test_create_does_not_clear(self):
        assert self._clear(
            {"customer_account_id": 2, "contact_party_id": 7}, None) == {}

    def test_missing_customer_field_keeps_columns(self):
        assert self._clear(
            {"contact_party_id": 7},
            {"status": "draft", "customer_account_id": 1,
             "contact_party_id": 7}) == {}


# ─────────────────────────────────────────────────────────────────────────────
# 候选集实测（value_help → BOEngine → QueryBuilder → SQLite）
# ─────────────────────────────────────────────────────────────────────────────

class TestCandidateSet:
    """FR-001 核心验收：下拉候选集只含「启用中的自然人」。

    走真实 provider 链路（value_help_providers → BOEngine → QueryBuilder → SQLite），
    不只断言 YAML 声明 —— `party_type` 过滤能否真正生效由此证明。
    """

    def _candidates(self, tmp_path, monkeypatch):
        path = tmp_path / 'candidate_set.db'
        conn = sqlite3.connect(str(path))
        create_tables(conn, ['party', 'person_profile'])
        seed_row(conn, 'parties', id=1, code='P1', name='张三',
                 party_type='person', status='active')
        seed_row(conn, 'parties', id=2, code='P2', name='某公司',
                 party_type='organization', status='active')
        seed_row(conn, 'parties', id=3, code='P3', name='停用的人',
                 party_type='person', status='inactive')
        conn.commit()
        conn.close()

        ds = get_data_source('sqlite', database=str(path))
        import meta.services.query_service as query_service
        monkeypatch.setattr(query_service, '_data_source_instance', ds)

        _reload_quietly()
        from dataclasses import replace
        from meta.core.value_help_providers import BoValueHelpProvider
        mo = registry.get('sales_order')
        field = next(f for f in mo.fields if f.id == 'contact_party_id')
        # 权限层需要 Flask app context（见 test_division_master 同款做法），
        # 本用例只验 value_filter 生效，故关掉权限层；过滤链路仍真实执行。
        provider = BoValueHelpProvider(
            replace(field.value_help.source, apply_target_permissions=False))
        result = provider.search('', [], {}, 1, 50, [], None)
        return [row['display'] for row in result['data']]

    def test_only_active_persons_in_candidate_set(self, tmp_path, monkeypatch):
        displays = self._candidates(tmp_path, monkeypatch)
        assert '张三' in displays
        assert '某公司' not in displays, "企业主体不得出现在联系人候选集"
        assert '停用的人' not in displays, "停用主体不得出现在联系人候选集"


# ─────────────────────────────────────────────────────────────────────────────
# 拦截器接线
# ─────────────────────────────────────────────────────────────────────────────

class TestInterceptorWiring:

    def _source(self):
        return inspect.getsource(SalesOrderGuardInterceptor.before_action)

    def test_snapshot_and_clear_are_wired(self):
        src = self._source()
        assert 'snapshot_contact_text' in src
        assert 'contact_clear_on_customer_change' in src

    def test_clear_runs_before_snapshot(self):
        """清空必须先于快照：清空后无联系人可快照。"""
        src = self._source()
        assert src.index('contact_clear_on_customer_change') \
            < src.index('snapshot_contact_text')

    def test_clear_and_snapshot_write_back_to_params(self):
        """更新场景 merged 是新 dict ⇒ 必须回写 context.params 才能落库。"""
        src = self._source()
        assert src.count('context.params.update(') >= 3
