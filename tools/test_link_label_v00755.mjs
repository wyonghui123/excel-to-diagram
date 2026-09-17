// [V007.55] 验证 sanitizeLabel 转义后 link label 通过 mermaid 11.13 + innerHTML 注入
import { Window } from 'happy-dom';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import vm from 'vm';

const __dirname = dirname(fileURLToPath(import.meta.url));
const arrowHelperPath = join(__dirname, '..', 'src', 'composables', 'useMermaid', 'syntax', '_shared', 'arrowHelper.js');
const src = readFileSync(arrowHelperPath, 'utf-8');

// 提取 sanitizeLabel
const match = src.match(/export function sanitizeLabel[\s\S]+?\n\}/);
if (!match) {
  console.error('FAIL: 无法在 arrowHelper.js 找到 sanitizeLabel');
  process.exit(1);
}
const ctx = {};
vm.createContext(ctx);
vm.runInContext(match[0].replace('export function', 'function'), ctx);
const sanitizeLabel = ctx.sanitizeLabel;
console.log('sanitizeLabel 加载成功');

const window = new Window({ url: 'http://localhost/' });
function setGlobal(name, value) {
  try { Object.defineProperty(globalThis, name, { value, configurable: true, writable: true }); } catch {}
}
setGlobal('window', window);
setGlobal('document', window.document);
setGlobal('navigator', window.navigator);
setGlobal('HTMLElement', window.HTMLElement);
setGlobal('Node', window.Node);
setGlobal('DocumentFragment', window.DocumentFragment);
setGlobal('SVGElement', window.SVGElement);
setGlobal('Element', window.Element);
setGlobal('NodeList', window.NodeList);
setGlobal('DOMParser', window.DOMParser);
setGlobal('MutationObserver', window.MutationObserver);
setGlobal('getComputedStyle', window.getComputedStyle.bind(window));
setGlobal('requestAnimationFrame', (cb) => setTimeout(cb, 16));
setGlobal('cancelAnimationFrame', (id) => clearTimeout(id));

const mermaid = await import('mermaid');
mermaid.default.initialize({ startOnLoad: false, securityLevel: 'loose' });

// 测试用例
const testLabels = [
  '正常',
  'rel&test',
  'rel<tag>',
  'rel&"x"',
  'rel|pipe',
  'rel\nnewline',
  'rel"quote',
  'BO_001-BO_002',
  '正常 & 含 < > "',
];

let pass = 0, fail = 0;
for (const label of testLabels) {
  const safe = sanitizeLabel(label);

  // 单向 (有 label)
  const codeUni = 'flowchart TB\n  A -->|"' + safe + '"| B';
  // 双向 (裸 label, mermaid 11.13 接受但 sanitizeLabel 输出可能含 & 实体)
  const codeBidi = 'flowchart TB\n  A <-- ' + safe + ' --> B';

  // 模拟 innerHTML 注入
  const div = window.document.createElement('div');
  div.innerHTML = '<pre class="mermaid">' + codeUni + '</pre>';
  const receivedUni = div.querySelector('pre.mermaid')?.textContent || '';

  const div2 = window.document.createElement('div');
  div2.innerHTML = '<pre class="mermaid">' + codeBidi + '</pre>';
  const receivedBidi = div2.querySelector('pre.mermaid')?.textContent || '';

  let uniResult = 'PASS', bidiResult = 'PASS', err = '';
  try {
    await mermaid.default.parse(receivedUni);
  } catch (e) {
    uniResult = 'FAIL';
    err = (e.message || e.toString()).split('\n')[0];
  }
  try {
    await mermaid.default.parse(receivedBidi);
  } catch (e) {
    bidiResult = 'FAIL';
    err = (e.message || e.toString()).split('\n')[0];
  }

  const ok = (uniResult === 'PASS' && bidiResult === 'PASS');
  if (ok) pass++; else fail++;
  console.log((ok ? 'PASS' : 'FAIL') + ' label=' + JSON.stringify(label) + ' → safe=' + JSON.stringify(safe) + ' | uni=' + uniResult + ' bidi=' + bidiResult);
  if (!ok) console.log('  err: ' + err);
}

console.log('\n=== ' + pass + ' pass, ' + fail + ' fail ===');
process.exit(fail > 0 ? 1 : 0);