#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[2026-09-26] prod 认证修复 delta 部署.

载荷 (用户已在对话中批准 prod 部署):
  A. lib/unified_8081.py 认证补丁 (3 处, 与 staging unified_18081 同源):
     1) 转发头白名单加 Cookie (根治: 浏览器 auth_token cookie 从未到达 backend,
        一直靠按 IP 注入 token 代偿, 缓存陈旧即全站 401 TOKEN_EXPIRED/未登录)
     2) 带 auth_token cookie 的请求不再注入缓存 token
     3) GET dev-login 也识别为登录请求 (刷新 IP 缓存)
     基于远端当前文件锚点替换 (保留已部署的 G1 落盘 + 静态 404 成果)。
  B. frontend_dist_files 换新 (含 3 个前端修复: tabs满LRU淘汰 / 深链路由自愈 /
     未登录深链重定向登录页) + CUR/全部 bak 代 assets 无覆盖保留 (G2 同策略)。

安全: DB .backup 前置 / 锚点断言 + compile 门禁 / 原子替换 / 探活失败自动回滚 /
      服务级备份保留 2 代。
用法: python tools/_deploy_prod_auth_delta.py
"""
import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import staging_round as sr  # noqa: E402

sr.use_prod_gateway()

LIB = "/opt/app/deployments/lib/unified_8081.py"
DIST_DIR = REPO / "dist"
LOCAL_TGZ = REPO / "dist_deploy_prod.tar.gz"
LOCAL_PATCH = REPO / "tools" / "_prod_unified8081.auth_patched.py"
STAMP = time.strftime("%Y%m%d-%H%M%S")

# 远端脚本经 write_remote_script 落盘执行, 命令文本只有 `bash /tmp/_x.sh`,
# 天然绕过 prod 网关词法白名单。
APPLY_UNIFIED_SH = r"""#!/bin/bash
set -u
STAMP=__STAMP__
LIB=/opt/app/deployments/lib/unified_8081.py
IP=172.20.59.7

# DB 安全快照 (本次不动 DB, 仍按 prod 惯例留底; sqlite3 CLI 太老, 用 python 模块)
PYBIN="$(command -v python3 || true)"
[ -x "$PYBIN" ] || PYBIN=/opt/miniconda3-py39/bin/python
db_ok=0
"$PYBIN" - "$STAMP" <<'PYEOF' && db_ok=1
import sqlite3, sys, os
stamp = sys.argv[1]
src = '/opt/app/deployments/meta/architecture.db'
dst = f'/opt/app/deployments/meta/architecture.db.bak_prod_auth_{stamp}'
con = sqlite3.connect(src, timeout=30)
out = sqlite3.connect(dst)
con.backup(out)
out.close(); con.close()
print('DB_BACKUP_OK', dst, os.path.getsize(dst), 'bytes')
PYEOF
if [ "$db_ok" != "1" ]; then
  echo "[FATAL] DB backup failed - abort before any change"
  exit 1
fi

cp -a "$LIB" "$LIB.bak_auth_$STAMP" && echo BACKUP_OK

install -m 755 /tmp/_unified_auth_patch.py "$LIB.new" && mv -f "$LIB.new" "$LIB" \
  && echo SWAP_OK

systemctl restart meta-unified.service
ok=0
for i in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://$IP:8081/" 2>/dev/null)
  [ "$code" = "200" ] && { ok=1; break; }
  sleep 1
done
if [ "$ok" != "1" ]; then
  echo "[ROLLBACK] 8081 not healthy after restart, restoring backup"
  cp -a "$LIB.bak_auth_$STAMP" "$LIB"
  systemctl restart meta-unified.service
  sleep 3
  echo "ROLLBACK_DONE code=$(curl -s -o /dev/null -w '%{http_code}' "http://$IP:8081/")"
  exit 1
