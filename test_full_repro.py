"""
完整复现 TEST60 的体验 - 把 3 个菜单都点一遍
"""
from playwright.sync_api import sync_playwright

FRONTEND = "http://localhost:3004"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1920, 'height': 1080})
    page = context.new_page()
    
    # Capture all errors and 4xx/5xx
    errors = []
    page.on('response', lambda r: 
        errors.append((r.status, r.url)) if r.status >= 400 and 'users/me' not in r.url else None
    )
    
    # Step 1: Login as TEST60
    print("=" * 70)
    print("TEST60 完整复现测试")
    print("=" * 70)
    page.goto(FRONTEND, wait_until='domcontentloaded', timeout=15000)
    page.wait_for_timeout(1000)
    page.evaluate("""async () => {
        await fetch('/api/v1/auth/dev-login?username=TEST60', {credentials: 'include'});
    }""")
    print("[1] Login OK")
    
    # Step 2: Go to dashboard (fresh, no cache)
    print("\n[2] Navigate to dashboard...")
    page.goto(f"{FRONTEND}/", wait_until='networkidle', timeout=20000)
    page.wait_for_timeout(3000)
    page.screenshot(path='test_step1_dashboard.png')
    print(f"  Screenshot saved")
    
    # Step 3: Click on each quick app tile and check what loads
    print("\n[3] Click each quick app tile...")
    tiles = page.locator('.app-tile')
    count = tiles.count()
    print(f"  Found {count} quick app tiles")
    
    for i in range(count):
        tile = tiles.nth(i)
        name = tile.text_content().strip().split('\n')[0] if tile.text_content() else 'unknown'
        print(f"\n  --- Tile {i}: {name} ---")
        errors.clear()
        tile.click()
        page.wait_for_timeout(2500)
        url = page.url
        print(f"    URL after click: {url}")
        
        # Check main content
        main_text = page.evaluate("""() => {
            const main = document.querySelector('main, .main-content, [class*="main"]');
            return main ? main.textContent.replace(/\\s+/g, ' ').trim().slice(0, 200) : 'no main';
        }""")
        print(f"    Content: {main_text[:200]}")
        print(f"    HTTP errors: {len(errors)}")
        for s, u in errors[:3]:
            print(f"      [{s}] {u}")
        
        # Screenshot
        page.screenshot(path=f'test_tile_{i}.png')
        
        # Go back to dashboard
        page.goto(f"{FRONTEND}/", wait_until='networkidle', timeout=20000)
        page.wait_for_timeout(2000)
    
    # Step 4: Click hamburger to verify sidebar
    print("\n[4] Sidebar check...")
    items = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('.nav-item, [class*="nav-item"]'))
            .map(e => e.textContent.trim());
    }""")
    print(f"  Sidebar items: {items}")
    
    browser.close()
print("\nDone.")
