# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: core-object-verification.spec.js >> 核心对象 DisplayName 验证 >> Role - displayName应为name字段
- Location: e2e\core-object-verification.spec.js:69:3

# Error details

```
Error: expect(received).toBeTruthy()

Received: false
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
      - generic [ref=e24]: IP已被封禁，请2分钟后重试
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
  2   |  * 核心对象 E2E 验证测试
  3   |  * 
  4   |  * 验证内容：
  5   |  * 1. DisplayName 配置正确性
  6   |  * 2. ValueHelp 配置和功能正确性
  7   |  * 3. 时间格式正确性
  8   |  * 4. 控件类型正确性（form字段、table列）
  9   |  * 5. Association Tab中的table列配置
  10  |  * 6. Add/Remove Association弹窗功能
  11  |  */
  12  | 
  13  | import { test, expect } from '@playwright/test'
  14  | 
  15  | const BASE_URL = process.env.VITE_API_BASE || 'http://localhost:3004'
  16  | 
  17  | async function login(page) {
  18  |   await page.goto(`${BASE_URL}/`)
  19  |   await page.waitForLoadState('networkidle')
  20  |   await page.waitForTimeout(2000)
  21  | 
  22  |   const usernameInput = page.locator('input[placeholder*="用户名"], input[type="text"]').first()
  23  |   const passwordInput = page.locator('input[type="password"]')
  24  | 
  25  |   if (await usernameInput.isVisible()) {
  26  |     await usernameInput.fill('admin')
  27  |     await passwordInput.fill('admin123')
  28  |     const loginBtn = page.locator('button[type="submit"], button:has-text("登 录")')
  29  |     if (await loginBtn.isVisible()) {
  30  |       await loginBtn.click()
  31  |       await page.waitForTimeout(3000)
  32  |     }
  33  |   }
  34  | }
  35  | 
  36  | test.describe('核心对象 DisplayName 验证', () => {
  37  |   test.beforeEach(async ({ page }) => {
  38  |     await login(page)
  39  |   })
  40  | 
  41  |   test('User - displayName应为username字段', async ({ page, request }) => {
  42  |     const loginResponse = await request.post('/api/v1/auth/login', {
  43  |       data: { username: 'admin', password: 'admin123' }
  44  |     })
  45  |     const loginData = await loginResponse.json()
  46  |     const token = loginData.data?.token
  47  | 
  48  |     const metaResponse = await request.get('/api/v2/meta/user/ui-config', {
  49  |       headers: { Authorization: `Bearer ${token}` }
  50  |     })
  51  |     expect(metaResponse.ok()).toBeTruthy()
  52  |     const metaData = await metaResponse.json()
  53  |     
  54  |     expect(metaData.data.display_name_field).toBe('username')
  55  |     console.log('✅ User displayName_field = username')
  56  | 
  57  |     const userResponse = await request.get('/api/v2/bo/user', {
  58  |       headers: { Authorization: `Bearer ${token}` },
  59  |       params: { page: 1, page_size: 1 }
  60  |     })
  61  |     const userData = await userResponse.json()
  62  |     if (userData.data?.items?.length > 0) {
  63  |       const user = userData.data.items[0]
  64  |       expect(user.username).toBeDefined()
  65  |       console.log(`✅ User示例: username=${user.username}, display_name=${user.display_name}`)
  66  |     }
  67  |   })
  68  | 
  69  |   test('Role - displayName应为name字段', async ({ request }) => {
  70  |     const loginResponse = await request.post('/api/v1/auth/login', {
  71  |       data: { username: 'admin', password: 'admin123' }
  72  |     })
  73  |     const loginData = await loginResponse.json()
  74  |     const token = loginData.data?.token
  75  | 
  76  |     const metaResponse = await request.get('/api/v2/meta/role/ui-config', {
  77  |       headers: { Authorization: `Bearer ${token}` }
  78  |     })
> 79  |     expect(metaResponse.ok()).toBeTruthy()
      |                               ^ Error: expect(received).toBeTruthy()
  80  |     const metaData = await metaResponse.json()
  81  |     
  82  |     expect(metaData.data.display_name_field).toBe('name')
  83  |     console.log('✅ Role displayName_field = name')
  84  |   })
  85  | 
  86  |   test('Product - displayName应为name字段', async ({ request }) => {
  87  |     const loginResponse = await request.post('/api/v1/auth/login', {
  88  |       data: { username: 'admin', password: 'admin123' }
  89  |     })
  90  |     const loginData = await loginResponse.json()
  91  |     const token = loginData.data?.token
  92  | 
  93  |     const metaResponse = await request.get('/api/v2/meta/product/ui-config', {
  94  |       headers: { Authorization: `Bearer ${token}` }
  95  |     })
  96  |     expect(metaResponse.ok()).toBeTruthy()
  97  |     const metaData = await metaResponse.json()
  98  |     
  99  |     expect(metaData.data.display_name_field).toBe('name')
  100 |     console.log('✅ Product displayName_field = name')
  101 |   })
  102 | 
  103 |   test('Version - displayName应为name字段', async ({ request }) => {
  104 |     const loginResponse = await request.post('/api/v1/auth/login', {
  105 |       data: { username: 'admin', password: 'admin123' }
  106 |     })
  107 |     const loginData = await loginResponse.json()
  108 |     const token = loginData.data?.token
  109 | 
  110 |     const metaResponse = await request.get('/api/v2/meta/version/ui-config', {
  111 |       headers: { Authorization: `Bearer ${token}` }
  112 |     })
  113 |     expect(metaResponse.ok()).toBeTruthy()
  114 |     const metaData = await metaResponse.json()
  115 |     
  116 |     const displayName = metaData.data.display_name_field
  117 |     
  118 |     const fields = metaData.data.fields || []
  119 |     const nameField = fields.find(f => f.id === 'name')
  120 |     const codeField = fields.find(f => f.id === 'code')
  121 |     
  122 |     if (displayName) {
  123 |       console.log(`Version displayName_field = ${displayName}`)
  124 |     } else {
  125 |       const hasNameField = nameField?.semantics?.display_name
  126 |       console.log(`Version displayName无需显式配置（通过name字段推断）: ${hasNameField ? '✅' : '需确认'}`)
  127 |     }
  128 | 
  129 |     const schemaRes = await request.get('/api/v2/meta/version/schema', {
  130 |       headers: { Authorization: `Bearer ${token}` }
  131 |     })
  132 |     const schemaData = await schemaRes.json()
  133 |     const sData = schemaData.data || schemaData
  134 |     const rawJson = JSON.stringify(sData)
  135 |     const hasDisplayName = rawJson.includes('display_name_field') || rawJson.includes('display_name')
  136 |     console.log(`  schema含displayName配置: ${hasDisplayName ? '✅' : '⚠️'}`)
  137 |   })
  138 | 
  139 |   test('BusinessObject - displayName应为name字段', async ({ request }) => {
  140 |     const loginResponse = await request.post('/api/v1/auth/login', {
  141 |       data: { username: 'admin', password: 'admin123' }
  142 |     })
  143 |     const loginData = await loginResponse.json()
  144 |     const token = loginData.data?.token
  145 | 
  146 |     const metaResponse = await request.get('/api/v2/meta/business_object/ui-config', {
  147 |       headers: { Authorization: `Bearer ${token}` }
  148 |     })
  149 |     expect(metaResponse.ok()).toBeTruthy()
  150 |     const metaData = await metaResponse.json()
  151 |     
  152 |     expect(metaData.data.display_name_field).toBe('name')
  153 |     console.log('✅ BusinessObject displayName_field = name')
  154 |   })
  155 | })
  156 | 
  157 | test.describe('ValueHelp 配置验证', () => {
  158 |   test.beforeEach(async ({ page }) => {
  159 |     await login(page)
  160 |   })
  161 | 
  162 |   test('User.status - ValueHelp应配置为enum类型', async ({ request }) => {
  163 |     const loginResponse = await request.post('/api/v1/auth/login', {
  164 |       data: { username: 'admin', password: 'admin123' }
  165 |     })
  166 |     const loginData = await loginResponse.json()
  167 |     const token = loginData.data?.token
  168 | 
  169 |     const metaResponse = await request.get('/api/v2/meta/user/ui-config', {
  170 |       headers: { Authorization: `Bearer ${token}` }
  171 |     })
  172 |     const metaData = await metaResponse.json()
  173 |     
  174 |     const statusField = metaData.data.fields?.find(f => f.id === 'status')
  175 |     expect(statusField).toBeDefined()
  176 |     
  177 |     expect(statusField.value_help).toBeDefined()
  178 |     expect(statusField.value_help.source.type).toBe('enum')
  179 |     expect(statusField.value_help.source.enum_type_id).toBe('user_status')
```