# -*- coding: utf-8 -*-
import os
import logging

logger = logging.getLogger(__name__)


def run_startup_checks(app):
    results = []
    results.append(_check_debug_mode())
    results.append(_check_jwt_secret())
    results.append(_check_flask_secret_key())
    results.append(_check_cors_config())
    results.append(_check_admin_password())

    warnings = [r for r in results if r.get('level') == 'WARNING']
    errors = [r for r in results if r.get('level') == 'ERROR']

    if errors:
        logger.error("[StartupCheck] CRITICAL security issues found:")
        for e in errors:
            logger.error(f"  - {e['message']}")
        if not _is_production_safe():
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
    return os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'


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


def _check_debug_mode():
    flask_debug = os.environ.get('FLASK_DEBUG', 'false').lower()
    if flask_debug == 'true':
        return {'level': 'WARNING', 'message': 'FLASK_DEBUG=true is set, should not be used in production'}
    return {'level': 'OK', 'message': 'DEBUG mode is off (production)'}


def _check_jwt_secret():
    secret = os.environ.get('JWT_SECRET_KEY', '')
    if not secret or secret == 'your-secret-key-change-in-production':
        msg = 'JWT_SECRET_KEY is not set or is using default value'
        if _is_production_safe():
            return {'level': 'WARNING', 'message': msg}
        return {'level': 'ERROR', 'message': msg}
    if len(secret) < 32:
        msg = 'JWT_SECRET_KEY is shorter than 32 characters'
        if _is_production_safe():
            return {'level': 'WARNING', 'message': msg}
        return {'level': 'ERROR', 'message': msg}
    return {'level': 'OK', 'message': 'JWT_SECRET_KEY is properly configured'}


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
        if _is_production_safe():
            return {'level': 'WARNING', 'message': msg}
        return {'level': 'ERROR', 'message': msg}

    if secret == DEFAULT_DEV_SECRET:
        msg = f'FLASK_SECRET_KEY is using default value ({DEFAULT_DEV_SECRET})'
        if _is_production_safe():
            return {'level': 'WARNING', 'message': msg}
        return {'level': 'ERROR', 'message': msg}

    if len(secret) < 32:
        msg = f'FLASK_SECRET_KEY is shorter than 32 characters (length={len(secret)})'
        if _is_production_safe():
            return {'level': 'WARNING', 'message': msg}
        return {'level': 'ERROR', 'message': msg}

    return {'level': 'OK', 'message': f'FLASK_SECRET_KEY is properly configured (length={len(secret)})'}


def _check_cors_config():
    origins = os.environ.get('CORS_ALLOWED_ORIGINS', '')
    if not origins or origins.strip() == '':
        if _is_production_safe():
            return {'level': 'WARNING', 'message': 'CORS_ALLOWED_ORIGINS is empty (OK for dev, insecure for production)'}
        return {'level': 'ERROR', 'message': 'CORS_ALLOWED_ORIGINS must be configured in production mode'}
    return {'level': 'OK', 'message': 'CORS_ALLOWED_ORIGINS is configured'}


def _check_admin_password():
    admin_pass = os.environ.get('ADMIN_PASSWORD', '')
    if not admin_pass:
        if _is_production_safe():
            return {'level': 'OK', 'message': 'ADMIN_PASSWORD not set (using default for dev)'}
        return {'level': 'WARNING', 'message': 'ADMIN_PASSWORD is not set'}
    return {'level': 'OK', 'message': 'ADMIN_PASSWORD is configured'}
