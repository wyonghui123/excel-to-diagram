/**
 * 节点/容器/折叠标签统一模板层
 *
 * [TEMPLATE 2026-08-11] 单一事实来源：所有节点文字展示格式集中定义于此，
 *   各渲染点（groupedLayout / useBusinessObjectSyntax / useBlockDiagramSyntax）
 *   改为调用本模板，避免 20+ 处硬编码拼接导致的格式不一致与调整遗漏。
 *
 * 未来优化（字号/换行/标记样式/祖先路径）只需改本文件对应函数即可全局生效。
 *
 * 注意：
 * - 所有返回值中的 `\\n` 是"反斜杠 n"两个字面字符（Mermaid 节点标签的换行转义），
 *   不是真实换行符。调用方直接拼进 mermaid `["..."]` 内即可。
 * - BO 叶子节点统一为「名称\n编码」两行显示（2026-08-11 决策，与 groupedLayout 主流一致）。
 */

// 名称去尾随父路径后缀：兼容半角 () 与全角 （），仅去掉末尾单个括号组（内容不再含括号）。
//   如 "销售（供应链云）" → "销售"。避免父分组名称出现在子容器标题。
export function extractOwnGroupName(name) {
  if (!name) return name
  const str = String(name).trim()
  const m = str.match(/^(.+?)[（(]([^（()]*)[）)]$/)
  if (m && m[1]) return m[1].trim()
  return str
}

// 容器标题包裹符号（按层级类型）。其它类型返回 null，调用方保持原标题格式。
//   domain → <供应链云> / subdomain → {供应链计划} / servicemodule → [需求计划]
export function getContainerMarkers(type) {
  const t = String(type || '').toLowerCase().replace(/_/g, '')
  if (t === 'domain') return ['<', '>']
  if (t === 'subdomain') return ['{', '}']
  if (t === 'servicemodule') return ['[', ']']
  return null
}

// 折叠/上提聚合节点标题（COLLAPSE_）：名称置于标记内，类型+编码置下方。
//   - 领域:     <供应链云>\n领域 SCM
//   - 子领域:   {供应链计划}\n子领域 SCP
//   - 服务模块: [需求计划]\n服务模块 DP
//   无编码或名称或无法识别类型时返回空串（调用方回退原格式）。业务对象不经过此路径。
//   [SEC 2026-08-19] 容器标记 < > { } [ ] 是 mermaid 语法, 不能整体转义; 仅对内部 name/code 做
//   HTML 实体转义, 防业务数据注入 + 防语法破坏, 显示不变 (浏览器解码实体回原字符)。
export function collapseFormatMarker(type, code, name) {
  if (!code || !name) return ''
  const t = String(type || '').toLowerCase().replace(/_/g, '')
  const ownName = escapeMermaidLabelText(extractOwnGroupName(name))
  const safeCode = escapeMermaidLabelText(code)
  if (t === 'domain') return `<${ownName}>\\n领域 ${safeCode}`
  if (t === 'subdomain') return `{${ownName}}\\n子领域 ${safeCode}`
  if (t === 'servicemodule') return `[${ownName}]\\n服务模块 ${safeCode}`
  return ''
}

// [SEC 2026-08-19] 对进入 mermaid 节点标签 ["..."] 的文本做 HTML 实体转义。
//   背景: 渲染用 securityLevel:'loose' + htmlLabels:true, 节点标签经 foreignObject HTML 渲染。
//   - & < > 若不转义会被当作 HTML 标签/实体解析 → 业务数据(名称/编码)可注入 DOM (XSS)
//   - " 若不转义会提前结束 mermaid 的 ["..."] 字符串 → 非法语法
//   改用 HTML 实体后浏览器解码显示为原字符 → 视觉不变, 且阻断注入。
//   注意: \n (两字符字面, mermaid 节点标签换行) 不受影响; 顺序先 & 避免二次转义。
export function escapeMermaidLabelText(value) {
  if (value == null) return value
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// BO 叶子节点标签：统一「名称\n编码」两行显示。
//   @param {Object} node - { name|originalName, code }
//   @param {Object} [opts] - { centerMark: '◆', separator: '\\n' }
export function businessObjectLabel(node, opts = {}) {
  const name = node.originalName || node.name
  const centerMark = opts.centerMark || ''
  const separator = opts.separator !== undefined ? opts.separator : '\\n'
  const code = node.code || node.nodeCode
  if (!name) return ''
  // [SEC 2026-08-19] 名称/编码进入 ["..."] 前做 HTML 实体转义, 防 XSS + 防语法破坏
  const safeName = escapeMermaidLabelText(name)
  if (!code) return `${centerMark}${safeName}`
  return `${centerMark}${safeName}${separator}${escapeMermaidLabelText(code)}`
}
