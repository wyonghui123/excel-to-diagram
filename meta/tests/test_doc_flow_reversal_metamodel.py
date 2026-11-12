# -*- coding: utf-8 -*-
"""R-MM-05 正/逆/调整同构声明：覆盖度 + 原边 immutable lint（Spec §7）。

验收映射：
  A-05-1  第二类单据只靠声明即可冲销：编排器无按单据类型字面量的 Python 分支（R20）
  A-05-2  冲销只追加边：原单行（数量 / updated_at）不被 UPDATE（R21）
  A-05-3  三档（red_reverse / counter / red_ink）经同一 reverse_document 分派走通

lint 结构单测覆盖：document 段必填与引用可解析、切面注入字段、
posting_state 状态值校验、doc_effect.reversal 声明合法性、R21 白名单。

ALLOW_RAW_SQL：A-05-2 需构造最小 receipt_lines 桩表，证明冲销不改写原单行
（数量 / updated_at 前后一致），不走通用 factory。
"""

import subprocess
import sys

import pytest

from meta.core.datasource import (
    _clear_data_source_cache_for_testing,
    get_data_source,
)
from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables
from meta.core.reversal_orchestrator import reverse_document, reverse_document_edges
from meta.core.reversal_profiles import (
    REVERSAL_PROFILES,
    VALID_COMMITMENTS,
    VALID_MODES,
)
from meta.tools import lint_metamodel as lint


@pytest.fixture
def app_ds(tmp_path, monkeypatch):
    monkeypatch.setenv('SQLITE_DB_DIR', str(tmp_path / 'db'))
    _clear_data_source_cache_for_testing()
    ds = get_data_source('sqlite', database=str(tmp_path / 'biz.db'))
    ensure_doc_flow_edge_tables(ds)
    yield ds
    _clear_data_source_cache_for_testing()


def _edge(ds, edge_id, source_bo, source_id, rule_id, qty=10):
    ds.insert('doc_flow_edges', {
        'id': edge_id,
        'source_bo': source_bo,
        'source_id': str(source_id),
        'source_item': '',
        'target_bo': 'inventory_txn',
        'target_id': 'T-' + edge_id,
        'target_item': '',
        'quantity': qty,
        'rule_id': rule_id,
        'quantity_sign': 'normal',
        'status': 'active',
        'pool': 'default',
    })


def _row(ds, edge_id):
    rows = ds.query(
        'SELECT id, quantity_sign, status, edge_kind, reverses_edge_id '
        'FROM doc_flow_edges WHERE id = ?', (edge_id,))
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# 真实 schema 基线：覆盖度 14 个 document 段 / 6 个 reversal 声明 / 0 违规
# ---------------------------------------------------------------------------

def test_lint_doc_flow_passes_on_real_schemas():
    violations, scanned, fact_schemas, declared = lint.lint_doc_flow()

    assert violations == []
    assert scanned >= 14
    assert set(declared) == {
        'customer_invoice.yaml',
        'inventory_adjustment.yaml',
        'receipt.yaml',
        'shipment.yaml',
        'transfer_order.yaml',
        'vendor_invoice.yaml',
    }
    # 事实单据被登记（R20 扫描面 = 这些 schema id）
    assert {'receipt', 'purchase_order', 'shipment'} <= set(fact_schemas)


