# Playwright 测试调试与图标设计优化

## 会话概述

本次会话主要涉及两个技术任务：

1. **ArchWorkspace Logo 图标优化** - 将 AA图应用的图标与 ArchWorkspace Logo 风格统一
2. **Playwright 自动化测试修复** - 解决测试失败问题，实现截图和视频录制功能

---

## 一、图标设计优化

### 1.1 问题背景

用户注意到 AA图应用卡片中的图标与 ArchWorkspace Logo 不够匹配，希望进行优化统一。

### 1.2 技术实现

**文件位置**：`src/components/common/AppIcon/AppIcon.vue`

**初始状态**：diagram 图标是三个方块加简单连接线的架构图风格

**最终方案**：保持架构图风格，调整为：
- 上方两个并排方块（代表模块/组件）
- 下方一个居中的大方块（代表核心/汇总）
- 两条连接线从上方方块延伸到下方方块

**SVG 代码**：

```svg
<template v-else-if="name === 'diagram'">
  <rect x="2" y="2" width="5" height="4" rx="1" stroke="currentColor" stroke-width="1.5"/>
  <rect x="9" y="2" width="5" height="4" rx="1" stroke="currentColor" stroke-width="1.5"/>
  <rect x="5" y="9" width="6" height="5" rx="1" stroke="currentColor" stroke-width="1.5"/>
  <path d="M4.5 6V7.5C4.5 7.78 4.72 8 5 8H7.5V9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M11.5 6V7.5C11.5 7.78 11.28 8 11 8H8.5V9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
</template>
```

---

## 二、Playwright 自动化测试修复

### 2.1 问题分析

#### 问题描述

用户反映在 http://localhost:9323/ 查看测试结果时，发现大部分测试都失败了，特别是第一步点击操作都没有发生。

#### 根本原因

**测试预期的页面与实际不符**

查看 `App.vue` 第 53 行：
```javascript
currentApp: 'landing'  // 默认显示 ArchWorkspace，不是 ArchDataManageApp
```

当访问 `http://localhost:3005/` 时：
- **实际显示**：ArchWorkspace 主页（有"欢迎使用"和三个应用卡片）
- **测试期望**：ArchDataManageApp 页面（有 `.adm-title` 包含"架构数据管理"）

由于找不到 `.adm-title`，测试在第一步就失败了，所以根本没有机会执行后续的点击操作。

### 2.2 解决方案

#### 修改文件

**文件位置**：`e2e/arch-data-manage.spec.js`

#### 修改内容

**修改前**：
```javascript
test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await page.waitForLoadState('domcontentloaded')
})
```

**修改后**：
```javascript
test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await page.waitForLoadState('domcontentloaded')
  
  // 先点击"架构数据管理"卡片进入应用
  const archDataManageCard = page.locator('.app-card--tertiary')
  await archDataManageCard.click({ timeout: 15000 })
  await page.waitForTimeout(1000)
})
```

#### 修复范围

共修复了三个测试模块的 `beforeEach`：
1. `ArchDataManageApp E2E Tests`
2. `DynamicView Operations`
3. `Hierarchy Validation E2E`

### 2.3 测试执行与验证

#### 首次运行结果

```
Running 13 tests using 1 worker
  ✓ 13 passed (33.0s)
```

**结论**：修复方案完全正确！所有测试通过。

#### 测试报告

报告文件位置：`playwright-report/index.html`

访问地址：http://localhost:9323/

### 2.4 截图和视频配置

#### 初始配置问题

`playwright.config.js` 中的配置：
```javascript
screenshot: 'only-on-failure',  // 只在失败时截图
video: 'retain-on-failure',     // 只在失败时保留视频
```

由于所有测试都通过了，所以没有生成截图。

#### 优化配置

修改为：
```javascript
screenshot: 'on',  // 每次测试都截图
video: 'on',       // 每次测试都录制视频
```

#### 重新运行结果

```
Running 13 tests using 1 worker
  13 passed (1.8m)
```

#### 生成的文件

**位置**：`test-results/`

每个测试文件夹包含：
- `test-finished-1.png` - 测试成功完成时的截图
- `test-failed-1.png` - 测试失败时的截图
- `video.webm` - 测试执行过程视频
- `error-context.md` - 错误日志

### 2.5 测试失败原因分析

#### 主要失败原因

**开发服务器连接失败**：
```
Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:3005/
```

#### 原因分析

1. **webServer 启动失败** - Playwright 配置了 `webServer` 会在测试前自动启动开发服务器，但如果启动失败或超时，所有测试都会立即失败

