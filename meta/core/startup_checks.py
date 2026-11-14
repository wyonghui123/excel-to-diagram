# -*- coding: utf-8 -*-
import json
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def collect_checks():
    """[FR-014] 收集全部启动自检项（只读，不抛异常）。"""
    return [
        _check_debug_mode(),
        _check_jwt_secret(),
        _check_flask_secret_key(),
        _check_cors_config(),
        _check_admin_password(),
    ]


def format_startup_report(results):
    """[FR-014] 启动自检结构化结果（JSON 可序列化，供 CLI/日志/告警消费）。"""
    errors = [r for r in results if r.get('level') == 'ERROR']
    warnings = [r for r in results if r.get('level') == 'WARNING']
    oks = [r for r in results if r.get('level') == 'OK']
    return {
        'event': 'startup_check',
        'success': not errors,
        'mode': 'production' if not _is_production_safe() else 'development',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'exit_code': 1 if errors else 0,
        'summary': {
            'total': len(results),
            'ok': len(oks),
            'warning': len(warnings),
            'error': len(errors),
        },
        'checks': [
            {
                'name': r.get('name'),
                'level': r.get('level'),
                'error_code': r.get('error_code'),
                'message': r.get('message'),
                'suggestion': r.get('suggestion'),
            }
            for r in results
        ],
    }


def run_startup_checks(app):
    results = collect_checks()
    report = format_startup_report(results)
    logger.info('[StartupCheck] %s', json.dumps(report, ensure_ascii=False))

    warnings = [r for r in results if r.get('level') == 'WARNING']
    errors = [r for r in results if r.get('level') == 'ERROR']

    if errors:
        logger.error("[StartupCheck] CRITICAL security issues found:")
        for e in errors:
            logger.error(f"  - {e['message']}")
        if not _is_production_safe():
            # [FR-014] 生产环境自检失败可选上报告警（best-effort，不阻断启动判定）
            try:
                from meta.core.alert_service import report_alert
                for e in errors:
                    report_alert(
                        e.get('error_code') or 'startup_check_failed',
                        object_type='startup',
                        message=e.get('message') or '',
                        level='critical',
                    )
            except Exception:
                logger.debug('[StartupCheck] 告警上报失败', exc_info=True)
            raise RuntimeError(
                "Production mode requires all startup security checks to pass. "
                "Fix the issues above or set FLASK_DEBUG=true or TESTING=true for development."
            )

    if warnings:
        logger.warning("[StartupCheck] Security warnings:")
        for w in warnings:
            logger.warning(f"  - {w['message']}")

    logger.info(f"[StartupCheck] Completed: {len(errors)} errors, {len(warnings)} warnings")
    return results


def _is_debug():
    # [BUG-FIX V007.36] 默认值 'True' 跟 server.py:983 一致
    # 之前默认 'false' 导致手动启动 server.py 时, _is_production_safe() 错判为生产模式,
    # 在没有 .env (JWT_SECRET_KEY) 时阻断启动. deploy.sh 启动时显式设了 FLASK_DEBUG=false
    # 掩盖了此 bug, 直到 2026-07-07 23:51 手动启动才暴露.
    return os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'


def _is_testing():
    return os.environ.get('TESTING', 'false').lower() == 'true'


def _is_production_safe():
    if _is_debug():
        return True
    if _is_testing():
        return True
    flask_debug = os.environ.get('FLASK_DEBUG', '').lower()
    if flask_debug == 'false':
        return False
    return False


def _result(name, level, message, error_code=None, suggestion=None):
    """[FR-014] 统一自检项结构：name/level/error_code/message/suggestion。"""
    return {
        'name': name,
        'level': level,
        'error_code': error_code if level != 'OK' else None,
        'message': message,
        'suggestion': suggestion if level != 'OK' else None,
    }


def _check_debug_mode():
    flask_debug = os.environ.get('FLASK_DEBUG', 'false').lower()
    if flask_debug == 'true':
        return _result(
            'debug_mode', 'WARNING',
            'FLASK_DEBUG=true is set, should not be used in production',
            error_code='startup_debug_enabled',
            suggestion='生产环境设置 FLASK_DEBUG=false 并重启服务',
        )
    return _result('debug_mode', 'OK', 'DEBUG mode is off (production)')


