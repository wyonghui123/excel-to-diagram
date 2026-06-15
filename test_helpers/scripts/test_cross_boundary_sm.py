"""
验证: 范围外BO的SM容器 + 颜色正确显示
测试步骤:
  1. auth -> archdata
  2. 选择对象范围: 采购管理/采购需求, 供应商管理, 采购合同
  3. 进入图表 -> 选择关系: 范围内 + 范围内与外部
  4. 配置步骤 -> 按服务模块 -> 检查颜色配置
  5. 图表展示 -> 验证范围外SM容器 + 颜色
"""
import time
import json
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI()

try:
    # === Step 1: Auth ===
    print("Step 1: Authenticating...")
    cli.request('http://localhost:3010/api/v1/auth/dev-login?username=admin')
    cli.goto('http://localhost:3004/')
    time.sleep(4)
    cli.screenshot('s1_auth.png')

    # Check auth
    auth_state = cli.evaluate('document.querySelector("#app").__vue_app__.config.globalProperties.$pinia._s.get("auth").user')
    print(f"Auth state: {auth_state}")
    assert auth_state, "Auth failed"

    # === Step 2: Navigate to archdata ===
    print("Step 2: Navigating to archdata...")
    cli.goto('http://localhost:3004/system/archdata')
    time.sleep(4)
    cli.screenshot('s2_archdata.png')

    # === Step 3: Open scope panel ===
    print("Step 3: Opening scope panel...")
    # Click the scope/filter button
    scope_btn = cli.wait_for_selector('button:has-text("对象范围"), [class*="scope"], [class*="filter"]', timeout=8000)
    cli.click('button:has-text("对象范围")')
    time.sleep(2)
    cli.screenshot('s3_scope_panel.png')

    # === Step 4: Select objects ===
    print("Step 4: Selecting objects...")
    # First, expand the domain tree
    domain_nodes = cli.query_selector_all('[class*="tree-node"], [class*="el-tree-node"]')
    print(f"Found {len(domain_nodes)} tree nodes")

    # Click on domain filter/tree
    tree_nodes = cli.query_selector_all('.el-tree-node__content, [class*="tree-node"]')
    print(f"Tree nodes: {len(tree_nodes)}")

    # Try to expand domain
    cli.click('text=采购管理', timeout=5000)
    time.sleep(1)
    cli.screenshot('s4_domain_expanded.png')

    # Select sub-items
    cli.click('text=采购需求')
    time.sleep(0.5)
    cli.click('text=供应商管理')
    time.sleep(0.5)
    cli.click('text=采购合同')
    time.sleep(1)
    cli.screenshot('s4_objects_selected.png')

    # === Step 5: Enter diagram ===
    print("Step 5: Entering diagram...")
    cli.click('text=图表视图, [class*="chart"]')
    time.sleep(3)
    cli.screenshot('s5_diagram.png')

    # === Step 6: Select relation categories ===
    print("Step 6: Selecting relations (范围内 + 范围内与外部)...")
    # Expand relation tree
    cli.click('text=关系范围')
    time.sleep(1)

    # Check relation category tree
    tree = cli.evaluate(
        'document.querySelector("#app").__vue_app__.config.globalProperties.$pinia._s.get("chartArchData").relationCategoryTree'
    )
    print(f"Relation tree: {json.dumps(tree, ensure_ascii=False)[:500]}")

    # Select both categories (范围内 + 范围内与外部)
    cli.click('text=范围内')
    time.sleep(0.5)
    cli.click('text=范围内与外部')
    time.sleep(1)
    cli.screenshot('s6_relations_selected.png')

    # === Step 7: Go to config step ===
    print("Step 7: Navigating to config step...")
    cli.click('text=下一步, [class*="next"]')
    time.sleep(1)
    cli.click('text=下一步, [class*="next"]')
    time.sleep(3)
    cli.screenshot('s7_config.png')

    # === Step 8: Check color config by service module ===
    print("Step 8: Checking color config by service module...")

    # Enable centerScopeHighlight
    center_toggle = cli.query_selector('[class*="switch"], [class*="checkbox"], [class*="toggle"]')
    if center_toggle:
        cli.click('[class*="center"], [class*="区分"]')
        time.sleep(1)
        cli.screenshot('s8_center_highlight.png')

    # Select by service module
    cli.click('text=按服务模块')
    time.sleep(2)
    cli.screenshot('s8_sm_colors.png')

    # Get color items
    color_items = cli.query_selector_all('[class*="color-item"], [class*="group-item"], .el-tag, [class*="color-tag"]')
    print(f"Color items found: {len(color_items)}")

    # Get state from stores
    diagram_state = cli.evaluate(
        'document.querySelector("#app").__vue_app__.config.globalProperties.$pinia._s.get("chartArchData").diagramConfig'
    )
    config_state = cli.evaluate(
        'document.querySelector("#app").__vue_app__.config.globalProperties.$pinia._s.get("configStore").state'
    )

    print(f"centerScopeHighlight: {diagram_state.get('centerScopeHighlight') if isinstance(diagram_state, dict) else diagram_state}")
    print(f"colorGroupBy: {diagram_state.get('colorGroupBy') if isinstance(diagram_state, dict) else None}")
    print(f"configStore state keys: {list(config_state.keys()) if isinstance(config_state, dict) else None}")

    # === Step 9: Go to diagram view ===
    print("Step 9: Navigating to diagram view...")
    cli.click('text=下一步, [class*="next"]')
    time.sleep(3)
    cli.screenshot('s9_diagram_view.png')

    # Get group model to verify containers
    group_model = cli.evaluate(
        'document.querySelector("#app").__vue_app__.config.globalProperties.$pinia._s.get("chartArchData").groupModel'
    )

    def count_nodes(gm, nodes=None):
        if nodes is None:
            nodes = []
        if isinstance(gm, dict):
            if gm.get('elementRef', {}).get('type') == 'BUSINESS_OBJECT':
                nodes.append(gm)
            for child in gm.get('children', []):
                count_nodes(child, nodes)
        elif isinstance(gm, list):
            for item in gm:
                count_nodes(item, nodes)
        return nodes

    if group_model:
        nodes = count_nodes(group_model)
        print(f"Group model terminal BOs: {len(nodes)}")
        for n in nodes[:10]:
            print(f"  {n.get('title')} isCenter={n.get('isCenter')} parent={n.get('parentId')}")
    else:
        print("No group model found")

    print("\n=== VERIFICATION COMPLETE ===")
    print("Screenshots saved: s1_auth.png - s9_diagram_view.png")

finally:
    input("Press Enter to close browser...")
    cli.close()
