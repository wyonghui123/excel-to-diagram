# SPEC: wyonghui 在 TTTTT000/V11 下能看到 13 个域（应为 1 个供应链云）

## 任务概述
定位 user_id=10006 (wyonghui) 通过 TEST888 用户组 → scmgrp 角色 → role_dimension_scopes[domain=2200] 配置
应该仅看到 TTTTT000 / V11 下的 1 个供应链云域，实际可见 13 个域。

## 涉及文件（白名单）
- d:\filework\agent-dpiprint-worktree\meta\core\interceptors\data_permission_interceptor.py
- d:\filework\agent-dpiprint-worktree\meta\services\dimension_scope_engine.py
- d:\filework\agent-dpiprint-worktree\meta\core\interceptors\base.py  (查询/条件定义)

## 涉及文件（黑名单，绝对禁止修改）
- d:\filework\excel-to-diagram\**    (主工作树)
- d:\filework\worktrees/integration\**  (integration 主仓, 别人在跑)
- d:\filework\.git\**                  (git metadata)
- meta/server.py 除非必要（本任务只关心 interceptor 层）

## 调查步骤
1. 在 DPI 关键路径加 print (logger.info 改成 print 也可)
2. 启动 worktree 后端到端口 3015 (AGENT_PORT)
3. dev-login wyonghui, 调 `GET /api/v2/bo/domain?version_id=863`
4. 收集 stdout, 定位根因
5. 修复方案：
   - 若 dimension scope 没真被 SQL 消费 → 在 DPI 内强制包 QueryCondition
   - 若 derive_data_conditions 没产出 domain cond → 在 engine 加 fallback
   - 若两者都没问题 → 必有第三方原因，继续追

## 完成标准
- [ ] Wyonghui 经 TEST888 组 → 调 `GET /api/v2/bo/domain?version_id=863` 返回 = 1 个域(2200 供应链云)
- [ ] 不影响 admin / 其他角色
- [ ] 单测覆盖 `test_dimension_scope_for_user_via_group.py`
- [ ] commit + handover to PM
