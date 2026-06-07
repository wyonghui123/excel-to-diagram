# -*- coding: utf-8 -*-
"""
[DECORATIVE] v3.16: DB 损坏预防 3 大方案 - 端点
==========================================

提供 3 个端点 (admin only):
1. `_db_health`     - Pool 健康监控 (实时)
2. `db.backup`     - 立即备份
3. `db.recover`    - 从备份恢复 (谨慎!)

所有端点 admin only, 通过 existing g.current_user 检查。
"""
import os
import sqlite3
import sys
from datetime import datetime
from typing import Any, Dict

from flask import Blueprint, jsonify, request

# [DECORATIVE] v3.16: 找项目根 (从 meta/api/ 跑时)
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from flask import current_app, g  # noqa: E402

from meta.services.auth_middleware import get_current_user, is_admin  # noqa: E402
from meta.core.datasource import get_data_source  # noqa: E402

db_admin_bp = Blueprint('db_admin', __name__, url_prefix='/api/v2/action')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _ensure_current_user() -> dict:
    """[DECORATIVE] v3.16: 确保 g.current_user 已设置 (db_admin_bp 端点不走 execute_action)

    流程:
    1. 先看 g.current_user (可能在 middleware 中已设)
    2. 从 Authorization header / cookie 提取 token
    3. 验证 token, 设置 g.current_user
    """
    user = get_current_user()
    if user:
        return user

    from meta.services.auth_middleware import _extract_token
    from meta.services.token_service import TokenService
    from meta.services.token_blacklist_service import token_blacklist_service

    token = _extract_token()
    if not token:
        return None

    try:
        if token_blacklist_service.is_blacklisted(token):
            return None
    except Exception:
        return None

    user = TokenService.verify_token(token)
    if user:
        g.current_user = user
    return user


def _require_admin() -> bool:
    """检查当前用户是否 admin"""
    user = _ensure_current_user()
    if not user:
        return False
    return is_admin(user) or user.get('username') == 'admin'


def _get_db_path() -> str:
    """获取主 DB 路径"""
    return os.path.join(_PROJECT_ROOT, 'meta', 'architecture.db')


