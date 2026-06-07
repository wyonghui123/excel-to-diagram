# -*- coding: utf-8 -*-
"""
为现有测试数据补充备注测试数据
"""

import sqlite3
from datetime import datetime

conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

annotations = [
    ('domain', 1, 'important', '核心业务领域，需要重点关注系统稳定性和性能优化'),
    ('domain', 2, 'info', '支撑业务领域，为核心业务提供基础服务'),
    ('domain', 3, 'tip', '建议增加自动化测试覆盖率'),
    ('sub_domain', 1, 'important', '采购审批流程核心模块，涉及多级审批'),
    ('sub_domain', 2, 'info', '库存管理模块，支持多仓库管理'),
    ('sub_domain', 3, 'warning', '销售服务模块，需要注意并发处理'),
    ('service_module', 1, 'important', '采购申请服务，需要审批流程支持'),
    ('service_module', 2, 'info', '采购订单服务，支持批量导入'),
    ('service_module', 3, 'tip', '采购合同服务，建议增加电子签章功能'),
    ('business_object', 1, 'important', '采购申请单，核心业务对象'),
    ('business_object', 2, 'info', '采购申请明细，关联采购申请单'),
    ('business_object', 3, 'warning', '采购订单，需要注意状态流转'),
    ('relationship', 1, 'info', '采购申请单 -> 采购订单，一对多关系'),
    ('relationship', 3, 'important', '核心业务关系，需要保证数据一致性'),
]

created_at = datetime.now().isoformat()

for target_type, target_id, category, content in annotations:
    cursor.execute('''
        INSERT INTO annotations (target_type, target_id, category, content, created_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (target_type, target_id, category, content, created_at, 'admin'))

conn.commit()

cursor.execute('SELECT COUNT(*) FROM annotations')
count = cursor.fetchone()[0]
print(f"成功插入 {len(annotations)} 条备注数据，当前共有 {count} 条备注")

cursor.execute('''
    SELECT target_type, category, content 
    FROM annotations 
    ORDER BY created_at DESC 
    LIMIT 5
''')
print("\n最近插入的备注：")
for row in cursor.fetchall():
    print(f"  [{row[0]}] {row[1]}: {row[2][:30]}...")

conn.close()
