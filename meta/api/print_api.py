# -*- coding: utf-8 -*-
"""[打印平台] M4 HTTP 适配层（`/api/print/*`）。

依据: docs/specs/spec-print-platform-2026-11-15.md §8 / §10
职责:
  · 只做鉴权、入参整形、错误码映射；模板/渲染/归档逻辑全部在 M1-M3 服务层；
  · 打印类动作（printable / resolve / render / run / reprint / runs）判目标 BO `read`；
  · 模板与绑定管理判 `print_template:{create,update,delete}`（spec §10）；
  · 模板正文（html/css/variables）另需 `print_template:read`。

水印降级口径: 重打复用归档字节（D-PR-08 内容零漂移），P0 无 PDF 合成库，
REPRINT 只记 `print_runs`、不物理叠印，响应头 `X-Print-Watermark-Applied: false`
显式声明（spec §7.2）。
"""

import json
from urllib.parse import quote

from flask import Blueprint, Response, request

from meta.api._response_contract import (
    error_response, ok, ok_list, ok_message)
from meta.core.permission_gate import evaluate, evaluate_code
from meta.services import print_capability as capability
from meta.services import print_repository as repo
from meta.services import print_service
from meta.services import print_template_service as templates
from meta.services.auth_middleware import get_current_user, login_required

print_bp = Blueprint('print', __name__, url_prefix='/api/print')

TEMPLATE_READ = 'print_template:read'
MANAGE_ACTIONS = ('create', 'update', 'delete')


# ------------------------------------------------------------------ helpers

def _payload() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _json_object(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw or '{}'))
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _fail(exc) -> Response:
    return error_response(exc.message, error_code=exc.code, status=exc.status,
                          errors=exc.errors or None)


def _forbidden(required: str):
    return error_response('您没有执行该操作的权限', error_code='forbidden', status=403,
                          details={'required_permission': required})


def _require_bo_read(bo_code: str):
    if evaluate(get_current_user(), bo_code, 'crud_read').allowed:
        return None
    return _forbidden('%s:read' % bo_code)


def _require_manage(action: str):
    code = 'print_template:%s' % action
    if evaluate_code(get_current_user(), code):
        return None
    return _forbidden(code)


def _can_read_template_content() -> bool:
    return evaluate_code(get_current_user(), TEMPLATE_READ)


def _template_view(row: dict, with_content: bool = False) -> dict:
    view = {
        'id': int(row['id']),
        'bo_code': row['bo_code'],
        'type_code': row.get('type_code') or '',
        'code': row['code'],
        'name': row['name'],
        'version': int(row.get('version') or 0),
        'status': row.get('status'),
        'paper_size': row.get('paper_size'),
        'orientation': row.get('orientation'),
        'margin_top': float(row.get('margin_top') or 0),
        'margin_right': float(row.get('margin_right') or 0),
        'margin_bottom': float(row.get('margin_bottom') or 0),
        'margin_left': float(row.get('margin_left') or 0),
        'scope_type': row.get('scope_type'),
        'scope_id': row.get('scope_id'),
        'effective_from': row.get('effective_from'),
        'effective_to': row.get('effective_to'),
        'created_by': row.get('created_by'),
        'created_at': row.get('created_at'),
        'published_at': row.get('published_at'),
        'archived_at': row.get('archived_at'),
    }
    if with_content:
        view['html'] = row.get('html') or ''
        view['css'] = row.get('css') or ''
        view['variables'] = _json_object(row.get('variables_json'))
    return view


def _binding_view(row: dict) -> dict:
    return {
        'id': int(row['id']),
        'bo_code': row['bo_code'],
        'type_code': row.get('type_code') or '',
        'template_id': int(row['template_id']),
        'condition': _json_object(row.get('condition_json')),
        'priority': int(row.get('priority') or 0),
        'is_default': int(row.get('is_default') or 0),
        'is_active': int(row.get('is_active') or 0),
        'scope_type': row.get('scope_type'),
        'scope_id': row.get('scope_id'),
        'created_at': row.get('created_at'),
        'updated_at': row.get('updated_at'),
    }


