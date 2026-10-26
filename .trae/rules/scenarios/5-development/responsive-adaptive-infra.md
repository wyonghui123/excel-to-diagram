---
title: 双端自适应基础设施规范
scenario: 5-development
status: 活跃
last_updated: 2026-10-13
---

# 双端自适应基础设施规范

> **适用范围**：PC 端与手机端并存的全部前端开发。
> **定位**：手机端与 PC 端是**同级基础设施**，不是临时兼容层。
> 手机端改动按本规范走，不得当作「顺手适配」。

---

## 一、为什么有这份规范

本项目的界面在 PC 与手机两端都必须可用。2026-10-13 之前，手机端
适配是逐个页面临时补的，导致同一类问题反复出现、且修复不彻底。

**核心教训（本轮实测得出）**：

| 坑 | 表现 | 根因 | 正确解法 |
|----|------|------|----------|
| 空占位容器 | `flex: 2` 的空 div 白占 33% 宽度 | 只看宽度分配，没看容器里有没有内容 | 删掉，别用 `display:none` 补救 |
| 窄屏隐藏关键信息 | 品牌名在 ≤768px 被 `display:none` | 把「信息价值低」当成了隐藏理由 | 缩小 + ellipsis，不隐藏 |
| 中文字竖排 | 文本被压成每行 1 个字 | flex 子项缺 `white-space: nowrap` | 恒为单行，超长省略 |
| ellipsis 不生效 | 配了省略号但仍撑破容器 | flex 子项缺 `min-width: 0` | 见下文「铁律」 |
| 同比例互挤 | 两个 flex 项都缩到看不清 | 只配 `flex-shrink`，没定优先级 | 显式给次要项加 `max-width` 上限 |

---

## 二、基础设施清单

### 2.1 断点与视口

| 断点 | 范围 | 布局形态 |
|------|------|----------|
| 手机 | < 768px | 单列；侧栏为浮层抽屉；顶部两行 |
| 平板 | 768 – 1200px | 单列偏宽；两列卡片 |
| PC | > 1200px | 多列；侧栏常驻可展开 |

- 判定用 `window.matchMedia('(max-width: 768px)')`（`useBreakpoints.js`），
  **不要只听 resize 事件**
- 组件初始化时就要决定折叠态（如 `MultiObjectManagementPage` 的
  `sidebarCollapsed`），不要等 resize 才纠正
- 高度用 `100dvh` 而非 `100vh`（移动浏览器地址栏会吞高度）

### 2.2 安全区与视口

- `index.html` 的 viewport **必须** `width=device-width, initial-scale=1`
- **禁止** `user-scalable=no`（违反 WCAG 1.4.4 Resize Text）
- 需 `viewport-fit=cover` 才能用 `env(safe-area-inset-*)`
- `src/App.vue` 根容器用 `100dvh`

### 2.3 云端隧道（手机访问开发机）

手机访问本地 PC 上的前端，方案只有一条可用：

```powershell
# 生产预览 + 公网隧道
.\scripts\start-mobile.ps1
```

- 实测结论：SSH 类隧道（localhost.run / serveo.net）**传不动** ES module，
  会白屏；**只有 cloudflared quick tunnel 可用**
- 隧道地址**每次重启都变**，且会自行失效。发链接前必须先验证：

```powershell
$r = Invoke-WebRequest -Uri "<隧道地址>" -TimeoutSec 15 -UseBasicParsing
"$($r.StatusCode) $($r.Content.Length)B"
```

- 手机 4G 直连 Cloudflare 边缘常常超时，这是链路问题不是服务问题；
  排查前先用 `curl` 确认 PC 侧返回 200，再让用户换网络
- 隧道指向的是 `vite preview`（默认 4173），出网的是 **`dist` 构建产物**，不是源码：
  发链前比对 `dist/index.html` 与最近改动的 mtime——

```powershell
(Get-Item dist\index.html).LastWriteTime
Get-ChildItem src -Recurse -File | Sort-Object LastWriteTime -Descending | Select-Object -First 3 Name,LastWriteTime
```

  若晚于构建的改动**只是注释/文档**，无需重建；一旦是行为改动，必须重新 `npm run build`，
  否则对方在隧道里看到的仍是旧页面（表现为「改了没生效」）。

