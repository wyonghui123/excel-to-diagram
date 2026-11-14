# -*- coding: utf-8 -*-
"""[附件平台] API：6 个端点（上传 / by-target / 挂接 / 下载 / 解绑 / 删除）

依据: docs/specs/spec-platform-attachment-2026-11-13.md §15.9
"""

import os
from urllib.parse import quote

from flask import Blueprint, Response, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from meta.api._response_contract import error_response, ok
from meta.core.error_codes import ErrorCode
from meta.services import attachment_service as svc
from meta.services.attachment_service import AttachmentError
from meta.services.attachment_storage import get_storage, max_file_bytes
from meta.services.auth_middleware import get_current_user, login_required

attachment_bp = Blueprint('attachments', __name__, url_prefix='/api/v1')

DEFAULT_INLINE_MAX = 2 * 1024 * 1024


# --------------------------------------------------------------------- helpers

def _user():
    info = get_current_user() or {}
    return {
        'user_id': info.get('user_id') or info.get('id'),
        'user_name': (info.get('username') or info.get('user_name')
                      or info.get('display_name')),
        'is_admin': bool(info.get('is_admin')) or _is_admin(info),
        'ip_address': request.headers.get('X-Forwarded-For',
                                          request.remote_addr),
        'user_agent': request.headers.get('User-Agent'),
    }


def _is_admin(info):
    try:
        from meta.services.auth_middleware import is_admin
        return is_admin(info)
    except Exception:
        return False


def _fail(exc: AttachmentError):
    return error_response(exc.message, exc.code, exc.status)


def _flag(value) -> bool:
    return str(value or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _inline_max() -> int:
    raw = os.environ.get('ATTACHMENT_INLINE_MAX_BYTES')
    try:
        return int(raw) if raw not in (None, '') else DEFAULT_INLINE_MAX
    except ValueError:
        return DEFAULT_INLINE_MAX


def _use_send_file() -> bool:
    return os.environ.get('ATTACHMENT_USE_SEND_FILE', '1') != '0'


def _disposition(file_name: str, inline: bool) -> str:
    kind = 'inline' if inline else 'attachment'
    fallback = (file_name or 'download').encode('ascii', 'ignore').decode()
    fallback = fallback.replace('"', '').replace('\\', '') or 'download'
    encoded = quote(file_name or 'download', safe='')
    return '%s; filename="%s"; filename*=UTF-8\'\'%s' % (
        kind, fallback, encoded)


# --------------------------------------------------------------- error 413

@attachment_bp.errorhandler(RequestEntityTooLarge)
def _too_large(_exc):
    limit_mb = max(1, (max_file_bytes() + 1024 * 1024) // (1024 * 1024))
    return error_response('文件超过上限 %d MB' % limit_mb,
                          ErrorCode.ATTACHMENT_TOO_LARGE, 413)


# -------------------------------------------------------------------- upload

@attachment_bp.route('/attachments', methods=['POST'])
@login_required
def upload_attachment():
    if 'file' not in request.files:
        return error_response('缺少上传文件 file', ErrorCode.DATA_INVALID, 400)
    form = request.form
    try:
        result = svc.upload_and_link(
            request.files['file'],
            form.get('target_type'),
            form.get('target_id'),
            link_role=form.get('link_role') or 'supporting',
            category=form.get('category') or 'other',
            display_name=form.get('display_name') or None,
            description=form.get('description') or None,
            is_primary=_flag(form.get('is_primary')),
            visibility=form.get('visibility') or 'internal',
            user=_user())
    except AttachmentError as exc:
        return _fail(exc)
    return ok(result, '上传成功'), 201


# ----------------------------------------------------------------- by-target

@attachment_bp.route('/attachments/by-target', methods=['GET'])
@login_required
def list_by_target():
    try:
        result = svc.list_by_target(
            request.args.get('target_type'),
            request.args.get('target_id'),
            include_hidden=_flag(request.args.get('include_hidden')),
            role=request.args.get('link_role') or None,
            user=_user())
    except AttachmentError as exc:
        return _fail(exc)
    return ok(result)


# ---------------------------------------------------------------- link create

@attachment_bp.route('/attachments/<int:aid>/links', methods=['POST'])
@login_required
def create_link(aid):
    body = request.get_json(silent=True) or {}
    try:
        result = svc.create_link(
            aid,
            body.get('target_type'),
            body.get('target_id'),
            link_role=body.get('link_role') or 'supporting',
            is_primary=bool(body.get('is_primary')),
            description=body.get('description'),
            visibility=body.get('visibility') or 'internal',
            user=_user())
    except AttachmentError as exc:
        return _fail(exc)
    return ok(result, '挂接成功'), 201


# -------------------------------------------------------------------- content

@attachment_bp.route('/attachments/<int:aid>/content', methods=['GET'])
@login_required
def download_content(aid):
    inline = _flag(request.args.get('inline'))
    try:
        meta, path = svc.open_content(
            aid,
            target_type=request.args.get('target_type') or None,
            target_id=request.args.get('target_id'),
            user=_user())
    except AttachmentError as exc:
        return _fail(exc)

    storage = get_storage()
    if meta['size_bytes'] <= _inline_max() or not _use_send_file():
        data = b''.join(storage.iter_chunks(meta['storage_key']))
        resp = Response(data, mimetype=meta['mime_type'])
    else:
        resp = send_file(path, mimetype=meta['mime_type'],
                         as_attachment=not inline,
                         download_name=meta['original_file_name'],
                         conditional=True)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Cache-Control'] = 'private, max-age=0'
    resp.headers['Content-Disposition'] = _disposition(
        meta['original_file_name'], inline)
    return resp


# ---------------------------------------------------------------- link delete

@attachment_bp.route('/attachment-links/<int:lid>', methods=['DELETE'])
@login_required
def delete_link(lid):
    try:
        result = svc.unlink(lid, user=_user())
    except AttachmentError as exc:
        return _fail(exc)
    return ok(result, '已解绑')


# ----------------------------------------------------------- attachment delete

@attachment_bp.route('/attachments/<int:aid>', methods=['DELETE'])
@login_required
def delete_attachment(aid):
    try:
        result = svc.delete_attachment(aid, user=_user())
    except AttachmentError as exc:
        return _fail(exc)
    return ok(result, '已删除')