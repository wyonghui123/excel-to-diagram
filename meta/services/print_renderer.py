# -*- coding: utf-8 -*-
"""打印渲染层（M3）。

依据: docs/specs/spec-print-platform-2026-11-15.md §5 / §6 / D-PR-16
职责:
  · `default_layout(bo_meta)`：未配模板时按 BO 元数据合成默认版式（不落库）；
  · `render_template(html, data, variables)`：最小模板语言求值（`{{ path }}` /
    `{{#if}}` / `{{#each}}` / `{{else}}`）；
  · `build_document(...)`：拼装完整 HTML，纸张/边距由模板行参数注入（模板内 @page
    已在发布期剥离），并按场景叠加水印；
  · `render_pdf(...)`：HTML → PDF（`PRINT_ENGINE=chromium`，测试可切 `stub`）。

纪律:
  · 只读 BO 元数据与取数结果，不写任何表；
  · 模板页眉页脚与格式化由本层统一提供（`format_value`），模板不写逻辑；
  · 渲染期禁止外网请求（Chromium 路由拦截），字体只用系统内置。
"""

from __future__ import annotations

import html as html_lib
import os
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence, Tuple

from meta.services.print_template_service import (
    _child_sections, _meta_object, _section_field)

PAPER_SIZES = {
    'A4': '210mm 297mm',
    'A5': '148mm 210mm',
    'B5': '176mm 250mm',
    'Letter': '8.5in 11in',
}

ORIENTATIONS = ('portrait', 'landscape')

WATERMARK_NONE = 'NONE'
WATERMARK_PREVIEW = 'PREVIEW'
WATERMARK_DRAFT = 'DRAFT'
WATERMARK_REPRINT = 'REPRINT'
WATERMARKS = (WATERMARK_NONE, WATERMARK_PREVIEW, WATERMARK_DRAFT, WATERMARK_REPRINT)

#: 测试占位 PDF（`PRINT_ENGINE=stub`），不参与真实归档
STUB_PDF = b'%PDF-1.4\n% print-stub\n%%EOF\n'

MONEY_TYPES = ('money', 'currency', 'amount', 'price', 'decimal')

BASE_CSS = """
.print-sheet { font-family: "Microsoft YaHei", "PingFang SC", SimSun, sans-serif;
  font-size: 12px; color: #222; }
.print-doc-title { text-align: center; margin-bottom: 8mm; }
.print-doc-title h1 { font-size: 20px; margin: 0 0 2mm; }
.print-doc-no { font-size: 13px; color: #444; }
.print-grid { width: 100%; border-collapse: collapse; margin-bottom: 6mm; }
.print-grid th, .print-grid td { border: 1px solid #bbb; padding: 4px 6px;
  text-align: left; vertical-align: top; }
.print-grid th { background: #f3f3f3; font-weight: normal; width: 12%; }
.print-section { margin-top: 6mm; page-break-inside: auto; }
.print-section h2 { font-size: 14px; margin: 0 0 3mm; }
.print-table { width: 100%; border-collapse: collapse; }
.print-table th, .print-table td { border: 1px solid #bbb; padding: 4px 6px;
  text-align: left; }
.print-table thead th { background: #f3f3f3; font-weight: normal; }
.print-empty { color: #888; }
.print-watermark { position: fixed; top: 45%; left: 50%; z-index: 9999;
  transform: translate(-50%, -50%) rotate(-30deg); font-size: 64px;
  letter-spacing: 8px; color: rgba(0, 0, 0, 0.10); pointer-events: none; }
"""

_TOKEN_RE = re.compile(r'\{\{\s*(.*?)\s*\}\}', re.S)


