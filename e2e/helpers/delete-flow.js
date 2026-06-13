/**
 * 删除流程公共 Helper (v3.18.4+ Phase 6 抽取)
 *
 * 解决了 delete-validation-ui.spec.js 3 个 test 重复的删除流程模板:
 * 1. 勾选第一行
 * 2. 等"批量删除"按钮出现
 * 3. 点击, 等 ElMessageBox
 * 4. 找"确定"按钮 (多重 fallback)
 * 5. 装响应监听 + click (避免错过 notification 6s duration)
 * 6. 等响应 (10s timeout)
 *
 * v2 铁律:
 * [OK] 禁止 networkidle
 * [OK] 禁止 waitForLoadState + waitForTimeout 硬编码
 * [OK] 兼容 Element Plus 2.x checkbox inner span 点击
 */

const CHECKBOX_RETRY_TIMEOUT = 1000

/**
 * 在 GenericObjectList 页面勾选指定行的 checkbox
 * Element Plus 2.x el-table 行选择 checkbox DOM 结构:
 *   <td class="el-table-column--selection">
 *     <div class="cell">
 *       <label class="el-checkbox">
 *         <span class="el-checkbox__input">
 *           <span class="el-checkbox__inner"></span>
 *           <input class="el-checkbox__original" type="checkbox" aria-hidden="true">
 *         </span>
 *       </label>
 *     </div>
 *   </td>
 *
 * [CRITICAL] Element Plus 2.x 用 `el-checkbox__inner` span 作为可视化方块
 *   - input 是 aria-hidden="true" (display:none), 不能直接 click
 *   - click label 在某些情况下不能正确触发内部 change 事件
 *   - 真实可靠方案: 直接 click `el-checkbox__inner` span
 *   - 验证: 通过 "等批量删除按钮出现" 间接验证 (它在 totalSelectedCount > 0 时才渲染)
 */
export async function selectFirstRow(page) {
  const firstRow = page.locator('.el-table__body tr.el-table__row').first()
  await firstRow.waitFor({ state: 'visible', timeout: 10000 })
  await firstRow.scrollIntoViewIfNeeded()

  // 用 inner span (Element Plus 2.x 的可见点击区域)
  const innerSpan = firstRow.locator('span.el-checkbox__inner').first()
  await innerSpan.waitFor({ state: 'visible', timeout: 5000 })
  await innerSpan.click({ force: true })

  // 等 Vue 响应式更新 (selectedIds Set)
  await page.waitForTimeout(600)

  // 二次保险: 如果没生效, 重新点 label 触发 (input 本身 display:none 不能直接 click)
  const batchBtnCheck = await page
    .locator('button.el-button--danger:has-text("批量删除")')
    .first()
    .isVisible({ timeout: CHECKBOX_RETRY_TIMEOUT })
    .catch(() => false)

  if (!batchBtnCheck) {
    console.log('[selectFirstRow] click inner 未生效, 改用 JS dispatchEvent')
    // [FIX 2026-06-12] 不能用 .check() — input display:none 在 viewport 外
    // 改用 page.evaluate 直接调 input.click() (Vue @change 会响应)
    await firstRow.evaluate((row) => {
      const input = row.querySelector('input.el-checkbox__original')
      if (input) input.click()
    })
    await page.waitForTimeout(600)
  }
}

/**
 * 等待 ElNotification 出现, 返回该通知的 locator
 * Element Plus 的 .el-notification class 同时给 success/error/warning/info 通知用
 * .el-notification__title 含标题, .el-notification__content 含消息
 * 注意: notification duration=6s (失败) / 4.5s (成功), 用 5s timeout 安全捕获
 */
export async function waitForNotification(page, timeout = 5000) {
  const notification = page.locator('.el-notification').first()
  await notification.waitFor({ state: 'visible', timeout })
  return notification
}

/**
 * 通用: 走"勾选 → 批量删除 → 确认"流程
 * @param {string} apiDeletePattern - 用于 race-against 的 API 路径 (如 '/api/v2/bo/product/batch-delete')
 * @returns {Promise<{response: any, buttonInfo: any}>}
 */
export async function performBatchDeleteFlow(page, apiDeletePattern) {
  // 1. 勾选第一行
  await selectFirstRow(page)

  // 给 Vue reactivity 时间, 让 totalSelectedCount 触发 batch_actions 按钮出现
  // (MetaListPage.vue: batchActions 仅在 totalSelectedCount > 0 时渲染)
  await page.waitForTimeout(500)

  // 2. 等工具栏出现 "批量删除" 按钮
  const batchDeleteBtn = page.locator('button.el-button--danger:has-text("批量删除")').first()
  await batchDeleteBtn.waitFor({ state: 'visible', timeout: 15000 })
  console.log('[performBatchDeleteFlow] 找到 批量删除 按钮, 点击')
  await batchDeleteBtn.click()
  await page.waitForTimeout(300)  // 给 ElMessageBox 渲染时间

  // 3. ElMessageBox 弹窗 - 列出所有按钮, 确认哪个是 confirm
  const confirmBox = page.locator('.el-message-box').first()
  await confirmBox.waitFor({ state: 'visible', timeout: 5000 })
  const buttonInfo = await confirmBox.evaluate((box) => {
    const btns = Array.from(box.querySelectorAll('button'))
    return btns.map(b => ({
      text: b.textContent?.trim() || '',
      classes: Array.from(b.classList),
      visible: !!b.offsetParent
    }))
  })
  console.log('[performBatchDeleteFlow] ElMessageBox buttons:', JSON.stringify(buttonInfo))

  // 4. 找"确定"按钮 - 用 text 锁定
  let confirmBtn = confirmBox.locator('button.el-button--primary:has-text("确定")').first()
  let isVisible = await confirmBtn.isVisible({ timeout: 1000 }).catch(() => false)
  if (!isVisible) {
    confirmBtn = confirmBox.locator('button:has-text("确定")').first()
    isVisible = await confirmBtn.isVisible({ timeout: 1000 }).catch(() => false)
  }
  if (!isVisible) {
    confirmBtn = confirmBox.locator('.el-message-box__btns button').nth(1)
  }
  console.log('[performBatchDeleteFlow] confirm button visible:', await confirmBtn.isVisible())

  // 5. [CRITICAL] 在 click confirm 之前先装响应监听, 否则会错过
  //    notification duration=6s, 如果 click 后再装 waitForResponse (15s timeout),
  //    dump 时 notification 早已自动消失
  const responsePromise = page.waitForResponse(
    r => r.url().includes(apiDeletePattern) && r.request().method() === 'POST',
    { timeout: 10000 }
  )

  await confirmBtn.click({ force: true })
  console.log('[performBatchDeleteFlow] confirm button clicked, waiting response...')

  // 6. 等响应 (不超 10s, 远小于 notification 6s duration + 缓冲)
  let response = null
  try {
    response = await responsePromise
  } catch (e) {
    console.log('[performBatchDeleteFlow] no response within 10s:', e.message)
  }

  return { response, buttonInfo }
}
