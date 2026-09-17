// [V007.51 验证] 验证 sanitizeMermaidLabel 后是否能消除 syntax error
import { Window } from 'happy-dom';

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

// [V007.51] 镜像 src/composables/useMermaid/syntax/_shared/arrowHelper.js 的 sanitizeMermaidLabel
// 必须与源码保持完全一致
function sanitizeMermaidLabel(text) {
  if (text === null || text === undefined) return ''
  if (typeof text !== 'string') text = String(text)
  return text
    .replace(/\\/g, '#92;')
    .replace(/"/g, '#quot;')
    .replace(/\n/g, '<br/>')
    .replace(/\r/g, '')
    .replace(/\(/g, '#40;')
    .replace(/\)/g, '#41;')
}

// 测试 sanitize 行为
console.log('=== sanitize 行为验证 ===');
const samples = [
  ['销售 "BOSS" 系统', '销售 #quot;BOSS#quot; 系统'],
  ['B\\OS', 'B#92;OS'],
  ['销售\n订单', '销售<br/>订单'],
  ['订单(主)', '订单#40;主#41;'],
  ['销售/订单', '销售/订单'],
];
let allPass = true;
for (const [input, expected] of samples) {
  const got = sanitizeMermaidLabel(input);
  const ok = got === expected;
  if (!ok) allPass = false;
  console.log((ok ? 'PASS' : 'FAIL') + ' ' + JSON.stringify(input) + ' -> ' + JSON.stringify(got) + (ok ? '' : ' (期望 ' + JSON.stringify(expected) + ')'));
}

// 用 mermaid 11.13 parse 测试
const mermaid = await import('mermaid');
mermaid.default.initialize({ startOnLoad: false, securityLevel: 'loose' });

console.log('\n=== 原 failing 用例 sanitize 后 parse 测试 ===');
const failingCases = [
  { name: 'BO 名称含 "', label: '销售 "BOSS" 系统' },
  { name: 'subgraph 名称含 "', label: '◆销售 "BOSS" 系统' },
  { name: 'BO 名称含 \\ 反斜杠', label: 'B\\OS' },
  { name: 'BO 名称含实际换行', label: '销售\n订单' },
  { name: 'BO 名称含中文括号', label: '订单(主)' },
];

for (const c of failingCases) {
  const safe = sanitizeMermaidLabel(c.label);
  const code = 'flowchart TB\n  N1["' + safe + '"]\n  N2["用户"]\n  N1 --> N2';
  try {
    await mermaid.default.parse(code);
    console.log('PASS ' + c.name);
  } catch (e) {
    console.log('FAIL ' + c.name + ': ' + (e.message || e.toString()).split('\n')[0]);
    allPass = false;
  }
}

console.log('\n=== 链接 label sanitize 后 parse 测试 ===');
{
  const code = 'flowchart TB\n  N1["A"]\n  N2["B"]\n  N1 -- "label#quot;with#quot;quote" --> N2';
  try {
    await mermaid.default.parse(code);
    console.log('PASS link label 含 #quot;');
  } catch (e) {
    console.log('FAIL link label 含 #: ' + (e.message || e.toString()).split('\n')[0]);
    allPass = false;
  }
}

// 组合最复杂的：财务云 BO 名称含 " / \ / ( / ) / 换行
console.log('\n=== 组合最复杂用例 ===');
{
  const labels = [
    'BO"含双引号',
    'BO\\含反斜杠',
    'BO\n含换行',
    'BO(主)含括号',
    '正常 BO',
  ];
  let code = 'flowchart TB\n';
  labels.forEach((l, i) => { code += '  N' + (i+1) + '["' + sanitizeMermaidLabel(l) + '"]\n'; });
  for (let i = 0; i < labels.length - 1; i++) {
    code += '  N' + (i+1) + ' -- "rel ' + sanitizeMermaidLabel('"with"quote') + '" --> N' + (i+2) + '\n';
  }
  try {
    await mermaid.default.parse(code);
    console.log('PASS 组合用例');
    console.log('  code preview: ' + code.split('\n').slice(1, 3).join(' | '));
  } catch (e) {
    console.log('FAIL 组合用例: ' + (e.message || e.toString()).split('\n')[0]);
    allPass = false;
  }
}

console.log('\n=== 结果: ' + (allPass ? '全部 PASS' : '存在 FAIL') + ' ===');
process.exit(allPass ? 0 : 1);