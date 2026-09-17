// [V007.55] 测试 mermaid 11.13 解析 link label 含 HTML 实体的语法
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

const mermaid = await import('mermaid');
mermaid.default.initialize({ startOnLoad: false, securityLevel: 'loose' });

// 测 link label 各种语法 + 字符
const cases = [
  // 单向 + label
  'flowchart TB\n  A -->|"rel"| B',
  'flowchart TB\n  A -->|"rel&test"| B',
  'flowchart TB\n  A -->|"rel<tag>"| B',
  'flowchart TB\n  A -->|"rel<br/>break"| B',
  'flowchart TB\n  A -->|"rel&"x"| B',
  // 双向 + label (无引号包裹, 裸 label)
  'flowchart TB\n  A <-- rel --> B',
  'flowchart TB\n  A <-- rel&test --> B',
  'flowchart TB\n  A <-- rel<tag> --> B',
  'flowchart TB\n  A <-- rel<br/>break --> B',
  // 关系实例编码 (BO_RSCM005-RSCM001)
  'flowchart TB\n  A -->|"BO_001-BO_002"| B',
];

let pass = 0, fail = 0;
for (const code of cases) {
  try {
    await mermaid.default.parse(code);
    console.log('PASS ' + JSON.stringify(code));
    pass++;
  } catch (e) {
    console.log('FAIL ' + JSON.stringify(code) + ' - ' + (e.message || e.toString()).split('\n')[0]);
    fail++;
  }
}

// 测 innerHTML 注入: 验证 link label 含 < 或 > 时 mermaid 收到完整代码
console.log('\n=== innerHTML 注入 + mermaid parse 组合测试 ===');
const innerCases = [
  'flowchart TB\n  A -->|"rel<tag>"| B',
  'flowchart TB\n  A <-- rel<tag> --> B',
  'flowchart TB\n  A -->|"rel&x"| B',
  'flowchart TB\n  A <-- rel&x --> B',
];

for (const code of innerCases) {
  const div = window.document.createElement('div');
  div.innerHTML = '<pre class="mermaid">' + code + '</pre>';
  const received = div.querySelector('pre.mermaid')?.textContent || '';
  try {
    await mermaid.default.parse(received);
    console.log('PASS ' + JSON.stringify(code) + ' → received: ' + JSON.stringify(received));
    pass++;
  } catch (e) {
    console.log('FAIL ' + JSON.stringify(code) + ' → received: ' + JSON.stringify(received));
    console.log('  error: ' + (e.message || e.toString()).split('\n')[0]);
    fail++;
  }
}

console.log('\n=== ' + pass + ' pass, ' + fail + ' fail ===');
process.exit(fail > 0 ? 1 : 0);