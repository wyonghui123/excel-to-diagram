# -*- coding: utf-8 -*-
"""前端验证骨架：统一的 Element Plus 选择器 + 常用动作，避免每次现写脚本靠猜。

用法：
    from test_helpers.ui_verify import session, open_hub_tab, open_row, open_tab, \\
        click_button, drawer, field, select_option, save_and_wait

    with session() as (cli, page):          # 默认 390x844 手机视口
        open_hub_tab(page, '计量单位组')
        open_row(page, 'QTY')
        open_tab(page, '组内换算')
        click_button(page, '新增换算')
        d = drawer(page, '新建')
        select_option(d, '换算单位', '测试箱')
        field(d, '换算率').locator('input').first.fill('12')
        click_button(d, '保存')

选择器来源：2026-10-24 实测移动端 DOM（见各常量注释）。
"""
from contextlib import contextmanager

from test_helpers.browser_auth_cli import PlaywrightCLI

SEL = {
    'app': '#app',
    # MOMP 聚合页左侧/右侧的业务对象切换按钮是普通 el-button
    'anchor_tab': 'button.anchor-tab',        # 详情页签（不是 el-tabs__item）
    'drawer': '.el-drawer',
    'drawer_title': '.el-drawer__title',
    'field': '.op-field',                     # 表单字段（不是 el-form-item）
    'select_wrapper': '.el-select__wrapper',  # Element Plus 2.9 下拉触发区
    'select_option': '.el-select-dropdown__item',
    'message_success': '.el-message--success',
    'message_error': '.el-message--error',
    'table_row': '.el-table__row',
}

MOBILE = {'width': 390, 'height': 844}
DESKTOP = {'width': 1280, 'height': 860}


@contextmanager
def session(mobile=True, start_path='/', timeout=30000):
    """登录 + 打开首页（动态路由就绪）+ 设定视口，退出时关闭浏览器。"""
    with PlaywrightCLI() as cli:
        page = cli.authenticated_navigate(
            start_path, wait_for_selector=SEL['app'], timeout=timeout)
        page.set_viewport_size(MOBILE if mobile else DESKTOP)
        page.wait_for_timeout(1200)
        yield cli, page


def goto(page, path, wait=2500, port=4173):
    """整页跳转。动态路由需先经过首页会话（见 session），故不要在 session 之前调用。"""
    url = path if path.startswith('http') else f'http://localhost:{port}{path}'
    page.goto(url, wait_until='domcontentloaded')
    page.wait_for_timeout(wait)
    return page


def click_js(locator):
    """绕过 header 遮罩/悬浮层拦截的点击（实测 Locator.click 常被拦截超时）。"""
    locator.first.evaluate('el => el.click()')
    return locator


def open_hub_tab(page, label):
    """MOMP 聚合页切换右侧业务对象（如 计量单位 / 计量单位组）。"""
    return click_js(page.locator('button', has_text=label))


def open_row(page, label):
    """移动端卡片或表格行进入详情：点含业务键文本的按钮/单元格。"""
    btn = page.locator('button', has_text=label)
    if btn.count():
        return click_js(btn)
    return click_js(page.locator(SEL['table_row'], has_text=label))


def open_tab(page, label):
    """详情抽屉内的页签。"""
    return click_js(page.locator(SEL['anchor_tab'], has_text=label))


def click_button(root, label):
    return click_js(root.locator('button', has_text=label))


def drawer(page, title_part):
    """按标题定位抽屉；返回精确匹配的最内层抽屉。"""
    d = page.locator(SEL['drawer'], has_text=title_part).last
    d.wait_for(state='attached', timeout=10000)
    return d


def field(root, label):
    """按标签定位表单字段容器。"""
    return root.locator(SEL['field'], has_text=label).first


def field_value(root, label):
    """读取字段当前值：下拉取占位文本，输入框取 value。"""
    f = field(root, label)
    ph = f.locator('.el-select__placeholder span').first
    if ph.count():
        return ph.inner_text()
    return f.locator('input').first.input_value()


def select_option(root, field_label, option_label):
    """打开下拉并选择选项（Element Plus 2.9 结构）。"""
    field(root, field_label).locator(SEL['select_wrapper']).first.evaluate('el => el.click()')
    root.page.wait_for_timeout(800)
    click_js(root.page.locator(SEL['select_option'], has_text=option_label))
    root.page.wait_for_timeout(400)


def save_and_wait(page, root=None, timeout=8000):
    """点保存并等待成功提示；返回 (ok, 文本)。"""
    click_button(root or page, '保存')
    try:
        page.wait_for_selector(SEL['message_success'], timeout=timeout)
        return True, page.locator(SEL['message_success']).first.inner_text()
    except Exception:
        err = page.locator(SEL['message_error'])
        text = err.first.inner_text() if err.count() else '未捕获到成功/错误提示'
        return False, text


def console_errors(cli, limit=8):
    """取最近的控制台告警/错误，用于断言无前端异常。"""
    logs = getattr(cli, '_console_errors', []) or []
    return logs[-limit:]
