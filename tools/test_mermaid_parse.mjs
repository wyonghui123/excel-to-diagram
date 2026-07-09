// [V007.51 复现] 用 mermaid 11.13 实际 parser 测试典型 BO 图语法
// 用 happy-dom 提供 DOM（项目已装 devDependency）
import { Window } from 'happy-dom';

const window = new Window({ url: 'http://localhost/' });

function setGlobal(name, value) {
  try {
    Object.defineProperty(globalThis, name, { value, configurable: true, writable: true });
  } catch {
    /* node 24 已内置 navigator 等, 忽略 */
  }
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

// BO 名称样例
const testCases = [];
function tc(name, code) { testCases.push({ name, code }); }

tc('正常 BO 名称', 'flowchart TB\n  N1["销售订单"]\n  N2["用户"]\n  N1 --> N2');
tc('BO 名称含中文括号', 'flowchart TB\n  N1["销售订单(主)"]\n  N2["用户(已认证)"]\n  N1 --> N2');
tc('BO 名称含 " 双引号', 'flowchart TB\n  N1["销售 "BOSS" 系统"]\n  N2["用户"]\n  N1 --> N2');
tc('BO 名称含 / 斜杠', 'flowchart TB\n  N1["销售/订单"]\n  N2["用户/客户"]\n  N1 --> N2');
tc('BO 名称含 \\ 反斜杠', 'flowchart TB\n  N1["B\\OS"]\n  N2["用户"]\n  N1 --> N2');
tc('BO 名称含实际换行', 'flowchart TB\n  N1["销售\n订单"]\n  N2["用户"]\n  N1 --> N2');
tc('subgraph 中文', 'flowchart TB\n  subgraph SG1["◆财务云"]\n    direction TB\n    N1["销售订单"]\n    N2["用户"]\n    N1 --> N2\n  end');
tc('subgraph 名称含 "', 'flowchart TB\n  subgraph SG1["◆销售 "BOSS" 系统"]\n    direction TB\n    N1["销售订单"]\n  end');
tc('subgraph 名称含 <br/>', 'flowchart TB\n  subgraph SG1["◆财务<br/>云"]\n    direction TB\n    N1["销售订单"]\n  end');
tc('link label 含 |', 'flowchart TB\n  N1["A"]\n  N2["B"]\n  N1 -- "label|with|pipe" --> N2');
tc('link label 含 "', 'flowchart TB\n  N1["A"]\n  N2["B"]\n  N1 -- \'label"with"quote\' --> N2');
tc('link label 含 #', 'flowchart TB\n  N1["A"]\n  N2["B"]\n  N1 -- "label#with#hash" --> N2');

// 50 节点
let big = 'flowchart TB\n';
for (let i = 1; i <= 50; i++) big += '  N' + i + '["BO ' + i + '"]\n';
for (let i = 1; i <= 49; i++) big += '  N' + i + ' --> N' + (i + 1) + '\n';
tc('财务云 50 节点', big);

// 用 mermaid 11.13 parse 测试
console.log('=== mermaid 11.13.0 解析测试 ===\n');

const mermaid = await import('mermaid');
mermaid.default.initialize({ startOnLoad: false, securityLevel: 'loose' });

let pass = 0;
let fail = 0;
const failures = [];
for (const t of testCases) {
  try {
    await mermaid.default.parse(t.code);
    console.log('PASS ' + t.name);
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
  console.log('\n=== 失败用例代码 ===');
  for (const f of failures) {
    console.log('\n--- ' + f.name + ' ---');
    console.log(f.code);
  }
}
process.exit(fail > 0 ? 1 : 0);