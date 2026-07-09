// mermaid 11.13.0 实际解析测试 - 不需 jsdom, 用 mermaid 11 内置 parser
import mermaid from 'mermaid';

mermaid.initialize({ startOnLoad: false, securityLevel: 'loose' });

const tests = [
  ['1. 正常', `flowchart TB
    SD_1["财务云"]`],
  ['2. label 含 /', `flowchart TB
    SD_1["财务云 / 销售管理"]`],
  ['3. subgraph label 中文括号', `flowchart TB
    SD_1_2["销售管理（销售）"]`],
  ['4. disabledPath 场景 (L82)', `flowchart TB
    subgraph G_domain_2205["销售管理（财务云 / 销售）"]
        direction TB
        BO_100["销售订单(主)"]
    end`],
  ['5. 600 节点', `flowchart TB
${Array.from({length: 600}, (_, i) => `    BO_${i}["销售订单${i}\\n(CODE_${i})"]`).join('\n')}`],
  ['6. label 含 (', `flowchart TB
    BO_1["销售订单(主)"]`],
  ['7a. label 含 双引号 raw', `flowchart TB
    BO_1["BOSS"系统"]`],
  ['7b. label 含 1 个反斜杠 + 双引号', `flowchart TB
    BO_1["BOSS\"系统"]`],
  ['7c. label 含 2 个反斜杠 + 双引号', `flowchart TB
    BO_1["BOSS\\"系统"]`],
  ['12. label 含 /', `flowchart TB
    A["财务云 / 销售管理"]`],
  ['13. label 含 \n mermaid 强制换行', `flowchart TB
    A["财务云\\n销售管理"]`],
  ['14. label 含 ( 和 )', `flowchart TB
    A["销售订单(主)"]`],
  ['15. label 含 <br/>', `flowchart TB
    A["财务云<br/>销售管理"]`],
  ['16. subgraph 内部 node label 含 /', `flowchart TB
    subgraph G_SD_1["财务云"]
        direction TB
        BO_1["销售订单/子项"]
    end`],
  ['17. 600 节点用 #quot; 转义双引号', `flowchart TB
${Array.from({length: 600}, (_, i) => `    BO_${i}["BO${i}#quot;code${i}"]`).join('\n')}`],
  ['8. label 含 实际换行', `flowchart TB
    BO_1["销售订单
(主)"]`],
  ['9. mermaid #quot;', `flowchart TB
    BO_1["BOSS#quot;系统"]`],
  ['10. link label 含 /', `flowchart TB
    A["销售"]
    B["管理"]
    A -->|财务/管理| B`],
  ['11. 600 节点 + 关系 600', `flowchart TB
${Array.from({length: 600}, (_, i) => `    BO_${i}["销售订单${i}\\n(CODE_${i})"]`).join('\n')}
${Array.from({length: 600}, (_, i) => `    BO_${i} -->|"依赖${i}"| BO_${(i+1) % 600}`).join('\n')}`],
];

for (const [name, code] of tests) {
  try {
    const r = await mermaid.parse(code);
    console.log(`✅ ${name}: OK`);
  } catch (e) {
    const msg = String(e.message || e).split('\n').slice(0, 3).join(' | ');
    console.log(`❌ ${name}: ${msg}`);
  }
}
