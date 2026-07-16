#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
alert_monitor.py - Agent 端 IM 告警监控 (V007.58 2026-07-15)

设计动机:
    yonaa 服务器在阿里云 air-gapped 环境, 无法直连公网 IM (飞书/钉钉/微信)
    所以告警推送走 agent 端 (公司电脑, 有公网):
      1. agent 每 5 分钟调 yonaa log_service 的 /api/check 或 probe 工具
      2. 发现异常 → 推 IM webhook (飞书/钉钉/微信)
      3. 正常时静默 (不打扰)

支持 3 种 IM:
- 飞书 (Lark / Feishu) - 推荐 (国内最稳定)
- 钉钉 (Dingtalk)
- 企业微信 (WeCom)

用法:
    # 1. 一次性跑 (调试用)
    python tools/alert_monitor.py --check-now

    # 2. 守护模式 (每 5 分钟)
    python tools/alert_monitor.py --daemon

    # 3. 模拟一次失败
    python tools/alert_monitor.py --simulate-fail

    # 4. 测试 IM 推送
    python tools/alert_monitor.py --test-im

配置:
    配置文件: tools/alert_monitor_config.json (自动创建)
    飞书 webhook: https://open.feishu.cn/open-apis/bot/v2/hook/<token>
    钉钉 webhook: https://oapi.dingtalk.com/robot/send?access_token=<token>
    企业微信 webhook: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<key>

退出码:
    0 - 全部健康
    1 - 发现告警
    2 - 配置错误
    3 - 网络错误 (yonaa 连不上)
"""
import argparse
import hashlib
import hmac
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

# 配置文件路径 (Windows-friendly)
DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'alert_monitor_config.json')

# yonaa 端点 (与 core_service / log_service 通信)
# yonaa 端点 (与 core_service / log_service 通信)
# 注意: core_service 用 401/403 (认证失败) 也算 OK, 因为端口活着
YONAA_PROBE = {
    'log_service_prod': ('172.20.59.7', 9101, '/api/health'),
    'log_service_staging': ('172.20.59.7', 19101, '/api/health'),
    'core_service_prod': ('172.20.59.7', 9200, '/'),  # core_service 没 /api/health, 用 /
    'core_service_staging': ('172.20.59.7', 19200, '/'),
    'frontend': ('172.20.59.7', 8081, '/'),
    'backend': ('172.20.59.7', 3011, '/health'),
    'observability': ('172.20.59.7', 9201, '/'),
}

# 复用的 probe 函数 (从 remote_capability_probe 借)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from remote_capability_probe import probe_port, check_log_service, check_systemd
    HAS_PROBE = True
except ImportError:
    HAS_PROBE = False


def log(msg: str):
    """统一 log 输出"""
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] {msg}', flush=True)


def load_config(path: str = DEFAULT_CONFIG) -> dict:
    """加载配置"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log(f'[ERROR] load config failed: {e}')
        return {}


