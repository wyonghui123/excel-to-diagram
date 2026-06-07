# -*- coding: utf-8 -*-
"""
[DECORATIVE] v3.16: DB 异常恢复脚本
===========================

自动检测 DB 损坏并从最新备份恢复。

Usage:
    # 干跑 (检测 + 推荐, 不执行)
    python scripts/recover_db.py

    # 自动恢复 (从最新备份)
    python scripts/recover_db.py --auto

    # 从指定备份恢复
    python scripts/recover_db.py --from-backup architecture.db.backup-20260606-150000.bak

    # 仅诊断
    python scripts/recover_db.py --diagnose

诊断 5 步:
    1. PRAGMA integrity_check
    2. PRAGMA quick_check
    3. journal_mode (应是 WAL)
    4. data_version (PRAGMA data_version)
    5. 尝试 SELECT 1 (基本可读性)

退出码:
    0 - 健康, 无需恢复
    1 - 损坏, 但未恢复
    2 - 损坏, 已自动恢复
    3 - 损坏, 恢复失败
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime

# [DECORATIVE] v3.16: 找项目根
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _PROJECT_ROOT)

DEFAULT_DB = os.path.join(_PROJECT_ROOT, 'meta', 'architecture.db')
DEFAULT_BACKUP_DIR = os.path.join(_PROJECT_ROOT, 'meta', 'backups')


def _format_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f'{size_bytes:.1f}{unit}'
        size_bytes /= 1024
    return f'{size_bytes:.1f}TB'


def diagnose(db_path: str) -> dict:
    """诊断 DB 健康状态

    Returns: {
        'healthy': bool,
        'checks': { check_name: {'status': 'pass'|'warn'|'fail', 'detail': str} },
        'recommendation': 'recover_from_backup' | 'checkpoint' | 'none'
    }
    """
    if not os.path.exists(db_path):
        return {
            'healthy': False,
            'checks': {'file_exists': {'status': 'fail', 'detail': f'文件不存在: {db_path}'}},
            'recommendation': 'recover_from_backup',
        }

    result = {
        'healthy': True,
        'checks': {},
        'recommendation': 'none',
    }

    # Check 1: file_exists
    result['checks']['file_exists'] = {'status': 'pass', 'detail': f'{_format_size(os.path.getsize(db_path))}'}

    # Check 2-5: 需连接
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        # Check 2: integrity_check
        try:
            integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
            if integrity == 'ok':
                result['checks']['integrity_check'] = {'status': 'pass', 'detail': integrity}
            else:
                result['checks']['integrity_check'] = {'status': 'fail', 'detail': integrity}
                result['healthy'] = False
                result['recommendation'] = 'recover_from_backup'
        except Exception as e:
            result['checks']['integrity_check'] = {'status': 'fail', 'detail': str(e)}
            result['healthy'] = False
            result['recommendation'] = 'recover_from_backup'

        # Check 3: quick_check (更快, 不彻底)
        try:
            quick = conn.execute('PRAGMA quick_check').fetchone()[0]
            if quick == 'ok':
                result['checks']['quick_check'] = {'status': 'pass', 'detail': quick}
            else:
                result['checks']['quick_check'] = {'status': 'fail', 'detail': quick}
                if result['healthy']:
                    result['healthy'] = False
                    result['recommendation'] = 'recover_from_backup'
        except Exception as e:
            result['checks']['quick_check'] = {'status': 'fail', 'detail': str(e)}
            if result['healthy']:
                result['healthy'] = False
                result['recommendation'] = 'recover_from_backup'

        # Check 4: journal_mode
        try:
            journal = conn.execute('PRAGMA journal_mode').fetchone()[0]
            if journal.lower() == 'wal':
                result['checks']['journal_mode'] = {'status': 'pass', 'detail': journal}
            else:
                result['checks']['journal_mode'] = {'status': 'warn', 'detail': f'{journal} (推荐 WAL)'}
                if result['recommendation'] == 'none':
                    result['recommendation'] = 'checkpoint'
        except Exception as e:
            result['checks']['journal_mode'] = {'status': 'fail', 'detail': str(e)}

        # Check 5: basic read
        try:
            r = conn.execute('SELECT 1').fetchone()
            if r and r[0] == 1:
                result['checks']['basic_read'] = {'status': 'pass', 'detail': 'SELECT 1 OK'}
            else:
                result['checks']['basic_read'] = {'status': 'fail', 'detail': f'结果异常: {r}'}
                if result['healthy']:
                    result['healthy'] = False
                    result['recommendation'] = 'recover_from_backup'
        except Exception as e:
            result['checks']['basic_read'] = {'status': 'fail', 'detail': str(e)}
            if result['healthy']:
                result['healthy'] = False
                result['recommendation'] = 'recover_from_backup'

        # Check 6: data_version
        try:
            dv = conn.execute('PRAGMA data_version').fetchone()[0]
            result['checks']['data_version'] = {'status': 'pass', 'detail': str(dv)}
        except Exception as e:
            result['checks']['data_version'] = {'status': 'warn', 'detail': str(e)}
    finally:
        conn.close()

    return result


def list_backups(backup_dir: str = DEFAULT_BACKUP_DIR) -> list:
    """列出所有备份 (按时间倒序)"""
    if not os.path.exists(backup_dir):
        return []
    backups = []
    for f in os.listdir(backup_dir):
        if not f.endswith('.bak'):
            continue
        full = os.path.join(backup_dir, f)
        backups.append({
            'filename': f,
            'path': full,
            'mtime': os.path.getmtime(full),
            'size': os.path.getsize(full),
        })
    backups.sort(key=lambda b: b['mtime'], reverse=True)
    return backups


def recover_from_backup(db_path: str, backup_path: str) -> dict:
    """从备份恢复 DB

    流程:
    1. 备份当前 DB 到 .recover-backup-{timestamp}.bak (安全网)
    2. 从 backup_path 恢复到 db_path
    3. 验证恢复后完整性
    """
    backup_dir = os.path.dirname(backup_path)
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    safety_name = f'architecture.db.recover-backup-{timestamp}.bak'
    safety_path = os.path.join(backup_dir, safety_name)

    result = {'steps': []}

    # Step 1: 验证备份完整性
    try:
        check_conn = sqlite3.connect(backup_path, timeout=5)
        try:
            backup_integrity = check_conn.execute('PRAGMA integrity_check').fetchone()[0]
        finally:
            check_conn.close()
        if backup_integrity != 'ok':
            return {
                'success': False,
                'error': f'备份 integrity_check 失败: {backup_integrity}',
                'steps': result['steps'],
            }
        result['steps'].append(f'备份验证 OK: {backup_integrity}')
    except Exception as e:
        return {
            'success': False,
            'error': f'备份验证失败: {e}',
            'steps': result['steps'],
        }

    # Step 2: 备份当前 DB (安全网)
    try:
        source = sqlite3.connect(db_path, timeout=30)
        dest = sqlite3.connect(safety_path, timeout=30)
        try:
            source.backup(dest)
        finally:
            source.close()
            dest.close()
        result['steps'].append(f'当前 DB 备份到: {safety_name}')
    except Exception as e:
        return {
            'success': False,
            'error': f'安全网备份失败: {e}',
            'steps': result['steps'],
        }

    # Step 3: 从备份恢复
    try:
        source = sqlite3.connect(backup_path, timeout=30)
        dest = sqlite3.connect(db_path, timeout=30)
        try:
            source.backup(dest)
        finally:
            source.close()
            dest.close()
        result['steps'].append(f'从 {os.path.basename(backup_path)} 恢复到 {os.path.basename(db_path)}')
    except Exception as e:
        return {
            'success': False,
            'error': f'恢复失败: {e}',
            'safety_path': safety_path,
            'steps': result['steps'],
        }

    # Step 4: 验证恢复后
    try:
        check_conn = sqlite3.connect(db_path, timeout=5)
        try:
            after_integrity = check_conn.execute('PRAGMA integrity_check').fetchone()[0]
        finally:
            check_conn.close()
        result['integrity_after'] = after_integrity
        result['steps'].append(f'恢复后 integrity_check: {after_integrity}')
    except Exception as e:
        return {
            'success': False,
            'error': f'恢复后验证失败: {e}',
            'safety_path': safety_path,
            'steps': result['steps'],
        }

    result['success'] = True
    result['safety_path'] = safety_path
    return result


def main():
    parser = argparse.ArgumentParser(
        description='DB 异常恢复 - DB 损坏预防方案 3/3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--db', default=DEFAULT_DB, help=f'数据库路径 (默认: {DEFAULT_DB})')
    parser.add_argument('--backup-dir', default=DEFAULT_BACKUP_DIR, help=f'备份目录 (默认: {DEFAULT_BACKUP_DIR})')
    parser.add_argument('--diagnose', action='store_true', help='仅诊断, 不恢复')
    parser.add_argument('--auto', action='store_true', help='自动从最新备份恢复')
    parser.add_argument('--from-backup', metavar='FILENAME', help='从指定备份恢复')
    args = parser.parse_args()

    print(f'━' * 70)
    print(f'[DECORATIVE] v3.16: DB 异常恢复')
    print(f'━' * 70)
    print(f'数据库: {args.db}')
    print(f'备份目录: {args.backup_dir}')
    print(f'时间: {datetime.now().isoformat()}')
    print()

    # 1. 诊断
    print('━━━ 1. 诊断 ━━━')
    diag = diagnose(args.db)
    for name, check in diag['checks'].items():
        icon = {'pass': '[OK]', 'warn': '[WARNING]', 'fail': '[X]'}.get(check['status'], '?')
        print(f'  {icon} {name:20s} {check["status"]:6s} {check["detail"]}')
    print()
    print(f'整体: {"[OK] 健康" if diag["healthy"] else "[X] 异常"}')
    print(f'推荐: {diag["recommendation"]}')
    print()

    if args.diagnose:
        return 0 if diag['healthy'] else 1

    if diag['healthy']:
        print('[OK] DB 健康, 无需恢复')
        return 0

    # 2. 选备份
    print('━━━ 2. 选择备份 ━━━')
    backups = list_backups(args.backup_dir)
    if not backups:
        print(f'[X] 备份目录为空: {args.backup_dir}')
        return 3

    print(f'  找到 {len(backups)} 个备份 (最新 5):')
    for i, b in enumerate(backups[:5]):
        print(f'    {i+1}. {b["filename"]} ({_format_size(b["size"])}, '
              f'{datetime.fromtimestamp(b["mtime"]).isoformat()})')
    print()

    if args.from_backup:
        target = None
        for b in backups:
            if b['filename'] == args.from_backup:
                target = b
                break
        if not target:
            print(f'[X] 指定备份不存在: {args.from_backup}')
            return 3
        backup_path = target['path']
        print(f'  使用指定备份: {args.from_backup}')
    elif args.auto:
        target = backups[0]  # 最新
        backup_path = target['path']
        print(f'  自动使用最新备份: {target["filename"]}')
    else:
        print('  干跑模式 - 不执行恢复')
        print(f'  推荐: 用 --auto 自动恢复, 或 --from-backup <filename> 指定')
        return 1

    # 3. 恢复
    print()
    print('━━━ 3. 恢复 ━━━')
    result = recover_from_backup(args.db, backup_path)
    for step in result.get('steps', []):
        print(f'  → {step}')
    print()

    if not result.get('success'):
        print(f'[X] 恢复失败: {result.get("error")}')
        if 'safety_path' in result:
            print(f'  之前状态已保存到: {result["safety_path"]}')
        return 3

    print(f'[OK] 恢复成功')
    print(f'  恢复前状态: {result.get("safety_path", "N/A")}')
    print(f'  恢复后完整性: {result.get("integrity_after", "unknown")}')
    return 2


if __name__ == '__main__':
    sys.exit(main())
