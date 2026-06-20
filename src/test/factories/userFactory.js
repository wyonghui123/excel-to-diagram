/**
 * userFactory.js - User Test Data Factory
 *
 * Usage:
 *   import { createUser, createAdminUser, cleanupUser } from '@/test/factories/userFactory'
 *
 *   // Unit test
 *   const mockUser = createUser()
 *
 *   // E2E test
 *   const user = await createUser(api)
 *   // ... test ...
 *   await cleanupUser(user.id, api)
 */

const COUNTER = { value: 0 }

function nextId() {
  COUNTER.value += 1
  return COUNTER.value
}

function randomStr(n = 8) {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
  let result = ''
  for (let i = 0; i < n; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  return result
}

export function createUser(overrides = {}) {
  const id = nextId()
  const ts = Date.now()
  return {
    id,
    username: `test_user_${id}_${ts}_${randomStr(4)}`,
    display_name: `Test User ${id}`,
    email: `test_${id}_${ts}@test.local`,
    role: 'user',
    roles: ['user'],
    permissions: ['*'],
    status: 'active',
    ...overrides
  }
}

export function createAdminUser(overrides = {}) {
  return createUser({
    username: `admin_user_${Date.now()}_${randomStr(4)}`,
    display_name: 'Admin Test User',
    role: 'admin',
    roles: ['admin'],
    permissions: ['*'],
    ...overrides
  })
}

export async function createUserViaApi(api, overrides = {}) {
  const user = createUser(overrides)
  const resp = await api.post('/api/v2/bo/user', {
    data: user,
    headers: { 'Content-Type': 'application/json' }
  })

  if (!resp.ok()) {
    throw new Error(`Failed to create user: ${resp.status()} ${await resp.text()}`)
  }

  const json = await resp.json()
  return { ...user, id: json.data?.id || user.id }
}

export async function cleanupUser(userId, api) {
  if (!userId || !api) return
  try {
    await api.delete(`/api/v2/bo/user/${userId}`)
  } catch (e) {
    console.warn(`[cleanupUser] Failed to cleanup user ${userId}:`, e.message)
  }
}

export function buildUserResponse(user) {
  return {
    success: true,
    data: user
  }
}