### 2.4 品牌名（实例展示名）

展示名由环境变量 `PLATFORM_DISPLAY_NAME` 决定，经
`GET /api/v2/meta/instance` 下发，前端唯一数据源是
`useInstanceInfo().displayName`。

**铁律**：

- [FORBIDDEN] 组件里**禁止**硬编码品牌名做 prop 默认值
- [FORBIDDEN] 禁止出现第二套品牌名机制（如 i18n 里的 `app.title`）
- [FORBIDDEN] 侧边栏 app 菜单名来自 `app.yaml` 的 `name`，**不受**
  `PLATFORM_DISPLAY_NAME` 影响——两者是独立的命名轴，别混谈
- 需要兜底时引用 `useInstanceInfo` 的值，不要自己写一份

验证：`curl http://localhost:3011/api/v2/meta/instance` 看 `display_name`
与 `source`（`env` 表示来自环境变量）。

### 2.5 云端测试规范

`net-check.html` 类诊断页遵循**自举原则**：不依赖框架，纯静态。
白屏的真实原因通常不在 index.html（仅 ~1.4KB），而在数十个 JS chunk
的拉取环节——所以诊断必须覆盖 chunk 体积与加载耗时。

诊断页**禁止**使用 `dns.google` 做 DoH 探测：国内不可达，必然误报为
「域名解析失败」。

---

## 三、CSS 铁律

以下 5 条对应上表 5 个坑，全部来自实测。

```css
/* 铁律 1：flex 子项要能收缩，必须 min-width: 0
   否则 ellipsis 完全失效（flex 子项默认 min-width: auto） */
.flex-child { min-width: 0; }

/* 铁律 2：中文文本恒为单行，否则被压成竖排单字 */
.text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* 铁律 3：关键标识给保底宽度，宁可省略也不能整体消失
   实测踩过：品牌名被压到 5px，width>0 判「可见」是假象 */
.brand-name { min-width: 3.5em; }

/* 铁律 4：次要信息给硬上限，不要指望 flex 自动平衡
   实测踩过：仅配 flex:0 1 auto + min-width:0，两者仍同比例互挤 */
.breadcrumb { flex: 0 1 auto; min-width: 0; max-width: 55%; }

/* 铁律 5：窄屏优先「滚动」或「降级」，不要隐藏、不要竖排 */
@media (max-width: 768px) {
  .nav { overflow-x: auto; }        /* [OK] 横向滚动，如 SubNavTabs */
  .breadcrumb :not(:last-child) { display: none; }  /* [OK] 降级保留末级 */
  /* [FORBIDDEN] .important-title { display: none; } */
}
```

**媒体查询必须写在基础样式之后。** 同优先级下后定义者胜，写在前面会被
基础样式覆盖。这是本项目踩过的坑（工具栏按钮被挤出屏幕）。

---

## 四、验收标准

**不允许「没报错 = 正常」这种判定。** 本项目已两次因此漏掉真实缺陷：

- 分页器 total 取错导致列表少渲染一块，API 全 200、无 JS 报错
- 品牌名宽度 5px 但 `width > 0` 判为「可见」

### 验收必须做的

1. **5 视口断言**：1920 / 1366 / 768 / 414 / 360
2. **最坏数据**：用最长中文标签、多层级，不能用空数据走过场
3. **断言元素符合预期**，不能只断言 `display !== 'none'`：
   - 单行文本 → 断言 `height` ≈ 单行行高（竖排会翻数倍）
   - 关键标识 → 断言 `width >= 40px`（而非 `> 0`）
   - 布局挤压 → 断言相邻元素 `gap` 为**负值**（无重叠）
4. **功能不只验位置**：汉堡按钮要实测 `0 → 240 → 0` 开合
5. **PC 零回归**：断言 PC 端 `headerH`、间距等与改动前一致
6. **全量单测对照基线**：`git stash` 建基线，比对数字是否逐位一致，
   否则既有失败会被算到自己头上

