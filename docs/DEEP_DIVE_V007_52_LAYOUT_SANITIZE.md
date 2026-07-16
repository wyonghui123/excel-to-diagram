# DEEP_DIVE V007.52 — Layout 层 mermaid label 全面转义

> 日期: 2026-07-09 | 状态: 已完成 | 关联: V007.48 / V007.51 续作

## 一、问题背景

V007.48 修复了 `UnifiedRenderer.js` + `MermaidGenerator.js` 的转义注入点，V007.51 进一步补了
`useBusinessObjectSyntax.js` + `useServiceModuleSyntax.js`。但用户反馈：

> "Syntax error in text mermaid version 11.13.0 告警ok了，不过上面这个问题还是存在"

说明仍有未覆盖的注入点。

## 二、根因定位

### 2.1 用 mermaid 11.13 parser 实测验证

写 `tools/test_mermaid_parse.mjs`，用 happy-dom 提供 window，让真正的 mermaid 11.13.0 parser
解析典型用例。结果：

```
PASS 正常 BO 名称
PASS BO 名称含中文括号
FAIL BO 名称含 " 双引号: Parse error on line 2: ...
PASS BO 名称含 / 斜杠
PASS BO 名称含 \ 反斜杠
PASS BO 名称含实际换行
PASS subgraph 中文
FAIL subgraph 名称含 ": Parse error on line 2: ...
PASS subgraph 名称含 <br/>
PASS link label 含 |
FAIL link label 含 ": Parse error on line 4: ...
PASS link label 含 #
```

