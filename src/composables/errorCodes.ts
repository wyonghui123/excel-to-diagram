// Auto-generated from meta/core/error_codes.py
// DO NOT EDIT MANUALLY
// Date: 2026-06-06T01:54:57.275Z
//
// ⚠️ 命名约定：
//   - `ErrorCodes`（带 s）是运行时枚举值（30 个业务错误，lowercase snake_case）
//   - `ErrorCode`（无 s）是 TypeScript 类型（值联合）
//   - 这与 '@/utils/httpClient' 的 ErrorCode（HTTP 传输层，UPPER_SNAKE）不同源，
//     业务代码请勿混用。
// ---------------------------------------------------------------------------

export const ErrorCodes = {
  UNAUTHORIZED: 'unauthorized',
  TOKEN_EXPIRED: 'token_expired',
  TOKEN_BLACKLISTED: 'token_blacklisted',
  AUTH_SERVICE_ERROR: 'auth_service_error',
  FORBIDDEN: 'forbidden',
  ADMIN_REQUIRED: 'admin_required',
  ACTION_NOT_FOUND: 'action_not_found',
  ACTION_VALIDATION_ERROR: 'action_validation_error',
  ACTION_HANDLER_ERROR: 'action_handler_error',
  ACTION_PARAMS_MISSING: 'action_params_missing',
  ACTION_PERMISSION_DENIED: 'action_permission_denied',
  SUBFLOW_EMPTY: 'subflow_empty',
  SUBFLOW_STEP_FAILED: 'subflow_step_failed',
  SUBFLOW_ATOMIC_FAILED: 'subflow_atomic_failed',
  SUBFLOW_TRANSACTION_FAILED: 'subflow_transaction_failed',
  SUBFLOW_STEP_TIMEOUT: 'subflow_step_timeout',
  SUBFLOW_DRY_RUN: 'subflow_dry_run',
  SUBFLOW_TEMPLATE_NOT_FOUND: 'subflow_template_not_found',
  INTERNAL_ERROR: 'internal_error',
  DB_ERROR: 'db_error',
  NETWORK_ERROR: 'network_error',
  TIMEOUT_ERROR: 'timeout_error',
  DATA_NOT_FOUND: 'data_not_found',
  DATA_CONFLICT: 'data_conflict',
  DATA_INVALID: 'data_invalid',
  DATA_REFERENCED: 'data_referenced',
  FILE_TOO_LARGE: 'file_too_large',
  FILE_GENERATION_FAILED: 'file_generation_failed',
} as const;

export type ErrorCode = typeof ErrorCodes[keyof typeof ErrorCodes]

// HTTP status 映射
export const ErrorCodeHttpStatus: Record<ErrorCode, number> = {
  UNAUTHORIZED: 401,
  TOKEN_EXPIRED: 401,
  TOKEN_BLACKLISTED: 401,
  AUTH_SERVICE_ERROR: 401,
  FORBIDDEN: 403,
  ADMIN_REQUIRED: 403,
  ACTION_NOT_FOUND: 404,
  ACTION_VALIDATION_ERROR: 200,
  ACTION_HANDLER_ERROR: 200,
  ACTION_PARAMS_MISSING: 200,
  ACTION_PERMISSION_DENIED: 200,
  SUBFLOW_EMPTY: 400,
  SUBFLOW_STEP_FAILED: 200,
  SUBFLOW_ATOMIC_FAILED: 200,
  SUBFLOW_TRANSACTION_FAILED: 200,
  SUBFLOW_STEP_TIMEOUT: 200,
  SUBFLOW_DRY_RUN: 200,
  SUBFLOW_TEMPLATE_NOT_FOUND: 200,
  INTERNAL_ERROR: 500,
  DB_ERROR: 500,
  NETWORK_ERROR: 500,
  TIMEOUT_ERROR: 500,
  DATA_NOT_FOUND: 200,
  DATA_CONFLICT: 200,
  DATA_INVALID: 200,
  DATA_REFERENCED: 200,
  FILE_TOO_LARGE: 200,
  FILE_GENERATION_FAILED: 200,
};