class PrintRenderError(Exception):
    """渲染期错误（code 供 API 层映射错误码）。"""

    def __init__(self, code: str, message: str, status: int = 500,
                 errors: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.errors = errors or []


# ------------------------------------------------------------------ 值格式化

def format_value(value: Any, type_name: str = '') -> str:
    """渲染层统一格式化：金额 / 日期 / 布尔 / 空值（模板不写格式化逻辑）。"""
    if value is None:
        return ''
    if isinstance(value, bool):
        return '是' if value else '否'
    declared = (type_name or '').strip().lower()
    if declared in MONEY_TYPES:
        return _money(value)
    if declared.startswith('datetime'):
        return _datetime(value)
    if declared.startswith('date'):
        return str(value)[:10]
    if isinstance(value, (list, tuple)):
        return '、'.join(format_value(item) for item in value)
    if isinstance(value, dict):
        return ', '.join('{0}: {1}'.format(k, format_value(v))
                         for k, v in value.items())
    return str(value)


def _money(value: Any) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    return '{0:,.2f}'.format(amount)


def _datetime(value: Any) -> str:
    text = str(value).replace('T', ' ')
    return text[:19]


# ------------------------------------------------------------------ 模板求值

def _tokenize(text: str) -> List[Tuple[str, str]]:
    tokens: List[Tuple[str, str]] = []
    source = text or ''
    pos = 0
    for match in _TOKEN_RE.finditer(source):
        if match.start() > pos:
            tokens.append(('text', source[pos:match.start()]))
        tokens.append(('tag', match.group(1).strip()))
        pos = match.end()
    if pos < len(source):
        tokens.append(('text', source[pos:]))
    return tokens


def _parse(tokens: Sequence[Tuple[str, str]],
           pos: int) -> Tuple[List[Tuple], int]:
    nodes: List[Tuple] = []
    while pos < len(tokens):
        kind, value = tokens[pos]
        if kind == 'text':
            nodes.append(('text', value))
            pos += 1
            continue

        tag = value
        if tag == 'else' or tag.startswith('/'):
            return nodes, pos

        if tag.startswith('#if '):
            path = tag[4:].strip()
            then_nodes, pos = _parse(tokens, pos + 1)
            else_nodes: List[Tuple] = []
            if pos < len(tokens) and tokens[pos][1] == 'else':
                else_nodes, pos = _parse(tokens, pos + 1)
            if pos < len(tokens):
                pos += 1  # /if
            nodes.append(('if', path, then_nodes, else_nodes))
            continue

        if tag.startswith('#each '):
            name = tag[6:].strip()
            body, pos = _parse(tokens, pos + 1)
            if pos < len(tokens):
                pos += 1  # /each
            nodes.append(('each', name, body))
            continue

        nodes.append(('var', tag))
        pos += 1
    return nodes, pos


def _truthy(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        text = value.strip().lower()
        return text not in ('', '0', 'false', 'none', 'null')
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    return bool(value)


def _resolve(path: str, data: Dict[str, Any],
             scope: Dict[str, Dict[str, Any]]) -> Any:
    parts = [part.strip() for part in str(path).split('.') if part.strip()]
    if len(parts) != 2:
        return None
    head, tail = parts
    if head == data.get('root', 'doc'):
        return (data.get('doc') or {}).get(tail)
    row = scope.get(head)
    return row.get(tail) if row is not None else None


def _field_type(path: str, variables: Dict[str, Any],
                scope: Dict[str, Dict[str, Any]]) -> str:
    parts = [part.strip() for part in str(path).split('.') if part.strip()]
    if len(parts) != 2:
        return ''
    head, tail = parts
    if head == variables.get('root', 'doc') or head == 'doc':
        return ((variables.get('fields') or {}).get(tail) or {}).get('type', '')
    for key, collection in (variables.get('collections') or {}).items():
        if key == head or collection.get('inner_alias') == head:
            return ((collection.get('fields') or {}).get(tail) or {}).get('type', '')
    return ''


def _render_nodes(nodes: Sequence[Tuple], data: Dict[str, Any],
                  variables: Dict[str, Any],
                  scope: Dict[str, Dict[str, Any]], out: List[str]) -> None:
    for node in nodes:
        kind = node[0]
        if kind == 'text':
            out.append(node[1])
        elif kind == 'var':
            path = node[1]
            value = _resolve(path, data, scope)
            out.append(html_lib.escape(format_value(value, _field_type(path, variables, scope))))
        elif kind == 'if':
            path, then_nodes, else_nodes = node[1], node[2], node[3]
            branch = then_nodes if _truthy(_resolve(path, data, scope)) else else_nodes
            _render_nodes(branch, data, variables, scope, out)
        elif kind == 'each':
            name, body = node[1], node[2]
            rows = (data.get('collections') or {}).get(name) or []
            alias = name
            collection = (variables.get('collections') or {}).get(name)
            if collection:
                alias = collection.get('inner_alias') or name
            for row in rows:
                inner = dict(scope)
                inner[name] = row
                inner[alias] = row
                _render_nodes(body, data, variables, inner, out)


def render_template(html: str, data: Dict[str, Any],
                    variables: Optional[Dict[str, Any]] = None) -> str:
    """求值最小模板语言；data 形如 ``{'root':'doc','doc':{...},'collections':{...}}``。"""
    nodes, _ = _parse(_tokenize(html), 0)
    out: List[str] = []
    _render_nodes(nodes, data, variables or {}, {}, out)
    return ''.join(out)


# ------------------------------------------------------------------ 默认版式

def _is_readable(field: Any) -> bool:
    annotation = getattr(field, 'permission', None)
    return bool(getattr(annotation, 'readable', True))


def _is_virtual(field: Any) -> bool:
    storage = getattr(getattr(field, 'storage', None), 'value', 'stored')
    return storage == 'virtual'


def _layout_fields(meta_obj: Any, exclude: Sequence[str] = ('id',)) -> List[Any]:
    fields = []
    for field in getattr(meta_obj, 'fields', None) or []:
        code = str(getattr(field, 'id', '') or '')
        if not code or code in exclude:
            continue
        if _is_virtual(field) or not _is_readable(field):
            continue
        fields.append(field)
    return fields


def _field_value(field: Any, values: Dict[str, Any]) -> Any:
    code = str(getattr(field, 'id', '') or '')
    if code in values:
        return values.get(code)
    column = str(getattr(field, 'db_column', '') or '')
    return values.get(column)


def default_layout(bo_meta: Any, values: Optional[Dict[str, Any]] = None,
                   collections: Optional[Dict[str, List[Dict[str, Any]]]] = None,
                   doc_no: str = '') -> str:
    """按 BO 元数据合成默认版式（D-PR-16）：字段标签 + 值 + child_sections 子表。

    纯派生：不读模板、不落库；模板未配置时 `render` 直接走这里。
    """
    values = values or {}
    collections = collections or {}
    fields = _layout_fields(bo_meta)

    parts: List[str] = ['<div class="print-doc">']
    parts.append('<div class="print-doc-title"><h1>{0}</h1>'.format(
        html_lib.escape(str(getattr(bo_meta, 'name', '') or ''))))
    if doc_no:
        parts.append('<div class="print-doc-no">{0}</div>'.format(
            html_lib.escape(str(doc_no))))
    parts.append('</div>')

    if fields:
        parts.append('<table class="print-grid"><tbody>')
        for index in range(0, len(fields), 2):
            pair = fields[index:index + 2]
            cells = []
            for field in pair:
                declared = str(getattr(field, 'declared_type', '') or
                               getattr(getattr(field, 'field_type', None), 'value', ''))
                label = html_lib.escape(str(getattr(field, 'name', '') or ''))
                value = html_lib.escape(format_value(_field_value(field, values), declared))
                cells.append('<th>{0}</th><td>{1}</td>'.format(label, value))
            if len(cells) == 2:
                cells.append('<th></th><td></td>')
            parts.append('<tr>{0}</tr>'.format(''.join(cells)))
        parts.append('</tbody></table>')

    for section in _child_sections(bo_meta):
        child_code = _section_field(section, 'child_object')
        child_meta = _meta_object(child_code)
        if child_meta is None:
            continue
        rows = collections.get(child_code) or []
        title = _section_field(section, 'title') or getattr(child_meta, 'name', child_code)
        parts.append('<section class="print-section">')
        parts.append('<h2>{0}（{1}）</h2>'.format(html_lib.escape(title), len(rows)))
        child_fields = _layout_fields(child_meta)
        if child_fields:
            headers = ''.join('<th>{0}</th>'.format(
                html_lib.escape(str(getattr(field, 'name', '') or '')))
                for field in child_fields)
            parts.append('<table class="print-table"><thead><tr>{0}</tr></thead><tbody>'.format(headers))
            if rows:
                for row in rows:
                    cells = []
                    for field in child_fields:
                        declared = str(getattr(field, 'declared_type', '') or
                                       getattr(getattr(field, 'field_type', None), 'value', ''))
                        cells.append('<td>{0}</td>'.format(
                            html_lib.escape(format_value(_field_value(field, row), declared))))
                    parts.append('<tr>{0}</tr>'.format(''.join(cells)))
            else:
                parts.append('<tr><td colspan="{0}" class="print-empty">无明细</td></tr>'.format(
                    len(child_fields)))
            parts.append('</tbody></table>')
        parts.append('</section>')

    parts.append('</div>')
    return ''.join(parts)


# ------------------------------------------------------------------ 文档拼装

def page_css(paper_size: str = 'A4', orientation: str = 'portrait',
             margin_top: float = 10, margin_right: float = 10,
             margin_bottom: float = 10, margin_left: float = 10) -> str:
    """纸张唯一真源 = 模板行列参数；未知纸张回退 A4。"""
    size = PAPER_SIZES.get(str(paper_size or 'A4').strip(), PAPER_SIZES['A4'])
    direction = orientation if orientation in ORIENTATIONS else 'portrait'
    margins = ' '.join('{0:g}mm'.format(float(value or 0))
                       for value in (margin_top, margin_right, margin_bottom, margin_left))
    return '@page {{ size: {0} {1}; margin: {2}; }}\n'.format(size, direction, margins)


def watermark_text(watermark: str) -> str:
    if watermark == WATERMARK_PREVIEW:
        return 'PREVIEW'
    if watermark == WATERMARK_DRAFT:
        return 'DRAFT'
    if watermark == WATERMARK_REPRINT:
        return os.environ.get('PRINT_WATERMARK_TEXT', 'REPRINT').strip() or 'REPRINT'
    return ''


def build_document(body_html: str, *, css: str = '', paper_size: str = 'A4',
                   orientation: str = 'portrait', margin_top: float = 10,
                   margin_right: float = 10, margin_bottom: float = 10,
                   margin_left: float = 10, title: str = '',
                   watermark: str = WATERMARK_NONE) -> str:
    """拼装完整打印 HTML；@page 只在此处注入。"""
    style = page_css(paper_size, orientation, margin_top, margin_right,
                     margin_bottom, margin_left) + BASE_CSS
    if css:
        style += '\n' + css
    overlay = ''
    text = watermark_text(watermark)
    if text:
        overlay = '<div class="print-watermark">{0}</div>'.format(html_lib.escape(text))
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<title>{0}</title><style>{1}</style></head>'
        '<body>{2}<div class="print-sheet">{3}</div></body></html>'
    ).format(html_lib.escape(title or '打印'), style, overlay, body_html)


# ------------------------------------------------------------------ PDF 引擎

def render_pdf(html: str, engine: Optional[str] = None,
               timeout_ms: Optional[int] = None) -> bytes:
    """HTML → PDF。`PRINT_ENGINE=chromium`（默认）或 `stub`（测试）。

    Chromium 无网启动：拦截一切 http(s) 请求，避免模板残留外链造成 SSRF。
    """
    engine_name = (engine or os.environ.get('PRINT_ENGINE', 'chromium')).strip().lower()
    if engine_name == 'stub':
        return STUB_PDF
    if engine_name != 'chromium':
        raise PrintRenderError('pdf_engine_unsupported',
                               '不支持的打印引擎: %s' % engine_name, 500)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise PrintRenderError('pdf_engine_unavailable',
                               'Chromium 引擎不可用：未安装 playwright', 500) from None

    timeout = int(timeout_ms or os.environ.get('PRINT_RENDER_TIMEOUT_MS', '20000'))

    def _block_network(route: Any) -> None:
        if route.request.url.startswith(('http://', 'https://')):
            route.abort()
        else:
            route.continue_()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            try:
                page = browser.new_page()
                page.route('**/*', _block_network)
                page.set_content(html, wait_until='load', timeout=timeout)
                return page.pdf(print_background=True,
                                prefer_css_page_size=True, timeout=timeout)
            finally:
                browser.close()
    except PrintRenderError:
        raise
    except Exception as exc:  # playwright 超时 / 崩溃
        message = str(exc)
        code = 'render_timeout' if 'imeout' in message or 'Timeout' in message else 'render_failed'
        raise PrintRenderError(code, 'PDF 渲染失败: %s' % message, 500) from exc