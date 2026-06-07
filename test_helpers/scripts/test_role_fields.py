import sys
import os
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from test_helpers.browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True)

try:
    print("=" * 60)
    print("STEP 1: Login and navigate to system role (id=3)")
    print("=" * 60)
    cli.authenticated_navigate(
        '/system/role-detail/3',
        wait_for_selector='.object-page',
        timeout=15000
    )
    time.sleep(2)

    page = cli._ensure_browser()

    tags = page.evaluate("""() => {
        const tags = document.querySelectorAll('.el-tag');
        const result = [];
        for (const tag of tags) {
            let parent = tag.parentElement;
            let label = '';
            for (let i = 0; i < 3; i++) {
                if (!parent) break;
                const labelEl = parent.querySelector('label, .el-form-item__label, [class*="label"]');
                if (labelEl) { label = labelEl.textContent.trim(); break; }
                parent = parent.parentElement;
            }
            result.push({ label, tagText: tag.textContent.trim() });
        }
        return result;
    }""")

    is_system_tag = next((t for t in tags if t['label'] == '系统角色'), None)
    is_active_tag = next((t for t in tags if t['label'] == '启用状态'), None)
    print(f"EDIT system role - 系统角色: {is_system_tag['tagText'] if is_system_tag else 'NOT FOUND'}")
    print(f"EDIT system role - 启用状态: {is_active_tag['tagText'] if is_active_tag else 'NOT FOUND'}")

    print()
    print("=" * 60)
    print("STEP 2: Navigate to custom role (id=830) via SPA router")
    print("=" * 60)
    page.evaluate("() => { document.querySelector('#app').__vue_app__.config.globalProperties.$router.push('/system/role-detail/830') }")
    time.sleep(2)

    tags2 = page.evaluate("""() => {
        const tags = document.querySelectorAll('.el-tag');
        const result = [];
        for (const tag of tags) {
            let parent = tag.parentElement;
            let label = '';
            for (let i = 0; i < 3; i++) {
                if (!parent) break;
                const labelEl = parent.querySelector('label, .el-form-item__label, [class*="label"]');
                if (labelEl) { label = labelEl.textContent.trim(); break; }
                parent = parent.parentElement;
            }
            result.push({ label, tagText: tag.textContent.trim() });
        }
        return result;
    }""")

    is_system_tag2 = next((t for t in tags2 if t['label'] == '系统角色'), None)
    is_active_tag2 = next((t for t in tags2 if t['label'] == '启用状态'), None)
    print(f"EDIT custom role - 系统角色: {is_system_tag2['tagText'] if is_system_tag2 else 'NOT FOUND'}")
    print(f"EDIT custom role - 启用状态: {is_active_tag2['tagText'] if is_active_tag2 else 'NOT FOUND'}")

    print()
    print("=" * 60)
    print("STEP 3: Navigate to ADD mode via SPA router")
    print("=" * 60)
    page.evaluate("() => { document.querySelector('#app').__vue_app__.config.globalProperties.$router.push('/system/role-detail/new') }")
    time.sleep(3)

    add_fields = page.evaluate("""() => {
        const fields = document.querySelectorAll('.op-field');
        const result = [];
        for (const field of fields) {
            const label = field.querySelector('label')?.textContent?.trim() || '';
            const tag = field.querySelector('.el-tag');
            const span = field.querySelector('.op-field-value');
            const select = field.querySelector('.el-select');
            const switchEl = field.querySelector('.el-switch');
            const input = field.querySelector('input');

            let value = null;
            let type = 'unknown';
            if (tag) { value = tag.textContent.trim(); type = 'tag'; }
            else if (span) { value = span.textContent.trim(); type = 'span'; }
            else if (select) {
                type = 'select';
                const placeholder = select.querySelector('.el-select__placeholder');
                const selected = select.querySelector('.el-select__selected-item');
                value = {
                    placeholder: placeholder?.textContent?.trim() || null,
                    selected: selected?.textContent?.trim() || null,
                    allText: select.textContent.trim()
                };
            }
            else if (switchEl) {
                type = 'switch';
                value = switchEl.classList.contains('is-checked');
            }
            else if (input) {
                type = 'input';
                value = input.value;
            }
            result.push({ label, type, value });
        }
        return result;
    }""")
    print(f"ADD mode fields: {json.dumps(add_fields, indent=2, ensure_ascii=False)}")

    is_system_field = next((f for f in add_fields if '系统角色' in f.get('label', '')), None)
    is_active_field = next((f for f in add_fields if '启用状态' in f.get('label', '')), None)

    print(f"\nis_system field: {json.dumps(is_system_field, ensure_ascii=False)}")
    print(f"is_active field: {json.dumps(is_active_field, ensure_ascii=False)}")

    if is_system_field and is_system_field.get('type') == 'select':
        print("\nOpening is_system dropdown...")
        dropdown = cli.open_dropdown('label=系统角色', wait_ms=800)
        if dropdown.get('ok'):
            options = [opt['text'] for opt in dropdown.get('options', [])]
            print(f"is_system dropdown options: {options}")

    if is_active_field and is_active_field.get('type') == 'select':
        print("\nOpening is_active dropdown...")
        dropdown = cli.open_dropdown('label=启用状态', wait_ms=800)
        if dropdown.get('ok'):
            options = [opt['text'] for opt in dropdown.get('options', [])]
            print(f"is_active dropdown options: {options}")

    cli.screenshot('add_role_final.png')

