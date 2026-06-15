"""
Verify: TEST60 navigates to /product-management - no 403 console error
"""
from playwright.sync_api import sync_playwright

FRONTEND = "http://localhost:3004"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1920, 'height': 1080})
    
    errors = []
    page.on('response', lambda r: 
        errors.append((r.status, r.url)) if r.status >= 400 and 'users/me' not in r.url else None
    )
    page.on('console', lambda msg: 
        errors.append(f"[{msg.type}] {msg.text[:200]}") if msg.type == 'error' and 'useMetaList' in msg.text else None
    )
    
    # Login
    page.goto(FRONTEND, wait_until='domcontentloaded', timeout=15000)
    page.wait_for_timeout(1000)
    page.evaluate("""async () => {
        await fetch('/api/v1/auth/dev-login?username=TEST60', {credentials: 'include'});
    }""")
    
    # Navigate to product-management
    print("Navigate to /product-management...")
    page.goto(f"{FRONTEND}/product-management", wait_until='networkidle', timeout=20000)
    page.wait_for_timeout(4000)
    page.screenshot(path='test_after_fix.png', full_page=True)
    
    print(f"\nCritical errors: {len(errors)}")
    for e in errors:
        print(f"  {e}")
    
    # Check the page content
    text = page.evaluate("""() => document.body.textContent.replace(/\\s+/g, ' ').trim().slice(0, 400)""")
    print(f"\nPage text: {text[:400]}")
    
    browser.close()

if errors:
    print("\n[FAIL] Still has errors")
    exit(1)
print("\n[PASS] No 403 console errors")
