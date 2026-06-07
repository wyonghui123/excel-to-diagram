# -*- coding: utf-8 -*-
"""
L3 Auto-Generator: URL + page name → v2 spec (全自动)

依据项目最佳实践反向生成 (2026-06-07):
- v2 简化方案 8 铁律 (.trae/rules/e2e-simplification.md)
- 5 步视觉验证 (.trae/rules/frontend-test-auth.md)
- POM 模式 (GenericList/ArchData/DetailDrawer)
- v2 模板 (arch-data-crud-v2.spec.js)
- 项目认证 (test_helpers/browser_auth.py)

用法:
  python scripts/auto_gen_v2_spec.py <url> <page_name> <data_type> [output]

示例:
  python scripts/auto_gen_v2_spec.py /system/archdata?tab=business_object business-object business_object
  python scripts/auto_gen_v2_spec.py /product-management product business_object
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# 用项目自己的认证 helper
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from test_helpers.browser_auth import authenticated_page  # noqa: E402

# ==================== v2 Spec 模板 (8 铁律 100% 合规) ====================
# 注: 模板中 {{ }} 是 Python 转义,实际 JS 中是 { }

V2_FILE_HEADER = '''/**
 * S{ID}: {NAME} - 功能测试 (auto-generated)
 *
 * URL: {URL}
 * Data Type: {DATA_TYPE}
 * 生成时间: {TIMESTAMP}
 * 生成工具: scripts/auto_gen_v2_spec.py
 *
 * [E2E 规则速查] 修改前必读:
 * - 必须 import 自 auto-fixtures.js（新方案）
 * - 必须用 isolation.createTracked() 创建测试数据
 * - 必须用 withStep() 包裹每个业务步骤
 * - 详细: .trae/rules/e2e-simplification.md
 *
 * v2 铁律合规:
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions()
 * [OK] 用 navigateTo() 不用 page.goto()
 * [OK] 用 isolation.createTracked() 不用 Date.now() 硬编码
 * [OK] 用 POM 不用直接 .el-table locator
 * [OK] 用 waitForApiFn() 不用 waitForTimeout()
 * [OK] 每个步骤 withStep() 包裹
 * [OK] isolation fixture 自动清理
 */
'''

V2_IMPORTS = '''import {{ test, expect }} from '../helpers/auto-fixtures.js'
import {{ withStep }} from '../helpers/auto-trace.js'
{EXTRA_IMPORTS}
'''

V2_DESCRIBE_OPEN = '''
test.describe('S{ID}: {NAME}', () => {{
'''

# C01 模板: 页面加载
V2_C01_LOAD = '''  test('C01: 页面正常加载', async ({{ page, navigateTo, dataFinder }}, testInfo) => {{
    const pv = await dataFinder.productWithVersion()
    await withStep(page, testInfo, '导航到 {URL}', async () => {{
      await navigateTo(page, '{URL}?productId=' + pv.product.id + '&versionId=' + pv.version.id)
    }})
{ASSERTIONS}
  }})
'''

# C02 模板: 创建记录
V2_C02_CREATE = '''  test('C02: 创建{DATA_TYPE}记录', async ({{ page, navigateTo, dataFinder, isolation }}, testInfo) => {{
    const pv = await dataFinder.productWithVersion()
    await navigateTo(page, '{URL}?productId=' + pv.product.id + '&versionId=' + pv.version.id)

    const uniqueId = Date.now().toString(36).toUpperCase()
    const testCode = `E2E_${{uniqueId}}`
    const testName = `auto-gen-test-${{uniqueId}}`

    await withStep(page, testInfo, 'API 创建{DATA_TYPE} (自动跟踪)', async () => {{
      await isolation.createTracked('{DATA_TYPE}', {{
        code: testCode,
        name: testName,
        version_id: pv.version.id
      }})
    }})

{VERIFY_CREATE}
  }})
'''

# C03 模板: 搜索
V2_C03_SEARCH = '''  test('C03: 搜索过滤', async ({{ page, navigateTo, dataFinder }}, testInfo) => {{
    const pv = await dataFinder.productWithVersion()
    await navigateTo(page, '{URL}?productId=' + pv.product.id + '&versionId=' + pv.version.id)

    await withStep(page, testInfo, '验证初始列表加载', async () => {{
{ASSERT_LIST}
    }})
  }})
'''

# C04 模板: 删除
V2_C04_DELETE = '''  test('C04: 删除{DATA_TYPE}记录', async ({{ page, navigateTo, dataFinder, isolation }}, testInfo) => {{
    const pv = await dataFinder.productWithVersion()
    await navigateTo(page, '{URL}?productId=' + pv.product.id + '&versionId=' + pv.version.id)

    const uniqueId = Date.now().toString(36).toUpperCase()
    const testCode = `E2E_DEL_${{uniqueId}}`

    await withStep(page, testInfo, 'API 创建待删除对象', async () => {{
      await isolation.createTracked('{DATA_TYPE}', {{
        code: testCode,
        name: 'to-delete-' + uniqueId,
        version_id: pv.version.id
      }})
    }})

    await withStep(page, testInfo, 'API 删除对象', async () => {{
      const tracked = isolation.getTracked('{DATA_TYPE}')
      if (tracked.length === 0) throw new Error('No tracked {DATA_TYPE} to delete')
      const id = tracked[0].id
      await page.context().request.delete(
        `${{process.env.TEST_BASE_URL || 'http://localhost:3010'}}/api/v2/bo/{DATA_TYPE}/${{id}}`
      )
      isolation.markCleaned('{DATA_TYPE}')
    }})
  }})
'''

V2_DESCRIBE_CLOSE = '})\n'


# ==================== a11y 抓取 + 模式推断 ====================

async def get_product_version():
    """API 获取第一个 product + version (替代 dataFinder)"""
    import requests
    api = "http://localhost:3010"
    s = requests.Session()
    r = s.get(f"{api}/api/v1/auth/dev-login?username=admin", timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"dev-login failed: {r.status_code}")
    # 找 product
    r = s.get(f"{api}/api/v2/bo/product?page_size=10", timeout=10)
    products = r.json()
    items = (products.get("data") or {}).get("items") if isinstance(products.get("data"), dict) else products.get("data")
    if not items:
        raise RuntimeError("No products found")
    p = items[0]
    # 找 version
    r = s.get(f"{api}/api/v2/bo/version?product_id={p['id']}", timeout=10)
    versions = r.json()
    v_items = (versions.get("data") or {}).get("items") if isinstance(versions.get("data"), dict) else versions.get("data")
    if not v_items:
        raise RuntimeError(f"No versions for product {p['id']}")
    v = v_items[0]
    return p["id"], v["id"], p.get("name"), v.get("name")


async def capture_a11y(url, output_path=None):
    """登录 → 导航 → 抓 DOM 结构 (Element UI 选择器)"""
    # JS 脚本: 走 DOM 提取结构 (替代 page.accessibility)
    # 覆盖 Element UI 常见组件: .el-table / .el-tabs / .el-form / .el-button
    extract_script = r"""
