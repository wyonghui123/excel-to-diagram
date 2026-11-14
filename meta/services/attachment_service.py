# -*- coding: utf-8 -*-
"""[附件平台] 服务层：上传 / 链接 / 列表 / 下载鉴权 / 删除

依据: docs/specs/spec-platform-attachment-2026-11-13.md §15.8
约定:
- 落盘在 DB 事务之外（SQLite 单写者，事务窗口只含 insert）；
- 失败全部抛 AttachmentError(code, msg, status)，由 API 统一转 error_response；
- 字节操作只走 attachment_storage，本模块不读环境变量。
"""

import mimetypes
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from meta.core.error_codes import ErrorCode
from meta.core.enum_resolver import validate_enum_value
from meta.services.attachment_storage import (
    AttachmentStorageError,
    AttachmentTooLarge,
    get_storage,
    max_file_bytes,
    max_per_target,
)

ATTACHMENT_TABLE = 'attachments'
LINK_TABLE = 'attachment_links'

ATTACHMENT_STATUSES = ('active', 'superseded', 'deleted')
LINK_STATUSES = ('active', 'hidden', 'deleted')
LINK_ROLES = ('primary', 'supporting', 'signed', 'invoice_image',
              'contract', 'other')
# [v0.7 P0.2-2] 分类码值不在此硬编码：真源为 enum_types/enum_values（models_enums.AttachmentCategory）
CATEGORY_ENUM_TYPE_ID = 'attachment_category'

# 不允许挂附件的对象（附件自身 / 备注 / 系统表）
BLOCKED_TARGET_TYPES = frozenset([
    'attachment', 'attachment_link', 'annotation', 'audit_log',
    'enum_type', 'enum_value', 'user', 'role', 'permission_rule',
])

BLOCKED_EXTENSIONS = frozenset([
    'exe', 'com', 'cmd', 'bat', 'msi', 'vbs', 'sh', 'class', 'html', 'htm',
    'js', 'mjs', 'svg', 'xml', 'ps1', 'dll', 'scr', 'jar', 'apk', 'pif',
])

BLOCKED_MIMES = frozenset([
    'text/html', 'application/xhtml+xml', 'application/javascript',
    'text/javascript', 'image/svg+xml', 'text/xml', 'application/xml',
    'application/x-msdownload', 'application/x-dosexec',
    'application/x-sh', 'application/java-archive',
])

# 扩展名 → 魔数（仅对这些扩展名做一致性校验；Office OOXML 即 ZIP 容器）
MAGIC_PREFIXES = {
    'pdf': (b'%PDF',),
    'png': (b'\x89PNG',),
    'jpg': (b'\xff\xd8\xff',),
    'jpeg': (b'\xff\xd8\xff',),
    'gif': (b'GIF87a', b'GIF89a'),
    'bmp': (b'BM',),
    'zip': (b'PK\x03\x04',),
    'docx': (b'PK\x03\x04',),
    'xlsx': (b'PK\x03\x04',),
    'pptx': (b'PK\x03\x04',),
    'doc': (b'\xd0\xcf\x11\xe0',),
    'xls': (b'\xd0\xcf\x11\xe0',),
    'ppt': (b'\xd0\xcf\x11\xe0',),
}

_data_source = None


# ----------------------------------------------------------------- exceptions

class AttachmentError(Exception):
    """业务错误：code 取自 ErrorCode，status 为建议的 HTTP 状态。"""

    def __init__(self, code, message: str, status: int = 400):
        self.code = code.value if isinstance(code, ErrorCode) else str(code)
        self.message = message
        self.status = status
        super().__init__(message)


# ------------------------------------------------------------------ datasource

def init_attachment_service(data_source) -> None:
    global _data_source
    _data_source = data_source


def _ds():
    global _data_source
    if _data_source is None:
        from meta.core.datasource import get_platform_data_source
        _data_source = get_platform_data_source()
    return _data_source


# --------------------------------------------------------------------- helpers

def _now() -> str:
    return datetime.now().isoformat()


