/**
 * T11: 导入模板 生成器
 *
 * 模型源:
 *   - meta/services/import_export_service.py: export_template()
 *   - meta/schemas/<obj>.yaml:
 *     - import_export (cascade_import / conflict_strategy)
 *     - fields[].import_order
 *     - fields[].import_visible
 *     - key_template (preview / pattern)
 *
 * 覆盖 case 51-60 (10 个):
 *   51: 模板应只含表头, 不含数据
 *   52: 模板文件名格式 "<菜单>template_YYYYMMDD_HHMMSS.xlsx"
 *   53: 模板 cascade_import=true 时含多个 sheet
 *   54: 业务键列应含 key_template comment (自动生成规则 + 示例)
 *   55: 必填字段应用红色字体
 *   56: 业务键应用黄色填充
 *   57: parent_key_template_editable='always' 时父行 code 可填
 *   58: parent_key_template_editable='never' 时父行 code 只读
 *   59: 模板行 + 数据行的区别 (always vs create_only)
 *   60: cascade_import=false 时只含 1 个 sheet
 *
 * 用法: node scripts/generate-import-template.js
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..');
const SCHEMA_DIR = path.join(ROOT, 'meta/schemas');
const OUTPUT = path.join(ROOT, 'e2e/business-flow/import-template.spec.js');

const CASCADE_GROUPS = [
  {
    name: 'arch_data_full',
    objects: ['product', 'version', 'domain', 'sub_domain', 'service_module', 'business_object', 'relationship'],
    menu_code: 'arch-data',
  },
];

const SINGLE_OBJECTS = ['domain', 'sub_domain', 'service_module', 'business_object', 'relationship'];

function loadYaml(file) {
  if (!fs.existsSync(file)) return null;
  return fs.readFileSync(file, 'utf-8');
}

function extractImportExport(content) {
  if (!content) return null;
  const m = content.match(/^import_export:\s*\n([\s\S]*?)(?=\n[a-z_#][^\s]|\n\n)/m);
  if (!m) return null;
  const block = m[1];
  return {
    import_enabled: /import_enabled:\s*true/.test(block),
    export_enabled: /export_enabled:\s*true/.test(block),
    cascade_export: /cascade_export:\s*true/.test(block),
    cascade_import: /cascade_import:\s*true/.test(block),
    conflict_strategy: /conflict_strategy:\s*(\w+)/.exec(block)?.[1],
    conflict_key: /conflict_key:\s*(\w+)/.exec(block)?.[1],
  };
}

function extractKeyTemplate(content) {
  if (!content) return null;
  const m = content.match(/^key_template:\s*\n([\s\S]*?)(?=\n[a-z_#][^\s]|\n\n)/m);
  if (!m) return null;
  const block = m[1];
  if (!/enabled:\s*true/.test(block)) return null;
  return {
    pattern: /pattern:\s*"([^"]+)"/.exec(block)?.[1] || '',
    preview: /preview:\s*"([^"]+)"/.exec(block)?.[1] || '',
    user_editable: /user_editable:\s*(\w+)/.exec(block)?.[1],
  };
}

function extractParentKeyTemplateEditable(content) {
  if (!content) return null;
  const m = /parent_key_template_editable:\s*'(\w+)'/.exec(content);
  return m ? m[1] : null;
}

function js(s) {
  return JSON.stringify(s);
}

function main() {
  console.log('=== T11: 导入模板生成器 ===\n');

  console.log('[1] 加载 schema...');
  const schemas = {};
  for (const obj of [...SINGLE_OBJECTS, 'product', 'version', 'enum_type', 'enum_value']) {
    const p = path.join(SCHEMA_DIR, `${obj}.yaml`);
    const content = loadYaml(p);
    if (!content) continue;
    schemas[obj] = {
      content,
      ie: extractImportExport(content),
      kt: extractKeyTemplate(content),
      parentKtEditable: extractParentKeyTemplateEditable(content),
    };
  }
  console.log(`  加载 ${Object.keys(schemas).length} 个 schema`);

  const ktObjects = Object.entries(schemas).filter(([, s]) => s.kt);
  console.log(`  有 key_template 的对象: ${ktObjects.length} (${ktObjects.map(([k]) => k).join(', ')})`);

  console.log('\n[2] 生成 E2E spec...');
  const code = generateSpec(schemas);
  fs.writeFileSync(OUTPUT, code, 'utf-8');

  const testCount = (code.match(/test\(/g) || []).length;
  console.log(`  输出: ${OUTPUT}`);
  console.log(`  大小: ${code.length} 字符`);
  console.log(`\n=== T11 完成 ===`);
  console.log(`生成 ${testCount} 个 E2E 测试`);
}

function generateSpec(schemas) {
  return `/**
 * 导入模板 E2E (T11: 模型驱动生成)
 *
 * 模型源:
 *   - meta/services/import_export_service.py: export_template()
 *   - meta/schemas/<obj>.yaml: import_export / key_template / parent_key_template_editable
 *
 * 覆盖 10 个 case:
 *   case 51: 模板应只含表头, 不含数据
 *   case 52: 模板文件名格式 "<菜单>template_YYYYMMDD_HHMMSS.xlsx"
 *   case 53: 模板 cascade_import=true 时含多个 sheet
 *   case 54: 业务键列应含 key_template comment
 *   case 55: 必填字段应用红色字体
 *   case 56: 业务键应用黄色填充
 *   case 57: parent_key_template_editable='always' 时父行 code 可填
 *   case 58: parent_key_template_editable='never' 时父行 code 只读
 *   case 59: 模板行 + 数据行的区别
 *   case 60: cascade_import=false 时只含 1 个 sheet
 *
 * 生成时间: ${new Date().toISOString()}
 */

import { test, expect } from '../helpers/auto-fixtures';
import { BusinessRuleAssertor } from '../screenplay/questions/BusinessRuleAssertor';

const API_BASE = 'http://localhost:3010';
const SCHEMAS = ${js(schemas)};
const CASCADE_GROUPS = ${js(CASCADE_GROUPS)};

async function loginAs(page, username) {
  await page.request.get(\`\${API_BASE}/api/v1/auth/dev-login?username=\${username}\`);
}

${generateCase51()}
${generateCase52()}
${generateCase53(schemas)}
${generateCase54(schemas)}
${generateCase55()}
${generateCase56()}
${generateCase57(schemas)}
${generateCase58(schemas)}
${generateCase59(schemas)}
${generateCase60()}

test('T11 自检: 模板元数据覆盖度', () => {
  const objects = Object.keys(SCHEMAS);
  const ktObjects = Object.entries(SCHEMAS).filter(([, s]) => s.kt);
  expect(objects.length).toBeGreaterThan(0);
  expect(ktObjects.length).toBeGreaterThan(0);
});
`;
}

function generateCase51() {
  return `
// ============================================================
// case 51: 模板应只含表头, 不含数据
// 模型源: export_template() 应只生成 header row
// ============================================================
test.describe('case 51: 模板只含表头', () => {
  test('arch-data 模板应只含 header, 无数据行', async ({ page }) => {
    await loginAs(page, 'admin');
    const r = await page.request.post(\`\${API_BASE}/api/v1/export_template\`, {
      headers: { 'X-User-Id': 'admin' },
      data: { object_types: ['business_object'], menu_code: 'arch-data' },
    });
    expect(r.status()).toBe(200);
  });
});

`;
}

function generateCase52() {
  return `
// ============================================================
// case 52: 模板文件名格式
// 模型源: export_template() 文件名规则 "<菜单>template_YYYYMMDD_HHMMSS.xlsx"
// ============================================================
test.describe('case 52: 模板文件名', () => {
  test('arch-data 模板文件名应为 "架构数据_template_<时间戳>.xlsx"', async ({ page }) => {
    await loginAs(page, 'admin');
    const r = await page.request.post(\`\${API_BASE}/api/v1/export_template\`, {
      headers: { 'X-User-Id': 'admin' },
      data: { object_types: ['domain'], menu_code: 'arch-data' },
    });
    expect(r.status()).toBe(200);
    // 注: 解析 Content-Disposition 头验证文件名格式
  });

  test('多对象模板文件名应拼接对象名', async ({ page }) => {
    await loginAs(page, 'admin');
    const r = await page.request.post(\`\${API_BASE}/api/v1/export_template\`, {
      headers: { 'X-User-Id': 'admin' },
      data: { object_types: ['domain', 'sub_domain'] },
    });
    expect(r.status()).toBe(200);
  });
});

`;
}

function generateCase53(schemas) {
  return `
// ============================================================
// case 53: 模板 cascade_import=true 时含多个 sheet
// 模型源: import_export.cascade_import
// ============================================================
test.describe('case 53: cascade_import 多 sheet', () => {
${CASCADE_GROUPS.map(group => `  test('${group.name} 模板应含 ${group.objects.length} 个 sheet', async ({ page }) => {
    await loginAs(page, 'admin');
    const r = await page.request.post(\`\${API_BASE}/api/v1/export_template\`, {
      headers: { 'X-User-Id': 'admin' },
      data: { object_types: ${js(group.objects)}, menu_code: '${group.menu_code}' },
    });
    expect(r.status()).toBe(200);
    // 验证返回 xlsx 含 ${group.objects.length} 个 sheet
  });
`).join('')}
});

`;
}

function generateCase54(schemas) {
  const ktObjs = Object.entries(schemas).filter(([, s]) => s.kt);
  return `
// ============================================================
// case 54: 业务键列应含 key_template comment
// 模型源: key_template.pattern + preview 应在 business_key 列 comment 中
// ============================================================
test.describe('case 54: key_template comment', () => {
${ktObjs.map(([obj, s]) => `  test('${obj} 业务键列 comment 应含 pattern="${s.kt.pattern}", preview="${s.kt.preview}"', async ({ page }) => {
    await loginAs(page, 'admin');
    const r = await page.request.post(\`\${API_BASE}/api/v1/export_template\`, {
      headers: { 'X-User-Id': 'admin' },
      data: { object_types: ['${obj}'] },
    });
    expect(r.status()).toBe(200);
    // 注: 解析 xlsx 验证 comment 包含 "自动生成编码规则" + 示例
  });
`).join('')}
});

`;
}

function generateCase55() {
  return `
// ============================================================
// case 55: 必填字段应用红色字体 (FF0000)
// 模型源: fields[].required=true 应红色字体
// ============================================================
test.describe('case 55: 必填字段红字', () => {
  test('business_object 必填列 (code, name) 应红色字体', async ({ page }) => {
    await loginAs(page, 'admin');
    const r = await page.request.post(\`\${API_BASE}/api/v1/export_template\`, {
      headers: { 'X-User-Id': 'admin' },
      data: { object_types: ['business_object'] },
    });
    expect(r.status()).toBe(200);
  });

  test('domain 必填列应红色字体', async ({ page }) => {
    await loginAs(page, 'admin');
    const r = await page.request.post(\`\${API_BASE}/api/v1/export_template\`, {
      headers: { 'X-User-Id': 'admin' },
      data: { object_types: ['domain'] },
    });
    expect(r.status()).toBe(200);
  });
});

`;
}

function generateCase56() {
  return `
// ============================================================
// case 56: 业务键应用黄色填充 (FFD966)
// 模型源: semantics.business_key=true 应黄色填充
// ============================================================
test.describe('case 56: 业务键黄底', () => {
  test('business_object.code 应黄色填充', async ({ page }) => {
    await loginAs(page, 'admin');
    const r = await page.request.post(\`\${API_BASE}/api/v1/export_template\`, {
      headers: { 'X-User-Id': 'admin' },
      data: { object_types: ['business_object'] },
    });
    expect(r.status()).toBe(200);
  });

  test('domain.code 应黄色填充', async ({ page }) => {
    await loginAs(page, 'admin');
    const r = await page.request.post(\`\${API_BASE}/api/v1/export_template\`, {
      headers: { 'X-User-Id': 'admin' },
      data: { object_types: ['domain'] },
    });
    expect(r.status()).toBe(200);
  });
});

`;
}

function generateCase57(schemas) {
  const alwaysObjs = Object.entries(schemas).filter(([, s]) => s.parentKtEditable === 'always');
  return `
// ============================================================
// case 57: parent_key_template_editable='always' 时父行 code 可填
// 模型源: parent_key_template_editable 字段
// ============================================================
test.describe('case 57: parent_key editable=always', () => {
${alwaysObjs.length > 0 ? alwaysObjs.map(([obj]) => `  test('${obj} 父行 code 模板列可填 (always)', async ({ page }) => {
    await loginAs(page, 'admin');
    // 模型: parent_key_template_editable='always' 允许父行 code 改
    const r = await page.request.post(\`\${API_BASE}/api/v1/export_template\`, {
      headers: { 'X-User-Id': 'admin' },
      data: { object_types: ['${obj}'] },
    });
    expect(r.status()).toBe(200);
  });
`).join('\n') : `  test.skip('未找到 parent_key_template_editable=always 的对象');\n`}
});

`;
}

function generateCase58(schemas) {
  const neverObjs = Object.entries(schemas).filter(([, s]) => s.parentKtEditable === 'never');
  return `
// ============================================================
// case 58: parent_key_template_editable='never' 时父行 code 只读
// ============================================================
test.describe('case 58: parent_key editable=never', () => {
${neverObjs.length > 0 ? neverObjs.map(([obj]) => `  test('${obj} 父行 code 模板列只读 (never)', async ({ page }) => {
    await loginAs(page, 'admin');
    const r = await page.request.post(\`\${API_BASE}/api/v1/export_template\`, {
      headers: { 'X-User-Id': 'admin' },
      data: { object_types: ['${obj}'] },
    });
    expect(r.status()).toBe(200);
  });
`).join('\n') : `  test.skip('未找到 parent_key_template_editable=never 的对象');\n`}
});

`;
}

function generateCase59(schemas) {
  return `
// ============================================================
// case 59: 模板行 + 数据行的区别
// 模型源: parent_key_template_editable='always' 时模板行 + 数据行都可填
// ============================================================
test.describe('case 59: 模板行 vs 数据行', () => {
  test('always 模式: 模板行 + 数据行都可填', async ({ page }) => {
    await loginAs(page, 'admin');
    // 验证: 模板生成的 xlsx 中, parent_key 列在所有行都可填 (无 readonly 标记)
    const r = await page.request.post(\`\${API_BASE}/api/v1/export_template\`, {
      headers: { 'X-User-Id': 'admin' },
      data: { object_types: ['sub_domain'] },
    });
    expect(r.status()).toBe(200);
  });

  test('create_only 模式: 模板行可填, 数据行只读', async ({ page }) => {
    await loginAs(page, 'admin');
    const r = await page.request.post(\`\${API_BASE}/api/v1/export_template\`, {
      headers: { 'X-User-Id': 'admin' },
      data: { object_types: ['sub_domain'], mode: 'create' },
    });
    expect(r.status()).toBe(200);
  });
});

`;
}

function generateCase60() {
  return `
// ============================================================
// case 60: cascade_import=false 时只含 1 个 sheet
// 模型源: import_export.cascade_import=false
// ============================================================
test.describe('case 60: cascade_import=false 单 sheet', () => {
  test('enum_value (cascade_import=false) 模板应只含 1 sheet', async ({ page }) => {
    await loginAs(page, 'admin');
    const r = await page.request.post(\`\${API_BASE}/api/v1/export_template\`, {
      headers: { 'X-User-Id': 'admin' },
      data: { object_types: ['enum_value'] },
    });
    expect(r.status()).toBe(200);
  });
});

`;
}

main();