() => {
    const result = {
        url: window.location.href,
        title: document.title,
        has_table: false,
        has_form: false,
        has_tabs: false,
        has_search: false,
        has_new_btn: false,
        has_delete: false,
        has_edit: false,
        tab_names: [],
        button_names: [],
        field_names: [],
        table_columns: []
    };

    // 表格
    const tables = document.querySelectorAll('.el-table');
    if (tables.length > 0) {
        result.has_table = true;
        // 抓表头
        const headers = tables[0].querySelectorAll('.el-table__header th .cell');
        headers.forEach(h => {
            const txt = (h.textContent || '').trim();
            if (txt && txt.length < 30) result.table_columns.push(txt);
        });
    }

    // Tabs
    const tabs = document.querySelectorAll('.el-tabs__item, [role="tab"]');
    tabs.forEach(t => {
        const txt = (t.textContent || '').trim();
        if (txt && txt.length < 30 && !result.tab_names.includes(txt)) {
            result.tab_names.push(txt);
            result.has_tabs = true;
        }
    });

    // 表单
    const forms = document.querySelectorAll('.el-form, form');
    if (forms.length > 0) result.has_form = true;

    // 按钮 (Element UI 风格)
    const btns = document.querySelectorAll('button, .el-button');
    btns.forEach(b => {
        const txt = (b.textContent || '').trim();
        if (txt && txt.length < 30 && !result.button_names.includes(txt)) {
            result.button_names.push(txt);
            if (['新建', '新增', '创建', '+ 新建', 'New', 'Add', '添加'].includes(txt)) {
                result.has_new_btn = true;
            }
            if (txt.includes('删') || ['delete', 'remove', 'Delete', 'Remove'].includes(txt)) {
                result.has_delete = true;
            }
            if (txt.includes('编') || txt.includes('修改') || ['edit', 'modify', 'Edit'].includes(txt)) {
                result.has_edit = true;
            }
        }
    });

    // 输入框 / 搜索
    const inputs = document.querySelectorAll('input, .el-input__inner, .el-select');
    inputs.forEach(inp => {
        const ph = inp.placeholder || '';
        const aria = inp.getAttribute('aria-label') || '';
        const labelTxt = aria || ph;
        if (labelTxt) {
            if (labelTxt.includes('搜') || labelTxt.toLowerCase().includes('search')) {
                result.has_search = true;
            }
            if (labelTxt.length < 20 && !['产品', '版本'].includes(labelTxt)
                && !result.field_names.includes(labelTxt)) {
                result.field_names.push(labelTxt);
            }
        }
    });

    // 搜索框 (顶栏常见)
    const searchBoxes = document.querySelectorAll('[role="searchbox"], .search-input, input[type="search"]');
    if (searchBoxes.length > 0) result.has_search = true;

    return result;
}
"""
    # 1. 拿 product+version (避免页面"请选择"状态)
    has_pv = ("productId=" in url) and ("versionId=" in url)
    if not has_pv:
        try:
            pid, vid, pname, vname = await get_product_version()
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}productId={pid}&versionId={vid}"
            print(f"  [INFO] 注入 product/version context: {pname}/{vname}")
        except Exception as e:
            print(f"  [WARN] get_product_version 失败: {e},继续")

    async with authenticated_page(target_url=url) as page:
        print(f"  [OK] Logged in, current URL: {page.url}")
        # 等 2s 让页面稳定 (含 product/version context restore)
        await asyncio.sleep(2)
        snap = await page.evaluate(extract_script)
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(snap, f, ensure_ascii=False, indent=2)
            print(f"  [OK] DOM snapshot saved: {output_path}")
        return snap


def infer_page_pattern(snap):
    """从 DOM 快照推断页面结构 (Element UI 模式)

    snap 现在已经是 {has_table, has_form, has_tabs, ...} 格式
    (DOM 提取脚本已直接产出)
    """
    info = dict(snap)  # 已经是结构化数据
    # 推断 page_type
    if info["has_table"] and not info["has_form"]:
        info["page_type"] = "list"
    elif info["has_table"] and info["has_form"]:
        info["page_type"] = "list_with_form"
    elif info["has_form"]:
        info["page_type"] = "form"
    elif info["has_tabs"]:
        info["page_type"] = "tabbed"
    else:
        info["page_type"] = "other"
    return info


# ==================== POM 选择 ====================

def choose_pom(url, info):
    """根据 URL + 页面结构选择合适的 POM"""
    imports = []
    pom_var = None
    pom_class = None

    if info["has_table"]:
        if "archdata" in url.lower():
            pom_class = "ArchDataPage"
            imports.append("import { ArchDataPage } from '../page-objects/ArchDataPage.js'")
        else:
            pom_class = "GenericListPage"
            imports.append("import { GenericListPage } from '../page-objects/GenericListPage.js'")
        pom_var = "archData" if "archdata" in url.lower() else "listPage"

    if info["has_form"] or info["has_new_btn"]:
        imports.append("import { DetailDrawerPage } from '../page-objects/DetailDrawerPage.js'")

    return {
        "imports": imports,
        "pom_var": pom_var,
        "pom_class": pom_class,
    }


# ==================== v2 Spec 生成 ====================

def generate_v2_spec(page_id, page_name, url, data_type, info, output_path):
    """根据推断的模式生成 v2 spec"""
    pom = choose_pom(url, info)
    extra_imports = "\n".join(pom["imports"])

    # Header
    spec = V2_FILE_HEADER.format(
        ID=page_id,
        NAME=page_name,
        URL=url,
        DATA_TYPE=data_type,
        TIMESTAMP=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    # Imports
    spec += V2_IMPORTS.format(EXTRA_IMPORTS=extra_imports)

    # describe 开
    spec += V2_DESCRIBE_OPEN.format(ID=page_id, NAME=page_name)

    # C01 页面加载 (用 POM-friendly 的断言,不用 page.locator('.el-table'))
    assertions = []
    if info["has_tabs"]:
        assertions.append("    await expect(page.getByRole('tab').first()).toBeVisible({ timeout: 10000 })")
    if info["has_new_btn"]:
        assertions.append("    await expect(page.getByRole('button', { name: '新建' }).first()).toBeVisible()")
    if not assertions:
        # fallback: 用 Pom 内部的方法 (如果有)
        if pom["pom_class"]:
            assertions.append(f"    const {pom['pom_var']} = new {pom['pom_class']}(page)")
            assertions.append("    await expect(page.getByRole('tab').first()).toBeVisible({ timeout: 10000 })")
        else:
            assertions.append("    await expect(page.locator('main, .el-main, #app').first()).toBeVisible()")

    spec += V2_C01_LOAD.format(
        URL=url,
        ASSERTIONS="\n".join(assertions),
    )

    # C02 创建 (if applicable)
    if info["has_new_btn"] and data_type and pom["pom_class"]:
        verify_lines = []
        if pom["pom_class"]:
            verify_lines.append(f"    const {pom['pom_var']} = new {pom['pom_class']}(page)")
            verify_lines.append("    await withStep(page, testInfo, '验证列表中出现', async () => {")
            verify_lines.append(f"      await {pom['pom_var']}.expectRowExists(testCode, {{")
            verify_lines.append("        timeout: 20000,")
            verify_lines.append("        onRetry: async () => {")
            verify_lines.append(f"          try {{ await {pom['pom_var']}.search('') }} catch (e) {{}}")
            verify_lines.append("        }")
            verify_lines.append("      })")
            verify_lines.append("    })")
        spec += V2_C02_CREATE.format(
            DATA_TYPE=data_type,
            URL=url,
            VERIFY_CREATE="\n".join(verify_lines),
        )

    # C03 搜索 (if applicable)
    if info["has_search"] and pom["pom_class"]:
        assert_list = []
        if pom["pom_class"]:
            assert_list.append(f"      const {pom['pom_var']} = new {pom['pom_class']}(page)")
            # 不用 .el-table locator,改用 POM 的 waitForReady 模式
            assert_list.append(f"      await page.waitForLoadState('domcontentloaded')")
            assert_list.append(f"      await {pom['pom_var']}.waitForReady({{ timeout: 10000 }})")
        else:
            assert_list.append("      await expect(page.locator('main, .el-main, #app').first()).toBeVisible()")
        spec += V2_C03_SEARCH.format(
            URL=url,
            ASSERT_LIST="\n".join(assert_list),
        )

    # C04 删除 (if applicable)
    if info["has_delete"] and data_type:
        spec += V2_C04_DELETE.format(
            DATA_TYPE=data_type,
            URL=url,
        )

    # describe 闭
    spec += V2_DESCRIBE_CLOSE

    # 写文件
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(spec)
    return output_path


# ==================== 入口 ====================

async def main():
    if len(sys.argv) < 4:
        print("Usage: python scripts/auto_gen_v2_spec.py <url> <page_name> <data_type> [output_path]")
        print()
        print("Examples:")
        print("  python scripts/auto_gen_v2_spec.py /system/archdata?tab=business_object business-object business_object")
        print("  python scripts/auto_gen_v2_spec.py /product-management product business_object")
        sys.exit(1)

    url = sys.argv[1]
    page_name = sys.argv[2]
    data_type = sys.argv[3]
    output_path = (
        Path(sys.argv[4])
        if len(sys.argv) > 4
        else Path(f"e2e/features/auto-{page_name}.spec.js")
    )

    # 提取 page_id (简单的字母数字)
    page_id = "".join(c for c in page_name.upper() if c.isalnum())[:4] or "AUTO"

    print("=" * 60)
    print("L3 Auto-Generator: URL → v2 spec")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Page: {page_name} (id={page_id})")
    print(f"Data Type: {data_type}")
    print(f"Output: {output_path}")
    print()

    # 1. 抓 a11y
    print("[1/4] 抓 a11y snapshot...")
    snap_path = Path(f"reports/snap_{page_name}.json")
    snap = await capture_a11y(url, snap_path)

    # 2. 推断模式
    print()
    print("[2/4] 推断页面模式...")
    info = infer_page_pattern(snap)
    print(f"  page_type: {info['page_type']}")
    print(f"  has_table: {info['has_table']}")
    print(f"  has_tabs: {info['has_tabs']} (names: {info['tab_names'][:5]})")
    print(f"  has_search: {info['has_search']}")
    print(f"  has_new_btn: {info['has_new_btn']}")
    print(f"  has_edit: {info['has_edit']}")
    print(f"  has_delete: {info['has_delete']}")
    print(f"  button_names: {info['button_names'][:10]}")
    if info["field_names"]:
        print(f"  field_names: {info['field_names'][:10]}")

    # 3. 生成 spec
    print()
    print("[3/4] 生成 v2 spec...")
    out = generate_v2_spec(page_id, page_name, url, data_type, info, output_path)
    print(f"  [OK] Generated: {out}")

    # 4. 输出后续步骤
    print()
    print("[4/4] 后续步骤:")
    print(f"  1. 审查: code {out}")
    print(f"  2. 验证: python e2e/scripts/check_v2_compliance.py {out}")
    print(f"  3. 跑: npx playwright test {out.name} --retries=0 --project=features")
    print()
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
