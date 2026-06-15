"""
枚举类型/枚举值 变更历史 E2E 测试闭环（修复版）

测试场景：
  1. 后端 API 验证：/api/v1/audit/logs 支持字符串 object_id（annotation_category）
  2. 前端验证：AnnotationCategory 详情页"变更历史"标签正常渲染（非空状态）

使用方式：
    python d:/filework/excel-to-diagram/test_helpers/scripts/test_enum_audit_logs_e2e.py
"""
import sys
import os
import time

sys.path.insert(0, 'd:/filework/excel-to-diagram')

import requests
from playwright.async_api import async_playwright

BASE_URL = 'http://localhost:3010/api/v1'
FRONTEND_URL = 'http://localhost:3004'
session = requests.Session()
session.headers.update({'Content-Type': 'application/json'})


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def auth_admin():
    try:
        resp = session.get(f'{BASE_URL}/auth/dev-login?username=admin')
        if resp.status_code == 200:
            log("  [OK] 管理员认证成功")
            return True
        log(f"  [FAIL] 认证失败: {resp.status_code}")
        return False
    except Exception as e:
        log(f"  [FAIL] 认证异常: {e}")
        return False


# ============================================================
# TC-1: 后端 API - 枚举类型审计日志查询
# ============================================================
def test_backend_api_enum_type():
    """TC-BE-001: 后端 /audit/logs 支持 object_type=enum_type&object_id=annotation_category"""
    log("")
    log("--- TC-BE-001: 后端 API - 枚举类型审计日志查询 ---")

    try:
        resp = session.get(
            f'{BASE_URL}/audit/logs',
            params={
                'page': 1,
                'page_size': 20,
                'object_type': 'enum_type',
                'object_id': 'annotation_category',
            }
        )
        log(f"  请求: GET /api/v1/audit/logs?object_type=enum_type&object_id=annotation_category")
        log(f"  响应: HTTP {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            items = data.get('data', [])
            total = data.get('total', 0)
            log(f"  [OK] 返回 {len(items)} 条日志，total={total}")

            for item in items[:3]:
                action = item.get('action', '')
                obj_type = item.get('object_type', '')
                obj_id = item.get('object_id', '')
                ts = item.get('created_at', '')[:19]
                log(f"    - [{ts}] {obj_type}#{obj_id} {action}")

            return True
        else:
            log(f"  [FAIL] HTTP {resp.status_code}: {resp.text[:200]}")
            return False

    except Exception as e:
        log(f"  [FAIL] 异常: {e}")
        return False


# ============================================================
# TC-2: 前端验证 - AnnotationCategory 详情页变更历史标签
# ============================================================
async def test_frontend_enum_type_detail_audit():
    """TC-FE-001: AnnotationCategory 详情页"变更历史"标签正常渲染"""
    log("")
    log("--- TC-FE-001: 前端 - 枚举类型详情页变更历史 ---")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        api_requests = []

        def on_request(request):
            url = request.url
            if 'localhost:3010' in url and ('audit' in url.lower() or 'log' in url.lower()):
                api_requests.append(f"{request.method} {url}")

        def on_response(response):
            url = response.url
            if 'localhost:3010' in url and ('audit' in url.lower() or 'log' in url.lower()):
                print(f"  → [{response.status}] {url[:120]}")

        page.on('request', on_request)
        page.on('response', on_response)

        try:
            # dev-login
            log("  设置认证 cookie...")
            await page.goto(f'{FRONTEND_URL}/')
            await page.evaluate(
                "fetch('http://localhost:3010/api/v1/auth/dev-login?username=admin', {credentials: 'include'})"
            )
            await page.goto(f'{FRONTEND_URL}/detail/enum_type/annotation_category')
            await page.wait_for_load_state('domcontentloaded')

            # 等待 Vue 渲染
            await page.wait_for_timeout(2000)

            # 点击"变更历史"标签
            log("  查找并点击'变更历史'标签...")
            tab_clicked = False
            for sel in [
                '.el-tabs__item:has-text("变更历史")',
                'text=变更历史',
                '[class*="tab-item"]:has-text("变更历史")',
            ]:
                tabs = page.locator(sel)
                count = await tabs.count()
                if count > 0:
                    for i in range(count):
                        tab = tabs.nth(i)
                        text = (await tab.text_content() or '').strip()
                        if '变更历史' in text:
                            await tab.click()
                            tab_clicked = True
                            log(f"  [OK] 点击: {text}")
                            break
                if tab_clicked:
                    break

            # 等待 AuditLog 加载
            await page.wait_for_timeout(3000)

            # 截图
            await page.screenshot(path='d:/filework/excel-to-diagram/test_enum_audit_fe.png')

            # 验证1: 不应该显示空状态消息
            empty_state = await page.locator('text=缺少 objectType').count()
            log(f"  空状态消息数量: {empty_state}")

            # 验证2: 应该存在 AuditLog 表格（.el-table）
            table_count = await page.locator('.el-table').count()
            log(f"  .el-table 数量: {table_count}")

            # 验证3: 检查是否有行数据（证明 API 返回了内容）
            rows = 0
            if table_count > 0:
                for i in range(table_count):
                    el = page.locator('.el-table').nth(i)
                    if await el.is_visible():
                        rows = await el.locator('tbody tr').count()
                        log(f"  表格[{i}] 行数: {rows}")

            # 验证4: 检查是否有 audit API 请求
            audit_reqs = [r for r in api_requests if 'audit' in r.lower()]
            log(f"  Audit API 请求数: {len(audit_reqs)}")
            for req in audit_reqs[:5]:
                print(f"    {req[:150]}")

            # 综合判定
            no_empty = empty_state == 0
            has_table = table_count > 0
            has_rows = rows > 0

            if no_empty and has_table:
                log(f"  [OK] 变更历史组件已渲染")
                if has_rows:
                    log(f"  [OK] 表格有 {rows} 行数据，API 正常返回")
                else:
                    log(f"  [INFO] 表格无数据（该枚举类型暂无变更历史，这是正常的）")
                return True
            elif no_empty and not has_table:
                log(f"  [WARN] 无空状态但也未找到表格，可能标签未切换")
                return False
            else:
                log(f"  [FAIL] 显示了空状态消息，说明 objectId 判断仍然失败")
                return False

        finally:
            await browser.close()


# ============================================================
# 主函数
# ============================================================
async def main():
    print("=" * 60)
    print("枚举类型/枚举值 变更历史 E2E 测试")
    print("=" * 60)

    if not auth_admin():
        log("认证失败，测试中止")
        return

    # 后端 API 验证
    results = {
        'TC-BE-001': test_backend_api_enum_type(),
    }

    # 前端验证
    try:
        results['TC-FE-001'] = await test_frontend_enum_type_detail_audit()
    except Exception as e:
        import traceback
        log(f"  [FAIL] 前端测试异常: {e}")
        traceback.print_exc()
        results['TC-FE-001'] = False

    # 汇总
    print("")
    print("=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for tc, passed in results.items():
        symbol = "[OK]" if passed else "[FAIL]"
        status = "PASS" if passed else "FAIL"
        log(f"  {symbol} {tc}: {status}")

    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    log(f"")
    log(f"  通过率: {passed_count}/{total_count}")

    if passed_count == total_count:
        log(f"  所有测试通过！变更历史功能已修复。")
    else:
        log(f"  存在失败项，请检查上述日志。")
    print("=" * 60)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
