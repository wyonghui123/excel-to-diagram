# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: association-metadata.spec.js >> UserGroup Associations - 用户组关联测试 >> TC-ASSOC-GROUP-002: 移除成员时应显示自定义确认消息
- Location: e2e\association-metadata.spec.js:255:3

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
  200 |     // 打开第一个用户组的详情
  201 |     const firstRow = page.locator('.el-table__body tr').first()
  202 |     await firstRow.click()
  203 |     await page.waitForTimeout(2000)
  204 | 
  205 |     const drawer = page.locator('.el-drawer').first()
  206 |     if (await drawer.isVisible()) {
  207 |       // 查找成员标签
  208 |       const memberTab = drawer.locator('.el-tabs__item:has-text("成员"), .anchor-tab:has-text("成员")')
  209 |       const roleTab = drawer.locator('.el-tabs__item:has-text("角色"), .anchor-tab:has-text("角色")')
  210 | 
  211 |       const hasMemberTab = await memberTab.count() > 0
  212 |       const hasRoleTab = await roleTab.count() > 0
  213 | 
  214 |       console.log(`成员标签: ${hasMemberTab}, 角色标签: ${hasRoleTab}`)
  215 | 
  216 |       if (hasMemberTab) {
  217 |         await memberTab.first().click()
  218 |         await page.waitForTimeout(1000)
  219 | 
  220 |         // 验证成员关联面板
  221 |         const assocPanel = drawer.locator('.association-panel').first()
  222 |         if (await assocPanel.isVisible()) {
  223 |           console.log('✅ 成员关联面板已渲染')
  224 | 
  225 |           // 验证列定义: username, display_name, email
  226 |           const headers = assocPanel.locator('.ap-table th')
  227 |           const headerCount = await headers.count()
  228 |           console.log(`成员表格列数: ${headerCount}`)
  229 | 
  230 |           // user_group.yaml 定义了 username, display_name, email 三列
  231 |           expect(headerCount).toBeGreaterThanOrEqual(3)
  232 |         }
  233 |       }
  234 | 
  235 |       if (hasRoleTab) {
  236 |         await roleTab.first().click()
  237 |         await page.waitForTimeout(1000)
  238 | 
  239 |         // 验证角色关联面板
  240 |         const rolePanel = drawer.locator('.association-panel').first()
  241 |         if (await rolePanel.isVisible()) {
  242 |           console.log('✅ 角色关联面板已渲染')
  243 | 
  244 |           // 验证列定义: code, name, description
  245 |           const headers = rolePanel.locator('.ap-table th')
  246 |           const headerCount = await headers.count()
  247 |           console.log(`角色表格列数: ${headerCount}`)
  248 | 
  249 |           expect(headerCount).toBeGreaterThanOrEqual(3)
  250 |         }
  251 |       }
  252 |     }
  253 |   })
  254 | 
  255 |   test('TC-ASSOC-GROUP-002: 移除成员时应显示自定义确认消息', async ({ page }) => {
> 256 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
      |                ^ TimeoutError: page.waitForSelector: Timeout 15000ms exceeded.
  257 |     await page.waitForTimeout(2000)
  258 | 
  259 |     const firstRow = page.locator('.el-table__body tr').first()
  260 |     await firstRow.click()
  261 |     await page.waitForTimeout(2000)
  262 | 
  263 |     const drawer = page.locator('.el-drawer').first()
  264 |     if (await drawer.isVisible()) {
  265 |       const memberTab = drawer.locator('.el-tabs__item:has-text("成员"), .anchor-tab:has-text("成员")')
  266 |       if (await memberTab.count() > 0) {
  267 |         await memberTab.first().click()
  268 |         await page.waitForTimeout(1000)
  269 | 
  270 |         // 监听确认对话框
  271 |         let confirmMessage = ''
  272 |         page.on('dialog', async dialog => {
  273 |           confirmMessage = dialog.message()
  274 |           console.log(`成员移除确认消息: "${confirmMessage}"`)
  275 |           await dialog.dismiss()
  276 |         })
  277 | 
  278 |         const removeBtn = drawer.locator('.association-panel button:has-text("移除")').first()
  279 |         if (await removeBtn.isVisible()) {
  280 |           await removeBtn.click()
  281 |           await page.waitForTimeout(500)
  282 | 
  283 |           // 验证 confirm_message 来自 YAML 配置
  284 |           expect(confirmMessage).toContain('用户组')
  285 |         }
  286 |       }
  287 |     }
  288 |   })
  289 | })
  290 | 
  291 | test.describe('Role Associations - 角色关联测试', () => {
  292 |   test.beforeEach(async ({ page }) => {
  293 |     await login(page)
  294 |     // 导航到角色管理
  295 |     await page.goto(`${BASE_URL}/role-management`)
  296 |     await page.waitForLoadState('networkidle')
  297 |     await page.waitForTimeout(3000)
  298 |   })
  299 | 
  300 |   test('TC-ASSOC-ROLE-001: 角色详情应显示"用户"和"用户组"关联面板', async ({ page }) => {
  301 |     await page.waitForSelector('.el-table__body tr', { timeout: 15000 })
  302 |     await page.waitForTimeout(2000)
  303 | 
  304 |     // 打开第一个角色的详情
  305 |     const firstRow = page.locator('.el-table__body tr').first()
  306 |     await firstRow.click()
  307 |     await page.waitForTimeout(2000)
  308 | 
  309 |     const drawer = page.locator('.el-drawer').first()
  310 |     if (await drawer.isVisible()) {
  311 |       // 查找用户标签 (新增的 tab)
  312 |       const userTab = drawer.locator('.el-tabs__item:has-text("用户"), .anchor-tab:has-text("用户")')
  313 |       const groupTab = drawer.locator('.el-tabs__item:has-text("用户组"), .anchor-tab:has-text("用户组")')
  314 | 
  315 |       const hasUserTab = await userTab.count() > 0
  316 |       const hasGroupTab = await groupTab.count() > 0
  317 | 
  318 |       console.log(`用户标签: ${hasUserTab}, 用户组标签: ${hasGroupTab}`)
  319 | 
  320 |       if (hasUserTab) {
  321 |         await userTab.first().click()
  322 |         await page.waitForTimeout(1000)
  323 | 
  324 |         // 验证用户关联面板
  325 |         const userPanel = drawer.locator('.association-panel').first()
  326 |         if (await userPanel.isVisible()) {
  327 |           console.log('✅ 用户关联面板已渲染')
  328 | 
  329 |           // 验证列定义: username, display_name, email
  330 |           const headers = userPanel.locator('.ap-table th')
  331 |           const headerCount = await headers.count()
  332 |           console.log(`用户表格列数: ${headerCount}`)
  333 | 
  334 |           expect(headerCount).toBeGreaterThanOrEqual(3)
  335 |         }
  336 |       }
  337 | 
  338 |       if (hasGroupTab) {
  339 |         await groupTab.first().click()
  340 |         await page.waitForTimeout(1000)
  341 | 
  342 |         // 验证用户组关联面板 (readonly)
  343 |         const groupPanel = drawer.locator('.association-panel').first()
  344 |         if (await groupPanel.isVisible()) {
  345 |           console.log('✅ 用户组关联面板已渲染')
  346 | 
  347 |           // readonly 的关联不应有添加/移除按钮
  348 |           const addBtn = groupPanel.locator('button:has-text("添加")')
  349 |           const removeBtn = groupPanel.locator('button:has-text("移除")')
  350 |           
  351 |           const hasAddBtn = await addBtn.count() > 0 && await addBtn.isVisible()
  352 |           const hasRemoveBtn = await removeBtn.count() > 0 && await removeBtn.isVisible()
  353 | 
  354 |           console.log(`添加按钮可见: ${hasAddBtn}, 移除按钮可见: ${hasRemoveBtn}`)
  355 |           
  356 |           // assigned_groups 是 readonly，不应该有编辑按钮
```