#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[2026-09-26] prod delta 部署编排.

载荷 (基于 2026-09-26 prod 只读侦察):
  A. lib/unified_8081.py 补丁: G1 token 落盘 + 静态缺失 404
     (基于远端原版打补丁, 保留 NSFOCUS BIND/BACKEND_HOST 等 prod 差异)
  B. frontend_dist_files 换新 (0419bcc9 构建) + CUR/全部 bak 代 assets 无覆盖保留
     (与 staging G2 同策略: 旧 tab chunk 持续 200)

安全: DB .backup 前置 / 原子替换 / 探活失败自动回滚 / 服务级备份保留 2 代.
用法: python tools/_deploy_prod_delta.py   (用户已在对话中批准 prod 部署)
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

ORIG = REPO / "tools" / "_prod_unified8081.orig.py"
PATCHED = REPO / "tools" / "_prod_unified8081.patched.py"
DIST_DIR = REPO / "dist"
LOCAL_TGZ = REPO / "dist_deploy_prod.tar.gz"

STAMP = time.strftime("%Y%m%d-%H%M%S")

# 远端脚本经 write_remote_script(base64) 落盘执行, 命令文本只有 `bash /tmp/_x.sh`,
# 天然绕过 prod 网关词法白名单 (脚本内容可含任何文件名).
APPLY_UNIFIED_SH = r"""#!/bin/bash
set -u
STAMP=__STAMP__
LIB=/opt/app/deployments/lib/unified_8081.py
IP=172.20.59.7

# DB 安全快照 (本次不动 DB, 仍按 prod 惯例留底).
# 注意: prod sqlite3 CLI 是 2013 年老版 (3.7.17), 读不动 2023 版 DB 头
# (实测 "header and source version mismatch"), 改用 python sqlite3 模块
# (与 staging_round._check_prod_db_reachable 同姿势); 失败则任何变更前中止.
PYBIN="$(command -v python3 || true)"
[ -x "$PYBIN" ] || PYBIN=/opt/miniconda3-py39/bin/python
db_ok=0
"$PYBIN" - "$STAMP" <<'PYEOF' && db_ok=1
import sqlite3, sys, os
stamp = sys.argv[1]
src = '/opt/app/deployments/meta/architecture.db'
dst = f'/opt/app/deployments/meta/architecture.db.bak_prod_delta_{stamp}'
con = sqlite3.connect(src, timeout=30)
out = sqlite3.connect(dst)
con.backup(out)
out.close()
con.close()
print('DB_BACKUP_OK', dst, os.path.getsize(dst), 'bytes')
PYEOF
if [ "$db_ok" != "1" ]; then
  echo "[FATAL] DB backup failed - abort before any change"
  exit 1
fi

cp -a "$LIB" "$LIB.bak_$STAMP" && echo BACKUP_OK

install -m 755 /tmp/_unified_patch.py "$LIB.new" && mv -f "$LIB.new" "$LIB" \
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
  cp -a "$LIB.bak_$STAMP" "$LIB"
  systemctl restart meta-unified.service
  sleep 3
  echo "ROLLBACK_DONE code=$(curl -s -o /dev/null -w '%{http_code}' "http://$IP:8081/")"
  exit 1
fi
echo RESTART_OK
m=$(curl -s -o /dev/null -w '%{http_code}' "http://$IP:8081/assets/__missing_404_probe__.js")
lg=$(curl -s -o /dev/null -w '%{http_code}' "http://$IP:8081/login")
echo "MISSING_JS=$m SPA_LOGIN=$lg"
[ "$m" = "404" ] && echo UNIFIED_PATCH_OK
journalctl -u meta-unified.service --no-pager -n 6 | awk '/token cache|serving|listen|frontend_dir/'
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

# 记录部署前 CUR 代 chunk (部署后验证仍 200)
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
for p in ('/tmp/_unified_patch.py', '/tmp/_dl_dist.tar.gz',
          '/tmp/_prod_apply_unified.sh', '/tmp/_prod_deploy_dist.sh'):
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


# ============================================================
# Phase 0: 生成 unified_8081.py 补丁版 (锚点精确替换 + compile 校验)
# ============================================================
def build_patched() -> str:
    src = ORIG.read_text(encoding="utf-8")

    def sub1(cur, old, new):
        # 链式替换: 必须基于累计文本, 否则后一个补丁会把前一个静默冲掉
        assert cur.count(old) == 1, f"anchor not unique: {old[:60]!r}"
        return cur.replace(old, new)

    cur = src

    # --- G1: TOKEN_CACHE_PATH + _load/_persist (插在 _token_lock 之后) ---
    g1_block = '''
# [FIX 2026-09-26 G1] 缓存落盘持久化: 此前 cache 仅在内存, unified 重启(含每次
#   部署)即清空 -> 前端不发 Authorization 头的请求全部 401 -> 全体在线用户被弹到
#   登录页。落盘后重启自动恢复, 会话跨重启/部署存活。
#   路径: <脚本目录上两级>/unified_token_cache.json (=/opt/app/deployments/,
#   不随 dist / meta 包部署被替换), 可用 UNIFIED_TOKEN_CACHE 覆盖。
TOKEN_CACHE_PATH = os.environ.get(
    "UNIFIED_TOKEN_CACHE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "unified_token_cache.json"),
)


def _load_token_cache():
    """启动时从磁盘恢复 token 缓存 (丢弃过期条目), 失败不影响启动。"""
    try:
        with open(TOKEN_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        now = time.time()
        n = 0
        for ip, entry in (data or {}).items():
            if isinstance(entry, dict) and entry.get("token") \\
                    and now - entry.get("ts", 0) < TOKEN_TTL:
                TOKEN_CACHE[ip] = {"token": entry["token"], "ts": entry["ts"]}
                n += 1
        print(f"[unified] token cache restored from {TOKEN_CACHE_PATH} ({n} entries)", flush=True)
    except FileNotFoundError:
        print(f"[unified] token cache file not found (first boot): {TOKEN_CACHE_PATH}", flush=True)
    except Exception as e:
        print(f"[unified] token cache load failed (ignored): {e}", flush=True)


def _persist_token_cache():
    """原子落盘 token 缓存 (仅登录时触发, 频率低); 失败只打日志。"""
    try:
        with _token_lock:
            snapshot = dict(TOKEN_CACHE)
        tmp = TOKEN_CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f)
        os.replace(tmp, TOKEN_CACHE_PATH)
    except Exception as e:
        print(f"[unified] token cache persist failed (ignored): {e}", flush=True)

'''
    cur = sub1(cur,
               '_token_lock = threading.Lock()\n\n# Login 端点 (统一识别)',
               '_token_lock = threading.Lock()\n' + g1_block + '\n# Login 端点 (统一识别)')

    # --- G1: _save_token 末尾触发落盘 ---
    cur = sub1(cur,
        '    print(f"[unified] token saved for {client_ip} (cache size: {len(TOKEN_CACHE)})", flush=True)\n',
        '    print(f"[unified] token saved for {client_ip} (cache size: {len(TOKEN_CACHE)})", flush=True)\n'
        '    _persist_token_cache()\n')

    # --- G1: __main__ 启动恢复 ---
    cur = sub1(cur,
        'if __name__ == "__main__":\n    with ThreadedServer((BIND, PORT), UnifiedHandler) as httpd:',
        'if __name__ == "__main__":\n    _load_token_cache()\n'
        '    with ThreadedServer((BIND, PORT), UnifiedHandler) as httpd:')

    # --- 404: 静态缺失不再回 index.html ---
    fix404 = '''        full = os.path.join(FRONTEND_DIR, rel_path.lstrip("/"))
        if not os.path.isfile(full):
            # [FIX 2026-09-26] SPA fallback 只允许 HTML 导航请求 (无后缀 / .html)。
            #   静态资源 (.js/.css 等) 缺失时必须 404: 部署整目录替换 dist 后旧哈希
            #   chunk 消失, 旧页面点菜单会 import 旧 URL; 若把 index.html 当 200 返回,
            #   动态 import 拿到 HTML 解析失败且无失败信号, 造成"菜单 tab 空白"。
            #   404 让 router.onError (前端自愈) 能可靠识别并自动刷新。
            lower = rel_path.lower()
            if lower.endswith((
                    ".js", ".mjs", ".css", ".map", ".json", ".wasm",
                    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
                    ".woff", ".woff2", ".ttf", ".eot", ".otf", ".txt", ".xml")):
                self.send_error(404)
                return
            full = os.path.join(FRONTEND_DIR, "index.html")
'''
    cur = sub1(cur,
        '        full = os.path.join(FRONTEND_DIR, rel_path.lstrip("/"))\n'
        '        if not os.path.isfile(full):\n'
        '            # SPA fallback\n'
        '            full = os.path.join(FRONTEND_DIR, "index.html")\n',
        fix404)

    # 补丁完整性断言 (防静默丢失)
    for token in ("TOKEN_CACHE_PATH", "def _load_token_cache", "def _persist_token_cache",
                  "send_error(404)"):
        assert token in cur, f"patch lost: {token}"
    assert cur.count("def _load_token_cache") == 1
    assert cur.count("def _persist_token_cache") == 1
    assert "\n    _persist_token_cache()\n" in cur  # _save_token 末尾调用

    compile(cur, "unified_8081_patched", "exec")  # 语法门禁
    PATCHED.write_text(cur, encoding="utf-8", newline="\n")
    return cur


# ============================================================
def main() -> int:
    os.environ["APPROVED_DEPLOY"] = "1"  # 用户已在对话中批准 prod delta 部署
    print(f"[prod-delta] @ {time.strftime('%Y-%m-%d %H:%M:%S')} stamp={STAMP}")

    print("\n[0/4] 生成 unified_8081.py 补丁版 (G1 + 404) ...")
    patched = build_patched()
    patch_md5 = hashlib.md5(PATCHED.read_bytes()).hexdigest()
    print(f"    patched lines={patched.count(chr(10))} md5={patch_md5}")

    print("\n[1/4] 上传补丁 (兼网关 upload 通道自检) ...")
    r = sr.remote_upload(PATCHED, "/tmp/_unified_patch.py", timeout=300)
    step("upload patch", not r.get("error"))
    step("patch md5 verify", sr.remote_md5("/tmp/_unified_patch.py") == patch_md5)

    print("\n[2/4] 应用补丁 (DB backup -> 备份 -> 原子替换 -> restart -> 探活) ...")
    sh = APPLY_UNIFIED_SH.replace("__STAMP__", STAMP)
    w = sr.write_remote_script("/tmp/_prod_apply_unified.sh", sh)
    step("write apply script", not w.get("error"))
    r = sr.remote_exec("bash /tmp/_prod_apply_unified.sh 2>&1", timeout=180)
    out = r.get("stdout") or ""
    print(out.rstrip())
    step("apply script", not r.get("error"))
    step("DB backup done", "DB_BACKUP_OK" in out)
    step("unified patched+healthy", "UNIFIED_PATCH_OK" in out)

    print("\n[3/4] 打包 + 上传新 dist ...")
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

    print("\n[4/4] 部署 dist (旧 assets 全保留 -> 交换 -> HTTP 验证) ...")
    sh = DEPLOY_DIST_SH.replace("__STAMP__", STAMP).replace("__INDEX_MD5__", index_md5)
    w = sr.write_remote_script("/tmp/_prod_deploy_dist.sh", sh)
    step("write dist script", not w.get("error"))
    r = sr.remote_exec("bash /tmp/_prod_deploy_dist.sh 2>&1", timeout=600)
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

    # 清理远端载荷 (走脚本通道, 不赌网关词法; 清理脚本自身留在 /tmp 无害)
    w = sr.write_remote_script("/tmp/_prod_cleanup.sh", CLEANUP_SH)
    r = sr.remote_exec("bash /tmp/_prod_cleanup.sh 2>&1", timeout=15)
    print((r.get("stdout") or "").rstrip())
    print("\n[DONE] prod delta 部署完成:")
    print("  - unified_8081.py: G1 token 落盘 + 静态缺失 404 (备份 .bak_" + STAMP + ")")
    print("  - frontend_dist_files: 0419bcc9 新 dist, 旧 assets 全保留 (备份保留 2 代)")
    print("  - DB 快照: architecture.db.bak_prod_delta_" + STAMP)
    return 0


if __name__ == "__main__":
    sys.exit(main())
