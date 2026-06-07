# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: annotation-metadata.spec.js >> Annotation API Tests - Annotation API 测试 >> TC-ANN-API-003: UI Config 应返回 relationship 的 annotation child_section
- Location: e2e\annotation-metadata.spec.js:86:3

# Error details

```
Error: expect(received).toBeTruthy()

Received: false
```

# Test source

```ts
  1   | /**
  2   |  * Annotation 元数据驱动 E2E 测试
  3   |  * 
  4   |  * 测试服务模块、业务对象、关系的 Annotation CRUD
  5   |  * 验证:
  6   |  * 1. UI Config 返回 child_sections 配置
  7   |  * 2. 详情页显示 AnnotationList 组件
  8   |  * 3. Annotation CRUD 操作正常工作
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
  34  | test.describe('Annotation API Tests - Annotation API 测试', () => {
  35  |   test('TC-ANN-API-001: UI Config 应返回 service_module 的 annotation child_section', async ({ request }) => {
  36  |     const loginResponse = await request.post(`${BASE_URL}/api/v1/auth/login`, {
  37  |       data: { username: 'admin', password: 'admin123' }
  38  |     })
  39  |     expect(loginResponse.ok()).toBeTruthy()
  40  |     const loginData = await loginResponse.json()
  41  |     const token = loginData.data?.token
  42  | 
  43  |     const uiConfigResponse = await request.get(`${BASE_URL}/api/v2/meta/service_module/ui-config`, {
  44  |       headers: { Authorization: `Bearer ${token}` }
  45  |     })
  46  | 
  47  |     expect(uiConfigResponse.ok()).toBeTruthy()
  48  |     const uiConfig = await uiConfigResponse.json()
  49  |     expect(uiConfig.success).toBe(true)
  50  | 
  51  |     const childSections = uiConfig.data?.ui_view_config?.child_sections || []
  52  |     const annotationSection = childSections.find(cs => cs.child_object === 'annotation')
  53  | 
  54  |     expect(annotationSection).toBeDefined()
  55  |     expect(annotationSection.title).toBe('备注信息')
  56  |     expect(annotationSection.columns).toBeDefined()
  57  |     expect(annotationSection.columns.length).toBeGreaterThanOrEqual(3)
  58  |     
  59  |     console.log('✅ service_module UI Config 包含 annotation child_section')
  60  |     console.log(`   - title: ${annotationSection.title}`)
  61  |     console.log(`   - columns: ${annotationSection.columns.length} 个`)
  62  |   })
  63  | 
  64  |   test('TC-ANN-API-002: UI Config 应返回 business_object 的 annotation child_section', async ({ request }) => {
  65  |     const loginResponse = await request.post(`${BASE_URL}/api/v1/auth/login`, {
  66  |       data: { username: 'admin', password: 'admin123' }
  67  |     })
  68  |     const loginData = await loginResponse.json()
  69  |     const token = loginData.data?.token
  70  | 
  71  |     const uiConfigResponse = await request.get(`${BASE_URL}/api/v2/meta/business_object/ui-config`, {
  72  |       headers: { Authorization: `Bearer ${token}` }
  73  |     })
  74  | 
  75  |     expect(uiConfigResponse.ok()).toBeTruthy()
  76  |     const uiConfig = await uiConfigResponse.json()
  77  |     expect(uiConfig.success).toBe(true)
  78  | 
  79  |     const childSections = uiConfig.data?.ui_view_config?.child_sections || []
  80  |     const annotationSection = childSections.find(cs => cs.child_object === 'annotation')
  81  | 
  82  |     expect(annotationSection).toBeDefined()
  83  |     console.log('✅ business_object UI Config 包含 annotation child_section')
  84  |   })
  85  | 
  86  |   test('TC-ANN-API-003: UI Config 应返回 relationship 的 annotation child_section', async ({ request }) => {
  87  |     const loginResponse = await request.post(`${BASE_URL}/api/v1/auth/login`, {
  88  |       data: { username: 'admin', password: 'admin123' }
  89  |     })
  90  |     const loginData = await loginResponse.json()
  91  |     const token = loginData.data?.token
  92  | 
  93  |     const uiConfigResponse = await request.get(`${BASE_URL}/api/v2/meta/relationship/ui-config`, {
  94  |       headers: { Authorization: `Bearer ${token}` }
  95  |     })
  96  | 
> 97  |     expect(uiConfigResponse.ok()).toBeTruthy()
      |                                   ^ Error: expect(received).toBeTruthy()
  98  |     const uiConfig = await uiConfigResponse.json()
  99  |     expect(uiConfig.success).toBe(true)
  100 | 
  101 |     const childSections = uiConfig.data?.ui_view_config?.child_sections || []
  102 |     const annotationSection = childSections.find(cs => cs.child_object === 'annotation')
  103 | 
  104 |     expect(annotationSection).toBeDefined()
  105 |     console.log('✅ relationship UI Config 包含 annotation child_section')
  106 |   })
  107 | 
  108 |   test('TC-ANN-API-004: Annotation 应定义 polymorphic association', async ({ request }) => {
  109 |     const loginResponse = await request.post(`${BASE_URL}/api/v1/auth/login`, {
  110 |       data: { username: 'admin', password: 'admin123' }
  111 |     })
  112 |     const loginData = await loginResponse.json()
  113 |     const token = loginData.data?.token
  114 | 
  115 |     const uiConfigResponse = await request.get(`${BASE_URL}/api/v2/meta/annotation/ui-config`, {
  116 |       headers: { Authorization: `Bearer ${token}` }
  117 |     })
  118 | 
  119 |     expect(uiConfigResponse.ok()).toBeTruthy()
  120 |     const uiConfig = await uiConfigResponse.json()
  121 |     expect(uiConfig.success).toBe(true)
  122 | 
  123 |     const associations = uiConfig.data?.associations || []
  124 |     const targetAssoc = associations.find(a => a.name === 'target')
  125 | 
  126 |     expect(targetAssoc).toBeDefined()
  127 |     expect(targetAssoc.target_type).toBe('polymorphic')
  128 |     expect(targetAssoc.type).toBe('many_to_one')
  129 |     
  130 |     console.log('✅ annotation 定义了 polymorphic association')
  131 |     console.log(`   - polymorphic_type_field: ${targetAssoc.polymorphic_type_field}`)
  132 |     console.log(`   - polymorphic_id_field: ${targetAssoc.polymorphic_id_field}`)
  133 |   })
  134 | 
  135 |   test('TC-ANN-API-005: 创建和查询 service_module annotation', async ({ request }) => {
  136 |     const loginResponse = await request.post(`${BASE_URL}/api/v1/auth/login`, {
  137 |       data: { username: 'admin', password: 'admin123' }
  138 |     })
  139 |     const loginData = await loginResponse.json()
  140 |     const token = loginData.data?.token
  141 | 
  142 |     // 创建 annotation
  143 |     const createResponse = await request.post(`${BASE_URL}/api/v1/annotations`, {
  144 |       headers: { 
  145 |         Authorization: `Bearer ${token}`,
  146 |         'Content-Type': 'application/json'
  147 |       },
  148 |       data: {
  149 |         target_type: 'service_module',
  150 |         target_id: 1,
  151 |         category: 'important',
  152 |         content: 'E2E测试 - 服务模块重要备注'
  153 |       }
  154 |     })
  155 | 
  156 |     expect(createResponse.ok()).toBeTruthy()
  157 |     const createData = await createResponse.json()
  158 |     expect(createData.success).toBe(true)
  159 |     const annotationId = createData.data.id
  160 | 
  161 |     console.log(`✅ 创建 service_module annotation: ID=${annotationId}`)
  162 | 
  163 |     // 查询 annotation
  164 |     const getResponse = await request.get(`${BASE_URL}/api/v1/annotations/${annotationId}`, {
  165 |       headers: { Authorization: `Bearer ${token}` }
  166 |     })
  167 | 
  168 |     expect(getResponse.ok()).toBeTruthy()
  169 |     const getData = await getResponse.json()
  170 |     expect(getData.success).toBe(true)
  171 |     expect(getData.data.target_type).toBe('service_module')
  172 |     expect(getData.data.category).toBe('important')
  173 | 
  174 |     console.log('✅ 查询 annotation 成功')
  175 | 
  176 |     // 删除 annotation
  177 |     const deleteResponse = await request.delete(`${BASE_URL}/api/v1/annotations/${annotationId}`, {
  178 |       headers: { Authorization: `Bearer ${token}` }
  179 |     })
  180 | 
  181 |     expect(deleteResponse.ok()).toBeTruthy()
  182 |     console.log('✅ 删除 annotation 成功')
  183 |   })
  184 | 
  185 |   test('TC-ANN-API-006: 创建和查询 business_object annotation', async ({ request }) => {
  186 |     const loginResponse = await request.post(`${BASE_URL}/api/v1/auth/login`, {
  187 |       data: { username: 'admin', password: 'admin123' }
  188 |     })
  189 |     const loginData = await loginResponse.json()
  190 |     const token = loginData.data?.token
  191 | 
  192 |     // 创建 annotation
  193 |     const createResponse = await request.post(`${BASE_URL}/api/v1/annotations`, {
  194 |       headers: { 
  195 |         Authorization: `Bearer ${token}`,
  196 |         'Content-Type': 'application/json'
  197 |       },
```