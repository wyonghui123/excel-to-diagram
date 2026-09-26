#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deploy_staging_dist.py - staging 前端 dist 部署 (标准入口)

[2026-09-26 G2] 旧 assets 向前保留: 部署换目录后, 已打开的旧页面(旧 bundle)
内存里仍持旧哈希 chunk 清单, 点菜单会 import 旧 URL。旧目录一换掉, 这些
URL 就 404 → 旧 bundle 无自愈能力 → 菜单 tab 静默空白(本项目长期痛点)。
内容哈希文件名保证同路径=同内容, 因此部署时把旧 assets 无覆盖合并进新目录
(cp -an), 旧 chunk 持续可用, 旧 tab 在下次硬刷新前一直正常工作。

用法:
  python tools/deploy_staging_dist.py            # 打包 repo dist/ 并部署
  python tools/deploy_staging_dist.py --skip-upload <remote 已有 tar.gz 不支持, 留待后续>

步骤: 打包 dist → 上传 → md5 校验 → 解压到新目录 → 完整性校验
      → 旧 assets 合并(不覆盖) → 近原子交换(旧目录留备份, 保留最近 2 代)
      → HTTP 验证(含: 部署前已存在的旧 chunk 仍 200) → 清理
"""
import hashlib
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import staging_round as sr  # noqa: E402

DIST_DIR = REPO / "dist"
LOCAL_TGZ = REPO / "dist_deploy_staging.tar.gz"
REMOTE_TGZ = "/tmp/dist_deploy_staging.tar.gz"
STAGING = "/opt/app/staging"
CUR = f"{STAGING}/frontend_dist_files"
BASE = "http://127.0.0.1:18081"
KEEP_BAKS = 2

DEPLOY_SH = r"""#!/bin/bash
set -u
STAGING=/opt/app/staging
STAMP=__STAMP__
CUR=$STAGING/frontend_dist_files
NEW=$STAGING/dist_new_$STAMP
BAK=$STAGING/frontend_dist_files.bak-$STAMP

avail_kb=$(df -k $STAGING | awk 'NR==2 {print $4}')
echo "[df] avail=$((avail_kb/1024))MB"
if [ "$avail_kb" -lt 262144 ]; then echo "[FATAL] disk < 256MB"; exit 1; fi

# 解压
mkdir -p "$NEW"
tar -xzf /tmp/dist_deploy_staging.tar.gz -C "$NEW"
n=$(find "$NEW" -type f | wc -l)
echo "[extract] files=$n"
if [ "$n" -lt 100 ]; then echo "[FATAL] too few files: $n"; exit 1; fi
md5=$(md5sum "$NEW/index.html" | awk '{print $1}')
echo "[extract] index.html md5=$md5"
if [ "$md5" != "__INDEX_MD5__" ]; then echo "[FATAL] index.html md5 mismatch"; exit 1; fi

# G2: 旧 assets 无覆盖合并进新目录 (同路径=同内容, 哈希名不冲突)
if [ -d "$CUR/assets" ]; then
  old_chunk=$(find "$CUR/assets" -maxdepth 1 -name '*.js' | sort | awk 'NR==1')
  if [ -n "$old_chunk" ]; then
    echo "[old-probe-chunk] $old_chunk"
    echo "$old_chunk" > /tmp/_old_probe_chunk.txt
  fi
  cp -an "$CUR/assets/." "$NEW/assets/" || { echo "[FATAL] assets merge failed"; exit 1; }
  merged=$(find "$NEW/assets" -type f | wc -l)
  echo "[merge] assets after union: $merged"
fi

# 近原子交换
if [ -d "$CUR" ]; then
  mv "$CUR" "$BAK" || { echo "[FATAL] mv old -> bak failed"; exit 1; }
fi
mv "$NEW" "$CUR" || { echo "[FATAL] mv new -> current failed"; [ -d "$BAK" ] && mv "$BAK" "$CUR"; exit 1; }
echo "[swap] done; backup: $BAK"

# 备份只留最近 KEEP_BAKS 代 (gateway 禁 rm, 用 python)
/opt/miniconda3-py39/bin/python - "$STAGING" <<'PYEOF'
import glob, os, shutil, sys
baks = sorted(glob.glob(sys.argv[1] + "/frontend_dist_files.bak-*"), reverse=True)
for old in baks[2:]:
    shutil.rmtree(old, ignore_errors=True)
    print("[prune] removed old backup:", old)
PYEOF

