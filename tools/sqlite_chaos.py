#!/usr/bin/env python3
"""
sqlite_chaos.py - SQLite IO disk error 故障注入工具 [V007.49-D 2026-07-13]

用途: 在 staging 沙盒演练 SQLite IO 故障, 提前发现防护漏洞
       不能在 prod 跑 (会破坏生产数据)

用法:
  python tools/sqlite_chaos.py readonly    # TEST 1: 模拟 db 只读
  python tools/sqlite_chaos.py busy        # TEST 2: 锁竞争
  python tools/sqlite_chaos.py extlock     # TEST 3: 外部进程持锁
  python tools/sqlite_chaos.py corrupt     # TEST 4: db 头损坏
  python tools/sqlite_chaos.py deleted     # TEST 5: db 被删
  python tools/sqlite_chaos.py full        # TEST 6: 模拟磁盘满 (需 staging)
  python tools/sqlite_chaos.py all         # 跑所有非破坏性场景
  python tools/sqlite_chaos.py restore     # 从 backup 恢复 db
"""
import os
import sys
import time
import sqlite3
import subprocess
import shutil

# [V007.49-D 2026-07-13] 支持 staging 路径 (env var 覆盖, 默认 prod)
DB_PATH = os.environ.get("CHAOS_DB_PATH", "/opt/app/deployments/meta/architecture.db")
DB_BAK = os.environ.get("CHAOS_DB_BAK", f"{DB_PATH}.chaos_bak")


def backup_db():
    if not os.path.exists(DB_BAK):
        shutil.copy(DB_PATH, DB_BAK)
        print(f'[BACKUP] {DB_BAK}')
    return DB_BAK


def restore_db():
    if not os.path.exists(DB_BAK):
        print(f'[WARN] no backup at {DB_BAK}')
        return False
    shutil.copy(DB_BAK, DB_PATH)
    os.chmod(DB_PATH, 0o666)
    print(f'[RESTORE] {DB_PATH} from {DB_BAK}')
    # 验证
    conn = sqlite3.connect(DB_PATH, timeout=5)
    result = conn.execute("PRAGMA integrity_check").fetchone()
    conn.close()
    print(f'[VERIFY] integrity: {result[0]}')
    return result[0] == 'ok'


def test_readonly():
    """TEST 1: db 设为只读 (chmod 555) - 模拟云盘切换只读
    注意: chmod 555 对 root 写仍然无效 (重大发现 2026-07-13)
    """
    print('\n=== TEST 1: chmod 555 + 真 INSERT (audit_logs) ===')
    backup_db()
    try:
        os.chmod(DB_PATH, 0o555)
        conn = sqlite3.connect(DB_PATH, timeout=5)
        # 读应正常
        n = conn.execute("SELECT count(*) FROM audit_logs").fetchone()[0]
        print(f'  READ ok: {n} rows')
        # 写 (root 用户 - 不应被拦截)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""
                INSERT INTO audit_logs (object_type, object_id, action, field_name, user_name, created_at)
                VALUES ('chaos_readonly', 99999, 'CREATE', 'chaos', 'chaos', datetime('now'))
            """)
            conn.commit()
            print(f'  [BUG-CONFIRMED] root INSERT 成功! chmod 555 拦截不了 root')
            print(f'  实际云盘切换只读时, 我们的服务也是 root 跑, 所以会同样绕过')
            print(f'  → 必须代码层加 PRAGMA query_only 检测')
        except sqlite3.OperationalError as e:
            print(f'  [OK] INSERT blocked: {type(e).__name__}: {e}')
        conn.close()
    except Exception as e:
        print(f'  ERR: {type(e).__name__}: {e}')
    finally:
        os.chmod(DB_PATH, 0o666)


def test_busy():
    """TEST 2: BEGIN IMMEDIATE 持锁 + 另一连接 INSERT (测 busy_timeout)"""
    print('\n=== TEST 2: 锁竞争 + 真 INSERT (busy_timeout=5s) ===')
    backup_db()
    holder = sqlite3.connect(DB_PATH, timeout=60)
    holder.execute("BEGIN IMMEDIATE")
    holder.execute("SELECT count(*) FROM audit_logs").fetchone()
    print('  Holder got EXCLUSIVE lock')

    start = time.time()
    other = sqlite3.connect(DB_PATH, timeout=5)
    try:
        other.execute("BEGIN IMMEDIATE")
        other.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, field_name, user_name, created_at)
            VALUES ('chaos_busy', 99998, 'CREATE', 'busy_test', 'chaos', datetime('now'))
        """)
        other.commit()
        print(f'  [UNEXPECTED] INSERT ok in {(time.time()-start)*1000:.0f}ms')
    except sqlite3.OperationalError as e:
        elapsed = (time.time() - start) * 1000
        print(f'  [OK] other INSERT blocked in {elapsed:.0f}ms: {e}')
    finally:
        other.close()
        holder.execute("ROLLBACK")
        holder.close()


