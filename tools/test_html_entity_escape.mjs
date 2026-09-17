// [V007.53] 测 mermaid 11.13 是否接受 HTML 实体转义 (&lt; &gt; &amp; &apos;)
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

const testCases = [];
function tc(name, code) { testCases.push({ name, code }); }

// 节点 label 用 HTML 实体
tc('节点 &lt;', 'flowchart TB\n  N1["A&lt;B"]');
tc('节点 &gt;', 'flowchart TB\n  N1["A&gt;B"]');
tc('节点 &amp;', 'flowchart TB\n  N1["A&amp;B"]');
tc('节点 &apos;', 'flowchart TB\n  N1["A&apos;B"]');
tc('节点 &quot;', 'flowchart TB\n  N1["A&quot;B"]');
tc('节点 &nbsp;', 'flowchart TB\n  N1["A&nbsp;B"]');
tc('节点 &#91;', 'flowchart TB\n  N1["A&#91;B"]');
tc('节点 &#93;', 'flowchart TB\n  N1["A&#93;B"]');
tc('节点 &amp;&lt;&gt;', 'flowchart TB\n  N1["A&amp;&lt;&gt;B"]');

// subgraph label
tc('subgraph &lt;', 'flowchart TB\n  subgraph SG1["A&lt;B"]\n  end');

// link label
tc('link label &lt;', 'flowchart TB\n  N1["A"]\n  N2["B"]\n  N1 -- "A&lt;B" --> N2');

// 各种组合
tc('组合 &lt; &gt; &amp;', 'flowchart TB\n  N1["A&lt;B&gt;C&amp;D"]');

let pass = 0, fail = 0;
for (const t of testCases) {
  try {
    await mermaid.default.parse(t.code);
    console.log('PASS ' + t.name);
    pass++;
  } catch (e) {
    console.log('FAIL ' + t.name + ': ' + (e.message || e.toString()).split('\n')[0]);
    fail++;
  }
}
console.log('\n=== 结果: ' + pass + ' pass, ' + fail + ' fail ===');
process.exit(fail > 0 ? 1 : 0);