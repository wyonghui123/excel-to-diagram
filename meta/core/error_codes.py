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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 枚举管理 (v3.18 enum-mgmt-spec)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 详见 docs/specs/spec-enum-mgmt-v1.0.md
    ENUM_TYPE_LOCKED = 'enum_type_locked'                        # 200 false - mutability=locked 拒绝
    ENUM_VALUE_LOCKED = 'enum_value_locked'                      # 200 false - mutability=locked 拒绝
    SYSTEM_VALUE_IMMUTABLE = 'system_value_immutable'            # 200 false - is_system=true 拒绝 update/delete
    SYSTEM_ENUM_IMMUTABLE = 'system_enum_immutable'              # 200 false - category=system 拒绝 update/delete
    INVALID_MUTABILITY = 'invalid_mutability'                    # 400 - mutability 值不在 3 档内
    INVALID_CODE_FORMAT = 'invalid_code_format'                  # 400 - code 不符合 ^[A-Z][A-Z0-9_]*$
    CODE_IMMUTABLE = 'code_immutable'                            # 400 - enum_value.code 不可改
    ID_IMMUTABLE = 'id_immutable'                                # 400 - enum_type.id 不可改
    DUPLICATE_CODE = 'duplicate_code'                            # 400 - (enum_type_id, code) 重复
    DUPLICATE_NAME = 'duplicate_name'                            # 400 - (enum_type_id, name) 重复
    HAS_VALUES = 'has_values'                                    # 400 - 删除 enum_type 时仍有 enum_value
    MUTABILITY_CHANGE_REQUIRES_SUPER_ADMIN = 'mutability_change_requires_super_admin'  # 403
    MISSING_DIMENSION_KEY = 'missing_dimension_key'              # 400
    INVALID_DIMENSION_KEY = 'invalid_dimension_key'              # 400
    INVALID_DIMENSION_VALUE = 'invalid_dimension_value'          # 400

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 平台级附件 (v269 2026-11-13 attachment-platform)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 详见 docs/specs/spec-platform-attachment-2026-11-13.md §6.7
    ATTACHMENT_NOT_FOUND = 'attachment_not_found'                                # 404
    ATTACHMENT_LINK_NOT_FOUND = 'attachment_link_not_found'                      # 404
    ATTACHMENT_TARGET_INVALID = 'attachment_target_invalid'                      # 400
    ATTACHMENT_TOO_LARGE = 'attachment_too_large'                                # 400（Flask 层 413 同码）
    ATTACHMENT_LIMIT_EXCEEDED = 'attachment_limit_exceeded'                      # 400
    ATTACHMENT_INVALID_MIME = 'attachment_invalid_mime'                          # 400
    ATTACHMENT_DUPLICATE_LINK = 'attachment_duplicate_link'                      # 200 false
    ATTACHMENT_DUPLICATE_PRIMARY = 'attachment_duplicate_primary'                # 200 false
    ATTACHMENT_IN_USE = 'attachment_in_use'                                      # 200 false
    ATTACHMENT_MISSING_FILE = 'attachment_missing_file'                          # 410
    ATTACHMENT_STORAGE_ERROR = 'attachment_storage_error'                        # 500
    ATTACHMENT_TARGET_DELETED = 'attachment_target_deleted'                      # 400
    ATTACHMENT_VISIBILITY_UNSUPPORTED = 'attachment_visibility_unsupported'      # 400

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 传输 / 框架层 (v3.8 统一错误出口)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    BAD_REQUEST = 'bad_request'                # 400 - 请求体非法 / 参数缺失
    NOT_FOUND = 'not_found'                    # 404 - 路由或资源不存在
    METHOD_NOT_ALLOWED = 'method_not_allowed'  # 405 - 方法不允许
    UNPROCESSABLE_ENTITY = 'unprocessable_entity'  # 422 - 语义校验失败
    INVALID_QUERY = 'invalid_query'            # 400 - 查询条件非法
    STALE_SESSION = 'stale_session'            # 401 - 会话已失效（用户/角色被重置）

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 系统 / 可观测 (v3.8 告警体系)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    DB_LOCKED = 'db_locked'                    # 503 - 数据库锁等待超时
    STORAGE_ERROR = 'storage_error'            # 500 - 文件存储异常
    SCHEDULER_JOB_FAILED = 'scheduler_job_failed'    # 500 - 调度任务失败
    AUDIT_WRITE_FAILED = 'audit_write_failed'        # 500 - 审计写入失败
    ALERT_DELIVERY_FAILED = 'alert_delivery_failed'  # 500 - 告警投递失败
    CONTRACT_VIOLATION = 'contract_violation'        # 500 - 响应契约自检失败
    STATE_MACHINE_VIOLATION = 'STATE_MACHINE_VIOLATION'  # 400 - 状态机拒绝（历史大写，保持兼容）
    VALUE_HELP_VALIDATION_FAILED = 'VALUE_HELP_VALIDATION_FAILED'  # 400 - 值帮助校验失败（历史大写）
    DEEP_INSERT_FAILED = 'DEEP_INSERT_FAILED'        # 400 - Deep Insert 失败（历史大写）
    TRANSACTION_ROLLBACK = 'TRANSACTION_ROLLBACK'    # 409 - 事务已回滚（历史大写）


