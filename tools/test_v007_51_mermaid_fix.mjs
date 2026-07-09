// [V007.51 P0] mermaid 11.13 实际解析测试 - 模拟 useBusinessObjectSyntax 输出
import { sanitizeMermaidLabel } from '../src/composables/useMermaid/syntax/_shared/arrowHelper.js';

// 模拟 useBusinessObjectSyntax.js 的 subgraph 生成
function genSubgraphTitle(groupName, centerMark, type, parent, grandparent) {
  let subgraphTitle
  if (type === 'submodule') {
    subgraphTitle = `${centerMark}${groupName}\\n(${grandparent}/${parent})`
  } else if (type === 'module') {
    subgraphTitle = `${centerMark}${groupName}\\n(${parent})`
  } else {
    subgraphTitle = centerMark + groupName
  }
  // V007.51 P0 修复: 转义
  return sanitizeMermaidLabel(subgraphTitle)
}

// 模拟 L1180-1181 (BO 节点)
function genNodeLabel(nodeName, nodeCode) {
  const safeNodeName = sanitizeMermaidLabel(nodeName)
  const safeNodeCode = sanitizeMermaidLabel(nodeCode)
  const displayText = safeNodeCode ? `${safeNodeName} · (${safeNodeCode})` : safeNodeName
  return displayText
}

const testCases = [
  // groupName 含特殊字符
  { name: '财务云', code: 'FIN_001', type: 'module', parent: '销售管理' },
  { name: '销售 "BOSS" 系统', code: 'SALE_001', type: 'module', parent: '销售管理' },
  { name: 'B\\OS', code: 'TEST_001', type: 'submodule', parent: '服务A', grandparent: '财务云' },
  { name: '财务\n云', code: 'FIN_002', type: 'module', parent: '销售' },
  { name: '正常 BO', code: 'ORD_001', type: 'module', parent: 'P1' },
];

console.log('=== V007.51 P0 单元测试 ===\n');
for (const t of testCases) {
  const safeTitle = genSubgraphTitle(t.name, '◆', t.type, t.parent, t.grandparent)
  const safeNodeLabel = genNodeLabel(t.name, t.code)
  console.log(`groupName: ${JSON.stringify(t.name)}`)
  console.log(`  subgraph title (sanitized): ${JSON.stringify(safeTitle)}`)
  console.log(`  node label (sanitized):     ${JSON.stringify(safeNodeLabel)}`)
  console.log()
}

// 测试: 含 " 时不再触发 syntax error
const dangerousName = '销售 "BOSS" 系统'
const safeTitle = genSubgraphTitle(dangerousName, '◆', 'module', '销售管理', undefined)
const code = `flowchart TB
  subgraph SG1["${safeTitle}"]
    direction TB
    BO_1["${genNodeLabel('销售订单(主)', 'ORD_001')}"]
  end
`
console.log('=== 完整 mermaid 代码 (含 " 字符) ===')
console.log(code)
console.log('应无双引号 (除 mermaid 包裹) - V007.51 修复成功')
console.log(`含 " 数量: ${(code.match(/"/g) || []).length} (应 4: 2 包裹 subgraph + 2 包裹 node)`)
console.log(`含 \\n 实际换行: ${code.split('\\n').length - 1} (应 0 或 1, 不应有 BO 名称的换行)`)