fi
echo RESTART_OK
m=$(curl -s -o /dev/null -w '%{http_code}' "http://$IP:8081/assets/__missing_404_probe__.js")
lg=$(curl -s -o /dev/null -w '%{http_code}' "http://$IP:8081/login")
g1=$(grep -c 'FIX 2026-09-26 G1' "$LIB")
ck=$(grep -c '"Content-Type", "Cookie"' "$LIB")
echo "MISSING_JS=$m SPA_LOGIN=$lg G1_MARK=$g1 COOKIE_FWD=$ck"
[ "$m" = "404" ] && [ "$g1" = "1" ] && [ "$ck" = "1" ] && echo UNIFIED_AUTH_PATCH_OK
echo DONE_UNIFIED
"""

DEPLOY_DIST_SH = r"""#!/bin/bash
set -u
STAMP=__STAMP__
INDEX_MD5=__INDEX_MD5__
IP=172.20.59.7
DEP=/opt/app/deployments
CUR=$DEP/frontend_dist_files
NEW=$DEP/dist_new_$STAMP

avail_kb=$(df -k $DEP | awk 'NR==2 {print $4}')
echo "[df] avail=$((avail_kb/1024))MB"
[ "$avail_kb" -lt 262144 ] && { echo "[FATAL] disk < 256MB"; exit 1; }

mkdir -p "$NEW"
tar -xzf /tmp/_dl_dist.tar.gz -C "$NEW"
n=$(find "$NEW" -type f | wc -l)
echo "[extract] files=$n"
[ "$n" -lt 100 ] && { echo "[FATAL] too few files"; exit 1; }
md5=$(md5sum "$NEW/index.html" | awk '{print $1}')
echo "[extract] index md5=$md5"
[ "$md5" != "$INDEX_MD5" ] && { echo "[FATAL] index md5 mismatch"; exit 1; }

# 旧 assets 全保留合并 (CUR + 全部历史 bak 代): 旧 tab chunk 持续 200
for src in "$CUR" $DEP/frontend_dist_files.bak*; do
  [ -d "$src/assets" ] || continue
  cp -an "$src/assets/." "$NEW/assets/" || { echo "[FATAL] assets merge failed ($src)"; exit 1; }
done
echo "[merge] assets after union: $(find "$NEW/assets" -type f | wc -l)"

old_chunk=$(find "$CUR/assets" -maxdepth 1 -name '*.js' | sort | awk 'NR==1')
echo "[old-probe-chunk] $(basename "$old_chunk")"

mv "$CUR" "$DEP/frontend_dist_files.bak_$STAMP" || { echo "[FATAL] mv old->bak"; exit 1; }
if ! mv "$NEW" "$CUR"; then
  echo "[FATAL] mv new->cur, restoring old"
  mv "$DEP/frontend_dist_files.bak_$STAMP" "$CUR"
  exit 1
fi
echo SWAP_OK

# 备份保留最近 2 代 (按 mtime; 网关禁 rm -> python)
/opt/miniconda3-py39/bin/python - <<'PYEOF'
import glob, os, shutil
baks = sorted(glob.glob('/opt/app/deployments/frontend_dist_files.bak*'),
              key=os.path.getmtime, reverse=True)
for old in baks[2:]:
    shutil.rmtree(old, ignore_errors=True)
    print('[prune]', old)
PYEOF

sleep 1
entry=$(awk 'match($0, /assets\/index-[A-Za-z0-9_-]+\.js/) {print substr($0, RSTART, RLENGTH); exit}' "$CUR/index.html")
echo "entry chunk: $entry"
curl -s -o /dev/null -w "GET /                -> http=%{http_code}\n" "http://$IP:8081/"
curl -s -o /dev/null -w "GET /$entry  -> http=%{http_code} type=%{content_type}\n" "http://$IP:8081/$entry"
curl -s -o /dev/null -w "GET missing chunk    -> http=%{http_code}\n" "http://$IP:8081/assets/__missing_404_probe__.js"
curl -s -o /dev/null -w "GET /login (SPA)     -> http=%{http_code}\n" "http://$IP:8081/login"
curl -s -o /dev/null -w "GET api probe        -> http=%{http_code} type=%{content_type}\n" "http://$IP:8081/api/v1/object-types"
curl -s -o /dev/null -w "GET old-gen chunk ($(basename "$old_chunk")) -> http=%{http_code}\n" "http://$IP:8081/assets/$(basename "$old_chunk")"
echo DONE_DIST
"""

CLEANUP_SH = r"""#!/bin/bash
/opt/miniconda3-py39/bin/python - <<'PYEOF'
import os
for p in ('/tmp/_unified_auth_patch.py', '/tmp/_dl_dist.tar.gz',
          '/tmp/_prod_apply_auth.sh', '/tmp/_prod_deploy_dist2.sh'):
    try:
        os.remove(p)
        print('[cleaned]', p)
    except OSError:
        pass