# 用于脚本生成的常量
ALL_CODES = [c.value for c in ErrorCode]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 错误码 → 默认 HTTP 状态（唯一真源，供 error_response / 前端生成器使用）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ERROR_HTTP_STATUS = {
    # 鉴权
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.TOKEN_BLACKLISTED: 401,
    ErrorCode.AUTH_SERVICE_ERROR: 401,
    ErrorCode.STALE_SESSION: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.ADMIN_REQUIRED: 403,
    # Action
    ErrorCode.ACTION_NOT_FOUND: 404,
    ErrorCode.ACTION_VALIDATION_ERROR: 400,
    ErrorCode.ACTION_HANDLER_ERROR: 500,
    ErrorCode.ACTION_PARAMS_MISSING: 400,
    ErrorCode.ACTION_PERMISSION_DENIED: 403,
    # Subflow
    ErrorCode.SUBFLOW_EMPTY: 400,
    ErrorCode.SUBFLOW_STEP_FAILED: 400,
    ErrorCode.SUBFLOW_ATOMIC_FAILED: 400,
    ErrorCode.SUBFLOW_TRANSACTION_FAILED: 400,
    ErrorCode.SUBFLOW_STEP_TIMEOUT: 400,
    ErrorCode.SUBFLOW_DRY_RUN: 200,
    ErrorCode.SUBFLOW_TEMPLATE_NOT_FOUND: 404,
    # 服务端
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.DB_ERROR: 500,
    ErrorCode.NETWORK_ERROR: 500,
    ErrorCode.TIMEOUT_ERROR: 500,
    # 数据
    ErrorCode.DATA_NOT_FOUND: 404,
    ErrorCode.DATA_CONFLICT: 409,
    ErrorCode.DATA_INVALID: 400,
    ErrorCode.DATA_REFERENCED: 409,
    # 文件流
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.FILE_GENERATION_FAILED: 500,
    # 枚举管理
    ErrorCode.ENUM_TYPE_LOCKED: 400,
    ErrorCode.ENUM_VALUE_LOCKED: 400,
    ErrorCode.SYSTEM_VALUE_IMMUTABLE: 400,
    ErrorCode.SYSTEM_ENUM_IMMUTABLE: 400,
    ErrorCode.INVALID_MUTABILITY: 400,
    ErrorCode.INVALID_CODE_FORMAT: 400,
    ErrorCode.CODE_IMMUTABLE: 400,
    ErrorCode.ID_IMMUTABLE: 400,
    ErrorCode.DUPLICATE_CODE: 400,
    ErrorCode.DUPLICATE_NAME: 400,
    ErrorCode.HAS_VALUES: 400,
    ErrorCode.MUTABILITY_CHANGE_REQUIRES_SUPER_ADMIN: 403,
    ErrorCode.MISSING_DIMENSION_KEY: 400,
    ErrorCode.INVALID_DIMENSION_KEY: 400,
    ErrorCode.INVALID_DIMENSION_VALUE: 400,
    # 附件
    ErrorCode.ATTACHMENT_NOT_FOUND: 404,
    ErrorCode.ATTACHMENT_LINK_NOT_FOUND: 404,
    ErrorCode.ATTACHMENT_TARGET_INVALID: 400,
    ErrorCode.ATTACHMENT_TOO_LARGE: 413,
    ErrorCode.ATTACHMENT_LIMIT_EXCEEDED: 400,
    ErrorCode.ATTACHMENT_INVALID_MIME: 400,
    ErrorCode.ATTACHMENT_DUPLICATE_LINK: 400,
    ErrorCode.ATTACHMENT_DUPLICATE_PRIMARY: 400,
    ErrorCode.ATTACHMENT_IN_USE: 409,
    ErrorCode.ATTACHMENT_MISSING_FILE: 410,
    ErrorCode.ATTACHMENT_STORAGE_ERROR: 500,
    ErrorCode.ATTACHMENT_TARGET_DELETED: 400,
    ErrorCode.ATTACHMENT_VISIBILITY_UNSUPPORTED: 400,
    # 传输 / 框架层
    ErrorCode.BAD_REQUEST: 400,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.METHOD_NOT_ALLOWED: 405,
    ErrorCode.UNPROCESSABLE_ENTITY: 422,
    ErrorCode.INVALID_QUERY: 400,
    # 系统 / 可观测
    ErrorCode.DB_LOCKED: 503,
    ErrorCode.STORAGE_ERROR: 500,
    ErrorCode.SCHEDULER_JOB_FAILED: 500,
    ErrorCode.AUDIT_WRITE_FAILED: 500,
    ErrorCode.ALERT_DELIVERY_FAILED: 500,
    ErrorCode.CONTRACT_VIOLATION: 500,
    ErrorCode.STATE_MACHINE_VIOLATION: 400,
    ErrorCode.VALUE_HELP_VALIDATION_FAILED: 400,
    ErrorCode.DEEP_INSERT_FAILED: 400,
    ErrorCode.TRANSACTION_ROLLBACK: 409,
}