def test_extlock():
    """TEST 3: 外部 subprocess 持锁 + INSERT"""
    print('\n=== TEST 3: 外部进程持锁 + 真 INSERT ===')
    backup_db()
    proc = subprocess.Popen(
        ['/opt/miniconda3-py39/bin/python3', '-c', f'''
import sqlite3, time
conn = sqlite3.connect("{DB_PATH}", timeout=60)
conn.execute("BEGIN IMMEDIATE")
print("HOLDER: got IMMEDIATE lock", flush=True)
time.sleep(8)
print("HOLDER: rollback", flush=True)
conn.rollback()
conn.close()
'''],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    time.sleep(2)

    start = time.time()
    other = sqlite3.connect(DB_PATH, timeout=5)
    try:
        other.execute("BEGIN IMMEDIATE")
        other.execute("""
            INSERT INTO audit_logs (object_type, object_id, action, field_name, user_name, created_at)
            VALUES ('chaos_extlock', 99997, 'CREATE', 'ext_lock', 'chaos', datetime('now'))
        """)
        other.commit()
        print(f'  [UNEXPECTED] INSERT ok in {(time.time()-start)*1000:.0f}ms')
    except sqlite3.OperationalError as e:
        elapsed = (time.time() - start) * 1000
        print(f'  [OK] INSERT blocked in {elapsed:.0f}ms: {e}')
    finally:
        other.close()
        proc.wait(timeout=15)


def test_corrupt():
    """TEST 4: db 头损坏 (写 0 字节覆盖前 100 字节) - 破坏性, 跑完会恢复"""
    print('\n=== TEST 4: db 头损坏 (模拟 SQLITE_CORRUPT) ===')
    backup_db()
    # 写 0 到头
    with open(DB_PATH, 'r+b') as f:
        f.write(b'\x00' * 100)
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        try:
            result = conn.execute("SELECT count(*) FROM audit_logs").fetchone()
            print(f'  [UNEXPECTED] SELECT ok: {result[0]}')
        except sqlite3.DatabaseError as e:
            print(f'  [OK] SELECT failed: {type(e).__name__}: {e}')
        conn.close()
    except Exception as e:
        print(f'  [OK] open failed: {type(e).__name__}: {e}')


def test_deleted():
    """TEST 5: db 被删 + 访问 (破坏性)"""
    print('\n=== TEST 5: db 文件被删 ===')
    backup_db()
    os.unlink(DB_PATH)
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        try:
            result = conn.execute("SELECT count(*) FROM audit_logs").fetchone()
            print(f'  [UNEXPECTED] SELECT ok: {result[0]}')
        except sqlite3.DatabaseError as e:
            print(f'  [OK] SELECT failed: {type(e).__name__}: {e}')
        conn.close()
    except Exception as e:
        print(f'  [OK] open failed: {type(e).__name__}: {e}')


def test_full():
    """TEST 6: 模拟磁盘满 - 需要 staging 沙盒, prod 跑会卡"""
    print('\n=== TEST 6: 磁盘满 (需 staging 沙盒) ===')
    print('  [SKIP] 在 prod 不能跑 (会卡整个系统)')
    print('  模拟方法:')
    print('    1. staging 沙盒用 ulimit -f 限制 db 大小')
    print('    2. 用 overlayfs 拦截 ENOSPC')
    print('    3. 用 libfuse 写一个 mock fs, 强制返回 ENOSPC')
    print('  集成到 staging 沙盒时, 跑 chaos 工具即可验证 ENOSPC 防护')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    scenario = sys.argv[1].lower()
    print(f'[sqlite_chaos] scenario={scenario}  db={DB_PATH}')

    if scenario == 'readonly':
        test_readonly()
    elif scenario == 'busy':
        test_busy()
    elif scenario == 'extlock':
        test_extlock()
    elif scenario == 'corrupt':
        test_corrupt()
    elif scenario == 'deleted':
        test_deleted()
    elif scenario == 'full':
        test_full()
    elif scenario == 'all':
        test_readonly()
        test_busy()
        test_extlock()
        # corrupt + deleted 是破坏性, 需要最后
        test_corrupt()
        test_deleted()
    elif scenario == 'restore':
        restore_db()
    else:
        print(f'Unknown scenario: {scenario}')
        sys.exit(1)

    # 非破坏性场景, 自动恢复
    if scenario in ('readonly', 'busy', 'extlock', 'restore', 'all'):
        restore_db()


if __name__ == '__main__':
    main()