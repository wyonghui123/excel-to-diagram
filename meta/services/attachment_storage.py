# -*- coding: utf-8 -*-
"""[附件平台] 字节存储层（P0 仅文件系统 CAS）

依据: docs/specs/spec-platform-attachment-2026-11-13.md §15.6 / §16
职责单一：只碰字节，不碰 DB。数据库元数据由 attachment_service 负责。

CAS 布局:  <root>/attachments/yyyy/mm/<sha256[:2]>/<sha256>
中转目录:  <root>/.tmp/<uuid4>（必须与 root 同卷，os.replace 才原子）

配置（全部在此模块读取，其它模块不得直接读 env）:
  ATTACHMENT_STORAGE_BACKEND     fs（P0 仅 fs；db / s3 占位）
  ATTACHMENT_STORAGE_ROOT        默认 uploads
  ATTACHMENT_MAX_FILE_SIZE_MB    默认 50
  ATTACHMENT_MAX_PER_TARGET      默认 200（0 = 不限）
"""

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol

KEY_RE = re.compile(r'^attachments/\d{4}/\d{2}/[0-9a-f]{2}/[0-9a-f]{64}$')
CHUNK = 1024 * 1024
HEAD_BYTES = 8192

DEFAULT_ROOT = 'uploads'
DEFAULT_MAX_FILE_SIZE_MB = 50
DEFAULT_MAX_PER_TARGET = 200


# --------------------------------------------------------------------- config

def storage_root() -> Path:
    """CAS 根目录（每次调用读取 env，便于测试用临时目录覆盖）。"""
    raw = os.environ.get('ATTACHMENT_STORAGE_ROOT', DEFAULT_ROOT)
    return Path(raw).expanduser().resolve()


def max_file_bytes() -> int:
    raw = os.environ.get('ATTACHMENT_MAX_FILE_SIZE_MB')
    try:
        mb = int(raw) if raw not in (None, '') else DEFAULT_MAX_FILE_SIZE_MB
    except ValueError:
        mb = DEFAULT_MAX_FILE_SIZE_MB
    if mb <= 0:
        mb = DEFAULT_MAX_FILE_SIZE_MB
    return mb * 1024 * 1024


def max_per_target() -> int:
    """单目标有效链接上限；0 = 不限。"""
    raw = os.environ.get('ATTACHMENT_MAX_PER_TARGET')
    try:
        value = int(raw) if raw not in (None, '') else DEFAULT_MAX_PER_TARGET
    except ValueError:
        value = DEFAULT_MAX_PER_TARGET
    return max(0, value)


# ----------------------------------------------------------------- exceptions

class AttachmentStorageError(Exception):
    """存储层失败（路径非法 / 磁盘 IO）。"""


class AttachmentTooLarge(AttachmentStorageError):
    """写盘过程中超过上限（第二道闸；第一道是 Flask MAX_CONTENT_LENGTH）。"""

    def __init__(self, size_bytes: int, max_bytes: int):
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        super().__init__(
            'attachment too large: %d > %d bytes' % (size_bytes, max_bytes))


# ---------------------------------------------------------------- data types

@dataclass(frozen=True)
class StoredBlob:
    sha256: str
    size_bytes: int
    storage_key: str
    created: bool        # False = 命中已有内容（CAS 去重）
    head: bytes          # 前 8KB，供 MIME 魔数校验，避免二次读盘


class StorageBackend(Protocol):
    name: str

    def save(self, stream, *, max_bytes: int) -> StoredBlob: ...
    def exists(self, key: str) -> bool: ...
    def local_path(self, key: str) -> Optional[Path]: ...
    def iter_chunks(self, key: str, chunk: int = CHUNK): ...
    def delete(self, key: str) -> None: ...


# ------------------------------------------------------------------ fs impl

class FsStorage:
    """文件系统 CAS 实现。"""

    name = 'fs'

    def __init__(self, root=None):
        self.root = Path(root).expanduser().resolve() if root else storage_root()

    # ---------------------------------------------------------- path helpers

    def _key(self, digest: str) -> str:
        now = datetime.now()
        return 'attachments/%04d/%02d/%s/%s' % (
            now.year, now.month, digest[:2], digest)

    def _path_for(self, digest: str) -> Path:
        return self.root / self._key(digest)

    def _new_tmp(self) -> Path:
        tmp_dir = self.root / '.tmp'
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return tmp_dir / uuid.uuid4().hex

    def _resolve(self, key: str) -> Path:
        if not KEY_RE.match(key or ''):
            raise AttachmentStorageError('invalid storage_key: %r' % (key,))
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise AttachmentStorageError('storage_key escapes root')
        return path

    # ---------------------------------------------------------------- public

    def save(self, stream, *, max_bytes: int) -> StoredBlob:
        tmp = self._new_tmp()
        hasher = hashlib.sha256()
        size = 0
        head = b''
        try:
            with open(tmp, 'wb') as handle:
                while True:
                    buf = stream.read(CHUNK)
                    if not buf:
                        break
                    size += len(buf)
                    if size > max_bytes:
                        handle.close()
                        os.unlink(tmp)
                        raise AttachmentTooLarge(size, max_bytes)
                    if len(head) < HEAD_BYTES:
                        head += buf[:HEAD_BYTES - len(head)]
                    hasher.update(buf)
                    handle.write(buf)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            if tmp.exists():
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            raise
        digest = hasher.hexdigest()
        key = self._key(digest)
        final = self.root / key
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            os.unlink(tmp)
            return StoredBlob(digest, size, key, False, head)
        os.replace(tmp, final)
        return StoredBlob(digest, size, key, True, head)

    def exists(self, key: str) -> bool:
        try:
            return self._resolve(key).is_file()
        except AttachmentStorageError:
            return False

    def local_path(self, key: str) -> Optional[Path]:
        path = self._resolve(key)
        return path if path.is_file() else None

    def size(self, key: str) -> int:
        return self._resolve(key).stat().st_size

    def iter_chunks(self, key: str, chunk: int = CHUNK):
        path = self._resolve(key)
        with open(path, 'rb') as handle:
            while True:
                buf = handle.read(chunk)
                if not buf:
                    break
                yield buf

    def read_all(self, key: str) -> bytes:
        return b''.join(self.iter_chunks(key))

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        try:
            path.unlink()
        except FileNotFoundError:
            return


class DbStorage:
    """P1 占位：字节入库。"""

    name = 'db'

    def save(self, stream, *, max_bytes: int) -> StoredBlob:
        raise NotImplementedError('db 存储后端未实现（P0 仅 fs）')


class S3Storage:
    """P2 占位：对象存储。"""

    name = 'object'

    def save(self, stream, *, max_bytes: int) -> StoredBlob:
        raise NotImplementedError('object 存储后端未实现（P0 仅 fs）')


# ---------------------------------------------------------------- factory

_BACKENDS = {
    'fs': FsStorage,
    'db': DbStorage,
    'object': S3Storage,
}

_storage_cache = {}


def reset():
    """清空后端缓存（测试切换 ATTACHMENT_STORAGE_ROOT 后调用）。"""
    _storage_cache.clear()


def get_storage():
    """按 env 构造/复用存储后端；测试改 root 后自然换实例。"""
    backend = (os.environ.get('ATTACHMENT_STORAGE_BACKEND') or 'fs').strip()
    factory = _BACKENDS.get(backend)
    if factory is None:
        raise AttachmentStorageError('unknown storage backend: %r' % backend)
    if backend != 'fs':
        return factory()
    root = storage_root()
    cached = _storage_cache.get(root)
    if cached is None:
        cached = FsStorage(root)
        _storage_cache[root] = cached
    return cached