def _run_view(row: dict) -> dict:
    return {
        'id': int(row['id']),
        'bo_code': row['bo_code'],
        'type_code': row.get('type_code') or '',
        'doc_id': row.get('doc_id'),
        'doc_no': row.get('doc_no'),
        'doc_rev': row.get('doc_rev'),
        'template_id': int(row.get('template_id') or 0),
        'template_version': int(row.get('template_version') or 0),
        'trigger': row.get('trigger'),
        'is_formal': int(row.get('is_formal') or 0),
        'is_reprint': int(row.get('is_reprint') or 0),
        'print_seq': int(row.get('print_seq') or 0),
        'watermark': row.get('watermark'),
        'status': row.get('status'),
        'attachment_id': row.get('attachment_id'),
        'payload_hash': row.get('payload_hash'),
        'job_run_id': row.get('job_run_id'),
        'error_code': row.get('error_code'),
        'error_message': row.get('error_message'),
        'operator_id': row.get('operator_id'),
        'operator_name': row.get('operator_name'),
        'created_at': row.get('created_at'),
        'finished_at': row.get('finished_at'),
    }


def _pdf_stream(pdf: bytes, filename: str, headers: dict = None) -> Response:
    response = Response(pdf, status=200, mimetype='application/pdf')
    response.headers['Content-Disposition'] = (
        'inline; filename="print.pdf"; filename*=UTF-8\'\'%s' % quote(filename))
    response.headers['Cache-Control'] = 'no-store'
    for key, value in (headers or {}).items():
        response.headers[key] = str(value)
    return response


def _pdf_filename(doc_no: str, suffix: str = '') -> str:
    name = (doc_no or 'print').strip() or 'print'
    return '%s%s.pdf' % (name.replace('/', '_'), suffix)


def _validate_condition(bo_code: str, condition: dict):
    """条件键必须是该 BO 白名单字段（元数据即真源）。"""
    if not condition:
        return []
    fields = templates.derive_variables(bo_code).get('fields') or {}
    return [{'code': 'unknown_condition_field', 'field': key,
             'message': '条件字段不在 BO 白名单内: %s' % key}
            for key in condition if key not in fields]


def _merge_binding(row: dict, payload: dict) -> dict:
    condition = payload.get('condition')
    if condition is None:
        condition = _json_object(row.get('condition_json'))
    return {
        'bo_code': row['bo_code'],
        'type_code': payload.get('type_code', row.get('type_code') or ''),
        'template_id': int(payload.get('template_id', row['template_id'])),
        'condition_json': json.dumps(condition, ensure_ascii=False, sort_keys=True),
        'condition': condition,
        'priority': int(payload.get('priority', row.get('priority') or 100)),
        'is_default': int(payload.get('is_default', row.get('is_default') or 0)),
        'is_active': int(payload.get('is_active', row.get('is_active', 1))),
        'scope_type': payload.get('scope_type', row.get('scope_type') or 'system'),
        'scope_id': payload.get('scope_id', row.get('scope_id')),
    }


def _assert_binding_sources(bo_code: str, template_id: int, type_code: str,
                            condition: dict):
    """绑定必须指向同 BO 模板，且类型 / 条件字段在真源内。"""
    errors = _validate_condition(bo_code, condition)
    template = repo.get_template(int(template_id))
    if template is None:
        errors.append({'code': 'template_not_found',
                       'message': '绑定的模板不存在: %s' % template_id})
    else:
        if template['bo_code'] != bo_code:
            errors.append({'code': 'template_bo_mismatch',
                           'message': '模板属于 %s，不能绑定到 %s'
                                      % (template['bo_code'], bo_code)})
        template_type = template.get('type_code') or ''
        if template_type and type_code and template_type != type_code:
            errors.append({'code': 'template_type_mismatch',
                           'message': '模板类型 %s 与绑定类型 %s 不一致'
                                      % (template_type, type_code)})
    return errors


