"""
TEST60 端到端验证闭环脚本 v1.0.4
====================================
分两个流程:
  A) admin 视角: 配 TEST60 角色的 version 权限 (先确保有，再取消)
  B) TEST60 视角: 登录, 验证菜单, 验证 API 行为

简化原则: 不再模拟复杂 UI, 直接用 API + DB 验证
"""
import os
import sys
import json
import sqlite3
import asyncio
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar
from pathlib import Path
from playwright.async_api import async_playwright

BASE_DIR = Path(r"d:\filework\excel-to-diagram")
DB_PATH = BASE_DIR / "meta" / "architecture.db"
FRONTEND_URL = "http://localhost:3004"
BACKEND_URL = "http://localhost:3010"
SHOT_DIR = BASE_DIR / "logs" / "e2e_shots" / "test60_v104"
SHOT_DIR.mkdir(parents=True, exist_ok=True)


def log(msg, level="INFO"):
    import datetime
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] [{level}] {msg}", flush=True)


def make_opener(cookies=None):
    cookie_jar = http.cookiejar.CookieJar()
    if cookies:
        for k, v in cookies.items():
            ck = http.cookiejar.Cookie(
                version=0, name=k, value=v, port=None, port_specified=False,
                domain="localhost", domain_specified=True, domain_initial_dot=False,
                path="/", path_specified=True, secure=False, expires=None,
                discard=True, comment=None, comment_url=None, rest={}, rfc2109=False,
            )
            cookie_jar.set_cookie(ck)
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def dev_login(username, password):
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    qs = urllib.parse.urlencode({"username": username, "password": password})
    url = f"{BACKEND_URL}/api/v1/auth/dev-login?{qs}"
    req = urllib.request.Request(url, method="GET")
    try:
        with opener.open(req, timeout=10) as resp:
            body = resp.read().decode()
            cookies = {c.name: c.value for c in cookie_jar}
            return resp.status, body, cookies, opener
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        cookies = {c.name: c.value for c in cookie_jar}
        return e.code, body, cookies, opener


def check_db_state():
    log("=" * 60)
    log("STEP 1: DB 状态检查")
    log("=" * 60)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, code, name FROM roles WHERE code='TEST60'")
    role = cur.fetchone()
    if not role:
        log("❌ TEST60 角色不存在", "ERROR")
        conn.close()
        return None
    role_id = role['id']
    log(f"TEST60 role: id={role_id}, code={role['code']}, name={role['name']}")

    cur.execute("""
        SELECT p.code FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
        WHERE rp.role_id = ?
        ORDER BY p.code
    """, (role_id,))
    perms = [r['code'] for r in cur.fetchall()]
    log(f"TEST60 权限 (共 {len(perms)}): {perms}")
    version_perms = [p for p in perms if 'version' in p]
    product_perms = [p for p in perms if 'product' in p]
    log(f"  version 权限: {version_perms}")
    log(f"  product 权限: {product_perms}")

    cur.execute("""
        SELECT dimension_code, dimension_values, scope_mode, bo_id
        FROM role_dimension_scopes
        WHERE role_id = ?
    """, (role_id,))
    scopes = cur.fetchall()
    for s in scopes:
        log(f"  scope: dim={s['dimension_code']}, values={s['dimension_values']}, mode={s['scope_mode']}, bo_id={s['bo_id']}")

    cur.execute("""
        SELECT m.menu_code, m.menu_name, m.menu_path, m.page_type
        FROM role_menu_permissions rmp
        JOIN menus m ON m.menu_code = rmp.menu_code
        WHERE rmp.role_id = ?
        ORDER BY m.sort_order
    """, (role_id,))
    menus = cur.fetchall()
    log(f"TEST60 关联菜单 (共 {len(menus)}):")
    for m in menus:
        log(f"  - {m['menu_code']:30s} {m['menu_name']:20s} path={m['menu_path']} page_type={m['page_type']}")

    conn.close()
    return {
        'role_id': role_id,
        'perms': perms,
        'version_perms': version_perms,
        'product_perms': product_perms,
        'scopes': [dict(s) for s in scopes],
        'menus': [dict(m) for m in menus],
    }


