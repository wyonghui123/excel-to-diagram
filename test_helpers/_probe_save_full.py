# -*- coding: utf-8 -*-
"""
[临时探针 v3 2026-08-28] 严格复现：切 tab → 编辑 → 反勾选 → 保存
完整覆盖：
  1. 切到"权限配置"tab
  2. 进编辑（探查 PermissionConfigPanel 实例）
  3. 反勾选一个菜单项（探查 MenuPermissionMatrix.props.modelValue 实际值）
  4. 点保存（拦截 fetch + console）
  5. 全程监控 window.__watchTrigger / __flushOnExitDebug / __watchExitOld
  6. 对比 DB 前后状态
"""
import sys
sys.path.insert(0, r'D:\filework\excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import sqlite3
import json

DB_PATH = r'D:\filework\excel-to-diagram\meta\architecture.db'
BASE = 'http://localhost:3007'
ROLE_ID = 12666


def db_state():
    con = sqlite3.connect(DB_PATH)
    rows = [r[0] for r in con.execute(
        "SELECT menu_code FROM role_menu_permissions WHERE role_id=? ORDER BY menu_code",
        (ROLE_ID,)).fetchall()]
    con.close()
    return rows


# --- 重置 DB ---
print('=' * 60)
print('STEP 0: 重置 DB - 确保 user-permission 在勾选态')
con = sqlite3.connect(DB_PATH)
con.execute("DELETE FROM role_menu_permissions WHERE role_id=?", (ROLE_ID,))
# 让 user-permission 处于勾选态，arch-data 也勾选
con.execute("INSERT OR IGNORE INTO role_menu_permissions (role_id, menu_code) VALUES (?, ?)", (ROLE_ID, 'user-permission'))
con.execute("INSERT OR IGNORE INTO role_menu_permissions (role_id, menu_code) VALUES (?, ?)", (ROLE_ID, 'arch-data'))
con.commit()
con.close()
print('DB BEFORE:', db_state())
print('=' * 60)

with PlaywrightCLI(headless=False) as cli:
    page = cli.authenticated_navigate('/detail/role/12666', base_url=BASE, timeout=20000)
    page.wait_for_function('!!document.querySelector(".menu-permission-matrix")', timeout=20000)
    page.wait_for_timeout(1500)

    # === 拦截 fetch + XHR + console ===
    page.evaluate("""
        () => {
            window.__fl = []
            window.__xl = []
            window.__consoleLog = []
            const _f = window.fetch
            window.fetch = async function(i, init) {
                const u = (typeof i === 'string') ? i : i.url
                const m = (init && init.method) || 'GET'
                let b = null
                if (init && init.body) { try { b = JSON.parse(init.body) } catch(e) { b = init.body } }
                window.__fl.push({ u, m, b })
                console.log('[PROBE-FETCH]', m, u)
                return _f(i, init)
            }
            const _o = XMLHttpRequest.prototype.open
            const _s = XMLHttpRequest.prototype.send
            XMLHttpRequest.prototype.open = function(m, u) { this.__u = u; this.__m = m; return _o.apply(this, arguments) }
            XMLHttpRequest.prototype.send = function(b) {
                if (this.__u) window.__xl.push({ u: this.__u, m: this.__m, b })
                return _s.apply(this, arguments)
            }
            const _c = console.log
            console.log = function(...args) {
                try { window.__consoleLog.push(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ')) } catch(e) {}
                _c.apply(this, args)
            }
        }
    """)

    # === 1. 切到权限配置 tab ===
    print('\n' + '=' * 60)
    print('STEP 1: 切到权限配置 tab')
    tab_res = page.evaluate("""
        () => {
            const tabs = [...document.querySelectorAll('.el-tabs__item, [role=tab], .tab, button')]
                .filter(el => /权限配置/.test((el.textContent || '').trim()))
            const found = tabs[0]
            if (found) found.click()
            return { found: !!found, label: found?.textContent?.trim(), count: tabs.length }
        }
    """)
    print('TAB_SWITCH:', tab_res)
    page.wait_for_timeout(2000)
    # 验证 MenuPermissionMatrix 真的渲染了
    mpm = page.evaluate("""
        () => {
            const m = document.querySelector('.menu-permission-matrix')
            return { exists: !!m, classes: m?.className }
        }
    """)
    print('MPM:', mpm)

    # === 2. 进编辑 ===
    print('\n' + '=' * 60)
    print('STEP 2: 点编辑按钮')
    edit_res = page.evaluate("""
        () => {
            const b = [...document.querySelectorAll('button')].find(b => /^编辑$/.test((b.textContent || '').trim()))
            if (!b) return { found: false, all_buttons: [...document.querySelectorAll('button')].slice(0, 20).map(b => (b.textContent || '').trim()) }
            b.click()
            return { found: true }
        }
    """)
    print('EDIT:', edit_res)
    page.wait_for_function('!!document.querySelector(".menu-permission-matrix.mpm--editing")', timeout=8000)
    page.wait_for_timeout(800)

    # === 2.5 锁定 PermissionConfigPanel 组件实例 ===
    print('\n' + '=' * 60)
    print('STEP 2.5: 锁定 PermissionConfigPanel 组件实例')
    page.evaluate("""
        () => {
            const panels = [...document.querySelectorAll('.permission-config-panel')]
            window.__panels = []
            for (const p of panels) {
                let c = p.__vueParentComponent
                while (c && c.type?.__name !== 'PermissionConfigPanel') c = c.parent
                if (c) window.__panels.push(c)
            }
            // 同时找 MenuPermissionMatrix
            const mpms = [...document.querySelectorAll('.menu-permission-matrix')]
            window.__mpms = []
            for (const m of mpms) {
                let c = m.__vueParentComponent
                while (c && c.type?.__name !== 'MenuPermissionMatrix') c = c.parent
                if (c) window.__mpms.push(c)
            }
        }
    """)
    print('PANELS:', page.evaluate("() => window.__panels?.length"))
    print('MPMS:', page.evaluate("() => window.__mpms?.length"))

    # === 3. 反勾选 user-permission 菜单 ===
    print('\n' + '=' * 60)
    print('STEP 3: 反勾选 user-permission 菜单')
    click_res = page.evaluate("""
        () => {
            const cards = [...document.querySelectorAll('.menu-card, .mpm-menu-item, [class*=menu-item]')]
            // 找包含"用户与权限"或"user-permission"的菜单卡
            let target = null
            for (const c of cards) {
                const code = c.querySelector('[class*=code]')?.textContent || ''
                const txt = (c.textContent || '')
                if (/用户.*权限/.test(txt) || /user-permission/.test(code)) {
                    target = c; break
                }
            }
            if (!target) {
                // 兜底：取第一个可见 checkbox
                const cbs = [...document.querySelectorAll('.menu-permission-matrix input[type=checkbox]')]
                target = cbs[0]?.closest('.menu-card, .mpm-menu-item, label, div')
            }
            if (!target) return { found: false }
            const cb = target.querySelector('input[type=checkbox]')
            const before = cb?.checked
            const code = target.querySelector('[class*=code]')?.textContent || target.getAttribute('data-code') || ''
            cb?.click()
            return { found: true, before, after: cb?.checked, code }
        }
    """)
    print('CLICK:', click_res)
    page.wait_for_timeout(1000)

    # 探查实际 modelValue 状态
    mvm = page.evaluate("""
        () => {
            const m = window.__mpms?.[0]
            if (!m) return { found: false }
            const mv = m.props.modelValue
            return {
                found: true,
                len: mv?.length,
                assigned_set: (mv || []).filter(x => x?.assigned).map(x => x.menu_code),
                not_assigned_set: (mv || []).filter(x => !x?.assigned).map(x => x.menu_code),
            }
        }
    """)
    print('MV-AFTER-CLICK:', json.dumps(mvm, ensure_ascii=False, indent=2))

    # === 4. 触发 PermissionConfigPanel 的 save（绕过 ObjectPage 保存按钮，直接调组件方法）===
    print('\n' + '=' * 60)
    print('STEP 4a: 直接调 PermissionConfigPanel.save()（绕过 ObjectPage 保存按钮）')
    direct_save_res = page.evaluate("""
        () => {
            const p = window.__panels?.[0]
            if (!p) return { found: false }
            if (typeof p.exposed?.save !== 'function') return { found: true, has_save: false, exposed: Object.keys(p.exposed || {}) }
            p.exposed.save().then(r => {
                window.__directSaveResult = r
                console.log('[PROBE-DIRECT-SAVE-DONE]', JSON.stringify(r))
            }).catch(e => {
                window.__directSaveErr = String(e?.message || e)
                console.log('[PROBE-DIRECT-SAVE-ERR]', String(e?.message || e))
            })
            return { found: true, has_save: true }
        }
    """)
    print('DIRECT-SAVE:', direct_save_res)
    page.wait_for_timeout(3000)

    # 看 DB 状态
    print('DB AFTER DIRECT-SAVE:', db_state())

    # === 4b. 真实流程：进编辑 → 反勾选 → 点 ObjectPage 保存按钮 ===
    print('\n' + '=' * 60)
    print('STEP 4b: 真实流程 - 反勾选 + 点 ObjectPage 保存按钮')
    # 重置 DB（user-permission 再次勾选）+ 再次进编辑
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM role_menu_permissions WHERE role_id=?", (ROLE_ID,))
    con.execute("INSERT INTO role_menu_permissions (role_id, menu_code) VALUES (?, ?)", (ROLE_ID, 'arch-data'))
    con.execute("INSERT INTO role_menu_permissions (role_id, menu_code) VALUES (?, ?)", (ROLE_ID, 'user-permission'))
    con.commit(); con.close()
    print('DB RESET:', db_state())
    # 重新进编辑
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function('!!document.querySelector(".menu-permission-matrix")', timeout=20000)
    page.wait_for_timeout(1500)
    # 重新拦截
    page.evaluate("""
        () => {
            window.__fl = []; window.__consoleLog = []
            const _f = window.fetch
            window.fetch = async function(i, init) {
                const u = (typeof i === 'string') ? i : i.url
                const m = (init && init.method) || 'GET'
                window.__fl.push({ u, m })
                return _f(i, init)
            }
            const _c = console.log
            console.log = function(...args) {
                try { window.__consoleLog.push(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ')) } catch(e) {}
                _c.apply(this, args)
            }
        }
    """)
    # 重新锁定 panel/mpm
    page.evaluate("""
        () => {
            const panels = [...document.querySelectorAll('.permission-config-panel')]
            window.__panels = []
            for (const p of panels) {
                let c = p.__vueParentComponent
                while (c && c.type?.__name !== 'PermissionConfigPanel') c = c.parent
                if (c) window.__panels.push(c)
            }
            const mpms = [...document.querySelectorAll('.menu-permission-matrix')]
            window.__mpms = []
            for (const m of mpms) {
                let c = m.__vueParentComponent
                while (c && c.type?.__name !== 'MenuPermissionMatrix') c = c.parent
                if (c) window.__mpms.push(c)
            }
            window.__watchTrigger = null; window.__flushOnExitDebug = null; window.__watchExitOld = null
        }
    """)
    # 进编辑
    page.evaluate("""() => { const b=[...document.querySelectorAll('button')].find(b=>/^编辑$/.test((b.textContent||'').trim())); b&&b.click() }""")
    page.wait_for_function('!!document.querySelector(".menu-permission-matrix.mpm--editing")', timeout=8000)
    page.wait_for_timeout(800)
    # 重新锁定 panel 引用（reload 后 ref 变了）
    page.evaluate("""
        () => {
            const panels = [...document.querySelectorAll('.permission-config-panel')]
            window.__panels = []
            for (const p of panels) {
                let c = p.__vueParentComponent
                while (c && c.type?.__name !== 'PermissionConfigPanel') c = c.parent
                if (c) window.__panels.push(c)
            }
            const mpms = [...document.querySelectorAll('.menu-permission-matrix')]
            window.__mpms = []
            for (const m of mpms) {
                let c = m.__vueParentComponent
                while (c && c.type?.__name !== 'MenuPermissionMatrix') c = c.parent
                if (c) window.__mpms.push(c)
            }
        }
    """)
    print('PANELS after reload:', page.evaluate("() => window.__panels?.length"))
    print('MPMS after reload:', page.evaluate("() => window.__mpms?.length"))
    # 反勾选 user-permission
    page.evaluate("""
        () => {
            const m = window.__mpms?.[0]
            if (!m) return null
            const mv = m.props.modelValue
            const up = mv.find(x => x.menu_code === 'user-permission')
            if (up) up.assigned = false
        }
    """)
    # 检查 hasPendingChanges 是不是 true
    hpc = page.evaluate("""
        () => {
            const p = window.__panels?.[0]
            if (!p) return null
            return {
                setupState_keys: Object.keys(p.setupState || {}),
                isDirty: p.setupState?.isDirty?.value,
                matrixChanges_len: p.setupState?.matrixChanges?.value?.length,
                menus_len: p.setupState?.menus?.value?.length,
            }
        }
    """)
    print('PCP state before save:', json.dumps(hpc, ensure_ascii=False))
    # 点保存
    save_btn_res = page.evaluate("""
        () => {
            const s = [...document.querySelectorAll('button')].find(b => /^保存$/.test((b.textContent || '').trim()))
            if (!s) return { found: false }
            s.click()
            return { found: true }
        }
    """)
    print('SAVE-BTN:', save_btn_res)
    # 监控 5 秒
    for i in range(10):
        page.wait_for_timeout(500)
        st = page.evaluate("""
            () => {
                const p = window.__panels?.[0]
                const m = window.__mpms?.[0]
                return {
                    panel_editing: p?.props?.editing,
                    panel_flush: p?.props?.flushOnExit,
                    watchTrigger: window.__watchTrigger ? {now: window.__watchTrigger.now, before: window.__watchTrigger.before} : null,
                    flushDebug: window.__flushOnExitDebug ? 'YES' : null,
                    watchExitOld: window.__watchExitOld ? 'YES' : null,
                    cls: document.querySelector('.menu-permission-matrix')?.className,
                }
            }
        """)
        print(f'  +{(i+1)*0.5}s:', json.dumps(st, ensure_ascii=False))
    page.wait_for_timeout(2000)

    # === 5. 报告 ===
    print('\n' + '=' * 60)
    print('=== FINAL REPORT ===')
    fl = page.evaluate("() => window.__fl || []")
    print('FETCH calls:')
    for c in fl:
        body = c.get('b')
        body_str = ''
        if isinstance(body, dict):
            if 'menu_codes' in body:
                body_str = f' menu_codes={body["menu_codes"]}'
            elif 'cells' in body:
                body_str = f' cells={len(body["cells"])}'
        print(f"  {c['m']} {c['u']}{body_str}")

    print('\nCONSOLE log (filtered for PROBE):')
    logs = page.evaluate("() => window.__consoleLog || []")
    for l in logs[-30:]:
        if 'PROBE' in l or 'watchTrigger' in l or 'flushOnExit' in l or '保存' in l or 'PCP' in l or 'flush' in l.lower():
            print(f"  {l}")

    print('\nDB AFTER:', db_state())

    page.screenshot(path=r'D:\filework\excel-to-diagram\test_helpers\_probe_v3_final.png')
