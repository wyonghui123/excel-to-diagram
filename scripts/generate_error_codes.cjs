#!/usr/bin/env node
/**
 * generate_error_codes.cjs
 *
 * E-6: 后端 ErrorCode 枚举自动生成 TS 文件
 * 输入: meta/core/error_codes.py
 * 输出: src/composables/errorCodes.ts
 */
'use strict';

const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', 'meta', 'core', 'error_codes.py');
const OUT = path.join(__dirname, '..', 'src', 'composables', 'errorCodes.ts');

function main() {
  const content = fs.readFileSync(SRC, 'utf-8');
  // 匹配 = 'code' 模式
  const lines = content.split('\n');
  const codes = [];
  for (const line of lines) {
    const m = line.match(/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*['"]([a-z_]+)['"]/);
    if (m) {
      codes.push({ name: m[1], value: m[2] });
    }
  }

  let ts = `// Auto-generated from meta/core/error_codes.py\n`;
  ts += `// DO NOT EDIT MANUALLY\n`;
  ts += `// Date: ${new Date().toISOString()}\n\n`;

  ts += `export const ErrorCodes = {\n`;
  for (const c of codes) {
    ts += `  ${c.name}: '${c.value}',\n`;
  }
  ts += `} as const;\n\n`;

  ts += `export type ErrorCode = typeof ErrorCodes[keyof typeof ErrorCodes]\n\n`;

  ts += `// HTTP status 映射\n`;
  ts += `export const ErrorCodeHttpStatus: Record<ErrorCode, number> = {\n`;
  ts += `  UNAUTHORIZED: 401,\n`;
  ts += `  TOKEN_EXPIRED: 401,\n`;
  ts += `  TOKEN_BLACKLISTED: 401,\n`;
  ts += `  AUTH_SERVICE_ERROR: 401,\n`;
  ts += `  FORBIDDEN: 403,\n`;
  ts += `  ADMIN_REQUIRED: 403,\n`;
  ts += `  ACTION_NOT_FOUND: 404,\n`;
  ts += `  ACTION_VALIDATION_ERROR: 200,\n`;
  ts += `  ACTION_HANDLER_ERROR: 200,\n`;
  ts += `  ACTION_PARAMS_MISSING: 200,\n`;
  ts += `  ACTION_PERMISSION_DENIED: 200,\n`;
  ts += `  SUBFLOW_EMPTY: 400,\n`;
  ts += `  SUBFLOW_STEP_FAILED: 200,\n`;
  ts += `  SUBFLOW_ATOMIC_FAILED: 200,\n`;
  ts += `  SUBFLOW_TRANSACTION_FAILED: 200,\n`;
  ts += `  SUBFLOW_STEP_TIMEOUT: 200,\n`;
  ts += `  SUBFLOW_DRY_RUN: 200,\n`;
  ts += `  SUBFLOW_TEMPLATE_NOT_FOUND: 200,\n`;
  ts += `  INTERNAL_ERROR: 500,\n`;
  ts += `  DB_ERROR: 500,\n`;
  ts += `  NETWORK_ERROR: 500,\n`;
  ts += `  TIMEOUT_ERROR: 500,\n`;
  ts += `  DATA_NOT_FOUND: 200,\n`;
  ts += `  DATA_CONFLICT: 200,\n`;
  ts += `  DATA_INVALID: 200,\n`;
  ts += `  DATA_REFERENCED: 200,\n`;
  ts += `  FILE_TOO_LARGE: 200,\n`;
  ts += `  FILE_GENERATION_FAILED: 200,\n`;
  ts += `};\n`;

  fs.writeFileSync(OUT, ts, 'utf-8');
  console.log(`[generate_error_codes] Generated ${codes.length} codes to ${OUT}`);
}

main();