# ------------------------------------------------------------------ 可打印清单

@print_bp.route('/printable', methods=['GET'])
@login_required
def printable_list():
    """可打印接入点 × 可读 BO；附带该接入点的有效绑定摘要。"""
    user = get_current_user()
    grouped = {}
    items = []
    for raw in capability.list_printable_bo_types():
        bo_code = raw['bo_code']
        if not evaluate(user, bo_code, 'crud_read').allowed:
            continue
        if bo_code not in grouped:
            grouped[bo_code] = repo.list_bindings(bo_code)
        item = dict(raw)
        matched = [b for b in grouped[bo_code]
                   if (b.get('type_code') or '') in ('', raw['type_code'])]
        item['bindings'] = [_binding_view(b) for b in matched]
        item['binding_count'] = len(matched)
        items.append(item)
    return ok_list(items, total=len(items), page=1, page_size=len(items) or 1)


# ------------------------------------------------------------------ 模板

@print_bp.route('/templates', methods=['GET'])
@login_required
def template_list():
    bo_code = request.args.get('bo_code') or None
    type_code = request.args.get('type_code')
    status = request.args.get('status') or None
    rows = repo.list_templates(bo_code=bo_code, type_code=type_code, status=status)

    user = get_current_user()
    with_content = _can_read_template_content()
    items = [_template_view(row, with_content=with_content)
             for row in rows if evaluate(user, row['bo_code'], 'crud_read').allowed]
    total = len(items)
    page = request.args.get('page', 1, type=int)
    page_size = max(1, request.args.get('page_size', 50, type=int))
    start = (max(page, 1) - 1) * page_size
    return ok_list(items[start:start + page_size], total=total,
                   page=max(page, 1), page_size=page_size)


@print_bp.route('/templates/<int:template_id>', methods=['GET'])
@login_required
def template_detail(template_id):
    row = repo.get_template(template_id)
    if row is None:
        return error_response('模板不存在: %s' % template_id,
                              error_code='template_not_found', status=404)
    guard = _require_bo_read(row['bo_code'])
    if guard:
        return guard
    return ok(_template_view(row, with_content=_can_read_template_content()))


@print_bp.route('/templates', methods=['POST'])
@login_required
def template_create():
    guard = _require_manage('create')
    if guard:
        return guard
    payload = _payload()
    missing = [key for key in ('bo_code', 'code', 'name', 'html')
               if not str(payload.get(key) or '').strip()]
    if missing:
        return error_response('缺少必填字段', error_code='data_invalid', status=400,
                              errors=[{'code': 'required', 'field': key,
                                       'message': '%s 必填' % key} for key in missing])
    try:
        result = templates.create_draft(
            str(payload['bo_code']), str(payload['code']), str(payload['name']),
            str(payload['html']), css=str(payload.get('css') or ''),
            type_code=str(payload.get('type_code') or ''),
            paper_size=str(payload.get('paper_size') or 'A4'),
            orientation=str(payload.get('orientation') or 'portrait'),
            margin_top=float(payload.get('margin_top', 10)),
            margin_right=float(payload.get('margin_right', 10)),
            margin_bottom=float(payload.get('margin_bottom', 10)),
            margin_left=float(payload.get('margin_left', 10)),
            scope_type=str(payload.get('scope_type') or 'system'),
            scope_id=payload.get('scope_id'),
            effective_from=payload.get('effective_from'),
            effective_to=payload.get('effective_to'),
            created_by=str((get_current_user() or {}).get('username') or 'system'))
    except templates.PrintTemplateError as exc:
        return _fail(exc)
    return ok({'template': _template_view(result['template'], with_content=True),
               'errors': result['errors'], 'warnings': result['warnings']})


