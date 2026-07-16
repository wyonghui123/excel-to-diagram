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

// 模拟 MermaidComponent L372: 注入 "<pre class='mermaid'>${mermaidCode}</pre>"
const mermaidCode = 'flowchart TB\n  A -->|"x"| B';
const div = window.document.createElement('div');
div.innerHTML = '<pre class="mermaid">' + mermaidCode + '</pre>';
const pre = div.querySelector('pre.mermaid');
const received = pre?.textContent || '';
console.log('原始 mermaidCode: ' + JSON.stringify(mermaidCode));
console.log('innerHTML 注入后 textContent: ' + JSON.stringify(received));

try {
  await mermaid.default.parse(received);
  console.log('PASS mermaid parse received');
} catch (e) {
  console.log('FAIL mermaid parse received: ' + (e.message || e.toString()).split('\n')[0]);
}

// 测包含 HTML 实体的
const code2 = 'flowchart TB\n  A -->|"rel&amp;test"| B';
const div2 = window.document.createElement('div');
div2.innerHTML = '<pre class="mermaid">' + code2 + '</pre>';
const pre2 = div2.querySelector('pre.mermaid');
const received2 = pre2?.textContent || '';
console.log('\n原始 code2: ' + JSON.stringify(code2));
console.log('innerHTML 注入后 textContent: ' + JSON.stringify(received2));
try {
  await mermaid.default.parse(received2);
  console.log('PASS mermaid parse received2');
} catch (e) {
  console.log('FAIL mermaid parse received2: ' + (e.message || e.toString()).split('\n')[0]);
}

process.exit(0);