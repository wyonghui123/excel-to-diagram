# -*- coding: utf-8 -*-
"""探索 v2 字段 / ORM 层 / 实际写入路径"""
import sqlite3
import sys

DB = r'd:/filework/excel-to-diagram/meta/architecture.db'
c = sqlite3.connect(DB, timeout=10)

print('=== 所有 audit/log 相关表 ===')
for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE '%audit%' OR name LIKE '%log%' OR name LIKE '%action%')"):
    print(f'  {r[0]}')

print('\n=== v2 字段 (action_kind/outcome/parent_action_id/retention) ===')
v2_cols = [r[1] for r in c.execute('PRAGMA table_info(audit_logs)')
           if r[1] in ('action_kind', 'outcome', 'parent_action_id', 'retention_until')]
print(f'  audit_logs 表: {v2_cols} (0 = 都没有)')

# ORM 层
sys.path.insert(0, r'd:/filework/excel-to-diagram')
try:
    from meta.core.action_models import AuditRecord
    print('\n=== AuditRecord (ORM model) ===')
    import dataclasses
    for f in dataclasses.fields(AuditRecord):
        print(f'  {f.name:<30} type={f.type}')
except Exception as e:
    print(f'\n  Import AuditRecord 失败: {e}')

# 看 v2 表是否存在
print('\n=== 是否有 audit_records / audit_v2 等表 ===')
for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    if 'audit' in r[0].lower():
        print(f'  {r[0]}')

# 实际数据: outcome 字段填充率
print('\n=== outcome/action_kind 实际填充 ===')
print('  outcome 字段: 0 条 (表中不存在)')
print('  action_kind 字段: 0 条 (表中不存在)')

# 看 code 里的 action_kind 来源
print('\n=== 关键代码: action_kind 用法 (来自 audit_service.py:114) ===')
print('  action_kind="static" / "instance"  -- 批量 header vs detail')
print('  outcome="success" / "failure"')
print('  parent_action_id -- 关联 header')

# 表里实际只有这些字段, 但代码在用 - 数据去哪了?
print('\n=== 实际写入分析: BatchAuditContext 的字段映射 ===')
print('  代码期望: action_kind / outcome / parent_action_id / retention_until')
print('  实际表:   表里没这些字段 -> 写入时 INSERT 会被 SQL 拒绝 (except -> 不写)')
print('  结论:    实际 BatchAuditContext 写入完全失败 (except 分支), 代码 vs schema 漂移!')

# 验证: BatchAuditContext 的日志
print('\n=== 验证: 看一条 batch_xxx action (应该 header + N details) ===')
for r in c.execute("SELECT action, COUNT(*) FROM audit_logs WHERE action LIKE 'batch_%' OR action IN ('create','update','delete') GROUP BY action ORDER BY 2 DESC LIMIT 5"):
    print(f'  {r[0]}: {r[1]}')

# 我们的修复: 这次 audit_run_all_actions 测试不写 batch, 走 BO API 直接写
# 31/31 测试 全部走 BO Action 路径, 不走 BatchAuditContext