@print_bp.route('/templates/<int:template_id>', methods=['PUT'])
@login_required
def template_update(template_id):
    guard = _require_manage('update')
    if guard:
        return guard
    row = repo.get_template(template_id)
    if row is None:
        return error_response('模板不存在: %s' % template_id,
                              error_code='template_not_found', status=404)
    payload = _payload()
    try:
        result = templates.update_draft(
            template_id,
            name=str(payload.get('name') or row['name']),
            html=str(payload['html'] if 'html' in payload else row.get('html') or ''),
            css=str(payload['css'] if 'css' in payload else row.get('css') or ''),
            paper_size=str(payload.get('paper_size') or row.get('paper_size') or 'A4'),
            orientation=str(payload.get('orientation')
                            or row.get('orientation') or 'portrait'),
            margin_top=float(payload.get('margin_top', row.get('margin_top', 10))),
            margin_right=float(payload.get('margin_right', row.get('margin_right', 10))),
            margin_bottom=float(payload.get('margin_bottom', row.get('margin_bottom', 10))),
            margin_left=float(payload.get('margin_left', row.get('margin_left', 10))),
            effective_from=payload.get('effective_from', row.get('effective_from')),
            effective_to=payload.get('effective_to', row.get('effective_to')))
    except templates.PrintTemplateError as exc:
        return _fail(exc)
    return ok({'template': _template_view(result['template'], with_content=True),
               'errors': result['errors'], 'warnings': result['warnings']})


@print_bp.route('/templates/<int:template_id>/validate', methods=['POST'])
@login_required
def template_validate(template_id):
    guard = _require_manage('update')
    if guard:
        return guard
    row = repo.get_template(template_id)
    if row is None:
        return error_response('模板不存在: %s' % template_id,
                              error_code='template_not_found', status=404)
    payload = _payload()
    html = payload['html'] if 'html' in payload else row.get('html') or ''
    css = payload['css'] if 'css' in payload else row.get('css') or ''
    clean_html, html_warnings = templates.sanitize_html(html)
    clean_css, css_warnings = templates.sanitize_css(css)
    variables = templates.derive_variables(row['bo_code'])
    errors, warnings = templates.validate_template(clean_html, variables)
    errors.extend(templates.validate_css(clean_css))
    return ok({'valid': not errors, 'errors': errors,
               'warnings': warnings + html_warnings + css_warnings})


@print_bp.route('/templates/<int:template_id>/publish', methods=['POST'])
@login_required
def template_publish(template_id):
    guard = _require_manage('update')
    if guard:
        return guard
    try:
        result = templates.publish_template(template_id)
    except templates.PrintTemplateError as exc:
        return _fail(exc)
    return ok({'template': _template_view(result['template'], with_content=True),
               'warnings': result['warnings']})


@print_bp.route('/templates/<int:template_id>/fork-default', methods=['POST'])
@login_required
def template_fork_default(template_id):
    """把合成默认版式另存为 draft；`id=0` 时由 body 提供 `bo_code/type_code`。"""
    guard = _require_manage('create')
    if guard:
        return guard
    payload = _payload()
    bo_code = str(payload.get('bo_code') or '')
    type_code = str(payload.get('type_code') or '')
    if template_id:
        source = repo.get_template(template_id)
        if source is None:
            return error_response('模板不存在: %s' % template_id,
                                  error_code='template_not_found', status=404)
        bo_code = bo_code or source['bo_code']
        type_code = payload.get('type_code', source.get('type_code') or '')
    if not bo_code:
        return error_response('bo_code 必填', error_code='data_invalid', status=400)
    try:
        row = templates.fork_default(
            bo_code, type_code=str(type_code or ''),
            code=str(payload.get('code') or ''), name=str(payload.get('name') or ''),
            created_by=str((get_current_user() or {}).get('username') or 'system'))
    except templates.PrintTemplateError as exc:
        return _fail(exc)
    return ok({'template': _template_view(row, with_content=True)})


# ------------------------------------------------------------------ 绑定

