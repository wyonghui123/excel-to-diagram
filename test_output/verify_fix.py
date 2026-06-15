"""Final verification screenshot of role detail page after fix."""
import sys, os
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

os.makedirs('test_output', exist_ok=True)

with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/detail/role/1803', wait_for_selector='.object-detail-page, .empty', timeout=15000)
    cli.wait_for_stable(5000)

    # Scroll to user group section
    cli.evaluate("""
        () => {
            const headings = Array.from(document.querySelectorAll('h2, h3, .section-title, [class*=anchor-tab]'));
            const target = headings.find(h => h.textContent?.includes('用户组'));
            if (target) target.scrollIntoView({ behavior: 'instant', block: 'start' });
        }
    """)
    cli.wait_for_stable(1500)
    cli.screenshot('test_output/role-detail-fixed.png', full_page=False)
    print('Screenshot saved: test_output/role-detail-fixed.png')

    # Final assertion
    result = cli.evaluate("""
        () => {
            const allText = Array.from(document.querySelectorAll('button, .row-action-trigger, .el-table__row button')).map(b => b.textContent?.trim()).filter(Boolean);
            const hasRemove = allText.some(t => t === '移除');
            return { hasRemove, allActionTexts: allText };
        }
    """)
    print('Final check:', result)