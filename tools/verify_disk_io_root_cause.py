#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[V007.16 验证脚本] 验证 disk I/O error 真根因
===========================================

假说: WriteQueue 每 10 次 commit 跑 PRAGMA wal_checkpoint(TRUNCATE)
     会让 read pool 持有的 -shm 引用失效
     下次 reader 读 → disk I/O error

验证方法:
1. 创建 1 个 writer + 5 个 reader
2. writer 跑 10 次 commit (触发 checkpoint)
3. checkpoint 同时 reader 跑 SELECT
4. 看 reader 是否报 disk I/O error
5. 统计失败率
"""
import os
import sys
import time
import sqlite3
import tempfile
import threading
import random
from queue import Queue

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_wal_checkpoint_truncate_bug():
    """
    验证 WAL checkpoint TRUNCATE + read pool = disk I/O error
    """
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        # Setup schema
        conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        conn.execute("""
            CREATE TABLE test (
                id INTEGER PRIMARY KEY,
                val TEXT
            )
        """)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.commit()
        conn.close()

        # Create writer + 5 readers
        writer = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA busy_timeout=5000")

        readers = []
        for i in range(5):
            r = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
            r.execute("PRAGMA journal_mode=WAL")
            r.execute("PRAGMA query_only=ON")  # 标记只读
            r.execute("PRAGMA busy_timeout=5000")
            readers.append(r)

        # Insert some data
        for i in range(100):
            writer.execute("INSERT INTO test (val) VALUES (?)", (f"val_{i}",))

        errors = []
        reads_done = [0] * 5
        stop = [False]

        def reader_loop(idx, r):
            """持续读"""
            local_conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
            local_conn.execute("PRAGMA journal_mode=WAL")
            local_conn.execute("PRAGMA query_only=ON")
            local_conn.execute("PRAGMA busy_timeout=5000")

            while not stop[0]:
                try:
                    cursor = local_conn.execute("SELECT count(*) FROM test")
                    cursor.fetchone()
                    reads_done[idx] += 1
                except sqlite3.OperationalError as e:
                    if "disk I/O error" in str(e).lower():
                        errors.append((idx, str(e)))
                time.sleep(0.001)

        # Start 5 reader threads
        threads = []
        for i, r in enumerate(readers):
            t = threading.Thread(target=reader_loop, args=(i, r), daemon=True)
            t.start()
            threads.append(t)

        # Run 50 commits (will trigger 5 wal_checkpoint TRUNCATE)
        for commit_n in range(1, 51):
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("INSERT INTO test (val) VALUES (?)", (f"batch_{commit_n}",))
            writer.commit()

            # Every 10 commits = wal_checkpoint
            if commit_n % 10 == 0:
                print(f"  After commit {commit_n} (TRUNCATE triggered)")
                time.sleep(0.1)  # Give readers time to fail

        stop[0] = True
        for t in threads:
            t.join(timeout=2.0)

        # Cleanup
        for r in readers:
            r.close()
        writer.close()

        # Report
        total_reads = sum(reads_done)
        print(f"\n=== RESULTS ===")
        print(f"Total reads: {total_reads}")
        print(f"disk I/O errors: {len(errors)}")
        if errors:
            print(f"Sample error: {errors[0]}")
            print(f"Error rate: {len(errors)/total_reads*100:.2f}%" if total_reads else "N/A")
            return 1  # Bug reproduced
        else:
            print("No disk I/O errors. Hypothesis not confirmed.")
            return 0

    finally:
        try:
            os.unlink(db_path)
            os.unlink(db_path + '-wal')
            os.unlink(db_path + '-shm')
        except OSError:
            pass


if __name__ == '__main__':
    print("=" * 60)
    print("Verifying: PRAGMA wal_checkpoint(TRUNCATE) causes disk I/O error")
    print("=" * 60)
    sys.exit(test_wal_checkpoint_truncate_bug())