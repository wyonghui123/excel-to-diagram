/**
 * Playwright E2E 测试配置
 *
 * [CRITICAL] E2E 测试核心规则（修改此文件或测试用例前必读）:
 * ─────────────────────────────────────────────────────────
 * 1. 禁止 waitForLoadState('networkidle') - SPA 中会永久卡死
 * 2. 截图用 testInfo.attach() - 不用 screenshot:'on'（会截到首页）
 * 3. 导航用 navigateTo() - 不用 page.goto() + waitForTimeout
 * 4. 权限用 setAdminPermissions() - 必须同时改 localStorage + Pinia
 * 5. 每个 project 必须指定 testDir - 避免扫描旧文件
 * 6. 测试终端与 dev server 终端分离 - 否则服务被杀
 * 7. Element Plus 下拉选项用 :visible 约束
 * 8. API 请求必须带 Authorization header
 * 9. **认证共享：setup project + storageState** - 不再每个测试重复登录
 * 10. **数据查找：用 data-finder.js fixtures** - 不硬编码产品/版本 ID
 * ─────────────────────────────────────────────────────────
 * 详细规则: .trae/rules/e2e-testing.md
 * 辅助函数: e2e/helpers/auth.js
 */
import { defineConfig, devices } from '@playwright/test'
import path from 'path'

const baseUse = {
  baseURL: 'http://localhost:3004',
  trace: 'on',
  screenshot: 'only-on-failure',
  video: 'retain-on-failure',
  actionTimeout: 10000,
  locale: 'zh-CN'
}

// Auth state files (在 global-setup.js 中生成)
const AUTH_DIR = path.join(process.cwd(), 'e2e', '.auth')
const ADMIN_AUTH = path.join(AUTH_DIR, 'admin.json')
const USER_AUTH = path.join(AUTH_DIR, 'user.json')

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: 1,
  reporter: [['html', { open: 'never' }], ['list']],
  timeout: 60000,
  expect: {
    timeout: 15000
  },
  use: { ...baseUse },
  projects: [
    // ============================================================
    // Setup project - 一次登录，所有 project 共享
    // ============================================================
    {
      name: 'setup',
      testMatch: /.*\.setup\.js/,
      testDir: './e2e/helpers',
      timeout: 60000
    },

    // ============================================================
    // Smoke tests - 快速冒烟，admin 权限
    // ============================================================
    {
      name: 'smoke',
      testDir: './e2e/smoke',
      testMatch: '*.smoke.spec.js',
      use: {
        ...baseUse,
        ...devices['Desktop Chrome'],
        storageState: ADMIN_AUTH  // 自动登录
      },
      dependencies: ['setup']
    },

    // ============================================================
    // Features tests - 功能测试，admin 权限
    // ============================================================
    {
      name: 'features',
      testDir: './e2e/features',
      use: {
        ...baseUse,
        ...devices['Desktop Chrome'],
        storageState: ADMIN_AUTH
      },
      dependencies: ['setup']
    },
    {
      name: 'demo',
      testDir: './e2e/demo',
      testMatch: '*.spec.js',
      use: {
        ...baseUse,
        ...devices['Desktop Chrome'],
        storageState: ADMIN_AUTH
      },
      dependencies: ['setup']
    },

    // ============================================================
    // Permission tests - 权限测试，readonly 用户
    // ============================================================
    {
      name: 'permissions',
      testDir: './e2e/permissions',
      testMatch: '*.permission.spec.js',
      use: {
        ...baseUse,
        ...devices['Desktop Chrome'],
        storageState: USER_AUTH
      },
      dependencies: ['setup']
    }
  ]
})
