# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: audit-log-crud.spec.js >> 审计日志 - API CRUD >> GET /api/v2/bo/audit_log 应返回审计日志列表
- Location: e2e\audit-log-crud.spec.js:17:3

# Error details

```
Error: expect(received).toBeTruthy()

Received: false
```

# Test source

```ts
  1   | /**
  2   |  * 审计日志 E2E 测试
  3   |  * 
  4   |  * 测试范围：
  5   |  * - 审计日志 API CRUD
  6   |  * - 审计日志字段完整性
  7   |  * - 审计日志查询过滤
  8   |  * - 审计日志关联操作记录
  9   |  */
  10  | 
  11  | import { test, expect } from '@playwright/test'
  12  | 
  13  | const UI_BASE_URL = process.env.VITE_API_BASE || 'http://localhost:3004'
  14  | const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:3010'
  15  | 
  16  | test.describe('审计日志 - API CRUD', () => {
  17  |   test('GET /api/v2/bo/audit_log 应返回审计日志列表', async ({ request }) => {
  18  |     const response = await request.get(`${API_BASE_URL}/api/v2/bo/audit_log`, {
  19  |       params: { page: 1, page_size: 10 }
  20  |     })
  21  |     
> 22  |     expect(response.ok()).toBeTruthy()
      |                           ^ Error: expect(received).toBeTruthy()
  23  |     const data = await response.json()
  24  |     expect(data.success).toBe(true)
  25  |     expect(Array.isArray(data.data.items)).toBe(true)
  26  |   })
  27  | 
  28  |   test('GET /api/v2/bo/audit_log/:id 应返回单条审计日志', async ({ request }) => {
  29  |     const listResponse = await request.get(`${API_BASE_URL}/api/v2/bo/audit_log`, {
  30  |       params: { page: 1, page_size: 1 }
  31  |     })
  32  |     
  33  |     const listData = await listResponse.json()
  34  |     if (listData.data.items.length > 0) {
  35  |       const logId = listData.data.items[0].id
  36  |       const detailResponse = await request.get(`${API_BASE_URL}/api/v2/bo/audit_log/${logId}`)
  37  |       expect(detailResponse.ok()).toBeTruthy()
  38  |       const detailData = await detailResponse.json()
  39  |       expect(detailData.success).toBe(true)
  40  |     }
  41  |   })
  42  | 
  43  |   test('GET /api/v2/bo/audit_log 应支持分页', async ({ request }) => {
  44  |     const response = await request.get(`${API_BASE_URL}/api/v2/bo/audit_log`, {
  45  |       params: { page: 1, page_size: 5 }
  46  |     })
  47  |     
  48  |     const data = await response.json()
  49  |     expect(data.data.page).toBe(1)
  50  |     expect(data.data.page_size).toBe(5)
  51  |   })
  52  | })
  53  | 
  54  | test.describe('审计日志 - 字段完整性', () => {
  55  |   test('审计日志应包含基本字段', async ({ request }) => {
  56  |     const response = await request.get(`${API_BASE_URL}/api/v2/bo/audit_log`, {
  57  |       params: { page: 1, page_size: 10 }
  58  |     })
  59  |     
  60  |     const data = await response.json()
  61  |     if (data.data.items.length > 0) {
  62  |       const log = data.data.items[0]
  63  |       
  64  |       expect(log).toHaveProperty('id')
  65  |       expect(log).toHaveProperty('object_type')
  66  |       expect(log).toHaveProperty('action')
  67  |       expect(log).toHaveProperty('user_id')
  68  |       expect(log).toHaveProperty('created_at')
  69  |     }
  70  |   })
  71  | 
  72  |   test('审计日志应包含变更详情字段', async ({ request }) => {
  73  |     const response = await request.get(`${API_BASE_URL}/api/v2/bo/audit_log`, {
  74  |       params: { page: 1, page_size: 10 }
  75  |     })
  76  |     
  77  |     const data = await response.json()
  78  |     if (data.data.items.length > 0) {
  79  |       const log = data.data.items[0]
  80  |       
  81  |       expect(log).toHaveProperty('field_name')
  82  |       expect(log).toHaveProperty('old_value')
  83  |       expect(log).toHaveProperty('new_value')
  84  |     }
  85  |   })
  86  | 
  87  |   test('审计日志应包含追踪字段', async ({ request }) => {
  88  |     const response = await request.get(`${API_BASE_URL}/api/v2/bo/audit_log`, {
  89  |       params: { page: 1, page_size: 10 }
  90  |     })
  91  |     
  92  |     const data = await response.json()
  93  |     if (data.data.items.length > 0) {
  94  |       const log = data.data.items[0]
  95  |       
  96  |       expect(log).toHaveProperty('trace_id')
  97  |       expect(log).toHaveProperty('transaction_id')
  98  |     }
  99  |   })
  100 | })
  101 | 
  102 | test.describe('审计日志 - 查询过滤', () => {
  103 |   test('审计日志应支持按对象类型过滤', async ({ request }) => {
  104 |     const response = await request.get(`${API_BASE_URL}/api/v2/bo/audit_log`, {
  105 |       params: { 
  106 |         page: 1, 
  107 |         page_size: 10,
  108 |         filters: JSON.stringify([{ field: 'object_type', operator: 'eq', value: 'user' }])
  109 |       }
  110 |     })
  111 |     
  112 |     const data = await response.json()
  113 |     expect(data.success).toBe(true)
  114 |     
  115 |     for (const item of data.data.items) {
  116 |       expect(item.object_type).toBe('user')
  117 |     }
  118 |   })
  119 | 
  120 |   test('审计日志应支持按操作类型过滤', async ({ request }) => {
  121 |     const response = await request.get(`${API_BASE_URL}/api/v2/bo/audit_log`, {
  122 |       params: { 
```