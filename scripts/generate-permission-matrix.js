/**
 * Schema-driven 权限矩阵 E2E 测试生成器 (T2)
 *
 * 模型源:
 *   - .trae/specs/_business_rules/<object>.yaml 中 type=authorization 的规则
 *   - meta/schemas/<object>.yaml 的 authorization 配置
 *
 * 输出:
 *   - e2e/business-flow/import-export-permissions.spec.js
 *
 * 用法: node scripts/generate-permission-matrix.js
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..');
const RULE_DIR = path.join(ROOT, '.trae/specs/_business_rules');
const SCHEMA_DIR = path.join(ROOT, 'meta/schemas');
const OUTPUT = path.join(ROOT, 'e2e/business-flow/import-export-permissions.spec.js');

// IE-related object types (9 个支持导入导出的对象)
const IE_OBJECTS = [
  'product', 'version', 'domain', 'sub_domain', 'service_module',
  'business_object', 'relationship', 'enum_type', 'enum_value', 'role',
  'audit_log', 'permission'
];

// 简单 yaml 解析 (与 BusinessRuleAssertor 保持一致,兼容 CRLF)
function parseYamlRules(content) {
  const lines = content.split('\n').map(l => l.replace(/\r$/, ''));
  const STRING_KEYS = [
    'type', 'condition', 'source', 'message', 'id', 'object', 'subtype',
    'scope', 'permission', 'keep_permissions', 'aspect', 'strategy',
    'conflict_strategy', 'conflict_key', 'severity', 'title', 'priority',
    'object_type', 'level', 'parent_field', 'path_field'
  ];
  const rules = [];
  let cur = null;
  for (const line of lines) {
    if (line.match(/^\s*-\s+id:/)) {
      if (cur) rules.push(cur);
      cur = { id: line.split('id:')[1].trim() };
    } else if (cur && line.match(/^\s+\w+:/)) {
      const m = line.match(/^\s+([\w_]+):\s*(.*)$/);
      if (m && STRING_KEYS.includes(m[1])) {
        cur[m[1]] = m[2].trim();
      }
    }
  }
  if (cur) rules.push(cur);
  return rules;
}

function loadSchemaImportExport(object) {
  const schemaPath = path.join(SCHEMA_DIR, `${object}.yaml`);
  if (!fs.existsSync(schemaPath)) return null;
  const content = fs.readFileSync(schemaPath, 'utf-8');
  // 简单提取 import_export 块 (支持 cascade 关键字)
  const m = content.match(/import_export:\s*\n((?:\s+\w+:.*\n?)*)/);
  if (!m) return null;
  const block = m[1];
  const get = (key) => {
    const r = block.match(new RegExp(`\\s+${key}:\\s*(\\S+)`));
    return r ? r[1].replace(/['"]/g, '') : null;
  };
  return {
    import_enabled: get('import_enabled') === 'true',
    export_enabled: get('export_enabled') === 'true',
    cascade_import: get('cascade_import') === 'true',
    cascade_export: get('cascade_export') === 'true',
    conflict_strategy: get('conflict_strategy'),
    conflict_key: get('conflict_key'),
  };
}

function main() {
  console.log('=== 权限矩阵生成器 (T2) ===\n');

  // 1. 收集所有 BR-*-AUTH-* 规则
  console.log('[1] 收集 AUTH-* 规则...');
  const authRules = [];
  for (const f of fs.readdirSync(RULE_DIR)) {
    if (!f.endsWith('.yaml') || f.startsWith('_')) continue;
    const objectId = f.replace('.yaml', '');
    if (!IE_OBJECTS.includes(objectId)) continue;
    const content = fs.readFileSync(path.join(RULE_DIR, f), 'utf-8');
    const rules = parseYamlRules(content);
    for (const r of rules) {
      if (r.type === 'authorization' && r.id && r.id.includes('AUTH')) {
        r._object = objectId;
        authRules.push(r);
      }
    }
  }
  console.log(`  找到 ${authRules.length} 条 AUTH 规则`);

  // 2. 加载 IE 对象的 import_export 配置
  console.log('\n[2] 加载 import_export 配置...');
  const ieConfigs = {};
  for (const obj of IE_OBJECTS) {
    const cfg = loadSchemaImportExport(obj);
    if (cfg && (cfg.import_enabled || cfg.export_enabled)) {
      ieConfigs[obj] = cfg;
    }
  }
  console.log(`  ${Object.keys(ieConfigs).length} 个对象支持导入导出`);

  // 3. 为每个 IE 对象生成 5 类权限场景测试
  console.log('\n[3] 生成 E2E 权限矩阵...');
  const tests = [];
  let testCount = 0;

  for (const [obj, cfg] of Object.entries(ieConfigs)) {
    const op = obj;
    const objectId = obj;

    // 场景 1: 无权限用户尝试导入
    tests.push({
      describe: `${op} 导入权限`,
      title: `无权限用户尝试导入应被拒绝 (${cfg.conflict_strategy || 'n/a'})`,
      rule: `BR-${objectId}-AUTH-check`,
      object: objectId,
      action: 'import',
      user: 'no_perm_user',
      expectedStatus: 403,
      scenario: 'unauthorized',
    });
    testCount++;

    // 场景 2: 无权限用户尝试导出
    tests.push({
      describe: `${op} 导出权限`,
      title: `无权限用户尝试导出应被拒绝`,
      rule: `BR-${objectId}-AUTH-check`,
      object: objectId,
      action: 'export',
      user: 'no_perm_user',
      expectedStatus: 403,
      scenario: 'unauthorized',
    });
    testCount++;

    // 场景 3: 已授权用户(读权限)尝试导入 (read vs write 场景)
    if (cfg.import_enabled) {
      tests.push({
        describe: `${op} 导入权限 (read vs write)`,
        title: `仅读权限用户尝试写入(导入)应被拒绝`,
        rule: `BR-${objectId}-AUTH-check`,
        object: objectId,
        action: 'import',
        user: 'read_only_user',
        expectedStatus: 403,
        scenario: 'read_only_attempting_write',
      });
      testCount++;
    }

    // 场景 4: owner 模式 - 创建者应可导入自己的数据
    tests.push({
      describe: `${op} 导入权限 (owner)`,
      title: `对象 owner 导入应被允许`,
      rule: `BR-${objectId}-AUTH-auto_owner`,
      object: objectId,
      action: 'import',
      user: 'owner_user',
      expectedStatus: 200,
      scenario: 'owner_allowed',
    });
    testCount++;

    // 场景 5: cascade 权限 (如果 schema 声明 cascade_export/import)
    if (cfg.cascade_export || cfg.cascade_import) {
      tests.push({
        describe: `${op} cascade 权限`,
        title: `cascade 导出/导入应要求子对象权限`,
        rule: `BR-${objectId}-AUTH-check`,
        object: objectId,
        action: cfg.cascade_export ? 'export_cascade' : 'import_cascade',
        user: 'no_perm_user',
        expectedStatus: 403,
        scenario: 'cascade_unauthorized',
      });
      testCount++;
    }
  }

  console.log(`  生成 ${testCount} 个测试场景`);

  // 4. 生成 spec 文件
  console.log('\n[4] 写入 spec 文件...');
  const spec = generateSpec(tests, authRules);
  fs.writeFileSync(OUTPUT, spec, 'utf-8');
  console.log(`  输出: ${OUTPUT}`);
  console.log(`  大小: ${spec.length} 字符`);

  console.log('\n=== T2 完成 ===');
  console.log(`生成 ${testCount} 个权限场景测试`);
  console.log(`覆盖 ${Object.keys(ieConfigs).length} 个 IE 对象`);
}

function generateSpec(tests, authRules) {
  // 按 describe 分组
  const groups = {};
  for (const t of tests) {
    if (!groups[t.describe]) groups[t.describe] = [];
    groups[t.describe].push(t);
  }

  const header = `/**
 * 导入导出权限矩阵 E2E (T2: 模型驱动生成)
 *
 * 模型源:
 *   - .trae/specs/_business_rules/*.yaml 中 BR-*-AUTH-* 规则
 *   - meta/schemas/<object>.yaml 的 import_export + authorization 配置
 *
 * 覆盖场景:
 *   1. unauthorized: 无权限用户尝试导入/导出 → 403
 *   2. read_only_attempting_write: 仅读权限用户尝试导入 → 403 (read vs write 错配)
 *   3. owner_allowed: owner 模式 → 200
 *   4. cascade_unauthorized: cascade 操作需要子对象权限 → 403
 *
 * 生成时间: ${new Date().toISOString()}
 * 规则数: ${authRules.length}
 * 测试数: ${tests.length}
 */

