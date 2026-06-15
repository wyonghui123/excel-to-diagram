"""检查架构数据管理页统计数字显示"""
from playwright.sync_api import sync_playwright
import time

def check_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        
        # 访问页面
        page.goto('http://localhost:3005/', wait_until='networkidle')
        time.sleep(2)
        
        # 截图
        page.screenshot(path='d:/filework/excel-to-diagram/screenshot_1.png', full_page=True)
        
        # 查找所有 badge 元素
        badges = page.locator('.collapsible-panel__badge').all()
        print(f"找到 {len(badges)} 个 badge 元素")
        
        for i, badge in enumerate(badges):
            text = badge.inner_text()
            print(f"Badge {i+1}: {text}")
        
        # 查找过滤条件相关的元素
        filter_badge = page.locator('.filter-badge-text').first
        if filter_badge.is_visible():
            print(f"过滤条件 badge: {filter_badge.inner_text()}")
        
        browser.close()

if __name__ == '__main__':
    check_page()
