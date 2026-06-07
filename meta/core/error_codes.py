# -*- coding: utf-8 -*-
"""
BO Action 统一错误码 (v3.7)
==============================

后端所有 endpoint 返回的 `code` 字段常量。
前端 useBoAction.js 自动生成 TS enum。
"""
from enum import Enum


class ErrorCode(str, Enum):
    """
    统一错误码
    - 鉴权类: 401/403 (HTTP status)
    - 业务类: 200 (success: false) 或 4xx
    - 服务类: 500
    """

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 鉴权 (401/403)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    UNAUTHORIZED = 'unauthorized'              # 401 - 未登录
    TOKEN_EXPIRED = 'token_expired'          # 401 - token 过期
    TOKEN_BLACKLISTED = 'token_blacklisted'  # 401 - token 已失效
    AUTH_SERVICE_ERROR = 'auth_service_error'  # 401 - 认证服务异常
    FORBIDDEN = 'forbidden'                   # 403 - 权限不足
    ADMIN_REQUIRED = 'admin_required'         # 403 - 需要 admin 权限

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Action 业务 (200 false / 404)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ACTION_NOT_FOUND = 'action_not_found'              # 404
    ACTION_VALIDATION_ERROR = 'action_validation_error'  # 200 false
    ACTION_HANDLER_ERROR = 'action_handler_error'      # 200 false
    ACTION_PARAMS_MISSING = 'action_params_missing'    # 200 false
    ACTION_PERMISSION_DENIED = 'action_permission_denied'  # 200 false

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Subflow (200 false / 400)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    SUBFLOW_EMPTY = 'subflow_empty'                  # 400 - steps 为空
    SUBFLOW_STEP_FAILED = 'subflow_step_failed'      # 200 false - 步骤失败
    SUBFLOW_ATOMIC_FAILED = 'subflow_atomic_failed'  # 200 false - 原子失败
    SUBFLOW_TRANSACTION_FAILED = 'subflow_transaction_failed'  # 200 false
    SUBFLOW_STEP_TIMEOUT = 'subflow_step_timeout'    # 200 false
    SUBFLOW_DRY_RUN = 'subflow_dry_run'              # 200 success (preview)
    SUBFLOW_TEMPLATE_NOT_FOUND = 'subflow_template_not_found'  # 200 false

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 服务端 (500)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    INTERNAL_ERROR = 'internal_error'        # 500
    DB_ERROR = 'db_error'                   # 500
    NETWORK_ERROR = 'network_error'         # 500
    TIMEOUT_ERROR = 'timeout_error'         # 500

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 数据 (200 false)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    DATA_NOT_FOUND = 'data_not_found'        # 200 false
    DATA_CONFLICT = 'data_conflict'          # 200 false (duplicate key)
    DATA_INVALID = 'data_invalid'            # 200 false
    DATA_REFERENCED = 'data_referenced'      # 200 false (FK constraint)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 文件流
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    FILE_TOO_LARGE = 'file_too_large'        # 200 false
    FILE_GENERATION_FAILED = 'file_generation_failed'  # 200 false


# 用于脚本生成的常量
ALL_CODES = [c.value for c in ErrorCode]
