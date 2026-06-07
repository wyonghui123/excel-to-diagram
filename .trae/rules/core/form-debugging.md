# 表单渲染问题排查铁律

> 最后更新: 2026-06-07 | 状态: 活跃
> 拆分自 project_rules.md（原第 1083-1190 行）
> **背景**：2026-05-25 一次简单的"下拉框不显示/保存无效"问题耗时 20+ 轮对话才修完。

## 铁律 1：先验证数据，再改代码

任何表单渲染问题（下拉无选项、显示 `-`、保存无效），第一步永远是：

```bash
# 1. 验证后端 API 返回什么（不需要写文件，一行命令）
python -c "
import urllib.request, json
login=json.dumps({'username':'admin','password':'admin123'}).encode()
req=urllib.request.Request('http://localhost:3010/api/v1/auth/login',data=login,headers={'Content-Type':'application/json'})
r=json.loads(urllib.request.urlopen(req).read())
token=r['data']['token']
req2=urllib.request.Request('http://localhost:3010/api/v2/meta/{OBJECT}/view-config/default',headers={'Authorization':f'Bearer {token}'})
r2=json.loads(urllib.request.urlopen(req2).read())
[f for f in r2['data']['fields'] if f['id']=='{FIELD}']
"
```

**[X] 禁止**：在未验证 API 返回值的情况下推演代码逻辑。

## 铁律 2：确认三层缓存全部失效

修改 YAML 或 Python 代码后，以下缓存必须依次清除：

| 缓存层 | 位置 | 清除方式 |
|--------|------|---------|
| YAML registry | 后端内存 | `POST /api/v1/meta/reload` |
| 前端 metaService | src/services/metaService.js | `Ctrl+Shift+R` 硬刷新浏览器 |
| 浏览器 HTTP | Browser cache | `Ctrl+Shift+R` 硬刷新浏览器 |

```bash
python -c "import urllib.request; urllib.request.urlopen(urllib.request.Request('http://localhost:3010/api/v1/meta/reload',method='POST'))"
```

**[X] 禁止**：改了 YAML 后告诉用户"重启前端就行" -- 必须先 reload 后端。

## 铁律 3：列表和详情是两套渲染链路

同一个字段在列表页和详情页走完全不同的渲染逻辑：

| 页面 | 组件 | 判断函数 | 数据来源 |
|------|------|---------|---------|
| 列表 | MetaListPage.vue | isBadgeColumn() / getBadgeDisplayValue() | metaConfig.value.fields |
| 新建/编辑 | ObjectPage.vue | valueHelpFieldKeys / getFieldWidget() | autoFieldDefs.value |
| 详情 Drawer | DetailPage.vue | computedSections -> ObjectPage | entityMeta.value |

**[X] 禁止**：修了一个页面的渲染逻辑后假设其他页面也生效。

## 铁律 4：Vue v-for key 不变时模板分支不会重新求值

当 `autoFieldDefs` 从 `{}` 变为有值后，`v-for="fieldKey in group.fields" :key="fieldKey"` 的 key 没变，Vue 复用旧 vnode，`v-else-if` 条件不会重新执行。

正确做法 -- 使用 formRenderKey 强制重建：

```javascript
const formRenderKey = ref(0)
// loadFieldMeta 完成后
autoFieldDefs.value = defs
formRenderKey.value++  // force re-render

// template
<template v-for="fieldKey in group.fields" :key="`${fieldKey}-${formRenderKey}`">
```

或者使用 ref Set 做判断而非 computed：

```javascript
const valueHelpFieldKeys = ref(new Set())
valueHelpFieldKeys.value = new Set(Object.entries(defs).filter(([,d]) => d.widget === 'value_help').map(([k]) => k))
// template
v-else-if="valueHelpFieldKeys.has(fieldKey)"
```

## 铁律 5：已知硬编码问题速查

| 问题 | 文件 | 根因 |
|------|------|------|
| hidden_in_form 不生效 | models.py#L547 + yaml_loader.py#L508 | UIAnnotation 类缺字段 + parse_ui_annotation 不提取 |
| enum 下拉无选项 | value_help_providers.py#L21 | EnumValueHelpProvider 只查 DB，表无数据时返回空 |
| is_system 保存无效 | DetailPage.vue#L896 | 硬编码为 SYSTEM_FIELDS，save 时被跳过 |
| boolean 枚举显示 `-` | MetaListPage.vue#L900 | rawValue==null 直接 return '-'， DB 部分记录为 NULL |

## 铁律 6：Python 代码修改必须重启后端

任何 .py 文件修改后必须重启 Python 进程。
YAML 改动可以 meta/reload，.py 代码改动不行。

## 铁律 7：排查顺序速查卡

```
收到"XX字段没有下拉/显示不对/保存无效"反馈时：

Step 1: Python 一行命令调 /api/v2/meta/{object}/view-config/default
        -> 检查 fields 中目标字段的 widget / enum_values / value_help / hidden_in_form

Step 2: Python 一行命令调 /api/v2/bo/{object}?page=1&page_size=5
        -> 检查实际数据的类型（true/false/1/0/null）

Step 3: POST /api/v1/meta/reload 清除后端缓存

Step 4: F12 硬刷新 -> Network 面板确认前端拿到了正确数据

Step 5: 如果前4步都正确 -> 再去看前端渲染代码
```

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-07 | AI Assistant | 从 project_rules.md 拆分 |
