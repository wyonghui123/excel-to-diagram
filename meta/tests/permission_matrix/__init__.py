# meta/tests/permission_matrix/
#
# [SPEC] FR-006: 权限回归测试矩阵 (annotation-permission-hardening)
#
# 测试范围:
# - annotation 权限: orphan 硬拒, visibility 继承, 决策埋点
# - PERMISSION_GUARD_MODE 灰度开关
# - 文档契约 (annotation_routes_api docstring + permission-contract.md)
#
# 运行方式:
#   cd d:/filework/excel-to-diagram
#   pytest meta/tests/permission_matrix/ -v