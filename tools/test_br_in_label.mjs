// [V007.54] 测试 sanitizeMermaidLabel 后的 BO 名称走 innerHTML 注入不破坏 mermaid 文本
import { Window } from 'happy-dom';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const arrowHelperPath = join(__dirname, '..', 'src', 'composables', 'useMermaid', 'syntax', '_shared', 'arrowHelper.js');

// 用 VM 提取 sanitizeMermaidLabel 函数 (避免依赖其他模块)
import vm from 'vm';
const src = readFileSync(arrowHelperPath, 'utf-8');
// 提取 sanitizeMermaidLabel 函数定义
const match = src.match(/export function sanitizeMermaidLabel[\s\S]+?\n\}/);
if (!match) {
  console.error('FAIL: 无法在 arrowHelper.js 找到 sanitizeMermaidLabel 函数');
  process.exit(1);
}
const ctx = {};
vm.createContext(ctx);
vm.runInContext(match[0].replace('export function', 'function'), ctx);
const sanitizeMermaidLabel = ctx.sanitizeMermaidLabel;
console.log('sanitizeMermaidLabel 加载成功');

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

const testCases = [
  '正常 BO',
  'BO<br>名称',
  'BO</pre>名称',
  'BO<节点>名称',
  'BO&名称',
  'BO"双引号"',
  'BO\'单引号\'',
  'BO(主)名称',
  'BO[特]殊',
  'BO{a}b',
  'BO\\反斜杠',
  'BO\n换行',
  'BO>大于',
  'BO<小于',
  'BO&amp;测试',
];

const mermaid = await import('mermaid');
mermaid.default.initialize({ startOnLoad: false, securityLevel: 'loose' });

let pass = 0, fail = 0;
for (const label of testCases) {
  const sanitized = sanitizeMermaidLabel(label);
  const mermaidCode = 'flowchart TB\n  N1["' + sanitized + '"]';

  // 模拟 MermaidComponent.vue L342 注入
  const container = window.document.createElement('div');
  container.innerHTML = '<pre class="mermaid">' + mermaidCode + '</pre>';
  const preEl = container.querySelector('pre.mermaid');
  const receivedByMermaid = preEl ? preEl.textContent : '<NO PRE>';

  // 尝试用 mermaid 11.13 解析收到的代码
  let parseResult = 'PASS';
  let parseErr = '';
  try {
    await mermaid.default.parse(receivedByMermaid);
  } catch (e) {
    parseResult = 'FAIL';
    parseErr = (e.message || e.toString()).split('\n')[0];
  }

  if (parseResult === 'PASS') pass++;
  else fail++;
  console.log('[' + parseResult + '] ' + JSON.stringify(label) + ' → sanitize=' + JSON.stringify(sanitized).slice(0, 60));
  if (parseResult === 'FAIL') {
    console.log('  mermaid 收到: ' + JSON.stringify(receivedByMermaid.split('\n').slice(-3).join(' | ').slice(0, 150)));
    console.log('  error: ' + parseErr);
  }
}

console.log('\n=== 结果: ' + pass + ' pass, ' + fail + ' fail ===');
process.exit(fail > 0 ? 1 : 0);