def _rows(cursor) -> List[Dict[str, Any]]:
    if cursor is None:
        return []
    rows = cursor.fetchall()
    cols = [d[0] for d in (cursor.description or [])]
    return [dict(zip(cols, row)) for row in rows]


def _one(cursor) -> Optional[Dict[str, Any]]:
    rows = _rows(cursor)
    return rows[0] if rows else None


def _to_int(value, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise AttachmentError(ErrorCode.DATA_INVALID,
                              '%s 必须为整数' % field, 400)


def _get_attachment(attachment_id: int) -> Optional[Dict[str, Any]]:
    return _one(_ds().execute(
        'SELECT * FROM %s WHERE id = ?' % ATTACHMENT_TABLE, (attachment_id,)))


def _get_link(link_id: int) -> Optional[Dict[str, Any]]:
    return _one(_ds().execute(
        'SELECT * FROM %s WHERE id = ?' % LINK_TABLE, (link_id,)))


def _active_link_count(target_type: str, target_id: int) -> int:
    row = _one(_ds().execute(
        'SELECT COUNT(*) AS n FROM %s l JOIN %s a ON a.id = l.attachment_id '
        "WHERE l.target_type = ? AND l.target_id = ? AND l.status = 'active' "
        "AND a.status = 'active'" % (LINK_TABLE, ATTACHMENT_TABLE),
        (target_type, target_id)))
    return int(row['n']) if row else 0


def _next_seq(target_type: str, target_id: int) -> int:
    row = _one(_ds().execute(
        'SELECT COALESCE(MAX(seq), 0) AS s FROM %s '
        'WHERE target_type = ? AND target_id = ?' % LINK_TABLE,
        (target_type, target_id)))
    return int(row['s'] if row else 0) + 10


def _code(attachment_id: int) -> str:
    return 'ATT-%06d' % attachment_id


def _file_name(row: Dict[str, Any]) -> str:
    return row.get('display_name') or row.get('original_file_name') or ''


def _attachment_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(row)
    data['code'] = _code(row['id'])
    data['file_name'] = _file_name(row)
    data['download_url'] = '/api/v1/attachments/%d/content' % row['id']
    return data


def _link_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return dict(row)


# ------------------------------------------------------------------ 白名单

def resolve_allowed_targets() -> Dict[str, str]:
    """BO id → 物理表名；派生自 schema 注册表（D-AT-04）。"""
    from meta.core.models import registry as meta_registry
    allowed = {}
    for bo_id, obj in (meta_registry.get_all() or {}).items():
        name = getattr(obj, 'id', None) or bo_id
        table = getattr(obj, 'table_name', None)
        if not table or name in BLOCKED_TARGET_TYPES:
            continue
        allowed[name] = table
    return allowed


def _assert_target(target_type: str) -> str:
    if not target_type:
        raise AttachmentError(ErrorCode.ATTACHMENT_TARGET_INVALID,
                              'target_type 不能为空', 400)
    table = resolve_allowed_targets().get(target_type)
    if not table or table not in _existing_tables():
        raise AttachmentError(ErrorCode.ATTACHMENT_TARGET_INVALID,
                              '不支持的目标类型: %s' % target_type, 400)
    return table


_table_cache: Dict[str, bool] = {}


def _existing_tables() -> set:
    if not _table_cache:
        cursor = _ds().execute(
            "SELECT name FROM sqlite_master WHERE type='table'")
        for (name,) in cursor.fetchall():
            _table_cache[name] = True
    return set(_table_cache.keys())


def _assert_target_exists(target_type: str, target_id: int) -> None:
    table = resolve_allowed_targets().get(target_type)
    if not table:
        raise AttachmentError(ErrorCode.ATTACHMENT_TARGET_INVALID,
                              '不支持的目标类型: %s' % target_type, 400)
    row = _one(_ds().execute(
        'SELECT id FROM %s WHERE id = ?' % table, (target_id,)))
    if not row:
        raise AttachmentError(ErrorCode.ATTACHMENT_TARGET_DELETED,
                              '目标记录不存在或已删除: %s#%s'
                              % (target_type, target_id), 400)


def _assert_permission(user: Dict[str, Any], target_type: str,
                       target_id: int, action: str) -> None:
    if user.get('is_admin'):
        return
    user_id = user.get('user_id')
    if not user_id:
        raise AttachmentError(ErrorCode.UNAUTHORIZED, '未登录', 401)
    from meta.services.permission_service import PermissionService
    try:
        allowed = PermissionService(_ds()).check_permission_unified(
            user_id, target_type, action, resource_id=target_id)
    except Exception:
        allowed = False
    if not allowed:
        raise AttachmentError(ErrorCode.FORBIDDEN,
                              '没有 %s:%s 权限' % (target_type, action), 403)


def _assert_quota(target_type: str, target_id: int) -> None:
    limit = max_per_target()
    if limit <= 0:
        return
    if _active_link_count(target_type, target_id) >= limit:
        raise AttachmentError(ErrorCode.ATTACHMENT_LIMIT_EXCEEDED,
                              '单目标附件数已达上限 %d' % limit, 400)


def _assert_extension(file_name: str) -> str:
    ext = os.path.splitext(file_name or '')[1].lower().lstrip('.')
    if not ext:
        raise AttachmentError(ErrorCode.ATTACHMENT_INVALID_MIME,
                              '文件缺少扩展名', 400)
    if ext in BLOCKED_EXTENSIONS:
        raise AttachmentError(ErrorCode.ATTACHMENT_INVALID_MIME,
                              '不允许的文件类型: .%s' % ext, 400)
    return ext


def _guess_mime(file_name: str, ext: str) -> str:
    guessed = mimetypes.guess_type(file_name or '')[0]
    if guessed and guessed in BLOCKED_MIMES:
        raise AttachmentError(ErrorCode.ATTACHMENT_INVALID_MIME,
                              '不允许的 MIME 类型: %s' % guessed, 400)
    return guessed or 'application/octet-stream'


def _assert_magic(head: bytes, ext: str) -> None:
    prefixes = MAGIC_PREFIXES.get(ext)
    if not prefixes:
        return
    if not head or not any(head.startswith(p) for p in prefixes):
        raise AttachmentError(ErrorCode.ATTACHMENT_INVALID_MIME,
                              '文件内容与扩展名 .%s 不匹配' % ext, 400)


def _assert_role(link_role: str) -> str:
    if link_role not in LINK_ROLES:
        raise AttachmentError(ErrorCode.DATA_INVALID,
                              '非法的 link_role: %s' % link_role, 400)
    return link_role


def _assert_category(category: str) -> str:
    if not validate_enum_value(CATEGORY_ENUM_TYPE_ID, category, _ds()):
        raise AttachmentError(ErrorCode.DATA_INVALID,
                              '非法的 category: %s' % category, 400)
    return category


def _assert_visibility(visibility: str) -> str:
    if visibility != 'internal':
        raise AttachmentError(ErrorCode.ATTACHMENT_VISIBILITY_UNSUPPORTED,
                              'P0 仅支持 visibility=internal', 400)
    return visibility


def _dedupe_check(attachment_id: Optional[int], target_type: str,
                  target_id: int, link_role: str, is_primary: bool) -> None:
    if attachment_id is not None:
        dup = _one(_ds().execute(
            'SELECT id FROM %s WHERE attachment_id = ? AND target_type = ? '
            "AND target_id = ? AND link_role = ? AND status = 'active'"
            % LINK_TABLE,
            (attachment_id, target_type, target_id, link_role)))
        if dup:
            raise AttachmentError(ErrorCode.ATTACHMENT_DUPLICATE_LINK,
                                  '该附件已挂接到此目标（角色 %s）' % link_role, 200)
    if is_primary:
        dup = _one(_ds().execute(
            'SELECT id FROM %s WHERE target_type = ? AND target_id = ? '
            'AND link_role = ? AND is_primary = 1 AND status = \'active\''
            % LINK_TABLE,
            (target_type, target_id, link_role)))
        if dup:
            raise AttachmentError(
                ErrorCode.ATTACHMENT_DUPLICATE_PRIMARY,
                '该目标此角色已有主文件', 200)


def _insert_attachment(data: Dict[str, Any]) -> int:
    cursor = _ds().execute(
        'INSERT INTO %s (created_at, created_by, updated_by, '
        'original_file_name, display_name, mime_type, size_bytes, sha256, '
        'storage_backend, storage_key, category, status, scan_status, '
        'uploaded_by, uploaded_at, description) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
        % ATTACHMENT_TABLE,
        (data['created_at'], data['created_by'], data['created_by'],
         data['original_file_name'], data['display_name'], data['mime_type'],
         data['size_bytes'], data['sha256'], data['storage_backend'],
         data['storage_key'], data['category'], data['status'],
         data['scan_status'], data['uploaded_by'], data['uploaded_at'],
         data['description']))
    return cursor.lastrowid


def _insert_link(data: Dict[str, Any]) -> int:
    cursor = _ds().execute(
        'INSERT INTO %s (created_at, created_by, updated_by, attachment_id, '
        'target_type, target_id, link_role, seq, is_primary, visibility, '
        'status, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
        % LINK_TABLE,
        (data['created_at'], data['created_by'], data['created_by'],
         data['attachment_id'], data['target_type'], data['target_id'],
         data['link_role'], data['seq'], 1 if data['is_primary'] else 0,
         data['visibility'], data['status'], data['description']))
    return cursor.lastrowid


def _audit(object_type: str, object_id: Any, action: str,
           user: Dict[str, Any], new_data: Dict[str, Any]) -> None:
    try:
        from meta.services.audit_service import AuditService
        AuditService(_ds()).log(
            object_type=object_type, object_id=object_id, action=action,
            user_id=user.get('user_id'), user_name=user.get('user_name'),
            new_data=new_data, ip_address=user.get('ip_address'),
            user_agent=user.get('user_agent'))
    except Exception:
        pass


# -------------------------------------------------------------------- 上传

def upload_and_link(file_storage, target_type: str, target_id,
                    *, link_role: str = 'supporting', category: str = 'other',
                    display_name: Optional[str] = None,
                    description: Optional[str] = None,
                    is_primary: bool = False,
                    visibility: str = 'internal',
                    user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    user = user or {}
    if file_storage is None or not getattr(file_storage, 'filename', ''):
        raise AttachmentError(ErrorCode.DATA_INVALID, '缺少上传文件 file', 400)
    target_id = _to_int(target_id, 'target_id')
    link_role = _assert_role(link_role)
    category = _assert_category(category)
    visibility = _assert_visibility(visibility)
    original = os.path.basename(file_storage.filename or '')

    _assert_target(target_type)
    _assert_target_exists(target_type, target_id)
    _assert_permission(user, target_type, target_id, 'update')
    _assert_quota(target_type, target_id)
    ext = _assert_extension(original)
    mime_type = _guess_mime(original, ext)
    _dedupe_check(None, target_type, target_id, link_role, bool(is_primary))

    storage = get_storage()
    try:
        stored = storage.save(file_storage.stream, max_bytes=max_file_bytes())
    except AttachmentTooLarge as exc:
        raise AttachmentError(ErrorCode.ATTACHMENT_TOO_LARGE,
                              '文件超过上限 %d MB'
                              % (exc.max_bytes // (1024 * 1024)), 400)
    except (OSError, AttachmentStorageError):
        raise AttachmentError(ErrorCode.ATTACHMENT_STORAGE_ERROR,
                              '文件写入失败', 500)

    try:
        _assert_magic(stored.head, ext)
    except AttachmentError:
        _cleanup_blob(storage, stored)
        raise

    now = _now()
    user_name = user.get('user_name') or 'system'
    attachment_payload = {
        'created_at': now,
        'created_by': user_name,
        'original_file_name': original,
        'display_name': display_name or os.path.splitext(original)[0],
        'mime_type': mime_type,
        'size_bytes': stored.size_bytes,
        'sha256': stored.sha256,
        'storage_backend': storage.name,
        'storage_key': stored.storage_key,
        'category': category,
        'status': 'active',
        'scan_status': 'unchecked',
        'uploaded_by': user_name,
        'uploaded_at': now,
        'description': description,
    }
    link_payload = {
        'created_at': now,
        'created_by': user_name,
        'target_type': target_type,
        'target_id': target_id,
        'link_role': link_role,
        'seq': _next_seq(target_type, target_id),
        'is_primary': bool(is_primary),
        'visibility': visibility,
        'status': 'active',
        'description': description,
    }

    ds = _ds()
    ds.begin_transaction()
    try:
        attachment_id = _insert_attachment(attachment_payload)
        link_payload['attachment_id'] = attachment_id
        link_id = _insert_link(link_payload)
        ds.commit()
    except sqlite3.IntegrityError as exc:
        ds.rollback()
        _cleanup_blob(storage, stored)
        raise _integrity_error(exc)
    except Exception:
        ds.rollback()
        _cleanup_blob(storage, stored)
        raise

    attachment = _get_attachment(attachment_id) or {}
    link = _get_link(link_id) or {}
    _audit('attachment', attachment_id, 'create', user,
           {'file_name': original, 'size_bytes': stored.size_bytes})
    _audit('attachment_link', link_id, 'link', user,
           {'attachment_id': attachment_id, 'target_type': target_type,
            'target_id': target_id, 'link_role': link_role})
    return {'attachment': _attachment_dict(attachment),
            'link': _link_dict(link)}


def _integrity_error(exc) -> AttachmentError:
    text = str(exc).lower()
    if 'uq_attachment_link_primary' in text:
        return AttachmentError(ErrorCode.ATTACHMENT_DUPLICATE_PRIMARY,
                               '该目标此角色已有主文件', 200)
    if 'uq_attachment_link_active' in text or 'unique' in text:
        return AttachmentError(ErrorCode.ATTACHMENT_DUPLICATE_LINK,
                               '重复挂接', 200)
    return AttachmentError(ErrorCode.DB_ERROR, '数据库写入失败', 500)


def _cleanup_blob(storage, stored) -> None:
    """仅当本次新建且无任何元数据引用该 key 时才删字节。"""
    if not getattr(stored, 'created', False):
        return
    try:
        row = _one(_ds().execute(
            'SELECT COUNT(*) AS n FROM %s WHERE storage_key = ?'
            % ATTACHMENT_TABLE, (stored.storage_key,)))
        if row and int(row['n']) == 0:
            storage.delete(stored.storage_key)
    except Exception:
        pass


# -------------------------------------------------------------------- 链接

def list_by_target(target_type: str, target_id,
                   *, include_hidden: bool = False, role: Optional[str] = None,
                   user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    user = user or {}
    target_id = _to_int(target_id, 'target_id')
    _assert_target(target_type)
    _assert_permission(user, target_type, target_id, 'read')

    statuses = ['active'] + (['hidden'] if include_hidden else [])
    placeholders = ', '.join('?' for _ in statuses)
    sql = (
        'SELECT a.*, l.id AS link_id, l.link_role, l.seq, l.is_primary, '
        'l.visibility, l.description AS link_description, '
        'l.status AS link_status '
        'FROM %s l JOIN %s a ON a.id = l.attachment_id '
        'WHERE l.target_type = ? AND l.target_id = ? '
        "AND l.status IN (%s) AND a.status != 'deleted'"
        % (LINK_TABLE, ATTACHMENT_TABLE, placeholders))
    params: List[Any] = [target_type, target_id] + statuses
    if role:
        sql += ' AND l.link_role = ?'
        params.append(role)
    sql += ' ORDER BY l.is_primary DESC, l.seq ASC, a.uploaded_at DESC'
    rows = _rows(_ds().execute(sql, tuple(params)))
    items = []
    for row in rows:
        item = _attachment_dict(row)
        item['link_role'] = row['link_role']
        item['link_id'] = row['link_id']
        item['seq'] = row['seq']
        item['is_primary'] = row['is_primary']
        item['visibility'] = row['visibility']
        item['link_status'] = row['link_status']
        items.append(item)
    return {'items': items, 'total': len(items)}


def create_link(attachment_id, target_type: str, target_id,
                *, link_role: str = 'supporting', is_primary: bool = False,
                description: Optional[str] = None,
                visibility: str = 'internal',
                user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    user = user or {}
    attachment_id = _to_int(attachment_id, 'attachment_id')
    target_id = _to_int(target_id, 'target_id')
    link_role = _assert_role(link_role)
    visibility = _assert_visibility(visibility)

    attachment = _get_attachment(attachment_id)
    if not attachment or attachment.get('status') == 'deleted':
        raise AttachmentError(ErrorCode.ATTACHMENT_NOT_FOUND,
                              '附件不存在: %d' % attachment_id, 404)

    _assert_target(target_type)
    _assert_target_exists(target_type, target_id)
    _assert_permission(user, target_type, target_id, 'update')
    _assert_quota(target_type, target_id)
    _dedupe_check(attachment_id, target_type, target_id, link_role,
                  bool(is_primary))

    now = _now()
    user_name = user.get('user_name') or 'system'
    payload = {
        'created_at': now,
        'created_by': user_name,
        'attachment_id': attachment_id,
        'target_type': target_type,
        'target_id': target_id,
        'link_role': link_role,
        'seq': _next_seq(target_type, target_id),
        'is_primary': bool(is_primary),
        'visibility': visibility,
        'status': 'active',
        'description': description,
    }
    ds = _ds()
    ds.begin_transaction()
    try:
        link_id = _insert_link(payload)
        ds.commit()
    except sqlite3.IntegrityError as exc:
        ds.rollback()
        raise _integrity_error(exc)
    except Exception:
        ds.rollback()
        raise
    link = _get_link(link_id) or {}
    _audit('attachment_link', link_id, 'link', user,
           {'attachment_id': attachment_id, 'target_type': target_type,
            'target_id': target_id, 'link_role': link_role})
    return {'link': _link_dict(link)}


def unlink(link_id, *, user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    user = user or {}
    link_id = _to_int(link_id, 'link_id')
    link = _get_link(link_id)
    if not link:
        raise AttachmentError(ErrorCode.ATTACHMENT_LINK_NOT_FOUND,
                              '链接不存在: %d' % link_id, 404)
    if link.get('status') == 'deleted':
        return {'link': _link_dict(link), 'already_deleted': True}

    attachment = _get_attachment(link['attachment_id']) or {}
    if not user.get('is_admin'):
        _assert_permission(user, link['target_type'], link['target_id'],
                           'update')
        if attachment.get('uploaded_by') != user.get('user_name'):
            raise AttachmentError(ErrorCode.FORBIDDEN, '无权解绑该附件', 403)

    _ds().execute(
        'UPDATE %s SET status = \'deleted\', updated_by = ? WHERE id = ?'
        % LINK_TABLE, (user.get('user_name') or 'system', link_id))
    _audit('attachment_link', link_id, 'unlink', user,
           {'attachment_id': link['attachment_id'],
            'target_type': link['target_type'],
            'target_id': link['target_id']})
    return {'link': _get_link(link_id) or link}


# -------------------------------------------------------------------- 删除

def delete_attachment(attachment_id,
                      *, user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    user = user or {}
    attachment_id = _to_int(attachment_id, 'attachment_id')
    attachment = _get_attachment(attachment_id)
    if not attachment or attachment.get('status') == 'deleted':
        raise AttachmentError(ErrorCode.ATTACHMENT_NOT_FOUND,
                              '附件不存在: %d' % attachment_id, 404)

    if not user.get('is_admin') and attachment.get('uploaded_by') != user.get(
            'user_name'):
        raise AttachmentError(ErrorCode.FORBIDDEN, '仅上传人或管理员可删除', 403)

    row = _one(_ds().execute(
        'SELECT COUNT(*) AS n FROM %s WHERE attachment_id = ? '
        "AND status IN ('active', 'hidden')" % LINK_TABLE, (attachment_id,)))
    if row and int(row['n']) > 0:
        raise AttachmentError(ErrorCode.ATTACHMENT_IN_USE,
                              '附件仍被 %d 个目标引用' % int(row['n']), 200)

    _ds().execute(
        'UPDATE %s SET status = \'deleted\', updated_by = ? WHERE id = ?'
        % ATTACHMENT_TABLE, (user.get('user_name') or 'system', attachment_id))
    _audit('attachment', attachment_id, 'delete', user, {'hard': False})
    return {'attachment': _attachment_dict(_get_attachment(attachment_id) or {})}


# -------------------------------------------------------------------- 下载

def open_content(attachment_id, *, target_type: Optional[str] = None,
                 target_id=None,
                 user: Optional[Dict[str, Any]] = None):
    """鉴权后返回 (attachment_row, 本地路径)；字节缺失 → 410。"""
    user = user or {}
    attachment_id = _to_int(attachment_id, 'attachment_id')
    attachment = _get_attachment(attachment_id)
    if not attachment or attachment.get('status') == 'deleted':
        raise AttachmentError(ErrorCode.ATTACHMENT_NOT_FOUND,
                              '附件不存在: %d' % attachment_id, 404)

    if target_type:
        target_id = _to_int(target_id, 'target_id')
        link = _one(_ds().execute(
            'SELECT id FROM %s WHERE attachment_id = ? AND target_type = ? '
            "AND target_id = ? AND status = 'active'" % LINK_TABLE,
            (attachment_id, target_type, target_id)))
        if not link:
            raise AttachmentError(ErrorCode.FORBIDDEN, '该附件未挂接到此目标', 403)
        _assert_permission(user, target_type, target_id, 'read')
    else:
        links = _rows(_ds().execute(
            'SELECT target_type, target_id FROM %s WHERE attachment_id = ? '
            "AND status = 'active'" % LINK_TABLE, (attachment_id,)))
        if not links:
            raise AttachmentError(ErrorCode.FORBIDDEN, '附件没有有效链接', 403)
        allowed = False
        for link in links:
            try:
                _assert_permission(user, link['target_type'],
                                   link['target_id'], 'read')
                allowed = True
                break
            except AttachmentError:
                continue
        if not allowed:
            raise AttachmentError(ErrorCode.FORBIDDEN, '无权下载该附件', 403)

    if attachment.get('storage_backend') != 'fs':
        raise AttachmentError(ErrorCode.ATTACHMENT_STORAGE_ERROR,
                              '不支持的存储后端: %s'
                              % attachment.get('storage_backend'), 500)
    try:
        path = get_storage().local_path(attachment['storage_key'])
    except AttachmentStorageError:
        path = None
    if path is None:
        raise AttachmentError(ErrorCode.ATTACHMENT_MISSING_FILE,
                              '附件文件已缺失', 410)
    return attachment, path


# -------------------------------------------------------------------- 巡检

def collect_orphans(grace_days: int = 30) -> Dict[str, Any]:
    """枚举无有效元数据引用的字节（P0 只枚举、不删除）。"""
    storage = get_storage()
    referenced = set()
    for row in _rows(_ds().execute(
            'SELECT storage_key FROM %s' % ATTACHMENT_TABLE)):
        referenced.add(row['storage_key'])

    root = storage.root
    items = []
    base = root / 'attachments'
    if base.is_dir():
        for path in base.rglob('*'):
            if not path.is_file():
                continue
            key = path.relative_to(root).as_posix()
            if key not in referenced:
                items.append({'storage_key': key,
                              'size_bytes': path.stat().st_size})
    return {'items': items, 'total': len(items), 'grace_days': grace_days}