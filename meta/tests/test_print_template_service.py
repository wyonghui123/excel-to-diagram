# -*- coding: utf-8 -*-
"""[M2 2026-11-15] 打印模板服务：变量白名单派生 / 静态校验 / 净化 / 漂移签名

覆盖 spec-print-platform-2026-11-15 §5、§8 的纯逻辑口径（不触库）：
  1. 白名单派生自 BO 元数据：header 字段 + child_sections 子表集合
  2. 合法模板零错误；未知字段 / 未声明别名 / 未知集合 / 未闭合块均报错
  3. HTML 净化：script / 内联事件 / link / 远程 url() 被移除并告警
  4. CSS 净化：@page / @import 剥离；expression() 与远程 url() 校验报错
  5. 白名单签名稳定，且跨 BO 可区分（漂移检测口径）
"""
import pytest

pytestmark = pytest.mark.unit

from meta.core.models import registry
from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory
from meta.services import print_template_service as svc

BO = 'customer_invoice'


def setup_module(module):
    if not registry.list_objects():
        register_from_directory(get_yaml_schema_dir())


def test_derive_variables_from_bo_metadata():
    variables = svc.derive_variables(BO)
    assert variables['root'] == 'doc'
    assert 'bill_to_account_id' in variables['fields']
    assert 'customer_invoice_line' in variables['collections']
    inner = variables['collections']['customer_invoice_line']['inner_alias']
    assert inner == 'customer_invoice_line'
    assert variables['collections']['customer_invoice_line']['fields']


def test_derive_variables_unknown_bo():
    with pytest.raises(svc.PrintTemplateError) as exc:
        svc.derive_variables('__not_a_bo__')
    assert exc.value.code == 'bo_not_found'


def test_validate_valid_template():
    variables = svc.derive_variables(BO)
    line_field = sorted(variables['collections']['customer_invoice_line']['fields'])[0]
    html = (
        '<h1>{{ doc.bill_to_account_id }}</h1>'
        '{{#if doc.bill_to_account_id}}<span>x</span>{{else}}<span>-</span>{{/if}}'
        '{{#each customer_invoice_line}}'
        '<tr><td>{{ customer_invoice_line.' + line_field + ' }}</td></tr>'
        '{{/each}}'
    )
    errors, warnings = svc.validate_template(html, variables)
    assert errors == []
    assert warnings == []


def test_validate_rejects_unknown_variables_and_blocks():
    variables = svc.derive_variables(BO)
    html = (
        '{{ doc.__nope__ }} {{ oops }} '
        '{{#each not_a_collection}}x{{/each}} '
        '{{#if doc.bill_to_account_id}}unclosed'
    )
    errors, _ = svc.validate_template(html, variables)
    codes = {item['code'] for item in errors}
    assert 'unknown_variable' in codes
    assert 'unknown_collection' in codes
    assert 'unclosed_block' in codes


def test_validate_empty_template():
    errors, _ = svc.validate_template('   ', svc.derive_variables(BO))
    assert [item['code'] for item in errors] == ['template_empty']


def test_sanitize_html_strips_scripts_handlers_and_links():
    clean, warnings = svc.sanitize_html(
        '<script>alert(1)</script>'
        '<img src="x" onerror="alert(2)">'
        '<link rel="stylesheet" href="//cdn.example/x.css">'
        '<p style="background:url(https://example.test/a.png)">ok</p>'
    )
    assert '<script' not in clean
    assert 'onerror' not in clean
    assert '<link' not in clean
    assert 'https://example.test' not in clean
    assert warnings


def test_sanitize_css_strips_page_and_import():
    clean, warnings = svc.sanitize_css(
        '@page { size: A5 } @import url("http://x/y.css"); body{color:red}')
    assert '@page' not in clean
    assert '@import' not in clean
    assert 'body{color:red}' in clean
    assert len(warnings) == 2


def test_validate_css_rejects_expression_and_remote():
    errors = svc.validate_css('@import url("http://x"); body{width:expression(1)}')
    assert len(errors) == 3
    assert {item['code'] for item in errors} == {'unsupported_css'}


def test_variables_signature_stable_and_discriminating():
    first = svc.variables_signature(svc.derive_variables(BO))
    second = svc.variables_signature(svc.derive_variables(BO))
    assert first == second
    assert first != svc.variables_signature(svc.derive_variables('sales_order'))
    assert first != svc.variables_signature({})