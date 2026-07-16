#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
alert_im_setup.py - 一键配置 IM webhook (V007.58 2026-07-15)

用法:
    # 交互式配置 (推荐, 会问你 webhook)
    python tools/alert_im_setup.py

    # 命令行直接配置
    python tools/alert_im_setup.py --type feishu --webhook https://open.feishu.cn/... --secret xxx
    python tools/alert_im_setup.py --type dingtalk --webhook https://oapi.dingtalk.com/... --secret xxx
    python tools/alert_im_setup.py --type wecom --webhook https://qyapi.weixin.qq.com/...

    # 测试推送 (发送一条 hello 消息验证 webhook 通了)
    python tools/alert_im_setup.py --test --type feishu

    # 上传到 yonaa 端
    python tools/alert_im_setup.py --upload

    # 安装 cron (V007.58)
    python tools/alert_im_setup.py --install-cron
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from yonaa_exec import yexec, yupload

LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_CRON = os.path.join(LOCAL_DIR, 'log_service_monitor.cron')
LOCAL_ALERT = os.path.join(LOCAL_DIR, 'alert_im.py')

# yonaa 端路径
PROD_CONFIG_DIR = '/opt/app/deployments/config'
PROD_CRON_DIR = '/etc/cron.d'
PROD_CRON_FILE = '/etc/cron.d/log_service_monitor'

REMOTE_CONFIG_DIRS = [PROD_CONFIG_DIR]


def gen_config(im_type: str, webhook: str, secret: str = '') -> dict:
    """生成单 IM 配置"""
    return {im_type: {'webhook': webhook, 'secret': secret}}