def _get_backup_dir() -> str:
    """获取 backup 目录"""
    backup_dir = os.path.join(_PROJECT_ROOT, 'meta', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def _format_size(size_bytes: int) -> str:
    """格式化为可读 size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f'{size_bytes:.1f}{unit}'
        size_bytes /= 1024
    return f'{size_bytes:.1f}TB'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 方案 1: Pool 健康监控
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@db_admin_bp.route('/_db_health', methods=['GET'])
def db_health():
    """[DECORATIVE] v3.16: DB Pool 健康监控 (admin only)

    返回:
    - pool_stats: 当前 pool 状态 (acquire/release/wait 等)
    - write_queue_stats: 写队列状态
    - integrity: DB 完整性 (PRAGMA integrity_check)
    - wal_info: WAL 模式 + 状态
    - db_size: 主 DB 文件大小
    - backup_count: 备份数量
    - last_backup: 最新备份时间
    - status: healthy / warning / critical
    """
    if not _require_admin():
        return jsonify({'success': False, 'message': 'admin only', 'code': 'E010'}), 403

    result = {
        'success': True,
        'data': {
            'pool_stats': {},
            'write_queue_stats': {},
            'integrity': 'unknown',
            'wal_info': {},
            'db_size': '0B',
            'disk_free': 'unknown',
            'backup_count': 0,
            'last_backup': None,
            'status': 'healthy',
            'checked_at': datetime.now().isoformat(),
        },
        'message': 'db_health OK',
    }

    # 1. Pool stats
    try:
        # [DECORATIVE] v3.16 fix: 显式传 file-based DB path (v3.13 起 :memory: 不支持)
        ds = get_data_source('sqlite', path=_get_db_path())
        result['data']['pool_stats'] = ds.get_pool_stats()
        result['data']['write_queue_stats'] = ds.get_write_queue_stats()
    except Exception as e:
        result['data']['status'] = 'critical'
        result['data']['pool_stats'] = {'error': str(e)}

    # 2. DB 完整性
    db_path = _get_db_path()
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            check = conn.execute('PRAGMA integrity_check').fetchone()[0]
            result['data']['integrity'] = check
            if check != 'ok':
                result['data']['status'] = 'critical'
        finally:
            conn.close()
    except Exception as e:
        result['data']['integrity'] = f'error: {e}'
        result['data']['status'] = 'critical'

    # 3. WAL 模式
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            journal_mode = conn.execute('PRAGMA journal_mode').fetchone()[0]
            wal_info = {
                'journal_mode': journal_mode,
            }
            if journal_mode.lower() == 'wal':
                wal_info['wal_file_size'] = _format_size(
                    os.path.getsize(db_path + '-wal') if os.path.exists(db_path + '-wal') else 0
                )
                # checkpoint stats
                busy = conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
                wal_info['checkpoint'] = {
                    'busy': busy[0] if busy else None,
                    'log_pages': busy[1] if busy else None,
                    'checkpointed_pages': busy[2] if busy else None,
                }
            result['data']['wal_info'] = wal_info
        finally:
            conn.close()
    except Exception as e:
        result['data']['wal_info'] = {'error': str(e)}

    # 4. DB size
    try:
        if os.path.exists(db_path):
            result['data']['db_size'] = _format_size(os.path.getsize(db_path))
    except Exception:
        pass

    # 5. Disk free
    try:
        import shutil
        usage = shutil.disk_usage(_PROJECT_ROOT)
        result['data']['disk_free'] = _format_size(usage.free)
    except Exception:
        pass

    # 6. Backup count + last backup
    try:
        backup_dir = _get_backup_dir()
        backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.bak')])
        result['data']['backup_count'] = len(backups)
        if backups:
            last = backups[-1]
            full = os.path.join(backup_dir, last)
            result['data']['last_backup'] = {
                'filename': last,
                'size': _format_size(os.path.getsize(full)),
                'mtime': datetime.fromtimestamp(os.path.getmtime(full)).isoformat(),
            }
    except Exception:
        pass

    # 7. 状态决策
    pool = result['data']['pool_stats']
    if result['data']['status'] == 'critical':
        pass  # 已 critical
    elif pool.get('error_count', 0) > 10:
        result['data']['status'] = 'critical'
    elif pool.get('error_count', 0) > 0 or pool.get('acquire_timeout_count', 0) > 0:
        result['data']['status'] = 'warning'
    elif result['data']['backup_count'] == 0:
        result['data']['status'] = 'warning'  # 无备份 = 风险

    return jsonify(result)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 方案 2: 立即备份
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@db_admin_bp.route('/db.backup', methods=['POST'])
def db_backup():
    """[DECORATIVE] v3.16: 立即备份 (admin only)

    使用 SQLite 在线备份 API (不锁表)。
    返回: filename, size, duration_ms
    """
    if not _require_admin():
        return jsonify({'success': False, 'message': 'admin only', 'code': 'E010'}), 403

    db_path = _get_db_path()
    backup_dir = _get_backup_dir()
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_name = f'architecture.db.backup-{timestamp}.bak'
    backup_path = os.path.join(backup_dir, backup_name)

    start = datetime.now()
    try:
        # SQLite 在线备份 API (支持热备份)
        source = sqlite3.connect(db_path, timeout=30)
        dest = sqlite3.connect(backup_path, timeout=30)
        try:
            source.backup(dest)
        finally:
            source.close()
            dest.close()

        # 验证备份完整性
        check_conn = sqlite3.connect(backup_path, timeout=5)
        try:
            integrity = check_conn.execute('PRAGMA integrity_check').fetchone()[0]
        finally:
            check_conn.close()

        duration_ms = (datetime.now() - start).total_seconds() * 1000
        size = os.path.getsize(backup_path)

        if integrity != 'ok':
            # 删除损坏的备份
            os.remove(backup_path)
            return jsonify({
                'success': False,
                'message': f'备份后 integrity_check 失败: {integrity}',
                'code': 'E030',
            }), 500

        return jsonify({
            'success': True,
            'data': {
                'filename': backup_name,
                'path': backup_path,
                'size': _format_size(size),
                'duration_ms': round(duration_ms, 1),
                'integrity': integrity,
                'created_at': start.isoformat(),
            },
            'message': 'backup created',
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'备份失败: {e}',
            'code': 'E030',
        }), 500


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 方案 3: 从备份恢复 (高危!)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@db_admin_bp.route('/db.recover', methods=['POST'])
def db_recover():
    """[DECORATIVE] v3.16: 从备份恢复 (admin only, 高危!)

    必填: backup_filename (来自 GET /api/v2/db/backups)
    可选: dry_run=true (仅检查, 不执行)
    """
    if not _require_admin():
        return jsonify({'success': False, 'message': 'admin only', 'code': 'E010'}), 403

    body = request.get_json(silent=True) or {}
    backup_filename = body.get('backup_filename')
    dry_run = body.get('dry_run', False)

    if not backup_filename:
        return jsonify({
            'success': False,
            'message': 'backup_filename 必填',
            'code': 'E001',
        }), 400

    backup_dir = _get_backup_dir()
    backup_path = os.path.join(backup_dir, backup_filename)

    if not os.path.exists(backup_path):
        return jsonify({
            'success': False,
            'message': f'备份文件不存在: {backup_filename}',
            'code': 'E030',
        }), 404

    # 验证备份完整性
    try:
        check_conn = sqlite3.connect(backup_path, timeout=5)
        try:
            integrity = check_conn.execute('PRAGMA integrity_check').fetchone()[0]
        finally:
            check_conn.close()
        if integrity != 'ok':
            return jsonify({
                'success': False,
                'message': f'备份 integrity_check 失败: {integrity}',
                'code': 'E030',
            }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'备份验证失败: {e}',
            'code': 'E030',
        }), 500

    if dry_run:
        return jsonify({
            'success': True,
            'data': {
                'dry_run': True,
                'backup_filename': backup_filename,
                'integrity': integrity,
                'would_recover_to': _get_db_path(),
            },
            'message': 'dry run OK - 备份有效, 可执行实际恢复',
        })

    # 实际恢复: 备份当前 DB 到 .recover-backup, 然后从指定备份恢复
    db_path = _get_db_path()
    recover_backup_name = f'architecture.db.recover-backup-{datetime.now().strftime("%Y%m%d-%H%M%S")}.bak'
    recover_backup_path = os.path.join(backup_dir, recover_backup_name)

    try:
        # 1. 备份当前 DB (安全网)
        source = sqlite3.connect(db_path, timeout=30)
        dest = sqlite3.connect(recover_backup_path, timeout=30)
        try:
            source.backup(dest)
        finally:
            source.close()
            dest.close()

        # 2. 从指定备份恢复
        source = sqlite3.connect(backup_path, timeout=30)
        dest = sqlite3.connect(db_path, timeout=30)
        try:
            source.backup(dest)
        finally:
            source.close()
            dest.close()

        return jsonify({
            'success': True,
            'data': {
                'recovered_from': backup_filename,
                'recovered_to': db_path,
                'previous_state_backup': recover_backup_name,
                'integrity_after': integrity,
            },
            'message': 'recovery completed - 之前状态已备份到 ' + recover_backup_name,
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'恢复失败: {e}',
            'code': 'E030',
        }), 500
