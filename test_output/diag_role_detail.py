"""Diagnose role detail page: user group section - safe version."""
import sys, os, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

os.makedirs('test_output', exist_ok=True)

with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/detail/role/1803', wait_for_selector='.object-detail-page, .empty', timeout=15000)
    cli.wait_for_stable(5000)
    cli.screenshot('test_output/role-detail-via-objectpage.png', full_page=True)
    print('Screenshot saved')

    # UI: collect tables and section info
    ui_dump = cli.evaluate("""
        () => {
            const tables = Array.from(document.querySelectorAll('.el-table, table'));
            return tables.map(t => ({
                cls: t.className,
                rows: t.querySelectorAll('tbody tr').length,
                headers: Array.from(t.querySelectorAll('th')).map(h => h.textContent?.trim()).filter(Boolean).slice(0, 15),
                firstRowActionIcons: Array.from(t.querySelectorAll('tbody tr:first-child .el-icon, tbody tr:first-child [class*=more], tbody tr:first-child button')).map(e => e.className || e.textContent?.trim()).filter(Boolean).slice(0, 10)
            })).slice(0, 5);
        }
    """)
    print('=== Tables ===')
    print(json.dumps(ui_dump or {}, ensure_ascii=False, indent=2))

    # Section labels
    sections_dump = cli.evaluate("""
        () => {
            const titles = Array.from(document.querySelectorAll('h2, h3, .section-title, .section-header, [class*=anchor-tab]')).map(e => e.textContent?.trim()).filter(t => t && t.length < 80);
            return titles.slice(0, 30);
        }
    """)
    print('=== Section Titles ===')
    print(json.dumps(sections_dump or {}, ensure_ascii=False, indent=2))

    # Check for "更新时间" column / operation column
    cols = cli.evaluate("""
        () => {
            const all = Array.from(document.querySelectorAll('th, .el-table__cell'));
            const texts = all.map(e => e.textContent?.trim()).filter(Boolean);
            const op = texts.filter(t => t.includes('操作') || t.includes('更新时间') || t.includes('更'));
            return { allHeaders: texts.slice(0, 50), operationLike: op };
        }
    """)
    print('=== Column Texts ===')
    print(json.dumps(cols or {}, ensure_ascii=False, indent=2))