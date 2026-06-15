"""端到端验证测试: 状态转换后页面是否实时更新"""
import sys, time, json
sys.path.insert(0, r"d:\filework\excel-to-diagram")
from test_helpers.browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI()
try:
    cli._ensure_browser()
    page = cli._page

    logs = []
    page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
    page.on("request", lambda req: logs.append(f"[REQ] {req.method} {req.url}") if '/api/' in req.url else None)
    page.on("pageerror", lambda err: logs.append(f"[PAGEERROR] {err}"))

    page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
    time.sleep(1)
    page.goto(f"http://localhost:3004/detail/user/1686?_={int(time.time())}", wait_until="networkidle")
    time.sleep(3)

    def grab_state_field():
        return page.evaluate("""() => {
            const fields = Array.from(document.querySelectorAll('.op-field'));
            const statusField = fields.find(f => {
                const label = f.querySelector('label');
                return label && label.textContent.trim().startsWith('状态');
            });
            if (!statusField) return { error: 'no field' };
            const tag = statusField.querySelector('.el-tag');
            const span = statusField.querySelector('.op-field-value');
            return {
                tag_text: tag ? tag.textContent.trim() : null,
                span_text: span ? span.textContent.trim() : null,
            };
        }""")

    print("=== STEP 1: Initial state ===")
    initial = grab_state_field()
    print(json.dumps(initial, ensure_ascii=False))

    print("\n=== STEP 2: Click 锁定 ===")
    page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const lockBtn = btns.find(b => (b.textContent || '').trim() === '锁定');
        if (lockBtn) lockBtn.click();
        return !!lockBtn;
    }""")
    time.sleep(1)
    page.evaluate("""() => {
        const dialogs = Array.from(document.querySelectorAll('.el-dialog, .el-message-box'));
        for (const d of dialogs) {
            if (!d.offsetParent) continue;
            const btns = Array.from(d.querySelectorAll('button'));
            const okBtn = btns.find(b => (b.textContent || '').trim() === '确定');
            if (okBtn) { okBtn.click(); return true; }
        }
        return false;
    }""")
    time.sleep(3)

    after_lock = grab_state_field()
    print("AFTER LOCK:", json.dumps(after_lock, ensure_ascii=False))

    print("\n=== STEP 3: Click 激活 ===")
    page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const actBtn = btns.find(b => {
            const t = (b.textContent || '').trim();
            return ['激活', 'Active', '启用', '解禁', '恢复'].includes(t);
        });
        if (actBtn) actBtn.click();
        return !!actBtn;
    }""")
    time.sleep(1)
    page.evaluate("""() => {
        const dialogs = Array.from(document.querySelectorAll('.el-dialog, .el-message-box'));
        for (const d of dialogs) {
            if (!d.offsetParent) continue;
            const btns = Array.from(d.querySelectorAll('button'));
            const okBtn = btns.find(b => (b.textContent || '').trim() === '确定');
            if (okBtn) { okBtn.click(); return true; }
        }
        return false;
    }""")
    time.sleep(3)

    after_activate = grab_state_field()
    print("AFTER ACTIVATE:", json.dumps(after_activate, ensure_ascii=False))

    print("\n=== Verification ===")
    i = initial.get('span_text') or initial.get('tag_text')
    a1 = after_lock.get('span_text') or after_lock.get('tag_text')
    a2 = after_activate.get('span_text') or after_activate.get('tag_text')
    print(f"INITIAL     : {i!r}")
    print(f"AFTER LOCK  : {a1!r}")
    print(f"AFTER ACTIV.: {a2!r}")
    pass_lock = (i != a1)
    pass_activate = (a1 != a2)
    print(f"\n[LOCK]  {'PASS' if pass_lock else 'FAIL'}: {i!r} -> {a1!r}")
    print(f"[ACTIV.] {'PASS' if pass_activate else 'FAIL'}: {a1!r} -> {a2!r}")

    print("\n=== DetailPage log (新代码关键日志) ===")
    for l in logs:
        if '[DetailPage]' in l:
            print(l)

    print("\n=== API calls ===")
    for l in logs:
        if '[REQ]' in l:
            print(l)
finally:
    cli.close()
