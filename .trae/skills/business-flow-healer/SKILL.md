---
name: business-flow-healer
description: Analyze failed Playwright tests, suggest fixes via IDE dialog, apply only after user confirmation. CRITICAL: Never fix business assertion failures automatically.
triggers:
  - "测试失败"
  - "修复这个失败"
  - "/heal"
  - "h"
  - 业务流 spec 跑失败时自动触发
---

# business-flow-healer

> **版本**: 1.0
> **状态**: Active
> **注册 ID**: SK-024
> **依赖**: `.trae/skills/healer/PERMISSIONS.md`

## 1. 必读上下文

- `.trae/skills/healer/PERMISSIONS.md` (deny list)
- `.trae/state/healings.jsonl` (历史)
- 失败 trace.zip
- 业务流 spec.js

## 2. Pipeline

### Stage 1: 失败分析
- 解析 trace.zip
- 判断 `root_cause`:
  - `locator_drift` - 选择器变更
  - `wait_timeout` - 等待超时
  - `data_mismatch` - 数据不匹配
  - `business_assertion` - **业务断言失败** (不修复)
  - `network_error` - 网络错误
  - `unknown` - 未知

### Stage 2: 业务断言失败 → 不修复
- 如果 `root_cause == "business_assertion"`:
  - 调用 MCP `show_dialog`:
    ```
    ❌ 业务断言失败 - 需要人工 review
    
    规则: BR-business_object-DEL-condition
    错误: 存在关联关系的业务对象不能删除 (实际 1)
    
    [查看业务规则] [跳转 YAML] [忽略]
    ```
  - 选项: 查看业务规则 / 跳转到相关业务流 YAML / 忽略
  - **永远不自动修复业务断言**

### Stage 3: UI/数据问题 → 人在回路修复
- 如果 `root_cause ∈ {locator_drift, wait_timeout, data_mismatch}`:
  - 检查 `healer/PERMISSIONS.md` deny list
  - **安全模块** (authService / permissionService / crypto) → 拒绝修复
  - 生成修复建议
  - 调用 MCP `show_dialog`:
    ```
    🔧 失败原因: locator 漂移
    建议修复: 将 '.el-button--primary' 替换为 role=button[name='保存']
    
    [Apply Fix]  [Edit Manually]  [Mark as Bug]  [Skip]
    ```
  - 选项:
    - **Apply Fix** → 应用并重跑
    - **Edit Manually** → 打开 spec.js
    - **Mark as Bug** → 写入 fix_tasks.json
    - **Skip** → 标记为预期失败

### Stage 4: 修复日志
- 写入 `.trae/state/healings.jsonl`:
  ```json
  {
    "trace_id": "uuid-32-chars",
    "spec_path": "e2e/business-flow/<feat>.spec.js",
    "root_cause_slug": "locator_drift",
    "fix_strategy": "role-based_replacement",
    "iterations": 1,
    "status": "healed|denied|failed",
    "duration_ms": 1234
  }
  ```

## 3. 修复策略(借鉴 2026 业界)

| 策略 | 适用 | 实现 |
|------|------|------|
| `role_based_replacement` | locator_drift | CSS → role-based locator |
| `wait_backoff` | wait_timeout | 智能 backoff 200-2000ms |
| `a11y_tree_fallback` | locator_drift | DOM 不稳定时回退 a11y |
| `data_correction` | data_mismatch | 从 trace 提取正确数据 |

## 4. 人在回路(关键)

**永远不自动应用修复**,必须用户在 IDE 弹窗中点击 [Apply Fix] 才应用。

业务断言失败 → 直接报错,不提议修复。

## 5. 关联

- 触发: 测试失败 / chat: "/heal" / "修复这个失败"
- 输入: trace.zip + spec.js
- 输出: 修复建议(经用户确认后应用)
- 写入: `.trae/state/healings.jsonl`
