# -*- coding: utf-8 -*-
"""打印服务层（M3）：取数 → 选模板 → 渲染 → 归档 → 打印记录。

依据: docs/specs/spec-print-platform-2026-11-15.md §6 / §7 / D-PR-08 / D-PR-09 / D-PR-11 / D-PR-16
职责:
  · 只按 `(bo_code, type_code)` 取数并渲染，不做权限与 HTTP（M4）；
  · 模板绑定条件求值（`condition_json` 对单据字段等值匹配），按仓库返回顺序命中；
  · 未命中或未配置 → 合成默认版式（不落库、不建模板行）；
  · 非预览触发一律归档 PDF 到附件平台，`print_runs` 只追加；
  · 正式打印序号只从 `print_runs` 派生（D-PR-09），不写业务表。

约定:
  · `print_runs.template_id = 0 / template_version = 0` 表示「合成默认版式」；
  · `payload_hash` = sha256(规范取数 JSON + 模板 id/version)，用于防篡改追溯。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import BytesIO
from typing import Any, Callable, Dict, List, Optional

from meta.core.bo_engine import BOEngine
from meta.core.datasource import get_platform_data_source
from meta.core.query_builder import QueryBuilder
from meta.services import print_repository as repo
from meta.services import print_renderer as renderer
from meta.services.print_capability import is_printable
from meta.services.print_renderer import PrintRenderError
from meta.services.print_template_service import (
    _child_sections, _meta_object, _section_field)

#: 非正式状态（打印件需叠加 DRAFT 水印）
NON_FORMAL_STATES = frozenset({'draft', 'void', 'voided', 'cancelled', 'canceled'})

#: 可归档触发方式（预览不落 run / 不归档）
ARCHIVE_TRIGGERS = frozenset({'print', 'download', 'batch'})
PREVIEW_TRIGGER = 'preview'
RUN_TRIGGERS = ARCHIVE_TRIGGERS | {PREVIEW_TRIGGER}

_FILENAME_SAFE_RE = re.compile(r'[^0-9A-Za-z_.\-\u4e00-\u9fff]+')


class PrintError(Exception):
    """打印服务错误（code 与 status 供 API 层直接映射）。"""

    def __init__(self, code: str, message: str, status: int = 400,
                 errors: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.errors = errors or []


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ------------------------------------------------------------------ 取数

def _normalize_row(meta_obj: Any, row: Dict[str, Any]) -> Dict[str, Any]:
    """行数据统一按字段 id 归一（SELECT * 回来的是 db_column）。"""
    values: Dict[str, Any] = {}
    for field in getattr(meta_obj, 'fields', None) or []:
        code = str(getattr(field, 'id', '') or '')
        column = str(getattr(field, 'db_column', '') or '')
        if column and column in row:
            values[code] = row.get(column)
        elif code in row:
            values[code] = row.get(code)
    return values


def _value_by_name(meta_obj: Any, values: Dict[str, Any], name: str) -> Any:
    """按字段 id / db_column 命中取值（单据六件套声明可能是任一写法）。"""
    if not name:
        return None
    for field in getattr(meta_obj, 'fields', None) or []:
        if name in (getattr(field, 'id', ''), getattr(field, 'db_column', '')):
            return values.get(getattr(field, 'id', '') or name)
    return values.get(name)


def _parent_field(child_meta: Any, header_bo: str) -> str:
    """子表父键解析：hierarchy.parent_field → ui.relation → `<header>_id` 兜底。"""
    hierarchy = getattr(child_meta, 'hierarchy', None)
    declared = ''
    if isinstance(hierarchy, dict):
        declared = str(hierarchy.get('parent_field') or '')
    else:
        declared = str(getattr(hierarchy, 'parent_field', '') or '')
    if declared:
        return declared

    for field in getattr(child_meta, 'fields', None) or []:
        relation = getattr(getattr(field, 'ui', None), 'relation', '')
        if relation == header_bo:
            return str(getattr(field, 'id', '') or '')

    fallback = '{0}_id'.format(header_bo)
    for field in getattr(child_meta, 'fields', None) or []:
        if fallback in (getattr(field, 'id', ''), getattr(field, 'db_column', '')):
            return str(getattr(field, 'id', '') or '')
    return ''


def load_document(bo_code: str, doc_id: str) -> Dict[str, Any]:
    """取单据头 + child_sections 子表行（按字段 id 归一）。"""
    meta_obj = _meta_object(bo_code)
    if meta_obj is None:
        raise PrintError('bo_not_found', '业务对象不存在: %s' % bo_code, 404)

    row = BOEngine(meta_obj).get_record(doc_id)
    if not row:
        raise PrintError('doc_not_found', '单据不存在: %s/%s' % (bo_code, doc_id), 404)

    values = _normalize_row(meta_obj, row)
    collections: Dict[str, List[Dict[str, Any]]] = {}
    data_source = get_platform_data_source()

    for section in _child_sections(meta_obj):
        child_code = _section_field(section, 'child_object')
        child_meta = _meta_object(child_code)
        if child_meta is None:
            continue
        parent_field = _parent_field(child_meta, bo_code)
        if not parent_field:
            collections[child_code] = []
            continue
        builder = QueryBuilder(data_source, child_meta).where_eq(parent_field, doc_id)
        if any(str(getattr(f, 'id', '')) == 'id' for f in child_meta.fields or []):
            builder.order_by('id', 'asc')
        collections[child_code] = [_normalize_row(child_meta, child)
                                   for child in (builder.execute() or [])]

    profile = getattr(meta_obj, 'document_profile', None)
    number_field = str(getattr(profile, 'number_field', '') or '')
    state_field = str(getattr(profile, 'state_field', '') or '')
    doc_no = _value_by_name(meta_obj, values, number_field) if number_field else values.get('code')
    state = _value_by_name(meta_obj, values, state_field) if state_field else None
    doc_rev = (values.get('revised_at') or values.get('updated_at')
               or values.get('version') or '')

    return {
        'bo_code': bo_code,
        'meta': meta_obj,
        'values': values,
        'collections': collections,
        'doc_no': str(doc_no or ''),
        'doc_rev': str(doc_rev or ''),
        'state': str(state or ''),
        'has_numbering': bool(getattr(meta_obj, 'numbering', None)),
    }


# ------------------------------------------------------------------ 模板绑定

def _parse_condition(raw: Any) -> Dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw))
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _condition_matches(condition: Dict[str, Any], meta_obj: Any,
                       values: Dict[str, Any]) -> bool:
    for name, expected in condition.items():
        actual = _value_by_name(meta_obj, values, str(name))
        if isinstance(expected, (list, tuple)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _assert_template_usable(template: Dict[str, Any], allow_draft: bool = False) -> None:
    status = str(template.get('status') or '')
    if status == 'stale':
        raise PrintError('template_stale',
                         '模板变量白名单已漂移，请重建模板: %s' % template.get('code'), 409)
    if status == 'active':
        return
    if allow_draft and status == 'draft':
        return
    raise PrintError('template_not_active',
                     '模板未发布（status=%s）: %s' % (status, template.get('code')), 409)


def resolve_template(bo_code: str, type_code: str,
                     values: Optional[Dict[str, Any]] = None,
                     meta_obj: Any = None, scope_type: Optional[str] = None,
                     scope_id: Optional[str] = None) -> Dict[str, Any]:
    """候选绑定按优先级求值；全不命中返回 ``template=None``（走默认版式）。

    Returns: ``{'template','binding','reason','candidates'}``；`reason` 供
    `/api/print/resolve` 排障（如 ``binding:3 condition:{"status":"draft"}``）。
    """
    values = values or {}
    meta_obj = meta_obj or _meta_object(bo_code)
    candidates = repo.candidate_bindings(bo_code, type_code or '',
                                         scope_type=scope_type, scope_id=scope_id)
    rejected: List[Dict[str, Any]] = []
    for binding in candidates:
        condition = _parse_condition(binding.get('condition_json'))
        if not _condition_matches(condition, meta_obj, values):
            rejected.append({'binding_id': binding.get('id'),
                             'condition': condition,
                             'reason': 'condition_unmatched'})
            continue
        template = repo.get_template(int(binding['template_id']))
        if template is None:
            raise PrintError('template_missing',
                             '绑定指向的模板不存在: binding=%s' % binding.get('id'), 409)
        _assert_template_usable(template)
        reason = 'binding:{0} priority:{1}'.format(binding.get('id'), binding.get('priority'))
        if condition:
            reason += ' condition:{0}'.format(json.dumps(condition, ensure_ascii=False,
                                                         sort_keys=True))
        return {'template': template, 'binding': binding, 'reason': reason,
                'candidates': len(candidates)}
    return {'template': None, 'binding': None, 'candidates': len(candidates),
            'reason': 'conditions_unmatched' if candidates else 'no_binding',
            'rejected': rejected}


# ------------------------------------------------------------------ 渲染

def _template_variables(template: Dict[str, Any]) -> Dict[str, Any]:
    raw = template.get('variables_json')
    if not raw:
        raise PrintError('template_invalid', '模板缺少发布期冻结的变量快照', 409)
    try:
        variables = json.loads(raw)
    except (ValueError, TypeError):
        raise PrintError('template_invalid', '模板变量快照不是合法 JSON', 409) from None
    return variables if isinstance(variables, dict) else {}


def _render_data(values: Dict[str, Any], collections: Dict[str, List[Dict[str, Any]]],
                 variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    variables = variables or {}
    data: Dict[str, Any] = {'root': 'doc', 'doc': values, 'collections': {}}
    for code, rows in (collections or {}).items():
        data['collections'][code] = rows
        collection = (variables.get('collections') or {}).get(code)
        alias = (collection or {}).get('inner_alias')
        if alias:
            data['collections'][alias] = rows
    return data


def payload_hash(values: Dict[str, Any],
                 collections: Dict[str, List[Dict[str, Any]]],
                 template_id: int, template_version: int) -> str:
    """入参摘要：规范取数 JSON + 模板 id/version（与渲染时刻无关，可复算）。"""
    canonical = json.dumps({
        'doc': values,
        'collections': collections,
        'template_id': int(template_id),
        'template_version': int(template_version),
    }, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _formal_flags(context: Dict[str, Any]) -> Dict[str, Any]:
    state = (context.get('state') or '').lower()
    doc_no = (context.get('doc_no') or '').strip()
    only_numbered = bool(context.get('has_numbering'))
    is_formal = 0
    if state not in NON_FORMAL_STATES and (doc_no or not only_numbered):
        is_formal = 1
    watermark = renderer.WATERMARK_NONE if is_formal else renderer.WATERMARK_DRAFT
    return {'is_formal': is_formal, 'watermark': watermark}


def render_document(bo_code: str, type_code: str, doc_id: str, *,
                    template_id: Optional[int] = None,
                    mode: str = PREVIEW_TRIGGER,
                    engine: Optional[str] = None,
                    template: Optional[Dict[str, Any]] = None,
                    context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """渲染一份 PDF；预览不落 run。返回 pdf 字节 + 追溯信息。"""
    if mode not in RUN_TRIGGERS:
        raise PrintError('invalid_trigger', '非法触发方式: %s' % mode)
    if not is_printable(bo_code, type_code or None):
        raise PrintError('bo_not_printable',
                         '该单据类型不可打印: %s/%s' % (bo_code, type_code or '-'), 400)

    context = context or load_document(bo_code, doc_id)
    meta_obj = context['meta']

    if template is None and template_id is not None:
        template = repo.get_template(int(template_id))
        if template is None:
            raise PrintError('template_not_found', '模板不存在: %s' % template_id, 404)
        _assert_template_usable(template, allow_draft=(mode == PREVIEW_TRIGGER))
    if template is None and template_id is None:
        template = resolve_template(bo_code, type_code, context['values'],
                                    meta_obj=meta_obj).get('template')

    variables = _template_variables(template) if template else {}
    data = _render_data(context['values'], context['collections'], variables)

    if template:
        body = renderer.render_template(template.get('html') or '', data, variables)
        css = template.get('css') or ''
        paper = {'paper_size': template.get('paper_size') or 'A4',
                 'orientation': template.get('orientation') or 'portrait',
                 'margin_top': template.get('margin_top', 10),
                 'margin_right': template.get('margin_right', 10),
                 'margin_bottom': template.get('margin_bottom', 10),
                 'margin_left': template.get('margin_left', 10)}
        template_id_value = int(template.get('id') or 0)
        template_version = int(template.get('version') or 0)
    else:
        body = renderer.default_layout(meta_obj, context['values'],
                                       context['collections'], doc_no=context['doc_no'])
        css = ''
        paper = {}
        template_id_value = 0
        template_version = 0

    flags = _formal_flags(context)
    watermark = renderer.WATERMARK_PREVIEW if mode == PREVIEW_TRIGGER else flags['watermark']
    title = '{0} {1}'.format(getattr(meta_obj, 'name', '') or bo_code, context['doc_no'])
    html = renderer.build_document(body, css=css, title=title,
                                   watermark=watermark, **paper)
    pdf = renderer.render_pdf(html, engine=engine)

    return {
        'pdf': pdf,
        'html': html,
        'context': context,
        'template': template,
        'template_id': template_id_value,
        'template_version': template_version,
        'variables': variables,
        'is_formal': flags['is_formal'],
        'watermark': watermark,
        'payload_hash': payload_hash(context['values'], context['collections'],
                                     template_id_value, template_version),
        'doc_no': context['doc_no'],
        'doc_rev': context['doc_rev'],
    }


# ------------------------------------------------------------------ 归档

def _normalize_operator(operator: Any) -> Dict[str, Any]:
    user = dict(operator) if isinstance(operator, dict) else {}
    if isinstance(operator, str) and operator:
        user = {'id': operator}
    user_id = str(user.get('id') or user.get('user_id') or 'system')
    user.setdefault('id', user_id)
    user.setdefault('user_id', user_id)
    user.setdefault('user_name', str(user.get('name') or user_id))
    return user


def _archive_name(context: Dict[str, Any], template: Optional[Dict[str, Any]],
                  print_seq: int, run_id: int) -> str:
    doc_no = (context.get('doc_no') or '').strip() or context.get('bo_code') or 'doc'
    code = (template or {}).get('code') or 'default'
    version = int((template or {}).get('version') or 0)
    suffix = 'seq{0}'.format(print_seq) if print_seq else 'run{0}'.format(run_id)
    name = '{0}_{1}_v{2}_{3}.pdf'.format(doc_no, code, version, suffix)
    return _FILENAME_SAFE_RE.sub('_', name)


def _archive_pdf(pdf: bytes, run_id: int, file_name: str,
                 operator: Dict[str, Any]) -> int:
    """默认归档：走附件平台（唯一字节真源），挂到 `print_run`。

    归档件属打印子系统账本：上传走系统身份，避免普通打印人被
    `print_run:update` 拦截；真实操作人只落在 `print_runs.operator_*`。
    """
    from werkzeug.datastructures import FileStorage
    from meta.services import attachment_service

    archive_user = {'id': 'system', 'user_id': 'system',
                    'user_name': 'print-subsystem', 'is_admin': True}
    file_storage = FileStorage(stream=BytesIO(pdf), filename=file_name,
                               content_type='application/pdf')
    result = attachment_service.upload_and_link(
        file_storage, 'print_run', run_id,
        link_role='primary', category='other', is_primary=True,
        display_name=file_name, user=archive_user)
    return int((result.get('attachment') or {}).get('id'))


ArchiveWriter = Callable[[bytes, int, str, Dict[str, Any]], int]


def print_document(bo_code: str, type_code: str, doc_id: str, *,
                   template_id: Optional[int] = None,
                   trigger: str = 'print',
                   operator: Any = None,
                   engine: Optional[str] = None,
                   writer: Optional[ArchiveWriter] = None,
                   job_run_id: Optional[str] = None) -> Dict[str, Any]:
    """非预览触发：渲染 → 归档 → 写 `print_runs`；失败也留 run 记录。"""
    if trigger not in ARCHIVE_TRIGGERS:
        raise PrintError('invalid_trigger', '非法归档触发方式: %s' % trigger)

    user = _normalize_operator(operator)
    context = load_document(bo_code, doc_id)
    resolved = resolve_template(bo_code, type_code, context['values'],
                                meta_obj=context['meta'])
    template = resolved['template']
    if template_id is not None:
        template = repo.get_template(int(template_id))
        if template is None:
            raise PrintError('template_not_found', '模板不存在: %s' % template_id, 404)
        _assert_template_usable(template)

    flags = _formal_flags(context)
    print_seq = repo.next_print_seq(bo_code, doc_id) if flags['is_formal'] else 0
    run_id = repo.insert_run({
        'bo_code': bo_code,
        'type_code': type_code or '',
        'doc_id': doc_id,
        'doc_no': context['doc_no'] or None,
        'doc_rev': context['doc_rev'] or None,
        'template_id': int((template or {}).get('id') or 0),
        'template_version': int((template or {}).get('version') or 0),
        'trigger': trigger,
        'is_formal': flags['is_formal'],
        'is_reprint': 0,
        'print_seq': print_seq,
        'watermark': flags['watermark'],
        'job_run_id': job_run_id,
        'status': 'running',
        'operator_id': user['id'],
        'operator_name': user['user_name'],
        'created_at': _now(),
    })

    try:
        rendered = render_document(bo_code, type_code, doc_id, mode=trigger,
                                   engine=engine, template=template,
                                   context=context)
        file_name = _archive_name(context, template, print_seq, run_id)
        attachment_id = (writer or _archive_pdf)(rendered['pdf'], run_id,
                                                 file_name, user)
        repo.finish_run(run_id, 'succeeded', attachment_id=attachment_id,
                        payload_hash=rendered['payload_hash'])
    except Exception as exc:
        code = getattr(exc, 'code', None) or 'print_failed'
        message = getattr(exc, 'message', None) or str(exc)
        repo.finish_run(run_id, 'failed', error_code=code, error_message=message[:500])
        if isinstance(exc, PrintError):
            raise
        if isinstance(exc, PrintRenderError):
            raise PrintError(exc.code, exc.message, exc.status, exc.errors) from exc
        raise PrintError(code, '打印失败: %s' % message, 500) from exc

    return {'run': repo.get_run(run_id), 'template': template,
            'attachment_id': attachment_id}


# ------------------------------------------------------------------ 重打

#: REPRINT 水印是否物理叠加进 PDF。P0 无 PDF 合成库，只记 run 不叠印（见 spec §7.2）。
REPRINT_WATERMARK_APPLIED = False


def _read_archived(attachment_id: int) -> bytes:
    """读取归档件字节：归档属打印子系统账本，走系统身份（BO read 已在 API 校验）。"""
    from meta.services import attachment_service

    _row, path = attachment_service.open_content(
        attachment_id, user={'id': 'system', 'user_id': 'system',
                             'user_name': 'print-subsystem', 'is_admin': True})
    with open(path, 'rb') as handle:
        return handle.read()


def reprint_document(print_run_id: int, operator: Any = None, *,
                     reader: Optional[Callable[[int], bytes]] = None) -> Dict[str, Any]:
    """重打：复用原归档字节（内容零漂移），只追加一条 `reprint` run。

    D-PR-08：不重渲染、不覆盖归档字节；`print_seq` 沿用原序号（D-PR-06
    重打不消耗新凭证序号）。无 PDF 叠加库时 REPRINT 水印只落在 run 记录。
    """
    source = repo.get_run(int(print_run_id))
    if source is None:
        raise PrintError('run_not_found', '打印记录不存在: %s' % print_run_id, 404)
    if source.get('status') != 'succeeded' or not source.get('attachment_id'):
        raise PrintError('run_not_archived', '该打印记录没有归档件，无法重打', 409)

    attachment_id = int(source['attachment_id'])
    pdf = (reader or _read_archived)(attachment_id)
    user = _normalize_operator(operator)

    run_id = repo.insert_run({
        'bo_code': source['bo_code'],
        'type_code': source.get('type_code') or '',
        'doc_id': source['doc_id'],
        'doc_no': source.get('doc_no'),
        'doc_rev': source.get('doc_rev'),
        'template_id': int(source.get('template_id') or 0),
        'template_version': int(source.get('template_version') or 0),
        'trigger': 'reprint',
        'is_formal': int(source.get('is_formal') or 0),
        'is_reprint': 1,
        'print_seq': int(source.get('print_seq') or 0),
        'watermark': 'REPRINT',
        'status': 'running',
        'operator_id': user['id'],
        'operator_name': user['user_name'],
        'created_at': _now(),
    })
    try:
        repo.finish_run(run_id, 'succeeded', attachment_id=attachment_id,
                        payload_hash=source.get('payload_hash'))
    except Exception as exc:
        code = getattr(exc, 'code', None) or 'print_failed'
        repo.finish_run(run_id, 'failed', error_code=code,
                        error_message=str(getattr(exc, 'message', exc))[:500])
        raise PrintError(code, '重打失败: %s' % str(getattr(exc, 'message', exc)), 500) from exc

    return {'run': repo.get_run(run_id), 'pdf': pdf,
            'source_run_id': int(source['id']), 'attachment_id': attachment_id,
            'watermark': 'REPRINT', 'watermark_applied': REPRINT_WATERMARK_APPLIED}


# ------------------------------------------------------------------ 批量 (M5)

#: 单批上限 / 并发（spec §9；超限直接拒单，不排队膨胀）
MAX_BATCH_SIZE = 200
DEFAULT_BATCH_CONCURRENCY = 2


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def batch_limit() -> int:
    """单批上限：`PRINT_MAX_BATCH`（默认 200）。"""
    return _positive_int_env('PRINT_MAX_BATCH', MAX_BATCH_SIZE)


def batch_print_documents(bo_code: str, type_code: str, doc_ids: List[Any], *,
                          template_id: Optional[int] = None,
                          operator: Any = None,
                          job_run_id: Any = None,
                          progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
                          should_cancel: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
    """批量打印：每份独立渲染 / 归档 / 记账，单份失败不阻塞整批（spec §9）。

    进度按「每份」推进（total/completed/failed）；失败只进清单，
    整批不因单份异常抛出，便于执行器把进度与失败明细一起落 `task_runs.result`。
    """
    ids = [str(item) for item in (doc_ids or []) if str(item)]
    total = len(ids)
    if not total:
        raise PrintError('empty_batch', '批量打印缺少 doc_ids', 400)
    limit = batch_limit()
    if total > limit:
        raise PrintError('batch_too_large',
                         '单批最多 %d 份，当前 %d 份' % (limit, total), 400)

    workers = min(_positive_int_env('PRINT_BATCH_CONCURRENCY',
                                    DEFAULT_BATCH_CONCURRENCY), total)
    lock = threading.Lock()
    runs: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    cancelled = False

    def _one(doc_id: str):
        try:
            result = print_document(bo_code, type_code, doc_id,
                                    template_id=template_id, trigger='batch',
                                    operator=operator, job_run_id=job_run_id)
        except Exception as exc:  # 单份失败只进清单
            return doc_id, None, {
                'doc_id': doc_id,
                'code': getattr(exc, 'code', None) or 'print_failed',
                'message': str(getattr(exc, 'message', exc))[:500],
            }
        run = result.get('run') or {}
        return doc_id, {'doc_id': doc_id, 'run_id': run.get('id'),
                        'attachment_id': result.get('attachment_id'),
                        'print_seq': run.get('print_seq')}, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = []
        for doc_id in ids:
            if should_cancel is not None and should_cancel():
                cancelled = True
                break
            futures.append(pool.submit(_one, doc_id))
        for future in as_completed(futures):
            doc_id, run_info, failure = future.result()
            with lock:
                if failure is not None:
                    failures.append(failure)
                else:
                    runs.append(run_info)
                snapshot = {'total': total, 'completed': len(runs),
                            'failed': len(failures), 'stage': doc_id}
            if progress_callback is not None:
                try:
                    progress_callback(snapshot)
                except Exception:
                    pass

    return {'total': total,
            'completed': len(runs),
            'failed': len(failures),
            'processed': len(runs) + len(failures),
            'cancelled': cancelled,
            'failures': failures,
            'runs': runs}