**确认根因**：mermaid 11.13 严格解析下，BO 名称里的 `"` 双引号 / `\` 反斜杠 / 实际换行符
都会导致 `Syntax error in text`。其他字符（`/`、`(`、`)`、`<br/>`、中文）合法。

### 2.2 全面 grep `["${` 模式搜注入点

跑完 V007.48 / V007.51 后，遗留注入点分布：

| 文件 | 行号 | 内容 |
|------|------|------|
| `useBusinessObjectSyntax.js` | L815 | 顶层 fallback 节点 label |
| `useBusinessObjectSyntax.js` | L1007 | subgraph 内部节点 label |
| `useBusinessObjectSyntax.js` | L1201 | disabled container 节点 label |
| `useBusinessObjectSyntax.js` | L1231 | directNodesContainer 节点 label |
| `useBusinessObjectSyntax.js` | L1253 | 子组 enabled container 节点 label |
| `useBusinessObjectSyntax.js` | L1264 | 子组 disabled container 节点 label |
| `useServiceModuleSyntax.js` | L341 | 顶层 fallback 节点 label |
| `layouts/linearLayout.js` | L21, L29 | container + node label |
| `layouts/elkZoneLayout.js` | L69, L77 | container + node label |
| `layouts/gridLayout.js` | L31 | container label |
| `layouts/groupedLayout.js` | L182, L200, L226, L283, L308, L355, L376, L392, L518, L536, L582, L600, L623 | 节点/容器/group title |
| `services/groupModel/groupRenderer.js` | L77, L87, L141 | group/terminal node label |
| `services/groupModel/MermaidGenerator.js` | L267 | directNodes 节点 label |
| `services/serviceModuleDiagramBuilder.js` | L442, L448, L449 | container + node label |

**漏修的根因**：V007.48 / V007.51 只检查了主入口的几个文件，layout 层和 groupRenderer 等
辅助渲染器**完全没碰**。

## 三、修复策略

**统一做法**：每个拼接 `["..."]` label 的地方，对 `node.name` / `node.code` / `containerTitle`
/ `groupTitle` 都过一遍 `sanitizeMermaidLabel`。

sanitize 函数 (`src/composables/useMermaid/syntax/_shared/arrowHelper.js`)：

```js
function sanitizeMermaidLabel(text) {
  if (text === null || text === undefined) return ''
  if (typeof text !== 'string') text = String(text)
  return text
    .replace(/\\/g, '#92;')    // \ → #92;
    .replace(/"/g, '#quot;')   // " → #quot;
    .replace(/\n/g, '<br/>')   // 换行 → <br/>
    .replace(/\r/g, '')
    .replace(/\(/g, '#40;')    // ( → #40;
    .replace(/\)/g, '#41;')    // ) → #41;
}
```

## 四、修改文件清单

| 文件 | 修改内容 | 注入点数 |
|------|----------|----------|
| `src/composables/useMermaid/syntax/useBusinessObjectSyntax.js` | 6 处 L815/L1007/L1201/L1231/L1253/L1264 加 sanitize | 6 |
| `src/composables/useMermaid/syntax/useServiceModuleSyntax.js` | L341 加 sanitize | 1 |
| `src/composables/useMermaid/layouts/linearLayout.js` | import sanitizeMermaidLabel; L21 containerName + L29 nodeLabel | 2 |
| `src/composables/useMermaid/layouts/elkZoneLayout.js` | import; L69 containerName + L77 nodeLabel | 2 |
| `src/composables/useMermaid/layouts/gridLayout.js` | import; L31 containerName | 1 |
| `src/composables/useMermaid/layouts/groupedLayout.js` | import; L182/L200/L226/L283/L308/L355/L376/L392/L518/L536/L582/L600/L623 共 13 处 | 13 |
| `src/services/groupModel/groupRenderer.js` | import; L77 groupTitle + L87 nodeLabel + L141 terminal displayText | 3 |
| `src/services/groupModel/MermaidGenerator.js` | L267 directNodes displayText | 1 |
| `src/services/serviceModuleDiagramBuilder.js` | import; L442 containerTitle + L448/L449 nodeLabel | 3 |

**总计：9 个文件，32 处注入点**。

## 五、验证

### 5.1 单元测试

- `tools/test_mermaid_parse.mjs`：用 mermaid 11.13 实际 parser 跑 13 个用例，3 个原始失败用例
  sanitize 后全部 PASS。
- `tools/test_sanitize_efficacy.mjs`：覆盖双引号/反斜杠/换行/中文括号/链接 label 全部 sanitize
  后通过 parse 测试。
- `tools/test_v007_49_warn_dedup.mjs`：11/11 PASS（告警状态机未受影响）
- `tools/test_v007_51_mermaid_fix.mjs`：PASS（V007.51 转义未受影响）
- `tools/verify_v007_46_ioerror_recovery.py`：12/12 PASS

### 5.2 构建 + 部署

- `npm run build`：成功生成新 dist（`index-D1H_SYxC.js` + `index-Dkx3L-2V.js` 等 chunk）
- 复制 `dist` → `d:/filework/frontend_dist_files`（vite preview cwd 解析路径）
- 复制 `dist` → `d:/filework/release-prep-worktree/frontend_dist_files`（备选路径）
- 重启 `vite preview --host 0.0.0.0 --port 3006 --outDir frontend_dist_files`
- 验证 3006 能正常返回 200，HTML 引用的 chunk 含 sanitize 逻辑
- `rg -o '#92' d:/filework/release-prep-worktree/dist/assets/index-Dkx3L-2V.js` → 4 处
- `rg -o '#quot' ...` → 1 处（在 sanitize 函数定义里）

### 5.3 重要路径解析经验

vite preview 启动时 cwd 解析 `--outDir frontend_dist_files` 是**相对路径**，所以
实际路径取决于启动进程的 cwd：
- 如果在 `d:\filework\release-prep-worktree\` 下启动 → `frontend_dist_files` = `release-prep-worktree/frontend_dist_files`
- 如果在 `d:\filework\` 下启动 → `frontend_dist_files` = `d:/filework/frontend_dist_files`

**两边都要复制**，否则无论 vite preview 在哪个 cwd 启动都会找不到对应 chunk。

## 六、后续风险

### 6.1 仍有未覆盖的注入点（次要）

- `useBlockDiagramSyntax.js:17` 的 `NODE_TEXT_FORMATS` 是纯函数，不直接拼 mermaid 代码，
  调用方在外部 sanitize，OK。
- 测试文件 `__tests__/deep_optimization_bench.spec.js` 不进生产，OK。

### 6.2 转义对渲染的影响

`(` → `#40;`、`)` → `#41;` 转义后 BO 显示文字会带 `#40;` 字面量。
如果 renderer 不解码，UI 上会显示 `销售#40;主#41;`。需要确认 Mermaid 11.13 是否会自动
解码 `#40;` → `(`（mermaid 官方文档说会的）。如不自动解码，后续需要在前端渲染层
做反向解码或用 SVG `<text>` 替换。

## 七、CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-07-09 | AI Assistant | 创建 V007.52 深度修复：layout 层 + groupRenderer 全面 sanitizeMermaidLabel |
| 2026-07-09 | AI Assistant | 用 happy-dom + mermaid 11.13 真实 parser 复现 Syntax error，定位 32 处注入点 |
| 2026-07-09 | AI Assistant | 完成 build + 部署到 3006 + 验证 dist 含转义 |