# 统一转换为字符串键，允许 error_response 直接以 code 字符串查询
ERROR_HTTP_STATUS = {code.value: status for code, status in ERROR_HTTP_STATUS.items()}

# HTTP 状态 → 通用错误码（框架层异常兜底）
HTTP_TO_ERROR_CODE = {
    400: ErrorCode.BAD_REQUEST.value,
    401: ErrorCode.UNAUTHORIZED.value,
    403: ErrorCode.FORBIDDEN.value,
    404: ErrorCode.NOT_FOUND.value,
    405: ErrorCode.METHOD_NOT_ALLOWED.value,
    413: ErrorCode.FILE_TOO_LARGE.value,
    422: ErrorCode.UNPROCESSABLE_ENTITY.value,
    500: ErrorCode.INTERNAL_ERROR.value,
    503: ErrorCode.DB_LOCKED.value,
}

# 启动期自检：映射必须覆盖全部码（缺漏只告警，由 contract test 强制）
import logging as _logging

# ERROR_HTTP_STATUS 已在上面转成字符串键，键集即已覆盖的错误码
_missing_status = sorted(set(ALL_CODES) - set(ERROR_HTTP_STATUS))
if _missing_status:
    _logging.getLogger(__name__).warning(
        "ERROR_HTTP_STATUS 缺少错误码映射: %s", _missing_status
    )
