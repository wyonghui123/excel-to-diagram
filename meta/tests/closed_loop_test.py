"""
[Closed-Loop Test] 验证 batch_save 修复
[目的] 端到端验证: 产品 + 2 个重名 version 失败时, 必须整批回滚
[场景] 复现用户报告: TEST111 + V11/V11_重复 → 整批回滚
[执行] 必须在 worktree 中执行: cd d:/filework/agent-batch-tx-worktree && python meta/tests/closed_loop_test.py
"""
import os
os.environ.setdefault('FLASK_DEBUG', 'true')
os.environ.setdefault('TESTING', 'true')

import sys
import time
from pathlib import Path

# 加入 worktree 根目录到 path, 使 meta.* 可导入 (不是主工作树!)
WORKTREE_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKTREE_ROOT))

from meta.core.datasource import get_data_source
from meta.core.bo_framework import BOFramework
from meta.services.draft_batch_save import batch_save_handler
from meta.server import create_app
from flask import g


# [FIX 2026-06-18] 模块级 app 单例, 避免重复 create_app
_app = None
_ctx = None
_app_started = False


def _start_app_once():
    """初始化 app + ctx + 当前用户 (只调用一次)"""
    global _app, _ctx, _app_started
    if _app_started:
        return
    _app = create_app(db_path='d:/filework/excel-to-diagram/meta/architecture.db')
    _ctx = _app.app_context()
    _ctx.push()
    # mock 当前用户 (batch_save_handler 第一行会鉴权, 需 admin 权限才能创建)
    g.current_user = {
        'id': 1,
        'username': 'admin',
        'user_id': 1,
        'display_name': 'admin',
        'permissions': ['*'],
        'roles': [{'id': 1, 'name': 'admin'}],
    }
    _app_started = True


def closed_loop_test():
    """端到端: 直接调 batch_save_handler, 验证事务回滚"""
    print("=" * 60)
    print("[Closed-Loop] 验证 batch_save 整批回滚")
    print("=" * 60)

    # 1. 准备工作环境 - 启动 Flask app context 供 batch_save_handler 使用
    # [FIX 2026-06-18] 不能重复 create_app! 第二次会重新注册所有拦截器 + 重新包装 telemetry,
    #                  导致 persistence_interceptor 被调用 2 次, 第二次看到刚插入的记录,
    #                  validator 误判"重复"并失败. 复用模块级 app.
    if not _app_started:
        _start_app_once()
    return _run_test()


def _run_test_scenario(product_name: str, version_name: str, scenario_name: str = "默认") -> bool:
    """通用闭环测试: 创建 product + 同名 version, 验证整批回滚"""
    print(f"\n[{scenario_name}] 产品={product_name}, version={version_name}")

    # 2. 先建一个 product
    suffix = int(time.time() * 1000)
    unique_product_name = f'{product_name}_{suffix}'
    unique_product_code = f'PCODE_{suffix}'

    print(f"\n[1/4] 单独创建产品 {unique_product_name} (用 batch_save)...")
    product_result = batch_save_handler(
        params={
            'object_type': 'product',
            'drafts': [{
                'row_id': f'__new_p_{suffix}',
                'is_new': True,
                'fields': {
                    'name': unique_product_name,
                    'code': unique_product_code,
                }
            }]
        },
        context={}
    )
    print(f"      result: success={product_result.get('success')}, "
          f"created={product_result.get('data', {}).get('created')}")
    assert product_result.get('success'), f"产品创建失败: {product_result}"
    product_id = product_result.get('data', {}).get('created', [None])[0]
    print(f"      product_id = {product_id}")

    # 3. 关键测试: 用 batch_save 创建 2 个同名 version
    unique_version_name = f'{version_name}_{suffix}'
    print(f"\n[2/4] batch_save 2 个同名 version ({unique_version_name})...")
    version_result = batch_save_handler(
        params={
            'object_type': 'version',
            'drafts': [
                {
                    'row_id': f'__new_v1_{suffix}',
                    'is_new': True,
                    'fields': {
                        'name': unique_version_name,
                        'code': f'V1_{suffix}',
                        'product_id': product_id,
                    }
                },
                {
                    'row_id': f'__new_v2_{suffix}',
                    'is_new': True,
                    'fields': {
                        'name': unique_version_name,  # 同名 → 应失败
                        'code': f'V2_{suffix}',
                        'product_id': product_id,
                    }
                }
            ]
        },
        context={}
    )

    print(f"      result: success={version_result.get('success')}")
    print(f"      data.created = {version_result.get('data', {}).get('created')}")
    print(f"      data.failures = {version_result.get('data', {}).get('failures')}")
    print(f"      message = {version_result.get('message')}")

    # 4. 直接查 DB 验证
    print(f"\n[3/4] 直接查 DB 验证: 该 product 下有几个 version?")
    import sqlite3
    db_path = Path('d:/filework/excel-to-diagram') / 'meta' / 'architecture.db'
    if not db_path.exists():
        for p in [
            'd:/filework/excel-to-diagram/meta/architecture.db',
            'd:/filework/agent-batch-tx-worktree/meta/architecture.db',
        ]:
            if Path(p).exists():
                db_path = Path(p)
                break
    print(f"      db_path = {db_path}")
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    # [FIX 2026-06-18] 表名是 versions (不是 bo_record)
    cur.execute("SELECT id, name, product_id, code FROM versions WHERE product_id=?", (product_id,))
    rows = cur.fetchall()
    print(f"      SQL: SELECT id, name, product_id, code FROM versions WHERE product_id={product_id}")
    print(f"      rows: {rows}")
    version_count = len(rows)
    conn.close()

    # 5. 清理
    print(f"\n[4/4] 清理: 删除产品 {product_id}")
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("DELETE FROM versions WHERE product_id=?", (product_id,))
        cur.execute("DELETE FROM products WHERE id=?", (product_id,))
        conn.commit()
        conn.close()
        print(f"      cleanup done")
    except Exception as e:
        print(f"      cleanup error: {e}")

    # 6. 断言
    print("\n" + "=" * 60)
    print(f"[VERIFICATION: {scenario_name}]")
    print("=" * 60)
    print(f"  - batch_save success (期望 False): {version_result.get('success')}")
    print(f"  - DB 中该 product 的 version 数 (期望 0): {version_count}")

    assert version_result.get('success') is False, "失败时 batch_save 应返回 success=False"
    assert version_count == 0, f"事务未回滚! DB 中仍有 {version_count} 个 version, rows={rows}"
    print(f"\n[PASS: {scenario_name}] 整批回滚生效! bug 修复闭环验证通过")
    return True


def _run_test():
    """运行所有闭环测试场景"""
    # 场景 1: 用户报告的原始 TEST111 场景
    _run_test_scenario("TEST111", "V11", "场景1-用户报告TEST111")

    # 场景 2: 通用测试名
    _run_test_scenario("TEST_CLOSED_LOOP", "V_DUP", "场景2-通用")

    return True


if __name__ == '__main__':
    try:
        closed_loop_test()
    except AssertionError as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n[ERROR] {e}")
        sys.exit(1)
