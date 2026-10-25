# -*- coding: utf-8 -*-
"""税务波次 0 —— schema 接线 / 守卫 G1–G6 与 C1–C2 / 拦截器 / 菜单权限 / 种子幂等

依据: docs/superpowers/specs/2026-10-25-tax-wave0-implementation-spec.md §10（A1–A11）
"""

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

pytestmark = pytest.mark.unit

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.tax_guard_interceptor import TaxGuardInterceptor
from meta.services.tax_guard_service import TaxGuardError, TaxGuardService

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / 'schemas'
_DB_PATH = Path(__file__).resolve().parents[1] / 'architecture.db'


# ─────────────────────────────────────────────────────────────────────────────
# 假数据源（只实现守卫用到的三种 SQL 形态）
# ─────────────────────────────────────────────────────────────────────────────

class _FakeDS:
    def __init__(self, tax_codes=None, rates=None, registrations=None,
                 raise_on_query=False):
        self.tax_codes = tax_codes or []
        self.rates = rates or []
        self.registrations = registrations or []
        self.raise_on_query = raise_on_query

    def query(self, sql, params):
        if self.raise_on_query:
            raise RuntimeError('db down')
        if 'FROM tax_codes' in sql:
            target = str(params[0])
            return [r for r in self.tax_codes if str(r['id']) == target]
        if 'FROM tax_rates' in sql:
            tax_code_id = str(params[0])
            exclude = str(params[1]) if len(params) > 1 else None
            rows = [r for r in self.rates
                    if str(r['tax_code_id']) == tax_code_id
                    and (exclude is None or str(r['id']) != exclude)]
            return rows
        if 'FROM party_tax_registrations' in sql:
            party_id, country_id, tax_type = (str(params[0]), str(params[1]),
                                              str(params[2]))
            exclude = str(params[3]) if len(params) > 3 else None
            matched = [
                r for r in self.registrations
                if str(r['party_id']) == party_id
                and str(r['country_id']) == country_id
                and str(r['tax_type']) == tax_type
                and r.get('is_primary') in (1, True, '1')
                and (exclude is None or str(r['id']) != exclude)
            ]
            return [{'cnt': len(matched)}]
        raise AssertionError(f'未预期的 SQL: {sql}')


def _svc(**kwargs):
    return TaxGuardService(_FakeDS(**kwargs))


# ─────────────────────────────────────────────────────────────────────────────
# A1 / A2 / A3 —— schema 接线
# ─────────────────────────────────────────────────────────────────────────────

def _load(name):
    with open(_SCHEMA_DIR / f'{name}.yaml', encoding='utf-8') as f:
        return yaml.safe_load(f)


class TestSchemaWiring:
    def test_a1_tables(self):
        expected = {
            'tax_classification': 'tax_classifications',
            'tax_code': 'tax_codes',
            'tax_rate': 'tax_rates',
            'party_tax_registration': 'party_tax_registrations',
        }
        for obj, table in expected.items():
            assert _load(obj)['table_name'] == table

    def test_a2_carrier_field(self):
        expected = {'items': 'item', 'customer_account': 'customer',
                    'vendor_account': 'supplier'}
        for obj, constant in expected.items():
            data = _load(obj)
            field = next(f for f in data['fields']
                         if f['id'] == 'tax_classification_id')
            binding = field['value_help']['behavior']['parameter_bindings'][0]
            assert binding['target_field'] == 'applicable_to'
            assert binding['constant'] == constant

    def test_a3_child_sections(self):
        code = _load('tax_code')
        children = [c['child_object']
                    for c in code['ui_view_config']['child_sections']]
        assert children == ['tax_rate']

        archive = _load('party_archive')
        children = [c['child_object']
                    for c in archive['ui_view_config']['child_sections']]
        assert children == ['party_tax_registration']

        reg = _load('party_tax_registration')
        party_field = next(f for f in reg['fields'] if f['id'] == 'party_id')
        assert party_field['ui']['relation'] == 'party_archive'
        assert reg['parent_object'] == 'party'


# ─────────────────────────────────────────────────────────────────────────────
# A4 – A8 —— 守卫
# ─────────────────────────────────────────────────────────────────────────────