def _check_jwt_secret():
    secret = os.environ.get('JWT_SECRET_KEY', '')
    if not secret or secret == 'your-secret-key-change-in-production':
        msg = 'JWT_SECRET_KEY is not set or is using default value'
        level = 'WARNING' if _is_production_safe() else 'ERROR'
        return _result(
            'jwt_secret', level, msg, error_code='startup_jwt_secret_invalid',
            suggestion='设置长度 >= 32 的随机 JWT_SECRET_KEY 后重启服务（生产环境必填）',
        )
    if len(secret) < 32:
        msg = 'JWT_SECRET_KEY is shorter than 32 characters'
        level = 'WARNING' if _is_production_safe() else 'ERROR'
        return _result(
            'jwt_secret', level, msg, error_code='startup_jwt_secret_invalid',
            suggestion='把 JWT_SECRET_KEY 替换为长度 >= 32 的随机字符串',
        )
    return _result('jwt_secret', 'OK', 'JWT_SECRET_KEY is properly configured')


def _check_flask_secret_key():
    """v1.4 修复：生产环境强制要求 secret_key

    Flask session 依赖 secret_key 签名。如果生产环境使用默认值，
    session 可被伪造 → 权限绕过。OWASP A02:2021。
    """
    secret = (
        os.environ.get('FLASK_SECRET_KEY', '')
        or os.environ.get('JWT_SECRET_KEY', '')
    )
    DEFAULT_DEV_SECRET = 'dev-secret-key-change-in-prod'

    if not secret:
        msg = 'FLASK_SECRET_KEY/JWT_SECRET_KEY is not set'
        level = 'WARNING' if _is_production_safe() else 'ERROR'
        return _result(
            'flask_secret_key', level, msg, error_code='startup_flask_secret_missing',
            suggestion='设置 FLASK_SECRET_KEY（或 JWT_SECRET_KEY）为长度 >= 32 的随机字符串',
        )

    if secret == DEFAULT_DEV_SECRET:
        msg = f'FLASK_SECRET_KEY is using default value ({DEFAULT_DEV_SECRET})'
        level = 'WARNING' if _is_production_safe() else 'ERROR'
        return _result(
            'flask_secret_key', level, msg, error_code='startup_flask_secret_default',
            suggestion='把 FLASK_SECRET_KEY 替换为非默认的随机值（生产环境禁止默认密钥）',
        )

    if len(secret) < 32:
        msg = f'FLASK_SECRET_KEY is shorter than 32 characters (length={len(secret)})'
        level = 'WARNING' if _is_production_safe() else 'ERROR'
        return _result(
            'flask_secret_key', level, msg, error_code='startup_flask_secret_weak',
            suggestion='把 FLASK_SECRET_KEY 替换为长度 >= 32 的随机字符串',
        )

    return _result('flask_secret_key', 'OK',
                   f'FLASK_SECRET_KEY is properly configured (length={len(secret)})')


def _check_cors_config():
    origins = os.environ.get('CORS_ALLOWED_ORIGINS', '')
    if not origins or origins.strip() == '':
        if _is_production_safe():
            return _result(
                'cors_config', 'WARNING',
                'CORS_ALLOWED_ORIGINS is empty (OK for dev, insecure for production)',
                error_code='startup_cors_missing',
                suggestion='生产环境设置 CORS_ALLOWED_ORIGINS 为允许的前端来源（逗号分隔）',
            )
        return _result(
            'cors_config', 'ERROR',
            'CORS_ALLOWED_ORIGINS must be configured in production mode',
            error_code='startup_cors_missing',
            suggestion='设置 CORS_ALLOWED_ORIGINS=https://<前端域名> 后重启服务',
        )
    return _result('cors_config', 'OK', 'CORS_ALLOWED_ORIGINS is configured')


def _check_admin_password():
    admin_pass = os.environ.get('ADMIN_PASSWORD', '')
    if not admin_pass:
        if _is_production_safe():
            return _result('admin_password', 'OK',
                           'ADMIN_PASSWORD not set (using default for dev)')
        return _result(
            'admin_password', 'WARNING', 'ADMIN_PASSWORD is not set',
            error_code='startup_admin_password_missing',
            suggestion='生产环境设置 ADMIN_PASSWORD 为强密码后重启服务',
        )
    return _result('admin_password', 'OK', 'ADMIN_PASSWORD is configured')


def main(argv=None):
    """[FR-014] CLI 入口：python -m meta.core.startup_checks [--json]

    退出码：存在 ERROR 时返回 1，否则 0（WARNING 不算失败）。
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(description='启动自检（结构化输出）')
    parser.add_argument('--json', action='store_true', help='以单行 JSON 输出，便于脚本消费')
    args, _unknown = parser.parse_known_args(argv)

    report = format_startup_report(collect_checks())
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        for item in report['checks']:
            print(f"[{item['level']}] {item['name']}: {item['message']}")
            if item.get('suggestion'):
                print(f"    建议: {item['suggestion']}")
        print(f"结果: {report['summary']}")
    return report['exit_code']


if __name__ == '__main__':
    import sys

    sys.exit(main())
