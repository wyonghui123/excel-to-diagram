# 服务器管理规范

> 最后更新: 2026-06-07 | 状态: 活跃
> 拆分自 project_rules.md（原第 184-202 行）

## 重启后端服务流程

### 1. 强制终止旧进程

- 使用 `taskkill /F /PID <pid>` 而不是优雅终止
- 原因：Flask Debug 模式的 stat reloader 会在终止后立即重启进程

### 2. 检测服务状态

- 使用 `Test-NetConnection` 而不是 `Invoke-WebRequest`

```powershell
# [OK] 正确
Test-NetConnection -ComputerName localhost -Port 5000 -InformationLevel Quiet

# [X] 错误 - 会卡住
Invoke-WebRequest -Uri "http://localhost:5000/..."
```

### 3. 启动服务

- 使用分号分隔命令

```powershell
cd d:\filework\excel-to-diagram; python -m meta.server
```

## 开发约定

### 消息通知服务 (CRUD 操作反馈)

所有 CRUD 操作（创建、读取、更新、删除）必须提供用户反馈，使用全局消息服务：

```javascript
import { useMessage } from '@/composables/useMessage'
const message = useMessage()

// [OK] 正确用法
async function handleSave() {
  try {
    const resp = await fetch('/api/...', { method: 'POST', ... })
    const data = await resp.json()
    if (data.success) {
      message.success('保存成功')
    } else {
      message.error(data.message || '保存失败')
    }
  } catch (e) {
    message.error('网络错误，请重试')
  }
}

async function handleDelete(id) {
  if (!confirm('确定删除？')) return
  try {
    const resp = await fetch(`/api/.../${id}`, { method: 'DELETE', ... })
    const data = await resp.json()
    if (data.success) {
      message.success('删除成功')
      await loadData()
    } else {
      message.error(data.message || '删除失败')
    }
  } catch (e) {
    message.error('网络错误，请重试')
  }
}

// [X] 禁止使用 alert()
alert('操作成功')  // 不允许
alert('操作失败')  // 不允许
```

**消息类型：**

- `message.success('操作成功')` - 成功操作
- `message.error('错误信息')` - 错误提示
- `message.warning('警告信息')` - 警告提示
- `message.info('提示信息')` - 一般信息

### 导出功能

- 导出列名优先使用字段的 `ui.title` 配置
- 版本/产品线列通过 `default_exclude_fields` 排除
- 层级相关字段（父对象_name）不导出，通过 `hierarchy_fields` 排除
- Virtual 字段如需导出，需设置 `export_visible: true`

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-07 | AI Assistant | 从 project_rules.md 拆分 |