### 注入 DOM 测 scoped 样式的陷阱

用 JS 注入假 DOM 验证 scoped 样式会**假阴性**——编译后选择器带
`[data-v-xxx]`，注入的元素没有该属性，媒体查询测出来像没生效。

解法：先从运行时 CSSOM 抓真实 scope id，再打到注入元素上。

```js
// 先抓真实 scope（不要从别的组件借，那是不同的组件）
for (const ss of document.styleSheets) {
  for (const r of ss.cssRules) {
    if (r.cssText.includes('目标类名')) console.log(r.cssText);
  }
}
```

优先改真实数据源（如临时给 dev 页塞长面包屑）跑真链路；
`devOnly` 路由在生产构建里被禁用，`vite preview` 进不去。

---

## 五、常见任务的目标形态

| 元素 | 手机端目标形态 | 参照 |
|------|----------------|------|
| 表格 | 卡片列表，点标题进详情 | `MetaListPage` |
| 侧栏 | 浮层抽屉 + 遮罩，汉堡在头部左侧 | `AppShell` |
| 详情双栏 | 上主下辅，默认折叠辅栏 | `MultiObjectManagementPage` |
| 面包屑 | 只留末级，前置 `›` | `BreadcrumbNav` |
| 次级页签 | 横向滚动，不换行 | `SubNavTabs` |
| 弹窗 | 底部抽屉，宽度 92vw 兜底 | `AppModal` / `yon-ep.scss` |
| 头部 | `[☰] [图标 品牌名] …… [用户]`，两行 | `TopNavHeader` + `AppShell` |

### 数据展示选型（Ant Design 规范）

| 空间 | 组件 |
|------|------|
| 空间充足、需要扫读与对比 | Table |
| 空间受限、条目少 | List |
| 只需展示、不需交互 | Card list |

- 内容不足一页时**不显示**分页器
- 标题是详情入口（`<button>`），不是纯文本
- 复用页面必须显式声明 `display-mode`（`page` / `embedded` / `dialog`），
  不依赖默认值——`embedded`/`dialog` **不可**卡片化，否则单击高亮、
  双击确认、`tableRef` 全部失效

---

## 六、禁止事项

| 禁止 | 原因 |
|------|------|
| 用 `display:none` 隐藏文字信息 | 信息价值低不等于可隐藏；品牌名、标题、计数是必须可见的 |
| 窄屏把中文文本压成多行 | 竖排单字极难阅读 |
| 空占位容器 | 白占宽度，是「只能靠隐藏」的根因 |
| 在组件里硬编码品牌名 | 部署改名必然漏改 |
| 用 `:nth-child` 定位可省略的 slot 容器 | 容器不渲染时会把后续兄弟错设样式 |
| 媒体查询写在基础样式之前 | 同优先级后写者胜，会被覆盖 |
| 手动改 chunk 分包（`manualChunks`）而不配 E2E 冒烟 | 改变模块初始化顺序，实测导致页面启动崩溃 |

---

## 七、关联规范

| 规范 | 关系 |
|------|------|
| [ui-standards.md](../../core/ui-standards.md) | 视觉与组件封装（双端共用） |
| [file-encoding-rules.md](../../file-encoding-rules.md) | `start-mobile.ps1` 必须带 BOM |
| [../3-local-server-mgmt/project_startup.md](../3-local-server-mgmt/project_startup.md) | 本地服务启动顺序 |
| [../6-test-debug/browser-test-verification.md](../../browser-test-verification.md) | 前端验证方法 |
| [DEPLOYMENT_STANDARDS.md](../../../excel-to-diagram/docs/DEPLOYMENT_STANDARDS.md) §9.2 | 部署级环境变量 |

---

## CHANGELOG

| 日期 | 变更 |
|------|------|
| 2026-10-13 | v1.0 新建。沉淀本轮手机端自适应实战：断点/隧道/品牌名三条基础设施 + CSS 五铁律 + 验收标准（含两处「没报错≠正常」的判错教训） |
