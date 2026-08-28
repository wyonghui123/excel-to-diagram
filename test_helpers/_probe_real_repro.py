# -*- coding: utf-8 -*-
"""
[临时探针 v4 2026-08-28] 100% 模拟用户操作流程
关键修复:
  1. 不 reload 页面（避免污染 window 标记）
  2. 监控整段时间不中断（不清理 window 标记）
  3. 保存后等 5 秒，刷新页面看 DB 是否真的持久化
  4. 直接读 DB 看持久化结果
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


def reset_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM role_menu_permissions WHERE role_id=?", (ROLE_ID,))
    con.execute("INSERT INTO role_menu_permissions (role_id, menu_code) VALUES (?, ?)", (ROLE_ID, 'arch-data'))
    con.execute("INSERT INTO role_menu_permissions (role_id, menu_code) VALUES (?, ?)", (ROLE_ID, 'user-permission'))
    con.commit(); con.close()


# 重置 DB
reset_db()
print('DB RESET:', db_state())

with PlaywrightCLI(headless=False) as cli:
    page = cli.authenticated_navigate('/detail/role/12666', base_url=BASE, timeout=20000)
    page.wait_for_function('!!document.querySelector(".menu-permission-matrix")', timeout=20000)
    page.wait_for_timeout(2000)

    # 拦截 fetch + console（不拦截 reload/window）
    page.evaluate("""
        () => {
            window.__fl = []
            window.__consoleLog = []
            const _f = window.fetch
            window.fetch = async function(i, init) {
                const u = (typeof i === 'string') ? i : i.url
                const m = (init && init.method) || 'GET'
                let b = null
                if (init && init.body) { try { b = JSON.parse(init.body) } catch(e) { b = init.body } }
                window.__fl.push({ u, m, b })
                return _f(i, init)
            }
            const _c = console.log
            console.log = function(...args) {
                try { window.__consoleLog.push(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ')) } catch(e) {}
                _c.apply(this, args)
            }
        }
    """)

    # === STEP A: 切到权限配置 tab ===
    print('\n[A] 切到权限配置 tab')
    page.evaluate("""
        () => {
            const tabs = [...document.querySelectorAll('.el-tabs__item, [role=tab]')]
                .filter(el => /权限配置/.test((el.textContent || '').trim()))
            if (tabs[0]) tabs[0].click()
        }
    """)
    page.wait_for_timeout(2000)
    # 锁定组件实例（关键：保存到 __panel_save，用于保存前调）
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
            window.__watchTrigger = null
            window.__flushOnExitDebug = null
            window.__watchExitOld = null
        }
    """)
    print('PANELS:', page.evaluate("() => window.__panels?.length"))

    # === STEP B: 进编辑 ===
    print('\n[B] 进编辑')
    page.evaluate("""
        () => {
            const b = [...document.querySelectorAll('button')].find(b => /^编辑$/.test((b.textContent || '').trim()))
            if (b) b.click()
        }
    """)
    page.wait_for_function('!!document.querySelector(".menu-permission-matrix.mpm--editing")', timeout=8000)
    page.wait_for_timeout(800)
    print('  editing class:', page.evaluate("() => document.querySelector('.menu-permission-matrix')?.className"))

    # === STEP C: 通过 UI 点击反勾选 user-permission（不绕过）===
    print('\n[C] UI 点击反勾选 user-permission')
    # 找到"用户与权限管理"的菜单卡，再点 checkbox
    click_res = page.evaluate("""
        () => {
            const mpm = window.__mpms?.[0]
            const cards = [...document.querySelectorAll('.menu-permission-matrix .menu-card, .menu-permission-matrix [class*=menu-item]')]
            for (const c of cards) {
                if (/用户.*权限/.test(c.textContent || '')) {
                    const cb = c.querySelector('input[type=checkbox]')
                    const before = cb?.checked
                    cb?.click()
                    return { found: true, before, after: cb?.checked, label: (c.textContent || '').trim().slice(0, 30) }
                }
            }
            return { found: false }
        }
    """)
    print('  click:', click_res)
    page.wait_for_timeout(800)

    # 验证 modelValue 真的变了
    mv = page.evaluate("""
        () => {
            const m = window.__mpms?.[0]
            const mv = m?.props?.modelValue
            return {
                assigned: (mv || []).filter(x => x?.assigned).map(x => x.menu_code),
                not_assigned: (mv || []).filter(x => !x?.assigned).map(x => x.menu_code),
            }
        }
    """)
    print('  modelValue:', json.dumps(mv, ensure_ascii=False))

    # 验证 hasPendingChanges 是否真为 true（PCPanel 视角）
    hpc = page.evaluate("""
        () => {
            const p = window.__panels?.[0]
            if (!p) return null
            // 直接计算
            const isDirty = p.setupState?.isDirty?.value
            const matrixChanges = p.setupState?.matrixChanges?.value?.length || 0
            const hasPendingChanges = p.setupState?.hasPendingChanges?.value
            return { isDirty, matrixChanges, hasPendingChanges }
        }
    """)
    print('  hasPendingChanges:', hpc)

    # === STEP D: 点保存按钮（真实用户操作） ===
    print('\n[D] 点 ObjectPage 保存按钮')
    page.evaluate("""
        () => {
            const s = [...document.querySelectorAll('button')].find(b => /^保存$/.test((b.textContent || '').trim()))
            if (s) s.click()
        }
    """)
    # 监控 6 秒（每 500ms 采样一次）
    print('  monitoring 6s...')
    for i in range(12):
        page.wait_for_timeout(500)
        st = page.evaluate("""
            () => {
                const p = window.__panels?.[0]
                return {
                    panel_editing: p?.props?.editing,
                    panel_flush: p?.props?.flushOnExit,
                    watchTrigger: window.__watchTrigger ? `${window.__watchTrigger.now} <- ${window.__watchTrigger.before}` : null,
                    flushDebug: !!window.__flushOnExitDebug,
                    watchExitOld: !!window.__watchExitOld,
                }
            }
        """)
        print(f'    +{(i+1)*0.5}s: {json.dumps(st, ensure_ascii=False)}')
    page.wait_for_timeout(2000)

    # === STEP E: 看 DB 终态 ===
    print('\n[E] 保存后 DB 状态:')
    print('  DB AFTER SAVE:', db_state())

    # 看所有 fetch 请求
    fl = page.evaluate("() => window.__fl || []")
    print('\n  All FETCH calls:')
    for c in fl:
        body = c.get('b')
        body_str = ''
        if isinstance(body, dict):
            if 'menu_codes' in body:
                body_str = f' menu_codes={body["menu_codes"]}'
            elif 'cells' in body:
                body_str = f' cells={len(body["cells"])}'
        print(f"    {c['m']} {c['u']}{body_str}")

    # === STEP F: 刷新页面，看是否真的持久化 ===
    print('\n[F] 刷新页面验证持久化')
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function('!!document.querySelector(".menu-permission-matrix")', timeout=20000)
    page.wait_for_timeout(2000)
    page.evaluate("""
        () => {
            const tabs = [...document.querySelectorAll('.el-tabs__item, [role=tab]')]
                .filter(el => /权限配置/.test((el.textContent || '').trim()))
            if (tabs[0]) tabs[0].click()
        }
    """)
    page.wait_for_timeout(2000)
    # 重新锁定
    page.evaluate("""
        () => {
            const mpms = [...document.querySelectorAll('.menu-permission-matrix')]
            window.__mpms2 = []
            for (const m of mpms) {
                let c = m.__vueParentComponent
                while (c && c.type?.__name !== 'MenuPermissionMatrix') c = c.parent
                if (c) window.__mpms2.push(c)
            }
        }
    """)
    final_mv = page.evaluate("""
        () => {
            const m = window.__mpms2?.[0]
            const mv = m?.props?.modelValue
            return {
                assigned: (mv || []).filter(x => x?.assigned).map(x => x.menu_code),
                not_assigned: (mv || []).filter(x => !x?.assigned).map(x => x.menu_code),
            }
        }
    """)
    print('  After refresh, modelValue:', json.dumps(final_mv, ensure_ascii=False))
    print('  DB AFTER REFRESH:', db_state())

    # 截图
    page.screenshot(path=r'D:\filework\excel-to-diagram\test_helpers\_probe_v4_final.png')
    print('\n  saved screenshot: _probe_v4_final.png')
