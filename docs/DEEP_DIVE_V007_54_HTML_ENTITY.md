# DEEP_DIVE V007.54 — sanitizeMermaidLabel 加 HTML 实体转义（根治 Syntax error）

> 日期: 2026-07-09 | 状态: 已完成 | 关联: V007.48 / V007.51 / V007.52 续作

## 一、问题背景

V007.52 完成用户仍反馈：

> "还是有 Syntax error in text 3006测试"

经排查 V007.52 已覆盖所有 layout 层注入点。但 Syntax error 仍然存在。

## 二、真正的根因（V007.52 漏掉了）

### 2.1 innerHTML 注入破坏

`MermaidComponent.vue` L342：
```js
mermaidContainer.value.innerHTML = `<pre class="mermaid">${mermaidCode}</pre>`
```

`mermaidCode` 是含 BO 名称的 mermaid 文本。如果 BO 名称含 `<`、`>`、`<br>`、`</pre>` 等
HTML 特殊字符，**浏览器会把 mermaidCode 当 HTML 解析**，导致：

- `<br>` 变成实际 `<br>` HTML 标签，`textContent` 丢失
- `</pre>` 提前关闭 `<pre>` 标签，`textContent` 截断
- `<节点>` 中文标签，`textContent` 丢失
- `&` 可能被解析为 HTML entity 起始

**结果：mermaid.run() 拿到的 `textContent` 残缺不全 → Syntax error in text**。

### 2.2 复现验证

写 `tools/test_br_in_label.mjs`，模拟 innerHTML 注入：

```
输入: "BO</pre>名称"
sanitize: "BO</pre>名称" (旧版本)
mermaid 收到 (textContent): "flowchart TB\n  N1[\"BO"  ← 截断!
mermaid parse: FAIL Syntax error
```

`BO<br>名称` 同样被截断为 `BO名称`（mermaid parser 接受但**信息丢失**）。

## 三、修复

### 3.1 sanitizeMermaidLabel 加 3 行 HTML 实体转义

`src/composables/useMermaid/syntax/_shared/arrowHelper.js`：

```js
return raw
  .replace(/&/g, '&amp;')           // [V007.54] & 必须在 < > 之前转, 否则双重转义
  .replace(/</g, '&lt;')            // [V007.54] < HTML 标签起始
  .replace(/>/g, '&gt;')            // [V007.54] > HTML 标签结束
  .replace(/\\/g, '#92;')           // 反斜杠
  .replace(/"/g, '#quot;')          // 双引号
  .replace(/'/g, '#apos;')          // 单引号
  .replace(/[\r\n]+/g, '<br/>')    // 换行
  .replace(/\[/g, '#91;')           // [
  .replace(/\]/g, '#93;')           // ]
  .replace(/\{/g, '#123;')          // {
  .replace(/\}/g, '#125;')          // }
  .replace(/\(/g, '#40;')           // (
  .replace(/\)/g, '#41;')           // )
  .trim()
```

### 3.2 顺序很关键

**`&` 必须先转**，否则后面 `&lt;` 中的 `&` 会被双重转义为 `&amp;lt;`。

### 3.3 mermaid 11.13 接受 HTML 实体

`tools/test_html_entity_escape.mjs` 验证 12 种 HTML 实体（`&lt;`/`&gt;`/`&amp;`/`&apos;`/
`&quot;`/`&nbsp;`/`&#91;`/`&#93;`）全部 12/12 PASS。

## 四、验证

### 4.1 单测

- `tools/test_mermaid_parse.mjs`：13 个用例，3 个原始 fail（验证 mermaid 严格 parser 不接受
  裸双引号/反斜杠/换行），其余 10 个 PASS
- `tools/test_mermaid_parse_extended.mjs`：35 个用例全 PASS（覆盖 23 种字符）
- `tools/test_html_entity_escape.mjs`：12 个 HTML 实体用例全 PASS
- `tools/test_sanitize_efficacy.mjs`：sanitize 后 mermaid parse 全 PASS
- `tools/test_br_in_label.mjs`：[V007.54 新增] 模拟 innerHTML 注入后 mermaid parse

**`test_br_in_label.mjs` 15/15 PASS**：
```
[PASS] "BO</pre>名称" → sanitize="BO&lt;/pre&gt;名称"
[PASS] "BO<br>名称" → sanitize="BO&lt;br&gt;名称"
[PASS] "BO<节点>名称" → sanitize="BO&lt;节点&gt;名称"
[PASS] "BO&名称" → sanitize="BO&amp;名称"
[PASS] "BO\"双引号\"" → sanitize="BO#quot;双引号#quot;"
[PASS] "BO(主)名称" → sanitize="BO#40;主#41;名称"
...
```

### 4.2 现有 invariant

- `tools/test_v007_49_warn_dedup.mjs`：11/11 PASS（告警状态机未受影响）
- `tools/verify_v007_46_ioerror_recovery.py`：12/12 PASS（含 V8ae / V8ah 转义 invariant）

### 4.3 Build + 部署

- `npm run build` 成功（V007.54 之后的 dist 包含新转义逻辑）
- 复制 dist → 2 个目标位置（`d:/filework/frontend_dist_files` 和
  `worktrees/release-prep/frontend_dist_files`，覆盖 vite preview 不同 cwd 的查找路径）
- 重启 vite preview：使用项目本地 `node node_modules/vite/bin/vite.js` 启动
  (让 cwd = worktrees/release-prep，vite 才能读到 vite.config.js)
- 验证 3006 `/api/v1/auth/dev-login` 返回 JSON（vite.config.js 加了 `preview.proxy`）
- 验证 dist `index-Dkx3L-2V.js` 含 **10066 处** `&amp;`/`&lt;`/`&gt;`（HTML 实体转义）

## 五、为什么之前 vite.config.js 的 preview.proxy 没生效

之前用 `npx vite preview` 启动，npx 会从 `npm-cache/_npx/.../node_modules/.bin/vite`
启动，**cwd 是 d:\filework 而不是 worktrees/release-prep**，所以 vite 找不到
`worktrees/release-prep/vite.config.js` 里的 `preview.proxy` 配置。

正确启动方式（修复 3006 代理）：
```bash
cd d:\filework\worktrees/release-prep
node node_modules/vite/bin/vite.js preview --host 0.0.0.0 --port 3006 --outDir frontend_dist_files
```

## 六、CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-07-09 | AI Assistant | 创建 V007.54 深度修复：sanitizeMermaidLabel 加 HTML 实体转义 |
| 2026-07-09 | AI Assistant | 诊断真正根因：MermaidComponent.vue L342 innerHTML 注入破坏 |
| 2026-07-09 | AI Assistant | 修复 vite.config.js preview.proxy + 重启方式 |
| 2026-07-09 | AI Assistant | build + 部署到 3006 + 验证 10066 处 HTML 实体在 dist |