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

const tests = [
  'A -->|"x"| B',
  'A --> B',
  'A -- B',
  'A -.-> B',
  'A ==> B',
  'A <-- B',
  'A --- B',
];
for (const t of tests) {
  const div = window.document.createElement('div');
  div.innerHTML = '<pre class="mermaid">' + t + '</pre>';
  const pre = div.querySelector('pre.mermaid');
  console.log('input: ' + JSON.stringify(t) + ' -> textContent: ' + JSON.stringify(pre?.textContent));
}
process.exit(0);