#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
alert_im.py - yonaa 端 IM 告警推送 (V007.58 2026-07-15)

支持 3 种 IM:
- 飞书 (Lark / Feishu) webhook
- 钉钉 (Dingtalk) webhook
- 企业微信 (WeCom) webhook

用法:
    python tools/alert_im.py --type feishu --webhook <url> --title "..." --content "..."
    python tools/alert_im.py --type dingtalk --webhook <url> --title "..." --content "..." --at-all
    python tools/alert_im.py --type wecom --webhook <url> --title "..." --content "..."

配置文件:
    /opt/app/deployments/config/alert_im.json
    {
      "feishu": {"webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx", "secret": "..."},
      "dingtalk": {"webhook": "https://oapi.dingtalk.com/robot/send?access_token=xxx", "secret": "..."},
      "wecom": {"webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"}
    }

退出码:
    0 - 推送成功
    1 - 参数错误
    2 - 推送失败 (网络/认证)
    3 - 配置文件未找到
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

# 配置文件路径 (按 priority 查找)
CONFIG_PATHS = [
    os.path.expanduser('~/.alert_im.json'),
    '/opt/app/deployments/config/alert_im.json',
    '/opt/app/staging/deploy/config/alert_im.json',
]


def load_config() -> dict:
    """加载 IM 配置"""
    for p in CONFIG_PATHS:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f'[WARN] load config {p} failed: {e}', file=sys.stderr)
    return {}


# ====== 飞书 ======
def feishu_sign(secret: str, timestamp: str) -> str:
    """飞书签名 (HmacSHA256)"""
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
                'template': 'red' if '[ALERT]' in title or 'FAIL' in title else 'blue',
            },
            'elements': [
                {
                    'tag': 'markdown',
                    'content': content[:3000],
                },
                {
                    'tag': 'note',
                    'elements': [
                        {
                            'tag': 'plain_text',
                            'content': f'yonaa alert · {time.strftime("%Y-%m-%d %H:%M:%S")}',
                        }
                    ],
                },
            ],
        },
    }
    if at_all:
        data['card']['elements'].append({'tag': 'at', 'at_all': True})

    # 加签名
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
                # 飞书 StatusCode 0 = OK
                if j.get('StatusCode') == 0 or j.get('code') == 0:
                    return True, body
                return False, body
            except json.JSONDecodeError:
                return resp.status == 200, body
    except urllib.error.URLError as e:
        return False, str(e)


# ====== 钉钉 ======
def dingtalk_sign(secret: str) -> tuple:
    """钉钉签名 (返回 timestamp + sign)"""
    ts = str(round(time.time() * 1000))
    string_to_sign = f'{ts}\n{secret}'
    hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return ts, sign


def send_dingtalk(webhook: str, title: str, content: str, secret: str = '', at_all: bool = False) -> tuple:
    """发钉钉 webhook"""
    # 钉钉新版机器人用 markdown (不支持 at_all @所有人 — 必须手机确认)
    data = {
        'msgtype': 'markdown',
        'markdown': {
            'title': title[:50],
            'text': f'## {title}\n\n{content}\n\n---\n{yonaa_alert_footer()}',
        },
    }
    if at_all:
        data['at'] = {'isAtAll': True}

    # 加签名
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
                if j.get('errcode') == 0:
                    return True, body
                return False, body
            except json.JSONDecodeError:
                return resp.status == 200, body
    except urllib.error.URLError as e:
        return False, str(e)


# ====== 企业微信 ======
def send_wecom(webhook: str, title: str, content: str, secret: str = '', at_all: bool = False) -> tuple:
    """发企业微信 webhook (markdown)"""
    data = {
        'msgtype': 'markdown',
        'markdown': {
            'content': f'## {title}\n{content}\n\n{yonaa_alert_footer()}',
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
                if j.get('errcode') == 0:
                    return True, body
                return False, body
            except json.JSONDecodeError:
                return resp.status == 200, body
    except urllib.error.URLError as e:
        return False, str(e)


def yonaa_alert_footer() -> str:
    """统一告警 footer"""
    return f'<sub>yonaa alert · {time.strftime("%Y-%m-%d %H:%M:%S")} (UTC+8)</sub>'


def send(type_: str, webhook: str, title: str, content: str, secret: str = '', at_all: bool = False) -> tuple:
    """统一发送入口"""
    if type_ == 'feishu':
        return send_feishu(webhook, title, content, secret, at_all)
    elif type_ == 'dingtalk':
        return send_dingtalk(webhook, title, content, secret, at_all)
    elif type_ == 'wecom':
        return send_wecom(webhook, title, content, secret, at_all)
    else:
        return False, f'unsupported type: {type_}'


def main():
    parser = argparse.ArgumentParser(description='yonaa IM 告警推送 (飞书/钉钉/企业微信)')
    parser.add_argument('--type', choices=['feishu', 'dingtalk', 'wecom'], required=True, help='IM 类型')
    parser.add_argument('--webhook', help='webhook URL (优先级: 命令行 > 配置文件)')
    parser.add_argument('--secret', help='签名密钥 (可选, 用于加签)')
    parser.add_argument('--title', default='[ALERT] yonaa', help='告警标题')
    parser.add_argument('--content', default='', help='告警内容 (markdown)')
    parser.add_argument('--at-all', action='store_true', help='@所有人')
    parser.add_argument('--from-config', action='store_true', help='从配置文件读取 webhook/secret')
    parser.add_argument('--config', help='配置文件路径 (默认 ~/.alert_im.json / /opt/app/deployments/config/alert_im.json)')
    args = parser.parse_args()

    # 加载配置
    cfg = {}
    if args.config and os.path.exists(args.config):
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception as e:
            print(f'[WARN] load config {args.config} failed: {e}', file=sys.stderr)
    elif args.from_config:
        cfg = load_config()

    # 解析 webhook / secret
    webhook = args.webhook or cfg.get(args.type, {}).get('webhook')
    secret = args.secret or cfg.get(args.type, {}).get('secret', '')

    if not webhook:
        print(f'[ERROR] webhook missing. 提供 --webhook 或 --from-config', file=sys.stderr)
        return 1

    # 发送
    ok, body = send(args.type, webhook, args.title, args.content, secret, args.at_all)
    if ok:
        print(f'[OK] {args.type} 推送成功: {body[:200]}')
        return 0
    else:
        print(f'[FAIL] {args.type} 推送失败: {body[:500]}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())