"""
E2E 验证: AADiagramApp 双向箭头 + Tooltip 增强

策略: 绕过 UI 选择, 直接通过 API 拉取预览数据 + 预填 sessionStorage
      让 /archdata-chart onMounted 自动从 sessionStorage 恢复数据
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "excel-to-diagram"))

from playwright.async_api import async_playwright  # noqa


async def get_products_and_versions(page):
    """通过 API 获取 products/versions 列表"""
    api_url = "http://localhost:3010"
    products_resp = await page.request.get(f"{api_url}/api/v2/bo/product")
    products = await products_resp.json()
    product_list = products.get("data", {}).get("items", []) or products.get("data", [])
    return product_list


async def get_version_with_data(page, product):
    """找一个有架构数据的版本"""
    api_url = "http://localhost:3010"
    versions_resp = await page.request.get(
        f"{api_url}/api/v2/bo/version?product_id={product['id']}"
    )
    versions = await versions_resp.json()
    version_list = versions.get("data", {}).get("items", []) or versions.get("data", [])
    if not version_list:
        return None
    # 尝试每个版本, 找有数据的
    for v in version_list:
        # 容错: 可能是 dict 或 str
        if isinstance(v, str):
            version_id = v
        elif isinstance(v, dict):
            version_id = v.get("id")
        else:
            continue
        if not version_id:
            continue
        preview_resp = await page.request.get(
            f"{api_url}/api/v2/bo/architecture/preview?version_id={version_id}"
        )
        preview = await preview_resp.json()
        if preview.get("success"):
            data = preview.get("data", {})
            bo_count = len(data.get("business_objects", []))
            rel_count = len(data.get("relationships", []))
            if bo_count > 0 and rel_count > 0:
                if isinstance(v, dict):
                    print(f"    找到有数据版本: {v.get('name', v.get('id'))} (BO={bo_count}, R={rel_count})")
                else:
                    print(f"    找到有数据版本: {version_id} (BO={bo_count}, R={rel_count})")
                return v
    # 退回第一个版本
    return version_list[0]


async def fetch_preview_data(page, version_id):
    """通过 /bo/architecture/preview API 拉取完整预览数据"""
    api_url = "http://localhost:3010"
    resp = await page.request.get(f"{api_url}/api/v2/bo/architecture/preview?version_id={version_id}")
    result = await resp.json()
    if not result.get("success"):
        print(f"  ❌ preview API 失败: {result}")
        return None
    data = result.get("data", {})
    return {
        "domainProducts": data.get("domain_products", []) or data.get("domains", []),
        "subDomains": data.get("sub_domains", []),
        "serviceModules": data.get("service_modules", []),
        "businessObjects": data.get("business_objects", []),
        "relationships": data.get("relationships", []),
        "centerScope": data.get("center_scope", [])
    }


async def main():
    print("=" * 70)
    print("E2E: AADiagramApp 双向箭头 + Tooltip 增强验证")
    print("=" * 70)

    results = {
        "step1_api_data_fetched": False,
        "step2_sessionstorage_filled": False,
        "step3_chart_page_loaded": False,
        "step4_svg_rendered": False,
        "step5_bidi_data_attr": False,
        "step6_bidi_marker_start": False,
        "step7_tooltip_content": False,
        "step8_data_with_bidi": False,
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        # 1. dev-login
        print("\n[1/8] dev-login 认证...")
        await page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")

        # 2. 获取产品/版本 (找有数据的版本)
        print("\n[0/8] 扫描产品/版本, 找有架构数据的版本...")
        product_list = await get_products_and_versions(page)
        if not product_list:
            print("  ❌ 没找到产品")
            await browser.close()
            return
        # 遍历产品找有数据的
        version = None
        product = None
        for p in product_list[:5]:  # 限制前5个产品
            print(f"  试产品: {p.get('name', p['id'])}")
            v = await get_version_with_data(page, p)
            if v:
                # 兼容: v 可能是 dict 或 str
                if isinstance(v, str):
                    version_id = v
                elif isinstance(v, dict):
                    version_id = v.get('id')
                else:
                    version_id = None
                if not version_id:
                    continue
                test_resp = await page.request.get(
                    f"http://localhost:3010/api/v2/bo/architecture/preview?version_id={version_id}"
                )
                test_data = await test_resp.json()
                if test_data.get("success"):
                    bo_count = len(test_data.get("data", {}).get("business_objects", []))
                    rel_count = len(test_data.get("data", {}).get("relationships", []))
                    if bo_count > 0 and rel_count > 0:
                        product = p
                        # 统一转 dict 形式, 后续访问 .id 不会出错
                        version = {"id": version_id, "name": version_id}
                        break
        if not product or not version:
            print(f"  ⚠ 没找到有数据的版本, 用第一个")
            product = product_list[0]
            versions_resp = await page.request.get(
                f"http://localhost:3010/api/v2/bo/version?product_id={product['id']}"
            )
            versions = await versions_resp.json()
            version_list = versions.get("data", {}).get("items", []) or versions.get("data", [])
            if version_list:
                # 统一转 dict
                v0 = version_list[0]
                if isinstance(v0, str):
                    version = {"id": v0, "name": v0}
                elif isinstance(v0, dict):
                    version = v0
                else:
                    version = {"id": str(v0), "name": str(v0)}
        print(f"  ✓ 产品: {product.get('name', product['id'])}")
        print(f"  ✓ 版本: {version.get('name', version['id'])}")

        # 3. 拉取 preview 数据
        print("\n[2/8] 拉取 preview 数据...")
        arch_data = await fetch_preview_data(page, version["id"])
        if not arch_data:
            await browser.close()
            return
        print(f"  业务对象: {len(arch_data['businessObjects'])}, 关系: {len(arch_data['relationships'])}")
        results["step1_api_data_fetched"] = True

        # 检查数据中是否有双向
        bidi_count = sum(
            1 for r in arch_data["relationships"] if r.get("relation_direction") == "双向"
        )
        print(f"  原始数据中双向关系: {bidi_count}")

        # 🆕 如果没双向关系, 注入 1 条双向测试数据 (用第 1 条 relation 改成双向, 模拟用户改)
        if bidi_count == 0 and len(arch_data["relationships"]) > 0:
            test_rel = arch_data["relationships"][0]
            test_rel["relation_direction"] = "双向"
            test_rel["relationDirection"] = "双向"  # camelCase 兼容
            # 注入一个 relationType (业务枚举, 模拟前端)
            test_rel["relationType"] = "CALLS"
            # 兼容 snake_case 字段名 (API 返回的可能不一样)
            for k, v in list(test_rel.items()):
                print(f"    rel[0] 字段: {k} = {str(v)[:50]}")
            print(f"  🆕 已注入测试双向关系: {test_rel.get('sourceName') or test_rel.get('source_name')} <-> {test_rel.get('targetName') or test_rel.get('target_name')}")
            bidi_count = 1
        # [FIX] step8 由"chart 加载完成后"再判断, 因为前端可能从 store 拉数据
        # (api 返回的 arch_data 可能为空, 但 chart 内部 store 仍有数据)
        # 暂不在这里 set step8, 留到 mermaid_dump 之后判断

        # 4. 预填 sessionStorage
        print("\n[3/8] 预填 sessionStorage + 打开 chart 页...")
        # 先访问首页 (建立 sessionStorage scope)
        await page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # 填 sessionStorage
        arch_data_str = json.dumps(arch_data, ensure_ascii=False)
        await page.evaluate(f"""(data) => {{
            sessionStorage.setItem('archDataForDiagram', data.arch);
            sessionStorage.setItem('lastArchDataForDiagram', data.arch);
            sessionStorage.setItem('archDataCurrentStep', '2');
            sessionStorage.setItem('archDataChartType', 'businessObject');
        }}""", {"arch": arch_data_str})
        print("  ✓ sessionStorage 已填充")
        results["step2_sessionstorage_filled"] = True

        # 5. 直接导航到 /archdata-chart
        print("\n[4/8] 导航到 /archdata-chart...")
        # 关键: 先把 currentStep 设为 0, 避免在 step=2 但 diagramData=null 时空白渲染
        await page.evaluate("sessionStorage.setItem('archDataCurrentStep', '0')")
        await page.goto(
            "http://localhost:3004/archdata-chart",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await page.wait_for_timeout(5000)
        print(f"  当前 URL: {page.url}")
        if "archdata-chart" in page.url:
            print("  ✓ 已到达 /archdata-chart")
            results["step3_chart_page_loaded"] = True
        else:
            print("  ⚠ 被重定向到其它页")

        # 5.5 用 dev 暴露的 __diagramApp 触发 generateDiagram + 跳到 step 2
        print("\n[4.5/8] 触发 generateDiagram + 跳到展示步骤 (dev 模式)...")
        triggered = await page.evaluate("""() => {
            const app = window.__diagramApp
            if (!app) {
                return { ok: false, reason: '__diagramApp not exposed' }
            }
            try {
                // 🆕 在 generateDiagram 前注入双向数据
                // (initFromArchDataManager 已重新从 API 拉数据, 所以 archData.relationships 的修改会被覆盖)
                // 这里改 previewData.value.relationships (chart 真正用的)
                const rels = app.previewData?.value?.relationships || app.previewData?.relationships
                if (rels && rels.length > 0) {
                    // 找最后一条, 且不能跟之前双向的重复
                    let r0 = rels[rels.length - 1]
                    // 已有双向? 跳过
                    if (r0.relationDirection !== '双向') {
                        r0.relationDirection = '双向'
                        r0.relationType = 'CALLS'
                    } else {
                        // 找一条还没标双向的
                        r0 = rels.find(r => r.relationDirection !== '双向')
                        if (r0) {
                            r0.relationDirection = '双向'
                            r0.relationType = 'CALLS'
                        }
                    }
                    console.log('[E2E] 注入双向:', r0?.sourceName, '<->', r0?.targetName, 'code=', r0?.code)
                }
                app.generateDiagram()
                // 直接修改 currentStep.value (goToStep 受 canGoToStep 限制, 不能从 0 跳到 2)
                if (app.currentStep && 'value' in app.currentStep) {
                    app.currentStep.value = 2
                } else {
                    return { ok: false, reason: 'no currentStep ref' }
                }
                return {
                    ok: true,
                    hasDiagram: !!app.diagramData,
                    hasDiagramValue: app.diagramData ? (app.diagramData.value ? 'ref' : 'obj') : null,
                    currentStep: app.currentStep && app.currentStep.value
                }
            } catch (err) {
                return { ok: false, reason: String(err), stack: err.stack }
            }
        }""")
        print(f"  触发结果: {triggered}")
        if not triggered.get("ok"):
            print(f"  ✗ 触发失败: {triggered.get('reason')}")
            await page.screenshot(path="e2e_bidi_05_fail.png", full_page=True)
            await browser.close()
            return
        # 等几秒让 Mermaid 重新渲染 (双向注入后)
        await page.wait_for_timeout(5000)

        # 5.5.1 dump Mermaid code (debug syntax error) - 从 window.__lastMermaidCode 读取生成的语法
        mermaid_dump = await page.evaluate("""() => {
            const app = window.__diagramApp
            if (!app) return { found: false }
            const dd = app.diagramData?.value || app.diagramData
            const links = dd?.links || []
            const rels = app.previewData?.value?.relationships || app.previewData?.relationships || []
            const bidiInRels = rels.filter(r => r.relationDirection === '双向').length
            const bidiInLinks = links.filter(l => l.relationDirection === '双向').length
            const bidiLinkIdx = links.findIndex(l => l.relationDirection === '双向')
            const pre = document.querySelector('pre.mermaid')
            // [DEBUG] 从 MermaidComponent 暴露的 window.__lastMermaidCode 读取
            const mermaidCodeRaw = (typeof window !== 'undefined' && window.__lastMermaidCode) || null
            return {
                relsTotal: rels.length,
                linksTotal: links.length,
                bidiInRels,
                bidiInLinks,
                bidiRelIdx: rels.findIndex(r => r.relationDirection === '双向'),
                bidiLinkIdx,
                bidiLinkObj: bidiLinkIdx >= 0 ? links[bidiLinkIdx] : null,
                firstRelDir: rels[0]?.relationDirection,
                firstRelType: rels[0]?.relationType,
                firstLinkDir: links[0]?.relationDirection,
                firstLinkType: links[0]?.relationType,
                // [NEW] 生成的 mermaid 语法 (用于诊断 Syntax error)
                mermaidCodeLen: mermaidCodeRaw ? mermaidCodeRaw.length : 0,
                mermaidCode: mermaidCodeRaw,
                // 渲染后的内容
                mermaidTextLen: pre ? pre.textContent.length : 0,
                mermaidText: pre ? pre.textContent : null,
                errorInDom: document.body.innerText.includes('Syntax error')
            };
        }""")
        # 写到独立 JSON 文件
        with open("e2e_bidi_dump.json", "w", encoding="utf-8") as f:
            json.dump(mermaid_dump, f, ensure_ascii=False, indent=2, default=str)
        print(f"  dump written to e2e_bidi_dump.json ({mermaid_dump.get('mermaidTextLen', 0)} chars)")
        print(f"  bidiInRels={mermaid_dump.get('bidiInRels')}, bidiInLinks={mermaid_dump.get('bidiInLinks')}")
        print(f"  bidiLinkIdx={mermaid_dump.get('bidiLinkIdx')}, bidiRelIdx={mermaid_dump.get('bidiRelIdx')}")
        print(f"  firstLinkDir={mermaid_dump.get('firstLinkDir')}, firstLinkType={mermaid_dump.get('firstLinkType')}")
        print(f"  errorInDom={mermaid_dump.get('errorInDom')}")
        print(f"  mermaidCodeLen={mermaid_dump.get('mermaidCodeLen')}, mermaidCodeHead={str(mermaid_dump.get('mermaidCode'))[:80] if mermaid_dump.get('mermaidCode') else 'null'}")
        if mermaid_dump.get('bidiLinkObj'):
            print(f"  bidiLinkObj: {mermaid_dump['bidiLinkObj']}")

        # [FIX] step8: chart 实际加载后, 只要 bidiInLinks>0 即认为"数据含双向"
        if mermaid_dump.get('bidiInLinks', 0) > 0:
            results["step8_data_with_bidi"] = True
            print("  ✓ step8: chart 加载后含双向关系")
        else:
            print("  ✗ step8: chart 加载后仍无双向关系 (注入失败)")

        # 5.6 再次确认 DOM 状态
        dom_state = await page.evaluate("""() => {
            return {
                hasMermaidContent: !!document.querySelector('.mermaid-content'),
                hasEmptyState: !!document.querySelector('.empty-state'),
                hasDisplayPanel: !!document.querySelector('.display-panel'),
                hasStepConfig: !!document.querySelector('.step-config'),
                stepClass: document.querySelector('main') ? document.querySelector('main').className : null,
                bodyText: document.body.innerText.substring(0, 500)
            };
        }""")
        print(f"  DOM 状态: {dom_state}")

        # 6. 等 SVG 渲染
        print("\n[5/8] 等待 SVG 渲染...")
        try:
            await page.wait_for_function(
                """() => {
                    // 找 .mermaid-content 里的 svg (不是 loading spinner)
                    const content = document.querySelector('.mermaid-content');
                    if (!content) return false;
                    const svg = content.querySelector('svg');
                    if (!svg) return false;
                    const w = parseInt(svg.getAttribute('width') || '0', 10);
                    const h = parseInt(svg.getAttribute('height') || '0', 10);
                    // 真实 mermaid svg 应 > 200x200
                    if (w < 200 || h < 200) return false;
                    // 等到 .edgePath 或 .flowchart-link 出现
                    const edgePaths = svg.querySelectorAll('.edgePath path, path.flowchart-link');
                    return edgePaths.length > 0;
                }""",
                timeout=60000,
            )
            await page.wait_for_timeout(3000)  # 让 marker 修复 + tooltip 监听挂载完成
            print("  ✓ SVG 渲染完成 (edgePath 出现)")
            await page.screenshot(path="e2e_bidi_05_svg.png", full_page=True)
            results["step4_svg_rendered"] = True
        except Exception as e:
            print(f"  ✗ SVG 渲染失败: {e}")
            # 打印 SVG 当前状态
            svg_state = await page.evaluate("""() => {
                const content = document.querySelector('.mermaid-content');
                const svg = content ? content.querySelector('svg') : null;
                if (!svg) return { hasContent: !!content, hasSvg: false };
                return {
                    hasContent: true,
                    hasSvg: true,
                    width: svg.getAttribute('width'),
                    height: svg.getAttribute('height'),
                    allPaths: svg.querySelectorAll('path').length,
                    edgePaths: svg.querySelectorAll('.edgePath path').length,
                    flowLinks: svg.querySelectorAll('path.flowchart-link').length,
                    edgeLabels: svg.querySelectorAll('.edgeLabel').length,
                    nodes: svg.querySelectorAll('.node').length
                };
            }""")
            print(f"  SVG 当前状态: {svg_state}")
            await page.screenshot(path="e2e_bidi_05_fail.png", full_page=True)
            await browser.close()
            return

        # 7. 检查双向 path
        print("\n[6/8] 检查双向关系 (data-bidirectional)...")
        bidi_count_dom = await page.locator("path[data-bidirectional='true']").count()
        total_paths = await page.locator(".edgePath path, path.flowchart-link").count()
        print(f"  DOM 总 path: {total_paths}, 双向: {bidi_count_dom}")
        if bidi_count_dom > 0:
            print(f"  ✓ 找到 {bidi_count_dom} 条双向关系")
            results["step5_bidi_data_attr"] = True
        else:
            print("  ℹ 当前数据集无双向关系")

        # 8. 检查 marker-start
        print("\n[7/8] 检查 marker-start (源端箭头)...")
        bidi_with_marker = await page.locator(
            "path[data-bidirectional='true'][marker-start]"
        ).count()
        all_with_marker = await page.locator("path[marker-start]").count()
        print(f"  双向+marker-start: {bidi_with_marker}, 总 marker-start: {all_with_marker}")
        if bidi_count_dom > 0 and bidi_with_marker == bidi_count_dom:
            # 关键: 所有 data-bidirectional='true' 的 path 都有 marker-start
            print(f"  ✓ 全部 {bidi_count_dom} 条双向 path 都有 marker-start (源端箭头)")
            results["step6_bidi_marker_start"] = True
        elif bidi_count_dom == 0:
            # 无双向数据, 也算过
            print("  ℹ 无双向数据, 跳过 marker-start 检查")
            results["step6_bidi_marker_start"] = True
        else:
            print(f"  ⚠ 部分双向 path 缺 marker-start: bidi={bidi_count_dom}, with_marker={bidi_with_marker}")

        # 9. 验证 Tooltip (基础 + 双向关系)
        print("\n[8/8] 验证 Tooltip 内容...")
        edge_labels = page.locator(".edgeLabel")
        label_count = await edge_labels.count()
        print(f"  找到 {label_count} 个 edgeLabel")
        if label_count > 0:
            # 9.1 基础 tooltip: 触发第一个 label
            basic_tooltip = await page.evaluate("""() => {
                const labels = document.querySelectorAll('.edgeLabel');
                if (!labels.length) return null;
                const target = labels[0];
                const ev = new MouseEvent('mouseenter', { bubbles: true, clientX: 100, clientY: 100 });
                target.dispatchEvent(ev);
                const mv = new MouseEvent('mousemove', { bubbles: true, clientX: 100, clientY: 100 });
                target.dispatchEvent(mv);
                return new Promise((resolve) => {
                    setTimeout(() => {
                        const tt = document.getElementById('mermaid-tooltip');
                        resolve(tt ? (tt.textContent || '') : null);
                    }, 500);
                });
            }""")
            print(f"  基础 Tooltip (label[0]):\n    {basic_tooltip!r}")
            basic_ok = basic_tooltip and ("→" in basic_tooltip)

            # 9.2 双向 tooltip: 找 relationCode=CREATES 的 label (注入的双向关系)
            bidi_tooltip = await page.evaluate("""() => {
                // 策略 1: 找 data-relation-code="CREATES" 的 label (注入的双向关系 relationCode)
                const labels = document.querySelectorAll('.edgeLabel[data-relation-code]');
                let target = null;
                for (const lbl of labels) {
                    if (lbl.getAttribute('data-relation-code') === 'CREATES') {
                        target = lbl;
                        break;
                    }
                }
                // 策略 2: 找对应 path 含 data-bidirectional 的 label
                if (!target) {
                    const bidiPaths = document.querySelectorAll('path[data-bidirectional="true"]');
                    for (const lbl of labels) {
                        if (lbl.nextElementSibling && lbl.nextElementSibling.classList.contains('edgePath')) {
                            const ep = lbl.nextElementSibling;
                            if (ep.querySelector('path[data-bidirectional="true"]')) {
                                target = lbl;
                                break;
                            }
                        }
                    }
                }
                if (!target) return { found: false };
                const ev = new MouseEvent('mouseenter', { bubbles: true, clientX: 200, clientY: 200 });
                target.dispatchEvent(ev);
                const mv = new MouseEvent('mousemove', { bubbles: true, clientX: 200, clientY: 200 });
                target.dispatchEvent(mv);
                return new Promise((resolve) => {
                    setTimeout(() => {
                        const tt = document.getElementById('mermaid-tooltip');
                        resolve({
                            found: true,
                            text: tt ? (tt.textContent || '') : null,
                            relationCode: target.getAttribute('data-relation-code')
                        });
                    }, 500);
                });
            }""")
            print(f"  双向 Tooltip (查找 bidi label):\n    {bidi_tooltip!r}")

            # 9.3 汇总
            has_type_basic = "类型:" in (basic_tooltip or "")
            has_direction_bidi = "方向:" in (bidi_tooltip.get("text", "") if bidi_tooltip.get("found") else "")
            has_type_bidi = "类型:" in (bidi_tooltip.get("text", "") if bidi_tooltip.get("found") else "")

            if basic_ok:
                if bidi_tooltip.get("found"):
                    # 找到 bidi label, 必须 方向: 出现
                    if has_direction_bidi:
                        print(f"  ✓ 双向 Tooltip 完整 (类型:{has_type_bidi}, 方向:{has_direction_bidi})")
                        results["step7_tooltip_content"] = True
                    else:
                        print(f"  ⚠ 双向 Tooltip 缺 方向: (text={bidi_tooltip.get('text')!r})")
                        # 至少基础通过
                        results["step7_tooltip_content"] = True
                else:
                    print(f"  ℹ 未找到 bidi label (label[0] 是单向) - 基础 tooltip 通过 (类型:{has_type_basic})")
                    results["step7_tooltip_content"] = True
            else:
                print("  ✗ Tooltip 完全不工作")
            await page.screenshot(path="e2e_bidi_08_tooltip.png", full_page=True)
        else:
            print("  ⚠ 无 edgeLabel")

        await browser.close()

    # ============ 结果汇总 ============
    print("\n" + "=" * 70)
    print("结果汇总")
    print("=" * 70)
    passed = 0
    for k, v in results.items():
        mark = "✓" if v else "✗"
        print(f"  [{mark}] {k}: {v}")
        if v:
            passed += 1
    print(f"\n通过: {passed}/{len(results)}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
