// [V007.53 复现] 用 mermaid 11.13 实际 parser 测试更多可能的注入点
// 重点: 财务云真实数据可能含的字符
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

// [V007.53] 镜像 sanitizeMermaidLabel (与 src 完全一致)
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

const testCases = [];
function tc(name, code) { testCases.push({ name, code }); }

// ============== 节点 label 测试 ==============
tc('节点含 # (hash)', 'flowchart TB\n  N1["A#B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 ; (分号)', 'flowchart TB\n  N1["A;B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 : (冒号)', 'flowchart TB\n  N1["A:B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 | (管道)', 'flowchart TB\n  N1["A|B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 [ ] (方括号)', 'flowchart TB\n  N1["A[B]C"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 { } (花括号)', 'flowchart TB\n  N1["A{B}C"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 \' (单引号)', 'flowchart TB\n  N1["A\'B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 , (逗号)', 'flowchart TB\n  N1["A,B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 . (点)', 'flowchart TB\n  N1["A.B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 = (等号)', 'flowchart TB\n  N1["A=B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 + (加号)', 'flowchart TB\n  N1["A+B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 - (减号)', 'flowchart TB\n  N1["A-B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 < > (尖括号)', 'flowchart TB\n  N1["A<B>C"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 @ (at)', 'flowchart TB\n  N1["A@B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 & (and)', 'flowchart TB\n  N1["A&B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 % (百分号)', 'flowchart TB\n  N1["A%B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 $ (美元)', 'flowchart TB\n  N1["A$B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 ! (感叹号)', 'flowchart TB\n  N1["A!B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 ? (问号)', 'flowchart TB\n  N1["A?B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 * (星号)', 'flowchart TB\n  N1["A*B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 ^ (尖)', 'flowchart TB\n  N1["A^B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 ~ (波浪)', 'flowchart TB\n  N1["A~B"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 ` (反引号)', 'flowchart TB\n  N1["A`B"]\n  N2["C"]\n  N1 --> N2');

// ============== 财务云实际可能含的字符 (财务云 BO 名称通常含下划线/横线) ==============
tc('节点含 _ (下划线)', 'flowchart TB\n  N1["Sales_Order"]\n  N2["User"]\n  N1 --> N2');
tc('节点含空格', 'flowchart TB\n  N1["销售 订单"]\n  N2["用户"]\n  N1 --> N2');
tc('节点含 Unicode 控制字符', 'flowchart TB\n  N1["A\u200BB"]\n  N2["C"]\n  N1 --> N2');

// ============== link label 测试 ==============
tc('link label 含 | (变长箭头语法)', 'flowchart TB\n  N1["A"]\n  N2["B"]\n  N1 -->|"|"| N2');
tc('link label 含 [ (mermaid 11 特殊)', 'flowchart TB\n  N1["A"]\n  N2["B"]\n  N1 -- "[A]" --> N2');
tc('link label 含 \\\\ (反斜杠)', 'flowchart TB\n  N1["A"]\n  N2["B"]\n  N1 -- "A\\B" --> N2');
tc('link label 含换行', 'flowchart TB\n  N1["A"]\n  N2["B"]\n  N1 -- "A\nB" --> N2');

// ============== 用 sanitizeMermaidLabel 测 ==============
tc('节点含 [ ] (sanitize后)', 'flowchart TB\n  N1["' + sanitizeMermaidLabel('A[B]C') + '"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 { } (sanitize后)', 'flowchart TB\n  N1["' + sanitizeMermaidLabel('A{B}C') + '"]\n  N2["C"]\n  N1 --> N2');
tc('节点含 \' (sanitize后)', 'flowchart TB\n  N1["' + sanitizeMermaidLabel("A'B") + '"]\n  N2["C"]\n  N1 --> N2');

// ============== subgraph id 测试 ==============
tc('subgraph id 含中文', 'flowchart TB\n  subgraph 财务云\n    N1["A"]\n  end');
tc('subgraph id 含点', 'flowchart TB\n  subgraph C.1\n    N1["A"]\n  end');

const mermaid = await import('mermaid');
mermaid.default.initialize({ startOnLoad: false, securityLevel: 'loose' });

let pass = 0;
let fail = 0;
const failures = [];
for (const t of testCases) {
  try {
    await mermaid.default.parse(t.code);
    pass++;
  } catch (e) {
    const msg = (e.message || e.toString()).split('\n')[0];
    console.log('FAIL ' + t.name + ': ' + msg);
    failures.push({ name: t.name, msg, code: t.code });
    fail++;
  }
}
console.log('\n=== 结果: ' + pass + ' pass, ' + fail + ' fail ===');
if (fail > 0) {
  console.log('\n=== 失败用例 ===');
  for (const f of failures) {
    console.log('\n--- ' + f.name + ' ---');
    console.log(f.code);
  }
}
process.exit(fail > 0 ? 1 : 0);