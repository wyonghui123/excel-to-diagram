import os
from pathlib import Path

ROOT = Path(r'd:\filework\release-prep-worktree\deploy_bundle')
sh_files = list(ROOT.rglob('*.sh'))
print(f'.sh files: {len(sh_files)}')
crlf_count = 0
for f in sh_files:
    data = f.read_bytes()
    has_crlf = b'\r\n' in data
    rel = f.relative_to(ROOT)
    if has_crlf:
        crlf_count += 1
        print(f'  CRLF: {rel} ({f.stat().st_size} bytes)')
    else:
        print(f'  LF:   {rel}')
print(f'\nTotal CRLF: {crlf_count}/{len(sh_files)}')
