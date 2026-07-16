// [V007.49 P0] warnTooManyRelationships 状态转换测试
// 验证防重复告警逻辑

import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { readFileSync } from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT = join(__dirname, '..');

// Mock ElNotification
let notifyCount = 0;
const notifyCalls = [];
global.ElNotification = (opts) => {
  notifyCount++;
  notifyCalls.push(opts);
  console.log(`  🔔 ElNotification call #${notifyCount}: ${opts.title} (${opts.position})`);
};

// 动态 import useDiagramData.js 的相关函数
// 由于 useDiagramData.js 是 Vue composable, 我们只测试独立函数 warnTooManyRelationships
// 直接 eval 函数体 (因为是 module-level function)
const udContent = readFileSync(join(ROOT, 'src/views/AADiagramApp/composables/useDiagramData.js'), 'utf-8');
// 提取 warnTooManyRelationships + RELATIONSHIP_WARN_THRESHOLD
const fnMatch = udContent.match(/const RELATIONSHIP_WARN_THRESHOLD = \d+[\s\S]*?^}/m);
if (!fnMatch) {
  console.log('❌ 找不到 warnTooManyRelationships 函数');
  process.exit(1);
}

// 在新上下文 eval
// 关键: _lastWarnedKey 必须用 getter/setter 让 global 同步
const code = fnMatch[0] + `
  globalThis.warnTooManyRelationships = warnTooManyRelationships;
  globalThis.getLastWarnedKey = () => _lastWarnedKey;
  globalThis.resetWarnState = () => { _lastWarnedKey = null; };
`;
eval(code);

console.log('=== V007.49 P0 状态转换测试 ===\n');

const tests = [
  // [name, count, chartType, shouldNotify, expectedLastKey]
  ['1. 初始: 50 关系 (≤100)', 50, 'businessObject', false, null],
  ['2. 增加到 200 关系 (>100)', 200, 'businessObject', true, 'bo:above'],
  ['3. 200→300 (仍在 above)', 300, 'businessObject', false, 'bo:above'],
  ['4. 300→400 (仍在 above)', 400, 'businessObject', false, 'bo:above'],
  ['5. 400→80 (回到 below)', 80, 'businessObject', false, null],
  ['6. 80→150 (再次越阈值)', 150, 'businessObject', true, 'bo:above'],
  ['7. SM 图 200 关系 (不告警)', 200, 'serviceModule', false, 'bo:above'],
  ['8. BO 图 100 关系 (边界 ≤) → reset', 100, 'businessObject', false, null],
  ['9. BO 图 101 关系 (越阈值) → 告警', 101, 'businessObject', true, 'bo:above'],  // 重置后再越阈值
  ['10. 101→50 (重置)', 50, 'businessObject', false, null],
  ['11. 50→250 (越阈值)', 250, 'businessObject', true, 'bo:above'],
];

let pass = 0;
let fail = 0;

for (const [name, count, chartType, shouldNotify, expectedKey] of tests) {
  const beforeCount = notifyCount;
  globalThis.warnTooManyRelationships(count, chartType);
  const afterCount = notifyCount;
  const actualKey = globalThis.getLastWarnedKey();
  const notified = afterCount > beforeCount;

  const ok = notified === shouldNotify && actualKey === expectedKey;
  const status = ok ? '✅' : '❌';
  if (ok) pass++;
  else fail++;
  console.log(`  ${status} ${name}`);
  console.log(`     notify: ${notified} (expect ${shouldNotify}), lastKey: ${JSON.stringify(actualKey)} (expect ${JSON.stringify(expectedKey)})`);
}

console.log(`\n=== 结果: ${pass}/${pass+fail} PASS ===`);

// 最终验证: 整个会话总共通知次数应该 == 3
// (1. step 2 first 200, 2. step 6 second 150, 3. step 11 third 250)
console.log(`\n总 ElNotification 调用次数: ${notifyCount} (预期 3)`);
console.log(`通知 call 内容: ${notifyCalls.map(c => c.message.slice(0, 50)).join('\n  ')}`);

if (fail > 0) {
  console.log('\n❌ 测试失败');
  process.exit(1);
} else {
  console.log('\n✅ 全部通过');
  process.exit(0);
}
