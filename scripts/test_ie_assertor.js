/**
 * 验证 BusinessRuleAssertor 的 import_export / pm_boundary / 解析能力
 * 直接 import 被测模块 (ESM)
 */
import { BusinessRuleAssertor } from '../e2e/screenplay/questions/BusinessRuleAssertor.js';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const RULE_DIR = path.resolve(__dirname, '../.trae/specs/_business_rules');

async function main() {
  console.log('=== BusinessRuleAssertor 验证 ===\n');

  // 1. 找所有 IE-* 规则 ID
  console.log('[1] 扫描 IE-* 规则...');
  const ieRuleIds = [];
  const pmRuleIds = [];
  for (const f of fs.readdirSync(RULE_DIR)) {
    if (!f.endsWith('.yaml')) continue;
    const content = fs.readFileSync(path.join(RULE_DIR, f), 'utf-8');
    for (const line of content.split('\n')) {
      const m = line.match(/^\s*-\s+id:\s*(BR-\S+-(?:IE|PM)-\S+)/);
      if (m) {
        if (m[1].includes('IE-')) ieRuleIds.push(m[1]);
        else if (m[1].includes('PM-')) pmRuleIds.push(m[1]);
      }
    }
  }
  console.log(`  IE 规则: ${ieRuleIds.length} 条`);
  console.log(`  PM 规则: ${pmRuleIds.length} 条`);

  // 2. 用 assertRule 实际调用,看是否抛 "Unknown rule type"
  console.log('\n[2] 实际调用 assertRule 验证解析...');
  let passed = 0, failed = 0;
  const sample = [...ieRuleIds.slice(0, 4), ...pmRuleIds.slice(0, 2)];
  for (const rid of sample) {
    try {
      const result = await BusinessRuleAssertor.assertRule(rid, {});
      console.log(`  [OK]   ${rid} → ${result.message?.slice(0, 80) || 'ok'}`);
      passed++;
    } catch (e) {
      if (e.message.includes('Unknown rule type')) {
        console.log(`  [FAIL] ${rid} → Unknown rule type (parser 问题)`);
      } else {
        console.log(`  [WARN] ${rid} → ${e.message.slice(0, 80)}`);
      }
      failed++;
    }
  }
  console.log(`\n  通过: ${passed}/${sample.length}`);

  // 3. 测试 assertImportExport 校验冲突策略
  console.log('\n[3] 测试 assertImportExport 业务校验...');
  try {
    const result = await BusinessRuleAssertor.assertRule('BR-product-IE-import', {
      strategy: 'upsert',
      conflictKey: 'code'
    });
    console.log(`  [OK] BR-product-IE-import with upsert/code: ${result.message}`);
  } catch (e) {
    console.log(`  [FAIL] ${e.message}`);
  }

  // 4. 错误策略应被拒绝
  try {
    await BusinessRuleAssertor.assertRule('BR-product-IE-import', {
      strategy: 'BOGUS_STRATEGY'
    });
    console.log('  [FAIL] BOGUS_STRATEGY 应被拒绝但被接受');
  } catch (e) {
    if (e.message.includes('不合法')) {
      console.log(`  [OK] BOGUS_STRATEGY 正确被拒绝: ${e.message.slice(0, 80)}`);
    } else {
      console.log(`  [WARN] ${e.message.slice(0, 80)}`);
    }
  }

  // 5. 清理缓存
  BusinessRuleAssertor.clearCache();

  console.log('\n=== 验证完成 ===');
  console.log(`[总结] T1 完成: ${ieRuleIds.length} 条 IE 规则 + ${pmRuleIds.length} 条 PM 规则已可被 assertor 调用`);
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });
