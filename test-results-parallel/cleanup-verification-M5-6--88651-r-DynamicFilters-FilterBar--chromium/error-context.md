# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: cleanup-verification.spec.js >> M5   >> 6. FilterBar   (DynamicFilters ) >> FilterBar    
- Location: e2e\cleanup-verification.spec.js:214:5

# Error details

```
TimeoutError: page.waitForSelector: Timeout 15000ms exceeded.
Call log:
  - waiting for locator('.meta-list-page, .el-table') to be visible

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
  119 | 
  120 |   test.describe('4. AccountSettings    ', () => {
  121 |     test.beforeEach(async ({ page }) => {
  122 |       await login(page)
  123 |     })
  124 | 
  125 |     test(' AccountSettings  ', async ({ page }) => {
  126 |       await page.goto(`${BASE}/account`)
  127 |       await page.waitForLoadState('networkidle')
  128 |       await page.waitForTimeout(3000)
  129 | 
  130 |       const url = page.url()
  131 |       expect(url).toContain('/account')
  132 | 
  133 |       const title = page.locator('.page-title')
  134 |       if (await title.count() > 0) {
  135 |         const text = await title.textContent()
  136 |         console.log(`AccountSettings  : ${text}`)
  137 |       }
  138 |     })
  139 | 
  140 |     test('    ', async ({ page }) => {
  141 |       await page.goto(`${BASE}/account`)
  142 |       await page.waitForLoadState('networkidle')
  143 |       await page.waitForTimeout(3000)
  144 | 
  145 |       const securityNav = page.getByRole('button', { name: '安全设置' })
  146 |       if (await securityNav.count() > 0) {
  147 |         await securityNav.click()
  148 |         await page.waitForTimeout(800)
  149 |         const passwordForm = page.locator('.password-form, .security-section')
  150 |         if (await passwordForm.count() > 0) {
  151 |           console.log('PASS:    ')
  152 |         }
  153 |       }
  154 |     })
  155 |   })
  156 | 
  157 |   test.describe('5. MetaListPage  CRUD', () => {
  158 |     test.beforeEach(async ({ page }) => {
  159 |       await login(page)
  160 |     })
  161 | 
  162 |     test('   MetaListPage  ', async ({ page }) => {
  163 |       await page.goto(`${BASE}/user-permission`)
  164 |       await page.waitForLoadState('networkidle')
  165 |       await page.waitForTimeout(3000)
  166 | 
  167 |       await page.waitForSelector('.meta-list-page, .el-table', { timeout: 15000 })
  168 |       const tableVisible = await page.locator('.el-table').isVisible().catch(() => false)
  169 | 
  170 |       if (tableVisible) {
  171 |         const createBtn = page.locator('.toolbar button:has-text(""), .toolbar button:has-text("")').first()
  172 |         if (await createBtn.isVisible().catch(() => false)) {
  173 |           await createBtn.click()
  174 |           await page.waitForTimeout(2000)
  175 | 
  176 |           const dialog = page.locator('.el-dialog, .el-drawer')
  177 |           const dialogVisible = await dialog.isVisible().catch(() => false)
  178 | 
  179 |           if (dialogVisible) {
  180 |             console.log('PASS: MetaListPage   ( AddMemberDialog )')
  181 |             const cancelBtn = page.locator('.el-dialog button:has-text(""), .el-drawer button:has-text("")').first()
  182 |             if (await cancelBtn.isVisible().catch(() => false)) {
  183 |               await cancelBtn.click()
  184 |               await page.waitForTimeout(500)
  185 |             }
  186 |           }
  187 |         }
  188 |       }
  189 |     })
  190 | 
  191 |     test('    MetaListPage  ', async ({ page }) => {
  192 |       await page.goto(`${BASE}/user-permission`)
  193 |       await page.waitForLoadState('networkidle')
  194 |       await page.waitForTimeout(3000)
  195 | 
  196 |       await page.waitForSelector('.meta-list-page, .el-table', { timeout: 15000 })
  197 | 
  198 |       const groupTab = page.locator('.el-tabs__item:has-text("")')
  199 |       if (await groupTab.count() > 0) {
  200 |         await groupTab.first().click()
  201 |         await page.waitForTimeout(2000)
  202 | 
  203 |         await page.waitForSelector('.el-table', { timeout: 10000 })
  204 |         console.log('PASS:    MetaListPage  ')
  205 |       }
  206 |     })
  207 |   })
  208 | 
  209 |   test.describe('6. FilterBar   (DynamicFilters )', () => {
  210 |     test.beforeEach(async ({ page }) => {
  211 |       await login(page)
  212 |     })
  213 | 
  214 |     test('FilterBar    ', async ({ page }) => {
  215 |       await page.goto(`${BASE}/user-permission`)
  216 |       await page.waitForLoadState('networkidle')
  217 |       await page.waitForTimeout(3000)
  218 | 
> 219 |       await page.waitForSelector('.meta-list-page, .el-table', { timeout: 15000 })
      |                  ^ TimeoutError: page.waitForSelector: Timeout 15000ms exceeded.
  220 | 
  221 |       const filterBar = page.locator('.filter-bar, .meta-filter-bar, [class*="filter"]')
  222 |       const count = await filterBar.count()
  223 | 
  224 |       if (count > 0) {
  225 |         console.log(`PASS: FilterBar   (${count} )`)
  226 |       } else {
  227 |         console.log('INFO: FilterBar  ')
  228 |       }
  229 |     })
  230 |   })
  231 | 
  232 | })
  233 | 
```