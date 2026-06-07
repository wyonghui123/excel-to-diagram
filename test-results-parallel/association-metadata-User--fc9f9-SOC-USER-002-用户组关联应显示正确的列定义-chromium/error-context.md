# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: association-metadata.spec.js >> User Associations - 用户关联测试 >> TC-ASSOC-USER-002: 用户组关联应显示正确的列定义
- Location: e2e\association-metadata.spec.js:98:3

# Error details

```
TimeoutError: page.waitForSelector: Timeout 15000ms exceeded.
Call log:
  - waiting for locator('.el-table__body tr') to be visible

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
  1   | /**
  2   |  * Association 元数据驱动 E2E 测试
  3   |  * 
  4   |  * 测试用户、用户组、角色之间的关联操作
  5   |  * 验证:
  6   |  * 1. YAML 定义的 display.columns 正确渲染
  7   |  * 2. confirm_message 正确显示
  8   |  * 3. getAssociationConfig 从 uiConfig.associations 获取配置
  9   |  */
  10  | 
  11  | import { test, expect } from '@playwright/test'
  12  | 
  13  | const BASE_URL = process.env.VITE_API_BASE || 'http://localhost:3004'
  14  | 
  15  | async function login(page) {
  16  |   await page.goto(`${BASE_URL}/`)
  17  |   await page.waitForLoadState('networkidle')
  18  |   await page.waitForTimeout(2000)
  19  | 
  20  |   const usernameInput = page.locator('input[placeholder*="用户名"], input[type="text"]').first()
  21  |   const passwordInput = page.locator('input[type="password"]')
  22  | 
  23  |   if (await usernameInput.isVisible()) {
  24  |     await usernameInput.fill('admin')
  25  |     await passwordInput.fill('admin123')
  26  |     const loginBtn = page.locator('button[type="submit"], button:has-text("登 录")')
  27  |     if (await loginBtn.isVisible()) {
  28  |       await loginBtn.click()
  29  |       await page.waitForTimeout(3000)
  30  |     }
  31  |   }
  32  | }
  33  | 
  34  | test.describe('User Associations - 用户关联测试', () => {
  35  |   test.beforeEach(async ({ page }) => {
  36  |     await login(page)
  37  |     // 导航到用户详情页面
  38  |     await page.goto(`${BASE_URL}/user-permission`)
  39  |     await page.waitForLoadState('networkidle')
  40  |     await page.waitForTimeout(3000)
  41  |   })
  42  | 
  43  |   test('TC-ASSOC-USER-001: 用户详情页应显示"所属用户组"关联面板', async ({ page }) => {
  44  |     // 等待用户列表加载
  45  |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  46  |     await page.waitForTimeout(2000)
  47  | 
  48  |     // 点击第一行打开详情
  49  |     const firstRow = page.locator('.el-table__body tr').first()
  50  |     await firstRow.click()
  51  |     await page.waitForTimeout(2000)
  52  | 
  53  |     // 查找详情抽屉
  54  |     const drawer = page.locator('.el-drawer').first()
  55  |     if (await drawer.isVisible()) {
  56  |       // 查找 "所属用户组" 标签或内容
  57  |       const groupTab = drawer.locator('.el-tabs__item:has-text("所属用户组"), .anchor-tab:has-text("所属用户组")')
  58  |       
  59  |       if (await groupTab.count() > 0) {
  60  |         await expect(groupTab.first()).toBeVisible()
  61  |         console.log('✅ 用户详情页显示"所属用户组"标签')
  62  |         
  63  |         // 点击标签查看关联面板
  64  |         await groupTab.first().click()
  65  |         await page.waitForTimeout(1000)
  66  | 
  67  |         // 验证 AssociationPanel 组件
  68  |         const assocPanel = drawer.locator('.association-panel')
  69  |         if (await assocPanel.count() > 0) {
  70  |           console.log('✅ AssociationPanel 组件已渲染')
  71  | 
  72  |           // 验证标题使用 YAML 配置的 label
  73  |           const panelTitle = assocPanel.locator('.ap-header__title')
  74  |           if (await panelTitle.count() > 0) {
  75  |             const titleText = await panelTitle.textContent()
  76  |             console.log(`关联面板标题: "${titleText}"`)
  77  |             expect(titleText).toContain('用户组')
  78  |           }
  79  | 
  80  |           // 验证表格列使用 YAML 配置的 columns
  81  |           const tableHeaders = assocPanel.locator('.ap-table .el-table__header th')
  82  |           const headerCount = await tableHeaders.count()
  83  |           console.log(`表格列数: ${headerCount}`)
  84  |           
  85  |           // user.yaml 定义了 code, name, description 三列
  86  |           if (headerCount >= 3) {
  87  |             console.log('✅ 表格列数符合 YAML 配置 (>=3)')
  88  |           }
  89  |         }
  90  |       } else {
  91  |         console.log('⚠️ 未找到"所属用户组"标签，可能页面结构不同')
  92  |       }
  93  |     } else {
  94  |       console.log('⚠️ 详情抽屉未打开')
  95  |     }
  96  |   })
  97  | 
  98  |   test('TC-ASSOC-USER-002: 用户组关联应显示正确的列定义', async ({ page }) => {
> 99  |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
      |                ^ TimeoutError: page.waitForSelector: Timeout 15000ms exceeded.
  100 |     await page.waitForTimeout(2000)
  101 | 
  102 |     // 打开第一个用户的详情
  103 |     const detailBtn = page.locator('.el-table__body .el-button:has-text("详情")').first()
  104 |     if (await detailBtn.isVisible()) {
  105 |       await detailBtn.click()
  106 |       await page.waitForTimeout(2000)
  107 |     } else {
  108 |       await page.locator('.el-table__body tr').first().click()
  109 |       await page.waitForTimeout(2000)
  110 |     }
  111 | 
  112 |     const drawer = page.locator('.el-drawer').first()
  113 |     if (await drawer.isVisible()) {
  114 |       // 切换到用户组标签
  115 |       const groupTab = drawer.locator('.el-tabs__item:has-text("用户组"), .anchor-tab:has-text("用户组")')
  116 |       if (await groupTab.count() > 0) {
  117 |         await groupTab.first().click()
  118 |         await page.waitForTimeout(1000)
  119 | 
  120 |         // 验证列头
  121 |         const assocPanel = drawer.locator('.association-panel')
  122 |         if (await assocPanel.count() > 0) {
  123 |           // 检查 YAML 中定义的列: code(组编码), name(组名称), description(描述)
  124 |           const headers = assocPanel.locator('.ap-table th')
  125 |           const headerTexts = []
  126 |           
  127 |           for (let i = 0; i < await headers.count(); i++) {
  128 |             const text = await headers.nth(i).textContent()
  129 |             headerTexts.push(text?.trim())
  130 |           }
  131 |           
  132 |           console.log(`检测到的列: ${headerTexts.join(', ')}`)
  133 |           
  134 |           // 验证关键列存在
  135 |           const hasCodeColumn = headerTexts.some(h => h.includes('编码'))
  136 |           const hasNameColumn = headerTexts.some(h => h.includes('名称') || h.includes('组'))
  137 |           
  138 |           console.log(`包含编码列: ${hasCodeColumn}, 包含名称列: ${hasNameColumn}`)
  139 |         }
  140 |       }
  141 |     }
  142 |   })
  143 | 
  144 |   test('TC-ASSOC-USER-003: 移除用户组时应显示自定义确认消息', async ({ page }) => {
  145 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  146 |     await page.waitForTimeout(2000)
  147 | 
  148 |     // 打开用户详情
  149 |     const firstRow = page.locator('.el-table__body tr').first()
  150 |     await firstRow.click()
  151 |     await page.waitForTimeout(2000)
  152 | 
  153 |     const drawer = page.locator('.el-drawer').first()
  154 |     if (await drawer.isVisible()) {
  155 |       // 切换到用户组标签
  156 |       const groupTab = drawer.locator('.el-tabs__item:has-text("用户组"), .anchor-tab:has-text("用户组")')
  157 |       if (await groupTab.count() > 0) {
  158 |         await groupTab.first().click()
  159 |         await page.waitForTimeout(1000)
  160 | 
  161 |         // 查找移除按钮
  162 |         const removeBtn = drawer.locator('.association-panel button:has-text("移除")').first()
  163 |         if (await removeBtn.isVisible()) {
  164 |           // 设置对话框监听器来捕获确认消息
  165 |           page.on('dialog', async dialog => {
  166 |             const message = dialog.message()
  167 |             console.log(`确认对话框消息: "${message}"`)
  168 |             
  169 |             // 验证是否使用了 YAML 配置的 confirm_message
  170 |             expect(message).toContain('移除')
  171 |             
  172 |             await dialog.dismiss()
  173 |           })
  174 | 
  175 |           await removeBtn.click()
  176 |           await page.waitForTimeout(500)
  177 |           
  178 |           console.log('✅ 移除按钮点击成功，确认对话框触发')
  179 |         } else {
  180 |           console.log('⚠️ 无数据时移除按钮不可见（正常行为）')
  181 |         }
  182 |       }
  183 |     }
  184 |   })
  185 | })
  186 | 
  187 | test.describe('UserGroup Associations - 用户组关联测试', () => {
  188 |   test.beforeEach(async ({ page }) => {
  189 |     await login(page)
  190 |     // 导航到用户组管理
  191 |     await page.goto(`${BASE_URL}/user-group-management`)
  192 |     await page.waitForLoadState('networkidle')
  193 |     await page.waitForTimeout(3000)
  194 |   })
  195 | 
  196 |   test('TC-ASSOC-GROUP-001: 用户组详情应显示"成员"和"角色"关联面板', async ({ page }) => {
  197 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  198 |     await page.waitForTimeout(2000)
  199 | 
```