finally:
    cli.close()

print()
print("=" * 60)
print("FINAL VERIFICATION")
print("=" * 60)
edit_system_ok = is_system_tag and is_system_tag['tagText'] == '系统角色'
edit_custom_ok = is_system_tag2 and is_system_tag2['tagText'] == '自定义角色'
edit_active_ok = is_active_tag and is_active_tag['tagText'] == '启用中'

add_system_ok = False
add_active_ok = False
if is_system_field:
    if is_system_field['type'] == 'select':
        sel = is_system_field.get('value', {}).get('selected')
        ph = is_system_field.get('value', {}).get('placeholder')
        add_system_ok = sel == '自定义角色' or ph == '自定义角色'
        print(f"ADD is_system: selected={sel}, placeholder={ph}")
    elif is_system_field['type'] == 'tag':
        add_system_ok = is_system_field['value'] == '自定义角色'
        print(f"ADD is_system: tag={is_system_field['value']}")
    else:
        print(f"ADD is_system: type={is_system_field['type']}, value={is_system_field['value']}")

if is_active_field:
    if is_active_field['type'] == 'select':
        sel = is_active_field.get('value', {}).get('selected')
        ph = is_active_field.get('value', {}).get('placeholder')
        add_active_ok = sel == '启用中' or ph == '启用中'
        print(f"ADD is_active: selected={sel}, placeholder={ph}")
    elif is_active_field['type'] == 'switch':
        add_active_ok = is_active_field['value'] == True
        print(f"ADD is_active: switch checked={is_active_field['value']}")
    else:
        print(f"ADD is_active: type={is_active_field['type']}, value={is_active_field['value']}")

print(f"\nEDIT system role (is_system=1): {'PASS' if edit_system_ok else 'FAIL'}")
print(f"EDIT custom role (is_system=0): {'PASS' if edit_custom_ok else 'FAIL'}")
print(f"EDIT active status: {'PASS' if edit_active_ok else 'FAIL'}")
print(f"ADD is_system default: {'PASS' if add_system_ok else 'FAIL'}")
print(f"ADD is_active default: {'PASS' if add_active_ok else 'FAIL'}")
print(f"\nALL PASS: {edit_system_ok and edit_custom_ok and edit_active_ok and add_system_ok and add_active_ok}")