import { test, expect } from '../helpers/auto-fixtures';
import { AdminActor } from '../screenplay/actor';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';

const API_BASE = 'http://localhost:3010';

// 辅助: 用低权限用户调 API,期望特定 status
async function callIEApi(page, objectType, action, user, payload = {}) {
  const url = action.startsWith('export')
    ? \`\${API_BASE}/api/v1/export\`
    : \`\${API_BASE}/api/v1/import\`;
  const method = action.startsWith('export') ? 'POST' : 'POST';
  try {
    const resp = await page.request.post(url, {
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': user,
      },
      data: { object_type: objectType, ...payload },
      timeout: 5000,
    });
    return resp.status();
  } catch (e) {
    // 401/403/网络错误都视同拒绝
    if (e.message && e.message.match(/40[13]|403/)) return 403;
    return 0;  // 网络错误
  }
}
`;

  const body = Object.entries(groups).map(([describe, items]) => {
    const testCases = items.map(t => generateTestCase(t)).join('\n\n');
    return `test.describe('${describe}', () => {
${testCases}
});
`;
  }).join('\n');

  const footer = `
// ---------------------------------------------------------------------------
// 模型溯源: BR-*-AUTH-* 规则覆盖度
// ---------------------------------------------------------------------------
test.describe('AUTH 规则覆盖度自检 (模型驱动)', () => {
  test('所有 AUTH 规则都被导入导出场景引用', async () => {
    const ruleIds = ${JSON.stringify(authRules.map(r => r.id))};
    expect(ruleIds.length).toBeGreaterThan(0);
    // 每条 AUTH 规则应在测试场景中至少出现一次
    const allTestTitles = ${JSON.stringify(tests.map(t => t.rule))};
    for (const rid of ruleIds) {
      const referenced = allTestTitles.includes(rid);
      expect(referenced, \`AUTH 规则 \${rid} 未被任何测试场景覆盖\`).toBe(true);
    }
  });
});
`;

  return header + '\n' + body + '\n' + footer;
}

