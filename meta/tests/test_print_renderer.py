# -*- coding: utf-8 -*-
"""M3 渲染层单测：模板求值 / 默认版式合成 / @page 注入 / PDF 引擎选择。

覆盖口径:
  1. `{{ doc.field }}` 取值 + HTML 转义；`#each` 循环别名；`#if` / `{{else}}`；
  2. `format_value` 金额 / 日期 / 布尔 / 空值；
  3. `default_layout` 完全派生自 BO 元数据（字段标签 + child_sections 子表）；
  4. `build_document` 只在此注入 @page（纸张/方向/边距）与场景水印；
  5. PDF 引擎：`stub` 返回占位字节，未知引擎报错。
"""
import html as html_lib

import pytest

pytestmark = pytest.mark.unit

from meta import get_meta_object, registry
from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory
from meta.services import print_renderer as renderer


def setup_module():
    if not registry.list_objects():
        register_from_directory(get_yaml_schema_dir())


VARIABLES = {
    'root': 'doc',
    'fields': {
        'no': {'type': 'string'},
        'amount': {'type': 'money'},
        'status': {'type': 'string'},
    },
    'collections': {
        'demo_line': {
            'inner_alias': 'demo_line',
            'fields': {'item_name': {'type': 'string'}},
        },
    },
}


def _data(values=None, collections=None):
    return {
        'root': 'doc',
        'doc': values or {},
        'collections': collections or {},
    }


def test_render_template_variables_and_escaping():
    template = '<p>{{ doc.no }}</p><p>{{ doc.amount }}</p>'
    html = renderer.render_template(
        template,
        _data({'no': '<b>CI-001</b>', 'amount': '1234.5'}),
        VARIABLES)
    assert html == '<p>&lt;b&gt;CI-001&lt;/b&gt;</p><p>1,234.50</p>'
    assert html_lib.escape('<b>CI-001</b>') in html


def test_render_template_each_and_if_else():
    template = ('{{#each demo_line}}{{ demo_line.item_name }}:{{ doc.status }};{{/each}}'
                '{{#if doc.no}}HAS{{else}}EMPTY{{/if}}')
    html = renderer.render_template(
        template,
        _data({'status': 'draft', 'no': ''},
              {'demo_line': [{'item_name': 'A'}, {'item_name': 'B'}]}),
        VARIABLES)
    assert html == 'A:draft;B:draft;EMPTY'


def test_render_template_unknown_path_renders_blank():
    assert renderer.render_template('{{ doc.missing }}',
                                    _data({'no': 'x'}), VARIABLES) == ''


def test_format_value_types():
    assert renderer.format_value('1234.5', 'money') == '1,234.50'
    assert renderer.format_value('2026-11-15 10:20:30', 'date') == '2026-11-15'
    assert renderer.format_value('2026-11-15T10:20:30', 'datetime') == '2026-11-15 10:20:30'
    assert renderer.format_value(True) == '是'
    assert renderer.format_value(None) == ''
    assert renderer.format_value(['A', 'B']) == 'A、B'


def test_default_layout_derives_from_bo_metadata():
    obj = get_meta_object('customer_invoice')
    assert obj is not None

    fields = [field for field in obj.fields
              if field.id != 'id' and getattr(field.storage, 'value', 'stored') != 'virtual']
    first = fields[0]
    values = {first.id: '测试值<1>'}

    section = obj.ui_view_config.child_sections[0]
    child_code = section['child_object'] if isinstance(section, dict) else section.child_object
    child_meta = get_meta_object(child_code)
    child_fields = [field for field in child_meta.fields
                    if field.id != 'id' and getattr(field.storage, 'value', 'stored') != 'virtual']
    collections = {child_code: [{child_fields[0].id: '行值'}]}

    html = renderer.default_layout(obj, values, collections, doc_no='CI-001')
    assert 'CI-001' in html
    assert html_lib.escape(str(first.name)) in html
    assert html_lib.escape('测试值<1>') in html
    assert html_lib.escape(str(child_fields[0].name)) in html
    assert '行值' in html
    assert '（1）' in html


def test_build_document_injects_page_settings_and_watermark():
    html = renderer.build_document(
        '<p>x</p>', css='body{color:red}', paper_size='A5', orientation='landscape',
        margin_top=5, margin_right=6, margin_bottom=7, margin_left=8,
        title='示例', watermark='PREVIEW')
    assert '@page { size: 148mm 210mm landscape; margin: 5mm 6mm 7mm 8mm; }' in html
    assert 'body{color:red}' in html
    assert '<div class="print-watermark">PREVIEW</div>' in html
    assert '<title>示例</title>' in html


def test_page_css_falls_back_to_a4_for_unknown_paper():
    css = renderer.page_css('NoSuchPaper', 'diagonal')
    assert 'size: 210mm 297mm portrait' in css


def test_render_pdf_stub_engine():
    assert renderer.render_pdf('<html></html>', engine='stub') == renderer.STUB_PDF


def test_render_pdf_rejects_unknown_engine():
    with pytest.raises(renderer.PrintRenderError) as excinfo:
        renderer.render_pdf('<html></html>', engine='phantom')
    assert excinfo.value.code == 'pdf_engine_unsupported'