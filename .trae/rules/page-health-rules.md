# 页面健康检测规范

> **智能体必须在关键操作前检查页面健康状态，在测试结束时断言健康状态。**

## 为什么需要健康检测？

### Headless 浏览器的"时序陷阱"

| 时间点 | 发生的事件 | 旧版工具状态 | Playwright v1.40+ |
|--------|-----------|-------------|------------------|
| T0-T3 | 框架初始化、hydration | 未初始化 | **已初始化** |
| T4 | 抛出 JavaScript 错误 | 未初始化 | **正在捕获** |
| T7-T8 | 页面加载完成，注入捕获代码 | **已错过错误** | 已捕获完成 |

**结论**：Playwright v1.40+ 是目前原生错误捕获能力最强的工具。

### 常见阻断性错误类型

| 错误类型 | 示例 | 后果 |
|---------|------|------|
| **循环依赖** | `ReferenceError: Cannot access 'ObjectPage' before initialization` | 页面白屏 |
| **WebSocket 失败** | `WebSocket connection failed: Unexpected response code: 400` | HMR 失效 |
| **未捕获的 Promise** | `UnhandledPromiseRejectionWarning` | 功能异常 |
| **Vue 渲染错误** | `Uncaught Error: Cannot read property of undefined` | 组件崩溃 |
| **页面崩溃** | `Page crashed` | 完全不可用 |

## 四层错误检测机制

PlaywrightCLI 已实现完整的四层检测：

### 1. JavaScript 运行时错误（最关键）

```python
# 自动捕获
page.on('pageerror', error => {
    _page_errors.append({
        'type': 'pageerror',
        'message': str(error),
        'stack': error.stack
    })
})
```

**捕获的错误类型**：
- `ReferenceError` - 变量未定义
- `TypeError` - 类型错误
- `SyntaxError` - 语法错误
- `RangeError` - 范围错误

### 2. 控制台错误/警告

```python
page.on('console', msg => {
    if msg.type in ('error', 'warning'):
        _console_errors.append({
            'type': 'console',
            'level': msg.type,
            'text': msg.text
        })
})
```

**捕获的错误类型**：
- `console.error()` 输出
- `console.warn()` 输出
- 框架警告（Vue、React 等）

### 3. 页面崩溃

```python
page.on('crash', () => {
    _page_crashed = True
})
```

**触发条件**：
- 浏览器标签页崩溃
- 内存溢出
- 进程被杀死

### 4. Vue 应用错误

```python
vue_errors = page.evaluate("() => window.__appErrors || []")
```

**捕获的错误类型**：
- Vue 组件渲染错误
- 生命周期钩子错误
- 响应式系统错误

## 标准使用方式

### 方式 1：关键操作前检查

```python
with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/target-page')
    
    # 关键操作前检查健康状态
    health = cli.check_health()
    if not health['healthy']:
        print(f"页面不健康: {health['summary']}")
        print(f"详细信息: {health['details']}")
        # 诊断问题，不要继续测试
    
    # 继续操作
    cli.click('.submit-button')
```

### 方式 2：测试结束断言（推荐）

```python
def test_example():
    with PlaywrightCLI() as cli:
        cli.authenticated_navigate('/target-page')
        cli.click('.submit-button')
        # ... 其他操作 ...
        
        # 测试结束前断言健康状态
        cli.assert_healthy()  # 如果有错误，抛出 PageHealthError
```

### 方式 3：自动健康守卫

PlaywrightCLI 在关键操作前会自动检查：

```python
# click() 方法内部会调用 _guard_health()
def click(self, selector: str, ...):
    self._guard_health('click')  # 如果有 page_errors，抛出异常
    # ... 执行点击 ...
```

## 错误诊断流程

```
发现页面不健康
  ↓
查看 health['details']
  ├─ page_errors: JavaScript 运行时错误
  ├─ console_errors: 控制台错误
  ├─ vue_errors: Vue 应用错误
  └─ health_failures: 其他健康检查失败
  ↓
分析错误类型
  ├─ ReferenceError → 循环依赖或变量未定义
  ├─ TypeError → 类型不匹配
  ├─ WebSocket 错误 → Vite HMR 配置问题
  └─ Vue 渲染错误 → 组件逻辑问题
  ↓
定位错误位置
  ├─ 查看 stack trace
  ├─ 找到对应的源文件
  └─ 修复代码
  ↓
重新测试
```

## 禁止行为

| 禁止 | 后果 |
|------|------|
| 不检查健康状态就操作 | 可能操作失败，浪费时间调试 |
| 测试结束不调用 `assert_healthy()` | 阻断性错误被忽略，生产环境出问题 |
| 忽略 `check_health()` 返回的错误 | 错误累积，难以诊断 |
| 看到 `ReferenceError` 不处理 | 循环依赖会导致整个应用崩溃 |

## 行业最佳实践参考

| 实践 | 说明 |
|------|------|
| Fail-Fast | 发现错误立即停止，不要继续测试 |
| Trace Viewer | Playwright 的 `trace: 'on-first-retry'` 记录失败现场 |
| 错误汇总 | 测试结束时汇总所有错误，一次性报告 |
| 分层检测 | 四层检测机制确保不遗漏任何错误 |

Sources:
- [Headless浏览器的隐形陷阱](https://juejin.cn/post/7642221657361596416)
- [Playwright Event & Error Handling](https://blimto.com/concepts/playwright/playwright-event-and-error-handling)
- [How to Detect JavaScript Errors in Automated Tests](https://maestro.dev/insights/how-to-detect-javascript-errors-in-automated-tests)
