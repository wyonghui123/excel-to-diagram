# -*- coding: utf-8 -*-
"""
[FIX 2026-06-12] 用户视角诊断脚本 - 让用户自己在浏览器里跑
复制以下全部到浏览器 DevTools Console (F12) 跑, 把输出贴给 AI
"""
DIAG = """
async function __diagnoseBatchDelete() {
  console.log('=== 1. 后端 connectivity ===')
  const r1 = await fetch('/api/v2/bo/user_group_member?page=1&page_size=1', {credentials: 'include'})
  const m = await r1.json()
  console.log('  user_group_member first page:', m.data?.items?.[0])
  const gid = m.data?.items?.[0]?.group_id
  console.log('  using group_id =', gid)

  console.log()
  console.log('=== 2. 后端 batch-delete 实际响应 (绕过前端) ===')
  const r2 = await fetch('/api/v2/bo/user_group/batch-delete', {
    method: 'POST',
    credentials: 'include',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ids: [gid]})
  })
  console.log('  status:', r2.status)
  const txt = await r2.text()
  console.log('  raw body:', txt)

  console.log()
  console.log('=== 3. DB 验证 (用 fetch 读 GET 看是否真删) ===')
  const r3 = await fetch(`/api/v2/bo/user_group/${gid}`, {credentials: 'include'})
  console.log('  GET /user_group/' + gid + ' status:', r3.status, '→ 200 表示还在, 404 表示已删')

  console.log()
  console.log('=== 4. 当前 httpClient 实际行为 (复现前端 batchDelete 路径) ===')
  // 直接调 window 上的 httpClient (从 import 进来, 模拟前端的 _request)
  // 用动态 import 拿 module
  const httpMod = await import('/src/utils/httpClient.js')
  const result = await httpMod.apiV2.post('/bo/user_group/batch-delete', {ids: [gid]})
  console.log('  httpClient.apiV2.post result:', JSON.stringify(result, null, 2))

  console.log()
  console.log('=== 5. 检查 useMetaList 当前加载的是不是新代码 ===')
  const ml = await import('/src/composables/useMetaList.js')
  console.log('  useMetaList loaded, has handleBatchDelete?', typeof ml.useMetaList)

  return {ok: r2.status, gid}
}
console.log('[DIAG] 复制下面到 console 跑:')
console.log('  __diagnoseBatchDelete()')
"""
print(DIAG)