class TestTaxRateGuard:
    _CODE = {'id': 1, 'code': 'CN_VAT_13', 'status': 'active'}

    def test_a4_window_inverted(self):
        svc = _svc(tax_codes=[self._CODE])
        with pytest.raises(TaxGuardError) as e:
            svc.validate_tax_rate_write({
                'tax_code_id': 1, 'effective_from': '2024-06-01',
                'effective_to': '2024-06-01', 'rate_percent': 13})
        assert e.value.rule == 'window_inverted'

    def test_a5_overlap(self):
        svc = _svc(
            tax_codes=[self._CODE],
            rates=[{'id': 10, 'tax_code_id': 1,
                    'effective_from': '2024-01-01',
                    'effective_to': '2025-01-01'}])
        with pytest.raises(TaxGuardError) as e:
            svc.validate_tax_rate_write({
                'tax_code_id': 1, 'effective_from': '2024-06-01',
                'effective_to': None, 'rate_percent': 9})
        assert e.value.rule == 'window_overlap'

    def test_a6_adjacent_allowed(self):
        svc = _svc(
            tax_codes=[self._CODE],
            rates=[{'id': 10, 'tax_code_id': 1,
                    'effective_from': '2024-01-01',
                    'effective_to': '2025-01-01'}])
        svc.validate_tax_rate_write({
            'tax_code_id': 1, 'effective_from': '2025-01-01',
            'effective_to': None, 'rate_percent': 9})

    def test_g3_rate_out_of_range(self):
        svc = _svc(tax_codes=[self._CODE])
        with pytest.raises(TaxGuardError) as e:
            svc.validate_tax_rate_write({
                'tax_code_id': 1, 'effective_from': '2024-01-01',
                'rate_percent': 100})
        assert e.value.rule == 'rate_out_of_range'

    def test_g4_tax_code_missing(self):
        svc = _svc()
        with pytest.raises(TaxGuardError) as e:
            svc.validate_tax_rate_write({
                'tax_code_id': 999, 'effective_from': '2024-01-01',
                'rate_percent': 13})
        assert e.value.rule == 'tax_code_missing'

    def test_query_failure_fails_open(self):
        _svc(raise_on_query=True).validate_tax_rate_write({
            'tax_code_id': 1, 'effective_from': '2024-01-01',
            'rate_percent': 13})


class TestPartyTaxRegistrationGuard:
    _REG = {'id': 5, 'party_id': 100, 'country_id': 200,
            'tax_type': 'vat', 'is_primary': 1}

    def test_a7_primary_duplicated(self):
        svc = _svc(registrations=[self._REG])
        with pytest.raises(TaxGuardError) as e:
            svc.validate_party_tax_registration_write({
                'party_id': 100, 'country_id': 200, 'tax_type': 'vat',
                'registration_number': '91310000XXX', 'is_primary': True})
        assert e.value.rule == 'primary_duplicated'

    def test_a7_self_update_allowed(self):
        svc = _svc(registrations=[self._REG])
        svc.validate_party_tax_registration_write(
            {'id': 5, 'party_id': 100, 'country_id': 200, 'tax_type': 'vat',
             'registration_number': '91310000XXX', 'is_primary': True},
            exclude_id=5)

    def test_g6_validity_inverted(self):
        svc = _svc()
        with pytest.raises(TaxGuardError) as e:
            svc.validate_party_tax_registration_write({
                'party_id': 100, 'country_id': 200, 'tax_type': 'vat',
                'valid_from': '2024-06-01', 'valid_to': '2024-01-01'})
        assert e.value.rule == 'validity_inverted'


class TestTaxCodeGuard:
    def test_a8_exempt_requires_reason(self):
        with pytest.raises(TaxGuardError) as e:
            _svc().validate_tax_code_write(
                {'code': 'X', 'tax_treatment': 'exempt'})
        assert e.value.rule == 'exemption_reason_required'

    def test_exempt_with_reason_passes(self):
        _svc().validate_tax_code_write(
            {'code': 'X', 'tax_treatment': 'exempt',
             'exemption_reason': '法定免税项目'})

    def test_c2_external_requires_system(self):
        with pytest.raises(TaxGuardError) as e:
            _svc().validate_tax_code_write(
                {'code': 'X', 'tax_treatment': 'standard',
                 'rate_source': 'external'})
        assert e.value.rule == 'external_system_required'


# ─────────────────────────────────────────────────────────────────────────────
# 拦截器接线（R5：两条启动路径都注册）
# ─────────────────────────────────────────────────────────────────────────────

def _ctx(object_id, action, params, old_data=None, ds=None):
    return SimpleNamespace(
        meta_object=SimpleNamespace(id=object_id),
        action=action,
        params=params,
        old_data=old_data or {},
        object_id=params.get('id'),
        data_source=ds or _FakeDS(),
    )


