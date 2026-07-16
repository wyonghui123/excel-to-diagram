#!/usr/bin/env python3
"""
merge_telemetry_mcp.py - 从 V046 007.zip 抽 telemetry/ mcp/, 注入到 V007.21 zip

[CHG 2026-07-06] V007.21 zip 缺 telemetry/ mcp/, 通用 rebuild_zip.py 不打
"""
import zipfile, shutil
from pathlib import Path

ROOT = Path('d:/filework/release-prep-worktree')
V46 = ROOT / 'deploy_bundle' / 'deploy-v20260704_007.zip'
V21 = ROOT / 'deploy_bundle' / 'deploy-v20260706_021.zip'
TMP = ROOT / 'deploy_bundle' / 'deploy-v20260706_021.merged.zip'

with zipfile.ZipFile(V46) as v46, zipfile.ZipFile(V21) as v21:
    v46_names = set(v46.namelist())
    v21_names = set(v21.namelist())
    v46_tel = [n for n in v46_names if n.startswith('telemetry/')]
    v46_mcp = [n for n in v46_names if n.startswith('mcp/')]
    print(f'V046 007: {len(v46_names)} files, telemetry={len(v46_tel)}, mcp={len(v46_mcp)}')
    print(f'V21:      {len(v21_names)} files, telemetry={len([n for n in v21_names if n.startswith("telemetry/")])}, mcp={len([n for n in v21_names if n.startswith("mcp/")])}')

    # 合并: V21 全部 + V46 telemetry + V46 mcp
    with zipfile.ZipFile(TMP, 'w', zipfile.ZIP_DEFLATED) as out:
        written = set()
        # V21 优先
        for info in v21.infolist():
            out.writestr(info, v21.read(info.filename))
            written.add(info.filename)
        # V46 telemetry
        for name in v46_tel:
            if name not in written:
                out.writestr(name, v46.read(name))
                written.add(name)
                print(f'  + {name}')
        # V46 mcp
        for name in v46_mcp:
            if name not in written:
                out.writestr(name, v46.read(name))
                written.add(name)
                print(f'  + {name}')

    # 替换 V21
    shutil.move(str(TMP), str(V21))
    print(f'\n[OK] merged: {len(written)} files')

# 验证
with zipfile.ZipFile(V21) as v:
    names = v.namelist()
    tel = [n for n in names if n.startswith('telemetry/')]
    mcp = [n for n in names if n.startswith('mcp/')]
    print(f'V21 验证: total={len(names)}, telemetry={len(tel)}, mcp={len(mcp)}')
