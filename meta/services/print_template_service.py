# -*- coding: utf-8 -*-
"""[打印平台] M2 模板服务：变量白名单派生 / 校验 / 模板生命周期

依据: docs/specs/spec-print-platform-2026-11-15.md §5（变量白名单）、§8（模板生命周期）
单一事实:
  · 白名单只派生自 BO 元数据 registry（fields / ui_view_config.child_sections），
    不落第二真源；print_templates.variables_json 只是发布时冻结的只读快照；
  · 字段可读性沿用字段注解 PermissionAnnotation.readable，不另建字段权限表；
  · 页面纸张参数来自模板列，不由 HTML 内 @page 决定（模板内 @page 会被剥离）。
本模块只管模板本身：不渲染、不判用户权限、不写附件。
"""

import json
import re
from datetime import datetime
from html import escape
from typing import Any, Dict, List, Optional, Tuple

from meta.services import print_repository as repo

ROOT_ALIAS = 'doc'
LOOP_BLOCK = 'each'
IF_BLOCK = 'if'
SUPPORTED_BLOCKS = (IF_BLOCK, LOOP_BLOCK)

# 模板里出现即整段移除的标签（含内容）
FORBIDDEN_CONTENT_TAGS = ('script', 'iframe', 'object', 'applet', 'form')
# 空元素标签，出现即移除（不承载内容）
FORBIDDEN_VOID_TAGS = ('embed', 'link', 'meta', 'base', 'input', 'button')
EVENT_ATTR_RE = re.compile(r'\son[a-z]+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)', re.I)
REMOTE_URL_RE = re.compile(r'url\(\s*[\'"]?\s*(?:https?:)?//[^)]*\)', re.I)
CSS_IMPORT_RE = re.compile(r'@import[^;]*;', re.I)
CSS_PAGE_RE = re.compile(r'@page[^{]*\{[^}]*\}', re.I | re.S)
CSS_EXPRESSION_RE = re.compile(r'expression\s*\(', re.I)
TOKEN_RE = re.compile(r'\{\{\s*([^{}]*?)\s*\}\}')
LITERAL_VALUES = ('true', 'false')


class PrintTemplateError(Exception):
    """模板服务错误：code 为稳定字符串，errors 携带逐条校验问题。"""

    def __init__(self, code: str, message: str, status: int = 400,
                 errors: Optional[List[Dict[str, Any]]] = None):
        self.code = code
        self.message = message
        self.status = status
        self.errors = errors or []
        super().__init__(message)


# --------------------------------------------------------------------- helpers

def _now() -> str:
    return datetime.now().isoformat()


def _section_field(section: Any, key: str) -> str:
    if isinstance(section, dict):
        return str(section.get(key) or '')
    return str(getattr(section, key, '') or '')


def _meta_object(bo_code: str):
    from meta.core.models import registry
    obj = (registry.get_all() or {}).get(bo_code)
    if obj is None:
        obj = registry.get(bo_code)
    return obj


def _singular(alias: str) -> str:
    """集合别名 → 行别名（lines → line）；不猜不规则复数。"""
    if len(alias) > 1 and alias.endswith('s') and not alias.endswith('ss'):
        return alias[:-1]
    return alias


def _field_map(obj: Any) -> Dict[str, Dict[str, Any]]:
    fields: Dict[str, Dict[str, Any]] = {}
    for item in getattr(obj, 'fields', None) or []:
        code = str(getattr(item, 'id', '') or '')
        if not code:
            continue
        storage = getattr(getattr(item, 'storage', None), 'value', 'stored')
        if storage == 'virtual':
            continue
        declared = str(getattr(item, 'declared_type', '') or '')
        field_type = getattr(getattr(item, 'field_type', None), 'value', 'string')
        annotation = getattr(item, 'permission', None)
        fields[code] = {
            'label': str(getattr(item, 'name', '') or ''),
            'type': declared or str(field_type),
            'readable': bool(getattr(annotation, 'readable', True)),
            'required': bool(getattr(item, 'required', False)),
        }
    return fields