@print_bp.route('/bindings', methods=['GET'])
@login_required
def binding_list():
    bo_code = str(request.args.get('bo_code') or '')
    if not bo_code:
        return error_response('bo_code 必填', error_code='data_invalid', status=400)
    guard = _require_bo_read(bo_code)
    if guard:
        return guard
    type_code = request.args.get('type_code')
    rows = repo.list_bindings(bo_code, type_code=type_code)
    items = [_binding_view(row) for row in rows]
    return ok_list(items, total=len(items), page=1, page_size=len(items) or 1)


@print_bp.route('/bindings', methods=['POST'])
@login_required
def binding_create():
    guard = _require_manage('create')
    if guard:
        return guard
    payload = _payload()
    bo_code = str(payload.get('bo_code') or '')
    if not bo_code or not payload.get('template_id'):
        return error_response('bo_code 与 template_id 必填',
                              error_code='data_invalid', status=400)
    merged = _merge_binding({'bo_code': bo_code, 'type_code': '',
                             'template_id': 0, 'condition_json': '{}',
                             'priority': 100, 'is_default': 0, 'is_active': 1,
                             'scope_type': 'system', 'scope_id': None}, payload)
    errors = _assert_binding_sources(bo_code, merged['template_id'],
                                     merged['type_code'], merged['condition'])
    if errors:
        return error_response('绑定校验未通过', error_code='data_invalid',
                              status=400, errors=errors)
    binding_id = repo.insert_binding(merged)
    return ok({'binding': _binding_view(repo.get_binding(binding_id))})


@print_bp.route('/bindings/<int:binding_id>', methods=['PUT'])
@login_required
def binding_update(binding_id):
    guard = _require_manage('update')
    if guard:
        return guard
    row = repo.get_binding(binding_id)
    if row is None:
        return error_response('绑定不存在: %s' % binding_id,
                              error_code='binding_not_found', status=404)
    merged = _merge_binding(row, _payload())
    errors = _assert_binding_sources(row['bo_code'], merged['template_id'],
                                     merged['type_code'], merged['condition'])
    if errors:
        return error_response('绑定校验未通过', error_code='data_invalid',
                              status=400, errors=errors)
    repo.update_binding(binding_id, merged)
    return ok({'binding': _binding_view(repo.get_binding(binding_id))})


@print_bp.route('/bindings/<int:binding_id>', methods=['DELETE'])
@login_required
def binding_delete(binding_id):
    guard = _require_manage('delete')
    if guard:
        return guard
    if repo.get_binding(binding_id) is None:
        return error_response('绑定不存在: %s' % binding_id,
                              error_code='binding_not_found', status=404)
    repo.deactivate_binding(binding_id)
    return ok_message('绑定已下架', data={'binding_id': binding_id})


# ------------------------------------------------------------------ 解析 / 渲染 / 打印

@print_bp.route('/resolve', methods=['POST'])
@login_required
def resolve():
    payload = _payload()
    bo_code = str(payload.get('bo_code') or '')
    doc_id = str(payload.get('doc_id') or '')
    type_code = str(payload.get('type_code') or '')
    if not bo_code or not doc_id:
        return error_response('bo_code 与 doc_id 必填',
                              error_code='data_invalid', status=400)
    guard = _require_bo_read(bo_code)
    if guard:
        return guard
    try:
        context = print_service.load_document(bo_code, doc_id)
        resolved = print_service.resolve_template(
            bo_code, type_code, context['values'], meta_obj=context['meta'])
    except print_service.PrintError as exc:
        return _fail(exc)
    template = resolved['template']
    return ok({
        'doc_no': context['doc_no'],
        'template': _template_view(template) if template else None,
        'binding': _binding_view(resolved['binding']) if resolved.get('binding') else None,
        'reason': resolved['reason'],
        'candidates': resolved['candidates'],
        'rejected': resolved.get('rejected') or [],
        'uses_default_layout': template is None,
    })


