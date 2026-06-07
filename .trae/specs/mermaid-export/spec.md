# Mermaid 图表导出功能 Spec

## Why
用户生成图表后，需要将 Mermaid 代码导出以便：
1. 在其他工具中使用（如 Mermaid Live Editor、VS Code 插件）
2. 离线查看（导出为 HTML 直接用浏览器打开）
3. 分享给他人

## What Changes

### 导出功能概述

| 版本 | 类型 | 加载方式 | ELK支持 | 缩放/拖拽 | 特点 |
|------|------|----------|---------|------------|------|
| **简洁版** | 离线 | 内嵌 mermaid.min.js (UMD) | ❌ 不支持 | ✅ 支持滚轮缩放 | 可双击直接打开 |
| **彩色版** | 在线 | CDN 加载 mermaid v11 + ELK | ✅ 支持 | ✅ 支持滚轮缩放+拖拽 | 需要网络连接 |

### 按钮位置

在 `MermaidComponent.vue` 的工具栏（第3-18行）中添加导出按钮：

```html
<div class="toolbar">
  <button class="toolbar-btn" @click="resetAdaptive" title="重置视图">...</button>
  <button class="toolbar-btn" @click="toggleMaximize" title="全屏查看">...</button>
  <span class="toolbar-divider"></span>
  <button class="toolbar-btn" @click="copyToClipboard" title="复制代码">
    <AppIcon name="copy" size="sm" />
  </button>
  <button class="toolbar-btn" @click="exportAsHtmlFull" title="导出 HTML（彩色版 - 可直接双击打开）">
    <AppIcon name="export" size="sm" />
    <span style="font-size: 10px; margin-left: 2px;">彩</span>
  </button>
</div>
```

### 简洁版 HTML 结构

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{图表类型} - {日期}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #ffffff;
      height: auto;
      min-height: 100vh;
    }
    body {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      padding: 10px;
    }
    pre.mermaid {
      display: block;
      background: white;
      width: 100%;
      margin: 0;
      padding: 0;
      border: none;
      overflow: visible;
      line-height: 0;
    }
    pre.mermaid svg {
      display: block;
      cursor: grab;
      transform-origin: top left;
      transition: transform 0.1s ease-out;
      max-width: none;
    }
  </style>
</head>
<body>
  <pre class="mermaid">
{mermaid代码}
  </pre>
  <script>
    // 内嵌 mermaid.min.js Base64 编码
    const mermaidBase64 = "...";
    const mermaidCode = decodeURIComponent(escape(atob(mermaidBase64)));
    const mermaidBlob = new Blob([mermaidCode], { type: 'text/javascript' });
    const mermaidUrl = URL.createObjectURL(mermaidBlob);
    const script = document.createElement('script');
    script.src = mermaidUrl;
    script.onload = () => {
      mermaid.initialize({...});
      mermaid.run({ querySelector: '.mermaid' }).then(() => {
        // 滚轮缩放
        // 容器颜色处理
      });
    };
    document.head.appendChild(script);
  </script>
</body>
</html>
```

### 彩色版 HTML 结构

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{图表类型} - {日期}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #ffffff;
      height: auto;
      min-height: 100vh;
    }
    body {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      padding: 10px;
    }
    .notice {
      background: #fff3cd;
      border: 1px solid #ffc107;
      color: #856404;
      padding: 12px 20px;
      border-radius: 8px;
      margin-bottom: 10px;
      font-size: 13px;
      width: 100%;
    }
    pre.mermaid { ... }
    pre.mermaid svg { ... }
  </style>
</head>
<body>
  <div class="notice">
    ⚠️ 此文件需要从 CDN 加载资源，请保持网络连接。
  </div>
  <pre class="mermaid">
{mermaid代码}
  </pre>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';

    // ELK 加载（如果启用）
    let initPromise = Promise.resolve();
    if ('{isElk}') {
      initPromise = import('https://cdn.jsdelivr.net/npm/@mermaid-js/layout-elk@0.1.4/dist/mermaid-layout-elk.esm.min.mjs')
        .then(elkLayouts => {
          mermaid.registerLayoutLoaders(elkLayouts.default);
        });
    }

    // 滚轮缩放 + 拖拽移动
    let scale = 1, translateX = 0, translateY = 0;
    document.addEventListener('wheel', (e) => { ... });
    document.addEventListener('mousedown', (e) => { ... });
    document.addEventListener('mousemove', (e) => { ... });
    document.addEventListener('mouseup', () => { ... });

    initPromise.then(() => {
      mermaid.initialize({...});
      mermaid.run({ querySelector: '.mermaid' }).then(() => {
        // viewBox 修复
        // 容器颜色处理
      });
    });
  </script>
</body>
</html>
```

