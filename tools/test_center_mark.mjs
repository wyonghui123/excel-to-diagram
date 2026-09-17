// [V007.55 验证] mermaid 11.13 是否接受 ◆ 特殊字符
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

// 测试一些 UnifiedRenderer 实际可能产生的字符
const cases = [
  // centerMark
  'flowchart TB\n  N1["◆ 财务云"]\n  N2["应用"]\n  N1 --> N2',
  'flowchart TB\n  N1["◆ 财务云(AR_001)"]\n  N2["应用"]\n  N1 --> N2',
  // displayCode 强制换行
  'flowchart TB\n  N1["◆ 财务云\\n(AR_001)"]\n  N2["应用"]\n  N1 --> N2',
  // 实际 BO 名称含括号
  'flowchart TB\n  N1["发票(BOSS 系统)"]\n  N2["应用"]\n  N1 --> N2',
  'flowchart TB\n  N1["发票#40;BOSS 系统#41;"]\n  N2["应用"]\n  N1 --> N2',
  // 实测 <br/>
  'flowchart TB\n  N1["应收单<br/>主表"]\n  N2["应用"]\n  N1 --> N2',
  // 含 HTML 实体
  'flowchart TB\n  N1["应收单&lt;br&gt;主表"]\n  N2["应用"]\n  N1 --> N2',
  // 中文括号
  'flowchart TB\n  N1["应收单（主表）"]\n  N2["应用"]\n  N1 --> N2',
  // 已转义的字符
  'flowchart TB\n  N1["应付单#40;总#41;"]\n  N2["应用"]\n  N1 --> N2',
  // edge label 含 < >
  'flowchart TB\n  N1["A"]\n  N2["B"]\n  N1 -->|"&lt;关联&gt;"| N2',
  // 强制换行 \n 转义
  'flowchart TB\n  N1["A\\nB"]',
  'flowchart TB\n  N1["A\nB"]',  // 实际换行
];

let pass = 0, fail = 0;
for (const c of cases) {
  try {
    await mermaid.default.parse(c);
    console.log('PASS ' + JSON.stringify(c));
    pass++;
  } catch (e) {
    console.log('FAIL ' + JSON.stringify(c));
    console.log('  ' + (e.message || e.toString()).split('\n')[0]);
    fail++;
  }
}
console.log('\n=== ' + pass + ' pass, ' + fail + ' fail ===');
process.exit(0);