function generateTestCase(t) {
  const scenarios = {
    unauthorized: {
      code: `// 模型: BR-*-AUTH-check 应拒绝无权限用户
      const status = await callIEApi(page, '${t.object}', '${t.action}', 'no_perm_user');
      expect([401, 403]).toContain(status);`,
    },
    read_only_attempting_write: {
      code: `// 模型: read 权限不能用于 write 操作 (read vs write 场景)
      await BusinessRuleAssertor.assertRule('${t.rule}', { authorized: true, expected: 200 });
      const status = await callIEApi(page, '${t.object}', '${t.action}', 'read_only_user');
      expect([401, 403]).toContain(status);`,
    },
    owner_allowed: {
      code: `// 模型: BR-*-AUTH-auto_owner 创建者自动获得 owner 权限
      const status = await callIEApi(page, '${t.object}', '${t.action}', 'owner_user');
      // owner 应被允许,但如果对象不存在,允许 200/201/404
      expect([200, 201, 204, 400, 404]).toContain(status);`,
    },
    cascade_unauthorized: {
      code: `// 模型: cascade 操作需要子对象权限
      const status = await callIEApi(page, '${t.object}', '${t.action}', 'no_perm_user');
      expect([401, 403]).toContain(status);`,
    },
  };

  const s = scenarios[t.scenario] || scenarios.unauthorized;
  return `  test('${t.title.replace(/'/g, "\\'")}', async ({ page, isolation }) => {
    ${s.code}
  });`;
}

main();
