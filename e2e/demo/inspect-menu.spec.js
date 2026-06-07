import { test, expect } from '@playwright/test'

test('inspect menu structure', async ({ page }, testInfo) => {
  await page.goto('http://localhost:3004/', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(3000)

  // Dump all menu-related elements
  const menus = await page.evaluate(() => {
    const result = {}
    // 1. All clickable elements with text
    const allClickable = document.querySelectorAll('a, [role="menuitem"], [class*="menu"] > *, [class*="nav"] > *, [class*="side"] *')
    const texts = []
    allClickable.forEach(el => {
      const text = el.textContent?.trim()
      if (text && text.length < 30 && text.length > 1) {
        texts.push({
          tag: el.tagName,
          cls: el.className?.toString().substring(0, 60),
          text
        })
      }
    })
    result.clickables = texts.slice(0, 30)
    return result
  })

  console.log('=== CLICKABLE ELEMENTS ===')
  menus.clickables.forEach(c => console.log(`${c.tag} [${c.cls}] -> ${c.text}`))
})
