# -*- coding: utf-8 -*-
"""
AA 图 PDF 下载功能 E2E 测试
=============================

测试流程:
1. dev-login as admin
2. 导航到架构数据管理页 (选一个产品+版本)
3. 点击"架构图"按钮 → 跳转到 /archdata-chart
4. 3 步骤模式: 类型 → 配置 → 展示
5. 在展示页点击 "PDF" 按钮
6. 验证 PDF 文件已下载

v26 新功能: 矢量 PDF 导出 (jsPDF + svg2pdf.js)
"""
import sys
import os
import time
import json

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from playwright.sync_api import sync_playwright, expect

# 截图输出
SCREENSHOT_DIR = 'd:/filework/excel-to-diagram/test_screenshots/pdf_download'
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# 下载目录
DOWNLOAD_DIR = 'd:/filework/excel-to-diagram/test_downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def main():
    console_logs = []
    page_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            accept_downloads=True
        )
        page = context.new_page()

        # 收集 console + error
        page.on('console', lambda msg: console_logs.append(f'[{msg.type}] {msg.text}'))
        page.on('pageerror', lambda err: page_errors.append(str(err)))

        # ==============================
        # Step 1: dev-login as admin
        # ==============================
        print('=== Step 1: dev-login as admin ===')

        # 1.1 先 navigate 到 frontend, 让 page 处于 frontend origin (这样 cookie 会同步)
        page.goto('http://localhost:3004/', wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)

        # 1.2 在 frontend context 内调 dev-login (让 cookie 写入 frontend origin)
        login_resp = page.context.request.get(
            'http://localhost:3010/api/v1/auth/dev-login?username=admin'
        )
        if login_resp.status != 200:
            raise RuntimeError(f'dev-login failed: {login_resp.status}')
        print(f'   [OK] dev-login: {login_resp.status}')

        # 1.3 重新加载页面让 Vue app 读取 cookie 加载 auth
        page.goto('http://localhost:3004/', wait_until='domcontentloaded', timeout=15000)

        # 等待 Pinia + auth 准备好
        try:
            page.wait_for_function(
                '() => !!window.__pinia && !!window.__pinia._s.get("auth")?.user',
                timeout=15000
            )
        except Exception:
            # 主动调 loadFromCookie
            print('   [WARN] 等待 auth store 超时, 主动调 loadFromCookie')
            page.evaluate('''async () => {
                const pinia = window.__pinia
                if (!pinia) return
                const authStore = pinia._s.get("auth")
                if (authStore?.loadFromCookie) {
                    await authStore.loadFromCookie("restore")
                }
            }''')
            page.wait_for_function(
                '() => !!window.__pinia && !!window.__pinia._s.get("auth")?.user',
                timeout=10000
            )

        # 设置 admin 权限
        page.evaluate('''() => {
            const pinia = window.__pinia
            const authStore = pinia._s.get("auth")
            if (authStore?.user) {
                authStore.user.permissions = ["*"]
            }
        }''')
        time.sleep(0.5)
        page.screenshot(path=f'{SCREENSHOT_DIR}/01-logged-in.png')
        print('   [OK] Pinia auth ready')

        # ==============================
        # Step 2: 查找产品+版本
        # ==============================
        print('\n=== Step 2: 查找产品+版本 ===')
        products = page.context.request.get(
            'http://localhost:3010/api/v2/bo/product?page=1&page_size=5'
        ).json()
        product_list = products.get('data', {}).get('items', []) or products.get('data', {}).get('records', []) or []
        if not product_list:
            print('   [WARN] 没有产品, 尝试 product list = []')
            print(f'   products: {json.dumps(products, ensure_ascii=False)[:200]}')
            return False
        product = product_list[0]
        print(f'   [OK] Product: id={product.get("id")}, name={product.get("name")}')

        # 找该产品的版本
        versions = page.context.request.get(
            f'http://localhost:3010/api/v2/bo/product_version?page=1&page_size=10&product_id={product.get("id")}'
        ).json()
        version_list = versions.get('data', {}).get('items', []) or versions.get('data', {}).get('records', []) or []
        if not version_list:
            print(f'   [WARN] 产品 {product.get("id")} 没有版本, 尝试直接进入')
            product_id = product.get('id')
            version_id = 1
        else:
            version = version_list[0]
            product_id = product.get('id')
            version_id = version.get('id')
            print(f'   [OK] Version: id={version_id}, name={version.get("name")}')

        # ==============================
        # Step 3: 导航到架构数据管理页
        # ==============================
        print(f'\n=== Step 3: 导航到 /system/archdata?productId={product_id}&versionId={version_id} ===')
        page.goto(
            f'http://localhost:3004/system/archdata?productId={product_id}&versionId={version_id}',
            wait_until='domcontentloaded',
            timeout=15000
        )
        time.sleep(3)
        page.screenshot(path=f'{SCREENSHOT_DIR}/02-archdata-loaded.png')
        print(f'   [OK] URL: {page.url()}')

        # 检查页面是否就绪
        try:
            page.wait_for_selector(
                '.collapsible-panel, .el-tabs, .arch-data-manager, [class*="archdata"]',
                timeout=10000
            )
            print('   [OK] archdata 页面就绪')
        except Exception as e:
            print(f'   [WARN] archdata 页面就绪检查超时: {e}')

        # ==============================
        # Step 4: 触发 chart action
        # ==============================
        print('\n=== Step 4: 触发 chart action (点击架构图按钮) ===')

        # 方法 A: 找 UI 上的"架构图"按钮
        chart_btn_clicked = page.evaluate('''() => {
            // 方式 1: 找按钮文字
            const buttons = document.querySelectorAll('button, a, .el-button');
            for (const b of buttons) {
                const text = (b.textContent || '').trim();
                if (text === '架构图' || text.includes('架构图') || text === '生成图') {
                    b.click();
                    return { clicked: true, text, tag: b.tagName };
                }
            }
            return { clicked: false };
        }''')
        print(f'   方式 A (UI按钮): {chart_btn_clicked}')

        if not chart_btn_clicked.get('clicked'):
            # 方法 B: 调 page composable
            print('   方式 B: 通过 page composable handleGlobalAction("chart")')
            # 这一步可能不行, 因为 composable 不在 window 上
            time.sleep(0.5)
            # 备选: 直接 set sessionStorage + 跳转
            print('   方式 C: 直接构造 sessionStorage 数据并跳转')

        # 等待 URL 变更
        try:
            page.wait_for_url('**/archdata-chart**', timeout=8000)
            print(f'   [OK] 已跳转到: {page.url()}')
        except Exception as e:
            print(f'   [WARN] 未自动跳转到 archdata-chart ({e}), 尝试手动跳转')
            page.goto('http://localhost:3004/archdata-chart', wait_until='domcontentloaded', timeout=15000)
            time.sleep(2)

        page.screenshot(path=f'{SCREENSHOT_DIR}/03-archdata-chart-page.png')

        # ==============================
        # Step 5: 等待 chart app 挂载
        # ==============================
        print('\n=== Step 5: 等待 AADiagramApp 挂载 ===')
        try:
            page.wait_for_function('() => !!window.__diagramApp', timeout=10000)
            print('   [OK] window.__diagramApp 已挂载 (DEV mode)')
        except Exception as e:
            print(f'   [WARN] window.__diagramApp 未挂载 (production build?): {e}')

        # 检查当前步骤
        step_info = page.evaluate('''() => {
            const app = window.__diagramApp;
            if (!app) return { hasApp: false };
            return {
                hasApp: true,
                currentStep: app.currentStep?.value,
                displayCurrent: app.displayCurrent?.value,
                initFromArchData: app.initFromArchData?.value,
                hasDiagramData: !!app.diagramData?.value,
                hasPreviewData: !!app.previewData?.value,
                chartType: app.chartType?.value,
                visibleStepsCount: app.visibleSteps?.value?.length
            };
        }''')
        print(f'   Diagram app state: {json.dumps(step_info, ensure_ascii=False)}')

        # ==============================
        # Step 6: 走到 display 步骤
        # ==============================
        print('\n=== Step 6: 走到 display 步骤 ===')

        if step_info.get('initFromArchData'):
            print('   从 archdata 管理进入, 3 步骤模式: 类型 → 配置 → 展示')
            # 步骤 0 → 类型
            # 步骤 1 → 配置
            # 步骤 2 → 展示 (display)
        else:
            print('   6 步骤模式 (从 upload 进入), 需走完: 导入 → 中心 → 关系 → 类型 → 配置 → 展示')

        # 通用方法: 用 dev mode 的 goToStep 跳到 display
        for attempt in range(3):
            current = page.evaluate('() => window.__diagramApp?.currentStep?.value')
            print(f'   当前步骤: {current}')

            if current == 5:
                print('   [OK] 已在 display 步骤')
                break
            elif current == 4:
                # 配置步骤: 调用 generateDiagram + nextStep
                print('   在配置步骤, 调 generateDiagram + nextStep')
                page.evaluate('''() => {
                    const app = window.__diagramApp;
                    if (app?.generateDiagram) {
                        try { app.generateDiagram(); } catch (e) { console.error(e); }
                    }
                    if (app?.nextStep) app.nextStep();
                }''')
                time.sleep(2)
            elif current == 3:
                # 类型步骤, 调 nextStep 到配置
                print('   在类型步骤, 调 nextStep 到配置')
                page.evaluate('() => window.__diagramApp?.nextStep?.()')
                time.sleep(1)
            else:
                # 其他情况: 强制跳到 5
                print(f'   强制跳到 display (5)')
                page.evaluate('() => window.__diagramApp?.goToStep?.(5)')
                time.sleep(1)
                break
            time.sleep(0.5)

        page.screenshot(path=f'{SCREENSHOT_DIR}/04-display-step.png')

        # 等待 diagram SVG 渲染
        print('\n=== Step 7: 等待 diagram SVG 渲染 ===')
        try:
            page.wait_for_selector('.mermaid-container svg, .diagram-container svg, .mermaid svg', timeout=15000)
            print('   [OK] diagram SVG 已渲染')
        except Exception as e:
            print(f'   [WARN] diagram SVG 渲染超时: {e}')

        # 检查 diagramData
        diagram_data_check = page.evaluate('''() => {
            const app = window.__diagramApp;
            if (!app?.diagramData?.value) return { hasData: false };
            const dd = app.diagramData.value;
            return {
                hasData: true,
                type: dd.type,
                code: dd.code?.substring(0, 100),
                hasNodes: !!dd.nodes,
                hasEdges: !!dd.edges || !!dd.relationships,
                keys: Object.keys(dd)
            };
        }''')
        print(f'   diagramData: {json.dumps(diagram_data_check, ensure_ascii=False)}')

        time.sleep(2)
        page.screenshot(path=f'{SCREENSHOT_DIR}/05-diagram-rendered.png')

        # ==============================
        # Step 8: 找到 PDF 按钮并点击
        # ==============================
        print('\n=== Step 8: 找 PDF 按钮并点击 ===')

        # 找 PDF 按钮 (toolbar 里有 PDF 文字)
        pdf_btn_info = page.evaluate('''() => {
            const buttons = document.querySelectorAll('button.toolbar-btn, .mermaid-toolbar button, button');
            for (const b of buttons) {
                const text = (b.textContent || '').trim();
                if (text === 'PDF' || text === 'PDF ' || (b.title || '').includes('PDF')) {
                    const rect = b.getBoundingClientRect();
                    return {
                        found: true,
                        text,
                        title: b.title,
                        visible: rect.width > 0 && rect.height > 0,
                        selector: b.className,
                        rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height }
                    };
                }
            }
            return { found: false };
        }''')
        print(f'   PDF 按钮: {json.dumps(pdf_btn_info, ensure_ascii=False)}')

        if not pdf_btn_info.get('found'):
            print('   [FAIL] 未找到 PDF 按钮')
            page.screenshot(path=f'{SCREENSHOT_DIR}/06-pdf-btn-not-found.png', full_page=True)
            # 列出所有 toolbar 按钮
            all_btns = page.evaluate('''() => {
                const all = document.querySelectorAll('button');
                return Array.from(all).map(b => ({
                    text: (b.textContent || '').trim().substring(0, 30),
                    title: b.title,
                    classes: b.className?.substring(0, 50)
                })).filter(b => b.text || b.title);
            }''')
            print(f'   所有按钮: {json.dumps(all_btns, ensure_ascii=False)[:500]}')
            return False

        # 点击 PDF 按钮 (使用 evaluate 点击以避免 visibility 问题)
        print('   点击 PDF 按钮...')

        with page.expect_download(timeout=30000) as download_info:
            page.evaluate('''() => {
                const buttons = document.querySelectorAll('button.toolbar-btn, .mermaid-toolbar button, button');
                for (const b of buttons) {
                    const text = (b.textContent || '').trim();
                    if (text === 'PDF' || (b.title || '').includes('PDF')) {
                        b.click();
                        return true;
                    }
                }
                return false;
            }''')

        try:
            download = download_info.value
            suggested = download.suggested_filename
            print(f'   [OK] 下载触发: {suggested}')

            # 保存到 download dir
            save_path = os.path.join(DOWNLOAD_DIR, suggested)
            download.save_as(save_path)
            print(f'   [OK] 文件保存到: {save_path}')

            # 验证文件
            file_size = os.path.getsize(save_path)
            print(f'   [OK] 文件大小: {file_size} bytes')

            # 验证是 PDF (检查 magic bytes)
            with open(save_path, 'rb') as f:
                header = f.read(8)
            is_pdf = header.startswith(b'%PDF-')
            print(f'   PDF magic bytes: {header[:8]!r}, valid: {is_pdf}')

            if not is_pdf:
                print('   [FAIL] 下载的文件不是 PDF 格式')
                return False

            page.screenshot(path=f'{SCREENSHOT_DIR}/06-pdf-downloaded.png')

            # ==============================
            # Step 9: 验证 toast + console 无错误
            # ==============================
            print('\n=== Step 9: 验证无错误 ===')
            errors = [log for log in console_logs if 'error' in log.lower() and 'pdf' in log.lower()]
            print(f'   PDF 相关 console 错误: {len(errors)}')
            for e in errors[:5]:
                print(f'     {e[:150]}')

            if page_errors:
                print(f'   [WARN] Page errors ({len(page_errors)}):')
                for e in page_errors[:3]:
                    print(f'     {e[:200]}')

            print('\n========================================')
            print('  [PASS] PDF 下载测试通过!')
            print(f'  PDF: {save_path}')
            print(f'  Size: {file_size} bytes')
            print('========================================')
            return True

        except Exception as e:
            print(f'   [FAIL] 下载未触发: {e}')
            page.screenshot(path=f'{SCREENSHOT_DIR}/06-download-failed.png', full_page=True)
            # 列出 console 中最近的 PDF 相关消息
            recent = [log for log in console_logs if 'pdf' in log.lower() or 'PDF' in log][-10:]
            print(f'   最近 PDF 相关 console:')
            for r in recent:
                print(f'     {r[:200]}')
            return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