def _child_sections(obj: Any) -> List[Any]:
    config = getattr(obj, 'ui_view_config', None)
    sections = getattr(config, 'child_sections', None) or []
    return [s for s in sections if _section_field(s, 'child_object')]


# ------------------------------------------------------------- 白名单派生

def derive_variables(bo_code: str) -> Dict[str, Any]:
    """派生单打印接入点的变量白名单（不落库、无时间戳，便于漂移比对）。"""
    obj = _meta_object(bo_code)
    if obj is None:
        raise PrintTemplateError('bo_not_found', '未知 BO: %s' % bo_code)
    variables: Dict[str, Any] = {
        'bo_code': bo_code,
        'root': ROOT_ALIAS,
        'literals': list(LITERAL_VALUES),
        'fields': _field_map(obj),
        'collections': {},
    }
    for section in _child_sections(obj):
        child_code = _section_field(section, 'child_object')
        child_obj = _meta_object(child_code)
        if child_obj is None:
            continue
        variables['collections'][child_code] = {
            'label': _section_field(section, 'title'),
            'inner_alias': _singular(child_code),
            'fields': _field_map(child_obj),
        }
    return variables


def variables_signature(variables: Dict[str, Any]) -> str:
    """白名单结构签名（用于发布快照与即时派生的漂移比对）。"""
    compact = {
        'root': variables.get('root'),
        'fields': {k: [v.get('type'), v.get('readable')]
                   for k, v in (variables.get('fields') or {}).items()},
        'collections': {
            k: {
                'inner_alias': v.get('inner_alias'),
                'fields': {fk: [fv.get('type'), fv.get('readable')]
                           for fk, fv in (v.get('fields') or {}).items()},
            }
            for k, v in (variables.get('collections') or {}).items()
        },
    }
    return json.dumps(compact, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------- 净化

def sanitize_html(html: str) -> Tuple[str, List[str]]:
    """移除脚本/外链/事件属性；返回 (净化的 HTML, 警告)。"""
    text = html or ''
    warnings: List[str] = []
    for tag in FORBIDDEN_CONTENT_TAGS:
        pattern = re.compile(r'<\s*%s\b[^>]*>[\s\S]*?<\s*/\s*%s\s*>' % (tag, tag), re.I)
        text, removed = pattern.subn('', text)
        if removed:
            warnings.append('%s 标签已移除 ×%d' % (tag, removed))
    for tag in FORBIDDEN_VOID_TAGS:
        pattern = re.compile(r'<\s*%s\b[^>]*/?>' % tag, re.I)
        text, removed = pattern.subn('', text)
        if removed:
            warnings.append('%s 标签已移除 ×%d' % (tag, removed))
    text, removed = EVENT_ATTR_RE.subn('', text)
    if removed:
        warnings.append('内联事件属性已移除 ×%d' % removed)
    text, removed = REMOTE_URL_RE.subn('none', text)
    if removed:
        warnings.append('远程 url() 已移除 ×%d' % removed)
    return text, warnings


def sanitize_css(css: str) -> Tuple[str, List[str]]:
    """剥离 @page / @import；保留其余样式（样式无脚本执行面）。"""
    text = css or ''
    warnings: List[str] = []
    text, removed = CSS_PAGE_RE.subn('', text)
    if removed:
        warnings.append('@page 已剥离 ×%d（纸张由模板参数决定）' % removed)
    text, removed = CSS_IMPORT_RE.subn('', text)
    if removed:
        warnings.append('@import 已移除 ×%d' % removed)
    return text, warnings


# ---------------------------------------------------------------- 校验

def _add(errors: List[Dict[str, Any]], code: str, message: str,
         token: str = '') -> None:
    errors.append({'code': code, 'message': message, 'token': token})


def _check_path(path: str, variables: Dict[str, Any],
                loop_ctx: Optional[Tuple[str, str]],
                errors: List[Dict[str, Any]], token: str) -> bool:
    if path in LITERAL_VALUES:
        return True
    parts = [p for p in path.split('.') if p]
    if len(parts) != 2:
        _add(errors, 'unknown_variable',
             '变量必须为「别名.字段」两段式: %s' % path, token)
        return False
    head, field = parts
    if head == ROOT_ALIAS:
        fields = variables.get('fields') or {}
    elif loop_ctx and head in loop_ctx:
        collection = (variables.get('collections') or {}).get(loop_ctx[0]) or {}
        fields = collection.get('fields') or {}
    else:
        _add(errors, 'unknown_variable',
             '未声明的别名 %s（根别名 %s，循环别名 %s）'
             % (head, ROOT_ALIAS, loop_ctx[1] if loop_ctx else '无'), token)
        return False
    if field not in fields:
        _add(errors, 'unknown_variable',
             '字段 %s 不在 BO 变量白名单内' % path, token)
        return False
    if not fields[field].get('readable', True):
        _add(errors, 'field_not_readable', '字段不可读: %s' % path, token)
        return False
    return True


def validate_template(html: str,
                      variables: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """静态校验：变量白名单 + 控制流配对 + 禁用语法。返回 (errors, warnings)。"""
    errors: List[Dict[str, Any]] = []
    if not (html or '').strip():
        _add(errors, 'template_empty', '模板内容为空')
        return errors, []
    clean, warnings = sanitize_html(html)
    loop_ctx: Optional[Tuple[str, str]] = None
    depth = 0
    stack: List[str] = []
    for match in TOKEN_RE.finditer(clean):
        expr = match.group(1).strip()
        if not expr:
            continue
        if expr.startswith('#'):
            head, _, arg = expr[1:].partition(' ')
            block = head.strip()
            arg = arg.strip()
            if block == LOOP_BLOCK:
                if depth:
                    _add(errors, 'unsupported_nested_block',
                         'P0 不支持嵌套控制流', expr)
                    continue
                collection = (variables.get('collections') or {}).get(arg)
                if not collection:
                    _add(errors, 'unknown_collection',
                         '集合 %s 不在 BO 子表清单内' % arg, expr)
                    continue
                loop_ctx = (arg, str(collection.get('inner_alias') or ''))
                depth = 1
                stack.append(LOOP_BLOCK)
            elif block == IF_BLOCK:
                _check_path(arg, variables, loop_ctx, errors, expr)
                depth += 1
                stack.append(IF_BLOCK)
            else:
                _add(errors, 'unsupported_block',
                     '仅支持 #if / #each: %s' % block, expr)
        elif expr.startswith('/'):
            name = expr[1:].strip()
            if name not in SUPPORTED_BLOCKS:
                _add(errors, 'unsupported_block', '未知闭合块: %s' % name, expr)
                continue
            if not stack or stack[-1] != name:
                _add(errors, 'unclosed_block', '闭合块不配对: %s' % name, expr)
                continue
            stack.pop()
            depth = max(0, depth - 1)
            if name == LOOP_BLOCK:
                loop_ctx = None
        elif expr == 'else':
            if not stack or stack[-1] != IF_BLOCK:
                _add(errors, 'unclosed_block', 'else 必须位于 #if 内', expr)
        elif expr.startswith('>'):
            _add(errors, 'unsupported_partial', 'P0 不支持 {{> partial}}', expr)
        else:
            _check_path(expr, variables, loop_ctx, errors, expr)
    if stack:
        _add(errors, 'unclosed_block', '控制流未闭合: %s' % ','.join(stack))
    return errors, warnings


def validate_css(css: str) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    text = css or ''
    if CSS_EXPRESSION_RE.search(text):
        _add(errors, 'unsupported_css', '禁止 expression()')
    if CSS_IMPORT_RE.search(text):
        _add(errors, 'unsupported_css', '禁止 @import 外链样式')
    if REMOTE_URL_RE.search(text):
        _add(errors, 'unsupported_css', '禁止远程 url()')
    return errors


# ---------------------------------------------------------------- 生命周期

def _load_variables(row: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(row.get('variables_json') or '{}')
    except (TypeError, ValueError):
        return {}


def _assert_printable(bo_code: str, type_code: str) -> None:
    from meta.services.print_capability import is_printable
    if not is_printable(bo_code, type_code or None):
        raise PrintTemplateError(
            'bo_not_printable',
            '接入点不可打印: %s/%s（须为 header 类型且 BO 具备 numbering 或 doc_effect）'
            % (bo_code, type_code or '*'), 400)


def create_draft(bo_code: str, code: str, name: str, html: str,
                 css: str = '', type_code: str = '',
                 paper_size: str = 'A4', orientation: str = 'portrait',
                 margin_top: float = 10, margin_right: float = 10,
                 margin_bottom: float = 10, margin_left: float = 10,
                 scope_type: str = 'system', scope_id: Optional[str] = None,
                 effective_from: Optional[str] = None,
                 effective_to: Optional[str] = None,
                 created_by: str = 'system') -> Dict[str, Any]:
    """新建 draft（保存不阻断：校验问题随返回值提示，净化后落库）。"""
    _assert_printable(bo_code, type_code)
    variables = derive_variables(bo_code)
    clean_html, html_warnings = sanitize_html(html)
    clean_css, css_warnings = sanitize_css(css)
    errors, warnings = validate_template(clean_html, variables)
    version = repo.next_version(bo_code, type_code, code)
    template_id = repo.insert_template({
        'bo_code': bo_code, 'type_code': type_code, 'code': code, 'name': name,
        'version': version, 'status': 'draft',
        'html': clean_html, 'css': clean_css,
        'variables_json': json.dumps(variables, ensure_ascii=False),
        'paper_size': paper_size, 'orientation': orientation,
        'margin_top': margin_top, 'margin_right': margin_right,
        'margin_bottom': margin_bottom, 'margin_left': margin_left,
        'scope_type': scope_type, 'scope_id': scope_id,
        'effective_from': effective_from, 'effective_to': effective_to,
        'created_by': created_by, 'created_at': _now(),
    })
    return {
        'template': repo.get_template(template_id),
        'errors': errors,
        'warnings': warnings + html_warnings + css_warnings,
    }


def update_draft(template_id: int, name: str, html: str, css: str = '',
                 paper_size: str = 'A4', orientation: str = 'portrait',
                 margin_top: float = 10, margin_right: float = 10,
                 margin_bottom: float = 10, margin_left: float = 10,
                 effective_from: Optional[str] = None,
                 effective_to: Optional[str] = None) -> Dict[str, Any]:
    """编辑 draft（仅 draft 生效；已发布模板只能新建版本）。"""
    row = repo.get_template(template_id)
    if not row:
        raise PrintTemplateError('template_not_found', '模板不存在: %s' % template_id, 404)
    if row.get('status') != 'draft':
        raise PrintTemplateError('template_not_draft',
                                 '仅 draft 可编辑，当前状态 %s' % row.get('status'), 409)
    variables = derive_variables(row['bo_code'])
    clean_html, html_warnings = sanitize_html(html)
    clean_css, css_warnings = sanitize_css(css)
    errors, warnings = validate_template(clean_html, variables)
    repo.update_template_content(template_id, {
        'name': name, 'html': clean_html, 'css': clean_css,
        'variables_json': json.dumps(variables, ensure_ascii=False),
        'paper_size': paper_size, 'orientation': orientation,
        'margin_top': margin_top, 'margin_right': margin_right,
        'margin_bottom': margin_bottom, 'margin_left': margin_left,
        'effective_from': effective_from, 'effective_to': effective_to,
    })
    return {
        'template': repo.get_template(template_id),
        'errors': errors,
        'warnings': warnings + html_warnings + css_warnings,
    }


def publish_template(template_id: int) -> Dict[str, Any]:
    """发布 draft：严格校验 → 冻结白名单 → 旧 active 归档 → 置 active。

    发布后内容不可改（D-PR-05），修版走 create_version()。
    """
    row = repo.get_template(template_id)
    if not row:
        raise PrintTemplateError('template_not_found', '模板不存在: %s' % template_id, 404)
    if row.get('status') != 'draft':
        raise PrintTemplateError(
            'template_not_draft',
            '仅 draft 可发布，当前状态 %s（改版请新建版本）' % row.get('status'), 409)
    variables = derive_variables(row['bo_code'])
    clean_html, html_warnings = sanitize_html(row.get('html') or '')
    clean_css, css_warnings = sanitize_css(row.get('css') or '')
    errors, warnings = validate_template(clean_html, variables)
    errors.extend(validate_css(clean_css))
    if errors:
        raise PrintTemplateError('template_invalid', '模板校验未通过', 400, errors)
    repo.update_template_content(template_id, {
        'name': row['name'], 'html': clean_html, 'css': clean_css,
        'variables_json': json.dumps(variables, ensure_ascii=False),
        'paper_size': row.get('paper_size') or 'A4',
        'orientation': row.get('orientation') or 'portrait',
        'margin_top': row.get('margin_top', 10),
        'margin_right': row.get('margin_right', 10),
        'margin_bottom': row.get('margin_bottom', 10),
        'margin_left': row.get('margin_left', 10),
        'effective_from': row.get('effective_from'),
        'effective_to': row.get('effective_to'),
    })
    repo.supersede_active(row['bo_code'], row.get('type_code') or '',
                          row['code'], template_id)
    repo.set_template_status(template_id, 'active')
    return {
        'template': repo.get_template(template_id),
        'warnings': warnings + html_warnings + css_warnings,
    }


def create_version(template_id: int, created_by: str = 'system') -> Dict[str, Any]:
    """基于已有版本新建 draft（复制内容与参数，版本号 +1）。"""
    source = repo.get_template(template_id)
    if not source:
        raise PrintTemplateError('template_not_found', '模板不存在: %s' % template_id, 404)
    if source.get('status') == 'draft':
        raise PrintTemplateError('template_not_published',
                                 '当前已是 draft，请直接编辑', 409)
    version = repo.next_version(source['bo_code'], source.get('type_code') or '',
                                source['code'])
    new_id = repo.insert_template({
        'bo_code': source['bo_code'], 'type_code': source.get('type_code') or '',
        'code': source['code'], 'name': source['name'], 'version': version,
        'status': 'draft', 'html': source.get('html') or '',
        'css': source.get('css') or '',
        'variables_json': source.get('variables_json') or '{}',
        'paper_size': source.get('paper_size') or 'A4',
        'orientation': source.get('orientation') or 'portrait',
        'margin_top': source.get('margin_top', 10),
        'margin_right': source.get('margin_right', 10),
        'margin_bottom': source.get('margin_bottom', 10),
        'margin_left': source.get('margin_left', 10),
        'scope_type': source.get('scope_type') or 'system',
        'scope_id': source.get('scope_id'),
        'effective_from': source.get('effective_from'),
        'effective_to': source.get('effective_to'),
        'created_by': created_by, 'created_at': _now(),
    })
    return repo.get_template(new_id)


def mark_stale(bo_code: str) -> List[int]:
    """检测白名单漂移：active 模板的冻结快照 ≠ 当前派生 → 置 stale。"""
    current = variables_signature(derive_variables(bo_code))
    stale: List[int] = []
    for row in repo.list_templates(bo_code=bo_code, status='active'):
        frozen = variables_signature(_load_variables(row))
        if frozen != current:
            repo.set_template_status(row['id'], 'stale')
            stale.append(int(row['id']))
    return stale


# ------------------------------------------------------------ 默认版式源（D-PR-16）

DEFAULT_TEMPLATE_CSS = (
    '.print-doc { font-family: sans-serif; font-size: 12px; color: #222; }'
    '.print-doc-header h1 { font-size: 20px; text-align: center; margin: 0 0 4px; }'
    '.print-doc-no { text-align: center; margin: 0 0 12px; color: #555; }'
    '.print-doc-fields { width: 100%; border-collapse: collapse; margin-bottom: 12px; }'
    '.print-doc-fields th { width: 22%; text-align: right; font-weight: normal; '
    'color: #555; padding: 3px 6px; border-bottom: 1px solid #ddd; }'
    '.print-doc-fields td { padding: 3px 6px; border-bottom: 1px solid #ddd; }'
    '.print-collection h2 { font-size: 14px; margin: 12px 0 6px; }'
    '.print-collection table { width: 100%; border-collapse: collapse; }'
    '.print-collection th, .print-collection td { border: 1px solid #bbb; '
    'padding: 3px 5px; font-size: 11px; }'
    '.print-collection th { background: #f4f4f4; }'
)


def default_template_source(bo_code: str) -> Dict[str, str]:
    """把合成默认版式写成可编辑模板源（`{{ doc.<字段> }}` / `{{#each}}`）。

    与 `print_renderer.default_layout` 同源：字段顺序取自元数据白名单，
    区别仅是把取值替换为模板变量，供 fork-default 落成 draft（D-PR-16）。
    """
    obj = _meta_object(bo_code)
    if obj is None:
        raise PrintTemplateError('bo_not_found', '未知 BO: %s' % bo_code)
    variables = derive_variables(bo_code)
    fields = variables.get('fields') or {}
    number_field = str(getattr(getattr(obj, 'document_profile', None),
                               'number_field', '') or '')

    parts: List[str] = ['<div class="print-doc">',
                        '<header class="print-doc-header">',
                        '<h1>%s</h1>' % escape(str(getattr(obj, 'name', '') or bo_code))]
    if number_field and number_field in fields:
        parts.append('<p class="print-doc-no">编号：{{ doc.%s }}</p>' % number_field)
    parts.append('</header>')

    if fields:
        parts.append('<table class="print-doc-fields"><tbody>')
        for code, meta in fields.items():
            parts.append('<tr><th>%s</th><td>{{ doc.%s }}</td></tr>'
                         % (escape(str(meta.get('label') or code)), code))
        parts.append('</tbody></table>')

    for collection_code, collection in (variables.get('collections') or {}).items():
        inner_alias = str(collection.get('inner_alias') or '')
        child_fields = collection.get('fields') or {}
        if not inner_alias or not child_fields:
            continue
        parts.append('<section class="print-collection">')
        parts.append('<h2>%s</h2>' % escape(str(collection.get('label')
                                                 or collection_code)))
        parts.append('<table><thead><tr>')
        for code, meta in child_fields.items():
            parts.append('<th>%s</th>' % escape(str(meta.get('label') or code)))
        parts.append('</tr></thead><tbody>')
        parts.append('{{#each %s}}<tr>' % collection_code)
        for code in child_fields:
            parts.append('<td>{{ %s.%s }}</td>' % (inner_alias, code))
        parts.append('</tr>{{/each}}')
        parts.append('</tbody></table></section>')

    parts.append('</div>')
    html = ''.join(parts)
    errors, _warnings = validate_template(html, variables)
    if errors:
        raise PrintTemplateError('default_template_invalid',
                                 '默认版式生成未通过校验', 500, errors)
    return {'html': html, 'css': DEFAULT_TEMPLATE_CSS}


def _free_code(bo_code: str, type_code: str, base: str) -> str:
    """默认版式另存时避让已有模板族（同接入点内 code 唯一）。"""
    if repo.find_template(bo_code, type_code, base) is None:
        return base
    for index in range(2, 100):
        candidate = '%s_%d' % (base, index)
        if repo.find_template(bo_code, type_code, candidate) is None:
            return candidate
    raise PrintTemplateError('template_code_conflict',
                             '默认版式模板名已占满: %s' % base, 409)


def fork_default(bo_code: str, type_code: str = '', code: str = '',
                 name: str = '', created_by: str = 'system') -> Dict[str, Any]:
    """把合成默认版式另存为 draft（改动分叉点，D-PR-16）。"""
    obj = _meta_object(bo_code)
    if obj is None:
        raise PrintTemplateError('bo_not_found', '未知 BO: %s' % bo_code)
    source = default_template_source(bo_code)
    resolved_code = _free_code(bo_code, type_code, code or 'default')
    display_name = name or '%s 默认版式' % (getattr(obj, 'name', '') or bo_code)
    return create_draft(bo_code, resolved_code, display_name,
                        source['html'], css=source['css'],
                        type_code=type_code, created_by=created_by)