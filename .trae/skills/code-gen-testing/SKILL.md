---
name: "code-gen-testing"
description: "代码生成测试工作流。Token 效率最高 (~7.5K/任务)。AI 生成 Playwright 脚本执行，只返回结果。适用于回归测试和 CI 自动化。"
---

# 代码生成测试工作流

> **核心原理**：AI 生成代码执行，只返回最终结果，中间过程不占上下文
> **适用场景**：回归测试、CI 自动化、批量测试、生成可复用测试套件
> **浏览器工具规范：** `.trae/rules/SESSION_REMINDER.md` — 场景 A（自动化测试）禁止 MCP 工具，场景 B（开发调试）允许
> **验证方法**：`.trae/rules/browser-test-verification.md`

## 一、工作流程（5 步）

```
Step 1: INVOKE Skill — 加载测试工作流定义
Step 2: GENERATE    — AI 生成 Playwright 脚本
Step 3: EXECUTE     — 终端执行脚本
Step 4: RETURN      — 只返回最终结果
Step 5: VERIFY      — 如需修改，重复 Step 2-4
```

## 二、标准脚本模板

```python
import sys; sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import json

results = {'passed': False, 'steps': [], 'screenshot': '', 'error': ''}

with PlaywrightCLI() as cli:
    try:
        cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-table')
        results['steps'].append('导航成功')

        # 表格验证
        table = cli.assert_table('.el-table')
        assert table['rowCount'] > 0, "表格为空"
        results['steps'].append(f"表格 {table['rowCount']} 行")

        # 三层追踪：操作 + 变化检测
        cli.start_all_tracking('.el-table')
        cli.click('.el-table__row:first-child .el-checkbox')
        cli.wait_for_stable()
        changes = cli.get_all_changes()
        results['steps'].append(f"操作触发 {len(changes['store'])} Store + {len(changes['dom'])} DOM 变化")

        # 一致性验证
        consistency = cli.verify_table_consistency('boCrud', '.el-table')
        assert consistency['ok'], f"数据不一致: {consistency}"

        # 错误检测
        err = cli.assert_no_errors()
        assert err['ok'], f"页面存在错误: {err['details']}"

        cli.screenshot('result.png')
        results['screenshot'] = 'result.png'
        results['passed'] = True

    except Exception as e:
        results['error'] = str(e)
        cli.screenshot('error.png')
        results['screenshot'] = 'error.png'

print(json.dumps(results, ensure_ascii=False, indent=2))
sys.exit(0 if results['passed'] else 1)
```

## 三、状态变更测试模板

```python
with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-table')

    # 快照 → 操作 → diff
    before = cli.snapshot()
    cli.click('.el-table__row:first-child .el-button:has-text("启用")')
    cli.wait_for_stable()
    after = cli.snapshot()
    diff = cli.diff_snapshots(before, after)

    # 验证变化
    if diff['changed']:
        print(f"状态变更: {json.dumps(diff['changes'], ensure_ascii=False)}")
    else:
        print("警告: 操作后无状态变化")

    err = cli.assert_no_errors()
    assert err['ok'], f"页面存在错误: {err['details']}"
```

## 四、表单验证模板

```python
with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-table')
    cli.click('.el-button:has-text("新建")')
    cli.wait_for_selector('.el-dialog', timeout=5000)

    # 填写表单
    cli.fill('input[placeholder*="名称"]', '测试对象')
    cli.click('.el-dialog .el-button:has-text("确定")')

    # 等待稳定 + 自动检测错误
    cli.wait_for_stable()
    err = cli.assert_no_errors()
    assert err['ok'], f"保存失败: {err['details']}"

    # 验证新增行出现
    cli.wait_for_selector('.el-table__row', timeout=10000)
    table = cli.assert_table('.el-table')
    assert table['rowCount'] > 0, "新增后表格为空"
```

## 五、最佳实践

### 5.1 必须用 `with` 语句

```python
# [OK] 推荐 — with 自动清理
with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-table')

# [X] 禁止 — 异常时泄露浏览器进程
cli = PlaywrightCLI()
cli.authenticated_navigate(...)
```

### 5.2 永远输出 JSON 结果

```python
# 末尾输出 JSON，方便 AI 解析
print(json.dumps(results, ensure_ascii=False, indent=2))
```

### 5.3 超时设置

```python
TIMEOUT_NAVIGATION = 15000   # 页面导航
TIMEOUT_ELEMENT = 5000       # 元素操作
TIMEOUT_STATE_CHANGE = 10000 # 状态变更
```

### 5.4 验证方法速查

> 完整方法表见 `.trae/rules/browser-test-verification.md`

| 场景 | 方法 |
|------|------|
| 表格渲染 | `cli.assert_table('.el-table')` |
| 操作变化 | `cli.verify_action(js, store_name)` |
| 三层追踪 | `cli.start_all_tracking()` + `cli.get_all_changes()` |
| 智能等待 | `cli.wait_for_stable()` |
| 数据一致性 | `cli.verify_table_consistency('boCrud', '.el-table')` |
| 错误检测 | `cli.assert_no_errors()` |