# HTTP 验证
sleep 1
entry=$(awk 'match($0, /assets\/index-[A-Za-z0-9_-]+\.js/) {print substr($0, RSTART, RLENGTH); exit}' "$CUR/index.html")
echo "entry chunk: $entry"
curl -s -o /dev/null -w "GET /                -> http=%{http_code} type=%{content_type}\n" http://127.0.0.1:18081/
curl -s -o /dev/null -w "GET /$entry  -> http=%{http_code} type=%{content_type}\n" "http://127.0.0.1:18081/$entry"
curl -s -o /dev/null -w "GET missing chunk    -> http=%{http_code}\n" "http://127.0.0.1:18081/assets/__missing_404_probe__.js"
curl -s -o /dev/null -w "GET /login (SPA)     -> http=%{http_code}\n" "http://127.0.0.1:18081/login"
curl -s -o /dev/null -w "GET /api proxy probe -> http=%{http_code} type=%{content_type}\n" "http://127.0.0.1:18081/api/v1/object-types"
if [ -f /tmp/_old_probe_chunk.txt ]; then
  oc=$(awk '{print $1}' /tmp/_old_probe_chunk.txt)
  ob=$(basename "$oc")
  curl -s -o /dev/null -w "GET old-gen chunk ($ob) -> http=%{http_code}\n" "http://127.0.0.1:18081/assets/$ob"
fi
echo "[DONE-remote]"
"""


def step(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'OK' if ok else 'FAIL'}] {name}" + (f" {detail}" if detail else ""))
    if not ok:
        print("[ABORT]", name)
        sys.exit(1)


def package() -> tuple:
    print("[1] packaging dist/ ...")
    if LOCAL_TGZ.exists():
        LOCAL_TGZ.unlink()
    subprocess.run(["tar", "-czf", LOCAL_TGZ.name, "-C", "dist", "."],
                   cwd=str(REPO), check=True)
    md5 = hashlib.md5(LOCAL_TGZ.read_bytes()).hexdigest()
    size = LOCAL_TGZ.stat().st_size / 1048576
    print(f"    {LOCAL_TGZ.name} {size:.1f}MB md5={md5}")
    index_md5 = hashlib.md5((DIST_DIR / "index.html").read_bytes()).hexdigest()
    print(f"    dist/index.html md5={index_md5}")
    return md5, index_md5


def main() -> int:
    if not (DIST_DIR / "index.html").exists():
        print("[FATAL] dist/index.html not found; run npm run build first")
        return 2

    local_md5, index_md5 = package()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    script = DEPLOY_SH.replace("__STAMP__", stamp).replace("__INDEX_MD5__", index_md5)

    print("[2] uploading tarball ...")
    r = sr.remote_upload(LOCAL_TGZ, REMOTE_TGZ, timeout=900)
    step("upload", not r.get("error"))
    step("tarball md5 verify", sr.remote_md5(REMOTE_TGZ) == local_md5)

    r = sr.write_remote_script("/tmp/_step_dist_deploy.sh", script)
    step("upload deploy script", not r.get("error"))
    r = sr.remote_exec("bash /tmp/_step_dist_deploy.sh 2>&1", timeout=600)
    print((r.get("stdout") or "").rstrip())
    step("deploy script", not r.get("error"))
    out = r.get("stdout") or ""

    body = out.split("entry chunk:")[1] if "entry chunk:" in out else ""
    step("GET / = 200", "\nGET /                -> http=200" in out)
    step("entry chunk = 200", "http=200 type=application/javascript" in body.split("GET missing")[0] if body else False)
    step("missing chunk = 404", "GET missing chunk    -> http=404" in out)
    step("SPA /login = 200", "GET /login (SPA)     -> http=200" in out)
    step("api proxy alive", "GET /api proxy probe -> http=502" not in out)
    if "[old-probe-chunk]" in out:
        old_lines = [l for l in out.splitlines() if "old-gen chunk" in l and "http=" in l]
        step("old-gen chunk still 200 (G2)", bool(old_lines) and "http=200" in old_lines[0],
             old_lines[0].strip() if old_lines else "(no probe line)")
    step("[DONE-remote] seen", "[DONE-remote]" in out)

    sr.remote_exec(
        "/opt/miniconda3-py39/bin/python -c \"import os; os.remove('/tmp/dist_deploy_staging.tar.gz')\"",
        timeout=15)
    print("[cleanup] remote tarball removed")
    print(f"\n[DONE] staging dist 部署完成 (stamp={stamp}); 旧目录备份保留最近 {KEEP_BAKS} 代")
    return 0


if __name__ == "__main__":
    sys.exit(main())
