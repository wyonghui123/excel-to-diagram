#!/usr/bin/env python3
"""查 audit log 的正确接口 + 查包含 TEST77777 的所有历史"""
import urllib.request, http.cookiejar, json

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# 1. audit log 接口
print('=== 尝试多种 audit log 接口 ===')
for path in [
    '/api/v1/audit/logs',
    '/api/v1/audit/logs?page=1&page_size=50',
    '/api/v2/audit/logs',
    '/api/v1/audit-logs',
]:
    try:
        r = op.open(f'http://localhost:3010{path}')
        d = json.loads(r.read().decode())
        items = d.get('data', d.get('items', []))
        if isinstance(items, list):
            print(f'  {path}: 返回 {len(items)} 条')
            # 查找 TEST 相关
            for log in items[:20]:
                log_str = json.dumps(log, ensure_ascii=False)
                if 'TEST77777' in log_str or 'TEST888' in log_str:
                    print(f'    *** FOUND: {log_str[:200]}')
        else:
            print(f'  {path}: 返回类型 {type(items).__name__}, keys: {list(d.keys())}')
    except Exception as e:
        print(f'  {path}: 失败 {e}')

# 2. 看 353 之前是否真的被创建过
print(f'\n=== 查找所有 id < 354 的 TEST7 产品 (含已删除) ===')
# 数据库视图可能不显示已删除的，尝试查 deleted 字段
for pid in [353, 352, 351, 350, 349, 348, 347, 346, 345, 340, 335, 330, 325, 320, 315, 310, 300, 250, 200, 100]:
    try:
        r = op.open(f'http://localhost:3010/api/v2/bo/product/{pid}?include_deleted=true')
        d = json.loads(r.read().decode())
        p = d.get('data', {})
        if p and (p.get('name', '').startswith('TEST7') or p.get('code', '').startswith('TEST7')):
            print(f'  id={pid}: name={p.get("name")} code={p.get("code")} deleted={p.get("is_deleted")}')
    except:
        pass

# 3. 直接查 DB 视图 - 看是否有 soft-delete 的产品
print(f'\n=== 直接查 DB: 所有 code=TEST77777 的产品 (含 deleted) ===')
import sqlite3
try:
    conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%product%'")
    tables = [t[0] for t in cur.fetchall()]
    print(f'  product 相关表: {tables}')

    for tbl in tables:
        if 'audit' in tbl.lower() or 'log' in tbl.lower() or 'history' in tbl.lower():
            continue
        try:
            cur.execute(f"SELECT id, name, code, is_deleted, created_at FROM {tbl} WHERE name LIKE '%TEST77777%' OR code LIKE '%TEST77777%' ORDER BY id")
            rows = cur.fetchall()
            if rows:
                print(f'  {tbl}:')
                for row in rows:
                    print(f'    {row}')
        except Exception as e:
            pass
    conn.close()
except Exception as e:
    print(f'  DB 查询失败: {e}')