## Impact

### 影响文件
- `src/components/MermaidComponent.vue` - 新增 `exportAsHtmlFull`、`exportAsHtmlSimple` 方法
- 新增依赖：无

## ADDED Requirements

### Requirement: 简洁版 HTML 导出
系统 SHALL 提供将当前 Mermaid 图表导出为简洁版 HTML 文件的功能（离线可用）

#### Scenario: 用户导出简洁版 HTML
- **WHEN** 用户点击工具栏的"简洁版"导出按钮
- **THEN** 系统生成包含内嵌 mermaid.min.js 的 HTML 文件
- **AND** 文件名为 `diagram-simple-{timestamp}.html`
- **AND** 支持滚轮缩放
- **NOTE** 不支持 ELK 布局（ELK ESM 版本有 chunk 依赖问题）

### Requirement: 彩色版 HTML 导出
系统 SHALL 提供将当前 Mermaid 图表导出为彩色版 HTML 文件的功能（支持 ELK）

#### Scenario: 用户导出彩色版 HTML
- **WHEN** 用户点击工具栏的"彩色版"导出按钮
- **THEN** 系统生成从 CDN 加载 mermaid v11 和 ELK 的 HTML 文件
- **AND** 文件名为 `diagram-full-{timestamp}.html`
- **AND** 支持滚轮缩放和拖拽移动
- **AND** 支持 ELK 布局
- **AND** 需要网络连接

### Requirement: 滚轮缩放功能
导出的 HTML 文件 SHALL 支持滚轮缩放

#### Scenario: 用户滚轮缩放
- **WHEN** 用户在图表区域滚动鼠标滚轮
- **THEN** 图表以鼠标位置为中心进行缩放
- **AND** 缩放范围为 0.1x - 3x

### Requirement: 拖拽移动功能（仅彩色版）
彩色版导出的 HTML 文件 SHALL 支持拖拽移动

#### Scenario: 用户拖拽移动图表
- **WHEN** 用户在图表区域按住鼠标拖拽
- **THEN** 图表跟随鼠标移动

### Requirement: 容器颜色区分
导出的 HTML 文件 SHALL 对嵌套容器使用渐进颜色区分

#### Scenario: 容器颜色分配
- **GIVEN** 存在多个嵌套层级的容器
- **WHEN** 图表渲染完成
- **THEN** 外层容器使用浅色，内层容器使用深色
- **AND** 颜色数组：`['#ffffff', '#e0e0e0', '#c0c0c0', '#a0a0a0']`

### Requirement: 复制到剪贴板功能
系统 SHALL 提供将 Mermaid 代码复制到系统剪贴板的功能

#### Scenario: 用户复制代码
- **WHEN** 用户点击工具栏的"复制代码"按钮
- **THEN** 当前 Mermaid 代码被复制到剪贴板
- **AND** 显示"已复制"Toast 提示

## Technical Notes

### 为什么简洁版不支持 ELK？
- ELK 只有 ESM 版本，且依赖外部 chunk 文件（`chunk-SP2CHFBE.mjs` 等）
- `file://` 协议禁止 dynamic import()
- Base64 内嵌方案无法解决 chunk 依赖问题
- 解决方案：简洁版使用 dagre 布局，彩色版使用 CDN 加载支持 ELK

### 为什么彩色版使用 mermaid v11？
- mermaid v10 的 ESM 版本是代理入口，依赖外部 chunk
- mermaid v10 没有 `registerLayoutLoaders` API
- mermaid v11 ESM 版本导出了 `registerLayoutLoaders` 方法
- `registerLayoutLoaders` 是 v11 才引入的 API

### CSS 选择器注意
- HTML 结构是 `<pre class="mermaid">` 不是 `<div class="mermaid"><pre>`
- CSS 选择器应使用 `pre.mermaid` 而不是 `.mermaid pre`

### 待解决问题
- ⚠️ 彩色版容器背景色问题：图表上是浅灰色，但彩色full HTML上显示白色
  - 原因：可能是 `getNestingLevel` 函数无法正确识别嵌套关系
  - 优先级：高
