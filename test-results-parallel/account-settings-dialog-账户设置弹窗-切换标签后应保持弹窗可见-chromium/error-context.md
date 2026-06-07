# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: account-settings-dialog.spec.js >> 账户设置弹窗 >> 切换标签后应保持弹窗可见
- Location: e2e\account-settings-dialog.spec.js:206:3

# Error details

```
TimeoutError: locator.click: Timeout 15000ms exceeded.
Call log:
  - waiting for locator('.user-menu__trigger')
    - locator resolved to <div tabindex="0" role="button" id="el-id-6847-0" data-v-8289ce8d="" aria-haspopup="menu" aria-expanded="false" aria-controls="el-id-6847-1" class="user-menu__trigger el-tooltip__trigger el-tooltip__trigger">…</div>
  - attempting click action
    2 × waiting for element to be visible, enabled and stable
      - element is visible, enabled and stable
      - scrolling into view if needed
      - done scrolling
      - <div data-v-1aea22a9="" class="login-overlay">…</div> intercepts pointer events
    - retrying click action
    - waiting 20ms
    2 × waiting for element to be visible, enabled and stable
      - element is visible, enabled and stable
      - scrolling into view if needed
      - done scrolling
      - <div data-v-1aea22a9="" class="login-overlay">…</div> intercepts pointer events
    - retrying click action
      - waiting 100ms
    27 × waiting for element to be visible, enabled and stable
       - element is visible, enabled and stable
       - scrolling into view if needed
       - done scrolling
       - <div data-v-1aea22a9="" class="login-overlay">…</div> intercepts pointer events
     - retrying click action
       - waiting 500ms

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
          - text: admin
      - generic [ref=e21]:
        - generic [ref=e22]: 密码
        - textbox "密码" [ref=e23]:
          - /placeholder: 请输入密码
          - text: admin123
      - generic [ref=e24]: IP已被封禁，请4分钟后重试
      - button "登 录" [ref=e25] [cursor=pointer]:
        - generic [ref=e26]: 登 录
    - generic [ref=e27]: "默认管理员账号: admin / admin123"
  - generic [ref=e28]:
    - banner [ref=e29]:
      - generic [ref=e31] [cursor=pointer]:
        - img [ref=e32]
        - generic [ref=e39]: BIP应用架构管理
      - generic [ref=e40]:
        - button "AI 智能助手" [ref=e41] [cursor=pointer]:
          - generic:
            - img
        - button "收藏夹" [ref=e42] [cursor=pointer]:
          - generic:
            - img
        - button "最近访问" [ref=e43] [cursor=pointer]:
          - generic:
            - img
        - button [ref=e45] [cursor=pointer]:
          - generic:
            - img
        - button "U 用户" [ref=e48] [cursor=pointer]:
          - generic [ref=e49]: U
          - generic [ref=e50]: 用户
          - img [ref=e52]
    - button [ref=e56] [cursor=pointer]:
      - img [ref=e57]
    - generic [ref=e59]:
      - complementary:
        - navigation [ref=e60]:
          - generic [ref=e61] [cursor=pointer]:
            - generic: 首页
      - main [ref=e63]:
        - generic [ref=e64]:
          - main [ref=e65]:
            - generic [ref=e66]:
              - heading "快捷应用" [level=2] [ref=e68]
              - generic [ref=e70] [cursor=pointer]:
                - img [ref=e72]
                - generic [ref=e75]: 首页
            - generic [ref=e77]:
              - generic [ref=e78]:
                - generic [ref=e79]: 常用产品版本
                - generic [ref=e80]: 点击快速进入架构数据管理
              - generic [ref=e81]: 暂无常用产品版本，请先访问架构数据管理
            - generic [ref=e83]:
              - heading "统计概览" [level=3] [ref=e84]
              - generic [ref=e85]:
                - generic [ref=e86]: 平台全貌
                - generic [ref=e87]:
                  - generic [ref=e88]:
                    - img [ref=e90]
                    - generic [ref=e93]:
                      - generic [ref=e94]: "5"
                      - generic [ref=e95]: 产品
                    - generic [ref=e96]: "+2"
                  - generic [ref=e97]:
                    - img [ref=e99]
                    - generic [ref=e103]:
                      - generic [ref=e104]: "11"
                      - generic [ref=e105]: 版本
                    - generic [ref=e106]: "+7"
                  - generic [ref=e107]:
                    - img [ref=e109]
                    - generic [ref=e112]:
                      - generic [ref=e113]: "116"
                      - generic [ref=e114]: 领域
                    - generic [ref=e115]: "+97"
                  - generic [ref=e116]:
                    - img [ref=e118]
                    - generic [ref=e120]:
                      - generic [ref=e121]: "14298"
                      - generic [ref=e122]: 业务对象
                    - generic [ref=e123]: "+12249"
                  - generic [ref=e124]:
                    - img [ref=e126]
                    - generic [ref=e132]:
                      - generic [ref=e133]: "19306"
                      - generic [ref=e134]: 关系
                    - generic [ref=e135]: "+16550"
          - paragraph [ref=e137]: © 2026 BIP应用架构管理
```

# Test source

