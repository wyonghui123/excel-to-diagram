import sys
import os
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    results = {}
    cli = PlaywrightCLI(headless=True)

    try:
        print("=" * 60)
        print("STEP 1: Find test roles via API")
        print("=" * 60)

        login_result = cli.request(
            'http://localhost:3010/api/v1/auth/login',
            method='POST',
            data={'username': 'admin', 'password': 'admin123'}
        )
        if 'data' not in login_result:
            print(f"[FAIL] Login failed: {login_result}")
            return

        token = login_result['data']['token']
        print(f"[OK] Login success")

        req = urllib_request('http://localhost:3010/api/v2/bo/role?pageSize=50', token)
        roles_data = json.loads(urllib.request.urlopen(req).read().decode())
        roles = roles_data.get('data', {}).get('items', [])

        custom_role = None
        system_role = None
        for r in roles:
            if r.get('is_system') == 0 and not custom_role:
                custom_role = r
            if r.get('is_system') == 1 and not system_role:
                system_role = r

        print(f"Custom role: {custom_role['name'] if custom_role else 'NOT FOUND'} (id={custom_role['id'] if custom_role else 'N/A'})")
        print(f"System role: {system_role['name'] if system_role else 'NOT FOUND'} (id={system_role['id'] if system_role else 'N/A'})")

        results['custom_role'] = custom_role['name'] if custom_role else None
        results['system_role'] = system_role['name'] if system_role else None

        print()
        print("=" * 60)
        print("STEP 2: Test EDIT mode - Custom Role (is_system=0)")
        print("=" * 60)

        if custom_role:
            test_edit_mode(cli, custom_role, 'custom', results)
        else:
            print("[SKIP] No custom role found")

        print()
        print("=" * 60)
        print("STEP 3: Test EDIT mode - System Role (is_system=1)")
        print("=" * 60)

        if system_role:
            test_edit_mode(cli, system_role, 'system', results)
        else:
            print("[SKIP] No system role found")

        print()
        print("=" * 60)
        print("STEP 4: Test ADD mode - Default values")
        print("=" * 60)

        test_add_mode(cli, results)

    finally:
        cli.close()

    print()
    print("=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(json.dumps(results, indent=2, ensure_ascii=False))

    all_pass = (
        results.get('edit_custom_is_system_label') == '自定义角色'
        and results.get('edit_system_is_system_label') == '系统角色'
        and results.get('add_is_system_default') == '自定义角色'
        and results.get('add_is_active_default') == '启用中'
    )
    print(f"\nALL PASS: {all_pass}")


def urllib_request(url, token):
    req = urllib.request.Request(url)
    req.add_header('Authorization', f'Bearer {token}')
    return req


def test_edit_mode(cli, role, role_type, results):
    role_id = role['id']
    path = f'/system/role-detail/{role_id}'

    print(f"[NAV] Navigating to {path}")
    cli.authenticated_navigate(
        path,
        wait_for_selector='.op-field, .el-descriptions__cell',
        timeout=15000
    )
    time.sleep(1)

    screenshot_name = f'edit_{role_type}_role.png'
    cli.screenshot(screenshot_name)
    print(f"[OK] Screenshot saved: {screenshot_name}")

    is_system_text = cli.evaluate("""
        (() => {
            const fields = document.querySelectorAll('.op-field');
            for (const field of fields) {
                const label = field.querySelector('label');
                if (label && label.textContent.includes('系统角色')) {
                    const tag = field.querySelector('.el-tag');
                    const span = field.querySelector('.op-field-value');
                    if (tag) return { type: 'tag', text: tag.textContent.trim() };
                    if (span) return { type: 'span', text: span.textContent.trim() };
                    return { type: 'unknown', text: field.textContent.trim() };
                }
            }
            return { type: 'not_found', text: null };
        })()
    """)
    print(f"[RESULT] is_system display: {json.dumps(is_system_text, ensure_ascii=False)}")
    results[f'edit_{role_type}_is_system_label'] = is_system_text.get('text')

    is_active_text = cli.evaluate("""
        (() => {
            const fields = document.querySelectorAll('.op-field');
            for (const field of fields) {
                const label = field.querySelector('label');
                if (label && label.textContent.includes('启用状态')) {
                    const tag = field.querySelector('.el-tag');
                    const span = field.querySelector('.op-field-value');
                    if (tag) return { type: 'tag', text: tag.textContent.trim() };
                    if (span) return { type: 'span', text: span.textContent.trim() };
                    return { type: 'unknown', text: field.textContent.trim() };
                }
            }
            return { type: 'not_found', text: null };
        })()
    """)
    print(f"[RESULT] is_active display: {json.dumps(is_active_text, ensure_ascii=False)}")
    results[f'edit_{role_type}_is_active_label'] = is_active_text.get('text')


def test_add_mode(cli, results):
    path = '/system/role-detail/new'

    print(f"[NAV] Navigating to {path}")
    cli.authenticated_navigate(
        path,
        wait_for_selector='.op-field, .el-select',
        timeout=15000
    )
    time.sleep(2)

    cli.screenshot('add_role.png')
    print(f"[OK] Screenshot saved: add_role.png")

    is_system_value = cli.evaluate("""
        (() => {
            const fields = document.querySelectorAll('.op-field');
            for (const field of fields) {
                const label = field.querySelector('label');
                if (label && label.textContent.includes('系统角色')) {
                    const select = field.querySelector('.el-select');
                    if (select) {
                        const input = select.querySelector('input');
                        const placeholder = input ? input.getAttribute('placeholder') : null;
                        const selectedLabel = select.querySelector('.el-select__selected-item, .el-select__placeholder');
                        const allText = select.textContent.trim();
                        return {
                            type: 'select',
                            placeholder: placeholder,
                            selectedText: selectedLabel ? selectedLabel.textContent.trim() : null,
                            allText: allText
                        };
                    }
                    const tag = field.querySelector('.el-tag');
                    const span = field.querySelector('.op-field-value');
                    if (tag) return { type: 'tag', text: tag.textContent.trim() };
                    if (span) return { type: 'span', text: span.textContent.trim() };
                    return { type: 'unknown', text: field.textContent.trim() };
                }
            }
            return { type: 'not_found', text: null };
        })()
    """)
    print(f"[RESULT] is_system in ADD mode: {json.dumps(is_system_value, ensure_ascii=False)}")
    results['add_is_system_value'] = is_system_value

    is_active_value = cli.evaluate("""
        (() => {
            const fields = document.querySelectorAll('.op-field');
            for (const field of fields) {
                const label = field.querySelector('label');
                if (label && label.textContent.includes('启用状态')) {
                    const select = field.querySelector('.el-select');
                    if (select) {
                        const input = select.querySelector('input');
                        const placeholder = input ? input.getAttribute('placeholder') : null;
                        const selectedLabel = select.querySelector('.el-select__selected-item, .el-select__placeholder');
                        const allText = select.textContent.trim();
                        return {
                            type: 'select',
                            placeholder: placeholder,
                            selectedText: selectedLabel ? selectedLabel.textContent.trim() : null,
                            allText: allText
                        };
                    }
                    const switchEl = field.querySelector('.el-switch');
                    if (switchEl) {
                        const isChecked = switchEl.classList.contains('is-checked');
                        return { type: 'switch', checked: isChecked };
                    }
                    return { type: 'unknown', text: field.textContent.trim() };
                }
            }
            return { type: 'not_found', text: null };
        })()
    """)
    print(f"[RESULT] is_active in ADD mode: {json.dumps(is_active_value, ensure_ascii=False)}")
    results['add_is_active_value'] = is_active_value

    form_data = cli.evaluate("""
        (() => {
            const app = document.querySelector('#app').__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            const stores = Array.from(pinia._s.entries());
            let roleData = null;
            for (const [name, store] of stores) {
                if (store.$id === 'role' || (store.role && typeof store.role === 'object')) {
                    roleData = store.role;
                    break;
                }
            }
            if (!roleData) {
                const vueComps = document.querySelectorAll('[data-v-inspector]');
                for (const el of vueComps) {
                    const vn = el.__vue_parent_component;
                    if (vn && vn.setupState && vn.setupState.role) {
                        roleData = vn.setupState.role;
                        break;
                    }
                }
            }
            if (roleData) {
                return { is_system: roleData.is_system, is_active: roleData.is_active };
            }
            return null;
        })()
    """)
    print(f"[RESULT] Form data: {json.dumps(form_data, ensure_ascii=False)}")
    results['add_form_data'] = form_data

    if is_system_value.get('type') == 'select':
        print("\n[CHECK] Opening is_system dropdown to verify options...")
        dropdown_result = cli.open_dropdown('label=系统角色', wait_ms=800)
        if dropdown_result.get('ok'):
            options = [opt['text'] for opt in dropdown_result.get('options', [])]
            print(f"[RESULT] is_system dropdown options: {options}")
            results['add_is_system_options'] = options
        else:
            print(f"[WARN] Could not open dropdown: {dropdown_result.get('error')}")

    if is_active_value.get('type') == 'select':
        print("\n[CHECK] Opening is_active dropdown to verify options...")
        dropdown_result = cli.open_dropdown('label=启用状态', wait_ms=800)
        if dropdown_result.get('ok'):
            options = [opt['text'] for opt in dropdown_result.get('options', [])]
            print(f"[RESULT] is_active dropdown options: {options}")
            results['add_is_active_options'] = options
        else:
            print(f"[WARN] Could not open dropdown: {dropdown_result.get('error')}")


if __name__ == '__main__':
    import urllib.request
    main()