async def test60_login_view():
    """用 Playwright 登录 TEST60, 验证菜单"""
    log("=" * 60)
    log("STEP 2: Playwright 登录 TEST60 查看实际菜单")
    log("=" * 60)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
        )
        page = await context.new_page()

        # 监听 API
        api_log = []
        async def on_response(response):
            if '/api/' in response.url:
                try:
                    body = await response.text()
                except Exception:
                    body = '<binary>'
                api_log.append({
                    'method': response.request.method,
                    'url': response.url,
                    'status': response.status,
                    'body': body[:300],
                })

        async def on_console(msg):
            if msg.type in ('error', 'warning'):
                text = msg.text[:200]
                if 'Vue Router warn' not in text and 'transition' not in text and 'keep-alive' not in text:
                    log(f"  [console.{msg.type}] {text}")

        page.on("response", on_response)
        page.on("console", on_console)

        # 打开登录页 / dev-login
        log("打开 dev-login 拿 TEST60 cookie...")
        await page.goto(f"{BACKEND_URL}/api/v1/auth/dev-login?username=TEST60&password=TEST60", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(1000)
        # 拿 cookie 注入
        cookies_list = await context.cookies()
        log(f"  拿到 {len(cookies_list)} 个 cookie")
        for c in cookies_list:
            log(f"    - {c['name']}={c['value'][:30]}... (domain={c.get('domain')})")

        # 打开首页
        log("打开 frontend 首页...")
        await page.goto(f"{FRONTEND_URL}/", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(SHOT_DIR / "01_test60_home.png"), full_page=True)

        # 实际 URL
        log(f"  当前 URL: {page.url}")

        # 取页面所有菜单项 (侧边栏)
        log("查找侧边栏菜单项...")
        menu_items = await page.evaluate("""
() => {
  // 尝试找侧边栏菜单
  const selectors = [
    '.el-menu-item',
    '.sidebar-menu .menu-item',
    'nav a',
    'aside a',
    '.menu-item',
    '[class*="menu"] a',
    '[class*="Menu"] a',
  ];
  let results = [];
  for (const sel of selectors) {
    const els = document.querySelectorAll(sel);
    for (const e of els) {
      const text = e.textContent?.trim();
      if (text && text.length < 50) {
        results.push({selector: sel, text: text, href: e.href || e.getAttribute('href') || ''});
      }
    }
  }
  return results;
}
        """)
        log(f"  找到 {len(menu_items)} 个菜单元素:")
        for mi in menu_items[:30]:
            log(f"    [{mi['selector']}] {mi['text']!r} -> {mi['href']}")

        # 抓取 /api/v1/users/menus 或类似 endpoint
        log("检查 /api/v1/users/me 和菜单 API 调用:")
        for r in api_log:
            if 'menus' in r['url'] or 'me' in r['url'] or 'menu' in r['url']:
                log(f"  {r['method']} {r['url'][:80]} -> {r['status']}")
                if 'menus' in r['url']:
                    log(f"    body: {r['body'][:500]}")

        # 试着点进产品版本管理
        log("尝试访问 /product-management 路径...")
        await page.goto(f"{FRONTEND_URL}/product-management", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(SHOT_DIR / "02_test60_product_management.png"), full_page=True)
        log(f"  URL: {page.url}")
        # 检查页面是否报错
        body_text = await page.text_content("body")
        if "403" in body_text or "forbidden" in body_text.lower():
            log(f"  ⚠ 页面含 403/forbidden", "WARN")
        else:
            log(f"  ✓ 页面正常 (前 200 字: {body_text[:200]})")

        # 访问 /api/v2/bo/product
        log("直接测 /api/v2/bo/product...")
        resp = await page.request.get(f"{BACKEND_URL}/api/v2/bo/product?page=1&page_size=20")
        log(f"  /api/v2/bo/product -> {resp.status}")
        if resp.status == 200:
            body = await resp.text()
            log(f"  body[:300]: {body[:300]}")
        else:
            log(f"  body: {await resp.text()[:200]}")

        # 测 /api/v2/bo/version
        log("直接测 /api/v2/bo/version...")
        resp = await page.request.get(f"{BACKEND_URL}/api/v2/bo/version?page=1&page_size=10")
        log(f"  /api/v2/bo/version -> {resp.status}")
        log(f"  body: {await resp.text()[:200]}")

        await browser.close()


async def admin_config_version_perm():
    """admin 登录, 通过 API 端点给 TEST60 加/减 version 权限"""
    log("=" * 60)
    log("STEP 3: admin 端通过 API 配置 TEST60 version 权限")
    log("=" * 60)

    # admin 登录
    status, body, cookies, opener = dev_login("admin", "admin")
    log(f"admin 登录: {status}, cookies: {list(cookies.keys())}")
    if status != 200:
        return None

    # 看菜单权限端点
    log("查找菜单权限端点...")
    # 标准路径: PUT /api/v1/roles/{role_id}/menu-permissions
    # 先 GET 看下结构
    role_id = 1803
    get_url = f"{BACKEND_URL}/api/v1/roles/{role_id}/menu-permissions"
    try:
        with opener.open(get_url, timeout=10) as resp:
            log(f"  GET {get_url} -> {resp.status}")
            body = resp.read().decode()
            log(f"  body[:500]: {body[:500]}")
    except urllib.error.HTTPError as e:
        log(f"  GET failed: {e.code} {e.reason}", "WARN")
        log(f"  body: {e.read().decode()[:300]}", "WARN")


async def main():
    log("=" * 60)
    log("TEST60 端到端验证闭环 v1.0.4")
    log("=" * 60)

    # Step 1
    state = check_db_state()
    if not state:
        return 1

    # Step 2: TEST60 登录实际看
    await test60_login_view()

    # Step 3: admin 配置
    await admin_config_version_perm()

    return 0


if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc)
