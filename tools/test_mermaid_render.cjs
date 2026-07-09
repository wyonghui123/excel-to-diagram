// mermaid 11.13.0 实际解析测试 - 用 mermaid 内置的 parser
const { JSDOM } = require('jsdom');
const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>');
global.window = dom.window;
global.document = dom.window.document;
global.navigator = dom.window.navigator;
global.DOMParser = dom.window.DOMParser;
global.HTMLElement = dom.window.HTMLElement;
global.SVGElement = dom.window.SVGElement;
global.Element = dom.window.Element;

(async () => {
  const mermaid = (await import('mermaid')).default;
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
    ['7. label 含 \\" 实际', `flowchart TB
    BO_1["BOSS\\"系统"]`],
    ['8. label 含 \\\\n 实际换行', `flowchart TB
    BO_1["销售订单
(主)"]`],
    ['9. mermaid #quot;', `flowchart TB
    BO_1["BOSS#quot;系统"]`],
    ['10. link label 含 /', `flowchart TB
    A["销售"]
    B["管理"]
    A -->|财务/管理| B`],
  ];

  for (const [name, code] of tests) {
    try {
      await mermaid.parse(code);
      console.log(`✅ ${name}`);
    } catch (e) {
      const msg = String(e.message || e).split('\n').slice(0, 2).join(' | ');
      console.log(`❌ ${name}: ${msg}`);
    }
  }
})();