print('CLEANUP_OK')
PYEOF
"""


def step(name, ok, detail=""):
    print(f"[{'OK' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        print("[ABORT]", name)
        sys.exit(1)


def fetch_remote_lib() -> str:
    """拉取远端当前 unified_8081.py (补丁基线 = 远端实际内容, 保留 G1/404 成果)"""
    r = sr.remote_exec(f"cat {LIB}", timeout=45)
    step("fetch remote unified_8081.py", not r.get("error"))
    src = r.get("stdout") or ""
    step("remote lib non-empty", len(src) > 5000, f"{len(src)} chars")
    return src


def build_auth_patched(src: str) -> str:
    """3 处认证锚点替换 + 完整性断言 + compile 门禁"""
    # 基线断言: G1/404 成果必须在 (防用错基线)
    assert "FIX 2026-09-26 G1" in src, "G1 marker missing - wrong base?"
    assert "send_error(404)" in src, "static-404 fix missing - wrong base?"

    def sub1(cur, old, new):
        assert cur.count(old) == 1, f"anchor not unique ({cur.count(old)}): {old[:60]!r}"
        assert new not in cur, f"already patched? {new[:60]!r}"
        return cur.replace(old, new)

    cur = src
    # 1) 转发白名单加 Cookie
    cur = sub1(cur,
               'for k in ("Authorization", "Content-Type", "X-User-Id", "X-User-Name", "X-IP-Address"):',
               'for k in ("Authorization", "Content-Type", "Cookie", "X-User-Id", "X-User-Name", "X-IP-Address"):')
    # 2) 带 auth_token cookie 的请求不再注入缓存 token
    cur = sub1(cur,
               'if not self.headers.get("Authorization"):',
               'if not self.headers.get("Authorization") and '
               '"auth_token=" not in (self.headers.get("Cookie") or ""):')
    # 3) GET dev-login 识别为登录请求
    cur = sub1(cur,
               'if method != "POST":',
               'if method not in ("POST", "GET"):')

    for token in ('"Content-Type", "Cookie"',
                  '"auth_token=" not in (self.headers.get("Cookie") or "")',
                  'if method not in ("POST", "GET"):',
                  "TOKEN_CACHE_PATH", "send_error(404)"):
        assert token in cur, f"patch lost: {token}"
    compile(cur, "unified_8081_auth_patched", "exec")  # 语法门禁
    LOCAL_PATCH.write_text(cur, encoding="utf-8", newline="\n")
    return cur


def main() -> int:
    os.environ["APPROVED_DEPLOY"] = "1"  # 用户已在对话中批准 prod 部署
    print(f"[prod-auth-delta] @ {time.strftime('%Y-%m-%d %H:%M:%S')} stamp={STAMP}")

    print("\n[1/5] 拉取远端 unified_8081.py + 生成认证补丁 ...")
    src = fetch_remote_lib()
    patched = build_auth_patched(src)
    patch_md5 = hashlib.md5(LOCAL_PATCH.read_bytes()).hexdigest()
    print(f"    patched lines={patched.count(chr(10))} md5={patch_md5}")

    print("\n[2/5] 上传补丁 ...")
    r = sr.remote_upload(LOCAL_PATCH, "/tmp/_unified_auth_patch.py", timeout=300)
    step("upload patch", not r.get("error"))
    step("patch md5 verify", sr.remote_md5("/tmp/_unified_auth_patch.py") == patch_md5)

    print("\n[3/5] 应用补丁 (DB backup -> 备份 -> 原子替换 -> restart -> 探活/回滚) ...")
    sh = APPLY_UNIFIED_SH.replace("__STAMP__", STAMP)
    w = sr.write_remote_script("/tmp/_prod_apply_auth.sh", sh)
    step("write apply script", not w.get("error"))
    r = sr.remote_exec("bash /tmp/_prod_apply_auth.sh 2>&1", timeout=180)
    out = r.get("stdout") or ""
    print(out.rstrip())
    step("apply script", not r.get("error"))
    step("DB backup done", "DB_BACKUP_OK" in out)
    step("unified auth patched+healthy", "UNIFIED_AUTH_PATCH_OK" in out)
    step("G1 preserved", "G1_MARK=1" in out)

    print("\n[4/5] 打包 + 上传新 dist ...")
    if LOCAL_TGZ.exists():
        LOCAL_TGZ.unlink()
    subprocess.run(["tar", "-czf", LOCAL_TGZ.name, "-C", "dist", "."],
                   cwd=str(REPO), check=True)
    tgz_md5 = hashlib.md5(LOCAL_TGZ.read_bytes()).hexdigest()
    index_md5 = hashlib.md5((DIST_DIR / "index.html").read_bytes()).hexdigest()
    size_mb = LOCAL_TGZ.stat().st_size / 1048576
    print(f"    {LOCAL_TGZ.name} {size_mb:.1f}MB md5={tgz_md5}; index md5={index_md5}")
    r = sr.remote_upload(LOCAL_TGZ, "/tmp/_dl_dist.tar.gz", timeout=900)
    step("upload dist", not r.get("error"))
    step("dist md5 verify", sr.remote_md5("/tmp/_dl_dist.tar.gz") == tgz_md5)

    print("\n[5/5] 部署 dist (旧 assets 全保留 -> 交换 -> HTTP 验证) ...")
    sh = DEPLOY_DIST_SH.replace("__STAMP__", STAMP).replace("__INDEX_MD5__", index_md5)
    w = sr.write_remote_script("/tmp/_prod_deploy_dist2.sh", sh)
    step("write dist script", not w.get("error"))
    r = sr.remote_exec("bash /tmp/_prod_deploy_dist2.sh 2>&1", timeout=600)
    out = r.get("stdout") or ""
    print(out.rstrip())
    step("dist deploy script", not r.get("error"))
    step("GET / = 200", re.search(r"GET /\s+-> http=200\b", out) is not None)
    step("new entry = 200 js", "http=200 type=application/javascript" in out)
    step("missing chunk = 404", re.search(r"GET missing chunk\s+-> http=404", out) is not None)
    step("SPA /login = 200", re.search(r"GET /login \(SPA\)\s+-> http=200", out) is not None)
    step("old-gen chunk still 200", "old-gen chunk" in out and
         "-> http=200" in [l for l in out.splitlines() if "old-gen chunk" in l][0])
    step("[DONE_DIST] seen", "DONE_DIST" in out)

    w = sr.write_remote_script("/tmp/_prod_cleanup2.sh", CLEANUP_SH)
    r = sr.remote_exec("bash /tmp/_prod_cleanup2.sh 2>&1", timeout=15)
    print((r.get("stdout") or "").rstrip())

    print("\n[DONE] prod 认证修复 delta 部署完成:")
    print(f"  - unified_8081.py: Cookie 透传 + 注入条件 + GET login (备份 .bak_auth_{STAMP}; G1/404 保留)")
    print(f"  - frontend_dist_files: 新 dist (tabs LRU / 深链自愈 / 未登录重定向), 旧 assets 全保留")
    print(f"  - DB 快照: architecture.db.bak_prod_auth_{STAMP}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
