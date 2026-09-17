#!/usr/bin/env python3
"""一次性脚本: 把 v84 已部署 dist 回填为 round 1 (staging_round 工具测试用)

[v1.0 v84 fix verification backfill]
  - 真实场景: v83+v84 修复已于 16:55 由 mx80 v5 部署到 staging, 浏览器验证 PASS
  - 本脚本把这次成功部署补录进 .staging_rounds/round_001.json
  - 后续可用 `python tools/staging_round.py status` 一屏看到历史事实
  - 用 `python tools/staging_round.py verify --round 1` 重跑验证可重现 PASS
"""
import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

ROUNDS_DIR = Path(r'D:\filework\excel-to-diagram\tools\.staging_rounds')
HEAD = '9081acb62ac30d59d44c7ba25254bf1aa42af0c8'
HEAD_SHORT = HEAD[:6]
N = 1
STAMP = f'r{N:03d}_{HEAD_SHORT}'
BACKUP = f'/opt/app/staging/frontend_dist_files_bak_{STAMP}'

# 已知 v84 部署后的 chunk (从 status 远端探查可知)
key_chunks = [
    'PermissionConfigPanel-DS4-P1Pi.js',
    'vendor-mermaid-DqLdkIeh.js',
    'vendor-vue-ep-C0Ugr7nq.js',
    'vendor-echarts-B9F17iRh.js',
    'vendor-xlsx-BBWTpfDg.js',
]

rdata = {
    'started_at': '2026-09-03T16:55:00+08:00',
    'git': {'branch': 'release/integrated-main', 'head': HEAD,
            'head_short': HEAD_SHORT, 'uncommitted_changes': False},
    'build': {
        'dist_zip': f'tools/.staging_rounds/{STAMP}_dist.zip',
        'dist_size_mb': 17.5,
        'zip_md5': 'ec9a4c82 (mx80 v5 verified, dist zip not preserved)',
        'n_files': 129,
        'key_chunks': key_chunks,
        'build_command': 'npm run build (with chunk cycle gate) - backfilled from mx80 v5 history'
    },
    'deploy': {
        'status': 'OK',
        'at': '2026-09-03T16:55:00+08:00',
        'remote_backup': '/opt/app/staging/frontend_dist_files_bak_20260903_mx84 (legacy name, pre-rounds format)',
        'key_chunks_served': key_chunks,
        'probe_stdout': 'index=200\nchunk=200',
        'note': 'Backfilled from mx80 v5 manual deployment; remote name uses pre-rounds convention'
    },
    'verify': {
        'status': 'PASS',
        'at': '2026-09-03T16:58:00+08:00',
        'spec': 'tools/_scratch/mx78_permconfig_tab.py (predecessor)',
        'checks': [
            {
                'name': 'ps1228_sub_domain_contains',
                'permission_set_id': 1228,
                'tab_clicked': True,
                'expect_hits': {'目标绩效': True},
                'forbid_hits': {},
                'data_scope_context': 'data scope row "sub_domain" shows "view (1 item) | 目标绩效"',
                'screenshot': 'tools/_scratch/ps1228_permconfig.png',
                'ok': True
            },
            {
                'name': 'ps1232_sub_domain_contains',
                'permission_set_id': 1232,
                'tab_clicked': True,
                'expect_hits': {'时间管理': True},
                'forbid_hits': {},
                'data_scope_context': 'data scope row "sub_domain" shows "view (1 item) | 时间管理"',
                'screenshot': 'tools/_scratch/ps1232_permconfig.png',
                'ok': True
            }
        ]
    },
    'note': 'Backfilled: v84 row_scope fix + chunk cycle gate (deployed via mx80 v5, verified PASS)',
    'round': N
}

p = ROUNDS_DIR / f'round_{N:03d}.json'
p.write_text(json.dumps(rdata, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'[OK] round {N} backfilled to {p}')
print(f'     key chunks: {key_chunks[:2]} ...')
print(f'     verify: PASS (ps1228=目标绩效, ps1232=时间管理)')