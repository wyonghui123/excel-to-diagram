# -*- coding: utf-8 -*-
"""第三方集成 API（P0-1）

契约：
  POST /api/v2/integrations/ai/validate          body {provider, messages, model?} → {valid, content, issues}
  POST /api/v2/integrations/feishu/request       body {method, path, query?, body?, file?} → 上游 JSON
  POST /api/v2/integrations/feishu/test          连通性自检
  GET  /api/v2/system/settings/integrations      脱敏配置视图（secret 永不下发）

所有端点仅要求登录；密钥在后端，前端不再传任何 secret。
"""
import logging

from flask import Blueprint, request

from meta.api._response_contract import error_response, ok
from meta.services.auth_middleware import login_required
from meta.services.integration_credential_service import (
    IntegrationConfigError,
    IntegrationUpstreamError,
    integration_credential_service,
)

logger = logging.getLogger(__name__)

integration_bp = Blueprint('integration_api', __name__)


@integration_bp.route('/api/v2/integrations/ai/validate', methods=['POST'])
@login_required
def validate_ai():
    payload = request.get_json(silent=True) or {}
    provider = (payload.get('provider') or '').strip().lower()
    messages = payload.get('messages')
    if not provider or not isinstance(messages, list) or not messages:
        return error_response(
            'provider 与 messages 必填', code='INVALID_REQUEST', status=400
        )
    try:
        result = integration_credential_service.validate_ai(
            provider,
            messages,
            model=payload.get('model'),
            max_tokens=payload.get('max_tokens'),
        )
    except IntegrationConfigError as exc:
        return ok({
            'valid': False,
            'provider': provider,
            'issues': [{'level': 'error', 'message': str(exc)}],
        })
    except IntegrationUpstreamError as exc:
        return ok({
            'valid': False,
            'provider': provider,
            'issues': [{'level': 'error', 'message': str(exc)}],
        })
    return ok(result)


@integration_bp.route('/api/v2/integrations/feishu/request', methods=['POST'])
@login_required
def feishu_request():
    payload = request.get_json(silent=True) or {}
    try:
        upstream = integration_credential_service.feishu_request(
            method=payload.get('method') or 'GET',
            path=payload.get('path') or '',
            query=payload.get('query'),
            body=payload.get('body'),
            file_payload=payload.get('file'),
        )
    except IntegrationConfigError as exc:
        return error_response(str(exc), code='INTEGRATION_CONFIG', status=400)
    except IntegrationUpstreamError as exc:
        return error_response(str(exc), code='INTEGRATION_UPSTREAM', status=502)
    return ok(upstream)


@integration_bp.route('/api/v2/integrations/feishu/test', methods=['POST'])
@login_required
def feishu_test():
    try:
        result = integration_credential_service.feishu_test()
    except IntegrationConfigError as exc:
        return ok({
            'valid': False,
            'issues': [{'level': 'error', 'message': str(exc)}],
        })
    except IntegrationUpstreamError as exc:
        return ok({
            'valid': False,
            'issues': [{'level': 'error', 'message': str(exc)}],
        })
    return ok(result)


@integration_bp.route('/api/v2/system/settings/integrations', methods=['GET'])
@login_required
def get_integration_settings():
    return ok(integration_credential_service.get_settings())