def save_config(cfg: dict, path: str = DEFAULT_CONFIG):
    """保存配置"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    log(f'[OK] config saved to {path}')


# ====== 飞书 ======
def feishu_sign(secret: str, timestamp: str) -> str:
    string_to_sign = f'{timestamp}\n{secret}'
    hmac_code = hmac.new(string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode('utf-8')


def send_feishu(webhook: str, title: str, content: str, secret: str = '', at_all: bool = False) -> tuple:
    """发飞书 webhook"""
    headers = {'Content-Type': 'application/json'}
    data = {
        'msg_type': 'interactive',
        'card': {
            'header': {
                'title': {'tag': 'plain_text', 'content': title[:50]},
                'template': 'red' if ('FAIL' in title or 'DEAD' in title) else 'blue',
            },
            'elements': [
                {'tag': 'markdown', 'content': content[:3000]},
            ],
        },
    }
    if at_all:
        data['card']['elements'].append({'tag': 'at', 'at_all': True})
    if secret:
        ts = str(int(time.time()))
        data['timestamp'] = ts
        data['sign'] = feishu_sign(secret, ts)

    req = urllib.request.Request(webhook, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode('utf-8')
            try:
                j = json.loads(body)
                if j.get('StatusCode') == 0 or j.get('code') == 0:
                    return True, body[:200]
                return False, body[:300]
            except json.JSONDecodeError:
                return resp.status == 200, body[:200]
    except urllib.error.URLError as e:
        return False, f'URLError: {e}'


# ====== 钉钉 ======
def dingtalk_sign(secret: str) -> tuple:
    ts = str(round(time.time() * 1000))
    string_to_sign = f'{ts}\n{secret}'
    hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    return ts, urllib.parse.quote_plus(base64.b64encode(hmac_code))


def send_dingtalk(webhook: str, title: str, content: str, secret: str = '', at_all: bool = False) -> tuple:
    data = {
        'msgtype': 'markdown',
        'markdown': {
            'title': title[:50],
            'text': f'## {title}\n\n{content}\n\n---\n{_footer()}',
        },
    }
    if at_all:
        data['at'] = {'isAtAll': True}
    if secret:
        ts, sign = dingtalk_sign(secret)
        sep = '&' if '?' in webhook else '?'
        webhook = f'{webhook}{sep}timestamp={ts}&sign={sign}'

    headers = {'Content-Type': 'application/json'}
    req = urllib.request.Request(webhook, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode('utf-8')
            try:
                j = json.loads(body)
                return j.get('errcode') == 0, body[:300]
            except json.JSONDecodeError:
                return resp.status == 200, body[:200]
    except urllib.error.URLError as e:
        return False, f'URLError: {e}'


# ====== 企业微信 ======
def send_wecom(webhook: str, title: str, content: str, secret: str = '', at_all: bool = False) -> tuple:
    data = {
        'msgtype': 'markdown',
        'markdown': {
            'content': f'## {title}\n{content}\n\n{_footer()}',
        },
    }
    if at_all:
        data['markdown']['mentioned_list'] = ['@all']

    headers = {'Content-Type': 'application/json'}
    req = urllib.request.Request(webhook, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode('utf-8')
            try:
                j = json.loads(body)
                return j.get('errcode') == 0, body[:300]
            except json.JSONDecodeError:
                return resp.status == 200, body[:200]
    except urllib.error.URLError as e:
        return False, f'URLError: {e}'


def _footer() -> str:
    return f'<sub>yonaa agent alert · {time.strftime("%Y-%m-%d %H:%M:%S")}</sub>'


# ====== 飞书应用机器人 API (V007.59 2026-07-15) ======
# 走 tenant_access_token + im/v1/messages API
# 比 webhook 优势: 不被企业管理员禁, 可发丰富卡片, 可 @具体人
_TOKEN_CACHE = {'token': '', 'expire_at': 0}


def _lark_get_token(app_id: str, app_secret: str) -> str:
    """拿 tenant_access_token (带缓存, 提前 5 分钟过期)"""
    if _TOKEN_CACHE['token'] and time.time() < _TOKEN_CACHE['expire_at']:
        return _TOKEN_CACHE['token']

    url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
    data = json.dumps({'app_id': app_id, 'app_secret': app_secret}).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as r:
        body = json.loads(r.read().decode())
    if body.get('code') != 0:
        raise RuntimeError(f'lark get token fail: code={body.get("code")} msg={body.get("msg")}')
    _TOKEN_CACHE['token'] = body['tenant_access_token']
    _TOKEN_CACHE['expire_at'] = time.time() + body.get('expire', 7200) - 300  # 提前 5 分钟
    return _TOKEN_CACHE['token']


def _lark_list_chats(app_id: str, app_secret: str) -> list:
    """列出应用机器人加入的所有群 (用来找 chat_id)"""
    token = _lark_get_token(app_id, app_secret)
    url = 'https://open.feishu.cn/open-apis/im/v1/chats?page_size=50'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=10) as r:
        body = json.loads(r.read().decode())
    if body.get('code') != 0:
        raise RuntimeError(f'lark list chats fail: {body.get("msg")}')
    return body.get('data', {}).get('items', [])


def send_lark_app(app_id: str, app_secret: str, chat_id: str, title: str, content: str, at_all: bool = False) -> tuple:
    """发飞书应用机器人消息 (interactive card)"""
    try:
        token = _lark_get_token(app_id, app_secret)
    except Exception as e:
        return False, f'lark get token fail: {e}'

    url = f'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id'

    # 内容 (interactive card) - V007.59 修复: @所有人 在 markdown 里用 <at id=all></at>
    md_content = content[:3000]
    if at_all:
        md_content = f'<at id=all></at> {md_content}'

    card_content = {
        'config': {'wide_screen_mode': True},
        'header': {
            'title': {'tag': 'plain_text', 'content': title[:50]},
            'template': 'red' if ('ALERT' in title or 'FAIL' in title or 'DEAD' in title) else 'blue',
        },
        'elements': [
            {'tag': 'div', 'text': {'tag': 'lark_md', 'content': md_content}},
            {'tag': 'hr'},
            {'tag': 'note', 'elements': [{'tag': 'plain_text', 'content': f'yonaa agent alert · {time.strftime("%Y-%m-%d %H:%M:%S")}'}]},
        ],
    }

    data = {
        'receive_id': chat_id,
        'msg_type': 'interactive',
        'content': json.dumps(card_content, ensure_ascii=False),
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={
            'Content-Type': 'application/json; charset=utf-8',
            'Authorization': f'Bearer {token}',
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
            if body.get('code') == 0:
                return True, f'msg_id={body.get("data", {}).get("message_id", "?")}'
            return False, f'code={body.get("code")} msg={body.get("msg")}'
    except urllib.error.HTTPError as e:
        # 飞书 4xx 错误带详细 reason
        try:
            err_body = e.read().decode()
            err_j = json.loads(err_body)
            return False, f'HTTP {e.code} code={err_j.get("code")} msg={err_j.get("msg")}'
        except Exception:
            return False, f'HTTPError {e.code}: {e.reason}'
    except urllib.error.URLError as e:
        return False, f'URLError: {e}'
    except Exception as e:
        return False, f'{type(e).__name__}: {e}'


def _get_lark_cred_with_hkcu_fallback(name: str) -> str:
    """凭证获取优先级: env var > HKCU\\Environment 注册表 > 空

    Task Scheduler 启动的 bat 进程会继承系统 env, 但 LARK_* 是写在 HKCU 下的,
    不会自动出现在系统 env 里. 所以这里加 HKCU 回退.
    """
    v = os.environ.get(name, '')
    if v:
        return v
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment') as k:
            val, _ = winreg.QueryValueEx(k, name)
            return str(val) if val else ''
    except Exception:
        return ''


def send_im(im_type: str, cfg: dict, title: str, content: str, at_all: bool = False) -> tuple:
    """统一发送入口"""
    im_cfg = cfg.get('im', {}).get(im_type, {})
    webhook = im_cfg.get('webhook', '')
    secret = im_cfg.get('secret', '')

    # 飞书应用机器人走独立路径 (V007.59)
    # 凭证优先级: env var > HKCU 注册表 > config 占位符
    if im_type == 'lark_app':
        app_id     = _get_lark_cred_with_hkcu_fallback('LARK_APP_ID')     or im_cfg.get('app_id', '')
        app_secret = _get_lark_cred_with_hkcu_fallback('LARK_APP_SECRET') or im_cfg.get('app_secret', '')
        chat_id    = _get_lark_cred_with_hkcu_fallback('LARK_CHAT_ID')    or im_cfg.get('chat_id', '')
        if not all([app_id, app_secret, chat_id]):
            return False, 'lark_app 需要 app_id + app_secret + chat_id (可在 HKCU 环境变量 或 config 配)'
        if '<' in app_id or '替换' in app_id:
            return False, f'lark_app 凭证未配置 (仍是占位符)'
        return send_lark_app(app_id, app_secret, chat_id, title, content, at_all)

    if not webhook:
        return False, f'no webhook configured for {im_type}'
    if '<' in webhook or '>' in webhook or '替换' in webhook:
        return False, f'webhook URL 未配置 (仍是占位符: {webhook[:60]})'

    if im_type == 'feishu':
        return send_feishu(webhook, title, content, secret, at_all)
    elif im_type == 'dingtalk':
        return send_dingtalk(webhook, title, content, secret, at_all)
    elif im_type == 'wecom':
        return send_wecom(webhook, title, content, secret, at_all)
    else:
        return False, f'unknown IM type: {im_type}'


# ====== 健康检查 ======
def check_yonaa_services() -> list:
    """检查 yonaa 所有关键服务 (端口活 + 端点可达)"""
    results = []
    for name, (host, port, path_) in YONAA_PROBE.items():
        url = f'http://{host}:{port}{path_}'
        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=4) as resp:
                status = resp.status
                # 200 OK, 3xx redirect, 401/403 auth-required = 端口活着 (只是没权限/路径错)
                ok = status < 500
                results.append({'name': name, 'host': host, 'port': port, 'status': status, 'ok': ok, 'msg': f'HTTP {status}'})
        except urllib.error.HTTPError as e:
            # 4xx (404, 401, 403) = 服务活着, 路径不对 = OK (端口在 listen)
            ok = 400 <= e.code < 500
            results.append({'name': name, 'host': host, 'port': port, 'status': e.code, 'ok': ok, 'msg': f'HTTP {e.code} ({"端点不对但端口在" if ok else "FAIL"})'})
        except Exception as e:
            results.append({'name': name, 'host': host, 'port': port, 'status': 0, 'ok': False, 'msg': f'{type(e).__name__}: {str(e)[:80]}'})
    return results


def check_systemd_via_agent() -> list:
    """通过 probe --check-systemd 检查 systemd"""
    if not HAS_PROBE:
        return []
    try:
        # check_systemd 返回 exit code (0=OK, 1/2=fail)
        # 我们重新调 probe 拿端口状态
        results = []
        log_ports = [
            (9101, 'prod log_service'),
            (19101, 'staging log_service'),
        ]
        for port, label in log_ports:
            r = probe_port(port, label)
            ok = r.get('reachable') and 200 <= r.get('status', 0) < 500
            results.append({'name': f'systemd:{label}', 'port': port, 'ok': ok, 'msg': f'status={r.get("status")}' if ok else r.get('reason', 'unreachable')})
        return results
    except Exception as e:
        return [{'name': 'check_systemd', 'ok': False, 'msg': f'{e}'}]


def check_log_service_via_agent() -> list:
    """通过 probe --check-log-service 检查 (端口活 + 进程在)"""
    if not HAS_PROBE:
        return []
    try:
        results = []
        log_ports = [
            (9101, 'prod log_service'),
            (19101, 'staging log_service'),
        ]
        alive = 0
        for port, label in log_ports:
            r = probe_port(port, label)
            ok = r.get('reachable') and 200 <= r.get('status', 0) < 500
            results.append({'name': f'log_service:{label}', 'port': port, 'ok': ok, 'msg': f'status={r.get("status")}' if ok else r.get('reason', 'unreachable')})
            if ok:
                alive += 1
        # 额外: 进程检查
        try:
            from yonaa_exec import yexec
            r = yexec('bash -c "ps -ef | grep log_service | grep -v grep || echo NO_PROCESS"',
                      port=9200, secret='prod_write', timeout=10)
            out = (r.get('stdout') or '').strip()
            if 'NO_PROCESS' in out or not out:
                results.append({'name': 'log_service:process', 'port': 0, 'ok': False, 'msg': 'no log_service process on server'})
        except Exception as e:
            pass
        return results
    except Exception as e:
        return [{'name': 'check_log_service', 'ok': False, 'msg': f'{e}'}]


def format_alert(failed: list) -> tuple:
    """格式化告警消息"""
    title = f'[ALERT] yonaa {len(failed)} 服务异常'

    lines = ['**yonaa 端服务异常告警**', '']
    for f in failed:
        ok_mark = '✓' if f.get('ok') else '✗'
        name = f.get('name', '?')
        msg = f.get('msg', '?')
        port = f.get('port', '')
        lines.append(f'- {ok_mark} **{name}** (port {port}): {msg}')
    lines.append('')
    lines.append(f'检测时间: {time.strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append('检测节点: agent (公司电脑)')

    return title, '\n'.join(lines)


def format_recovery(recovered: list) -> tuple:
    """格式化恢复消息"""
    title = f'[OK] yonaa 全部恢复 ({len(recovered)})'
    lines = ['**yonaa 端服务已恢复**', '']
    for f in recovered:
        lines.append(f'- ✓ {f.get("name", "?")} (port {f.get("port", "?")})')
    lines.append('')
    lines.append(f'恢复时间: {time.strftime("%Y-%m-%d %H:%M:%S")}')
    return title, '\n'.join(lines)


# ====== 状态去重 ======
def load_state(state_path: str) -> dict:
    if not os.path.exists(state_path):
        return {'failed': [], 'last_alert_ts': 0}
    try:
        with open(state_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'failed': [], 'last_alert_ts': 0}


def save_state(state: dict, state_path: str):
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def run_once(cfg: dict, state_path: str) -> int:
    """跑一次检查"""
    log('[CHECK] 开始 yonaa 健康检查...')

    # 1. 端口探测
    port_results = check_yonaa_services()
    log(f'  ports: {sum(1 for r in port_results if r["ok"])}/{len(port_results)} OK')

    # 2. systemd 检查 (V007.57)
    sys_results = check_systemd_via_agent()
    log(f'  systemd: {sys_results}')

    # 3. log_service 检查
    log_results = check_log_service_via_agent()
    log(f'  log_service: {log_results}')

    # 合并失败
    all_results = port_results + sys_results + log_results
    failed = [r for r in all_results if not r.get('ok')]
    failed_keys = {f'{r["name"]}:{r.get("port", "")}' for r in failed}

    # 状态对比
    state = load_state(state_path)
    prev_failed_keys = set(state.get('failed_keys', []))

    cooldown_sec = cfg.get('alert', {}).get('cooldown_sec', 600)  # 默认 10 分钟
    now = time.time()
    last_alert_ts = state.get('last_alert_ts', 0)

    if failed:
        # 有失败
        new_failed = failed_keys - prev_failed_keys
        recovered = prev_failed_keys - failed_keys

        # 推送新失败
        if new_failed and (now - last_alert_ts) > cooldown_sec:
            title, content = format_alert(failed)
            im_type = cfg.get('im', {}).get('default', 'feishu')
            at_all = cfg.get('alert', {}).get('at_all_on_fail', False)
            ok, body = send_im(im_type, cfg, title, content, at_all)
            log(f'  [IM] {im_type}: {"OK" if ok else "FAIL: " + body}')
            state['last_alert_ts'] = now

        elif not new_failed and (now - last_alert_ts) < cooldown_sec:
            log('  [COOLDOWN] 失败未变化, 但仍在冷却期内, 不重发')

        elif not new_failed:
            log('  [SKIP] 失败未变化, 不重复推送')

        # 恢复通知 (只在 cooldown 之外)
        if recovered and (now - last_alert_ts) > cooldown_sec:
            recovered_list = [r for r in all_results if f'{r["name"]}:{r.get("port", "")}' in recovered]
            title, content = format_recovery(recovered_list)
            im_type = cfg.get('im', {}).get('default', 'feishu')
            at_all = cfg.get('alert', {}).get('at_all_on_recovery', False)
            ok, body = send_im(im_type, cfg, title, content, at_all)
            log(f'  [RECOVERY IM] {im_type}: {"OK" if ok else "FAIL: " + body}')

        state['failed_keys'] = list(failed_keys)
        save_state(state, state_path)

        return 1  # 有告警
    else:
        # 全部正常
        if prev_failed_keys:
            # 之前有失败, 现在恢复
            recovered_list = [r for r in all_results]
            title, content = format_recovery(recovered_list)
            im_type = cfg.get('im', {}).get('default', 'feishu')
            at_all = cfg.get('alert', {}).get('at_all_on_recovery', False)
            ok, body = send_im(im_type, cfg, title, content, at_all)
            log(f'  [RECOVERY IM] {im_type}: {"OK" if ok else "FAIL: " + body}')
            state['last_alert_ts'] = now

        state['failed_keys'] = []
        save_state(state, state_path)
        log('  [OK] 全部健康')
        return 0


def run_daemon(cfg: dict, state_path: str):
    """守护模式"""
    interval = cfg.get('alert', {}).get('interval_sec', 300)  # 默认 5 分钟
    log(f'[DAEMON] 启动, 间隔 {interval}s')
    while True:
        try:
            run_once(cfg, state_path)
        except KeyboardInterrupt:
            log('[DAEMON] 收到 Ctrl+C, 退出')
            break
        except Exception as e:
            log(f'[DAEMON ERROR] {e}')
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description='yonaa agent 端 IM 告警监控')
    parser.add_argument('--config', default=DEFAULT_CONFIG, help=f'配置文件 (默认 {DEFAULT_CONFIG})')
    parser.add_argument('--check-now', action='store_true', help='跑一次检查并退出')
    parser.add_argument('--daemon', action='store_true', help='守护模式, 每 5 分钟跑一次')
    parser.add_argument('--simulate-fail', action='store_true', help='模拟失败 (发测试告警)')
    parser.add_argument('--test-im', action='store_true', help='测试 IM 推送 (发 hello 消息)')
    parser.add_argument('--list-chats', action='store_true', help='列出飞书应用机器人加入的群 (用来找 chat_id)')
    parser.add_argument('--test-lark-app', action='store_true', help='测试飞书应用机器人 API 推送')
    parser.add_argument('--init-config', action='store_true', help='初始化配置文件')
    args = parser.parse_args()

    state_path = args.config.replace('.json', '_state.json')

    # 初始化配置
    if args.init_config:
        if os.path.exists(args.config):
            print(f'配置已存在: {args.config}')
            return 1
        example = {
            'im': {
                'default': 'lark_app',  # 默认推送的 IM 类型 (V007.59 推荐)
                # 飞书应用机器人 (V007.59 推荐, 不受管理员禁自定义机器人影响)
                'lark_app': {
                    'app_id': '<替换为你的飞书 app_id>',
                    'app_secret': '<替换为你的飞书 app_secret>',
                    'chat_id': '<替换为你的群 chat_id>',
                },
                # 飞书 webhook (V007.58, 旧方案, 可能被禁)
                'feishu': {
                    'webhook': 'https://open.feishu.cn/open-apis/bot/v2/hook/<替换为你的token>',
                    'secret': '',  # 可选, 飞书签名密钥
                },
                'dingtalk': {
                    'webhook': 'https://oapi.dingtalk.com/robot/send?access_token=<替换>',
                    'secret': '',  # 可选
                },
                'wecom': {
                    'webhook': 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<替换>',
                },
            },
            'alert': {
                'interval_sec': 300,           # 检查间隔 (秒)
                'cooldown_sec': 600,           # 告警冷却 (秒, 防止重复推送)
                'at_all_on_fail': True,         # 失败时 @所有人
                'at_all_on_recovery': False,    # 恢复时 @所有人
            },
        }
        save_config(example, args.config)
        print(f'\n请编辑 {args.config} 填入真实的凭证')
        print('V007.59 推荐用 lark_app (飞书应用机器人), 详见 docs/INCIDENT_ALERT_SETUP.md §1b')
        return 0

    cfg = load_config(args.config)

    # 测试 IM
    if args.test_im:
        title = '[TEST] yonaa IM 告警连通测试'
        content = f'''**测试推送**: agent → IM 链路验证

- agent 端: 公司电脑 (windows)
- IM 类型: {cfg.get("im", {}).get("default", "?")}
- 时间: {time.strftime("%Y-%m-%d %H:%M:%S")}

收到此消息表示告警链路就绪.'''
        im_type = cfg.get('im', {}).get('default', 'feishu')
        ok, body = send_im(im_type, cfg, title, content, False)
        print(f'[IM] {im_type}: {"OK" if ok else "FAIL"}')
        print(f'  body: {body[:200]}')
        return 0 if ok else 2

    # 列出飞书应用机器人群 (找 chat_id)
    if args.list_chats:
        lark_cfg = cfg.get('im', {}).get('lark_app', {})
        app_id = lark_cfg.get('app_id', '')
        app_secret = lark_cfg.get('app_secret', '')
        if not app_id or '<' in app_id:
            print('[FAIL] lark_app.app_id 未配置')
            return 2
        if not app_secret:
            print('[FAIL] lark_app.app_secret 未配置')
            return 2
        try:
            chats = _lark_list_chats(app_id, app_secret)
            print(f'[OK] 找到 {len(chats)} 个群:\n')
            for c in chats:
                chat_id = c.get('chat_id', '?')
                name = c.get('name', '?')
                desc = c.get('description', '')
                print(f'  chat_id: {chat_id}')
                print(f'  name    : {name}')
                print(f'  desc    : {desc[:50]}')
                print()
            print('复制上面的 chat_id 到 alert_monitor_config.json:')
            print('  "lark_app": {')
            print('    "app_id": "...",')
            print('    "app_secret": "...",')
            print(f'    "chat_id": "<粘上面 chat_id>"')
            print('  }')
            return 0
        except Exception as e:
            print(f'[FAIL] {e}')
            return 2

    # 测试飞书应用机器人 API
    if args.test_lark_app:
        title = '[TEST] yonaa 应用机器人连通测试'
        content = f'''**测试推送**: agent → 飞书应用机器人 (V007.59)

- agent 端: 公司电脑 (windows)
- IM 类型: lark_app (飞书应用机器人 API)
- 时间: {time.strftime("%Y-%m-%d %H:%M:%S")}

收到此消息表示告警链路就绪 (走 open-apis/im/v1/messages, 不用 webhook).'''
        ok, body = send_im('lark_app', cfg, title, content, False)
        print(f'[LARK_APP] {"OK" if ok else "FAIL"}')
        print(f'  body: {body[:300]}')
        return 0 if ok else 2

    # 模拟失败
    if args.simulate_fail:
        title = '[ALERT] yonaa 服务异常 (模拟)'
        content = '''这是 agent 端模拟的告警, 用于验证推送链路.

**场景**: 模拟 log_service 9101 端口死掉

- 服务: log_service_prod
- 端口: 9101
- 期望: 5 分钟内能 @all 推送告警
- 验证: 手机应收到红色卡片, 标题 [ALERT]'''

        im_type = cfg.get('im', {}).get('default', 'feishu')
        ok, body = send_im(im_type, cfg, title, content, True)
        print(f'[IM] {im_type}: {"OK" if ok else "FAIL"}')
        print(f'  body: {body[:300]}')
        return 0 if ok else 2

    # 一次性检查
    if args.check_now:
        return run_once(cfg, state_path)

    # 守护模式
    if args.daemon:
        run_daemon(cfg, state_path)
        return 0

    # 默认: 跑一次
    return run_once(cfg, state_path)


if __name__ == '__main__':
    sys.exit(main())