def test_lint_tool_exit_code_zero_for_doc_flow():
    result = subprocess.run(
        [sys.executable, 'meta/tools/lint_metamodel.py', '--doc-flow'],
        capture_output=True, text=True, cwd=str(lint.ROOT), timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# document 段判据（tmp 隔离目录）
# ---------------------------------------------------------------------------

def _isolate(monkeypatch, tmp_path, schema_text, aspects_text=None):
    schemas = tmp_path / 'schemas'
    schemas.mkdir()
    (schemas / 'demo.yaml').write_text(schema_text, encoding='utf-8')
    if aspects_text is not None:
        (schemas / 'aspects.yaml').write_text(aspects_text, encoding='utf-8')
    empty_meta = tmp_path / 'meta'
    (empty_meta / 'core').mkdir(parents=True)
    # R20 判据要求编排器文件存在；桩文件无单据类型字面量
    (empty_meta / 'core' / 'reversal_orchestrator.py').write_text(
        "MODE = 'shared'\n", encoding='utf-8')
    monkeypatch.setattr(lint, 'SCHEMAS_DIR', schemas)
    monkeypatch.setattr(lint, 'R21_SCAN_ROOT', empty_meta)
    monkeypatch.setattr(lint, 'ROOT', tmp_path)


def test_document_requires_state_field(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, (
        'id: demo\n'
        'fields:\n'
        '  - id: demo_no\n'
        'document:\n'
        '  number_field: demo_no\n'
    ))
    violations, scanned, _facts, _declared = lint.lint_doc_flow()
    assert scanned == 1
    assert any(field == 'document.state_field' and '必填' in reason
               for _label, field, reason in violations)


def test_document_fields_resolve_through_aspect(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, (
        'id: demo\n'
        'aspects: [document_type_aspect]\n'
        'states:\n'
        '  - code: draft\n'
        '  - code: confirmed\n'
        'fields:\n'
        '  - id: demo_no\n'
        '  - id: demo_date\n'
        '  - id: status\n'
        'document:\n'
        '  state_field: status\n'
        '  number_field: demo_no\n'
        '  business_date_field: demo_date\n'
        '  document_type_field: document_type_id\n'
        '  posting_state: confirmed\n'
    ), aspects_text=(
        'document_type_aspect:\n'
        '  fields:\n'
        '    - id: document_type_id\n'
        '      db_column: document_type_id\n'
    ))
    violations, scanned, _facts, _declared = lint.lint_doc_flow()
    assert scanned == 1
    # 隔离目录不含真实 profiles 指向的对象，只看本文件自身违规
    assert [v for v in violations if v[0] == 'demo.yaml'] == []


def test_posting_state_must_be_declared_state(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, (
        'id: demo\n'
        'states:\n'
        '  - code: draft\n'
        'fields:\n'
        '  - id: status\n'
        'document:\n'
        '  state_field: status\n'
        '  posting_state: confirmed\n'
    ))
    violations, _scanned, _facts, _declared = lint.lint_doc_flow()
    assert any(field == 'document.posting_state' and 'confirmed' in reason
               for _label, field, reason in violations)


def test_unknown_document_field_is_flagged(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, (
        'id: demo\n'
        'fields:\n'
        '  - id: status\n'
        'document:\n'
        '  state_field: status\n'
        '  number_field: no_such_field\n'
    ))
    violations, _scanned, _facts, _declared = lint.lint_doc_flow()
    assert any(field == 'document.number_field'
               for _label, field, _reason in violations)


# ---------------------------------------------------------------------------
# doc_effect.reversal 声明合法性
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('reversal, expect_field', [
    ('not-a-mapping', 'doc_effect.reversal'),
    ({}, 'doc_effect.reversal.from_states'),
    ({'from_states': ['posted']}, 'doc_effect.reversal.to_state'),
    ({'from_states': ['posted'], 'to_state': 'reversed',
      'order': 'random'}, 'doc_effect.reversal.order'),
    ({'from_states': ['posted'], 'to_state': 'reversed',
      'create_document': {'primitive': 'no_such_creator'}},
     'doc_effect.reversal.create_document.primitive'),
    ({'from_states': ['posted'], 'to_state': 'reversed',
      'write_audit_fields': ['reversed_at']},
     'doc_effect.reversal.write_audit_fields'),
])
def test_lint_reversal_block_rejects_invalid(reversal, expect_field):
    violations = lint._lint_reversal_block('demo.yaml', reversal, {'doc_creator_x'})
    assert any(field == expect_field for _label, field, _reason in violations)


def test_lint_reversal_block_accepts_valid():
    violations = lint._lint_reversal_block('demo.yaml', {
        'from_states': ['posted'],
        'to_state': 'reversed',
        'idempotent_states': [],
        'order': 'inverted',
        'write_audit_fields': {'reversed_at': '{now}'},
        'create_document': {'primitive': 'doc_creator_x'},
    }, {'doc_creator_x'})
    assert violations == []


# ---------------------------------------------------------------------------
# profiles：三档齐全且取值受控（A-05-3 的声明侧）
# ---------------------------------------------------------------------------

def test_profiles_cover_three_modes():
    assert {profile['mode'] for profile in REVERSAL_PROFILES.values()} == VALID_MODES
    for document_type, profile in REVERSAL_PROFILES.items():
        assert profile['mode'] in VALID_MODES, document_type
        assert profile['commitment'] in VALID_COMMITMENTS, document_type
        for idx, edge in enumerate(profile.get('edges') or []):
            assert str(edge.get('rule_id') or '').strip(), (document_type, idx)
            assert str(edge.get('source_bo') or '').strip(), (document_type, idx)


# ---------------------------------------------------------------------------
# R20：编排器无单据类型字面量分支
# ---------------------------------------------------------------------------

def test_orchestrator_has_no_document_type_literal():
    literals = lint._orchestrator_string_literals()
    assert literals is not None
    _violations, _scanned, fact_schemas, _declared = lint.lint_doc_flow()
    assert not (set(fact_schemas) & literals)
    assert not (set(REVERSAL_PROFILES) & literals)


# ---------------------------------------------------------------------------
# R21：数量列 UPDATE 判据 + 白名单
# ---------------------------------------------------------------------------

def test_r21_flags_quantity_update_outside_allowlist(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, 'id: demo\nfields:\n  - id: status\n'
                                    'document:\n  state_field: status\n')
    bad = tmp_path / 'meta' / 'core' / 'bad_compensation.py'
    bad.write_text(
        "SQL = 'UPDATE receipt_lines SET qty_received = 0 WHERE id = 1'\n",
        encoding='utf-8')
    violations, _scanned, _facts, _declared = lint.lint_doc_flow()
    assert any(field == 'UPDATE receipt_lines'
               for _label, field, reason in violations)


def test_r21_allowlist_covers_transfer_compensation_only():
    assert lint.R21_ALLOWLIST == {
        ('meta/core/reversal_primitives.py', 'transfer_order_lines'):
            '补偿原语：调拨行发货事实归零供履约投影重算（不改 cancelled 行）',
    }
    target = lint.ROOT / 'meta' / 'core' / 'reversal_primitives.py'
    assert target.exists()


# ---------------------------------------------------------------------------
# A-05-2：冲销只追加边，原单行不被改写
# ---------------------------------------------------------------------------

def test_a05_2_source_level_reversal_keeps_original_line_untouched(app_ds):
    app_ds.execute(
        'CREATE TABLE receipt_lines ('
        'id INTEGER PRIMARY KEY, receipt_id INTEGER, line_no INTEGER, '
        'qty_received REAL, updated_at TEXT)')
    app_ds.insert('receipt_lines', {
        'id': 1, 'receipt_id': 7, 'line_no': 1,
        'qty_received': 10, 'updated_at': '2026-11-01T10:00:00',
    })
    _edge(app_ds, 'e1', 'receipt_line', 1, 'receipt_line_to_inventory_txn', qty=10)

    reverse_document_edges(app_ds, app_ds, 'receipt', 1,
                           ref_id='RED-1', reason='供应商错发')

    line = app_ds.query('SELECT qty_received, updated_at FROM receipt_lines WHERE id = 1')[0]
    assert line['qty_received'] == 10
    assert line['updated_at'] == '2026-11-01T10:00:00'
    # 原边保留（immutable），仅追加补偿边
    assert _row(app_ds, 'e1')['status'] == 'active'


# ---------------------------------------------------------------------------
# A-05-3：同一 reverse_document 按 profile 分派三档
# ---------------------------------------------------------------------------

def test_a05_3_red_reverse_flips_original_and_appends_red(app_ds):
    _edge(app_ds, 'e1', 'receipt_line', 1, 'receipt_line_to_inventory_txn')
    reverse_document(app_ds, app_ds, 'receipt', edge_id='e1',
                     reason='供应商错发', ref_id='RED-1', quantity=10)
    assert _row(app_ds, 'e1')['status'] == 'reversed'


def test_a05_3_counter_dispatch_is_profile_driven(app_ds, monkeypatch):
    from meta.core import reversal_orchestrator

    calls = {}

    def fake_counter(app_ds_, platform_ds_, edge_id, **kwargs):
        calls['edge_id'] = edge_id
        calls['return_rule_id'] = kwargs.get('return_rule_id')
        return 'counter-ok'

    monkeypatch.setattr(reversal_orchestrator, 'counter_edge', fake_counter)
    result = reverse_document(app_ds, app_ds, 'shipment', edge_id='e1',
                              reason='客户退货', ref_id='SR-1', quantity=10,
                              return_rule_id='inventory_txn_to_return')
    assert result == 'counter-ok'
    assert calls == {'edge_id': 'e1', 'return_rule_id': 'inventory_txn_to_return'}


def test_a05_3_red_ink_appends_same_direction_red_edge(app_ds):
    _edge(app_ds, 'e1', 'vendor_invoice_line', 1,
          'po_schedule_to_vendor_invoice_line')
    reverse_document(app_ds, app_ds, 'vendor_invoice', edge_id='e1',
                     reason='发票金额调减', ref_id='CN-1', quantity=10)
    rows = app_ds.query(
        "SELECT id, quantity_sign, status FROM doc_flow_edges "
        "WHERE quantity_sign = 'red'")
    assert len(rows) == 1
    assert rows[0]['status'] == 'active'
    # red_ink 同方向红字：原边不翻转
    assert _row(app_ds, 'e1')['status'] == 'active'