```ts
  1   | /**
  2   |  * 账户设置弹窗 E2E 测试
  3   |  *
  4   |  * 完整测试弹窗的打开、编辑、保存、密码修改、标签切换等流程
  5   |  */
  6   | 
  7   | import { test, expect } from '@playwright/test'
  8   | 
  9   | async function login(page) {
  10  |   await page.goto('/', { waitUntil: 'networkidle', timeout: 15000 })
  11  |   await page.waitForTimeout(2000)
  12  | 
  13  |   const usernameInput = page.locator('input[type="text"]')
  14  |   if (await usernameInput.count() > 0) {
  15  |     await usernameInput.fill('admin')
  16  |     await page.locator('input[type="password"]').first().fill('admin123')
  17  |     const loginBtn = page.locator('form button, button[type="submit"]').first()
  18  |     if (await loginBtn.count() > 0) {
  19  |       await loginBtn.click()
  20  |       await page.waitForTimeout(3000)
  21  |     }
  22  |   }
  23  | }
  24  | 
  25  | async function openAccountDialog(page) {
> 26  |   await page.locator('.user-menu__trigger').click()
      |                                             ^ TimeoutError: locator.click: Timeout 15000ms exceeded.
  27  |   await page.waitForTimeout(500)
  28  | 
  29  |   const accountItem = page.locator('.el-dropdown-menu__item:has-text("账户设置")')
  30  |   if (await accountItem.count() > 0) {
  31  |     await accountItem.click()
  32  |     await page.waitForTimeout(1500)
  33  |   } else {
  34  |     const fallback = page.locator('.el-dropdown-menu__item:has-text("个人资料"), .el-dropdown-menu__item:has-text("设置")').first()
  35  |     if (await fallback.count() > 0) await fallback.click()
  36  |     await page.waitForTimeout(1500)
  37  |   }
  38  | }
  39  | 
  40  | test.describe('账户设置弹窗', () => {
  41  | 
  42  |   test.beforeEach(async ({ page }) => {
  43  |     await login(page)
  44  |   })
  45  | 
  46  |   test('应能从用户菜单打开弹窗', async ({ page }) => {
  47  |     await openAccountDialog(page)
  48  | 
  49  |     const modal = page.locator('.app-modal')
  50  |     await expect(modal).toBeVisible()
  51  | 
  52  |     const title = page.locator('.app-modal__title, .modal-title, .app-modal-header')
  53  |     if (await title.count() > 0) {
  54  |       await expect(title.first()).toContainText('账户设置')
  55  |     }
  56  | 
  57  |     await page.screenshot({ path: 'e2e-results/dialog-open.png' })
  58  |   })
  59  | 
  60  |   test('默认显示个人信息标签页', async ({ page }) => {
  61  |     await openAccountDialog(page)
  62  | 
  63  |     const profileTab = page.locator('.dialog-tab.active:has-text("个人信息")')
  64  |     if (await profileTab.count() > 0) {
  65  |       await expect(profileTab).toBeVisible()
  66  |     }
  67  | 
  68  |     const profileView = page.locator('.profile-view')
  69  |     if (await profileView.count() > 0) {
  70  |       await expect(profileView).toBeVisible()
  71  |     }
  72  |   })
  73  | 
  74  |   test('个人信息标签页应显示用户头像和用户名', async ({ page }) => {
  75  |     await openAccountDialog(page)
  76  | 
  77  |     const avatar = page.locator('.profile-avatar')
  78  |     if (await avatar.count() > 0) {
  79  |       await expect(avatar).toBeVisible()
  80  |       const avatarText = await avatar.textContent()
  81  |       expect(avatarText.trim().length).toBeGreaterThan(0)
  82  |     }
  83  | 
  84  |     const username = page.locator('.pf-value').first()
  85  |     if (await username.count() > 0) {
  86  |       const text = await username.textContent()
  87  |       expect(text.trim().length).toBeGreaterThan(0)
  88  |     }
  89  |   })
  90  | 
  91  |   test('个人信息标签页应有编辑按钮', async ({ page }) => {
  92  |     await openAccountDialog(page)
  93  | 
  94  |     const editBtn = page.locator('.btn-primary:has-text("编辑资料")')
  95  |     if (await editBtn.count() > 0) {
  96  |       await expect(editBtn).toBeVisible()
  97  |     }
  98  |   })
  99  | 
  100 |   test('点击编辑按钮应切换到编辑模式', async ({ page }) => {
  101 |     await openAccountDialog(page)
  102 | 
  103 |     const editBtn = page.locator('.btn-primary:has-text("编辑资料")')
  104 |     if (await editBtn.count() > 0) {
  105 |       await editBtn.click()
  106 |       await page.waitForTimeout(500)
  107 | 
  108 |       const editView = page.locator('.profile-edit')
  109 |       if (await editView.count() > 0) {
  110 |         await expect(editView).toBeVisible()
  111 |       }
  112 | 
  113 |       const displayNameInput = page.locator('.form-group input[placeholder*="显示名称"], .form-group input[placeholder*="display"]')
  114 |       if (await displayNameInput.count() > 0) {
  115 |         await expect(displayNameInput).toBeVisible()
  116 |       }
  117 | 
  118 |       await page.screenshot({ path: 'e2e-results/dialog-edit-mode.png' })
  119 |     }
  120 |   })
  121 | 
  122 |   test('编辑模式下点击取消应返回查看模式', async ({ page }) => {
  123 |     await openAccountDialog(page)
  124 | 
  125 |     const editBtn = page.locator('.btn-primary:has-text("编辑资料")')
  126 |     if (await editBtn.count() > 0) {
```