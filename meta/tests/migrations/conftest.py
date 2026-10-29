# -*- coding: utf-8 -*-
"""
migrations 子目录 pytest 配置

[NEW 2026-10-29] 排除脚本型伪测试:
test_e2e_verify.py 模块顶层连接硬编码 DB 路径
(D:\\filework\\worktrees/release-prep/meta/architecture.db), 该路径在普通
开发环境不存在 → import 期抛 sqlite3.OperationalError ('unable to open
database file'), 整个收集期 exit 2, 堵死 --failed 通道。

该文件不是 pytest 用例 (0 个 def test_*), 仅供手工脚本执行, 故排除出收集面。
"""

collect_ignore = ['test_e2e_verify.py']