class TestInterceptor:
    def test_priority(self):
        assert TaxGuardInterceptor().priority == 46

    def test_guards_three_objects_write_only(self):
        ic = TaxGuardInterceptor()
        for obj in ('tax_code', 'tax_rate', 'party_tax_registration'):
            assert ic.should_execute(_ctx(obj, 'crud_create', {}))
            assert ic.should_execute(_ctx(obj, 'crud_update', {}))
            assert not ic.should_execute(_ctx(obj, 'crud_delete', {}))
        assert not ic.should_execute(_ctx('items', 'crud_create', {}))

    def test_dispatch_raises_validation_failed(self):
        ic = TaxGuardInterceptor()
        ctx = _ctx('tax_code', 'crud_create',
                   {'code': 'X', 'tax_treatment': 'out_of_scope'})
        with pytest.raises(ValidationFailedError):
            ic.before_action(ctx)

    def test_update_merges_old_data(self):
        ic = TaxGuardInterceptor()
        ds = _FakeDS(tax_codes=[{'id': 1, 'code': 'CN_VAT_13'}],
                     rates=[{'id': 10, 'tax_code_id': 1,
                             'effective_from': '2024-01-01',
                             'effective_to': '2025-01-01'},
                            {'id': 11, 'tax_code_id': 1,
                             'effective_from': '2024-01-01',
                             'effective_to': '2025-01-01'}])
        # 只改税率：旧行的 tax_code_id / 区间被合并回来 ⇒ 命中重叠
        ctx = _ctx('tax_rate', 'crud_update',
                   {'id': 10, 'rate_percent': 9},
                   old_data={'id': 10, 'tax_code_id': 1,
                             'effective_from': '2024-01-01',
                             'effective_to': '2025-01-01'},
                   ds=ds)
        with pytest.raises(ValidationFailedError):
            ic.before_action(ctx)

    def test_registered_in_both_boot_paths(self):
        root = Path(__file__).resolve().parents[1]
        for rel in ('core/app_builder.py', 'server.py'):
            text = (root / rel).read_text(encoding='utf-8')
            assert 'TaxGuardInterceptor' in text, f'{rel} 未注册税务守卫'


# ─────────────────────────────────────────────────────────────────────────────
# A9 —— 税码删除保护（restrict_on 配置）
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteProtection:
    def test_a9_tax_code_restrict_on_rates(self):
        policy = _load('tax_code')['deletion_policy']
        assert policy['mode'] == 'restrict'
        targets = {(r['table'], r['foreign_key']) for r in policy['restrict_on']}
        assert ('tax_rates', 'tax_code_id') in targets

    def test_classification_restrict_on_three_carriers(self):
        policy = _load('tax_classification')['deletion_policy']
        targets = {(r['table'], r['foreign_key']) for r in policy['restrict_on']}
        assert targets == {
            ('items', 'tax_classification_id'),
            ('customer_accounts', 'tax_classification_id'),
            ('vendor_accounts', 'tax_classification_id'),
        }


# ─────────────────────────────────────────────────────────────────────────────
# A10 / A11 —— 菜单权限（只读） / 种子幂等（写同值）
# ─────────────────────────────────────────────────────────────────────────────

def _db():
    if not _DB_PATH.exists():
        pytest.skip('architecture.db 不存在')
    conn = sqlite3.connect(str(_DB_PATH))
    return conn


class TestMenuPermissions:
    def test_a10_menus(self):
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT menu_code, page_type, primary_object_type, parent_menu, "
                "show_in_sidebar FROM menus WHERE menu_code IN "
                "('tax-management','tax-classification-management')").fetchall()
            assert len(rows) == 2
            by_code = {r[0]: r for r in rows}
            assert by_code['tax-management'][1] == 'object_list'
            assert by_code['tax-management'][2] == 'tax_code'
            assert by_code['tax-classification-management'][2] == 'tax_classification'
            for row in rows:
                assert row[3] == 'master-data'
                assert row[4] == 0

            orphan = conn.execute(
                "SELECT menu_code FROM menus WHERE menu_code IN "
                "('tax-code-list','tax-classification-list','tax-rate-list',"
                "'party-tax-registration-list')").fetchall()
            assert orphan == []
        finally:
            conn.close()

    def test_a10_permissions_double_segment(self):
        conn = _db()
        try:
            codes = []
            for obj in ('tax_classification', 'tax_code', 'tax_rate',
                        'party_tax_registration'):
                codes += [f'{obj}:{obj}_{a}' for a in
                          ('create', 'read', 'update', 'delete', 'list')]
            found = conn.execute(
                'SELECT code FROM permissions WHERE code IN (%s)'
                % ', '.join('?' * len(codes)), codes).fetchall()
            assert len(found) == 20
            for (code,) in found:
                head, tail = code.split(':')
                assert tail.startswith(head + '_')
        finally:
            conn.close()


class TestSeedIdempotency:
    def test_a11_two_runs_stable(self):
        conn = _db()
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if not {'tax_codes', 'tax_rates', 'tax_classifications'} <= tables:
                pytest.skip('税务表尚未建')
            before = {
                t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                for t in ('tax_classifications', 'tax_codes', 'tax_rates')
            }
        finally:
            conn.close()

        from meta.core.datasource import get_data_source
        from meta.core.db_path import get_meta_db_path
        from meta.scripts.init_tax_seed import init_tax_seed_data

        ds = get_data_source('sqlite', database=get_meta_db_path())
        init_tax_seed_data(ds)
        init_tax_seed_data(ds)

        conn = sqlite3.connect(str(_DB_PATH))
        try:
            after = {
                t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                for t in ('tax_classifications', 'tax_codes', 'tax_rates')
            }
        finally:
            conn.close()
        assert after == before
