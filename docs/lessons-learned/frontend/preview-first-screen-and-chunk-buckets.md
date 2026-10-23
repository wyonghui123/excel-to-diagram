# 预览环境首屏体积与分包桶陷阱

## 一、症状

生产构建产物经 Cloudflare 隧道访问时页面长时间白屏（`#app` 为空、无 JS 报错、
无失败请求）。本地直连同一份产物秒开，因此容易被误判为隧道故障。

## 二、根因

`vite.config.js` 的 `manualChunks` 把"未命中任何规则的第三方库"统一兜底到
`vendor-mermaid` 桶。这个兜底桶实际同时装着：

| 来源 | 模块数 | 性质 |
|------|--------|------|
| `mermaid` 及其族依赖（d3 / dagre / katex / cytoscape / langium / chevrotain） | ~500 | 仅图表页使用 |
| `lodash-es` / `core-js` / `dayjs` / `@babel/runtime` | ~460 | Element Plus 等首屏必需 |
| `@vue/shared` / `@vue/runtime-core` / `@vue/runtime-dom` / `@vue/reactivity` | 4 | Vue 运行时本身 |

`element-plus` 依赖 `lodash-es` 与 `@vue/shared`，两者都在该桶内 ⇒
`vendor-vue-ep` 静态 import `vendor-mermaid` ⇒ **5.3MB 图表库成为首屏硬依赖**。
入口 chunk 的 `modulepreload` 因此包含整包 mermaid。

用 sourcemap 的 `sources` 可精确核对每个桶的成员，不要靠体积猜测：

```python
json.load(open("dist/assets/vendor-mermaid-*.js.map"))["sources"]
```

## 三、四条路线的实测结果

| # | 做法 | 结果 |
|---|------|------|
| 1 | 在 vue-ep 规则补 `/@vue/` | 无效。`@vue/shared` 的边断了，`lodash-es` 的边仍在，首屏仍 preload mermaid |
| 2 | 兜底桶拆成 `vendor-misc` + `vendor-mermaid` | 出现 `Circular chunk: vendor-mermaid -> vendor-misc -> vendor-mermaid`；`misc` 仍被入口静态引用，首屏字节不变 |
| 3 | 兜底桶整体并入 `vendor-vue-ep` | 出现 `Circular chunk: vendor-mermaid -> vendor-vue-ep -> vendor-mermaid`；首屏仍 preload mermaid（2026-10-12 的回滚记录正是这一形态） |
| 4 | **关闭 `manualChunks`，交回 Rollup 自动判定** | 无循环；入口不再含 mermaid；93 个 chunk 通过 `scripts/check_chunk_cycles.mjs` |

结论：只要手工把 Vue 运行时与 mermaid 族依赖分到不同桶，就会产生双向 import 边。
这类循环不是靠补规则能消除的，需要让打包器按动态边界自行切分。

## 四、当前口径

- `rollupOptions.output.manualChunks: undefined`；原规则函数保留为
  `_manualChunks_disabled`（含历史回滚记录，勿再启用）。
- 首屏：入口 437KB gzip + CSS 50KB ≈ **486KB gzip**（此前 ≈ 2.0MB）。
- 图表页的 `MermaidComponent` / mermaid 核 / cytoscape 均为懒加载 chunk，
  只在进入图表路由时请求。

## 五、缓存头

`vite preview` 会继承 `server.headers` 的 `no-store`，导致每次访问全量重下。
新增 `preview-cache-headers` 插件：

- `/assets/*` → `public, max-age=31536000, immutable`（文件名自带 hash）；
- 其余路径保持 `no-store`，保证重建后立即生效。

注意：Cloudflare quick tunnel 一律 `cf-cache-status: DYNAMIC`，边缘不缓存，
所以该改动只改善浏览器侧重复访问，不改善冷启动。

## 六、验证方法

1. `npm run build:raw` 后检查 `dist/index.html` 的 `modulepreload` 列表，
   确认不含 mermaid 相关文件；
2. `node scripts/check_chunk_cycles.mjs` 必须无环；
3. PlaywrightCLI 冒烟：业务伙伴页 `#app` 非空、页签正常；
   图表页确认 `MermaidComponent` chunk 是**按需**加载；
4. 经隧道逐文件计时，核对首屏总字节与耗时。

## CHANGELOG

| 日期 | 变更 |
|------|------|
| 2026-10-23 | 首版：记录白屏根因、四条分包路线实测、关闭 manualChunks、预览缓存头 |