def merge_config(existing: dict, new: dict) -> dict:
    """合并配置 (新覆盖旧)"""
    out = dict(existing)
    for k, v in new.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def save_local_config(cfg: dict, path: str = None):
    """保存配置到本地"""
    if path is None:
        path = os.path.join(LOCAL_DIR, 'alert_im.local.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f'[OK] 配置保存到 {path}')
    return path


def upload_to_yonaa(cfg: dict, port: int = 9200):
    """上传配置到 yonaa 端"""
    cfg_content = json.dumps(cfg, indent=2, ensure_ascii=False)
    cfg_local = os.path.join(LOCAL_DIR, '_alert_im_config.json')
    with open(cfg_local, 'w', encoding='utf-8') as f:
        f.write(cfg_content)

    # 上传到白名单路径
    tmp_remote = '/opt/app/deployments/_alert_im_config.json'
    print(f'[1] upload config {cfg_local} -> {tmp_remote}')
    r = yupload(cfg_local, tmp_remote, port=port, secret='prod_write', timeout=20)
    print(f'    {r.get("action", r)}')

    # mkdir + cp 到 config 目录
    print(f'[2] mkdir -p {PROD_CONFIG_DIR} && cp')
    r = yexec(f'mkdir -p {PROD_CONFIG_DIR} && cp {tmp_remote} {PROD_CONFIG_DIR}/alert_im.json && chmod 600 {PROD_CONFIG_DIR}/alert_im.json && ls -la {PROD_CONFIG_DIR}/',
              port=port, secret='prod_write', timeout=10)
    print(f'    {(r.get("stdout") or "").strip()[:500]}')

    os.remove(cfg_local)
    return True


def install_cron(port: int = 9200):
    """装 cron 文件"""
    # 上传 cron
    tmp_remote = '/opt/app/deployments/log_service_monitor.cron'
    print(f'[1] upload cron {LOCAL_CRON} -> {tmp_remote}')
    r = yupload(LOCAL_CRON, tmp_remote, port=port, secret='prod_write', timeout=20)
    print(f'    {r.get("action", r)}')

    # cp 到 /etc/cron.d/
    print(f'[2] cp {tmp_remote} -> {PROD_CRON_FILE}')
    r = yexec(f'cp {tmp_remote} {PROD_CRON_FILE} && chmod 644 {PROD_CRON_FILE} && cat {PROD_CRON_FILE}',
              port=port, secret='prod_write', timeout=10)
    print(f'    {(r.get("stdout") or "").strip()[:1000]}')


def test_push(im_type: str, webhook: str, secret: str = '', port: int = 9200):
    """远程测试推送"""
    print(f'\n[TEST] {im_type} 推送到 yonaa 端验证')

    # 把 alert_im.py 上传
    tmp_alert = '/opt/app/deployments/_alert_im_test.py'
    print(f'[1] upload alert_im.py -> {tmp_alert}')
    r = yupload(LOCAL_ALERT, tmp_alert, port=port, secret='prod_write', timeout=20)
    print(f'    {r.get("action", r)}')

    # 远端跑 alert_im.py
    title = '[TEST] yonaa IM 告警连通测试'
    content = f'''**测试推送**: yonaa 端 → {im_type} 链路验证
- 服务器: yonaa (172.20.59.7)
- 时间: {time.strftime("%Y-%m-%d %H:%M:%S")}
- V007.58

收到此消息表示 IM 告警已就绪.'''

    cmd = f'/opt/miniconda3-py39/bin/python {tmp_alert} --type {im_type} --webhook "{webhook}" --secret "{secret}" --title "{title}" --content "{content}"'
    print(f'[2] 远端执行: {cmd[:100]}...')
    r = yexec(cmd, port=port, secret='prod_write', timeout=20)
    print(f'    stdout: {(r.get("stdout") or "").strip()[:500]}')
    print(f'    stderr: {(r.get("stderr") or "").strip()[:500]}')

    # 清理
    r = yexec(f'rm -f {tmp_alert}', port=port, secret='prod_write', timeout=5)
    return r


def interactive_setup():
    """交互式配置"""
    print('=== IM 告警配置向导 ===\n')
    print('支持的 IM: 飞书 (feishu) / 钉钉 (dingtalk) / 企业微信 (wecom)')
    print()

    cfg = {}
    for im_type in ['feishu', 'dingtalk', 'wecom']:
        add = input(f'配置 {im_type}? (y/N): ').strip().lower()
        if add != 'y':
            continue
        webhook = input(f'  {im_type} webhook URL: ').strip()
        if not webhook:
            continue
        secret = input(f'  {im_type} 签名密钥 (可选, 直接回车跳过): ').strip()
        cfg = merge_config(cfg, gen_config(im_type, webhook, secret))
        print(f'  [OK] {im_type} 配置完成')

    if not cfg:
        print('\n[FAIL] 没配置任何 IM')
        return False

    save_local_config(cfg)
    return cfg


def main():
    parser = argparse.ArgumentParser(description='一键配置 IM 告警')
    parser.add_argument('--type', choices=['feishu', 'dingtalk', 'wecom'], help='IM 类型')
    parser.add_argument('--webhook', help='webhook URL')
    parser.add_argument('--secret', default='', help='签名密钥 (可选)')
    parser.add_argument('--upload', action='store_true', help='上传配置到 yonaa')
    parser.add_argument('--install-cron', action='store_true', help='装 cron 到 /etc/cron.d/')
    parser.add_argument('--test', action='store_true', help='测试推送')
    parser.add_argument('--port', type=int, default=9200, help='yonaa 端口 (默认 9200 prod)')
    parser.add_argument('--interactive', action='store_true', help='交互式配置')
    args = parser.parse_args()

    cfg = {}

    # 命令行参数
    if args.type and args.webhook:
        cfg = gen_config(args.type, args.webhook, args.secret)
        save_local_config(cfg)

    # 交互式
    if args.interactive:
        cfg = interactive_setup()
        if not cfg:
            return 1

    if not cfg:
        print('请指定 --type + --webhook 或 --interactive', file=sys.stderr)
        return 1

    print(f'\n当前配置:')
    print(json.dumps(cfg, indent=2, ensure_ascii=False))

    if args.test:
        # 测试 (必须指定 webhook)
        for im_type, v in cfg.items():
            test_push(im_type, v['webhook'], v.get('secret', ''), port=args.port)

    if args.upload:
        upload_to_yonaa(cfg, port=args.port)

    if args.install_cron:
        install_cron(port=args.port)

    print('\n[DONE]')
    return 0


if __name__ == '__main__':
    sys.exit(main())