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

const tests = [
  'flowchart TB\n  A -->|"x"| B',
  'flowchart TB\n  A --> x B',
  'flowchart TB\n  A ---|"x"| B',
  'flowchart TB\n  A -- x --- B',
  'flowchart TB\n  A -- "x" --> B',
  'flowchart TB\n  A -->|"正常"| B',
  'flowchart TB\n  A -->|"rel&amp;test"| B',
  'flowchart TB\n  A -->|"rel&lt;tag&gt;"| B',
  'flowchart TB\n  A -.->|"x"| B',
  'flowchart TB\n  A -->|"x"| B\n  B -->|"y"| C',
];
for (const t of tests) {
  try {
    await mermaid.default.parse(t);
    console.log('PASS ' + t.replace(/\n/g, ' \\n '));
  } catch (e) {
    console.log('FAIL ' + t.replace(/\n/g, ' \\n ') + ' -> ' + (e.message || e.toString()).split('\n')[0]);
  }
}
process.exit(0);