// [V007.53] 测试 innerHTML 注入破坏
// MermaidComponent.vue L342: mermaidContainer.value.innerHTML = `<pre class="mermaid">${mermaidCode}</pre>`
// 如果 mermaidCode 含 </pre> 会破坏 HTML
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

// 模拟 MermaidComponent 的注入
const testCases = [
  { name: '正常 mermaid', code: 'flowchart TB\n  N1["A"]' },
  { name: '含 </pre> (HTML 注入)', code: 'flowchart TB\n  N1["A]</pre><script>alert(1)</script>"]' },
  { name: '含 < (sanitize 后)', code: 'flowchart TB\n  N1["A<B>C"]' },
  { name: '含 &', code: 'flowchart TB\n  N1["A&B"]' },
  { name: '含 \u202e (Unicode Bidi Override)', code: 'flowchart TB\n  N1["A\u202eB"]' },
];

for (const tc of testCases) {
  const container = window.document.createElement('div');
  // 模拟 MermaidComponent.vue L342
  container.innerHTML = `<pre class="mermaid">${tc.code}</pre>`;
  const preEl = container.querySelector('pre.mermaid');
  const found = preEl ? 'yes' : 'NO (corrupted!)';
  const innerText = preEl ? preEl.textContent.slice(0, 80) : 'N/A';
  console.log('[' + found + '] ' + tc.name);
  console.log('  textContent: ' + innerText.replace(/\n/g, '\\n'));
}

process.exit(0);