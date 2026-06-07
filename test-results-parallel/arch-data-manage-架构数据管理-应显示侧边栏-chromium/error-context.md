# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: arch-data-manage.spec.js >> 架构数据管理 >> 应显示侧边栏
- Location: e2e\arch-data-manage.spec.js:17:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('.adm-sidebar')
Expected: visible
Timeout: 30000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 30000ms
  - waiting for locator('.adm-sidebar')

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - generic [ref=e5]:
    - generic [ref=e6]:
      - img [ref=e8]
      - heading "BIP应用架构管理" [level=2] [ref=e15]
      - paragraph [ref=e16]: 请登录以继续
    - generic [ref=e17]:
      - generic [ref=e18]:
        - generic [ref=e19]: 用户名
        - textbox "用户名" [ref=e20]:
          - /placeholder: 请输入用户名
      - generic [ref=e21]:
        - generic [ref=e22]: 密码
        - textbox "密码" [ref=e23]:
          - /placeholder: 请输入密码
      - button "登 录" [disabled] [ref=e24]:
        - generic [ref=e25]: 登 录
    - generic [ref=e26]: "默认管理员账号: admin / admin123"
  - generic [ref=e27]:
    - banner [ref=e28]:
      - generic [ref=e30] [cursor=pointer]:
        - img [ref=e31]
        - generic [ref=e38]: BIP应用架构管理
      - generic [ref=e39]:
        - button "AI 智能助手" [ref=e40] [cursor=pointer]:
          - generic:
            - img
        - button "收藏夹" [ref=e41] [cursor=pointer]:
          - generic:
            - img
        - button "最近访问" [ref=e42] [cursor=pointer]:
          - generic:
            - img
        - button [ref=e44] [cursor=pointer]:
          - generic:
            - img
        - button "U 用户" [ref=e47] [cursor=pointer]:
          - generic [ref=e48]: U
          - generic [ref=e49]: 用户
          - img [ref=e51]
    - button [ref=e55] [cursor=pointer]:
      - img [ref=e56]
    - generic [ref=e58]:
      - complementary:
        - navigation [ref=e59]:
          - generic [ref=e60] [cursor=pointer]:
            - generic: 首页
      - main [ref=e62]
```

# Test source

```ts
  1  | /**
  2  |  * 架构数据管理 E2E 测试
  3  |  */
  4  | 
  5  | import { test, expect } from '@playwright/test'
  6  | 
  7  | test.describe('架构数据管理', () => {
  8  |   test('页面应正确加载', async ({ page }) => {
  9  |     await page.goto('/data')
  10 |     await page.waitForLoadState('domcontentloaded')
  11 |     await page.waitForTimeout(3000)
  12 |     
  13 |     const header = page.locator('.app-header')
  14 |     await expect(header).toBeVisible()
  15 |   })
  16 | 
  17 |   test('应显示侧边栏', async ({ page }) => {
  18 |     await page.goto('/data')
  19 |     await page.waitForLoadState('domcontentloaded')
  20 |     await page.waitForTimeout(3000)
  21 |     
  22 |     const sidebar = page.locator('.adm-sidebar')
> 23 |     await expect(sidebar).toBeVisible()
     |                           ^ Error: expect(locator).toBeVisible() failed
  24 |   })
  25 | 
  26 |   test('应显示内容区域', async ({ page }) => {
  27 |     await page.goto('/data')
  28 |     await page.waitForLoadState('domcontentloaded')
  29 |     await page.waitForTimeout(3000)
  30 |     
  31 |     const content = page.locator('.adm-content')
  32 |     await expect(content).toBeVisible()
  33 |   })
  34 | })
  35 | 
```