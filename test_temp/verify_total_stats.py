"""
聚焦端到端验证：displayStats.total = center + incremental

注入模拟数据到 Pinia store，验证 v39.6 修复后：
- center.objectRelations = 4
- incremental.objectRelations = 8
- total.objectRelations = 12 (修复前 = 8, 错误)
- config.objectRelations = 12 (修复前 = 11, 与 total 不一致)
"""
import sys
import os
import time
import json
from playwright.sync_api import sync_playwright

FRONTEND = "http://localhost:3004"
API = "http://localhost:3010"

# 模拟数据：1域 1子 8服 16对象 11关系 (用户真实场景)
MOCK_DATA = {
    "domains": [{"id": 1, "code": "DOM1", "name": "采购域"}],
    "sub_domains": [{"id": 1, "code": "SUB1", "name": "采购子域", "domain_id": 1}],
    "service_modules": [
        {"id": 1, "code": "SM1", "name": "采购需求", "sub_domain_id": 1},
        {"id": 2, "code": "SM2", "name": "供应商管理", "sub_domain_id": 1},
        {"id": 3, "code": "SM3", "name": "采购合同", "sub_domain_id": 1},
        {"id": 4, "code": "SM4", "name": "采购执行", "sub_domain_id": 1},
        {"id": 5, "code": "SM5", "name": "仓库管理", "sub_domain_id": 1},
        # external
        {"id": 6, "code": "SM6", "name": "销售管理"},
        {"id": 7, "code": "SM7", "name": "库存管理"},
        {"id": 8, "code": "SM8", "name": "财务管理"},
    ],
    "business_objects": [
        # 中心 (5 服务, 9 对象)
        {"id": 1, "code": "BO1", "name": "BO1", "service_module_id": 1},
        {"id": 2, "code": "BO2", "name": "BO2", "service_module_id": 1},
        {"id": 3, "code": "BO3", "name": "BO3", "service_module_id": 2},
        {"id": 4, "code": "BO4", "name": "BO4", "service_module_id": 2},
        {"id": 5, "code": "BO5", "name": "BO5", "service_module_id": 3},
        {"id": 6, "code": "BO6", "name": "BO6", "service_module_id": 3},
        {"id": 7, "code": "BO7", "name": "BO7", "service_module_id": 4},
        {"id": 8, "code": "BO8", "name": "BO8", "service_module_id": 4},
        {"id": 9, "code": "BO9", "name": "BO9", "service_module_id": 5},
        # external (3 服务, 7 对象)
        {"id": 10, "code": "BO10", "name": "BO10", "service_module_id": 6},
        {"id": 11, "code": "BO11", "name": "BO11", "service_module_id": 6},
        {"id": 12, "code": "BO12", "name": "BO12", "service_module_id": 7},
        {"id": 13, "code": "BO13", "name": "BO13", "service_module_id": 7},
        {"id": 14, "code": "BO14", "name": "BO14", "service_module_id": 8},
        {"id": 15, "code": "BO15", "name": "BO15", "service_module_id": 8},
        {"id": 16, "code": "BO16", "name": "BO16", "service_module_id": 8},
    ],
    "relationships": [
        # 中心 4 条 (internal: src+tgt 都在中心)
        {"id": 1, "source_code": "BO1", "target_code": "BO3", "relationCode": "GENERATES", "scopeType": "internal"},
        {"id": 2, "source_code": "BO3", "target_code": "BO5", "relationCode": "TRIGGERS", "scopeType": "internal"},
        {"id": 3, "source_code": "BO5", "target_code": "BO7", "relationCode": "DEPENDS_ON", "scopeType": "internal"},
        {"id": 4, "source_code": "BO7", "target_code": "BO9", "relationCode": "FEEDS", "scopeType": "internal"},
        # 跨域 8 条 (cross-boundary: 一方在中心一方在外)
        {"id": 5, "source_code": "BO1", "target_code": "BO10", "relationCode": "REFERENCES", "scopeType": "cross-boundary"},
        {"id": 6, "source_code": "BO2", "target_code": "BO11", "relationCode": "REFERENCES", "scopeType": "cross-boundary"},
        {"id": 7, "source_code": "BO4", "target_code": "BO12", "relationCode": "UPDATES", "scopeType": "cross-boundary"},
        {"id": 8, "source_code": "BO5", "target_code": "BO13", "relationCode": "UPDATES", "scopeType": "cross-boundary"},
        {"id": 9, "source_code": "BO6", "target_code": "BO14", "relationCode": "INFORMS", "scopeType": "cross-boundary"},
        {"id": 10, "source_code": "BO7", "target_code": "BO15", "relationCode": "INFORMS", "scopeType": "cross-boundary"},
        {"id": 11, "source_code": "BO8", "target_code": "BO16", "relationCode": "REPORTS_TO", "scopeType": "cross-boundary"},
        {"id": 12, "source_code": "BO9", "target_code": "BO10", "relationCode": "STOCKS", "scopeType": "cross-boundary"},
    ],
    "center_scope": ["BO1", "BO2", "BO3", "BO4", "BO5", "BO6", "BO7", "BO8", "BO9"]
}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()

    logs = []
    page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: logs.append(f"[err] {err}"))

    # 1. 登录
    print("=== Step 1: 登录 ===")
    page.goto(f"{API}/api/v1/auth/dev-login?username=admin", wait_until="networkidle", timeout=15000)
    page.goto(f"{FRONTEND}/", wait_until="networkidle", timeout=15000)
    time.sleep(2)

    # 2. 注入数据到 Pinia store
    print("\n=== Step 2: 注入测试数据到 Pinia store ===")
    page.goto(f"{FRONTEND}/archdata-chart", wait_until="networkidle", timeout=15000)
    time.sleep(2)

    # 通过 __diagramApp 暴露的 API 注入
    inject_result = page.evaluate("""(mockData) => {
        const d = window.__diagramApp;
        if (!d) return { ok: false, reason: 'no __diagramApp' };
        if (!d.chartArchStore) return { ok: false, reason: 'no chartArchStore' };
        d.chartArchStore.setArchData(mockData);
        return { ok: true };
    }""", MOCK_DATA)
    print(f"  注入结果: {inject_result}")
    time.sleep(2)

    # 3. 抓取 displayStats
    print("\n=== Step 3: 抓取 displayStats ===")
    stats = page.evaluate("""() => {
        const d = window.__diagramApp;
        if (!d) return { error: 'no __diagramApp' };
        // 尝试获取 displayStats
        if (d.displayStats) {
            const ds = d.displayStats.value || d.displayStats;
            return {
                center: { relations: ds.center?.objectRelations, services: ds.center?.serviceModules, objects: ds.center?.businessObjects },
                incremental: { relations: ds.incremental?.objectRelations, services: ds.incremental?.serviceModules, objects: ds.incremental?.businessObjects },
                total: { relations: ds.total?.objectRelations, services: ds.total?.serviceModules, objects: ds.total?.businessObjects },
                config: { relations: ds.config?.objectRelations, services: ds.config?.serviceModules, objects: ds.config?.businessObjects }
            };
        }
        return { error: 'no displayStats' };
    }""")
    print(f"  displayStats: {json.dumps(stats, ensure_ascii=False, indent=2)}")

    # 4. 抓取 UI 上显示的统计
    print("\n=== Step 4: 抓取 UI 显示 ===")
    ui_stats = page.evaluate("""() => {
        const items = document.querySelectorAll('.step-stats-inline, .step-stats, [class*="stat"]');
        return Array.from(items).map(el => el.textContent?.trim()).filter(t => t && t.length < 200);
    }""")
    print(f"  UI 元素: {ui_stats[:10]}")

    # 5. 验证
    print("\n=== Step 5: 验证修复 ===")
    if 'error' not in stats:
        center = stats.get('center', {}).get('relations', 0)
        incremental = stats.get('incremental', {}).get('relations', 0)
        total = stats.get('total', {}).get('relations', 0)
        config = stats.get('config', {}).get('relations', 0)
        expected_total = center + incremental
        print(f"  center.relations = {center} (期望 4)")
        print(f"  incremental.relations = {incremental} (期望 8)")
        print(f"  total.relations = {total} (期望 {expected_total} = 4+8)")
        print(f"  config.relations = {config} (期望 {expected_total}, 与 total 一致)")
        if total == expected_total and config == expected_total:
            print("  ✓✓✓ 修复成功！total = center + incremental = config")
        else:
            print(f"  ✗✗✗ 仍有差异：total={total} vs 期望{expected_total}, config={config}")
    else:
        print(f"  ✗ 抓取失败: {stats}")

    # 6. 抓取 console 日志
    print("\n=== Step 6: Console 日志 ===")
    for log in logs[-20:]:
        if 'error' in log.lower() or 'warn' in log.lower():
            print(f"  {log[:200]}")

    browser.close()
    print("\n=== Done ===")
