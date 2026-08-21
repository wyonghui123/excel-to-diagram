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
 *
 * [2026-08-21 图表专项移植] 转义统一为 release 原生 #XX; 方案：
 *   escapeMermaidLabelText / 依赖它的 collapseFormatMarker / businessObjectLabel
 *   全部委托给 release 基底的 sanitizeMermaidLabel（_shared/arrowHelper.js）。
 *   不再使用 HTML 实体（&amp; &lt; &gt; &quot;）：因为 MermaidComponent.vue 用
 *   innerHTML 注入 mermaid 代码会解码实体，导致转义失效；而 #38; #60; #62; #quot;
 *   等 mermaid 原生语法 innerHTML 不解码，视觉与注入防护均正确。
 */
import { sanitizeMermaidLabel } from './_shared/arrowHelper.js'

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
//   [2026-08-21] 容器标记 < > { } [ ] 是 mermaid 语法, 不能整体转义; 仅对内部 name/code 做
//   mermaid 原生 #XX; 转义（经 escapeMermaidLabelText→sanitizeMermaidLabel）, 防业务数据注入 + 防语法破坏。
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

// [2026-08-21 图表专项移植] 对进入 mermaid 节点标签 ["..."] 的文本做原生 #XX; 转义。
//   统一委托给 release 基底的 sanitizeMermaidLabel（_shared/arrowHelper.js），与
//   release 其它 subgraph/node label 转义点语义完全一致。
//   背景: 渲染用 securityLevel:'loose' + htmlLabels:true; 且 MermaidComponent.vue 用
//   innerHTML 注入 mermaid 代码。若用 HTML 实体(&amp; &lt; &gt;)会被 innerHTML 解码回
//   原字符→转义失效; 改用 mermaid 原生 #38; #60; #62; #quot; #apos; #91; #93; 等语法，
//   innerHTML 不解码 → 视觉不变且阻断业务数据注入/语法破坏。
//   注意: \n (两字符字面, mermaid 节点标签换行) 不受影响; 保留函数名以便各调用点沿用。
export function escapeMermaidLabelText(value) {
  return sanitizeMermaidLabel(value)
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
  // [2026-08-21] 名称/编码进入 ["..."] 前做 mermaid 原生 #XX; 转义（经 escapeMermaidLabelText→sanitizeMermaidLabel），防 XSS + 防语法破坏
  const safeName = escapeMermaidLabelText(name)
  if (!code) return `${centerMark}${safeName}`
  return `${centerMark}${safeName}${separator}${escapeMermaidLabelText(code)}`
}