@print_bp.route('/render', methods=['POST'])
@login_required
def render():
    payload = _payload()
    bo_code = str(payload.get('bo_code') or '')
    doc_id = str(payload.get('doc_id') or '')
    if not bo_code or not doc_id:
        return error_response('bo_code 与 doc_id 必填',
                              error_code='data_invalid', status=400)
    mode = str(payload.get('mode') or 'preview')
    if mode != 'preview':
        return error_response('该端点只接受 mode=preview；正式打印走 /run',
                              error_code='invalid_mode', status=400)
    guard = _require_bo_read(bo_code)
    if guard:
        return guard
    try:
        result = print_service.render_document(
            bo_code, str(payload.get('type_code') or ''), doc_id,
            template_id=payload.get('template_id'), mode='preview',
            engine=payload.get('engine'))
    except print_service.PrintError as exc:
        return _fail(exc)
    return _pdf_stream(result['pdf'], _pdf_filename(result['doc_no'], '_preview'),
                       headers={'X-Print-Template-Id': result['template_id'],
                                'X-Print-Template-Version': result['template_version'],
                                'X-Print-Watermark': result['watermark'],
                                'X-Print-Payload-Hash': result['payload_hash']})


@print_bp.route('/run', methods=['POST'])
@login_required
def run():
    payload = _payload()
    bo_code = str(payload.get('bo_code') or '')
    doc_id = str(payload.get('doc_id') or '')
    if not bo_code or not doc_id:
        return error_response('bo_code 与 doc_id 必填',
                              error_code='data_invalid', status=400)
    trigger = str(payload.get('trigger') or 'print')
    if trigger not in print_service.ARCHIVE_TRIGGERS:
        return error_response('trigger 仅支持 print/download',
                              error_code='invalid_trigger', status=400)
    guard = _require_bo_read(bo_code)
    if guard:
        return guard
    try:
        result = print_service.print_document(
            bo_code, str(payload.get('type_code') or ''), doc_id,
            template_id=payload.get('template_id'), trigger=trigger,
            operator=get_current_user(), engine=payload.get('engine'),
            job_run_id=payload.get('job_run_id'))
    except print_service.PrintError as exc:
        return _fail(exc)
    return ok({'run': _run_view(result['run']),
               'attachment_id': result['attachment_id']})


@print_bp.route('/reprint', methods=['POST'])
@login_required
def reprint():
    payload = _payload()
    print_run_id = payload.get('print_run_id')
    if not print_run_id:
        return error_response('print_run_id 必填', error_code='data_invalid', status=400)
    source = repo.get_run(int(print_run_id))
    if source is None:
        return error_response('打印记录不存在: %s' % print_run_id,
                              error_code='run_not_found', status=404)
    guard = _require_bo_read(source['bo_code'])
    if guard:
        return guard
    try:
        result = print_service.reprint_document(int(print_run_id),
                                                operator=get_current_user())
    except print_service.PrintError as exc:
        return _fail(exc)
    return _pdf_stream(result['pdf'], _pdf_filename(source.get('doc_no'), '_reprint'),
                       headers={'X-Print-Run-Id': result['run']['id'],
                                'X-Print-Source-Run-Id': result['source_run_id'],
                                'X-Print-Watermark': result['watermark'],
                                'X-Print-Watermark-Applied':
                                    str(result['watermark_applied']).lower()})


@print_bp.route('/runs', methods=['GET'])
@login_required
def run_list():
    bo_code = str(request.args.get('bo_code') or '')
    if not bo_code:
        return error_response('bo_code 必填', error_code='data_invalid', status=400)
    guard = _require_bo_read(bo_code)
    if guard:
        return guard
    doc_id = request.args.get('doc_id')
    limit = min(max(request.args.get('limit', 50, type=int), 1), 200)
    offset = max(request.args.get('offset', 0, type=int), 0)
    rows = repo.list_runs(bo_code, doc_id=doc_id, limit=limit, offset=offset)
    items = [_run_view(row) for row in rows]
    return ok_list(items, total=offset + len(items),
                   page=offset // limit + 1, page_size=limit)