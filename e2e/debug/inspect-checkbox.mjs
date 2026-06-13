/**
 * 模拟 C01 完整流程 + 抓网络响应, 确认后端是否真的返回了 restrict_on 错误
 */
import { chromium } from '@playwright/test'
import { readFileSync } from 'fs'

const authState = JSON.parse(
  readFileSync('./e2e/.auth/admin.json', 'utf-8')
)

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({
    storageState: authState,
    viewport: { width: 1280, height: 720 }
  })
  const page = await context.newPage()
  page.on('console', msg => {
    if (msg.type() === 'error' || msg.type() === 'log') {
      console.log(`[browser ${msg.type()}]`, msg.text().substring(0, 300))
    }
  })

  // 抓 batch-delete 的网络响应
  page.on('response', async resp => {
    if (resp.url().includes('batch-delete')) {
      const status = resp.status()
      let body = ''
      try { body = await resp.text() } catch {}
      console.log(`\n=== NETWORK: ${resp.request().method()} ${resp.url()} status=${status} ===`)
      console.log(body.substring(0, 800))
      console.log('=== /NETWORK ===\n')
    }
  })

  await page.goto('http://localhost:3004/product-management', { waitUntil: 'domcontentloaded' })
  await page.locator('.el-table__body tr.el-table__row').first().waitFor({ state: 'visible', timeout: 15000 })
  await page.waitForTimeout(2000)

  // search
  const search = page.locator('input[placeholder*="搜索"], input[placeholder*="名称"], input[placeholder*="编码"]').first()
  const firstRowText = await page.locator('.el-table__body tr.el-table__row').first().evaluate(el => {
    const nameCell = el.querySelector('td:nth-child(2)') || el.querySelectorAll('td')[1]
    return nameCell?.innerText?.trim() || ''
  })
  console.log('searching for:', firstRowText)
  await search.fill('')
  await search.fill(firstRowText)
  await search.press('Enter')
  await page.locator('.el-table__body tr.el-table__row').first().waitFor({ state: 'visible', timeout: 10000 })
  await page.waitForTimeout(1500)

  // 选第一行
  const firstRow = page.locator('.el-table__body tr.el-table__row').first()
  await firstRow.locator('label.el-checkbox').first().click({ force: true })
  await page.waitForTimeout(500)

  // 点批量删除
  const batchDeleteBtn = page.locator('button.el-button--danger:has-text("批量删除")').first()
  await batchDeleteBtn.waitFor({ state: 'visible', timeout: 5000 })
  await batchDeleteBtn.click()
  await page.waitForTimeout(500)

  // 确认弹窗
  const confirmBox = page.locator('.el-message-box').first()
  await confirmBox.waitFor({ state: 'visible', timeout: 5000 })
  const confirmBtn = confirmBox.locator('.el-button--primary, .el-message-box__btns button').first()
  await confirmBtn.click()
  console.log('confirmed batch delete')

  // 等 3s 看通知
  await page.waitForTimeout(3000)

  // 截图
  await page.screenshot({ path: 'd:/filework/excel-to-diagram/e2e/screenshots/c01-after-delete.png', fullPage: false })

  // 找通知
  const notifCount = await page.locator('.el-notification').count()
  console.log('notification count:', notifCount)
  if (notifCount > 0) {
    const html = await page.locator('.el-notification').first().evaluate(el => el.outerHTML.substring(0, 500))
    console.log('notification HTML:', html)
  }

  await browser.close()
})().catch(e => { console.error(e); process.exit(1) })