2. **端口未被监听** - 通过 `netstat` 检查，没有进程在监听 3005 端口，说明 Vite 开发服务器根本没有运行

3. **首次测试成功的原因** - 当第一次运行 `npm run test:e2e` 时，webServer 成功启动了服务器，所以测试通过。后来配置改为 `screenshot: 'on'` 后再次运行时，可能 webServer 没有正确启动

#### 解决方案

手动启动开发服务器：
```bash
npm run dev -- --port 3005
```

验证服务器状态：
```bash
netstat -ano | findstr :3005
```

输出结果：
```
TCP    [::1]:3005    [::]:0    LISTENING    31636
```

服务器成功运行。

---

## 三、Playwright 配置详解

### 3.1 配置文件

**文件位置**：`playwright.config.js`

```javascript
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',              // 测试文件目录
  fullyParallel: false,          // 禁用并行执行
  forbidOnly: !!process.env.CI,  // CI 环境禁止 only 测试
  retries: process.env.CI ? 2 : 0,  // CI 环境重试 2 次
  workers: 1,                   // 单线程执行
  reporter: 'html',             // HTML 报告
  timeout: 60000,               // 测试超时 60 秒
  expect: {
    timeout: 30000              // 断言超时 30 秒
  },
  use: {
    baseURL: 'http://localhost:3005',  // 基础 URL
    trace: 'on-first-retry',    // 首次重试时保存追踪
    screenshot: 'on',            // 每次测试都截图
    video: 'on',                // 每次测试都录制视频
    actionTimeout: 15000        // 操作超时 15 秒
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    }
  ],
  webServer: {
    command: 'npm run dev -- --port 3005',
    url: 'http://localhost:3005',
    reuseExistingServer: true,
    timeout: 120 * 1000
  }
})
```

### 3.2 测试文件结构

**文件位置**：`e2e/arch-data-manage.spec.js`

**测试模块**：
1. `ArchDataManageApp E2E Tests` - 7 个测试
2. `DynamicView Operations` - 3 个测试
3. `Hierarchy Validation E2E` - 1 个测试

---

## 四、技术要点总结

### 4.1 Vue 3 应用测试策略

1. **了解应用路由逻辑** - 测试前必须清楚应用的默认显示页面
2. **模拟用户操作** - 如果测试子页面，需要先通过导航进入
3. **使用精确选择器** - `.app-card--tertiary` 比 `:has-text()` 更稳定

### 4.2 Playwright 最佳实践

1. **使用 beforeEach** - 为所有测试设置统一的初始化步骤
2. **合理设置超时** - 根据实际场景调整 timeout 值
3. **配置截图和视频** - 方便调试和文档记录
4. **确保开发服务器运行** - 测试前检查端口监听状态

### 4.3 问题排查流程

1. 检查测试日志中的具体错误
2. 确认开发服务器是否正常运行
3. 使用 netstat 检查端口占用
4. 查看 Playwright 生成的截图和视频
5. 使用 `playwright show-report` 查看详细报告

---

## 五、相关文件列表

### 5.1 修改的文件

| 文件路径 | 修改内容 |
|---------|---------|
| `src/components/common/AppIcon/AppIcon.vue` | 更新 diagram 图标设计 |
| `e2e/arch-data-manage.spec.js` | 修复测试的导航逻辑 |
| `playwright.config.js` | 优化截图和视频配置 |

### 5.2 测试结果文件

| 文件路径 | 说明 |
|---------|------|
| `playwright-report/index.html` | 测试报告 |
| `test-results/*/test-finished-1.png` | 测试截图 |
| `test-results/*/video.webm` | 测试视频 |

---

## 六、后续建议

1. **持续监控测试状态** - 建议配置 CI/CD 自动运行测试
2. **优化测试性能** - 考虑启用并行执行以加快测试速度
3. **补充测试用例** - 增加边界情况和错误处理测试
4. **维护截图库** - 定期更新测试截图作为 UI 回归测试基准

---

## 附录：常用命令

```bash
# 运行所有测试
npm run test:e2e

# 使用 UI 模式运行测试
npm run test:e2e:ui

# 查看测试报告
npx playwright show-report

# 手动启动开发服务器
npm run dev -- --port 3005

# 检查端口占用
netstat -ano | findstr :3005
```

---

**会话时间**：2026-04-17  
**项目路径**：d:\filework\excel-to-diagram  
**状态**：已完成
