#!/usr/bin/env node
/**
 * generate_error_codes.cjs
 *
 * E-6 / FR-007: 后端 ErrorCode 枚举 + HTTP 状态映射自动生成 TS 文件。
 *
 * 单一真源：
 *   1. meta/core/error_codes.py::ErrorCode      → 错误码字面量
 *   2. meta/core/error_codes.py::ERROR_HTTP_STATUS → 码 → HTTP 状态
 *
 * 输出: src/composables/errorCodes.ts
 * 用法: node scripts/generate_error_codes.cjs
 */
'use strict';

const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', 'meta', 'core', 'error_codes.py');
const OUT = path.join(__dirname, '..', 'src', 'composables', 'errorCodes.ts');

const CODE_RE = /^\s*([A-Z_][A-Z0-9_]*)\s*=\s*['"]([^'"]+)['"]/;
const STATUS_RE = /^\s*ErrorCode\.([A-Z_][A-Z0-9_]*)\s*:\s*(\d+)/;

function parseBackend(content) {
  const lines = content.split('\n');
  const codes = [];
  const statuses = {};
  let inEnum = false;
  let inStatusMap = false;

  for (const line of lines) {
    if (/^\s*class\s+ErrorCode\b/.test(line)) {
      inEnum = true;
      continue;
    }
    if (inEnum && /^\s*ALL_CODES\s*=/.test(line)) {
      inEnum = false;
    }
    if (/^ERROR_HTTP_STATUS\s*=\s*\{/.test(line)) {
      inStatusMap = true;
      continue;
    }
    if (inStatusMap && /^\}/.test(line)) {
      inStatusMap = false;
      continue;
    }

    if (inEnum) {
      const m = line.match(CODE_RE);
      if (m) codes.push({ name: m[1], value: m[2] });
      continue;
    }
    if (inStatusMap) {
      const m = line.match(STATUS_RE);
      if (m) statuses[m[1]] = Number(m[2]);
    }
  }

  return { codes, statuses };
}

function generate({ codes, statuses }) {
  let ts = `// Auto-generated from meta/core/error_codes.py\n`;
  ts += `// DO NOT EDIT MANUALLY — 重新生成: node scripts/generate_error_codes.cjs\n`;
  ts += `// Date: ${new Date().toISOString()}\n`;
  ts += `//\n`;
  ts += `// 注意：命名约定\n`;
  ts += `//   - \`ErrorCodes\`（带 s）是运行时枚举值（lowercase snake_case）\n`;
  ts += `//   - \`ErrorCode\`（无 s）是 TypeScript 类型（值联合）\n`;
  ts += `//   - 与 '@/utils/httpClient' 的 ErrorCode（HTTP 传输层，UPPER_SNAKE）不同源\n`;
  ts += `// ---------------------------------------------------------------------------\n\n`;

  ts += `export const ErrorCodes = {\n`;
  for (const c of codes) ts += `  ${c.name}: '${c.value}',\n`;
  ts += `} as const;\n\n`;

  ts += `export type ErrorCode = typeof ErrorCodes[keyof typeof ErrorCodes]\n\n`;

  ts += `// HTTP status 映射（来自后端 ERROR_HTTP_STATUS 单一真源）\n`;
  ts += `export const ErrorCodeHttpStatus: Partial<Record<ErrorCode, number>> = {\n`;
  const missing = [];
  for (const c of codes) {
    if (statuses[c.name] === undefined) {
      missing.push(c.name);
      continue;
    }
    ts += `  ${c.name}: ${statuses[c.name]},\n`;
  }
  ts += `};\n`;

  if (missing.length > 0) {
    ts += `\n// 未映射 HTTP 状态（后端 ERROR_HTTP_STATUS 缺项）: ${missing.join(', ')}\n`;
  }

  return ts;
}

function main() {
  const content = fs.readFileSync(SRC, 'utf-8');
  const parsed = parseBackend(content);
  if (parsed.codes.length === 0) {
    throw new Error(`未从 ${SRC} 解析到任何错误码，生成中止`);
  }

  fs.writeFileSync(OUT, generate(parsed), 'utf-8');
  const unmapped = parsed.codes.filter((c) => parsed.statuses[c.name] === undefined);
  console.log(
    `[generate_error_codes] Generated ${parsed.codes.length} codes ` +
    `(${Object.keys(parsed.statuses).length} status mappings) to ${OUT}`
  );
  if (unmapped.length > 0) {
    console.warn(`[generate_error_codes] 未映射状态: ${unmapped.map((c) => c.name).join(', ')}`);
  }
}

main();